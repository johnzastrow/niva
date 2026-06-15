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

    def test_describe_real_algorithm(self):
        import niva

        out = niva.describe("native:buffer")
        self.assertIn("native:buffer", out)
        self.assertIn("DISTANCE", out)
        self.assertIn("parameters:", out)
        self.assertIn("outputs:", out)

    def test_assess_deep_real_layer(self):
        import niva

        report_path = os.path.join(self.tmp, "quality.md")
        niva.flow(f"load {self.src} | assess deep to {report_path}")
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("# Data quality assessment", report)
        self.assertIn("**Features:** 2", report)        # the fixture has 2 points
        self.assertIn("EPSG:3857", report)
        self.assertIn("| id |", report)                 # the fixture's field
        self.assertIn("## Quality checks", report)      # deep
        self.assertIn("**Invalid geometries:** 0", report)
        self.assertIn("**Duplicate geometries:** 0", report)

    def test_lineage_written_to_history(self):
        import niva

        out = os.path.join(self.tmp, "lineage.gpkg")
        niva.flow(f"load {self.src} | buffer 100m dissolve | save {out}")
        from qgis.core import QgsVectorLayer

        reloaded = QgsVectorLayer(f"{out}|layername=lineage", "l", "ogr")
        self.assertTrue(reloaded.isValid())
        history = reloaded.metadata().history()
        self.assertTrue(any("buffer 100m dissolve" in h for h in history), history)
        self.assertTrue(any(h.startswith("niva:") for h in history), history)

    def test_metadata_set_persists_to_file(self):
        import niva

        out = os.path.join(self.tmp, "meta.gpkg")
        niva.flow(
            f'load {self.src} | metadata set title="Cat homes" '
            f'abstract="Targets in Youngstown" keywords=cats,canvass | save {out}'
        )
        from qgis.core import QgsVectorLayer

        reloaded = QgsVectorLayer(f"{out}|layername=meta", "m", "ogr")
        self.assertTrue(reloaded.isValid())
        md = reloaded.metadata()
        self.assertEqual(md.title(), "Cat homes")
        self.assertEqual(md.abstract(), "Targets in Youngstown")
        self.assertEqual(md.keywords().get("keywords"), ["cats", "canvass"])

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


class TestPyqgisConnections(unittest.TestCase):
    """Real SpatiaLite connection: load @conn.table and sql @conn "…"."""

    CONN = "niva_smoke_sl"

    def setUp(self):
        from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                               QgsProviderRegistry, QgsVectorFileWriter, QgsVectorLayer)

        self.tmp = tempfile.mkdtemp(prefix="niva_sl_")
        self.db = os.path.join(self.tmp, "test.sqlite")
        vl = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer&field=name:string",
                            "t", "memory")
        pr = vl.dataProvider()
        for i, nm in [(1, "a"), (2, "b")]:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i, i)))
            f.setAttributes([i, nm])
            pr.addFeature(f)
        vl.updateExtents()
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "SpatiaLite"
        opts.layerName = "homes"
        QgsVectorFileWriter.writeAsVectorFormatV3(
            vl, self.db, QgsProject.instance().transformContext(), opts
        )
        self.md = QgsProviderRegistry.instance().providerMetadata("spatialite")
        connection = self.md.createConnection(f"dbname='{self.db}'", {})
        self.md.saveConnection(connection, self.CONN)

    def tearDown(self):
        try:
            self.md.deleteConnection(self.CONN)  # don't pollute the user's QGIS profile
        except Exception:
            pass

    def _saved(self, path):
        from qgis.core import QgsVectorLayer

        layer = QgsVectorLayer(path, "out", "ogr")
        self.assertTrue(layer.isValid(), f"{path} did not load")
        return layer

    def test_load_table_from_connection(self):
        import niva

        out = os.path.join(self.tmp, "tbl.gpkg")
        niva.flow(f"load @{self.CONN}.homes | save {out}")
        self.assertEqual(self._saved(out).featureCount(), 2)

    def test_sql_query_layer(self):
        import niva

        out = os.path.join(self.tmp, "q.gpkg")
        niva.flow(f'sql @{self.CONN} "SELECT * FROM homes WHERE id = 1" | save {out}')
        self.assertEqual(self._saved(out).featureCount(), 1)

    def test_unknown_connection_is_operror(self):
        import niva
        from niva.errors import OpError

        with self.assertRaises(OpError):
            niva.flow(f"load @no_such_conn_xyz.homes | save {self.tmp}/x.gpkg")


class TestFidCollisionSave(unittest.TestCase):
    """Saving a layer that carries an `fid` field to GeoPackage must not fail on the
    primary-key UNIQUE constraint — niva mints a fresh PK and keeps `fid` as data."""

    def test_save_layer_with_duplicate_fid(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

        from niva.engine.layer import MEMORY, Layer
        from niva.engine.pyqgis import PyqgisBackend

        tmp = tempfile.mkdtemp(prefix="niva_fid_")
        vl = QgsVectorLayer("Point?crs=EPSG:3857&field=fid:integer&field=name:string",
                            "t", "memory")
        pr = vl.dataProvider()
        for i in range(3):
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i, i)))
            f.setAttributes([1, "x"])  # duplicate fid=1 across all three
            pr.addFeature(f)
        vl.updateExtents()

        out = os.path.join(tmp, "fid.gpkg")
        PyqgisBackend().save(Layer(MEMORY, vl, facet="vector"), out)  # must not raise

        saved = QgsVectorLayer(f"{out}|layername=fid", "s", "ogr")
        self.assertTrue(saved.isValid())
        self.assertEqual(saved.featureCount(), 3)
        self.assertIn("fid", [f.name() for f in saved.fields()])  # source fid preserved


class TestMultiLayerLoad(unittest.TestCase):
    """A GeoPackage holds many layers — niva must not silently grab the first."""

    def setUp(self):
        from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY, QgsProject,
                               QgsVectorFileWriter, QgsVectorLayer)

        self.tmp = tempfile.mkdtemp(prefix="niva_multi_")
        self.gpkg = os.path.join(self.tmp, "multi.gpkg")
        action = QgsVectorFileWriter.ActionOnExistingFile

        def add(layername, on_existing):
            vl = QgsVectorLayer("Point?crs=EPSG:3857&field=id:integer", layername, "memory")
            pr = vl.dataProvider()
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
            f.setAttributes([1])
            pr.addFeature(f)
            vl.updateExtents()
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = layername
            opts.actionOnExistingFile = on_existing
            QgsVectorFileWriter.writeAsVectorFormatV3(
                vl, self.gpkg, QgsProject.instance().transformContext(), opts
            )

        add("roads", action.CreateOrOverwriteFile)
        add("rivers", action.CreateOrOverwriteLayer)

    def test_ambiguous_load_lists_the_layers(self):
        import niva
        from niva.errors import OpError

        with self.assertRaises(OpError) as ctx:
            niva.flow(f"load {self.gpkg} | save {self.tmp}/x.gpkg")
        msg = str(ctx.exception)
        self.assertIn("2 layers", msg)
        self.assertIn("roads", msg)
        self.assertIn("rivers", msg)
        self.assertIn("layername=", msg)

    def test_named_layer_loads(self):
        import niva
        from qgis.core import QgsVectorLayer

        out = os.path.join(self.tmp, "out.gpkg")
        niva.flow(f'load "{self.gpkg}|layername=rivers" | save {out}')
        self.assertTrue(QgsVectorLayer(f"{out}|layername=out", "o", "ogr").isValid())


if __name__ == "__main__":
    unittest.main()
