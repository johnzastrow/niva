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
from .layer import MEMORY, SOURCE, CrsInfo, Layer

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

    def save(self, layer: Layer, dest: str) -> Layer:
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
        options = QgsVectorFileWriter.SaveVectorOptions()
        driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(dest)[1])
        if driver:
            options.driverName = driver
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer.ref, dest, QgsProject.instance().transformContext(), options
        )
        if err[0] != 0:  # QgsVectorFileWriter.NoError == 0
            raise OpError(
                f"could not write `{dest}`: {err[1]}",
                algorithm="save", params={"dest": dest}, backend="pyqgis",
            )
        return Layer(SOURCE, dest, facet="vector", name=os.path.basename(dest))

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
