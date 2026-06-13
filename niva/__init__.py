"""niva — a concise, readable text-pipeline grammar for QGIS geoprocessing.

v0.1 (MVP, under construction). This is the pip package; the design lives in
``planning/``. Implemented: the **grammar** (lexer + parser), the **registry +
binder** (verb → QGIS algorithm params), the **engine core** (runs a flow over a
swappable backend), and the **PyQGIS backend** (the real ``processing.run`` adapter).

Quick start (inside QGIS's Python — a console, or a marimo notebook on QGIS's
interpreter)::

    import niva
    niva.flow("load roads.gpkg | buffer 100m dissolve | save out.gpkg")

Pass ``backend=MockBackend()`` to exercise a flow with no QGIS at all.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

from .errors import FlowError, NivaError, OpError

__all__ = ["__version__", "NivaError", "FlowError", "OpError", "flow", "run_file"]


def flow(text: str, *, backend=None, file: str | None = None):
    """Parse and execute a niva flow, returning the final layer handle.

    ``backend`` defaults to the real :class:`PyqgisBackend` (which requires QGIS);
    pass a ``MockBackend`` to dry-run a flow without QGIS.
    """
    import os

    from .engine import Engine
    from .grammar import parse

    program = parse(text, file=file)
    base_dir = os.path.dirname(os.path.abspath(file)) if file else None
    return Engine(backend or _default_backend()).execute(program, base_dir=base_dir)


def run_file(path: str, *, backend=None):
    """Execute a ``.niva`` file. See :func:`flow`."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return flow(text, backend=backend, file=path)


def _default_backend():
    # Imported lazily: QGIS is only needed when actually executing with the real
    # backend, so `import niva` stays safe on any interpreter.
    from .engine.pyqgis import PyqgisBackend, ensure_qgis

    ensure_qgis()
    return PyqgisBackend()
