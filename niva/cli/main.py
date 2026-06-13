"""niva CLI entry point (planning/11-cli-and-api-reference.md).

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
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    try:
        source, text = _read_source(argv)
        if text is None:
            return 2
        program = parse(text, file=None if source == "<inline>" else source)

        if mode == "explain":
            _print_plan(program, source)
        elif mode == "dry-run":
            _print_plan(program, source)
            _dry_run(program)
        else:
            return _execute(program)
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


def _execute(program) -> int:
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
    code = 0
    try:
        result = Engine(PyqgisBackend()).execute(program)
        _print_result(result)
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 2
    except OpError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        code = 1
    if owns:
        # Standalone run: tear QGIS down and hard-exit with our code before the
        # Python GC races QGIS's C++ teardown at interpreter shutdown (it segfaults,
        # which would otherwise clobber the exit code). Flush user output first.
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
            alias = _REG.get(s.verb)
            if alias is None:
                print(f"     {s.verb}  (built-in: load/save handled by the engine)")
                continue
            op = bind(s, alias)
            print(f"     {s.verb} → {op.algorithm}")
            print(f"         {op.input_param} ← upstream layer (engine fills)")
            for key, value in op.params.items():
                print(f"         {key} = {value!r}")
            print(f"         {op.output_param} ← output dest (engine fills)")


def _dry_run(program: list) -> None:
    from ..engine import Engine, MockBackend

    backend = MockBackend()
    Engine(backend).execute(program)  # raises FlowError on an invalid flow
    print(f"\n# dry-run OK — {len(backend.calls)} backend operation(s) over MockBackend:")
    for call in backend.calls:
        if call[0] == "run":
            print(f"     run {call[1]}  {call[2]}")
        else:
            print(f"     {call[0]} {call[1]}")


if __name__ == "__main__":
    raise SystemExit(main())
