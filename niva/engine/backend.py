"""The backend seam (planning/05-architecture.md, 06).

The engine never imports QGIS. Everything that touches real geodata goes through a
``Backend``: load a source, run an algorithm, save to disk, report a layer's CRS.
The real ``PyqgisBackend`` (a later increment) drives ``processing.run`` inside
QGIS's interpreter; ``MockBackend`` here is a no-QGIS double that records calls and
hands back fake handles, so the whole engine is testable with plain ``python3`` and
can power a ``--dry-run`` that validates a flow without executing it.
"""

from __future__ import annotations

import abc

from .layer import DB_TABLE, MEMORY, SOURCE, CrsInfo, Layer


class Backend(abc.ABC):
    @abc.abstractmethod
    def load(self, source: str, *, facet: str = "vector") -> Layer:
        """Open a source (path/URI) and return a handle to it."""

    @abc.abstractmethod
    def load_table(self, conn: str, schema: str | None, table: str) -> Layer:
        """Load a table from the named QGIS connection ``conn``. Credentials come
        from QGIS's connection store — the name is all niva passes through."""

    @abc.abstractmethod
    def run_sql(self, conn: str, query: str) -> Layer:
        """Run ``query`` against the named QGIS connection and return the result as
        a query layer."""

    @abc.abstractmethod
    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str) -> Layer:
        """Run ``algorithm`` with ``params``, feeding ``input_layer`` into
        ``input_param`` and a temporary sink into ``output_param``; return the
        output as a new handle. Failures raise ``OpError``."""

    @abc.abstractmethod
    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None):
        """The `run` escape hatch: pass ``params`` to ``algorithm`` verbatim. The
        backend injects ``INPUT`` from ``input_layer`` if absent (piped use) and a
        temporary ``OUTPUT`` if absent, then returns the output as a handle, or
        ``None`` if the algorithm produces no pipeable layer (e.g. a folder export)."""

    @abc.abstractmethod
    def set_metadata(self, layer: Layer, fields: dict) -> Layer:
        """Attach descriptive metadata (title/abstract/keywords/…) to ``layer`` and
        return it (a pass-through). Persisted to disk by the next ``save``."""

    @abc.abstractmethod
    def save(self, layer: Layer, dest: str) -> Layer:
        """Write ``layer`` to ``dest`` and return a handle to the written file."""

    @abc.abstractmethod
    def crs_of(self, layer: Layer) -> CrsInfo:
        """Report ``layer``'s CRS — used to resolve distances (units.py)."""


class MockBackend(Backend):
    """A QGIS-free double: records every operation in ``calls`` and returns fake
    handles. ``crs`` is configurable so tests can exercise both projected and
    geographic distance resolution."""

    def __init__(self, crs: CrsInfo | None = None):
        self.crs = crs or CrsInfo("EPSG:3857", is_geographic=False, units_to_meters=1.0)
        self.calls: list = []
        self._n = 0

    def load(self, source: str, *, facet: str = "vector") -> Layer:
        self.calls.append(("load", source))
        return Layer(SOURCE, source, facet=facet, name=source)

    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str) -> Layer:
        self.calls.append(("run", algorithm, params))
        self._n += 1
        return Layer(MEMORY, f"result-{self._n}", facet=input_layer.facet,
                     name=f"{algorithm}#{self._n}")

    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None):
        self.calls.append(("run", algorithm, params))
        self._n += 1
        facet = input_layer.facet if input_layer is not None else "vector"
        return Layer(MEMORY, f"result-{self._n}", facet=facet, name=algorithm)

    def load_table(self, conn: str, schema: str | None, table: str) -> Layer:
        self.calls.append(("load_table", conn, schema, table))
        ref = f"@{conn}." + (f"{schema}.{table}" if schema else table)
        return Layer(DB_TABLE, ref, facet="vector", name=table)

    def run_sql(self, conn: str, query: str) -> Layer:
        self.calls.append(("sql", conn, query))
        self._n += 1
        return Layer(MEMORY, f"sql-{self._n}", facet="vector", name="sql")

    def set_metadata(self, layer: Layer, fields: dict) -> Layer:
        self.calls.append(("metadata", fields))
        return layer

    def save(self, layer: Layer, dest: str) -> Layer:
        self.calls.append(("save", dest))
        return Layer(SOURCE, dest, facet=layer.facet, name=dest)

    def crs_of(self, layer: Layer) -> CrsInfo:
        return self.crs
