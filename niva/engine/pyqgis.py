"""The PyQGIS backend (docs/planning/05-architecture.md).

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


def _feedback(progress, cancel=None):
    """A QgsProcessingFeedback that forwards algorithm progress to ``progress`` (a
    ``callable(str)``) and asks ``cancel`` (a ``callable() -> bool``) whether to abort
    the running algorithm. Returns None if neither is given. Progress % is throttled
    to every 5%; the algorithm's own info/error messages are passed through."""
    if progress is None and cancel is None:
        return None
    from qgis.core import QgsProcessingFeedback

    class _NivaFeedback(QgsProcessingFeedback):
        def __init__(self):
            super().__init__(False)  # don't log to stdout
            self._last = -5

        def setProgress(self, value):  # noqa: N802 — Qt override (virtual; fires periodically)
            # QgsFeedback.isCanceled() is NOT virtual, so we can't intercept the poll —
            # instead, when the caller asks to cancel we call cancel() here to set the
            # internal flag the algorithm checks (it then stops and returns empty).
            # setProgress is the periodic hook on the algorithm's thread.
            if cancel and cancel():
                if not self.isCanceled():
                    if progress is not None:
                        progress("   canceling…")
                    self.cancel()
                return
            super().setProgress(value)
            if progress is None:
                return
            pct = int(value)
            if pct >= self._last + 5:
                self._last = pct
                progress(f"   {pct}%")

        def pushInfo(self, info):  # noqa: N802 — Qt override
            super().pushInfo(info)
            if progress is not None and info.strip():
                progress(f"   {info.strip()}")

        def reportError(self, error, fatalError=False):  # noqa: N802
            super().reportError(error, fatalError)
            if progress is not None:
                progress(f"   ! {error.strip()}")

    return _NivaFeedback()


def owned_app():
    """The QgsApplication niva created (standalone), or None if it reuses a running
    QGIS. The CLI uses this to tear down cleanly before a hard exit."""
    return _QGIS_APP


def algorithm_info(algorithm_id: str):
    """Introspect a QGIS algorithm by id for `describe`. Returns a plain dict, or
    None if no such algorithm is installed. Assumes QGIS is already initialised."""
    from qgis.core import QgsApplication, QgsProcessingParameterDefinition

    alg = QgsApplication.processingRegistry().algorithmById(algorithm_id)
    if alg is None:
        return None
    optional = QgsProcessingParameterDefinition.Flag.FlagOptional
    params = [
        {
            "name": p.name(),
            "type": p.type(),
            "optional": bool(p.flags() & optional),
            "default": p.defaultValue(),
            "description": p.description(),
        }
        for p in alg.parameterDefinitions()
    ]
    outputs = [{"name": o.name(), "type": o.type()} for o in alg.outputDefinitions()]
    return {
        "id": alg.id(),
        "display_name": alg.displayName(),
        "provider": alg.provider().id(),
        "params": params,
        "outputs": outputs,
    }


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
        from qgis.core import QgsProviderRegistry, QgsRasterLayer, QgsVectorLayer

        src = str(source)
        # A GeoPackage / SpatiaLite / etc. holds many layers, tables, and views. If the
        # caller did not name one, refuse to silently grab the first — list them and
        # tell them how to pick (a quiet wrong-layer is exactly the kind of silent error
        # niva exists to prevent; cf. Oscar D-series).
        if "|layername=" not in src and "|layerid=" not in src:
            subs = QgsProviderRegistry.instance().querySublayers(src)
            if len(subs) > 1:
                names = ", ".join(s.name() for s in subs)
                base = os.path.basename(src)
                raise OpError(
                    f"`{source}` holds {len(subs)} layers — name one with "
                    f'`load "{base}|layername=<name>"`. Available: {names}',
                    algorithm="load", params={"source": source}, backend="pyqgis",
                )
        name = os.path.basename(src.split("|", 1)[0]) or src
        if "layername=" in src:
            name = src.split("layername=", 1)[1].split("|", 1)[0] or name
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

    @staticmethod
    def _run_error(algorithm, params, cancel, exc):
        """Wrap a processing failure as OpError — as a cancellation if one was asked."""
        if cancel and cancel():
            return OpError(f"`{algorithm}` canceled", algorithm=algorithm, params={}, backend="pyqgis")
        return OpError(str(exc), algorithm=algorithm, params=params, backend="pyqgis")

    def run(self, algorithm: str, params: dict, *, input_param: str,
            input_layer: Layer, output_param: str, progress=None, cancel=None) -> Layer:
        import processing

        full = dict(params)
        full[input_param] = input_layer.ref
        full[output_param] = "TEMPORARY_OUTPUT"
        try:
            result = processing.run(algorithm, full, feedback=_feedback(progress, cancel))
        except Exception as exc:  # QgsProcessingException and friends
            raise self._run_error(algorithm, full, cancel, exc)
        if cancel and cancel():  # canceled algorithms return an empty result, not an error
            raise OpError(f"`{algorithm}` canceled", algorithm=algorithm, params={}, backend="pyqgis")
        out = result.get(output_param)
        if isinstance(out, str):  # a path/uri rather than a live layer — wrap it
            out = self.load(out).ref
        return Layer(MEMORY, out, facet=self._facet(out), name=algorithm)

    def run_raw(self, algorithm: str, params: dict, *, input_layer: Layer | None = None,
                progress=None, cancel=None):
        import processing

        full = dict(params)
        if "INPUT" not in full and input_layer is not None:
            full["INPUT"] = input_layer.ref
        full.setdefault("OUTPUT", "TEMPORARY_OUTPUT")
        try:
            result = processing.run(algorithm, full, feedback=_feedback(progress, cancel))
        except Exception as exc:
            raise self._run_error(algorithm, full, cancel, exc)
        if cancel and cancel():  # canceled algorithms return an empty result, not an error
            raise OpError(f"`{algorithm}` canceled", algorithm=algorithm, params={}, backend="pyqgis")
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

    def _metadata_dict(self, ref) -> dict:
        md = ref.metadata()
        keywords = []
        for words in md.keywords().values():
            keywords.extend(words)
        return {
            "title": md.title(),
            "abstract": md.abstract(),
            "keywords": keywords,
            "history": list(md.history()),
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
            "metadata": self._metadata_dict(ref),
        }
        if deep:
            import hashlib

            from qgis.core import NULL

            names = [f.name() for f in fields]
            invalid = empty = duplicates = 0
            nulls = {n: 0 for n in names}
            seen = set()  # sha1(WKB) digests — bounds memory on big layers
            for feat in ref.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    empty += 1
                else:
                    if not geom.isGeosValid():
                        invalid += 1
                    digest = hashlib.sha1(bytes(geom.asWkb())).digest()
                    if digest in seen:
                        duplicates += 1
                    else:
                        seen.add(digest)
                for n in names:
                    if feat[n] == NULL:
                        nulls[n] += 1
            prof.update(invalid_geometries=invalid, empty_geometries=empty,
                        duplicate_geometries=duplicates, null_counts=nulls)
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
            "metadata": self._metadata_dict(ref),
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

    def save(self, layer: Layer, dest: str, lineage: list | None = None, *,
             layer_name: str | None = None, append: bool = False) -> Layer:
        # Use QgsVectorFileWriter directly rather than a Processing algorithm: it is
        # the canonical write API, picks the driver from the extension, and does not
        # depend on the Processing registry being populated. We use a standalone
        # transform context (not QgsProject's) so save is safe to call off the main
        # thread — niva runs flows in a background QgsTask in the plugin.
        from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter

        if layer.facet == "raster":
            return self._save_raster(layer, str(dest))
        dest = str(dest)
        ext = os.path.splitext(dest)[1]
        name = layer_name or os.path.splitext(os.path.basename(dest))[0]
        multilayer = ext.lower() in (".gpkg", ".sqlite", ".db")
        options = QgsVectorFileWriter.SaveVectorOptions()
        driver = QgsVectorFileWriter.driverForExtension(ext)
        if driver:
            options.driverName = driver
        if multilayer:  # a known layer name is needed to persist metadata later
            options.layerName = name
            # Append only once the container exists: the FIRST layer creates the file
            # (the default CreateOrOverwriteFile), later layers add to it
            # (CreateOrOverwriteLayer) — so a batch accumulates layers in one .gpkg.
            if append and os.path.exists(dest):
                try:  # Qt6 scopes the enum; Qt5 exposes it flat
                    options.actionOnExistingFile = \
                        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                except AttributeError:  # pragma: no cover — Qt5 path
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
            # If the layer carries an `fid` field (many QGIS outputs do — e.g.
            # points-along-lines, intersection, joins), its values can collide with the
            # GeoPackage primary key → "UNIQUE constraint failed: fid". Tell GDAL to mint
            # a fresh PK and keep the source `fid` as an ordinary attribute (no data loss).
            fields = layer.ref.fields() if hasattr(layer.ref, "fields") else []
            names = {f.name().lower() for f in fields}
            if "fid" in names:
                pk = "gpkg_fid"
                while pk.lower() in names:
                    pk += "_"
                options.layerOptions = [f"FID={pk}"]
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer.ref, dest, QgsCoordinateTransformContext(), options
        )
        if err[0] != 0:  # QgsVectorFileWriter.NoError == 0
            raise OpError(
                f"could not write `{dest}`: {err[1]}",
                algorithm="save", params={"dest": dest}, backend="pyqgis",
            )
        self._persist_metadata(layer, dest, name, multilayer, lineage)
        return Layer(SOURCE, dest, facet="vector", name=os.path.basename(dest))

    def sublayers(self, source: str) -> list:
        """Vector layer names inside a container, via the provider registry. Returns
        ``[]`` when there's only one (so callers take the plain single-layer path)."""
        try:
            from qgis.core import QgsProviderRegistry

            details = QgsProviderRegistry.instance().querySublayers(source)
            names = [d.name() for d in details if d.name()]
            return names if len(names) > 1 else []
        except Exception:
            return []

    def _save_raster(self, layer: Layer, dest: str) -> Layer:
        """Write a raster result to ``dest`` via ``gdal:translate`` — it picks the
        driver from the extension and converts as needed. Runs on the same (worker)
        thread as the rest of the flow, like every other processing.run call here.

        For GeoTIFF output we default to **lossless DEFLATE + tiling** (with the
        PREDICTOR matched to the data type) so products aren't left uncompressed and
        far larger than their inputs. Override with `run gdal:translate … CREATION_OPTIONS=…`
        for other formats/options (e.g. JP2 QUALITY)."""
        import processing

        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        params = {"INPUT": layer.ref, "OUTPUT": dest}
        if os.path.splitext(dest)[1].lower() in (".tif", ".tiff"):
            params["CREATION_OPTIONS"] = self._raster_creation_options(layer.ref)
        try:
            result = processing.run("gdal:translate", params)
        except Exception as exc:
            raise OpError(f"could not write raster `{dest}`: {exc}",
                          algorithm="save", params={"dest": dest}, backend="pyqgis")
        out = result.get("OUTPUT") or dest
        return Layer(SOURCE, out, facet="raster", name=os.path.basename(dest))

    @staticmethod
    def _raster_creation_options(ref) -> str:
        """Sensible lossless GeoTIFF creation options for ``ref``: DEFLATE + tiling,
        with the right PREDICTOR for the data type (3 for floats, 2 for other
        integers, none for Byte). Falls back to plain DEFLATE if the type can't be
        read. Pipe-separated, as QGIS's GDAL algorithms expect."""
        opts = ["COMPRESS=DEFLATE", "TILED=YES"]
        try:
            from qgis.core import Qgis

            dt = ref.dataProvider().dataType(1)
            data_types = Qgis.DataType
            if dt in (data_types.Float32, data_types.Float64):
                opts.append("PREDICTOR=3")
            elif dt != data_types.Byte:
                opts.append("PREDICTOR=2")
        except Exception:  # unknown type / API shift — DEFLATE alone is still safe
            pass
        return "|".join(opts)

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
