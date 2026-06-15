"""Run a niva flow from the plugin — the GUI-free, cross-platform execution core.

Why this is portable across Windows / macOS / Linux: it runs niva **in-process**,
reusing the QgsApplication that QGIS is already running. There is no subprocess, no
`python.exe` / `python3` discovery, no OS-specific interpreter path — so it behaves
identically everywhere. (Contrast marimo-qgis, which had to launch a separate
process and detect the interpreter per OS.)
"""

from __future__ import annotations

import os


def run_flow(text: str, *, file: str | None = None, dry_run: bool = False) -> dict:
    """Execute ``text`` (or dry-run it). Returns a result dict:

    ``{ok: bool, mode: str, summary: str, layer, error: str | None}``
    where ``layer`` is the final niva ``Layer`` handle on a successful real run
    (``None`` otherwise) so the caller can add it to the map.
    """
    import niva
    from niva.errors import NivaError

    base = os.path.dirname(os.path.abspath(file)) if file else None

    if dry_run:
        from niva.engine import Engine, MockBackend
        from niva.grammar import parse

        backend = MockBackend()
        try:
            Engine(backend).execute(parse(text, file=file), base_dir=base)
        except NivaError as exc:
            return _fail("dry-run", exc)
        lines = [
            f"{c[0]} {c[1]}" + (f"  {c[2]}" if len(c) > 2 else "")
            for c in backend.calls
        ]
        body = "\n".join(lines) or "(no operations)"
        return {"ok": True, "mode": "dry-run", "summary": body, "layer": None, "error": None}

    try:
        layer = niva.flow(text, file=file)  # in-process; reuses the running QGIS
    except NivaError as exc:
        return _fail("run", exc)
    return {"ok": True, "mode": "run", "summary": _describe(layer), "layer": layer, "error": None}


def _fail(mode: str, exc: Exception) -> dict:
    return {"ok": False, "mode": mode, "summary": "", "layer": None, "error": str(exc)}


def _describe(layer) -> str:
    if layer is None:
        return "done — no output layer."
    ref = getattr(layer, "ref", None)
    counter = getattr(ref, "featureCount", None)
    count = ""
    if callable(counter):
        try:
            count = f", {counter()} feature(s)"
        except Exception:
            count = ""
    return f"done — {getattr(layer, 'name', '') or ref}{count}."
