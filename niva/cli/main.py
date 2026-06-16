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

_USAGE = (
    'usage: niva run <file.niva> [--dry-run|--explain]\n'
    '       niva "<flow>"        [--dry-run|--explain]\n'
    "       niva describe <verb-or-algorithm-id>\n"
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
        del argv[i:i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    if argv[0] == "describe":
        return _describe(argv[1:])
    if argv[0] in ("export", "import"):
        return _convert(argv[0], argv[1:])

    try:
        source, text = _read_source(argv)
        if text is None:
            return 2
        program = parse(text, file=None if source == "<inline>" else source)
        base_dir = None if source == "<inline>" else os.path.dirname(os.path.abspath(source))

        if mode == "explain":
            _print_plan(program, source)
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
    return "<inline>", argv[0]


def _convert(kind: str, args) -> int:
    """`niva export <file.niva>` → PyQGIS .py; `niva import <file.py>` → .niva.
    Writes to ``-o <out>`` or stdout. Import warnings go to stderr (non-fatal)."""
    out = None
    if "-o" in args:
        i = args.index("-o")
        out = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
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
            text, source_name=os.path.basename(args[0]),
            out_name=os.path.basename(out) if out else "out.py", file=args[0],
        )
    else:  # import
        result, warnings = import_script(text)
        for w in warnings:
            print(f"niva import: {w}", file=sys.stderr)
        if not result.strip():
            print("niva import: no processing.run(...) calls found — nothing to import",
                  file=sys.stderr)
            return 1

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(result)
        print(f"niva: wrote {out}", file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


def _describe(args) -> int:
    if len(args) != 1:
        print("usage: niva describe <verb-or-algorithm-id>", file=sys.stderr)
        return 2
    from .. import describe as _describe_fn

    code = 0
    try:
        print(_describe_fn(args[0]))
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 2
    except ImportError as exc:
        print(f"niva: describing an algorithm needs QGIS's Python [{exc}]", file=sys.stderr)
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
        app, owns = ensure_qgis()  # the qgis import happens here (lazy), so catch it here
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
        result = Engine(PyqgisBackend(), journal=journal, progress=progress).execute(
            program, base_dir=base_dir
        )
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


def _print_plan(program: list, source: str) -> None:
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
                continue
            alias = _REG.get(s.verb)
            if alias is None:
                print(f"     {s.verb}  (built-in: handled by the engine)")
                continue
            op = bind(s, alias)
            print(f"     {s.verb} → {op.algorithm}")
            print(f"         {op.input_param} ← upstream layer (engine fills)")
            for key, value in op.params.items():
                print(f"         {key} = {value!r}")
            print(f"         {op.output_param} ← output dest (engine fills)")


def _dry_run(program: list, base_dir=None) -> None:
    from ..engine import Engine, MockBackend

    backend = MockBackend()
    Engine(backend).execute(program, base_dir=base_dir)  # raises FlowError on an invalid flow
    print(f"\n# dry-run OK — {len(backend.calls)} backend operation(s) over MockBackend:")
    for call in backend.calls:
        if call[0] == "run":
            print(f"     run {call[1]}  {call[2]}")
        else:
            print(f"     {call[0]} {call[1]}")


if __name__ == "__main__":
    raise SystemExit(main())
