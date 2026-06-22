"""The backend seam (docs/planning/05-architecture.md, 06).

The engine never imports QGIS. Everything that touches real geodata goes through a
``Backend``: load a source, run an algorithm, save to disk, report a layer's CRS.
The real ``PyqgisBackend`` (a later increment) drives ``processing.run`` inside
QGIS's interpreter; ``MockBackend`` here is a no-QGIS double that records calls and
hands back fake handles, so the whole engine is testable with plain ``python3`` and
can power a ``--dry-run`` that validates a flow without executing it.
"""

from __future__ import annotations

import abc
import re

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
        a query layer. For SELECT-style reads; non-SELECT statements go to
        ``execute_sql``."""

    @abc.abstractmethod
    def execute_sql(self, conn: str, query: str) -> None:
        """Execute a non-SELECT statement (DDL/DML — ``CREATE``/``UPDATE``/``INSERT``/
        ``DROP``, spatial ``ST_*`` writes) against the named QGIS connection. A
        terminal step: returns nothing. Credentials stay in QGIS's store; the query
        text is never logged in errors."""

    @abc.abstractmethod
    def save_table(self, layer: Layer, conn: str, schema: str | None, table: str, *,
                   mode: str = "create", lineage: list | None = None) -> Layer:
        """Write ``layer`` into a table on the named QGIS connection and return a
        handle to it. ``mode`` is fail-closed: ``create`` errors if the table exists,
        ``replace`` drops+recreates it, ``append`` INSERTs into it. The destination
        URI (host/credentials) is built from the live QGIS connection — the flow never
        sees them. ``lineage`` is recorded best-effort into the table's comment."""

    @abc.abstractmethod
    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str, progress=None, cancel=None) -> Layer:
        """Run ``algorithm`` with ``params``, feeding ``input_layer`` into
        ``input_param`` and a temporary sink into ``output_param``; return the
        output as a new handle. Failures raise ``OpError``. ``progress`` is an
        optional ``callable(str)`` for live status (algorithm progress %)."""

    @abc.abstractmethod
    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None,
                progress=None, cancel=None):
        """The `run` escape hatch: pass ``params`` to ``algorithm`` verbatim. The
        backend injects ``INPUT`` from ``input_layer`` if absent (piped use) and a
        temporary ``OUTPUT`` if absent, then returns the output as a handle, or
        ``None`` if the algorithm produces no pipeable layer (e.g. a folder export)."""

    @abc.abstractmethod
    def profile(self, layer: Layer, deep: bool = False) -> dict:
        """Profile ``layer`` for a data-quality report (08-§4): feature count,
        geometry type, CRS, extent, field schema, and — with ``deep`` — invalid/
        empty geometry counts and per-field null counts. Returns a plain dict; the
        engine formats and writes the markdown."""

    @abc.abstractmethod
    def set_metadata(self, layer: Layer, fields: dict) -> Layer:
        """Attach descriptive metadata (title/abstract/keywords/…) to ``layer`` and
        return it (a pass-through). Persisted to disk by the next ``save``."""

    @abc.abstractmethod
    def save(self, layer: Layer, dest: str, lineage: list | None = None, *,
             layer_name: str | None = None, append: bool = False) -> Layer:
        """Write ``layer`` to ``dest`` and return a handle to the written file.
        ``lineage`` is the list of niva stages that built the layer; the backend
        records them into the output's metadata history (08-§3). ``layer_name`` names
        the written layer (for multi-layer containers); ``append`` adds/replaces just
        that layer in an existing container instead of overwriting the whole file —
        so many ``save … as <layer>`` calls accumulate layers in one GeoPackage."""

    @abc.abstractmethod
    def crs_of(self, layer: Layer) -> CrsInfo:
        """Report ``layer``'s CRS — used to resolve distances (units.py)."""

    @abc.abstractmethod
    def repoint_project(self, src: str, dest: str, *, target, missing: str,
                        rasters: str | None = None, paths: str | None = None,
                        bookmark: str | None = None, progress=None) -> None:
        """Copy the QGIS project ``src`` to ``dest``, optionally repointing each vector
        layer's datasource to ``target``, matched by layer name and preserving subset
        filters and symbology. ``target`` is one of: a GeoPackage path; an
        ``@conn[.schema]`` connection; ``None`` (copy without repointing); or a
        ``{name: uri}`` dict (the `project from-template` slot map — each template layer
        slot, vector *or* raster, is repointed to its same-named dataset). Otherwise raster
        layers are repointed to a same-basename file in the ``rasters`` directory when given.
        ``missing`` (``fail`` | ``keep`` | ``drop``) governs a layer absent from its target.
        ``paths`` (``relative`` | ``absolute``) rewrites datasource path storage; the output
        format follows ``dest``'s extension (``.qgs``/``.qgz``). The `project` verb; never
        silently breaks a project file."""

    @abc.abstractmethod
    def style_layer(self, layer: Layer, action: str, path: str) -> None:
        """``save`` the current layer's style/metadata to the sidecar ``path``, or
        ``apply`` a sidecar to it (persisting the style so QGIS picks it up). ``path``
        ends ``.qml`` (symbology) or ``.qmd`` (metadata). The `style` verb."""

    @abc.abstractmethod
    def create_project(self, layers: list, dest: str, *, crs: str | None = None,
                       title: str | None = None, progress=None) -> None:
        """Write a new QGIS project at ``dest`` loading each layer URI in ``layers``,
        optionally setting the project CRS and title. The `project new` form."""

    @abc.abstractmethod
    def read_project(self, src: str) -> dict:
        """Inventory the QGIS project ``src``: return
        ``{title, crs, layers: [{name, source, provider, type, crs, valid}, …]}``.
        The `project info` form."""

    @abc.abstractmethod
    def list_layers(self, source: str) -> list:
        """List the layers/datasets *inside* a single file or container (GeoPackage,
        SpatiaLite, shapefile, GeoTIFF, …). Returns one dict per layer:
        ``{name, kind ('vector'|'raster'), type (geometry name or raster band summary),
        format (driver/file type), ref (a string you can pass to ``load``)}``. The `show`
        verb; a lightweight name-and-type listing (no feature counts, no deep profiling —
        that's ``catalog``)."""

    @abc.abstractmethod
    def list_tables(self, conn: str, schema: str | None = None,
                    table: str | None = None) -> list:
        """List the tables in a database connection (the loadable ``@conn`` targets).
        ``schema`` limits to one schema (PostGIS); ``table`` limits to one table. Returns
        the same per-entry dicts as :meth:`list_layers`, with ``ref`` an
        ``@conn[.schema].table`` reference. The `show` verb. Never touches credentials —
        QGIS owns them; only the connection name is in scope."""

    @abc.abstractmethod
    def list_service(self, url: str) -> list:
        """List the layers/feature types at a remote OWS endpoint (WFS feature types, WMS
        layers). Returns the same per-entry dicts as :meth:`list_layers`, with ``format``
        ``WFS``/``WMS`` and ``ref`` a GDAL-style ``WFS:``/``WMS:`` source. The `show` verb;
        no credentials are sent (public services only)."""

    @abc.abstractmethod
    def environment_report(self) -> str:
        """A Markdown report of the live QGIS environment — niva build, versions, the
        Processing providers + reachable algorithm count, the registered database
        connection names (the valid ``@conn`` references), the verbs, and the niva
        environment variables (secrets masked). The `info` verb; the CLI counterpart of
        the plugin's Setup-tab Environment report."""

    def sublayers(self, source: str) -> list:
        """List the layer names inside a multi-layer container (e.g. a GeoPackage),
        for ``catalog``. Returns ``[]`` for a single-layer source (the default) — a
        backend overrides this when it can introspect containers."""
        return []

    def connection_names(self) -> list:
        """The names of all registered database connections (the valid ``@conn`` values).
        Used by `show` to resolve a connection reference robustly even when the name
        itself contains dots. ``[]`` by default; a real backend overrides it."""
        return []

    def compact(self, path: str) -> None:
        """Reclaim free pages in a GeoPackage/SpatiaLite container (SQLite ``VACUUM``)
        after multi-layer writes. No-op by default; the real backend implements it."""

    # --- journal echo (concrete; shared by every backend) --------------------

    def render_call(self, algorithm: str, params: dict, *, input_param: str | None = None,
                    input_layer: Layer | None = None, output_param: str | None = None) -> str:
        """A copy-pasteable ``processing.run(...)`` string equivalent to the call this
        op runs — echoed into the journal's machine (jsonl) record. Reconstructs the
        exact dict ``run``/``run_raw`` hand to ``processing.run``: the input layer
        rendered as its source path/URI (not a live-object repr), the output sink as
        ``TEMPORARY_OUTPUT``. ``input_param``/``output_param`` are the curated-verb
        param names; omit both for the ``run`` escape hatch (INPUT/OUTPUT defaults)."""
        full = dict(params)
        if input_param:
            full[input_param] = self._ref_source(input_layer) if input_layer is not None else None
        elif input_layer is not None and "INPUT" not in full:
            full["INPUT"] = self._ref_source(input_layer)
        full.setdefault(output_param or "OUTPUT", "TEMPORARY_OUTPUT")
        body = ", ".join(f"{k!r}: {v!r}" for k, v in full.items())
        return f"processing.run({algorithm!r}, {{{body}}})"

    def _ref_source(self, layer: Layer) -> str:
        """Render a layer handle as a string source for the journal echo. A string
        ref (MockBackend, a path) is used as-is; a live QgsMapLayer reports
        ``.source()``; anything else falls back to the layer's name."""
        ref = layer.ref
        if isinstance(ref, str):
            return ref
        getter = getattr(ref, "source", None)
        return getter() if callable(getter) else layer.name


class MockBackend(Backend):
    """A QGIS-free double: records every operation in ``calls`` and returns fake
    handles. ``crs`` is configurable so tests can exercise both projected and
    geographic distance resolution."""

    def __init__(self, crs: CrsInfo | None = None):
        self.crs = crs or CrsInfo("EPSG:3857", is_geographic=False, units_to_meters=1.0)
        self.calls: list = []
        self.last_lineage: list = []
        self.saves: list = []  # one dict per save: {dest, layer_name, append}
        self.db_saves: list = []  # one dict per DB save: {conn, schema, table, mode}
        self.sublayer_map: dict = {}  # source path -> [layer names], for `each` tests
        self.layer_map = None  # source -> [layer names] for `show` dir tests; None = 2 fakes
        self.conn_names = ["pg", "sl"]  # registered @conn names; tests may add dotted ones
        self._n = 0

    def sublayers(self, source: str) -> list:
        return list(self.sublayer_map.get(source, []))

    def connection_names(self) -> list:
        return list(self.conn_names)

    def valid_crs(self, text: str) -> bool:
        # No QGIS CRS database here — accept the well-formed forms used in tests, and treat an
        # obviously-bogus EPSG code (≥ 6 digits) as invalid so engine validation is exercisable.
        t = text.strip()
        m = re.fullmatch(r"(?i)epsg:(\d+)", t)
        if m:
            return len(m.group(1)) < 6
        return bool(t)

    def compact(self, path: str) -> None:
        self.calls.append(("compact", path))

    def load(self, source: str, *, facet: str = "vector") -> Layer:
        self.calls.append(("load", source))
        return Layer(SOURCE, source, facet=facet, name=source)

    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str, progress=None, cancel=None) -> Layer:
        self.calls.append(("run", algorithm, params))
        self._n += 1
        return Layer(MEMORY, f"result-{self._n}", facet=input_layer.facet,
                     name=f"{algorithm}#{self._n}")

    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None,
                progress=None, cancel=None):
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

    def execute_sql(self, conn: str, query: str) -> None:
        self.calls.append(("execute_sql", conn, query))
        return None

    def save_table(self, layer: Layer, conn: str, schema: str | None, table: str, *,
                   mode: str = "create", lineage: list | None = None) -> Layer:
        self.calls.append(("save_table", conn, schema, table, mode))
        self.db_saves.append({"conn": conn, "schema": schema, "table": table, "mode": mode})
        self.last_lineage = list(lineage) if lineage else []
        ref = f"@{conn}." + (f"{schema}.{table}" if schema else table)
        return Layer(DB_TABLE, ref, facet="vector", name=table)

    def repoint_project(self, src: str, dest: str, *, target, missing: str,
                        rasters: str | None = None, paths: str | None = None,
                        bookmark: str | None = None, progress=None) -> None:
        self.calls.append(
            ("repoint_project", src, dest, target, missing, rasters, paths, bookmark))

    def style_layer(self, layer: Layer, action: str, path: str) -> None:
        self.calls.append(("style", action, path))

    def create_project(self, layers: list, dest: str, *, crs: str | None = None,
                       title: str | None = None, progress=None) -> None:
        self.calls.append(("create_project", list(layers), dest, crs, title))

    def read_project(self, src: str) -> dict:
        self.calls.append(("read_project", src))
        return {"title": "", "crs": "", "layers": []}

    def list_layers(self, source: str) -> list:
        self.calls.append(("list_layers", source))
        if self.layer_map is not None:
            # Realistic: only mapped sources have layers; everything else is empty (so a
            # directory scan that probes every file mirrors querySublayers filtering junk).
            names = list(self.layer_map.get(source, []))
            return [{"name": n, "kind": "vector", "type": "Polygon", "format": "GPKG",
                     "ref": f"{source}|layername={n}"} for n in names]
        return [
            {"name": "layer_a", "kind": "vector", "type": "Polygon",
             "format": "GPKG", "ref": f"{source}|layername=layer_a"},
            {"name": "layer_b", "kind": "vector", "type": "Point",
             "format": "GPKG", "ref": f"{source}|layername=layer_b"},
        ]

    def list_tables(self, conn: str, schema: str | None = None,
                    table: str | None = None) -> list:
        self.calls.append(("list_tables", conn, schema, table))
        prefix = f"@{conn}." + (f"{schema}." if schema else "")
        rows = [
            {"name": "roads", "kind": "vector", "type": "LineString",
             "format": "postgres", "ref": f"{prefix}roads"},
            {"name": "homes", "kind": "vector", "type": "Point",
             "format": "postgres", "ref": f"{prefix}homes"},
        ]
        return [r for r in rows if table is None or r["name"] == table]

    def list_service(self, url: str) -> list:
        self.calls.append(("list_service", url))
        return [
            {"name": "topp:states", "kind": "vector", "type": "EPSG:4326",
             "format": "WFS", "ref": f"WFS:{url}"},
            {"name": "topp:roads", "kind": "vector", "type": "EPSG:4326",
             "format": "WFS", "ref": f"WFS:{url}"},
        ]

    def environment_report(self) -> str:
        self.calls.append(("environment_report",))
        return "# niva — environment\n\n- Backend: mock (no QGIS)\n"

    def profile(self, layer: Layer, deep: bool = False) -> dict:
        self.calls.append(("assess", layer.name, deep))
        prof = {
            "name": layer.name,
            "facet": layer.facet,
            "crs": {"authid": "EPSG:3857", "geographic": False, "valid": True},
            "feature_count": 2,
            "geometry_type": "Point",
            "extent": {"xmin": 0.0, "ymin": 0.0, "xmax": 1.0, "ymax": 1.0},
            "fields": [{"name": "id", "type": "Integer"}],
            "metadata": {"title": "", "abstract": "", "keywords": [], "history": []},
        }
        if deep:
            prof.update(invalid_geometries=0, empty_geometries=0,
                        duplicate_geometries=0, null_counts={"id": 0})
        return prof

    def set_metadata(self, layer: Layer, fields: dict) -> Layer:
        self.calls.append(("metadata", fields))
        return layer

    def save(self, layer: Layer, dest: str, lineage: list | None = None, *,
             layer_name: str | None = None, append: bool = False) -> Layer:
        self.calls.append(("save", dest))
        self.saves.append({"dest": dest, "layer_name": layer_name, "append": append})
        self.last_lineage = list(lineage) if lineage else []
        return Layer(SOURCE, dest, facet=layer.facet, name=dest)

    def crs_of(self, layer: Layer) -> CrsInfo:
        return self.crs
