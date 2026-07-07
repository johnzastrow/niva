"""niva — a concise, readable text-pipeline grammar for QGIS geoprocessing.

v0.1 (MVP, under construction). This is the pip package; the design lives in
``docs/planning/``. Implemented: the **grammar** (lexer + parser), the **registry +
binder** (verb → QGIS algorithm params), the **engine core** (runs a flow over a
swappable backend), and the **PyQGIS backend** (the real ``processing.run`` adapter).

Quick start (inside QGIS's Python — a console, or a marimo notebook on QGIS's
interpreter)::

    import niva
    niva.flow("load roads.gpkg | buffer 100m dissolve | save out.gpkg")

Pass ``backend=MockBackend()`` to exercise a flow with no QGIS at all.
"""

from __future__ import annotations

__version__ = "0.53.0"

from .describe import describe
from .errors import FlowError, NivaError, OpError

__all__ = [
    "__version__",
    "NivaError",
    "FlowError",
    "OpError",
    "flow",
    "run_file",
    "describe",
]


def flow(
    text: str,
    *,
    backend=None,
    file: str | None = None,
    log=None,
    log_append=False,
    progress=None,
    cancel=None,
):
    """Parse and execute a niva flow, returning the final layer handle.

    ``backend`` defaults to the real :class:`PyqgisBackend` (which requires QGIS);
    pass a ``MockBackend`` to dry-run a flow without QGIS.

    ``log`` is a base path for the run journal; ``<log>.jsonl`` (machine) and
    ``<log>.log`` (human) are written. Falls back to the ``NIVA_LOG`` env var.
    ``log_append=True`` appends to an existing journal (one log per session) instead
    of truncating (one log per invocation).

    ``progress`` is an optional ``callable(str)`` for live status — a ``▶ <stage>``
    line as each stage starts, and throttled algorithm progress (``   45%``) during
    long operations.
    """
    import os

    from .engine import Engine
    from .grammar import parse

    program = parse(text, file=file)
    base_dir = os.path.dirname(os.path.abspath(file)) if file else None

    journal = None
    log = log or os.environ.get("NIVA_LOG")
    if log:
        from .journal import Journal

        journal = Journal(log, append=log_append).open(
            flow=file or "<inline>", niva_version=__version__
        )
    try:
        return Engine(
            backend or _default_backend(),
            journal=journal,
            progress=progress,
            cancel=cancel,
        ).execute(program, base_dir=base_dir)
    finally:
        if journal is not None:
            journal.close()


def run_file(path: str, *, backend=None):
    """Execute a ``.niva`` file. See :func:`flow`."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return flow(text, backend=backend, file=path)


def _default_backend():
    # Imported lazily: QGIS is only needed when actually executing with the real
    # backend, so `import niva` stays safe on any interpreter.
    from .engine.pyqgis import PyqgisBackend, ensure_qgis
    from .engine.native import wrap_native

    ensure_qgis()
    # Wrap in the native-CLI harness so `saga:*` ids shell out to saga_cmd; every other
    # id passes straight through to QGIS. Transparent for non-SAGA flows.
    return wrap_native(PyqgisBackend())
