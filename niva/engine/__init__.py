"""niva execution engine (planning/05-architecture.md).

The QGIS-free orchestration core: ``Engine`` runs a parsed program over a
``Backend`` (``MockBackend`` for tests/dry-runs; ``PyqgisBackend`` — a later
increment — for the real thing), passing ``Layer`` handles down each flow.
"""

from .backend import Backend, MockBackend
from .engine import Engine
from .layer import CrsInfo, Layer
from .units import resolve_distance

__all__ = [
    "Engine",
    "Backend",
    "MockBackend",
    "Layer",
    "CrsInfo",
    "resolve_distance",
]
