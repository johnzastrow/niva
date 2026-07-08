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
    '       niva explain <file.niva> | "<flow>"       (human view of the resolved plan)\n'
    "       niva manifest [to=<file>]                 (machine-readable verb catalog, JSON)\n"
    "       niva search <keyword> [limit=N] [--json]  (fuzzy + synonym-aware discovery, offline)\n"
    "       niva find [glob] [in <dir>…] [--geom …] [--crs …] [--json|--as-flow|--paths|-0]  (discover data)\n"
    "       niva setup [doctor|wizard|show|init|path|get <k>|set <k> <v>|unset <k>]  (doctor: health check; wizard: guided config)\n"
    "       niva describe <verb-or-algorithm-id>\n"
    "       niva repl                                  (interactive authoring; Tab completion with the [cli] extra)\n"
    "       niva lsp                                   (Language Server over stdio: completion/diagnostics/hover in your editor)\n"
    "       niva pdal [check|test|setup]   (set up & test the point-cloud backend)\n"
    "       niva export <file.niva> [-o <file.py>]\n"
    "       niva import <file.py>   [-o <file.niva>]\n"
    "  (default executes via QGIS; --dry-run validates over a mock backend; "
    "--explain shows the plan)"
)


# Options to `niva find` that consume a following value (`--geom polygon`).
_FIND_VALUE_FLAGS = frozenset(
    {
        "--geom",
        "--crs",
        "--has-field",
        "--format",
        "--newer-than",
        "--min-size",
        "--max-size",
        "--min-features",
        "--max-features",
        "--max-depth",
        "--limit",
        "--in",
    }
)


def _err(msg: object) -> None:
    """One error line to stderr: a red ``niva:`` prefix + ``msg`` (colour auto-off off-TTY)."""
    from .. import color

    print(f"{color.paint('niva:', 'red', 'bold')} {msg}", file=sys.stderr)


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
    if argv[0] == "search":
        return _search(argv[1:])
    if argv[0] == "find":
        return _find(argv[1:])
    if argv[0] == "explain":
        return _explain(argv[1:])
    if argv[0] == "manifest":
        return _manifest(argv[1:])
    if argv[0] == "setup":
        return _setup(argv[1:])
    if argv[0] == "repl":
        from .repl import run as _repl

        return _repl(argv[1:])
    if argv[0] == "lsp":
        from ..lsp import run as _lsp

        return _lsp(argv[1:])
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
                _err("flow has unknown verb(s) — see ⚠ above")
                return 2
        elif mode == "dry-run":
            _print_plan(program, source)
            _dry_run(program, base_dir)
        else:
            return _execute(program, base_dir, source=source, log=log)
    except FlowError as exc:
        _err(exc)
        return 2
    except OpError as exc:
        _err(exc)
        return 1
    except OSError as exc:
        _err(exc)
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
        _err(exc)
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
        _err(exc)
        code = 2
    except ImportError as exc:
        _err(f"describing an algorithm needs QGIS's Python [{exc}]")
        code = 3
    except BaseException as exc:  # noqa: BLE001 — must still reach the safe teardown
        _err(f"unexpected error: {type(exc).__name__}: {exc}")
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
        _err(
            "could not import QGIS — run niva with QGIS's own Python "
            f"(inside QGIS, or with PYTHONPATH set to its bindings). [{exc}]"
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
        _err(exc)
        code = 2
    except OpError as exc:
        _err(exc)
        code = 1
    except BaseException as exc:  # noqa: BLE001 — incl. KeyboardInterrupt: must still
        # reach the safe teardown below, or interpreter shutdown races QGIS's C++
        # teardown and segfaults. Surface a generic message; never leak past `finally`.
        _err(f"unexpected error: {type(exc).__name__}: {exc}")
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
    from .. import color

    if result is None:
        print(color.paint("# done (no output layer)", "dim"))
        return
    count = ""
    fn = getattr(getattr(result, "ref", None), "featureCount", None)
    if callable(fn):
        try:
            count = f", {fn()} feature(s)"
        except Exception:
            count = ""
    print(
        color.paint(
            f"# done — {result.kind}: {result.name or result.ref}{count}",
            "green",
            "bold",
        )
    )


def _print_plan(program: list, source: str) -> bool:
    """Print the parse+bind plan. Returns True if any stage uses an **unknown verb**
    (not a built-in, alias, or `run` id) — the caller turns that into a non-zero exit."""
    from ..color import paint

    unknown = False
    print(paint(f"# parsed {source}: {len(program)} statement(s)", "dim"))
    for i, st in enumerate(program, start=1):
        num = paint(f"{i}.", "bold")
        if isinstance(st, Call):
            print(f"{num} call {paint(st.target, 'cyan')}")
            continue
        print(f"{num} flow — {len(st.stages)} stage(s):")
        for s in st.stages:
            if s.verb == "run":  # the escape hatch — passed to QGIS verbatim
                algo = s.args[0] if s.args else "?"
                print(
                    f"     {paint('run', 'cyan')} → {paint(str(algo), 'green')}"
                    f"  {paint('(raw)', 'dim')}  {s.options}"
                )
                for w in _run_warnings(algo, s.options):
                    print(paint(f"       ⚠ {w}", "yellow"))
                continue
            alias = _REG.get(s.verb)
            if alias is None:
                # A non-alias verb is only valid if it is a real BUILT-IN. Do not assume —
                # an invented/misspelled verb ("compute", "stats", "reproj") lands here and
                # must be flagged, or --explain silently blesses it (issue #29).
                if s.verb in _BUILTIN_VERB_NAMES:
                    print(
                        f"     {paint(s.verb, 'cyan')}  "
                        f"{paint('(built-in: handled by the engine)', 'dim')}"
                    )
                else:
                    import difflib

                    unknown = True
                    near = difflib.get_close_matches(s.verb, _ALL_VERB_NAMES, n=1)
                    hint = f" — did you mean `{near[0]}`?" if near else ""
                    print(
                        paint(
                            f"     {s.verb}  ⚠ UNKNOWN VERB — not a built-in or alias{hint} "
                            "(use `run <provider:id> KEY=value` for a raw algorithm)",
                            "red",
                        )
                    )
                continue
            op = bind(s, alias)
            print(f"     {paint(s.verb, 'cyan')} → {paint(op.algorithm, 'green')}")
            print(
                paint(
                    f"         {op.input_param} ← upstream layer (engine fills)", "dim"
                )
            )
            for key, value in op.params.items():
                print(f"         {key} = {value!r}")
            print(
                paint(f"         {op.output_param} ← output dest (engine fills)", "dim")
            )
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

    from ..color import paint
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
            print(paint(f"✗ {f}: {exc}", "red"), file=sys.stderr)
            had_error = True
            continue
        ok, issues = validate_text(text, file=f)
        errs = [i for i in issues if i[1] == "error"]
        warns = [i for i in issues if i[1] == "warning"]
        n_err += len(errs)
        n_warn += len(warns)
        sym = "✓" if ok and not warns else ("✗" if errs else "⚠")
        sty = "green" if sym == "✓" else ("red" if sym == "✗" else "yellow")
        print(f"{paint(sym, sty)} {f}")
        for line, sev, msg in sorted(issues, key=lambda i: (i[0], i[1])):
            loc = f"line {line}" if line else "flow"
            label = (
                paint("error", "red") if sev == "error" else paint("warn ", "yellow")
            )
            print(f"    {label}  {loc}: {msg}")
        if not ok:
            had_error = True
    err_txt = paint(f"{n_err} error(s)", "red") if n_err else "0 error(s)"
    warn_txt = paint(f"{n_warn} warning(s)", "yellow") if n_warn else "0 warning(s)"
    print(f"# {len(files)} file(s): {err_txt}, {warn_txt}")
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
        _err(exc)
        return 2
    print(json.dumps(build_plan(program, file=file), indent=2, ensure_ascii=False))
    return 0


def _search(args) -> int:
    """`niva search <keyword> [limit=N] [to=<file>] [--json]` — fuzzy + **synonym-aware**
    discovery (issue #44) over niva's verbs and the packaged QGIS algorithm catalog. Offline
    — no QGIS. `--json` emits machine-readable results; `to=<file>` writes the report."""
    from ..registry.catalog import catalog
    from ..search import format_results
    from ..search import search as run_search

    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    out = None
    limit = 20
    words: list = []
    for a in args:
        if a.startswith("to="):
            out = os.path.expanduser(a[len("to=") :])
        elif a.startswith("limit="):
            try:
                limit = int(a[len("limit=") :])
            except ValueError:
                pass
        else:
            words.append(a)
    query = " ".join(words).strip()
    if not query:
        print(
            "usage: niva search <keyword> [limit=N] [to=<file>] [--json]",
            file=sys.stderr,
        )
        return 2

    # Offline algorithm corpus straight from the packaged catalog (no QGIS).
    algs = [
        {
            "id": e.get("id", aid),
            "display_name": e.get("name", ""),
            "group": e.get("group", ""),
            "description": e.get("short_help", e.get("description", "")),
        }
        for aid, e in catalog().items()
    ]
    hits = run_search(query, algorithms=algs, limit=limit)

    if as_json:
        import json

        text = json.dumps(
            [
                {
                    "name": h.name,
                    "kind": h.kind,
                    "summary": h.summary,
                    "score": round(h.score, 3),
                }
                for h in hits
            ],
            indent=2,
            ensure_ascii=False,
        )
    else:
        text = format_results(query, hits, color=out is None)

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


def _find(args) -> int:
    """`niva find [glob] [in <dir>…] [filters] [--json|--as-flow]` — discover spatial data on
    the filesystem (issue #43). The scan is **offline** (glob / extension / size / mtime);
    the geometry/CRS/attribute filters (`--geom`, `--crs`, `--min-features`, `--max-features`,
    `--has-field`) need GDAL — present on QGIS's Python, absent in an isolated `uv`/`pipx` venv."""
    import time

    from .. import color
    from .. import find as F

    crit: dict = {}
    roots: list = []
    pattern = None
    as_json = as_flow = as_paths = nul = all_files = shallow = no_meta = False
    limit, max_depth = 500, None
    in_mode = False
    i = 0
    try:
        while i < len(args):
            a = args[i]
            nxt = args[i + 1] if i + 1 < len(args) else None
            if a == "in":
                in_mode = True
            elif a == "--json":
                as_json = True
            elif a == "--as-flow":
                as_flow = True
            elif a in ("--paths", "-l"):
                as_paths = True
            elif a in ("--print0", "-0"):
                as_paths = nul = True
            elif a == "--all-files":
                all_files = True
            elif a == "--shallow":
                shallow = True
            elif a == "--no-meta":
                no_meta = True
            elif a.startswith("limit="):
                limit = int(a.split("=", 1)[1])
            elif a in _FIND_VALUE_FLAGS:
                if nxt is None:
                    _err(f"{a} needs a value")
                    return 2
                i += 1
                if a == "--geom":
                    crit["geom"] = nxt
                elif a == "--crs":
                    crit["crs"] = nxt
                elif a == "--has-field":
                    crit["has_field"] = nxt
                elif a == "--format":
                    crit["format"] = nxt
                elif a == "--newer-than":
                    crit["newer_than"] = time.time() - F.parse_age(nxt)
                elif a == "--min-size":
                    crit["min_size"] = F.parse_size(nxt)
                elif a == "--max-size":
                    crit["max_size"] = F.parse_size(nxt)
                elif a == "--min-features":
                    crit["min_features"] = int(nxt)
                elif a == "--max-features":
                    crit["max_features"] = int(nxt)
                elif a == "--max-depth":
                    max_depth = int(nxt)
                elif a == "--limit":
                    limit = int(nxt)
                elif a == "--in":
                    roots.append(nxt)
            elif not a.startswith("-"):
                if in_mode or pattern is not None:
                    roots.append(a)
                else:
                    pattern = a
            else:
                _err(f"unknown option {a!r} (try: niva find --help)")
                return 2
            i += 1
    except ValueError as exc:
        _err(f"bad value: {exc}")
        return 2

    roots = roots or ["."]
    crit["pattern"] = pattern or "*"
    crit["exts"] = F.exts_for_pattern(crit["pattern"], all_files=all_files)

    wants_meta = any(
        k in crit for k in ("geom", "crs", "min_features", "max_features", "has_field")
    )
    if wants_meta and not F.have_gdal():
        _err(
            "the --geom/--crs/--features/--has-field filters need GDAL, which isn't importable "
            "here. Run niva on QGIS's Python (see the FAQ), or drop those filters."
        )
        return 2

    records = F.find(
        roots,
        crit,
        recursive=not shallow,
        max_depth=max_depth,
        limit=limit,
        do_enrich=not no_meta,
    )
    if as_paths:
        out = F.format_paths(records, nul=nul)
        # NUL-separated output must not get a trailing newline (xargs -0 would see an
        # empty final arg); write raw. The newline form gets the usual trailing newline.
        if nul:
            sys.stdout.write(out)
        elif out:
            print(out)
    elif as_json:
        print(F.format_json(records))
    elif as_flow:
        print(F.format_as_flow(records))
    else:
        print(
            F.format_table(
                records, color=color.enabled(), meta=F.have_gdal() and not no_meta
            )
        )
    return 0


def _explain(args) -> int:
    """`niva explain <file.niva> | "<flow>"` — a human-readable view of the resolved plan
    IR (no QGIS): each step's op → algorithm, params, injected defaults, and diagnostics.
    ``--json`` emits the raw IR (same as ``niva plan``). Always exits 0; read the
    diagnostics (or use ``niva validate``) to gate on errors."""
    from ..plan import build_plan, format_plan

    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        print(
            'usage: niva explain <file.niva> | niva explain "<flow>" [--json]',
            file=sys.stderr,
        )
        return 2
    if len(args) == 1 and os.path.isfile(args[0]):
        with open(args[0], encoding="utf-8") as fh:
            text, file = fh.read(), args[0]
    else:
        text, file = " ".join(args), None
    try:
        program = parse(text, file=file)
    except FlowError as exc:
        _err(exc)
        return 2
    plan = build_plan(program, file=file)
    if as_json:
        import json

        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(format_plan(plan))
    return 0


def _setup(args) -> int:
    """`niva setup [show|init|path|get <key>|set <key> <value>|unset <key>]` — view/edit
    niva's portable config file **without QGIS** (issue #36); `init` writes a commented
    sample. Secrets stay in the environment."""
    from .. import color
    from .. import config as cfg

    action = args[0] if args else "show"
    rest = args[1:]

    if action == "doctor":
        from ..doctor import run as _doctor

        return _doctor(rest)

    if action == "wizard":
        return _setup_wizard()

    if action == "init":
        path, written = cfg.write_template(force="--force" in rest)
        if not written:
            print(
                f"niva: {path} already exists — `niva setup init --force` to overwrite",
                file=sys.stderr,
            )
            return 1
        print(f"niva: wrote a sample config → {path}", file=sys.stderr)
        print("      edit it, or run `niva setup set <key> <value>`.", file=sys.stderr)
        return 0

    if action in ("show", "list"):
        data = cfg.load()
        print(color.paint(f"# niva config: {cfg.config_path()}", "dim"))
        for key, (env, _comment) in cfg.KNOWN_KEYS.items():
            if key in data:
                shown = color.paint(str(data[key]), "green")
            elif os.environ.get(env):
                shown = color.paint(os.environ[env], "yellow") + color.paint(
                    f"  (from ${env})", "dim"
                )
            else:
                shown = color.paint("(unset)", "dim")
            print(f"  {color.paint(f'{key:<14}', 'cyan', 'bold')} = {shown}")
        for key in (k for k in data if k not in cfg.KNOWN_KEYS):
            print(
                f"  {color.paint(f'{key:<14}', 'magenta')} = "
                f"{color.paint(str(data[key]), 'green')}  {color.paint('(custom)', 'dim')}"
            )
        print(
            color.paint(
                "  secrets — set NIVA_NTFY_TOKEN / NIVA_SMTP_PASSWORD in the environment, "
                "never here",
                "dim",
            )
        )
        return 0

    if action == "path":
        print(cfg.config_path())
        return 0

    if action == "get":
        if len(rest) != 1:
            print("usage: niva setup get <key>", file=sys.stderr)
            return 2
        value = cfg.get(rest[0])
        if value is None:
            return 1
        print(value)
        return 0

    if action == "set":
        if len(rest) < 2:
            print("usage: niva setup set <key> <value>", file=sys.stderr)
            return 2
        key, value = rest[0], " ".join(rest[1:])
        try:
            path = cfg.set_key(key, value)
        except ValueError as exc:
            _err(exc)
            return 2
        print(f"niva: set {key} = {value}  →  {path}", file=sys.stderr)
        return 0

    if action == "unset":
        if len(rest) != 1:
            print("usage: niva setup unset <key>", file=sys.stderr)
            return 2
        cfg.unset_key(rest[0])
        print(f"niva: unset {rest[0]}", file=sys.stderr)
        return 0

    print(
        "usage: niva setup [doctor | wizard | show | init | path | get <key> | set <key> <value> | unset <key>]",
        file=sys.stderr,
    )
    return 2


def _setup_wizard() -> int:
    """`niva setup wizard` — an interactive walk-through of niva's portable settings. For each
    known key: shows the current value (config, else the mirrored env var, else an example),
    then Enter keeps it, a typed value sets it, and `-` clears it. Secrets are never prompted —
    they belong in the environment; the wizard only reminds you which env vars to set. Writes
    through the same `config.set_key`/`unset_key` as `niva setup set`, so it's fully portable."""
    from .. import color
    from .. import config as cfg

    data = cfg.load()
    path = cfg.config_path()
    print(
        color.paint("niva setup wizard", "bold")
        + " — configure niva's portable settings"
    )
    print(color.paint(f"config file: {path}", "dim"))
    print(
        "For each setting: press "
        + color.paint("Enter", "bold")
        + " to keep it, type a value to set it, or "
        + color.paint("-", "bold")
        + " to clear it. Ctrl-D to stop.\n"
    )

    keys = list(cfg.KNOWN_KEYS.items())
    changes = 0
    for i, (key, (env, comment)) in enumerate(keys, 1):
        cur, src = data.get(key), ""
        if cur is None and os.environ.get(env):
            cur, src = os.environ[env], f" (from ${env})"
        if cur:
            shown = color.paint(str(cur), "green") + color.paint(src, "dim")
        else:
            example = cfg._EXAMPLES.get(key, "")
            shown = color.paint("not set", "dim") + (
                color.paint(f"   e.g. {example}", "dim") if example else ""
            )
        print(
            f"{color.paint(f'[{i}/{len(keys)}]', 'dim')} {color.paint(key, 'cyan')} — {comment}"
        )
        print(f"   current: {shown}")
        try:
            resp = input(color.paint("   › ", "yellow")).strip()
        except EOFError:
            print()
            break
        if resp == "-":
            if key in data:
                cfg.unset_key(key)
                data.pop(key, None)
                changes += 1
                print(color.paint("   cleared", "dim"))
        elif resp:
            cfg.set_key(key, resp)
            data[key] = resp
            changes += 1
            print(color.paint("   set", "green"))
        print()

    print(
        color.paint(
            "Secrets — set these in your environment (never the config file):", "bold"
        )
    )
    for skey, senv in cfg.SECRET_KEYS.items():
        state = (
            color.paint("set", "green")
            if os.environ.get(senv)
            else color.paint("unset", "yellow")
        )
        print(f"  {color.paint(senv, 'cyan')}  ({skey}) — {state}")
    print()

    if changes:
        print(color.paint(f"saved {changes} change(s) → {path}", "green"))
    else:
        print(color.paint("no changes", "dim"))
    print(color.paint("verify with `niva setup doctor`.", "dim"))
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
