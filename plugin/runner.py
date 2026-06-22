"""Run a niva flow from the plugin — the GUI-free, cross-platform execution core.

Why this is portable across Windows / macOS / Linux: it runs niva **in-process**,
reusing the QgsApplication that QGIS is already running. There is no subprocess, no
`python.exe` / `python3` discovery, no OS-specific interpreter path — so it behaves
identically everywhere. (Contrast marimo-qgis, which had to launch a separate
process and detect the interpreter per OS.)
"""

from __future__ import annotations

import os


def run_flow(text: str, *, file: str | None = None, dry_run: bool = False,
             log_base: str | None = None, progress=None, cancel=None) -> dict:
    """Execute ``text`` (or dry-run it). Returns a result dict:

    ``{ok: bool, mode: str, summary: str, layer, error: str | None, log}``
    where ``layer`` is the final niva ``Layer`` handle on a successful real run
    (``None`` otherwise) so the caller can add it to the map. ``log_base`` (when set)
    is the journal base path; the plugin passes one **session** base so all runs
    append to a single log. ``None`` disables logging.
    """
    import time

    import niva

    base = os.path.dirname(os.path.abspath(file)) if file else None
    t0 = time.monotonic()

    if dry_run:
        from niva.engine import Engine, MockBackend
        from niva.grammar import parse

        backend = MockBackend()
        try:
            Engine(backend).execute(parse(text, file=file), base_dir=base)
        except Exception as exc:  # noqa: BLE001 — never let it escape the worker thread
            result = _fail("dry-run", exc)
        else:
            lines = [
                f"{c[0]} {c[1]}" + (f"  {c[2]}" if len(c) > 2 else "")
                for c in backend.calls
            ]
            result = {"ok": True, "mode": "dry-run", "summary": "\n".join(lines) or "(no operations)",
                      "layer": None, "error": None, "log": None}
        result["elapsed"] = time.monotonic() - t0
        return result

    # Append every real run to the session journal (one file per QGIS session).
    # niva writes <base>.jsonl (machine) and <base>.log (human); we surface the .log.
    log_path = (log_base + ".log") if log_base else None
    try:
        layer = niva.flow(text, file=file, log=log_base, log_append=True,
                          progress=progress, cancel=cancel)
    except Exception as exc:  # noqa: BLE001 — a worker-thread exception escaping into
        # the QgsTask can destabilise QGIS; always return a result dict instead.
        result = _fail("run", exc)
    else:
        result = {"ok": True, "mode": "run", "summary": _describe(layer), "layer": layer,
                  "error": None}
    result["log"] = log_path  # the journal records even a failed run before raising
    result["elapsed"] = time.monotonic() - t0
    return result


def _fail(mode: str, exc: Exception) -> dict:
    import traceback

    from niva.errors import NivaError

    if isinstance(exc, NivaError):
        msg = str(exc)
    else:
        msg = f"unexpected error: {type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        if tb and tb.strip() != "NoneType: None":
            msg = msg + "\n\n" + tb
    return {"ok": False, "mode": mode, "summary": "", "layer": None, "error": msg}


def _describe(layer) -> str:
    if layer is None:
        return "done — no output layer."
    ref = getattr(layer, "ref", None)
    # Always show a FULL path: a saved file's ref is its path; a live layer exposes
    # its data source (which includes the absolute path).
    if isinstance(ref, str):
        where = os.path.abspath(ref)
    else:
        source = getattr(ref, "source", None)
        where = source() if callable(source) else (getattr(layer, "name", "") or str(ref))
    counter = getattr(ref, "featureCount", None)
    count = ""
    if callable(counter):
        try:
            count = f", {counter()} feature(s)"
        except Exception:
            count = ""
    return f"done — {where}{count}."
