"""Zero-dependency ANSI colour for the CLI (docs/planning/20 §10, Tier 0).

Colour is applied only to a real terminal: it turns **off** automatically when stdout is not
a TTY, when ``NO_COLOR`` is set, or when ``TERM=dumb`` — so piped/redirected output and file
writes stay plain. Force it with ``NIVA_COLOR=always|never``. Never pulls a colour library
into QGIS's Python (Oscar E1): just a few ANSI escapes behind an ``enabled()`` gate.
"""

from __future__ import annotations

import os
import sys

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}


def enabled() -> bool:
    """Whether ANSI colour should be emitted right now. ``NO_COLOR`` (the cross-tool
    standard) wins; then ``NIVA_COLOR=always|never``; otherwise auto-detect a real TTY."""
    if os.environ.get("NO_COLOR"):
        return False
    force = os.environ.get("NIVA_COLOR")
    if force == "always":
        return True
    if force == "never":
        return False
    try:
        return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    except Exception:  # noqa: BLE001 — a detached/redirected stdout must degrade to plain
        return False


def paint(text: str, *styles: str) -> str:
    """``text`` wrapped in the given ANSI ``styles`` (e.g. ``"cyan"``, ``"bold"``) when colour
    is enabled; otherwise ``text`` unchanged."""
    if not styles or not enabled():
        return text
    prefix = "".join(_CODES[s] for s in styles if s in _CODES)
    return f"{prefix}{text}{_CODES['reset']}" if prefix else text
