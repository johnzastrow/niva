"""The PyQGIS backend (planning/05-architecture.md).

The adapter that makes niva actually *do* geoprocessing: it implements the four
``Backend`` methods against QGIS's ``processing.run`` and ``QgsMapLayer`` API. All
``qgis`` imports are **lazy** (inside functions), so importing this module on a
plain interpreter never fails — only *using* the backend requires QGIS. That keeps
the rest of niva importable everywhere and lets the smoke test skip cleanly when
QGIS is absent.

Two ways niva gets a QGIS context (``ensure_qgis``):
- **Inside a running QGIS** (Python console, a marimo notebook launched on QGIS's
  interpreter): an app already exists — reuse it, just initialise Processing.
- **Standalone** (``niva run`` from a shell on QGIS's Python): bootstrap a headless,
  offscreen ``QgsApplication`` and initialise Processing.
"""

from __future__ import annotations

import os
import sys

from ..errors import OpError
from .backend import Backend
from .layer import DB_TABLE, MEMORY, SOURCE, CrsInfo, Layer

# Retained module-side so neither object is garbage-collected after creation:
# a dropped QgsApplication tears down the whole Processing registry, and a dropped
# QgsNativeAlgorithms takes its 339 algorithms with it. Both bit us in testing.
_QGIS_APP = None
_NATIVE_PROVIDER = None


def ensure_qgis(prefix: str | None = None):
    """Make sure a QGIS application and Processing are available.

    Returns ``(app, owns)`` — ``owns`` is True only when niva created the app (so a
    standalone caller knows it should ``app.exitQgis()`` on the way out)."""
    global _QGIS_APP
    from qgis.core import QgsApplication

    app = QgsApplication.instance()
    owns = False
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        prefix = prefix or os.environ.get("QGIS_PREFIX_PATH") or "/usr"
        QgsApplication.setPrefixPath(prefix, True)
        app = QgsApplication([], False)
        app.initQgis()
        _QGIS_APP = app  # CRITICAL: keep a reference, or it is GC'd and the registry dies
        owns = True
    _init_processing()
    return app, owns


def _init_processing():
    from qgis.core import QgsApplication

    global _NATIVE_PROVIDER
    reg = QgsApplication.processingRegistry()
    # A standalone QgsApplication does NOT load the native (C++) algorithms into the
    # Processing registry by itself — `Processing.initialize()` alone leaves it empty
    # in this build — so add them explicitly. CRITICAL: the QgsNativeAlgorithms
    # instance must be kept alive; if it is garbage-collected its 339 algorithms
    # vanish from the registry. We give it the registry as Qt parent AND hold a
    # module reference. Guarded so we only add it once (idempotent across re-entry;
    # inside a running QGIS the native provider is already present).
    if _NATIVE_PROVIDER is None and reg.providerById("native") is None:
        try:
            from qgis.analysis import QgsNativeAlgorithms

            _NATIVE_PROVIDER = QgsNativeAlgorithms(reg)
            reg.addProvider(_NATIVE_PROVIDER)
        except Exception:  # pragma: no cover — best effort; run() reports a clear error
            _NATIVE_PROVIDER = None
    plugins = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
    if plugins not in sys.path:
        sys.path.append(plugins)
    import processing  # noqa: F401  (brings in the Python providers: gdal, grass, …)
    from processing.core.Processing import Processing

    Processing.initialize()


class PyqgisBackend(Backend):
    def load(self, source: str, *, facet: str = "vector") -> Layer:
        from qgis.core import QgsRasterLayer, QgsVectorLayer

        src = str(source)
        name = os.path.basename(src.split("|", 1)[0]) or src
        vl = QgsVectorLayer(src, name, "ogr")
        if vl.isValid():
            return Layer(SOURCE, vl, facet="vector", name=name)
        rl = QgsRasterLayer(src, name)
        if rl.isValid():
            return Layer(SOURCE, rl, facet="raster", name=name)
        raise OpError(
            f"could not open `{source}` as a vector or raster layer",
            algorithm="load", params={"source": source}, backend="pyqgis",
        )

    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str) -> Layer:
        import processing

        full = dict(params)
        full[input_param] = input_layer.ref
        full[output_param] = "TEMPORARY_OUTPUT"
        try:
            result = processing.run(algorithm, full)
        except Exception as exc:  # QgsProcessingException and friends
            raise OpError(str(exc), algorithm=algorithm, params=full, backend="pyqgis") from exc
        out = result.get(output_param)
        if isinstance(out, str):  # a path/uri rather than a live layer — wrap it
            out = self.load(out).ref
        return Layer(MEMORY, out, facet=self._facet(out), name=algorithm)

    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None):
        import processing

        full = dict(params)
        if "INPUT" not in full and input_layer is not None:
            full["INPUT"] = input_layer.ref
        full.setdefault("OUTPUT", "TEMPORARY_OUTPUT")
        try:
            result = processing.run(algorithm, full)
        except Exception as exc:
            raise OpError(str(exc), algorithm=algorithm, params=full, backend="pyqgis") from exc
        out = result.get("OUTPUT")
        if out is None:  # no pipeable output (e.g. a folder/PDF export) — terminal
            return None
        if isinstance(out, str):
            try:
                return self.load(out)
            except OpError:  # wrote something that is not a loadable layer
                return Layer(SOURCE, out, facet="vector", name=os.path.basename(out))
        return Layer(MEMORY, out, facet=self._facet(out), name=algorithm)

    # --- data-quality profiling (assess, 08-§4) ------------------------------

    def profile(self, layer: Layer, deep: bool = False) -> dict:
        if layer.facet == "raster":
            return self._profile_raster(layer)
        return self._profile_vector(layer, deep)

    def _crs_dict(self, ref) -> dict:
        crs = ref.crs()
        return {
            "authid": crs.authid() or "(none)",
            "geographic": crs.isGeographic(),
            "valid": crs.isValid(),
        }

    def _extent_dict(self, ref):
        e = ref.extent()
        if e.isNull() or e.isEmpty():
            return None
        return {"xmin": e.xMinimum(), "ymin": e.yMinimum(),
                "xmax": e.xMaximum(), "ymax": e.yMaximum()}

    def _profile_vector(self, layer: Layer, deep: bool) -> dict:
        from qgis.core import QgsWkbTypes

        ref = layer.ref
        fields = ref.fields()
        prof = {
            "name": ref.name() or layer.name,
            "facet": "vector",
            "crs": self._crs_dict(ref),
            "feature_count": ref.featureCount(),
            "geometry_type": QgsWkbTypes.displayString(ref.wkbType()),
            "extent": self._extent_dict(ref),
            "fields": [{"name": f.name(), "type": f.typeName()} for f in fields],
        }
        if deep:
            from qgis.core import NULL

            names = [f.name() for f in fields]
            invalid = empty = 0
            nulls = {n: 0 for n in names}
            for feat in ref.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    empty += 1
                elif not geom.isGeosValid():
                    invalid += 1
                for n in names:
                    if feat[n] == NULL:
                        nulls[n] += 1
            prof.update(invalid_geometries=invalid, empty_geometries=empty, null_counts=nulls)
        return prof

    def _profile_raster(self, layer: Layer) -> dict:
        ref = layer.ref
        return {
            "name": ref.name() or layer.name,
            "facet": "raster",
            "crs": self._crs_dict(ref),
            "width": ref.width(),
            "height": ref.height(),
            "bands": ref.bandCount(),
            "extent": self._extent_dict(ref),
        }

    def set_metadata(self, layer: Layer, fields: dict) -> Layer:
        md = layer.ref.metadata()
        for key, value in fields.items():
            if key == "title":
                md.setTitle(value)
            elif key == "abstract":
                md.setAbstract(value)
            elif key == "keywords":
                md.setKeywords({"keywords": [k.strip() for k in value.split(",") if k.strip()]})
            elif key == "identifier":
                md.setIdentifier(value)
            elif key in ("license", "licence"):
                md.setLicenses([value])
            # unknown keys are rejected by the engine before we get here
        layer.ref.setMetadata(md)
        return layer

    def save(self, layer: Layer, dest: str, lineage: list | None = None) -> Layer:
        # Use QgsVectorFileWriter directly rather than a Processing algorithm: it is
        # the canonical write API, picks the driver from the extension, and does not
        # depend on the Processing registry being populated.
        from qgis.core import QgsProject, QgsVectorFileWriter

        if layer.facet == "raster":
            raise OpError(
                "saving raster results is not supported yet in v0.1",
                algorithm="save", params={"dest": dest}, backend="pyqgis",
            )
        dest = str(dest)
        ext = os.path.splitext(dest)[1]
        name = os.path.splitext(os.path.basename(dest))[0]
        multilayer = ext.lower() in (".gpkg", ".sqlite", ".db")
        options = QgsVectorFileWriter.SaveVectorOptions()
        driver = QgsVectorFileWriter.driverForExtension(ext)
        if driver:
            options.driverName = driver
        if multilayer:  # a known layer name is needed to persist metadata later
            options.layerName = name
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer.ref, dest, QgsProject.instance().transformContext(), options
        )
        if err[0] != 0:  # QgsVectorFileWriter.NoError == 0
            raise OpError(
                f"could not write `{dest}`: {err[1]}",
                algorithm="save", params={"dest": dest}, backend="pyqgis",
            )
        self._persist_metadata(layer, dest, name, multilayer, lineage)
        return Layer(SOURCE, dest, facet="vector", name=os.path.basename(dest))

    def _persist_metadata(self, layer: Layer, dest: str, name: str,
                          multilayer: bool, lineage: list | None) -> None:
        """Carry the source layer's descriptive metadata onto the written file and
        record the niva lineage into its history (08-§3). Best effort; runs only when
        there is something to write (descriptive fields or lineage)."""
        getter = getattr(layer.ref, "metadata", None)
        md = getter() if callable(getter) else None
        has_descriptive = bool(md and (md.title() or md.abstract() or md.keywords()))
        if not has_descriptive and not lineage:
            return
        from qgis.core import QgsVectorLayer

        uri = f"{dest}|layername={name}" if multilayer else dest
        out = QgsVectorLayer(uri, name, "ogr")
        if not out.isValid():
            return
        target = md if md is not None else out.metadata()
        for entry in lineage or []:
            target.addHistoryItem(f"niva: {entry}")
        out.setMetadata(target)
        ok, _msg = out.saveDefaultMetadata()
        if not ok:  # fall back to a .qmd sidecar
            out.saveNamedMetadata(os.path.splitext(dest)[0] + ".qmd")

    # --- database connections (credentials stay in QGIS's store) -------------

    def _find_connection(self, name: str):
        """Locate a named connection across all DB providers. Returns
        ``(metadata, connection)`` or raises OpError. Never touches credentials —
        QGIS owns them; we resolve by name only."""
        from qgis.core import QgsProviderRegistry

        reg = QgsProviderRegistry.instance()
        for provider in reg.providerList():
            md = reg.providerMetadata(provider)
            if md is None:
                continue
            try:
                conns = md.connections(False)  # {name: connection}; raises on non-DB providers
            except Exception:
                continue
            if name in conns:
                return md, conns[name]
        raise OpError(
            f"no saved QGIS connection named `{name}` — configure it in QGIS first",
            algorithm="connection", params={"connection": name}, backend="pyqgis",
        )

    def load_table(self, conn: str, schema: str | None, table: str) -> Layer:
        from qgis.core import QgsVectorLayer

        md, connection = self._find_connection(conn)
        try:
            uri = connection.tableUri(schema or "", table)
        except Exception as exc:
            raise OpError(
                f"connection `{conn}` cannot reference table `{table}`: {exc}",
                algorithm="load", params={"connection": conn, "table": table}, backend="pyqgis",
            ) from exc
        layer = QgsVectorLayer(uri, table, md.key())
        if not layer.isValid():
            raise OpError(
                f"could not load table `{table}` from connection `{conn}`",
                algorithm="load", params={"connection": conn, "table": table}, backend="pyqgis",
            )
        return Layer(DB_TABLE, layer, facet="vector", name=table)

    def run_sql(self, conn: str, query: str) -> Layer:
        from qgis.core import QgsAbstractDatabaseProviderConnection as DbConn

        _md, connection = self._find_connection(conn)
        options = DbConn.SqlVectorLayerOptions()
        options.sql = query
        try:
            layer = connection.createSqlVectorLayer(options)
        except Exception as exc:
            # The connection name is logged; the query text is not (it stays in the
            # provider). No credentials are ever in scope here.
            raise OpError(
                f"SQL query against connection `{conn}` failed: {exc}",
                algorithm="sql", params={"connection": conn}, backend="pyqgis",
            ) from exc
        if layer is None or not layer.isValid():
            raise OpError(
                f"SQL query against connection `{conn}` produced no valid layer",
                algorithm="sql", params={"connection": conn}, backend="pyqgis",
            )
        return Layer(MEMORY, layer, facet="vector", name="sql")

    def crs_of(self, layer: Layer) -> CrsInfo:
        from qgis.core import Qgis, QgsUnitTypes

        crs = layer.ref.crs()
        authid = crs.authid() or "USER:0"
        if crs.isGeographic():
            return CrsInfo(authid, True, map_units="degrees")
        map_unit = crs.mapUnits()
        factor = QgsUnitTypes.fromUnitToUnitFactor(map_unit, Qgis.DistanceUnit.Meters)
        return CrsInfo(
            authid, False,
            units_to_meters=factor or 1.0,
            map_units=QgsUnitTypes.toString(map_unit),
        )

    def _facet(self, obj) -> str:
        from qgis.core import QgsRasterLayer

        return "raster" if isinstance(obj, QgsRasterLayer) else "vector"
