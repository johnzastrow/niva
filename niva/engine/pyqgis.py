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
from contextlib import contextmanager

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


@contextmanager
def _capture_qgis_messages(progress):
    """Forward QGIS message-log Warnings/Criticals emitted during a run (e.g.
    "Cannot use preferred transform between EPSG:… — grid file not available") to
    ``progress`` and collect them, so they land in the human output and the journal
    instead of vanishing into the QGIS log panel. Best-effort; never fatal. Yields the
    list of captured message strings."""
    captured: list = []
    if progress is None:
        yield captured
        return
    try:
        from qgis.core import QgsApplication
    except Exception:
        yield captured
        return
    log = QgsApplication.messageLog()

    def handler(message, tag, level):
        try:
            if int(level) >= 1 and message and message.strip():  # Warning(1)/Critical(2)
                text = message.strip()
                progress(f"   [QGIS:{tag}] {text}")
                captured.append(text)
        except Exception:
            pass

    try:
        log.messageReceived.connect(handler)
    except Exception:
        yield captured
        return
    try:
        yield captured
    finally:
        try:
            log.messageReceived.disconnect(handler)
        except Exception:
            pass


def _is_geometry_type_error(exc) -> bool:
    """True if ``exc`` is QGIS refusing to write a feature whose geometry type does not
    match a typed output sink (e.g. a GeometryCollection into a MultiPolygon layer)."""
    msg = str(exc).lower()
    return "could not" in msg and "feature" in msg and "geometry type" in msg


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
    def _transform_note(input_layer, target_crs):
        """If the *preferred* (most accurate) datum transform from the layer's CRS to
        ``target_crs`` is unavailable because a grid file is missing — so a less
        accurate transform is used — return a one-line notice (with the missing grids
        and download URL). This is what QGIS's GUI shows as "Cannot use preferred
        transform …"; we surface it into the log too. Returns None when the preferred
        transform is available. Best-effort; never raises."""
        try:
            from qgis.core import QgsCoordinateReferenceSystem, QgsDatumTransform

            src = input_layer.ref.crs()
            dst = QgsCoordinateReferenceSystem(str(target_crs))
            if not (src.isValid() and dst.isValid()):
                return None
            ops = QgsDatumTransform.operations(src, dst)
            if not ops or ops[0].isAvailable:
                return None  # the preferred operation is usable — nothing to warn about
            preferred, used = ops[0], next((o for o in ops if o.isAvailable), None)
            grids = []
            for g in getattr(preferred, "grids", []):
                if not g.isAvailable:
                    grids.append(getattr(g, "url", "") or g.shortName)
            grid_txt = ("; install: " + ", ".join(dict.fromkeys(grids))) if grids else ""
            used_acc = f"±{used.accuracy} m" if used and used.accuracy and used.accuracy > 0 else "a fallback"
            pref_acc = f"±{preferred.accuracy} m" if preferred.accuracy and preferred.accuracy > 0 else "a more accurate"
            return (f"datum transform {src.authid()}→{dst.authid()}: the preferred "
                    f"transform ({pref_acc}) needs a grid not installed, so {used_acc} "
                    f"was used{grid_txt}")
        except Exception:
            return None

    def _note_qgis_messages(self, captured) -> None:
        """Fold any captured QGIS warnings (e.g. a preferred-transform notice) into the
        per-op journal note, unless a more specific note (mixed geometry) was set."""
        if captured and not getattr(self, "_note", None):
            uniq = list(dict.fromkeys(captured))
            self._note = "QGIS: " + " | ".join(uniq)[:400]

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
        with _capture_qgis_messages(progress) as captured:
            try:
                result = processing.run(algorithm, full, feedback=_feedback(progress, cancel))
            except Exception as exc:  # QgsProcessingException and friends
                # A typed output sink rejects features whose geometry type doesn't match
                # (e.g. a stray GeometryCollection in a polygon layer). For the operations
                # that have a lossless GDAL equivalent we redo the op keeping a GENERIC
                # geometry (so nothing is dropped); otherwise we raise a clear, actionable
                # error telling the user to `fix` first. See _lossless_retry.
                if _is_geometry_type_error(exc):
                    retried = self._lossless_retry(algorithm, input_layer, full)
                    if retried is not None:
                        note = ("mixed geometry encountered (GeometryCollection): reprojected "
                                "LOSSLESSLY into a generic-geometry layer, keeping every part. "
                                "Note: a single-type target like Shapefile can't store this, and "
                                "homogenising ops (clip/dissolve) would drop the odd parts — use "
                                "`split` to separate by type if you need them kept.")
                        self._note = note
                        if progress:
                            progress("   ⚠ " + note)
                        return retried
                raise self._run_error(algorithm, full, cancel, exc)
        self._note_qgis_messages(captured)
        if algorithm == "native:reprojectlayer" and not getattr(self, "_note", None):
            tnote = self._transform_note(input_layer, full.get("TARGET_CRS"))
            if tnote:
                self._note = tnote
                if progress:
                    progress("   ⚠ " + tnote)
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
        with _capture_qgis_messages(progress) as captured:
            try:
                result = processing.run(algorithm, full, feedback=_feedback(progress, cancel))
            except Exception as exc:
                raise self._run_error(algorithm, full, cancel, exc)
        self._note_qgis_messages(captured)
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
            hint = ""
            if ext.lower() == ".shp":
                # Shapefile stores ONE geometry type per file; mixed/collection geometry
                # (kept losslessly through reproject/clip) can't be written to it.
                hint = (" — Shapefile stores a single geometry type, so it can't hold "
                        "mixed/GeometryCollection geometry; save to .gpkg or .sqlite "
                        "instead.")
            raise OpError(
                f"could not write `{dest}`: {err[1]}{hint}",
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

    def _lossless_retry(self, algorithm: str, layer: Layer, full: dict):
        """Redo a typed-sink op that choked on mixed geometry, keeping a GENERIC output
        (``-nlt GEOMETRY``) so nothing is dropped. Operations with a GDAL equivalent
        (reproject, clip) are redone via ``osgeo.gdal`` (ships with QGIS, no extra dep);
        for the rest we raise a clear, actionable error pointing at `fix`. Returns a new
        Layer, or None to let the caller re-raise the original error (e.g. a non-file
        source)."""
        src = self._file_source(layer)
        if src is None:
            return None  # not file-backed (mid-pipe memory layer) — can't GDAL it
        path, layer_name = src

        if algorithm == "native:reprojectlayer":
            # Reprojection is a pure, geometry-preserving transform with a clean GDAL
            # equivalent, so we can redo it losslessly into a generic-geometry layer.
            target = full.get("TARGET_CRS")
            if not target:
                return None
            out = self._gdal_generic(path, layer_name, dstSRS=str(target))
            if out is None:
                return None
            return Layer(MEMORY, self.load(out).ref, facet="vector", name=algorithm)
        # Other operations that reject a mixed geometry have no lossless reimplementation
        # here — surface a clear, actionable error rather than guess.
        raise OpError(
            f"`{algorithm}` can't write this layer's mixed geometry (it has "
            "GeometryCollection features). Insert `fix` before it to coerce them into "
            "one type (drops the non-matching parts).",
            algorithm=algorithm, params={}, backend="pyqgis",
        )

    @staticmethod
    def _file_source(layer: Layer):
        """(path, layer_name|None) for a file-backed layer, else None."""
        ref = getattr(layer, "ref", None)
        source = ref.source() if hasattr(ref, "source") else None
        return PyqgisBackend._split_source(source)

    @staticmethod
    def _split_source(source):
        if not source:
            return None
        path = str(source).split("|", 1)[0]
        layer_name = None
        for part in str(source).split("|")[1:]:
            if part.startswith("layername="):
                layer_name = part.split("=", 1)[1]
        return (path, layer_name) if os.path.isfile(path) else None

    def _gdal_generic(self, path, layer_name, *, dstSRS=None):
        """Run GDAL VectorTranslate writing a GENERIC-geometry GeoPackage (``-nlt
        GEOMETRY`` keeps each feature's native type), optionally reprojecting
        (``dstSRS``). Returns the output path, or None on any failure."""
        try:
            from osgeo import gdal

            gdal.UseExceptions()
            out = self._temp_path(".gpkg")
            kwargs = {"geometryType": ["GEOMETRY"]}
            if layer_name:
                kwargs["layers"] = [layer_name]
            if dstSRS:
                kwargs["dstSRS"] = dstSRS
                kwargs["reproject"] = True
            gdal.VectorTranslate(out, path, options=gdal.VectorTranslateOptions(**kwargs))
            return out
        except Exception:  # GDAL unavailable / option unsupported — re-raise original
            return None

    @staticmethod
    def _temp_path(suffix: str) -> str:
        import tempfile

        fd, path = tempfile.mkstemp(suffix=suffix, prefix="niva_")
        os.close(fd)
        os.remove(path)  # GDAL wants to create it
        return path

    def compact(self, path: str) -> None:
        """VACUUM a GeoPackage/SpatiaLite container to reclaim free pages left by
        multi-layer appends. A GeoPackage is a SQLite database, so stdlib ``sqlite3``
        does it with no extra dependency. Best effort — raised errors are caught by
        the engine (a failed VACUUM never fails the flow)."""
        import sqlite3

        con = sqlite3.connect(path)
        try:
            con.execute("VACUUM")
            con.commit()
        finally:
            con.close()

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
        ext = os.path.splitext(dest)[1].lower()
        if ext in (".tif", ".tiff"):
            params["CREATION_OPTIONS"] = self._raster_creation_options(layer.ref)
        elif ext == ".jp2":
            # JP2OpenJPEG with no options writes near-lossless and balloons (a mosaic
            # can dwarf its inputs). Default to QUALITY=25 — a sensible visually-lossless
            # ratio for imagery. Override via `run gdal:translate … CREATION_OPTIONS=…`.
            params["CREATION_OPTIONS"] = "QUALITY=25"
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
