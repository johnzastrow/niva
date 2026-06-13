"""Lexical helpers for the niva grammar (planning/10-grammar-spec.md).

Pure Python, no QGIS. These turn raw text into the pieces the parser assembles:
comment stripping, quote-aware splitting on the pipe, stage tokenization that keeps
quoted spans and ``key="…"`` options intact, and quote removal.
"""

from __future__ import annotations

_QUOTES = "'\""


def strip_comment(line: str) -> str:
    """Remove a trailing ``# …`` comment, ignoring ``#`` inside quotes."""
    out: list[str] = []
    quote = None
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:        # keep an escaped char verbatim
                out.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in _QUOTES:
            quote = c
            out.append(c)
        elif c == "#":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def split_pipes(flow: str) -> list[str]:
    """Split a flow on ``|`` that is outside quotes; trim each stage."""
    parts: list[str] = []
    cur: list[str] = []
    quote = None
    i, n = 0, len(flow)
    while i < n:
        c = flow[i]
        if quote:
            cur.append(c)
            if c == "\\" and i + 1 < n:
                cur.append(flow[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in _QUOTES:
            quote = c
            cur.append(c)
        elif c == "|":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts]


def tokenize(stage: str) -> list[str]:
    """Split a stage into tokens, keeping quoted spans and ``key="…"`` intact.

    Whitespace separates tokens, but a quoted span is atomic (spaces preserved) and
    stays attached to a preceding ``key=`` — so ``title="Cat parcels"`` is one token
    and ``"a | b"`` is one token.
    """
    tokens: list[str] = []
    cur: list[str] = []
    quote = None
    i, n = 0, len(stage)
    while i < n:
        c = stage[i]
        if quote:
            cur.append(c)
            if c == "\\" and i + 1 < n:
                cur.append(stage[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
        elif c in " \t":
            if cur:
                tokens.append("".join(cur))
                cur = []
            i += 1
        elif c in _QUOTES:
            quote = c
            cur.append(c)
            i += 1
        else:
            cur.append(c)
            i += 1
    if cur:
        tokens.append("".join(cur))
    return tokens


def unquote(value: str) -> str:
    """Strip one surrounding quote pair and unescape ``\\\\``, ``\\"``, ``\\'``."""
    if len(value) >= 2 and value[0] in _QUOTES and value[-1] == value[0]:
        inner = value[1:-1]
        out: list[str] = []
        i, n = 0, len(inner)
        while i < n:
            if inner[i] == "\\" and i + 1 < n and inner[i + 1] in (value[0], "\\"):
                out.append(inner[i + 1])
                i += 2
            else:
                out.append(inner[i])
                i += 1
        return "".join(out)
    return value
