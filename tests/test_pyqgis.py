"""PyQGIS backend smoke tests (planning/05).

These need a working QGIS — they **skip cleanly** when ``qgis`` cannot be imported
or initialised, so the suite still runs green on a plain interpreter. To exercise
them, run under QGIS's own Python, e.g.::

    PYTHONPATH=/usr/share/qgis/python /usr/bin/python3 -m unittest discover -s tests
"""

import os
import tempfile
import unittest


def setUpModule():
    try:
        from niva.engine.pyqgis import ensure_qgis

        ensure_qgis()
    except Exception as exc:  # ImportError, or a QGIS init failure
        raise unittest.SkipTest(f"QGIS not available: {exc}")


def _write_points(path, crs, coords):
    """Create a tiny point layer in `crs` and save it to `path` via the backend."""
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

    from niva.engine.layer import MEMORY, Layer
    from niva.engine.pyqgis import PyqgisBackend

    vl = QgsVectorLayer(f"Point?crs={crs}&field=id:integer", "pts", "memory")
    pr = vl.dataProvider()
    for i, (x, y) in enumerate(coords):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([i])
        pr.addFeature(f)
    vl.updateExtents()
    PyqgisBackend().save(Layer(MEMORY, vl, facet="vector"), path)


class TestPyqgisBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_smoke_")
        self.src = os.path.join(self.tmp, "pts.gpkg")
        _write_points(self.src, "EPSG:3857", [(0, 0), (1000, 1000)])

    def _saved(self, path):
        from qgis.core import QgsVectorLayer

        layer = QgsVectorLayer(path, "out", "ogr")
        self.assertTrue(layer.isValid(), f"{path} did not load")
        return layer

    def test_load_buffer_save(self):
        import niva

        out = os.path.join(self.tmp, "out.gpkg")
        niva.flow(f"load {self.src} | buffer 100m | save {out}")
        from qgis.core import QgsWkbTypes

        layer = self._saved(out)
        self.assertEqual(layer.featureCount(), 2)
        self.assertIn("Polygon", QgsWkbTypes.displayString(layer.wkbType()))

    def test_buffer_dissolve_units(self):
        # Points are 1000 m apart; 1km buffers overlap, so dissolve → one feature.
        import niva

        out = os.path.join(self.tmp, "diss.gpkg")
        niva.flow(f"load {self.src} | buffer 1km dissolve | save {out}")
        self.assertEqual(self._saved(out).featureCount(), 1)

    def test_filter_then_save(self):
        import niva

        out = os.path.join(self.tmp, "filtered.gpkg")
        niva.flow(f'load {self.src} | filter "id = 1" | save {out}')
        self.assertEqual(self._saved(out).featureCount(), 1)

    def test_run_escape_hatch_real_algorithm(self):
        # `run` a native algorithm by id (not aliased), piped from the loaded layer.
        import niva

        out = os.path.join(self.tmp, "centroids.gpkg")
        niva.flow(f"load {self.src} | run native:centroids | save {out}")
        from qgis.core import QgsWkbTypes

        layer = self._saved(out)
        self.assertEqual(layer.featureCount(), 2)
        self.assertIn("Point", QgsWkbTypes.displayString(layer.wkbType()))

    def test_degrees_mismatch_is_flowerror(self):
        import niva
        from niva.errors import FlowError

        geo = os.path.join(self.tmp, "geo.gpkg")
        _write_points(geo, "EPSG:4326", [(0, 0), (0.01, 0.01)])
        out = os.path.join(self.tmp, "nope.gpkg")
        with self.assertRaises(FlowError):
            niva.flow(f"load {geo} | buffer 100m | save {out}")

    def test_bad_load_is_operror(self):
        import niva
        from niva.errors import OpError

        with self.assertRaises(OpError):
            niva.flow(f"load {self.tmp}/does_not_exist.gpkg | save {self.tmp}/x.gpkg")


if __name__ == "__main__":
    unittest.main()
