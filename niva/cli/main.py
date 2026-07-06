"""niva CLI entry point (docs/planning/11-cli-and-api-reference.md).

Modes:
- default — **execute** the flow for real via the PyQGIS backend (needs QGIS;
  run with QGIS's own Python).
- ``--dry-run`` — walk the flow through the engine over a no-QGIS ``MockBackend``,
  validating order and CRS/units, and print the backend operation sequence.
- ``--explain`` — parse + bind only; print the resolved algorithm and params for
  each stage. No execution, no QGIS.
"""

from __future__ import annotations

import os
import sys

from ..errors import FlowError, OpError
from ..grammar import Call, parse
from ..registry import bind, core_registry

_REG = core_registry()

# The closed set of valid verbs, for offline validation in --explain (issue #29). Built-ins
# come straight from the engine's dispatch table (+ each/call, handled specially there);
# aliases from the registry. Importing Engine is QGIS-free (its qgis imports are lazy).
from ..engine.engine import Engine as _Engine  # noqa: E402

_BUILTIN_VERB_NAMES = set(_Engine._BUILTIN_VERBS) | {"each", "call"}
_ALL_VERB_NAMES = _BUILTIN_VERB_NAMES | set(_REG.verbs())

_USAGE = (
    "usage: niva run <file.niva> [--dry-run|--explain]\n"
    '       niva "<flow>"        [--dry-run|--explain]\n'
    "       niva validate <file.niva> [more.niva …]   (offline linter)\n"
    '       niva plan <file.niva> | "<flow>"          (emit the resolved plan IR, JSON)\n'
    "       niva manifest [to=<file>]                 (machine-readable verb catalog, JSON)\n"
    "       niva describe <verb-or-algorithm-id>\n"
    "       niva pdal [check|test|setup]   (set up & test the point-cloud backend)\n"
    "       niva export <file.niva> [-o <file.py>]\n"
    "       niva import <file.py>   [-o <file.niva>]\n"
    "  (default executes via QGIS; --dry-run validates over a mock backend; "
    "--explain shows the plan)"
)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "execute"
    for flag in ("--dry-run", "--explain"):
        if flag in argv:
            argv = [a for a in argv if a != flag]
            mode = flag[2:]
    log = None
    if "--log" in argv:  # --log <base> → write <base>.jsonl + <base>.log
        i = argv.index("--log")
        log = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i : i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    if argv[0] == "describe":
        return _describe(argv[1:])
    if argv[0] == "validate":
        return _validate(argv[1:])
    if argv[0] == "plan":
        return _plan(argv[1:])
    if argv[0] == "manifest":
        return _manifest(argv[1:])
    if argv[0] == "pdal":
        from ..pdal_doctor import run as _pdal_doctor

        return _pdal_doctor(argv[1:])
    if argv[0] in ("export", "import"):
        return _convert(argv[0], argv[1:])

    try:
        source, text = _read_source(argv)
        if text is None:
            return 2
        program = parse(text, file=None if source == "<inline>" else source)
        base_dir = (
            None if source == "<inline>" else os.path.dirname(os.path.abspath(source))
        )

        if mode == "explain":
            # An unknown verb is a definitive error (the verb set is closed), so --explain
            # exits non-zero — a real offline gate for CI/agents (issue #29).
            if _print_plan(program, source):
                print("niva: flow has unknown verb(s) — see ⚠ above", file=sys.stderr)
                return 2
        elif mode == "dry-run":
            _print_plan(program, source)
            _dry_run(program, base_dir)
        else:
            return _execute(program, base_dir, source=source, log=log)
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 2
    except OpError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 3

    return 0


def _read_source(argv):
    if argv[0] == "run":
        if len(argv) < 2:
            print("niva run: missing <file.niva>", file=sys.stderr)
            return "<inline>", None
        with open(argv[1], encoding="utf-8") as fh:
            return argv[1], fh.read()
    # Inline mode: the program may arrive as one quoted argument
    # (`niva "show /path"`) or as several unquoted shell tokens
    # (`niva show /path`). Re-join the tokens so both forms work; a
    # single token joins to itself, so quoted usage is unchanged.
    return "<inline>", " ".join(argv)


def _convert(kind: str, args) -> int:
    """`niva export <file.niva>` → PyQGIS .py; `niva import <file.py>` → .niva.
    Writes to ``-o <out>`` or stdout. Import warnings go to stderr (non-fatal)."""
    out = None
    if "-o" in args:
        i = args.index("-o")
        out = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2 :]
    if len(args) != 1 or out is False:
        print(f"usage: niva {kind} <file> [-o <output>]", file=sys.stderr)
        return 2

    from ..transpile import export_script, import_script

    try:
        with open(args[0], encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 3

    if kind == "export":
        result = export_script(
            text,
            source_name=os.path.basename(args[0]),
            out_name=os.path.basename(out) if out else "out.py",
            file=args[0],
        )
    else:  # import
        result, warnings = import_script(text)
        for w in warnings:
            print(f"niva import: {w}", file=sys.stderr)
        if not result.strip():
            print(
                "niva import: no processing.run(...) calls found — nothing to import",
                file=sys.stderr,
            )
            return 1

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(result)
        print(f"niva: wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


def _describe(args) -> int:
    # Optional `to=<file>` writes the report to a text file (parity with the `describe`
    # flow verb and `show`/`info`'s `to=`); without it the report prints to stdout, which
    # the shell can still redirect (`niva describe buffer > buffer.md`).
    out = None
    positional = []
    for a in args:
        if a.startswith("to="):
            out = a[len("to=") :]
        else:
            positional.append(a)
    if len(positional) != 1:
        print(
            "usage: niva describe <verb-or-algorithm-id> [to=<file>]", file=sys.stderr
        )
        return 2
    from .. import describe as _describe_fn

    code = 0
    try:
        report = _describe_fn(positional[0])
        if out:
            out = os.path.expanduser(out)
            parent = os.path.dirname(out)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(report if report.endswith("\n") else report + "\n")
            print(f"niva: wrote {out}", file=sys.stderr)
        else:
            print(report)
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 2
    except ImportError as exc:
        print(
            f"niva: describing an algorithm needs QGIS's Python [{exc}]",
            file=sys.stderr,
        )
        code = 3
    except BaseException as exc:  # noqa: BLE001 — must still reach the safe teardown
        print(f"niva: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    finally:
        # If describing an algorithm bootstrapped a standalone QGIS, tear it down and
        # hard-exit (every path) to dodge the interpreter-shutdown segfault.
        from ..engine.pyqgis import owned_app

        app = owned_app()
        if app is not None:
            sys.stdout.flush()
            sys.stderr.flush()
            app.exitQgis()
            os._exit(code)
    return code


def _execute(program, base_dir=None, *, source="<inline>", log=None) -> int:
    from ..engine import Engine
    from ..engine.pyqgis import PyqgisBackend, ensure_qgis

    try:
        app, owns = (
            ensure_qgis()
        )  # the qgis import happens here (lazy), so catch it here
    except ImportError as exc:
        print(
            "niva: could not import QGIS — run niva with QGIS's own Python "
            f"(inside QGIS, or with PYTHONPATH set to its bindings). [{exc}]",
            file=sys.stderr,
        )
        return 3

    journal = None
    log = log or os.environ.get("NIVA_LOG")
    if log:
        from .. import __version__
        from ..journal import Journal

        journal = Journal(log).open(flow=source, niva_version=__version__)

    import time

    from ..engine.engine import _fmt_elapsed

    code = 0
    t0 = time.monotonic()
    try:
        progress = lambda msg: print(msg, file=sys.stderr, flush=True)  # noqa: E731
        from ..engine.native import wrap_native

        result = Engine(
            wrap_native(PyqgisBackend()), journal=journal, progress=progress
        ).execute(program, base_dir=base_dir)
        _print_result(result)
        print(f"# done in {_fmt_elapsed(time.monotonic() - t0)}")
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 2
    except OpError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 1
    except BaseException as exc:  # noqa: BLE001 — incl. KeyboardInterrupt: must still
        # reach the safe teardown below, or interpreter shutdown races QGIS's C++
        # teardown and segfaults. Surface a generic message; never leak past `finally`.
        print(f"niva: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    finally:
        if journal is not None:
            journal.close()
            print(f"# log: {os.path.abspath(journal.log_path)}")
        if owns:
            # Standalone run: tear QGIS down and hard-exit with our code before the
            # Python GC races QGIS's C++ teardown at interpreter shutdown (it
            # segfaults, clobbering the exit code). This runs for EVERY exit path —
            # success, handled error, or unexpected exception. Flush user output first.
            sys.stdout.flush()
            sys.stderr.flush()
            app.exitQgis()
            os._exit(code)
    return code


def _print_result(result) -> None:
    if result is None:
        print("# done (no output layer)")
        return
    count = ""
    fn = getattr(getattr(result, "ref", None), "featureCount", None)
    if callable(fn):
        try:
            count = f", {fn()} feature(s)"
        except Exception:
            count = ""
    print(f"# done — {result.kind}: {result.name or result.ref}{count}")


def _print_plan(program: list, source: str) -> bool:
    """Print the parse+bind plan. Returns True if any stage uses an **unknown verb**
    (not a built-in, alias, or `run` id) — the caller turns that into a non-zero exit."""
    unknown = False
    print(f"# parsed {source}: {len(program)} statement(s)")
    for i, st in enumerate(program, start=1):
        if isinstance(st, Call):
            print(f"{i}. call {st.target}")
            continue
        print(f"{i}. flow — {len(st.stages)} stage(s):")
        for s in st.stages:
            if s.verb == "run":  # the escape hatch — passed to QGIS verbatim
                algo = s.args[0] if s.args else "?"
                print(f"     run → {algo}  (raw)  {s.options}")
                for w in _run_warnings(algo, s.options):
                    print(f"       ⚠ {w}")
                continue
            alias = _REG.get(s.verb)
            if alias is None:
                # A non-alias verb is only valid if it is a real BUILT-IN. Do not assume —
                # an invented/misspelled verb ("compute", "stats", "reproj") lands here and
                # must be flagged, or --explain silently blesses it (issue #29).
                if s.verb in _BUILTIN_VERB_NAMES:
                    print(f"     {s.verb}  (built-in: handled by the engine)")
                else:
                    import difflib

                    unknown = True
                    near = difflib.get_close_matches(s.verb, _ALL_VERB_NAMES, n=1)
                    hint = f" — did you mean `{near[0]}`?" if near else ""
                    print(
                        f"     {s.verb}  ⚠ UNKNOWN VERB — not a built-in or alias{hint} "
                        "(use `run <provider:id> KEY=value` for a raw algorithm)"
                    )
                continue
            op = bind(s, alias)
            print(f"     {s.verb} → {op.algorithm}")
            print(f"         {op.input_param} ← upstream layer (engine fills)")
            for key, value in op.params.items():
                print(f"         {key} = {value!r}")
            print(f"         {op.output_param} ← output dest (engine fills)")
    return unknown


def _run_warnings(algo: str, options: dict) -> list:
    """`run <id>` id/param warnings for --explain — the shared offline check (issue #26)."""
    from ..validate import run_param_issues

    return run_param_issues(algo, options)


def _validate(paths) -> int:
    """`niva validate <file.niva> [more.niva …]` — a proper offline linter: grammar +
    closed-set verbs + alias arg/option/enum binding + `run <id>` params + best-practice lint,
    then a MockBackend dry-run so a passing flow is genuinely runnable. No QGIS. Exits non-zero
    if any file has an error (use it in CI / pre-commit)."""
    import glob

    from ..validate import validate_text

    if not paths:
        print("usage: niva validate <file.niva> [more.niva …]", file=sys.stderr)
        return 2
    files = []
    for p in paths:
        matches = sorted(glob.glob(p))
        files.extend(
            matches or [p]
        )  # keep a non-glob path so its "not found" is reported
    had_error = False
    n_err = n_warn = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"✗ {f}: {exc}", file=sys.stderr)
            had_error = True
            continue
        ok, issues = validate_text(text, file=f)
        errs = [i for i in issues if i[1] == "error"]
        warns = [i for i in issues if i[1] == "warning"]
        n_err += len(errs)
        n_warn += len(warns)
        mark = "✓" if ok and not warns else ("✗" if errs else "⚠")
        print(f"{mark} {f}")
        for line, sev, msg in sorted(issues, key=lambda i: (i[0], i[1])):
            loc = f"line {line}" if line else "flow"
            print(f"    {'error' if sev == 'error' else 'warn '}  {loc}: {msg}")
        if not ok:
            had_error = True
    print(f"# {len(files)} file(s): {n_err} error(s), {n_warn} warning(s)")
    return 1 if had_error else 0


def _plan(args) -> int:
    """`niva plan <file.niva> | "<flow>"` — emit the resolved plan IR as JSON (no QGIS).
    A `.niva` path is read; anything else is treated as an inline flow. Always exits 0
    (the plan is emitted even when invalid — read `diagnostics` for errors)."""
    import json

    from ..grammar import parse
    from ..plan import build_plan

    if not args:
        print('usage: niva plan <file.niva> | niva plan "<flow>"', file=sys.stderr)
        return 2
    if len(args) == 1 and os.path.isfile(args[0]):
        with open(args[0], encoding="utf-8") as fh:
            text, file = fh.read(), args[0]
    else:
        text, file = " ".join(args), None
    try:
        program = parse(text, file=file)
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(build_plan(program, file=file), indent=2, ensure_ascii=False))
    return 0


def _manifest(args) -> int:
    """`niva manifest [to=<file>]` — emit the machine-readable verb catalog as JSON
    (every verb: algorithm, params, defaults, synonyms, example). No QGIS."""
    import json

    from ..manifest import build_manifest

    out = None
    for a in args:
        if a.startswith("to="):
            out = os.path.expanduser(a[len("to=") :])
    text = json.dumps(build_manifest(), indent=2, ensure_ascii=False)
    if out:
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"niva: wrote {out}", file=sys.stderr)
    else:
        print(text)
    return 0


def _dry_run(program: list, base_dir=None) -> None:
    from ..engine import Engine, MockBackend

    backend = MockBackend()
    # inert=True: a dry-run validates order/CRS/units without any outward side effect
    # (no report/catalog writes, no `remove` deletions, no notify/email sends).
    Engine(backend, inert=True).execute(
        program, base_dir=base_dir
    )  # raises FlowError on an invalid flow
    print(
        f"\n# dry-run OK — {len(backend.calls)} backend operation(s) over MockBackend:"
    )
    for call in backend.calls:
        if call[0] == "run":
            print(f"     run {call[1]}  {call[2]}")
        else:
            print(f"     {call[0]} {call[1]}")


if __name__ == "__main__":
    raise SystemExit(main())
