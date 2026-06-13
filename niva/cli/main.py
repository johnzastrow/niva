"""niva CLI entry point (planning/11-cli-and-api-reference.md).

**v0.1 increment 3 — parse + bind + dry-run.** Lexes/parses a flow and, for every
alias verb, resolves it through the binder to show the QGIS algorithm and the
``processing.run`` params it would receive. With ``--dry-run`` it then walks the
whole flow through the engine over a no-QGIS ``MockBackend``, validating execution
order and CRS/units (catching e.g. an op before ``load`` or a metres distance on a
degrees CRS) and printing the backend operation sequence. The real PyQGIS backend
that actually runs the ops is the next increment.
"""

from __future__ import annotations

import sys

from ..engine import Engine, MockBackend
from ..errors import FlowError
from ..grammar import Call, parse
from ..registry import bind, core_registry

_REG = core_registry()

_USAGE = (
    'usage: niva run <file.niva> [--dry-run]  |  niva "<flow>" [--dry-run]\n'
    "       (v0.1: parse + bind; --dry-run validates the flow over a mock backend)"
)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = False
    if "--dry-run" in argv:
        argv = [a for a in argv if a != "--dry-run"]
        dry_run = True
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    try:
        if argv[0] == "run":
            if len(argv) < 2:
                print("niva run: missing <file.niva>", file=sys.stderr)
                return 2
            source = argv[1]
            with open(source, encoding="utf-8") as fh:
                text = fh.read()
            program = parse(text, file=source)
        else:
            source = "<inline>"
            program = parse(argv[0])
        _print_program(program, source)
        if dry_run:
            _dry_run(program)
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 3

    return 0


def _print_program(program: list, source: str) -> None:
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
    """Walk the program through the engine over a mock backend (no QGIS)."""
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
