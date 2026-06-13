"""niva CLI entry point (planning/11-cli-and-api-reference.md).

**v0.1 increment 2 — parse + bind, no execution yet.** Lexes/parses a flow and,
for every verb that is a registered alias, resolves it through the binder to show
the QGIS algorithm and the ``processing.run`` params it would receive (a permanent
``--dry-run``). Built-in verbs (``load`` / ``save`` / …) are marked as such; the
engine and PyQGIS backend that would actually run them are the next increments.
"""

from __future__ import annotations

import sys

from ..errors import FlowError
from ..grammar import Call, parse
from ..registry import bind, core_registry

_REG = core_registry()

_USAGE = 'usage: niva run <file.niva>  |  niva "<flow>"   (v0.1: parse-only)'


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
                print(f"     {s.verb}  (built-in — engine not built yet)")
                continue
            op = bind(s, alias)
            print(f"     {s.verb} → {op.algorithm}")
            print(f"         {op.input_param} ← upstream layer (engine fills)")
            for key, value in op.params.items():
                print(f"         {key} = {value!r}")
            print(f"         {op.output_param} ← output dest (engine fills)")


if __name__ == "__main__":
    raise SystemExit(main())
