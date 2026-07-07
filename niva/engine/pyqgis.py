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
import re
import sys
import tempfile
from contextlib import contextmanager

from ..errors import OpError
from .backend import Backend
from .connections import default_schema, is_connection_ref, parse_connection_ref
from .layer import DB_TABLE, MEMORY, SOURCE, CrsInfo, Layer

# A GDAL/OGR processing algorithm runs an external command; on a nonzero exit QGIS's
# GdalUtils reports "Process returned error code N" through the feedback but does NOT
# raise from processing.run — so without this check a failed warp/clip/translate would
# look like success. We treat a nonzero code here as a hard failure.
_GDAL_ERRCODE_RE = re.compile(r"returned error code\s+(\d+)")


def _command_failure(errors):
    """The error line proving an algorithm's external command exited nonzero (a
    "Process returned error code N" with N != 0), or None. Pure helper shared by the
    feedback and the engine so it's unit-testable without QGIS."""
    for e in errors:
        m = _GDAL_ERRCODE_RE.search(e)
        if m and m.group(1) != "0":
            return e
    return None


def scratch_dir() -> str:
    """Directory for niva's large intermediate GDAL/Processing scratch.

    Big raster steps (``warp``, ``clipraster``, ``hillshade``, …) write a full
    intermediate raster — often gigabytes — before ``save`` re-encodes it to the
    user's chosen format. By default that scratch lands in the system temp dir,
    which on many setups is a small, quota'd **tmpfs** (RAM-backed ``/tmp``): a long
    raster pipeline can exhaust it and abort the run mid-flight with a "disk quota
    exceeded" error even when the real disk has hundreds of gigabytes free.

    Set ``NIVA_TMPDIR`` to a roomy, disk-backed folder to keep that scratch off the
    tmpfs. When it is set (and creatable), niva writes raster intermediates there and
    points GDAL's own internal scratch (``CPL_TMPDIR``) at the same place. When it is
    unset, behaviour is unchanged — the system temp dir is used.
    """
    d = os.environ.get("NIVA_TMPDIR")
    if d:
        try:
            os.makedirs(d, exist_ok=True)
            os.environ.setdefault("CPL_TMPDIR", d)  # GDAL internal scratch, too
            return d
        except OSError:  # not creatable/writable — fall back rather than fail the run
            pass
    return tempfile.gettempdir()


def _layer_source_path(layer):
    """The absolute on-disk path backing ``layer`` (a :class:`Layer` or None), or None.

    Used to spare a run's final raster from scratch cleanup. Handles both a path-string
    ref (a saved file) and a live ``QgsMapLayer`` ref (whose ``source()`` carries the
    path, possibly with a ``|layername=…`` suffix)."""
    ref = getattr(layer, "ref", None)
    if ref is None:
        return None
    if isinstance(ref, str):
        src = ref
    else:
        source = getattr(ref, "source", None)
        src = source() if callable(source) else None
    if not src:
        return None
    return os.path.abspath(src.split("|", 1)[0])


# Retained module-side so neither object is garbage-collected after creation:
# a dropped QgsApplication tears down the whole Processing registry, and a dropped
# QgsNativeAlgorithms takes its 339 algorithms with it. Both bit us in testing.
_QGIS_APP = None
_NATIVE_PROVIDER = None

# SpatiaLite ships internal metadata + virtual tables (the KNN/KNN2 nearest-neighbour modules,
# ElementaryGeometries, SpatialIndex, data_licenses, and the *_geometry_columns* registries).
# These are not user data. QGIS 4 hides them from a connection's table listing, but older QGIS
# (3.x) reports some — e.g. KNN2 and data_licenses — as ordinary spatial tables, so `show @conn`
# would advertise them as loadable layers. Drop them so discovery lists only real layers
# consistently across QGIS versions. Names are SpatiaLite-reserved, so this can't hide user data.
_SPATIALITE_SYSTEM_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "spatial_ref_sys_aux",
        "spatialite_history",
        "sql_statements_log",
        "geometry_columns",
        "geometry_columns_auth",
        "geometry_columns_field_infos",
        "geometry_columns_statistics",
        "geometry_columns_time",
        "views_geometry_columns",
        "views_geometry_columns_auth",
        "views_geometry_columns_field_infos",
        "views_geometry_columns_statistics",
        "virts_geometry_columns",
        "virts_geometry_columns_auth",
        "virts_geometry_columns_field_infos",
        "virts_geometry_columns_statistics",
        "spatialindex",
        "elementarygeometries",
        "knn",
        "knn2",
        "data_licenses",
        "sqlite_sequence",
        "niva_lineage",  # niva's own provenance table (aspatial) — metadata, not user data
    }
)


def _is_spatialite_system_table(name: str) -> bool:
    """True for a SpatiaLite-internal metadata/virtual table that isn't user data."""
    return name.lower() in _SPATIALITE_SYSTEM_TABLES


def _desktop_profile_folder() -> str | None:
    """Point a standalone niva at the SAME QGIS user profile the desktop uses, so the
    registered database connections (the ``@conn`` names a flow references), and other
    QGIS settings, match exactly what the user sees in QGIS.

    A ``QgsApplication`` created off the GUI otherwise falls back to a generic Qt
    settings store (``…/Unknown Organization.ini``) that contains *none* of the user's
    connections — so ``load @conn.table`` and the ``info`` report would be blind to them.
    Setting the Qt org/app identity to QGIS's own (``QGIS`` / ``QGIS<major>``) makes
    ``QgsSettings`` resolve to
    ``~/.local/share/QGIS/QGIS<major>/profiles/<profile>/QGIS/QGIS<major>.ini`` — the real
    profile. The active profile comes from the desktop's ``profiles.ini`` (``lastProfile``),
    or ``$NIVA_QGIS_PROFILE`` to force one. Returns the profile folder for the
    ``QgsApplication`` constructor, or ``None`` if it can't be resolved (QGIS then uses its
    own default). Only relevant when niva creates the app — inside the QGIS plugin the app
    already exists and this is never called.

    Best-effort: any failure here must never stop QGIS from initialising."""
    from qgis.core import Qgis
    from qgis.PyQt.QtCore import QCoreApplication, QStandardPaths

    try:
        # Adopt QGIS's QSettings identity (only if the host hasn't already set one).
        if not QCoreApplication.organizationName():
            QCoreApplication.setOrganizationName("QGIS")
            QCoreApplication.setOrganizationDomain("qgis.org")
            QCoreApplication.setApplicationName(f"QGIS{Qgis.QGIS_VERSION_INT // 10000}")
        # PyQt6 enums are scoped; PyQt5 exposes them unscoped — support both.
        loc = getattr(QStandardPaths, "AppDataLocation", None)
        if loc is None:
            loc = QStandardPaths.StandardLocation.AppDataLocation
        root = os.path.join(QStandardPaths.writableLocation(loc), "profiles")
        profile = os.environ.get("NIVA_QGIS_PROFILE")
        if not profile:
            import configparser

            cp = configparser.ConfigParser()
            cp.read(os.path.join(root, "profiles.ini"))
            profile = cp.get("core", "lastProfile", fallback="default")
        folder = os.path.join(root, profile)
        return folder if os.path.isdir(folder) else None
    except Exception:  # noqa: BLE001 — never block QGIS init on profile resolution
        return None


def _qgis_prefix_path() -> str:
    """Infer the QGIS prefix path from the running interpreter.

    On macOS, QGIS ships as a .app bundle where the interpreter lives at
    ``<Bundle>.app/Contents/MacOS/python3.x`` and the provider plugins live at
    ``<Bundle>.app/Contents/PlugIns/qgis``. QgsApplication.setPrefixPath() must
    receive the bundle root (``<Bundle>.app``) so it resolves the plugin path
    as ``Contents/PlugIns/qgis`` — passing the inner ``Contents/MacOS`` level
    causes a doubly-nested path that misses all database providers (spatialite,
    postgres, WFS, …). On Linux the QGIS prefix is typically ``/usr``.
    """
    import sys

    exe = sys.executable  # e.g. .../QGIS.app/Contents/MacOS/python3.12
    parts = exe.replace("\\", "/").split("/")
    # Walk up to find the .app bundle root on macOS.
    for i, part in enumerate(parts):
        if part.endswith(".app"):
            return "/".join(parts[: i + 1])
    return "/usr"


def _qgis_python_dirs() -> list:
    """Directories that may hold QGIS's Python bindings (the ``qgis`` package), so
    ``import qgis`` can work on a standalone interpreter that wasn't told where QGIS lives —
    e.g. a plain ``pip install qgis-niva`` into Ubuntu's **system** Python, where the bindings
    sit at ``/usr/share/qgis/python`` and aren't on ``sys.path`` by default. Ordered by
    priority; only directories that exist are returned."""
    import sys

    cands: list = []
    env = os.environ.get("NIVA_QGIS_PYTHONPATH")
    if env:
        cands += env.split(os.pathsep)
    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        cands.append(
            os.path.join(prefix, "share", "qgis", "python")
        )  # Unix prefix layout
        cands.append(os.path.join(prefix, "python"))  # some bundle layouts
    exe = sys.executable.replace(
        "\\", "/"
    )  # macOS: infer the .app bundle from the interpreter
    parts = exe.split("/")
    for i, part in enumerate(parts):
        if part.endswith(".app"):
            bundle = "/".join(parts[: i + 1])
            cands.append(os.path.join(bundle, "Contents", "Resources", "python"))
            break
    cands += [
        "/usr/share/qgis/python",  # Debian/Ubuntu/Fedora system QGIS
        "/Applications/QGIS.app/Contents/Resources/python",  # macOS default install
    ]
    seen, out = set(), []
    for d in cands:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def _ensure_qgis_importable() -> None:
    """Best-effort: make the ``qgis`` package importable by adding known binding directories to
    ``sys.path`` when it isn't already. A no-op when ``import qgis`` already works (inside QGIS,
    the plugin, or a correctly-set ``PYTHONPATH``). Never raises — if nothing is found the
    caller's import fails with the usual clear message. Override/extend via ``NIVA_QGIS_PYTHONPATH``."""
    import importlib.util
    import sys

    if importlib.util.find_spec("qgis") is not None:
        return
    for d in _qgis_python_dirs():
        if d not in sys.path:
            sys.path.insert(0, d)
        importlib.invalidate_caches()
        if importlib.util.find_spec("qgis") is not None:
            return


def ensure_qgis(prefix: str | None = None):
    """Make sure a QGIS application and Processing are available.

    Returns ``(app, owns)`` — ``owns`` is True only when niva created the app (so a
    standalone caller knows it should ``app.exitQgis()`` on the way out)."""
    global _QGIS_APP
    _ensure_qgis_importable()  # add QGIS's bindings to sys.path if a bare interpreter lacks them
    from qgis.core import QgsApplication

    app = QgsApplication.instance()
    owns = False
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        prefix = prefix or os.environ.get("QGIS_PREFIX_PATH") or _qgis_prefix_path()
        profile_folder = _desktop_profile_folder()
        QgsApplication.setPrefixPath(prefix, True)
        # Pass the desktop profile folder so `@conn` names match the QGIS GUI.
        if profile_folder:
            app = QgsApplication([], False, profile_folder, "external")
        else:
            app = QgsApplication([], False)
        app.initQgis()
        _QGIS_APP = (
            app  # CRITICAL: keep a reference, or it is GC'd and the registry dies
        )
        _install_gdal_error_filter()
        owns = True
    _init_processing()
    return app, owns


def _install_gdal_error_filter() -> None:
    """Filter one benign GDAL message out of standalone niva's stderr: when a flow reads from
    and writes to the *same* GeoPackage, GDAL probes the optional `gpkg_metadata` table under
    SQLite lock contention and logs ``unable to open database file`` — yet the write succeeds
    and niva reports real failures through its own error codes. We drop exactly that message
    and pass everything else through (so genuine GDAL errors stay visible). Installed only when
    niva owns the QGIS app (CLI/standalone); inside the QGIS plugin, QGIS owns error routing."""
    import sys

    from osgeo import gdal

    def handler(err_class, err_no, msg):
        if "gpkg_metadata" in msg and "unable to open database file" in msg:
            return
        if err_class >= gdal.CE_Warning:
            label = "ERROR" if err_class >= gdal.CE_Failure else "Warning"
            sys.stderr.write(f"{label} {err_no}: {msg}\n")

    try:
        gdal.PushErrorHandler(handler)
    except Exception:  # noqa: BLE001 — never let error-handler setup break QGIS init
        pass


def _feedback(progress, cancel=None):
    """A QgsProcessingFeedback that forwards algorithm progress to ``progress`` (a
    ``callable(str)``) and asks ``cancel`` (a ``callable() -> bool``) whether to abort
    the running algorithm. Progress % is throttled to every 5%; the algorithm's own
    info/error messages are passed through.

    Always returns an instance (never None) so callers can also inspect it for a
    command failure afterwards: some providers — notably the GDAL/OGR algorithms — run
    an external command that can exit nonzero yet still return a result dict from
    ``processing.run`` without raising. The feedback records those error lines so
    ``run``/``run_raw`` can detect the "Process returned error code N" sentinel and fail
    the step instead of reporting a false success (see ``command_failure``)."""
    from qgis.core import QgsProcessingFeedback

    class _NivaFeedback(QgsProcessingFeedback):
        def __init__(self):
            super().__init__(False)  # don't log to stdout
            self._last = -5
            self.errors: list[str] = []  # error lines the algorithm reported

        def command_failure(self):
            """The error line proving the algorithm's external command failed (a nonzero
            "Process returned error code N"), or None. This is the signal that a GDAL/OGR
            op did *not* really succeed even though ``processing.run`` returned a result."""
            return _command_failure(self.errors)

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
            text = (error or "").strip()
            if text:
                self.errors.append(text)
            if progress is not None and text:
                progress(f"   ! {text}")

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
            if (
                int(level) >= 1 and message and message.strip()
            ):  # Warning(1)/Critical(2)
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


def algorithm_catalog():
    """Every installed QGIS Processing algorithm, for `search`/`docs`: one dict per
    algorithm — ``{id, display_name, group, description}``. Assumes QGIS is initialised.
    Hidden/deprecated algorithms are skipped (they aren't `run`-able discovery targets)."""
    from qgis.core import QgsApplication, QgsProcessingAlgorithm

    try:
        hidden = QgsProcessingAlgorithm.Flag.FlagHideFromToolbox
    except AttributeError:  # pragma: no cover — older Qt enum access
        hidden = QgsProcessingAlgorithm.FlagHideFromToolbox
    out = []
    for alg in QgsApplication.processingRegistry().algorithms():
        if int(alg.flags()) & int(hidden):
            continue
        out.append(
            {
                "id": alg.id(),
                "display_name": alg.displayName(),
                "group": alg.group() or "",
                "description": alg.shortDescription() or "",
            }
        )
    return out


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
    def __init__(self):
        self._note = (
            None  # per-op handling notice (e.g. mixed geometry), read by Engine
        )
        self._scratch: list[
            str
        ] = []  # raster intermediates to delete when the run ends

    def purge_scratch(self, keep=None, remove_dir=False) -> None:
        """Delete the intermediates this run created in the scratch dir.

        ``keep`` is the run's final :class:`Layer` (or ``None``): its on-disk source is
        spared so a terminal ``warp``/``clipraster`` with no ``save`` still resolves on
        the map. Called from the engine's top-level ``finally`` — including after a
        failed run, so a crash no longer strands gigabytes of scratch behind it.
        Best-effort: a file that cannot be removed is left, never raised.

        ``remove_dir`` (set only on a clean, successful run) additionally removes the
        niva-owned scratch *directory* itself — but only when ``NIVA_TMPDIR`` was set
        (never the shared system temp fallback) and only if it is now empty, so a user
        dir holding other files is never touched. ``scratch_dir`` recreates it next run."""
        keep_src = _layer_source_path(keep)
        survivors = []
        for path in self._scratch:
            if keep_src and os.path.abspath(path) == keep_src:
                survivors.append(path)
                continue
            for f in (path, path + ".aux.xml", path + ".ovr"):
                try:
                    os.remove(f)
                except OSError:  # already gone / in use — leave it
                    pass
        self._scratch = survivors
        if remove_dir and not survivors:
            d = os.environ.get("NIVA_TMPDIR")
            if d:
                try:
                    os.rmdir(d)  # only succeeds if empty — safe for a shared/user dir
                except OSError:  # non-empty or in use — leave it
                    pass

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
                    algorithm="load",
                    params={"source": source},
                    backend="pyqgis",
                )
        name = os.path.basename(src.split("|", 1)[0]) or src
        if "layername=" in src:
            name = src.split("layername=", 1)[1].split("|", 1)[0] or name
        vl = QgsVectorLayer(src, name, "ogr")
        if vl.isValid():
            # A delimited-text file (CSV/TSV) with longitude/latitude columns loads *aspatial*
            # through OGR. Detect that and rebuild it as a point layer so it's geoprocessable —
            # otherwise a `load points.csv | buffer …` silently fails on a geometry-less layer.
            pts = self._csv_point_layer(src, vl, name)
            return Layer(SOURCE, pts or vl, facet="vector", name=name)
        rl = QgsRasterLayer(src, name)
        if rl.isValid():
            return Layer(SOURCE, rl, facet="raster", name=name)
        raise OpError(
            f"could not open `{source}` as a vector or raster layer",
            algorithm="load",
            params={"source": source},
            backend="pyqgis",
        )

    # Delimited-text extensions niva will try to geometrize, and the coordinate-column names it
    # recognises. Only the GEOGRAPHIC longitude/latitude family is auto-detected — those imply
    # EPSG:4326 unambiguously. Projected x/y / easting-northing are intentionally NOT guessed
    # (their CRS is unknowable from a header), so they stay aspatial rather than silently wrong.
    _CSV_EXTS = (".csv", ".tsv", ".txt")
    _LON_NAMES = ("longitude", "lon", "lng", "long", "x_long", "long_x")
    _LAT_NAMES = ("latitude", "lat", "y_lat", "lat_y")

    def _csv_point_layer(self, src: str, ogr_layer, name: str):
        """If ``src`` is a delimited-text file that OGR loaded *aspatial* but whose columns hold
        longitude/latitude, return a point layer built via QGIS's delimited-text provider (CRS
        EPSG:4326). Returns None if it isn't applicable — caller falls back to the aspatial layer.

        The provider URI is assembled with QUrlQuery so the (file-controlled) column names are
        URL-encoded — no string-built URI or VRT/XML, hence no injection surface."""
        path = src.split("|", 1)[0]
        if os.path.splitext(path)[1].lower() not in self._CSV_EXTS:
            return None
        if not self._is_aspatial(
            ogr_layer
        ):  # already has geometry (e.g. a WKT column) — leave it
            return None
        fields = {f.name().lower(): f.name() for f in ogr_layer.fields()}
        xcol = next((fields[n] for n in self._LON_NAMES if n in fields), None)
        ycol = next((fields[n] for n in self._LAT_NAMES if n in fields), None)
        if not (xcol and ycol):
            return None

        from qgis.core import QgsVectorLayer
        from qgis.PyQt.QtCore import QUrl, QUrlQuery

        url = QUrl.fromLocalFile(os.path.abspath(path))
        query = QUrlQuery()
        for key, val in (
            ("type", "csv"),
            ("detectTypes", "yes"),
            ("xField", xcol),
            ("yField", ycol),
            ("crs", "EPSG:4326"),
            ("spatialIndex", "no"),
            ("subsetIndex", "no"),
            ("watchFile", "no"),
        ):
            query.addQueryItem(key, val)
        url.setQuery(query)
        pts = QgsVectorLayer(url.toString(), name, "delimitedtext")
        if pts.isValid() and not self._is_aspatial(pts) and pts.featureCount() > 0:
            return pts
        return None

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
            grid_txt = (
                ("; install: " + ", ".join(dict.fromkeys(grids))) if grids else ""
            )
            used_acc = (
                f"±{used.accuracy} m"
                if used and used.accuracy and used.accuracy > 0
                else "a fallback"
            )
            pref_acc = (
                f"±{preferred.accuracy} m"
                if preferred.accuracy and preferred.accuracy > 0
                else "a more accurate"
            )
            return (
                f"datum transform {src.authid()}→{dst.authid()}: the preferred "
                f"transform ({pref_acc}) needs a grid not installed, so {used_acc} "
                f"was used{grid_txt}"
            )
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
            return OpError(
                f"`{algorithm}` canceled",
                algorithm=algorithm,
                params={},
                backend="pyqgis",
            )
        return OpError(str(exc), algorithm=algorithm, params=params, backend="pyqgis")

    @staticmethod
    def _raise_on_command_failure(algorithm, params, feedback):
        """Fail the step if the algorithm's external command exited nonzero.

        ``processing.run`` returns a result dict for the GDAL/OGR algorithms even when
        their command failed (e.g. a truncated raster: gdalwarp prints "Process returned
        error code 1" and writes an empty output). Without this, niva would report a
        false success and hand on a blank/partial result. ``feedback`` is the
        ``_NivaFeedback`` we passed in; ``command_failure`` returns the proving line."""
        err = feedback.command_failure() if feedback is not None else None
        if err:
            raise OpError(
                f"`{algorithm}` failed — the underlying command did not complete "
                f"({err}). The input may be corrupt or truncated.",
                algorithm=algorithm,
                params=params,
                backend="pyqgis",
            )

    @staticmethod
    def _output_is_raster(algorithm: str, output_param: str) -> bool:
        """True if ``algorithm``'s ``output_param`` is a raster output — so a raster-in /
        vector-out op (e.g. gdal:polygonize) is correctly treated as producing a vector."""
        from qgis.core import QgsApplication

        alg = QgsApplication.processingRegistry().algorithmById(algorithm)
        if alg is None:
            return False
        try:
            od = alg.outputDefinition(output_param)
        except Exception:
            od = None
        return od is not None and "raster" in (od.type() or "").lower()

    def run(
        self,
        algorithm: str,
        params: dict,
        *,
        input_param: str,
        input_layer: Layer,
        output_param: str,
        progress=None,
        cancel=None,
    ) -> Layer:
        import processing

        full = dict(params)
        full[input_param] = input_layer.ref
        # Raster intermediates can be gigabytes. QGIS's ``TEMPORARY_OUTPUT`` sentinel
        # writes them into the system temp dir — often a small, quota'd tmpfs that a
        # long raster pipeline exhausts. Give raster *outputs* an explicit GeoTIFF path in
        # niva's scratch dir (relocatable off the tmpfs via NIVA_TMPDIR) and track it so
        # the engine can delete it once the run ends. Keying on the OUTPUT facet (not the
        # input's) matters for raster-in / vector-out ops like `gdal:polygonize`: their
        # output is a vector, which must NOT be forced to a `.tif`. See ``scratch_dir``.
        if self._output_is_raster(algorithm, output_param):
            full[output_param] = self._temp_path(".tif")
        else:
            full[output_param] = "TEMPORARY_OUTPUT"
        feedback = _feedback(progress, cancel)
        with _capture_qgis_messages(progress) as captured:
            try:
                result = processing.run(algorithm, full, feedback=feedback)
            except Exception as exc:  # QgsProcessingException and friends
                # A typed output sink rejects features whose geometry type doesn't match
                # (e.g. a stray GeometryCollection in a polygon layer). For the operations
                # that have a lossless GDAL equivalent we redo the op keeping a GENERIC
                # geometry (so nothing is dropped); otherwise we raise a clear, actionable
                # error telling the user to `fixgeom` first. See _lossless_retry.
                if _is_geometry_type_error(exc):
                    retried = self._lossless_retry(algorithm, input_layer, full)
                    if retried is not None:
                        note = (
                            "mixed geometry encountered (GeometryCollection): reprojected "
                            "LOSSLESSLY into a generic-geometry layer, keeping every part. "
                            "Note: a single-type target like Shapefile can't store this, and "
                            "homogenising ops (clip/dissolve) would drop the odd parts — use "
                            "`split` to separate by type if you need them kept."
                        )
                        self._note = note
                        if progress:
                            progress("   ⚠ " + note)
                        return retried
                    # No lossless retry (e.g. a mid-pipe memory layer, or an op without a GDAL
                    # equivalent) — raise the honest geometry-type error for ANY input, not the
                    # raw QGIS message.
                    raise self._geometry_type_error(algorithm)
                raise self._run_error(algorithm, full, cancel, exc)
        self._raise_on_command_failure(algorithm, full, feedback)
        self._note_qgis_messages(captured)
        if algorithm == "native:reprojectlayer" and not getattr(self, "_note", None):
            tnote = self._transform_note(input_layer, full.get("TARGET_CRS"))
            if tnote:
                self._note = tnote
                if progress:
                    progress("   ⚠ " + tnote)
        if (
            cancel and cancel()
        ):  # canceled algorithms return an empty result, not an error
            raise OpError(
                f"`{algorithm}` canceled",
                algorithm=algorithm,
                params={},
                backend="pyqgis",
            )
        out = result.get(output_param)
        if isinstance(out, str):  # a path/uri rather than a live layer — wrap it
            out = self.load(out).ref
        return Layer(MEMORY, out, facet=self._facet(out), name=algorithm)

    def run_raw(
        self,
        algorithm: str,
        params: dict,
        *,
        input_layer: Layer | None = None,
        progress=None,
        cancel=None,
    ):
        import processing

        full = dict(params)
        if "INPUT" not in full and input_layer is not None:
            full["INPUT"] = input_layer.ref
        full.setdefault("OUTPUT", "TEMPORARY_OUTPUT")
        feedback = _feedback(progress, cancel)
        with _capture_qgis_messages(progress) as captured:
            try:
                result = processing.run(algorithm, full, feedback=feedback)
            except Exception as exc:
                raise self._run_error(algorithm, full, cancel, exc)
        self._raise_on_command_failure(algorithm, full, feedback)
        self._note_qgis_messages(captured)
        if (
            cancel and cancel()
        ):  # canceled algorithms return an empty result, not an error
            raise OpError(
                f"`{algorithm}` canceled",
                algorithm=algorithm,
                params={},
                backend="pyqgis",
            )
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
        return {
            "xmin": e.xMinimum(),
            "ymin": e.yMinimum(),
            "xmax": e.xMaximum(),
            "ymax": e.yMaximum(),
        }

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
                    # usedforsecurity=False: this digest only dedups geometries (bounds
                    # memory), it is never a security/integrity check — so a fast non-crypto
                    # use of SHA-1 is fine and correct here.
                    digest = hashlib.sha1(
                        bytes(geom.asWkb()), usedforsecurity=False
                    ).digest()
                    if digest in seen:
                        duplicates += 1
                    else:
                        seen.add(digest)
                for n in names:
                    if feat[n] == NULL:
                        nulls[n] += 1
            prof.update(
                invalid_geometries=invalid,
                empty_geometries=empty,
                duplicate_geometries=duplicates,
                null_counts=nulls,
            )
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
                md.setKeywords(
                    {"keywords": [k.strip() for k in value.split(",") if k.strip()]}
                )
            elif key == "identifier":
                md.setIdentifier(value)
            elif key in ("license", "licence"):
                md.setLicenses([value])
            # unknown keys are rejected by the engine before we get here
        layer.ref.setMetadata(md)
        return layer

    def save(
        self,
        layer: Layer,
        dest: str,
        lineage: list | None = None,
        *,
        layer_name: str | None = None,
        append: bool = False,
    ) -> Layer:
        # Use QgsVectorFileWriter directly rather than a Processing algorithm: it is
        # the canonical write API, picks the driver from the extension, and does not
        # depend on the Processing registry being populated. We use a standalone
        # transform context (not QgsProject's) so save is safe to call off the main
        # thread — niva runs flows in a background QgsTask in the plugin.
        from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter

        if layer.facet == "raster":
            return self._save_raster(layer, str(dest), lineage)
        dest = str(dest)
        ext = os.path.splitext(dest)[1]
        name = layer_name or os.path.splitext(os.path.basename(dest))[0]
        multilayer = ext.lower() in (".gpkg", ".sqlite", ".db")
        options = QgsVectorFileWriter.SaveVectorOptions()
        driver = QgsVectorFileWriter.driverForExtension(ext)
        if driver:
            options.driverName = driver
        # A `.sqlite` target should be a real SpatiaLite database (so QGIS's SpatiaLite
        # connection + `sql @conn` ST_* functions work), not a bare OGR SQLite. The
        # dataset-creation option is honoured on first write and ignored on append.
        if ext.lower() == ".sqlite":
            options.datasourceOptions = ["SPATIALITE=YES"]
        # Attribute fields the output driver can't store as plain columns. Inspect once and
        # adjust the write so a single awkward field never sinks the whole save.
        wfields = layer.ref.fields() if hasattr(layer.ref, "fields") else []
        # (1) A geometry-TYPED attribute field — e.g. a PostGIS table's geometry column that the
        # provider surfaced as an attribute (a second column, or an SRID-0/unregistered one) —
        # cannot be written as an attribute ("Unsupported type for field <name>"). Identify it by
        # DATA TYPE, never by name: a geometry column can be called anything (`geom`, `shape`,
        # `the_geom`, …). QGIS types a geometry attribute as the Qt *user* type; the typeName
        # (`geometry`/`geography`) is a secondary signal. Drop it (the layer keeps its own
        # geometry) and surface the loss rather than failing the save.
        try:
            from qgis.PyQt.QtCore import QMetaType

            user_type = int(QMetaType.Type.User)
        except Exception:  # pragma: no cover — Qt5 fallback
            from qgis.PyQt.QtCore import QVariant

            user_type = int(QVariant.UserType)

        def _is_geom_field(f):
            return int(f.type()) == user_type or (f.typeName() or "").lower() in (
                "geometry",
                "geography",
            )

        drop = [i for i, f in enumerate(wfields) if _is_geom_field(f)]
        if drop:
            options.attributes = [i for i in range(len(wfields)) if i not in drop]
            dropped = ", ".join(f"`{wfields[i].name()}`" for i in drop)
            self._note = (
                f"save: dropped geometry-typed attribute field(s) {dropped} — a "
                f"{ext.lstrip('.') or 'vector'} file can't hold a geometry as an "
                "attribute (the layer's own geometry is unaffected)"
            )
        names = {
            wfields[i].name().lower() for i in range(len(wfields)) if i not in drop
        }
        layer_opts: list[str] = []

        if multilayer:  # a known layer name is needed to persist metadata later
            options.layerName = name
            # Append only once the container exists: the FIRST layer creates the file
            # (the default CreateOrOverwriteFile), later layers add to it
            # (CreateOrOverwriteLayer) — so a batch accumulates layers in one .gpkg.
            if append and os.path.exists(dest):
                try:  # Qt6 scopes the enum; Qt5 exposes it flat
                    options.actionOnExistingFile = (
                        QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                    )
                except AttributeError:  # pragma: no cover — Qt5 path
                    options.actionOnExistingFile = (
                        QgsVectorFileWriter.CreateOrOverwriteLayer
                    )
            # (2) If the layer carries an `fid` field (many QGIS outputs do — e.g.
            # points-along-lines, intersection, joins), its values can collide with the
            # GeoPackage primary key → "UNIQUE constraint failed: fid". Tell GDAL to mint
            # a fresh PK and keep the source `fid` as an ordinary attribute (no data loss).
            if "fid" in names:
                pk = "gpkg_fid"
                while pk.lower() in names:
                    pk += "_"
                layer_opts.append(f"FID={pk}")
            # (3) An attribute literally named like the GeoPackage geometry column (`geom`)
            # collides → "Cannot create field geom. It has the same name as the geometry
            # field". Name the output geometry column something else so the attribute survives.
            if ext.lower() == ".gpkg" and "geom" in names:
                gname = "geometry"
                while gname.lower() in names:
                    gname += "_"
                layer_opts.append(f"GEOMETRY_NAME={gname}")
        if layer_opts:
            options.layerOptions = layer_opts
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer.ref, dest, QgsCoordinateTransformContext(), options
        )
        if err[0] != 0:  # QgsVectorFileWriter.NoError == 0
            hint = ""
            if ext.lower() == ".shp":
                # Shapefile stores ONE geometry type per file; mixed/collection geometry
                # (kept losslessly through reproject/clip) can't be written to it.
                hint = (
                    " — Shapefile stores a single geometry type, so it can't hold "
                    "mixed/GeometryCollection geometry; save to .gpkg or .sqlite "
                    "instead."
                )
            elif not os.path.isabs(dest) and (
                "unable to open" in err[1].lower()
                or "creation of data source" in err[1].lower()
            ):
                # A relative path resolves against the QGIS plugin's working directory
                # (inside the app bundle on macOS, or another non-writable location).
                # Give a concrete corrective hint instead of a raw OGR error.
                hint = (
                    f" — `{dest}` is a relative path; the QGIS plugin's working "
                    "directory is not writable. Use an absolute path, e.g. "
                    f"`~/Desktop/{dest}` or `/Users/you/Documents/{dest}`."
                )
            raise OpError(
                f"could not write `{dest}`: {err[1]}{hint}",
                algorithm="save",
                params={"dest": dest},
                backend="pyqgis",
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
        for the rest we raise a clear, actionable error pointing at `fixgeom`. Returns a new
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
        # Other operations have no lossless reimplementation here — let the caller raise the
        # honest geometry-type error (so it fires for memory-backed inputs too).
        return None

    @staticmethod
    def _geometry_type_error(algorithm: str) -> "OpError":
        """The honest, actionable error when a typed-output op (centroid, point-on-surface, …)
        can't write a feature's geometry. Names BOTH real causes rather than guessing: mixed
        geometry (`fixgeom` coerces it) or invalid/empty geometry (NaN coordinates / no CRS,
        which `fixgeom` can't repair — the layer is likely corrupt; `assess`/`show` reveal it)."""
        return OpError(
            f"`{algorithm}` couldn't write a feature's geometry into its typed output. If the "
            "layer has mixed geometry types, insert `fixgeom` before it to coerce them. If "
            "`fixgeom` doesn't help, the geometry is likely invalid or empty (e.g. NaN "
            "coordinates or no CRS) — inspect the layer with `assess` or `show`.",
            algorithm=algorithm,
            params={},
            backend="pyqgis",
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
            gdal.VectorTranslate(
                out, path, options=gdal.VectorTranslateOptions(**kwargs)
            )
            return out
        except Exception:  # GDAL unavailable / option unsupported — re-raise original
            return None

    def _temp_path(self, suffix: str) -> str:
        """A fresh path in the scratch dir for an intermediate niva writes itself — a
        raster op's explicit output, or a lossless-retry GeoPackage. Tracked in
        ``_scratch`` so ``purge_scratch`` deletes it when the run ends (these are
        consumed by the next stage; only the run's final layer is spared)."""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="niva_", dir=scratch_dir())
        os.close(fd)
        os.remove(path)  # GDAL wants to create it
        self._scratch.append(path)
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

    def _save_raster(
        self, layer: Layer, dest: str, lineage: list | None = None
    ) -> Layer:
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
        feedback = _feedback(
            None
        )  # captures a nonzero "returned error code" from gdal_translate
        try:
            result = processing.run("gdal:translate", params, feedback=feedback)
        except Exception as exc:
            raise OpError(
                f"could not write raster `{dest}`: {exc}",
                algorithm="save",
                params={"dest": dest},
                backend="pyqgis",
            )
        self._raise_on_command_failure("save", {"dest": dest}, feedback)
        out = result.get("OUTPUT") or dest
        # Record provenance/lineage onto the raster too (embedded where the format allows,
        # else a .qmd sidecar) — rasters used to skip this entirely.
        self._persist_metadata(
            layer, out, os.path.splitext(os.path.basename(out))[0], False, lineage
        )
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

    def _persist_metadata(
        self, layer: Layer, dest: str, name: str, multilayer: bool, lineage: list | None
    ) -> None:
        """Carry the source layer's descriptive metadata onto the written file and
        record the niva lineage into its history (08-§3). Best effort; runs only when
        there is something to write (descriptive fields or lineage)."""
        getter = getattr(layer.ref, "metadata", None)
        md = getter() if callable(getter) else None
        has_descriptive = bool(md and (md.title() or md.abstract() or md.keywords()))
        if not has_descriptive and not lineage:
            return
        from qgis.core import QgsRasterLayer, QgsVectorLayer

        uri = f"{dest}|layername={name}" if multilayer else dest
        # Re-open the WRITTEN output as the right layer type. Rasters (DEMs, hillshades,
        # pdalcli exports) must open as a raster — opening them as a vector is invalid, which
        # used to silently drop their lineage entirely.
        if getattr(layer, "facet", "vector") == "raster":
            out = QgsRasterLayer(dest, name)
        else:
            out = QgsVectorLayer(uri, name, "ogr")
            if not out.isValid():  # e.g. a raster reached here with a stale facet
                out = QgsRasterLayer(dest, name)
        if not out.isValid():
            return
        from .. import __version__

        target = md if md is not None else out.metadata()
        # Stamp the niva version: with the flow text below, it pins the exact defaults this
        # run used (look them up with that version's `describe <id>` / algorithm catalog).
        target.addHistoryItem(f"niva {__version__}")
        for entry in lineage or []:
            target.addHistoryItem(f"niva: {entry}")
        out.setMetadata(target)
        # Try to embed (GeoPackage stores it internally). Formats that can't embed QGIS
        # metadata (GeoTIFF, Shapefile, …) get a `.qmd` sidecar written alongside so the
        # provenance is never lost.
        ok, _msg = out.saveDefaultMetadata()
        if (
            not ok
        ):  # can't embed → write a .qmd sidecar (best-effort; never fail a save)
            out.saveNamedMetadata(os.path.splitext(dest)[0] + ".qmd")

    def write_metadata_sidecar(self, dest: str, lineage: list | None) -> None:
        """Write a standalone `.qmd` provenance sidecar next to ``dest`` for outputs that
        don't pass through :meth:`save`'s metadata path — chiefly point clouds the pdalcli
        harness writes with an explicit ``output=``. Builds the QGIS metadata document
        directly (no layer needed), so it works even for a raw ``.las``/``.laz`` this build
        can't open as a layer. Best-effort — never raises."""
        if not lineage:
            return
        try:
            from qgis.core import QgsLayerMetadata
            from qgis.PyQt.QtXml import QDomDocument

            from .. import __version__

            md = QgsLayerMetadata()
            md.addHistoryItem(
                f"niva {__version__}"
            )  # pins this run's parameter defaults
            for entry in lineage:
                md.addHistoryItem(f"niva: {entry}")
            doc = QDomDocument("qgis")
            root = doc.createElement("qgis")
            root.setAttribute("version", f"niva {__version__}")
            md.writeMetadataXml(root, doc)
            doc.appendChild(root)
            sidecar = os.path.splitext(dest)[0] + ".qmd"
            with open(sidecar, "w", encoding="utf-8") as fh:
                fh.write(doc.toString(2))
        except Exception:  # noqa: BLE001 — provenance is best-effort, never break the run
            pass

    # --- database connections (credentials stay in QGIS's store) -------------

    def connection_names(self) -> list:
        """All registered DB connection names across providers (for `show` to resolve a
        ``@conn`` reference, robust to names containing dots)."""
        from qgis.core import QgsProviderRegistry

        reg = QgsProviderRegistry.instance()
        names = set()
        for provider in reg.providerList():
            md = reg.providerMetadata(provider)
            if md is None:
                continue
            try:
                names.update(md.connections(False).keys())
            except Exception:  # noqa: BLE001 — non-DB provider
                continue
        return sorted(names)

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
                conns = md.connections(
                    False
                )  # {name: connection}; raises on non-DB providers
            except Exception:
                continue
            if name in conns:
                return md, conns[name]
        raise OpError(
            f"no saved QGIS connection named `{name}` — configure it in QGIS first",
            algorithm="connection",
            params={"connection": name},
            backend="pyqgis",
        )

    def load_table(self, conn: str, schema: str | None, table: str) -> Layer:
        from qgis.core import QgsVectorLayer

        md, connection = self._find_connection(conn)
        try:
            uri = connection.tableUri(schema or "", table)
        except Exception as exc:
            raise OpError(
                f"connection `{conn}` cannot reference table `{table}`: {exc}",
                algorithm="load",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            ) from exc
        layer = QgsVectorLayer(uri, table, md.key())
        # Some `tableUri` results omit the geometry column (seen with PostGIS tables whose name
        # has unusual characters, or whose geometry isn't in the server's `geometry_columns`
        # view) — the layer then opens *aspatial* (NoGeometry) with empty geometry, which
        # silently breaks every downstream geometry op (reproject/buffer/centroid → empty). If
        # the connection's own metadata reports a geometry column, rebuild the URI with it.
        if layer.isValid() and self._is_aspatial(layer):
            geom_col = self._table_geometry_column(connection, schema or "", table)
            if geom_col:
                spatial = self._spatial_table_layer(
                    connection, schema or "", table, geom_col, md.key()
                )
                if spatial is not None:
                    layer = spatial
        if not layer.isValid():
            raise OpError(
                f"could not load table `{table}` from connection `{conn}`",
                algorithm="load",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            )
        return Layer(DB_TABLE, layer, facet="vector", name=table)

    @staticmethod
    def _is_aspatial(layer) -> bool:
        from qgis.core import QgsWkbTypes

        return QgsWkbTypes.displayString(layer.wkbType()) == "NoGeometry"

    @staticmethod
    def _table_geometry_column(connection, schema: str, table: str):
        """The geometry column name the connection reports for ``table`` (or None). Used to
        rescue a spatial table that ``tableUri`` opened as aspatial."""
        try:
            for t in connection.tables(schema):
                if t.tableName() == table and t.geometryColumnCount() > 0:
                    return t.geometryColumn()
        except Exception:  # noqa: BLE001 — best effort
            pass
        return None

    @staticmethod
    def _spatial_table_layer(
        connection, schema: str, table: str, geom_col: str, provider: str
    ):
        """Open ``table`` as a layer with an explicit geometry column, building the URI from
        the live connection (host/credentials stay in QGIS). Returns the layer if it is valid
        and actually spatial, else None."""
        from qgis.core import QgsDataSourceUri, QgsVectorLayer

        try:
            uri = QgsDataSourceUri(connection.uri())
            uri.setDataSource(schema, table, geom_col)
            layer = QgsVectorLayer(uri.uri(False), table, provider)
            if layer.isValid() and not PyqgisBackend._is_aspatial(layer):
                return layer
        except Exception:  # noqa: BLE001
            pass
        return None

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
                algorithm="sql",
                params={"connection": conn},
                backend="pyqgis",
            ) from exc
        if layer is None or not layer.isValid():
            raise OpError(
                f"SQL query against connection `{conn}` produced no valid layer",
                algorithm="sql",
                params={"connection": conn},
                backend="pyqgis",
            )
        # The provider doesn't always auto-detect the geometry column of a SELECT result, so a
        # spatial query can come back *aspatial* (NoGeometry) with the geometry sitting as an
        # ordinary attribute — breaking any geometry op on the result. If a result column is a
        # geometry type, name it and recreate the layer. Detected BY TYPE, any column name.
        if self._is_aspatial(layer):
            layer = self._respatialize_sql(connection, options, layer) or layer
        return Layer(MEMORY, layer, facet="vector", name="sql")

    # Column names commonly used for a geometry, and the attribute *types* a serialized
    # geometry can masquerade as. SpatiaLite surfaces a **computed** geometry (e.g.
    # `ST_Centroid(geom)`) as a BLOB/text attribute with no geometry type to detect, so
    # the type-based pass below finds nothing — we then probe these and verify by result.
    _GEOMISH_NAMES = frozenset(
        {
            "geom",
            "geometry",
            "the_geom",
            "geom2",
            "shape",
            "wkb_geometry",
            "way",
            "wkb",
        }
    )
    _BLOBISH_TYPES = frozenset(
        {"text", "binary", "blob", "bytea", "bytearray", "string", ""}
    )

    def _respatialize_sql(self, connection, options, layer):
        """Turn an *aspatial* SQL result back into a geometry layer by naming its geometry
        column. Tries the column detected **by type** first (any name); if that finds nothing
        — as for a SpatiaLite computed geometry, which comes back as a BLOB/text attribute —
        probes geometry-named / BLOB-typed columns and accepts the first that actually yields
        a non-aspatial layer. Verification-by-result means a wrongly-guessed column is rejected.
        Returns the respatialized layer, or None if nothing worked."""
        candidates: list[str] = []
        typed = self._geometry_field_name(layer)
        if typed:
            candidates.append(typed)
        for f in layer.fields():
            nm = f.name()
            if nm in candidates:
                continue
            if (
                nm.lower() in self._GEOMISH_NAMES
                or (f.typeName() or "").lower() in self._BLOBISH_TYPES
            ):
                candidates.append(nm)
        for col in candidates[:8]:  # bound the probing; SQL results have few columns
            options.geometryColumn = col
            try:
                respatial = connection.createSqlVectorLayer(options)
            except Exception:  # noqa: BLE001 — a bad guess just isn't a geometry column
                continue
            if (
                respatial is not None
                and respatial.isValid()
                and not self._is_aspatial(respatial)
            ):
                return respatial
        return None

    # Field type names that mark a geometry column in a SQL result — both the generic
    # PostGIS/PostgreSQL names and the per-type names SpatiaLite reports (e.g. `point`).
    _GEOM_FIELD_TYPES = frozenset(
        {
            "geometry",
            "geography",
            "point",
            "linestring",
            "polygon",
            "multipoint",
            "multilinestring",
            "multipolygon",
            "geometrycollection",
            "curve",
            "multicurve",
            "surface",
            "multisurface",
            "circularstring",
            "compoundcurve",
            "curvepolygon",
            "polyhedralsurface",
            "tin",
            "triangle",
        }
    )

    @staticmethod
    def _geometry_field_name(layer):
        """The name of ``layer``'s first geometry-typed attribute (a column the SQL provider
        surfaced as an attribute rather than the geometry) — detected by **type**, never by
        name, so any column name works. Recognises both PostGIS's `geometry`/`geography` and
        SpatiaLite's per-type names (`point`, …), with a Qt user-type fallback."""
        try:
            from qgis.PyQt.QtCore import QMetaType

            user = int(QMetaType.Type.User)
        except Exception:  # noqa: BLE001 — Qt5 fallback
            from qgis.PyQt.QtCore import QVariant

            user = int(QVariant.UserType)
        for f in layer.fields():
            tn = (
                (f.typeName() or "").lower().rstrip("zm ")
            )  # drop a Z/M dimension suffix
            if tn in PyqgisBackend._GEOM_FIELD_TYPES or int(f.type()) == user:
                return f.name()
        return None

    def execute_sql(self, conn: str, query: str) -> None:
        # A non-SELECT statement (DDL/DML) run server-side. As with `run_sql`, the
        # connection name is logged but the query text is not (it stays in the
        # provider) — and no credentials are ever in scope.
        _md, connection = self._find_connection(conn)
        try:
            connection.executeSql(query)
        except Exception as exc:
            raise OpError(
                f"SQL statement against connection `{conn}` failed: {exc}",
                algorithm="sql",
                params={"connection": conn},
                backend="pyqgis",
            ) from exc
        return None

    def save_table(
        self,
        layer: Layer,
        conn: str,
        schema: str | None,
        table: str,
        *,
        mode: str = "create",
        lineage: list | None = None,
    ) -> Layer:
        from qgis.core import (
            QgsDataSourceUri,
            QgsVectorLayer,
            QgsVectorLayerExporter,
        )

        md, connection = self._find_connection(conn)
        provider = md.key()
        eff_schema = default_schema(provider, schema)

        exists = self._table_exists(connection, eff_schema, table)
        if mode == "create" and exists:
            where = f"{eff_schema}.{table}" if eff_schema else table
            raise OpError(
                f"table `{where}` already exists on connection `{conn}` — use "
                "mode=replace or mode=append",
                algorithm="save",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            )
        if mode == "replace" and exists:
            try:
                connection.dropVectorTable(eff_schema, table)
            except Exception as exc:
                raise OpError(
                    f"could not replace table `{table}` on connection `{conn}`: {exc}",
                    algorithm="save",
                    params={"connection": conn, "table": table},
                    backend="pyqgis",
                ) from exc

        # Append adds rows to an existing table — the exporter can only *create* one
        # (every "append"/"update" option still tries to CREATE and fails "table exists"),
        # so we open the target and add features. Appending to a missing table falls
        # through to create.
        if mode == "append" and exists:
            return self._append_to_table(
                layer, connection, eff_schema, table, provider, conn
            )

        # create / replace → export a fresh table.
        # Build the destination URI from the *live connection* so host/port/dbname and
        # credentials come from QGIS's store — never from the flow text.
        geom_col = "geom" if layer.ref.isSpatial() else ""
        uri = QgsDataSourceUri(connection.uri())
        uri.setDataSource(eff_schema, table, geom_col)

        res = QgsVectorLayerExporter.exportLayer(
            layer.ref,
            uri.uri(False),
            provider,
            layer.ref.crs(),
            False,
            {"overwrite": True},
        )
        # exportLayer returns (resultCode, message); Success == 0. Keep the URI and message
        # out of the error we raise — they can carry credentials.
        code = res[0] if isinstance(res, (tuple, list)) else res
        if int(code) != int(QgsVectorLayerExporter.NoError):
            raise OpError(
                f"could not write table `{table}` on connection `{conn}`",
                algorithm="save",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            )

        # Record lineage best-effort. PostgreSQL gets a table COMMENT; SpatiaLite has none,
        # so it gets rows in a `niva_lineage` table. Never fatal, never carries credentials.
        if lineage and provider == "postgres":
            ident = (
                self._quote_ident(table)
                if not eff_schema
                else f"{self._quote_ident(eff_schema)}.{self._quote_ident(table)}"
            )
            note = " | ".join(str(x) for x in lineage).replace("'", "''")
            try:
                connection.executeSql(f"COMMENT ON TABLE {ident} IS '{note}'")
            except Exception:
                pass
        elif lineage and provider == "spatialite":
            self._record_spatialite_lineage(connection, table, lineage)

        # Reload the written table as a live layer so the result stays pipeable.
        out = QgsVectorLayer(connection.tableUri(eff_schema, table), table, provider)
        return Layer(
            DB_TABLE,
            out if out.isValid() else uri.uri(False),
            facet="vector",
            name=table,
        )

    def _record_spatialite_lineage(self, connection, table, lineage) -> None:
        """Record lineage into a `niva_lineage` table in a SpatiaLite DB (SpatiaLite has no
        COMMENT ON TABLE). The table is **aspatial** — it never touches `geometry_columns`,
        `spatial_ref_sys`, or the spatial index, so it can't break the DB's spatial state —
        idempotent (`CREATE TABLE IF NOT EXISTS`), and **best-effort**: any error is swallowed
        so a failed provenance write never fails the save. It's hidden from `show` (see
        `_SPATIALITE_SYSTEM_TABLES`) but stays queryable with `sql @conn "SELECT … "`. One row
        per lineage step, with the niva version stamped as its own first row.

        Written through Python's ``sqlite3`` with **bound parameters** (``?``) rather than the
        QGIS connection's string-only ``executeSql`` — no query is built from data, so there is
        no SQL-injection surface (a table name with a quote can't break out)."""
        from .. import __version__

        try:
            from qgis.core import QgsDataSourceUri

            path = QgsDataSourceUri(connection.uri()).database()
            if not path:  # can't locate the SpatiaLite file — skip (best-effort)
                return
            import sqlite3

            rows = [f"niva {__version__}"] + [str(e) for e in lineage]
            db = sqlite3.connect(path)
            try:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS niva_lineage "
                    "(table_name TEXT, recorded_at TEXT, step TEXT)"
                )
                db.executemany(
                    "INSERT INTO niva_lineage (table_name, recorded_at, step) "
                    "VALUES (?, datetime('now'), ?)",
                    [(table, step) for step in rows],
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — provenance is best-effort; a save must never fail on it
            pass

    def _append_to_table(
        self,
        layer: Layer,
        connection,
        schema: str,
        table: str,
        provider: str,
        conn: str,
    ) -> Layer:
        """INSERT the source features into an existing DB table (`mode=append`). Maps
        attributes by field name (the exporter adds a `pk` column, so positions differ)
        and transforms geometry to the table's CRS if needed. No credentials in scope."""
        from qgis.core import (
            QgsCoordinateTransform,
            QgsCoordinateTransformContext,
            QgsFeature,
            QgsGeometry,
            QgsVectorLayer,
        )

        dest = QgsVectorLayer(connection.tableUri(schema, table), table, provider)
        if not dest.isValid():
            raise OpError(
                f"could not open table `{table}` on connection `{conn}` to append",
                algorithm="save",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            )
        src = layer.ref
        dfields = dest.fields()
        sidx = {f.name(): i for i, f in enumerate(src.fields())}
        # Don't carry the source's value into a single integer primary key — a GeoPackage
        # `fid` copied into the table's `fid` PK collides with existing rows (and a plain
        # PK with no DB default can't be left null). Mint fresh keys past the current max.
        pk = list(dest.primaryKeyAttributes())
        mint_idx = pk[0] if len(pk) == 1 and dfields[pk[0]].isNumeric() else None
        next_pk = None
        if mint_idx is not None:
            mx = dest.maximumValue(mint_idx)
            next_pk = (int(mx) + 1) if mx is not None else 1
        xform = None
        if src.crs() != dest.crs() and src.crs().isValid() and dest.crs().isValid():
            xform = QgsCoordinateTransform(
                src.crs(), dest.crs(), QgsCoordinateTransformContext()
            )
        rows = []
        for sf in src.getFeatures():
            nf = QgsFeature(dfields)
            geom = sf.geometry()
            if xform is not None and not geom.isEmpty():
                geom = QgsGeometry(geom)
                geom.transform(xform)
            nf.setGeometry(geom)
            for di in range(len(dfields)):
                if di == mint_idx:
                    nf.setAttribute(di, next_pk)
                    next_pk += 1
                    continue
                si = sidx.get(dfields[di].name())
                if si is not None:
                    nf.setAttribute(di, sf.attribute(si))
            rows.append(nf)
        res = dest.dataProvider().addFeatures(rows)
        ok = res[0] if isinstance(res, (tuple, list)) else res
        if not ok:
            raise OpError(
                f"could not append to table `{table}` on connection `{conn}`",
                algorithm="save",
                params={"connection": conn, "table": table},
                backend="pyqgis",
            )
        return Layer(DB_TABLE, dest, facet="vector", name=table)

    @staticmethod
    def _quote_ident(name: str) -> str:
        """Quote a SQL identifier (schema/table) for safe interpolation — double-quote it
        and double any embedded quotes — so a name with odd characters can't break or
        inject into a statement we build (e.g. the lineage ``COMMENT ON TABLE``)."""
        return '"' + name.replace('"', '""') + '"'

    @staticmethod
    def _table_exists(connection, schema: str, table: str) -> bool:
        """True if ``table`` exists in ``schema`` on ``connection``. Best-effort: a
        provider that can't enumerate tables is treated as 'unknown' → not existing,
        so `create` falls through to the export (which will still fail loudly)."""
        try:
            return any(t.tableName() == table for t in connection.tables(schema))
        except Exception:
            return False

    # --- project file repointing (the `project` verb, roadmap §project) ----------

    def repoint_project(
        self,
        src: str,
        dest: str,
        *,
        target,
        missing: str,
        rasters: str | None = None,
        paths: str | None = None,
        bookmark: str | None = None,
        progress=None,
    ) -> None:
        # Use a STANDALONE QgsProject (never QgsProject.instance()) so this is safe on
        # the flow's worker thread — see plugin/flowtask.py and 15-§3.
        from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

        proj = QgsProject()
        if not proj.read(src):
            raise OpError(
                f"could not read project `{src}`",
                algorithm="project",
                params={"src": src},
                backend="pyqgis",
            )
        # target=None → copy/convert without repointing vectors (still does rasters/paths).
        # A {name: uri} dict is the `project from-template` slot map: every layer slot —
        # vector OR raster — is repointed from the one map by name (no separate rasters=).
        template_mode = isinstance(target, dict)
        resolve, available = self._repoint_target(target) if target else (None, set())
        counts = {"repointed": 0, "kept": 0, "dropped": 0}

        def emit(msg):
            if progress:
                progress(msg)

        def unmatched(lyr, name):
            """Apply the `missing` policy to a layer not found in its target."""
            if missing == "fail":
                raise OpError(
                    f"layer `{lyr.name()}` (source `{name}`) is not in the repoint target "
                    "— use missing=keep or missing=drop to override",
                    algorithm="project",
                    params={"src": src},
                    backend="pyqgis",
                )
            if missing == "drop":
                label = lyr.name()  # read before removeMapLayer deletes the object
                proj.removeMapLayer(lyr.id())
                counts["dropped"] += 1
                emit(f"   dropped `{label}` (not in target)")
            else:  # keep
                counts["kept"] += 1
                emit(f"   kept `{lyr.name()}` unchanged (not in target)")

        def slot_name(lyr):
            """The name to match against the target. In *template mode* a slot's identity
            is its **display name** (what the template author labelled it in the layer
            panel), so prefer that when it's in the data map; otherwise fall back to the old
            datasource's name (the plain-repoint rule: `|layername=` or file stem)."""
            if template_mode:
                dn = lyr.name()
                if dn in available:
                    return dn
            return self._layer_source_name(lyr)

        for lyr in list(proj.mapLayers().values()):
            if isinstance(lyr, QgsRasterLayer):
                # Template mode: match the raster slot against the data map by name (its
                # display name, else |layername=/file stem), same as the vector slots.
                if template_mode:
                    name = slot_name(lyr)
                    if name in available:
                        new_uri, _ = resolve(name)
                        lyr.setDataSource(new_uri.split("|", 1)[0], lyr.name(), "gdal")
                        counts["repointed"] += 1
                        emit(f"   repointed raster `{lyr.name()}` → {name}")
                    else:
                        unmatched(lyr, name)
                    continue
                # Otherwise rasters are separate files, not inside the vector container/DB.
                # Repoint them into the `rasters=` directory by basename; else leave them.
                if rasters is None:
                    counts["kept"] += 1
                    emit(
                        f"   ⚠ left raster `{lyr.name()}` unchanged (no rasters= target)"
                    )
                    continue
                base = os.path.basename(lyr.source().split("|", 1)[0])
                cand = os.path.join(rasters, base)
                if os.path.isfile(cand):
                    lyr.setDataSource(cand, lyr.name(), "gdal")
                    counts["repointed"] += 1
                    emit(f"   repointed raster `{lyr.name()}` → {base}")
                else:
                    unmatched(lyr, base)
                continue
            if not isinstance(lyr, QgsVectorLayer):
                counts["kept"] += 1
                emit(
                    f"   ⚠ left `{lyr.name()}` unchanged (not a vector or raster layer)"
                )
                continue
            if resolve is None:  # no repoint target — leave vector layers as they are
                counts["kept"] += 1
                continue
            name = slot_name(lyr)
            if name not in available:
                unmatched(lyr, name)
                continue
            new_uri, provider = resolve(name)
            subset = lyr.subsetString()
            lyr.setDataSource(new_uri, lyr.name(), provider)
            if subset:
                lyr.setSubsetString(subset)
            counts["repointed"] += 1
            emit(f"   repointed `{lyr.name()}` → {name}")

        if bookmark:
            self._add_bookmark(proj, bookmark)
            emit(f"   bookmark `{bookmark}` → project extent")
        if paths in ("relative", "absolute"):
            from qgis.core import Qgis

            proj.setFilePathStorage(
                Qgis.FilePathType.Relative
                if paths == "relative"
                else Qgis.FilePathType.Absolute
            )
            emit(f"   datasource paths → {paths}")
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if not proj.write(dest):  # output format (.qgs/.qgz) follows dest's extension
            raise OpError(
                f"could not write project `{dest}`",
                algorithm="project",
                params={"dest": dest},
                backend="pyqgis",
            )
        emit(
            f"   project written → {dest} ({counts['repointed']} repointed, "
            f"{counts['kept']} kept, {counts['dropped']} dropped)"
        )

    def create_project(
        self,
        layers: list,
        dest: str,
        *,
        crs: str | None = None,
        title: str | None = None,
        progress=None,
    ) -> None:
        # Standalone QgsProject (never the GUI singleton) — safe on the worker thread.
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        proj = QgsProject()
        added = 0
        for uri in layers:
            try:
                lyr = self.load(uri)  # reuse load's vector/raster detection
            except OpError as exc:
                if progress:
                    progress(f"   ⚠ skipped `{uri}`: {exc}")
                continue
            name = self._layer_source_name(lyr.ref)  # |layername= or file stem
            lyr.ref.setName(name)
            proj.addMapLayer(lyr.ref)  # the project takes ownership
            added += 1
            if progress:
                progress(f"   added `{name}`")
        if added == 0:
            raise OpError(
                "`project new`: none of the sources could be loaded",
                algorithm="project",
                params={"dest": dest},
                backend="pyqgis",
            )
        if crs:
            ref = QgsCoordinateReferenceSystem(str(crs))
            if ref.isValid():
                proj.setCrs(ref)
        if title:
            proj.setTitle(str(title))
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if not proj.write(dest):
            raise OpError(
                f"could not write project `{dest}`",
                algorithm="project",
                params={"dest": dest},
                backend="pyqgis",
            )
        if progress:
            progress(f"   created project → {dest} ({added} layer(s))")

    def read_project(self, src: str) -> dict:
        from qgis.core import QgsProject, QgsVectorLayer

        proj = QgsProject()
        if not proj.read(src):
            raise OpError(
                f"could not read project `{src}`",
                algorithm="project",
                params={"src": src},
                backend="pyqgis",
            )
        layers = []
        for lyr in proj.mapLayers().values():
            layers.append(
                {
                    "name": lyr.name(),
                    "source": lyr.source(),
                    "provider": lyr.providerType() or "",
                    "type": "vector" if isinstance(lyr, QgsVectorLayer) else "raster",
                    "crs": lyr.crs().authid(),
                    "valid": lyr.isValid(),
                }
            )
        layers.sort(key=lambda d: d["name"])
        return {"title": proj.title(), "crs": proj.crs().authid(), "layers": layers}

    def environment_report(self) -> str:
        from ..environment import report_markdown

        return report_markdown()

    def algorithm_catalog(self) -> list:
        ensure_qgis()
        return algorithm_catalog()

    # --- `show`: list datasets at a location ---------------------------------

    def list_layers(self, source: str) -> list:
        """List the layers inside a file/container via the provider registry's
        ``querySublayers`` — one pass handles GeoPackage (vector + raster), SpatiaLite,
        shapefiles, GeoTIFFs, etc. Vectors carry a **feature count** and rasters their
        **cell dimensions**, so an empty or oversized dataset is obvious at a glance
        (issue #21); both are best-effort and never break the listing."""
        from osgeo import gdal
        from qgis.core import Qgis, QgsProviderRegistry, QgsWkbTypes

        # A directory scan probes every file; silence GDAL's "not recognized" chatter on the
        # ones it can't read (the failed probe just yields no layers).
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            details = QgsProviderRegistry.instance().querySublayers(source)
        finally:
            gdal.PopErrorHandler()
        rows = []
        for d in details:
            try:
                if d.type() == Qgis.LayerType.Vector:
                    geom = QgsWkbTypes.displayString(d.wkbType()) or "Unknown"
                    # An attribute-only layer (NoGeometry) is a *table*, not a vector layer.
                    if geom == "NoGeometry":
                        kind, typ = "table", "(aspatial)"
                    else:
                        kind, typ = (
                            "vector",
                            self._vector_summary(d.uri(), d.providerKey(), geom),
                        )
                else:
                    kind, typ = "raster", self._raster_summary(d.uri(), d.providerKey())
                rows.append(
                    {
                        "name": d.name(),
                        "kind": kind,
                        "type": typ,
                        "format": d.driverName() or d.providerKey() or "",
                        "ref": d.uri(),
                    }
                )
            except Exception:  # noqa: BLE001 — one bad sublayer must not break the listing
                continue
        return rows

    def _vector_summary(self, uri: str, provider: str, geom: str) -> str:
        """`<geom> · <n> feature(s)` for a vector sublayer; best effort (issue #21).
        Surfaces empty (0) and huge layers; falls back to just the geometry type if the
        layer can't be opened or the provider won't count."""
        try:
            from qgis.core import QgsVectorLayer

            vl = QgsVectorLayer(uri, "v", provider or "ogr")
            if not vl.isValid():
                return geom
            n = vl.featureCount()
            if n < 0:  # provider couldn't count without a full scan — don't force one
                return geom
            return f"{geom} · {n:,} feature" + ("s" if n != 1 else "")
        except Exception:  # noqa: BLE001
            return geom

    def _raster_summary(self, uri: str, provider: str) -> str:
        """`<n> band(s) · <W>×<H> · <dtype>` for a raster sublayer; best effort. The
        `<W>×<H>` cell dimensions (issue #21) make an oversized grid obvious."""
        try:
            from qgis.core import Qgis, QgsRasterLayer

            rl = QgsRasterLayer(uri, "r", provider or "gdal")
            if not rl.isValid():
                return "raster"
            n = rl.bandCount()
            dtype = ""
            if n:
                try:
                    dtype = Qgis.DataType(rl.dataProvider().dataType(1)).name
                except Exception:  # noqa: BLE001
                    dtype = ""
            parts = [f"{n} band" + ("s" if n != 1 else "")]
            w, h = rl.width(), rl.height()
            if w > 0 and h > 0:
                parts.append(f"{w:,}×{h:,}")
            if dtype:
                parts.append(dtype)
            return " · ".join(parts)
        except Exception:  # noqa: BLE001
            return "raster"

    def list_tables(
        self, conn: str, schema: str | None = None, table: str | None = None, warn=None
    ) -> list:
        """List a connection's tables via the QGIS connection API. SpatiaLite has no
        schemas (``schemas()`` raises) → a single unnamed schema; PostGIS iterates
        schemas (or just the one requested). Geometry type from the table's first
        geometry column; aspatial tables show as `table`, raster tables as `raster`.

        ``warn`` is an optional callable(str) for surfacing per-schema errors (e.g.
        network failures or auth problems) that would otherwise be silently skipped.
        The engine passes ``self._emit`` so errors appear in the plugin output panel."""
        from qgis.core import QgsAbstractDatabaseProviderConnection as DbConn
        from qgis.core import QgsWkbTypes

        md, connection = self._find_connection(conn)
        provider = md.key()
        if schema:
            schemas = [schema]
        else:
            try:
                schemas = list(connection.schemas()) or [None]
            except Exception as exc:  # noqa: BLE001 — provider has no schema concept (SpatiaLite)
                # Surface the error if a warn callback is provided: a connection error here
                # (e.g. auth failure, host unreachable) is indistinguishable from a provider
                # that simply has no schema API, so we report it and fall back to [None].
                if warn and str(exc):
                    warn(f"  show @{conn}: schemas() — {exc}")
                schemas = [None]

        rows = []
        for sch in schemas:
            try:
                props = connection.tables(sch or "")
            except Exception as exc:  # noqa: BLE001
                # Surface per-schema failures (auth, network, permissions) so the user
                # sees a meaningful message instead of a silent empty listing.
                if warn:
                    warn(
                        f"  show @{conn}{('.' + sch) if sch else ''}: tables() — {exc}"
                    )
                continue
            for t in props:
                name = t.tableName()
                if table is not None and name != table:
                    continue
                # Skip SpatiaLite's internal metadata/virtual tables (older QGIS lists some as
                # ordinary spatial tables); they aren't loadable user layers. See the note on
                # _SPATIALITE_SYSTEM_TABLES.
                if provider == "spatialite" and _is_spatialite_system_table(name):
                    continue
                gtypes = t.geometryColumnTypes()
                flags = int(t.flags())
                if gtypes:
                    kind, typ = "vector", QgsWkbTypes.displayString(gtypes[0].wkbType)
                elif flags & int(DbConn.TableFlag.Raster):
                    kind, typ = "raster", "raster"
                else:
                    kind, typ = "table", "(aspatial)"
                ref = f"@{conn}." + (f"{sch}.{name}" if sch else name)
                rows.append(
                    {
                        "name": name,
                        "kind": kind,
                        "type": typ,
                        "format": provider,
                        "ref": ref,
                    }
                )
        rows.sort(key=lambda r: r.get("name") or "")
        return rows

    def list_service(self, url: str) -> list:
        """Remote OWS listing — delegated to the QGIS-free ``niva.remote`` (stdlib HTTP+XML)."""
        from ..remote import list_service

        return list_service(url)

    def _add_bookmark(self, proj, spec: dict) -> None:
        """Add a spatial bookmark to ``proj`` in the project CRS. ``spec`` is
        ``{name, at: (x,y)|None, width: float|None}``: a centre+width makes a square extent
        there; otherwise the bookmark covers the union of the project's layer extents (a
        'study area' jump-to for compiled outputs)."""
        from qgis.core import QgsBookmark, QgsRectangle, QgsReferencedRectangle

        pcrs = proj.crs()
        at, width = spec.get("at"), spec.get("width")
        if at is not None and width is not None:
            cx, cy = at
            half = width / 2.0
            extent = QgsRectangle(cx - half, cy - half, cx + half, cy + half)
        else:
            extent = self._union_extent(proj, pcrs)
        bm = QgsBookmark()
        bm.setName(spec["name"])
        bm.setExtent(QgsReferencedRectangle(extent, pcrs))
        proj.bookmarkManager().addBookmark(bm)

    @staticmethod
    def _union_extent(proj, pcrs):
        from qgis.core import (
            QgsCoordinateTransform,
            QgsCoordinateTransformContext,
            QgsRectangle,
        )

        extent = None
        for lyr in proj.mapLayers().values():
            le = lyr.extent()
            if le.isNull() or le.isEmpty():
                continue
            if lyr.crs() != pcrs and lyr.crs().isValid() and pcrs.isValid():
                try:
                    le = QgsCoordinateTransform(
                        lyr.crs(), pcrs, QgsCoordinateTransformContext()
                    ).transformBoundingBox(le)
                except Exception:
                    continue
            if extent is None:
                extent = QgsRectangle(le)
            else:
                extent.combineExtentWith(le)
        return extent if extent is not None else QgsRectangle()

    def _repoint_target(self, target):
        """Resolve a repoint ``target`` into ``(resolve, available)``: ``resolve(name)``
        returns ``(new_uri, provider)`` for a layer named ``name``, and ``available`` is
        the set of names the target holds. Kinds: a ``{name: uri}`` dict (the
        `project from-template` slot map); a GeoPackage path; or an ``@conn[.schema]``
        database connection."""
        if isinstance(target, dict):
            available = set(target)

            def resolve(name):
                # The vector default provider; the raster branch overrides to gdal.
                return target[name], "ogr"

            return resolve, available

        if is_connection_ref(target):
            conn, schema, table = parse_connection_ref(target, self.connection_names())
            if schema is not None:  # @conn.schema.table — names a table, not a target
                raise OpError(
                    f"`project` repoint target `{target}` names a table — use "
                    "`@conn` or `@conn.<schema>`",
                    algorithm="project",
                    params={},
                    backend="pyqgis",
                )
            md, connection = self._find_connection(conn)
            sch = default_schema(md.key(), table)
            try:
                available = {t.tableName() for t in connection.tables(sch)}
            except Exception:
                available = set()
            provider = md.key()

            def resolve(name):
                return connection.tableUri(sch, name), provider

            return resolve, available

        # GeoPackage / file container target. Query ALL layer names (unlike
        # ``sublayers``, which returns [] for a single-layer container).
        from qgis.core import QgsProviderRegistry

        try:
            details = QgsProviderRegistry.instance().querySublayers(target)
            available = {d.name() for d in details if d.name()}
        except Exception:
            available = set()

        def resolve(name):
            return f"{target}|layername={name}", "ogr"

        return resolve, available

    @staticmethod
    def _layer_source_name(layer) -> str:
        """The name to match against the repoint target: the old datasource's
        ``|layername=`` if present, else the source file's stem."""
        src = layer.source()
        if "layername=" in src:
            return src.split("layername=", 1)[1].split("|", 1)[0]
        path = src.split("|", 1)[0]
        return os.path.splitext(os.path.basename(path))[0]

    # --- layer styles / metadata (the `style` verb) ------------------------------

    def style_layer(self, layer: Layer, action: str, path: str) -> None:
        ml = layer.ref
        if isinstance(ml, str):
            # After `save`, the handle's ref is a path on disk, not a live layer — load it
            # so `style apply|save` can chain after `save` (the documented pattern
            # `… | save out.gpkg | style apply x.qml`).
            from qgis.core import QgsVectorLayer

            loaded = QgsVectorLayer(ml, layer.name or "layer", "ogr")
            if not loaded.isValid():
                raise OpError(
                    f"could not open `{ml}` to style it",
                    algorithm="style",
                    params={"path": path},
                    backend="pyqgis",
                )
            ml = loaded
        ext = os.path.splitext(path)[1].lower()
        if action == "save":
            return self._save_style(ml, path, ext)
        # apply (the engine restricts this to .qml/.qmd): load into the layer, then
        # persist so QGIS picks it up next time.
        is_meta = ext == ".qmd"
        res = ml.loadNamedMetadata(path) if is_meta else ml.loadNamedStyle(path)
        ok = res[1] if isinstance(res, tuple) else bool(res)
        msg = res[0] if isinstance(res, tuple) else ""
        if not ok:
            kind = "metadata" if is_meta else "style"
            raise OpError(
                f"could not apply {kind} `{path}`" + (f": {msg}" if msg else ""),
                algorithm="style",
                params={"path": path},
                backend="pyqgis",
            )
        self._persist_style(ml, is_meta)
        return None

    # --- figure: render a simple map image (vector + raster + labels) --------

    def render_figure(
        self,
        layer: Layer,
        dest: str,
        *,
        size=None,
        dpi: int = 96,
        extent=None,
        layers: list | None = None,
        basemap: str | None = None,
        bg: str | None = None,
        labels: str | None = None,
        progress=None,
    ) -> None:
        from qgis.core import (
            QgsMapRendererParallelJob,
            QgsMapSettings,
            QgsProject,
            QgsRasterLayer,
        )
        from qgis.PyQt.QtCore import QEventLoop, QSize
        from qgis.PyQt.QtGui import QColor

        stack, primary, dest_crs = self._build_stack(
            layer, layers, basemap, labels, progress
        )
        rect = self._resolve_extent(extent, stack, dest_crs)

        # Sensible default so the simplest `figure out.png` shows something useful: give
        # single-band rasters a min/max stretch over the visible extent (a flat DTM/DSM
        # otherwise renders washed-out).
        for ml in stack:
            if isinstance(ml, QgsRasterLayer):
                self._default_raster_stretch(ml, rect)

        # Size: explicit (w,h), else derive height from the extent aspect at a 1200 px width.
        if size:
            w, h = int(size[0]), int(size[1])
        else:
            w = 1200
            ar = (rect.height() / rect.width()) if rect.width() else 0.75
            h = max(1, min(8000, int(round(w * ar))))

        ms = QgsMapSettings()
        ms.setLayers(stack)
        ms.setDestinationCrs(dest_crs)
        ms.setExtent(rect)
        ms.setOutputSize(QSize(w, h))
        ms.setOutputDpi(dpi)
        ms.setFlag(QgsMapSettings.Flag.DrawLabeling, True)  # honour any layer's labels
        ms.setFlag(
            QgsMapSettings.Flag.Antialiasing, True
        )  # smooth lines/text by default
        ms.setFlag(QgsMapSettings.Flag.UseAdvancedEffects, True)
        ms.setBackgroundColor(QColor(bg) if bg else QColor(255, 255, 255))
        ms.setTransformContext(QgsProject.instance().transformContext())

        if progress:
            progress(
                f"   rendering {w}×{h} figure, {len(stack)} layer(s) "
                "(large point/vector layers can take a while)…"
            )
        job = QgsMapRendererParallelJob(ms)
        loop = QEventLoop()
        job.finished.connect(loop.quit)
        stop_beat = self._heartbeat(progress, "rendering")
        job.start()
        loop.exec()
        stop_beat()
        img = job.renderedImage()
        os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
        if not img.save(dest):
            raise OpError(
                f"could not write figure to `{dest}` (unsupported format? use .png/.jpg)",
                algorithm="figure",
                params={"dest": dest},
                backend="pyqgis",
            )

    def _build_stack(self, layer, layers, basemap, labels, progress=None):
        """Resolve the draw stack shared by `figure` and `map`: [primary, *overlays,
        basemap], plus the destination CRS. ``layers`` draw beneath the piped layer;
        ``basemap`` at the bottom; ``labels`` enables single-field labeling on the primary."""
        from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer

        primary = self._as_map_layer(layer.ref, layer.name)
        stack = [primary]
        for src in layers or []:
            if progress:
                progress(f"   loading overlay {os.path.basename(str(src))}…")
            stack.append(self._as_map_layer(os.path.expanduser(str(src)), None))
        if basemap:
            bm = self._basemap_layer(basemap)
            if bm is not None:
                stack.append(bm)
        if labels and isinstance(primary, QgsVectorLayer):
            self._enable_simple_labels(primary, labels)
        dest_crs = (
            primary.crs()
            if primary.crs().isValid()
            else QgsCoordinateReferenceSystem("EPSG:3857")
        )
        return stack, primary, dest_crs

    @staticmethod
    def _heartbeat(progress, label):
        """Start a periodic '… still <label> (Ns)' tick during a long async render;
        returns a ``stop()`` callable. No-op without a progress sink. The tick fires from
        the QEventLoop that drives the parallel render job, so a multi-minute render never
        looks frozen."""
        if not progress:
            return lambda: None
        from qgis.PyQt.QtCore import QTimer

        state = {"s": 0}
        timer = QTimer()

        def beat():
            state["s"] += 3
            progress(f"   … still {label} ({state['s']}s)")

        timer.timeout.connect(beat)
        timer.start(3000)
        return timer.stop  # keeps the timer alive until called

    # --- map: a composed cartographic layout (title/legend/scalebar/north) ----

    def render_map(
        self,
        layer: Layer,
        dest: str,
        *,
        title: str | None = None,
        legend: bool = False,
        scalebar: bool = False,
        northarrow: bool = False,
        page: str = "A4",
        orientation: str = "landscape",
        dpi: int = 300,
        extent=None,
        layers: list | None = None,
        basemap: str | None = None,
        labels: str | None = None,
        from_project: str | None = None,
        layout: str | None = None,
        progress=None,
    ) -> None:
        # Mode 1: export an existing QGIS project layout (full fidelity, atlases included).
        if from_project:
            return self._export_project_layout(
                from_project, layout, dest, dpi=dpi, progress=progress
            )
        # Mode 2: compose an ad-hoc layout from the piped layer(s).
        from qgis.core import (
            QgsLayout,
            QgsLayoutItemLabel,
            QgsLayoutItemLegend,
            QgsLayoutItemMap,
            QgsLayoutItemScaleBar,
            QgsLayoutPoint,
            QgsLayoutSize,
            QgsProject,
            QgsRasterLayer,
            QgsUnitTypes,
        )
        from qgis.PyQt.QtGui import QFont

        stack, primary, dest_crs = self._build_stack(
            layer, layers, basemap, labels, progress
        )
        rect = self._resolve_extent(extent, stack, dest_crs)
        for ml in stack:
            if isinstance(ml, QgsRasterLayer):
                self._default_raster_stretch(ml, rect)
        if progress:
            progress(
                f"   composing {page} {orientation} map, {len(stack)} layer(s) "
                "(large datasets can take a while)…"
            )

        # Page geometry in mm. Landscape swaps width/height.
        pw, ph = self._page_mm(page)
        if orientation.lower().startswith("land"):
            pw, ph = max(pw, ph), min(pw, ph)
        else:
            pw, ph = min(pw, ph), max(pw, ph)

        # The stack must live in a project's layer tree for the LEGEND to populate (a map
        # item's setLayers() alone leaves the legend empty). Adding a layer to a project
        # transfers OWNERSHIP, and this binding exposes no `takeOwnership` flag — so add
        # CLONES, never the originals: the isolated project owns/deletes the clones, while
        # the engine's live piped layer is untouched. Clones carry the style, labeling, and
        # raster stretch applied above. An ISOLATED project (never QgsProject.instance(),
        # which in the plugin is the user's live project) also keeps the render self-contained.
        render_stack = [ml.clone() for ml in stack]
        proj = QgsProject()
        proj.addMapLayers(
            render_stack, True
        )  # addToLegend=True → legend auto-populates
        proj.setCrs(dest_crs)
        lay = QgsLayout(proj)
        lay.initializeDefaults()
        lay.pageCollection().pages()[0].setPageSize(
            QgsLayoutSize(pw, ph, QgsUnitTypes.LayoutMillimeters)
        )

        margin = 8.0
        top = margin + (10.0 if title else 0.0)
        legend_w = 55.0 if legend else 0.0
        map_x, map_y = margin, top
        map_w = pw - 2 * margin - (legend_w + 4 if legend else 0)
        map_h = ph - top - margin

        mi = QgsLayoutItemMap(lay)
        mi.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
        mi.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
        mi.setLayers(render_stack)
        mi.setCrs(dest_crs)
        mi.zoomToExtent(rect)
        mi.setBackgroundColor(self._q_white())
        lay.addLayoutItem(mi)

        if title:
            lbl = QgsLayoutItemLabel(lay)
            lbl.setText(title)
            f = QFont()
            f.setPointSize(18)
            f.setBold(True)
            lbl.setFont(f)
            lbl.attemptMove(QgsLayoutPoint(margin, 3, QgsUnitTypes.LayoutMillimeters))
            lbl.attemptResize(
                QgsLayoutSize(pw - 2 * margin, 10, QgsUnitTypes.LayoutMillimeters)
            )
            lay.addLayoutItem(lbl)

        if legend:
            lg = QgsLayoutItemLegend(lay)
            lg.setLinkedMap(mi)
            lg.setTitle("Legend")
            lg.attemptMove(
                QgsLayoutPoint(
                    pw - margin - legend_w, top, QgsUnitTypes.LayoutMillimeters
                )
            )
            lay.addLayoutItem(lg)

        if scalebar:
            sb = QgsLayoutItemScaleBar(lay)
            sb.setLinkedMap(mi)
            sb.applyDefaultSettings()
            sb.setStyle("Single Box")
            try:
                sb.setUnits(QgsUnitTypes.DistanceMeters)
            except Exception:  # noqa: BLE001 — QGIS picks a sensible default otherwise
                pass
            sb.attemptMove(
                QgsLayoutPoint(
                    map_x + 2, ph - margin - 12, QgsUnitTypes.LayoutMillimeters
                )
            )
            lay.addLayoutItem(sb)

        if northarrow:
            self._add_north_arrow(lay, mi, map_x + map_w - 18, map_y + 4)

        self._export_layout(lay, dest, dpi=dpi, progress=progress)

    def _export_project_layout(self, project_path, layout_name, dest, *, dpi, progress):
        from qgis.core import QgsProject

        path = os.path.expanduser(project_path)
        if not os.path.isfile(path):
            raise OpError(
                f"`map from=`: no project at `{path}`",
                algorithm="map",
                params={"from": project_path},
                backend="pyqgis",
            )
        proj = QgsProject()
        if not proj.read(path):
            raise OpError(
                f"could not open project `{path}`",
                algorithm="map",
                params={"from": project_path},
                backend="pyqgis",
            )
        manager = proj.layoutManager()
        layouts = manager.printLayouts()
        if not layouts:
            raise OpError(
                f"project `{os.path.basename(path)}` has no print layouts to export",
                algorithm="map",
                params={"from": project_path},
                backend="pyqgis",
            )
        if layout_name:
            lay = manager.layoutByName(layout_name)
            if lay is None:
                names = ", ".join(x.name() for x in layouts)
                raise OpError(
                    f"no layout named `{layout_name}` — available: {names}",
                    algorithm="map",
                    params={"layout": layout_name},
                    backend="pyqgis",
                )
        else:
            lay = layouts[0]
        if progress:
            progress(
                f"   exporting layout '{lay.name()}' from {os.path.basename(path)}"
            )
        self._export_layout(lay, dest, dpi=dpi, progress=None)

    def _export_layout(self, lay, dest, *, dpi, progress):
        from qgis.core import QgsLayoutExporter

        os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
        exporter = QgsLayoutExporter(lay)
        ext = os.path.splitext(dest)[1].lower()
        if progress:
            progress(f"   rendering map → {os.path.basename(dest)}")
        if ext == ".pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = dpi
            res = exporter.exportToPdf(dest, settings)
        elif ext == ".svg":
            settings = QgsLayoutExporter.SvgExportSettings()
            settings.dpi = dpi
            res = exporter.exportToSvg(dest, settings)
        elif ext in (".png", ".jpg", ".jpeg"):
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = dpi
            res = exporter.exportToImage(dest, settings)
        else:
            raise OpError(
                f"`map` writes .pdf/.png/.jpg/.svg — `{dest}` is not one",
                algorithm="map",
                params={"dest": dest},
                backend="pyqgis",
            )
        if res != QgsLayoutExporter.Success:
            raise OpError(
                f"could not export map to `{dest}` (result {res})",
                algorithm="map",
                params={"dest": dest},
                backend="pyqgis",
            )

    @staticmethod
    def _page_mm(page: str):
        sizes = {
            "A5": (148, 210),
            "A4": (210, 297),
            "A3": (297, 420),
            "LETTER": (216, 279),
            "LEGAL": (216, 356),
            "TABLOID": (279, 432),
        }
        key = str(page).strip().upper()
        if key in sizes:
            return sizes[key]
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*", str(page))
        if m:
            return (float(m.group(1)), float(m.group(2)))
        return sizes["A4"]

    @staticmethod
    def _q_white():
        from qgis.PyQt.QtGui import QColor

        return QColor(255, 255, 255)

    def _add_north_arrow(self, lay, linked_map, x, y):
        """Best-effort north arrow via a bundled QGIS SVG; skipped if none is found."""
        from qgis.core import (
            QgsApplication,
            QgsLayoutItemPicture,
            QgsLayoutPoint,
            QgsLayoutSize,
            QgsUnitTypes,
        )

        svg = None
        for base in QgsApplication.svgPaths():
            cand = os.path.join(base, "arrows", "NorthArrow_02.svg")
            if os.path.isfile(cand):
                svg = cand
                break
        if svg is None:
            return  # no north arrow available — skip rather than fail the map
        pic = QgsLayoutItemPicture(lay)
        pic.setPicturePath(svg)
        try:
            pic.setLinkedMap(linked_map)  # rotates with the map's rotation
        except Exception:  # noqa: BLE001
            pass
        pic.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        pic.attemptResize(QgsLayoutSize(14, 14, QgsUnitTypes.LayoutMillimeters))
        lay.addLayoutItem(pic)

    def _as_map_layer(self, ref, name):
        """Resolve a layer handle or source path to a live vector/raster QgsMapLayer."""
        from qgis.core import QgsMapLayer

        if isinstance(ref, QgsMapLayer):
            return ref
        loaded = self.load(
            str(ref)
        ).ref  # opens as vector or raster, else raises OpError
        return loaded

    def _basemap_layer(self, spec: str):
        """An XYZ tile basemap. ``osm`` is a shortcut; anything else is treated as an
        XYZ URL template (with ``{z}/{x}/{y}``)."""
        from qgis.core import QgsRasterLayer

        url = (
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            if spec.lower() in ("osm", "openstreetmap")
            else spec
        )
        uri = f"type=xyz&url={url}&zmax=19&zmin=0"
        bm = QgsRasterLayer(uri, "basemap", "wms")
        return bm if bm.isValid() else None

    def _resolve_extent(self, extent, stack, dest_crs):
        """Return a QgsRectangle in ``dest_crs``: an explicit bbox tuple, a borrowed
        layer's extent, or the union of every drawn layer's extent."""
        from qgis.core import QgsCoordinateTransform, QgsProject, QgsRectangle

        ctx = QgsProject.instance().transformContext()

        def to_dest(rect, crs):
            if crs.isValid() and crs != dest_crs:
                try:
                    return QgsCoordinateTransform(
                        crs, dest_crs, ctx
                    ).transformBoundingBox(rect)
                except Exception:  # noqa: BLE001 — unprojectable layer; use as-is
                    return rect
            return rect

        if isinstance(extent, (tuple, list)) and len(extent) == 4:
            return QgsRectangle(
                float(extent[0]), float(extent[1]), float(extent[2]), float(extent[3])
            )
        if isinstance(extent, str) and extent not in ("", "layer"):
            borrow = self._as_map_layer(os.path.expanduser(extent), None)
            return to_dest(borrow.extent(), borrow.crs())
        union = QgsRectangle()
        union.setMinimal()
        for ml in stack:
            e = ml.extent()
            if e.isNull() or e.isEmpty():
                continue
            union.combineExtentWith(to_dest(e, ml.crs()))
        if union.isNull() or union.width() == 0:
            union = stack[0].extent()
        union.scale(1.05)  # a small margin around the data
        return union

    def _default_raster_stretch(self, rl, rect):
        """Stretch a single-band-gray raster to its min/max over ``rect`` so a bare
        `figure` of a DEM/elevation raster reads well. Leaves RGB/paletted rasters alone."""
        from qgis.core import QgsContrastEnhancement, QgsSingleBandGrayRenderer

        try:
            if isinstance(rl.renderer(), QgsSingleBandGrayRenderer):
                rl.setContrastEnhancement(
                    QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum,
                    extent=rect,
                )
        except Exception:  # noqa: BLE001 — a nice-to-have; never fail the render over it
            pass

    def _enable_simple_labels(self, vlayer, field: str):
        """Turn on single-field labeling on a vector layer (a convenience for `figure`)."""
        from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling

        if field not in [f.name() for f in vlayer.fields()]:
            raise OpError(
                f"`figure labels={field}`: no field `{field}` in `{vlayer.name()}`",
                algorithm="figure",
                params={"labels": field},
                backend="pyqgis",
            )
        s = QgsPalLayerSettings()
        s.fieldName = field
        s.enabled = True
        vlayer.setLabeling(QgsVectorLayerSimpleLabeling(s))
        vlayer.setLabelsEnabled(True)

    def _save_style(self, ml, path: str, ext: str) -> None:
        """Export the layer's style/metadata: ``.qml`` (QGIS style), ``.qmd`` (metadata),
        ``.sld`` (OGC, for interop), or ``.qlr`` (a portable layer definition — datasource
        + style)."""
        if ext == ".qlr":
            from qgis.core import Qgis, QgsLayerDefinition, QgsLayerTreeLayer

            node = QgsLayerTreeLayer(ml)
            ok, err = QgsLayerDefinition.exportLayerDefinition(
                path, [node], Qgis.FilePathType.Absolute
            )
            if not ok:
                raise OpError(
                    f"could not export QLR to `{path}`" + (f": {err}" if err else ""),
                    algorithm="style",
                    params={"path": path},
                    backend="pyqgis",
                )
            return None
        if ext == ".sld":
            msg, ok = ml.saveSldStyle(path)
        elif ext == ".qmd":
            msg, ok = ml.saveNamedMetadata(path)
        else:  # .qml
            msg, ok = ml.saveNamedStyle(path)
        if not ok:
            raise OpError(
                f"could not save to `{path}`" + (f": {msg}" if msg else ""),
                algorithm="style",
                params={"path": path},
                backend="pyqgis",
            )
        return None

    def _persist_style(self, ml, is_meta: bool) -> None:
        """Persist an applied style/metadata so it sticks on disk: a GeoPackage vector
        layer's symbology goes into the container's style table (a re-loaded layer adopts
        it as default), everything else to a same-basename ``.qml``/``.qmd`` sidecar QGIS
        auto-loads. The layer must be file-backed (``save`` it first)."""
        src = ml.source().split("|", 1)[0]
        if not os.path.exists(src):
            raise OpError(
                "`style apply` needs a file-backed layer — save it first, e.g. "
                "`… | save out.gpkg | style apply house.qml`",
                algorithm="style",
                params={},
                backend="pyqgis",
            )
        ext = os.path.splitext(src)[1].lower()
        is_container = ext in (".gpkg", ".sqlite", ".db")
        if not is_meta and is_container and hasattr(ml, "saveStyleToDatabaseV2"):
            _result, err = ml.saveStyleToDatabaseV2("default", "", True, "")
            if err:
                raise OpError(
                    f"could not store style in `{os.path.basename(src)}`: {err}",
                    algorithm="style",
                    params={},
                    backend="pyqgis",
                )
            return None
        sidecar = os.path.splitext(src)[0] + (".qmd" if is_meta else ".qml")
        msg, ok = (
            ml.saveNamedMetadata(sidecar) if is_meta else ml.saveNamedStyle(sidecar)
        )
        if not ok:
            raise OpError(
                f"could not write sidecar `{sidecar}`" + (f": {msg}" if msg else ""),
                algorithm="style",
                params={},
                backend="pyqgis",
            )
        return None

    def valid_crs(self, text: str) -> bool:
        """True if QGIS recognises ``text`` as a CRS (EPSG/authid/WKT/PROJ). Rejects an unknown
        code like `EPSG:99999`, so reproject/warp fail closed instead of yielding an empty CRS."""
        from qgis.core import QgsCoordinateReferenceSystem

        return QgsCoordinateReferenceSystem(text).isValid()

    def crs_of(self, layer: Layer) -> CrsInfo:
        from qgis.core import Qgis, QgsUnitTypes

        crs = layer.ref.crs()
        authid = crs.authid() or "USER:0"
        if crs.isGeographic():
            return CrsInfo(authid, True, map_units="degrees")
        map_unit = crs.mapUnits()
        factor = QgsUnitTypes.fromUnitToUnitFactor(map_unit, Qgis.DistanceUnit.Meters)
        return CrsInfo(
            authid,
            False,
            units_to_meters=factor or 1.0,
            map_units=QgsUnitTypes.toString(map_unit),
        )

    def _facet(self, obj) -> str:
        from qgis.core import QgsRasterLayer

        return "raster" if isinstance(obj, QgsRasterLayer) else "vector"
