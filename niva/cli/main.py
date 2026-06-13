"""niva CLI entry point (planning/11-cli-and-api-reference.md).

**v0.1 increment 1 — parse-only.** The registry binding and the PyQGIS backend are
not built yet, so this currently lexes/parses a flow and prints its structure
(effectively a permanent ``--dry-run`` of the grammar). That is enough to exercise
the grammar end to end from the command line and proves the foundation works.
"""

from __future__ import annotations

import sys

from ..errors import FlowError
from ..grammar import Call, parse

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
    except FlowError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"niva: {exc}", file=sys.stderr)
        return 3

    _print_program(program, source)
    return 0


def _print_program(program: list, source: str) -> None:
    print(f"# parsed {source}: {len(program)} statement(s)")
    for i, st in enumerate(program, start=1):
        if isinstance(st, Call):
            print(f"{i}. call {st.target}")
            continue
        print(f"{i}. flow — {len(st.stages)} stage(s):")
        for s in st.stages:
            bits = [f"verb={s.verb}"]
            if s.args:
                bits.append(f"args={s.args}")
            if s.options:
                bits.append(f"options={s.options}")
            print("     " + "  ".join(bits))


if __name__ == "__main__":
    raise SystemExit(main())
