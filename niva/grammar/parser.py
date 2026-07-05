"""The niva grammar parser (docs/planning/10-grammar-spec.md).

Turns ``.niva`` source (or an inline flow string) into a **Program**: an ordered
list of ``Flow`` and ``Call`` statements, executed procedurally. Pure Python, no
QGIS — the registry binds a parsed stage's args/options to algorithm parameters in
a later layer (docs/planning/07-alias-registry-design.md).

A ``Stage`` carries ``verb``, ``args`` (ordered bare terms — *positionals or
flags*, which the registry resolves), and ``options`` (``key=value``). The parser
deliberately does **not** split args into positionals vs flags: that needs the
per-verb spec (10-§2.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

from ..errors import FlowError
from .lexer import split_pipes, strip_comment, tokenize, unquote

# Option keys are identifier-like but may contain internal hyphens (e.g. `from-template=`).
# Only tokens that contain `=` are ever tested, so flags like `-deep` are unaffected.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass
class Stage:
    """One ``verb [args…] [key=value…]`` step of a flow."""

    verb: str
    args: list = field(default_factory=list)  # positionals OR flags (unresolved)
    options: dict = field(default_factory=dict)
    line: int = 0
    raw: str = ""


@dataclass
class Call:
    """A ``call <file.niva>`` statement (procedural include, 03-§4.1)."""

    target: str
    line: int = 0
    raw: str = ""


@dataclass
class Flow:
    """A chain of ``Stage`` joined by ``|``."""

    stages: list
    line: int = 0
    raw: str = ""


Statement = Union[Flow, Call]


def parse(text: str, *, file: str | None = None) -> list:
    """Parse niva source into a list of ``Flow`` | ``Call`` statements."""
    program: list = []
    for raw, line in _merge_lines(text):
        toks = tokenize(raw)
        if toks and toks[0] == "call":
            if len(toks) != 2:
                raise FlowError(
                    "`call` takes exactly one file path",
                    line=line,
                    stage=raw,
                    file=file,
                )
            program.append(
                Call(target=_unquote(toks[1], line, raw, file), line=line, raw=raw)
            )
        else:
            program.append(_parse_flow(raw, line, file))
    return program


def _merge_lines(text: str) -> list:
    """Strip comments and merge ``|``-continued lines into statements.

    Returns ``[(statement_text, start_line)]``. Blank lines separate statements; a
    ``|`` at the end of a line or the start of the next continues the flow (10-§2).
    """
    out: list = []
    buf = ""
    buf_line = 0
    for n, physical in enumerate(text.splitlines(), start=1):
        line = strip_comment(physical).strip()
        if not line:
            if buf:
                out.append((buf, buf_line))
                buf = ""
            continue
        if not buf:
            buf, buf_line = line, n
        elif buf.endswith("|") or line.startswith("|"):
            buf = f"{buf} {line}"
        else:
            out.append((buf, buf_line))
            buf, buf_line = line, n
    if buf:
        out.append((buf, buf_line))
    return out


def _parse_flow(raw: str, line: int, file: str | None) -> Flow:
    stages = []
    for part in split_pipes(raw):
        if not part:
            raise FlowError(
                "empty stage (a stray or doubled `|`?)", line=line, stage=raw, file=file
            )
        stages.append(_parse_stage(part, line, file))
    return Flow(stages=stages, line=line, raw=raw)


def _unquote(token: str, line: int, raw: str, file: str | None) -> str:
    """`unquote` a token, turning a lexer ``ValueError`` (e.g. an unterminated quote) into a
    located ``FlowError`` so the user gets line/stage context, not a bare traceback."""
    try:
        return unquote(token)
    except ValueError as exc:
        raise FlowError(str(exc), line=line, stage=raw, file=file) from exc


def _is_option(token: str) -> bool:
    """True if a token is ``key=value`` (not a quoted value, valid key)."""
    if token.startswith(("'", '"')) or "=" not in token:
        return False
    return bool(_KEY.match(token.split("=", 1)[0]))


def _parse_stage(raw: str, line: int, file: str | None) -> Stage:
    toks = tokenize(raw)
    if not toks:
        raise FlowError("empty stage", line=line, stage=raw, file=file)
    verb, *rest = toks
    if _is_option(verb):
        raise FlowError(
            f"a stage must start with a verb, got option `{verb}`",
            line=line,
            stage=raw,
            file=file,
        )
    stage = Stage(verb=verb, line=line, raw=raw)
    for tok in rest:
        if _is_option(tok):
            key, val = tok.split("=", 1)
            stage.options[key] = _unquote(val, line, raw, file)
        else:
            stage.args.append(_unquote(tok, line, raw, file))
    return stage
