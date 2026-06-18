"""PyQGIS backend smoke tests (docs/planning/05).

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


def _write_raster(path):
    """Create a tiny 2x2 GeoTIFF at `path` (for project raster-repoint tests)."""
    from osgeo import gdal, osr

    ds = gdal.GetDriverByName("GTiff").Create(path, 2, 2, 1, gdal.GDT_Byte)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform([0, 1, 0, 0, 0, -1])
    ds.GetRasterBand(1).Fill(7)
    ds = None


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

    def _table_count(self, table):
        from qgis.core import QgsVectorLayer

        from niva.engine.pyqgis import PyqgisBackend

        _md, connection = PyqgisBackend()._find_connection(self.CONN)
        layer = QgsVectorLayer(connection.tableUri("", table), table, "spatialite")
        self.assertTrue(layer.isValid(), f"table {table} did not load")
        return layer.featureCount()

    def test_save_table_round_trip(self):
        import niva

        niva.flow(f"load @{self.CONN}.homes | save @{self.CONN}.homes_copy")
        self.assertEqual(self._table_count("homes_copy"), 2)

    def test_save_table_create_collision_errors(self):
        import niva
        from niva.errors import OpError

        with self.assertRaises(OpError):  # `homes` already exists, default mode=create
            niva.flow(f"load @{self.CONN}.homes | save @{self.CONN}.homes")

    def test_save_table_replace(self):
        import niva

        niva.flow(f"load @{self.CONN}.homes | save @{self.CONN}.r")
        niva.flow(f'sql @{self.CONN} "SELECT * FROM homes WHERE id = 1" '
                  f"| save @{self.CONN}.r mode=replace")
        self.assertEqual(self._table_count("r"), 1)

    def test_save_table_append(self):
        import niva

        niva.flow(f"load @{self.CONN}.homes | save @{self.CONN}.a")
        niva.flow(f"load @{self.CONN}.homes | save @{self.CONN}.a mode=append")
        self.assertEqual(self._table_count("a"), 4)

    def test_sql_execute_creates_table(self):
        import niva

        niva.flow(f'sql @{self.CONN} "CREATE TABLE made AS SELECT * FROM homes"')
        self.assertEqual(self._table_count("made"), 2)


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


@unittest.skipUnless(
    os.environ.get("NIVA_TEST_PG"),
    "set NIVA_TEST_PG='host=… port=… dbname=… user=… password=…' to run the PostGIS tier")
class TestPyqgisPostgres(unittest.TestCase):
    """Real PostGIS write/analyse — the postgres-specific paths SpatiaLite can't exercise
    (COMMENT lineage, schema-qualified writes), plus the create/replace/append modes
    against a server with a real primary key. Gated on NIVA_TEST_PG; skips otherwise."""

    CONN = "niva_test_pg_ci"

    def setUp(self):
        from qgis.core import QgsSettings

        params = dict(kv.split("=", 1) for kv in os.environ["NIVA_TEST_PG"].split())
        s = QgsSettings()
        base = f"PostgreSQL/connections/{self.CONN}"
        for key, pg in (("host", "host"), ("port", "port"), ("database", "dbname"),
                        ("username", "user"), ("password", "password")):
            s.setValue(f"{base}/{key}", params.get(pg, ""))
        s.setValue(f"{base}/saveUsername", "true")  # persist creds so the URI can connect
        s.setValue(f"{base}/savePassword", "true")  # headless (no interactive prompt)
        s.sync()
        self._sql_quiet("DROP TABLE IF EXISTS niva_t1, niva_t2")
        self._sql_quiet("DROP SCHEMA IF EXISTS niva_s CASCADE")
        self.tmp = tempfile.mkdtemp(prefix="niva_pg_")
        self.g = os.path.join(self.tmp, "homes.gpkg")
        _write_points(self.g, "EPSG:4326", [(1, 1), (2, 2)])  # gpkg layer `homes`

    def tearDown(self):
        from qgis.core import QgsProviderRegistry

        self._sql_quiet("DROP TABLE IF EXISTS niva_t1, niva_t2")
        self._sql_quiet("DROP SCHEMA IF EXISTS niva_s CASCADE")
        try:
            QgsProviderRegistry.instance().providerMetadata("postgres").deleteConnection(self.CONN)
        except Exception:
            pass

    def _sql_quiet(self, stmt):
        import niva

        try:
            niva.flow(f'sql @{self.CONN} "{stmt}"')
        except Exception:
            pass

    def _count(self, table, schema="public"):
        from qgis.core import QgsVectorLayer

        from niva.engine.pyqgis import PyqgisBackend

        _md, c = PyqgisBackend()._find_connection(self.CONN)
        return QgsVectorLayer(c.tableUri(schema, table), table, "postgres").featureCount()

    def test_save_round_trip(self):
        import niva

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        self.assertEqual(self._count("niva_t1"), 2)

    def test_create_collision_errors(self):
        import niva
        from niva.errors import OpError

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        with self.assertRaises(OpError):
            niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')

    def test_replace(self):
        import niva

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1 mode=replace')
        self.assertEqual(self._count("niva_t1"), 2)

    def test_append_mints_fresh_keys(self):
        # The postgres table's `fid` PK has no default; append must mint fresh keys, not
        # copy the source fid (which would collide). This failed before the fix.
        import niva

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1 mode=append')
        self.assertEqual(self._count("niva_t1"), 4)

    def test_schema_qualified_write(self):
        import niva

        niva.flow(f'sql @{self.CONN} "CREATE SCHEMA niva_s"')
        niva.flow(f'load "{self.g}" | save @{self.CONN}.niva_s.roads')
        self.assertEqual(self._count("roads", "niva_s"), 2)

    def test_sql_execute_creates_table(self):
        import niva

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        niva.flow(f'sql @{self.CONN} "CREATE TABLE niva_t2 AS SELECT * FROM niva_t1"')
        self.assertEqual(self._count("niva_t2"), 2)

    def test_lineage_written_to_table_comment(self):
        # The postgres-only path: `save @pg` records the flow's lineage as a COMMENT ON
        # TABLE. (SpatiaLite has no COMMENT, so this is only testable here.)
        import niva

        niva.flow(f'load "{self.g}" | save @{self.CONN}.public.niva_t1')
        layer = niva.flow(
            f"sql @{self.CONN} \"SELECT obj_description('public.niva_t1'::regclass) AS c\"")
        comment = next(layer.ref.getFeatures())["c"]
        self.assertTrue(comment and "load" in comment, f"no lineage comment: {comment!r}")


class TestPyqgisProject(unittest.TestCase):
    """`project` — copy a QGIS project and repoint layer datasources (real QgsProject)."""

    def setUp(self):
        import niva
        from qgis.core import QgsProject, QgsVectorLayer

        self.tmp = tempfile.mkdtemp(prefix="niva_prj_")
        # A per-theme gpkg with a layer named `roads` (the file stem).
        self.orig = os.path.join(self.tmp, "roads.gpkg")
        _write_points(self.orig, "EPSG:4326", [(1, 1), (2, 2)])
        # A consolidated gpkg that contains a layer named `roads`.
        self.consolidated = os.path.join(self.tmp, "basemap_clip.gpkg")
        niva.flow(f'load "{self.orig}" | save "{self.consolidated}" as roads')
        # A source project pointing at the original per-theme gpkg.
        proj = QgsProject()
        vl = QgsVectorLayer(f"{self.orig}|layername=roads", "Roads", "ogr")
        self.assertTrue(vl.isValid())
        proj.addMapLayer(vl)
        self.src = os.path.join(self.tmp, "p.qgs")
        self.assertTrue(proj.write(self.src))

    def _reload(self, path):
        from qgis.core import QgsProject

        self._p = QgsProject()  # keep a reference: a GC'd project deletes its layers
        self.assertTrue(self._p.read(path))
        return list(self._p.mapLayers().values())

    def test_repoint_to_gpkg(self):
        import niva

        out = os.path.join(self.tmp, "out.qgs")
        niva.flow(f'project "{self.src}" to="{out}" repoint="{self.consolidated}"')
        layers = self._reload(out)
        self.assertEqual(len(layers), 1)
        src = layers[0].source()
        self.assertIn("basemap_clip.gpkg", src)
        self.assertIn("layername=roads", src)
        self.assertTrue(layers[0].isValid())

    def test_qgz_output(self):
        import niva

        out = os.path.join(self.tmp, "out.qgz")
        niva.flow(f'project "{self.src}" to="{out}" repoint="{self.consolidated}"')
        self.assertTrue(os.path.isfile(out))
        self.assertIn("basemap_clip.gpkg", self._reload(out)[0].source())

    def test_missing_fails_by_default(self):
        import niva
        from niva.errors import OpError

        empty = os.path.join(self.tmp, "empty.gpkg")
        _write_points(empty, "EPSG:4326", [(9, 9)])  # holds layer `empty`, not `roads`
        with self.assertRaises(OpError):
            niva.flow(f'project "{self.src}" to="{self.tmp}/o2.qgs" repoint="{empty}"')

    def test_missing_drop_removes_unmatched_layer(self):
        import niva

        empty = os.path.join(self.tmp, "empty2.gpkg")
        _write_points(empty, "EPSG:4326", [(9, 9)])
        out = os.path.join(self.tmp, "o3.qgs")
        niva.flow(f'project "{self.src}" to="{out}" repoint="{empty}" missing=drop')
        self.assertEqual(len(self._reload(out)), 0)

    def test_missing_keep_leaves_layer(self):
        import niva

        empty = os.path.join(self.tmp, "empty3.gpkg")
        _write_points(empty, "EPSG:4326", [(9, 9)])
        out = os.path.join(self.tmp, "o4.qgs")
        niva.flow(f'project "{self.src}" to="{out}" repoint="{empty}" missing=keep')
        layers = self._reload(out)
        self.assertEqual(len(layers), 1)
        self.assertIn("roads.gpkg", layers[0].source())  # unchanged

    def _raster_project(self):
        """A project with one raster layer at <tmp>/rold/dem.tif, and a sibling <tmp>/rnew
        holding a same-named dem.tif. Returns (src_project_path, rnew_dir)."""
        from qgis.core import QgsProject, QgsRasterLayer

        old = os.path.join(self.tmp, "rold")
        new = os.path.join(self.tmp, "rnew")
        os.makedirs(old, exist_ok=True)
        os.makedirs(new, exist_ok=True)
        _write_raster(os.path.join(old, "dem.tif"))
        _write_raster(os.path.join(new, "dem.tif"))
        proj = QgsProject()
        proj.addMapLayer(QgsRasterLayer(os.path.join(old, "dem.tif"), "DEM"))
        rsrc = os.path.join(self.tmp, "rp.qgs")
        self.assertTrue(proj.write(rsrc))
        return rsrc, new

    def test_repoint_raster_to_dir(self):
        import niva

        rsrc, new = self._raster_project()
        out = os.path.join(self.tmp, "rout.qgs")
        niva.flow(f'project "{rsrc}" to="{out}" repoint="{self.consolidated}" '
                  f'rasters="{new}" missing=keep')
        layer = self._reload(out)[0]
        self.assertIn(os.path.join("rnew", "dem.tif"), layer.source())
        self.assertTrue(layer.isValid())

    def test_raster_left_unchanged_without_rasters_option(self):
        import niva

        rsrc, _new = self._raster_project()
        out = os.path.join(self.tmp, "rout2.qgs")
        niva.flow(f'project "{rsrc}" to="{out}" repoint="{self.consolidated}" missing=keep')
        self.assertIn(os.path.join("rold", "dem.tif"), self._reload(out)[0].source())

    def test_project_new_from_dir(self):
        import niva

        outs = os.path.join(self.tmp, "outs")
        os.makedirs(outs)
        _write_points(os.path.join(outs, "a.gpkg"), "EPSG:4326", [(1, 1), (2, 2)])
        _write_raster(os.path.join(outs, "dem.tif"))
        proj_out = os.path.join(self.tmp, "new.qgs")
        niva.flow(f'project new from="{outs}" to="{proj_out}" crs=EPSG:6346 title="Region"')
        layers = self._reload(proj_out)  # keeps the project alive via self._p
        self.assertEqual(sorted(layer.name() for layer in layers), ["a", "dem"])
        self.assertTrue(all(layer.isValid() for layer in layers))
        self.assertEqual(self._p.crs().authid(), "EPSG:6346")
        self.assertEqual(self._p.title(), "Region")


class TestPyqgisStyle(unittest.TestCase):
    """`style` — apply/save a layer's .qml style (real symbology round-trip)."""

    def setUp(self):
        from qgis.core import QgsVectorLayer

        self.tmp = tempfile.mkdtemp(prefix="niva_sty_")
        self.gpkg = os.path.join(self.tmp, "roads.gpkg")
        _write_points(self.gpkg, "EPSG:4326", [(1, 1), (2, 2)])
        # A .qml carrying a distinctive style (layer opacity 0.37).
        lay = QgsVectorLayer(f"{self.gpkg}|layername=roads", "r", "ogr")
        lay.setOpacity(0.37)
        self.qml = os.path.join(self.tmp, "house.qml")
        lay.saveNamedStyle(self.qml)

    def _opacity(self, uri):
        from qgis.core import QgsVectorLayer

        return round(QgsVectorLayer(uri, "x", "ogr").opacity(), 3)

    def test_save_style_to_file(self):
        import niva

        out = os.path.join(self.tmp, "out.qml")
        niva.flow(f'load "{self.gpkg}|layername=roads" | style save "{out}"')
        self.assertTrue(os.path.isfile(out))

    def test_apply_to_gpkg_persists_in_style_table(self):
        import niva

        niva.flow(f'load "{self.gpkg}|layername=roads" | style apply "{self.qml}"')
        # a freshly loaded layer adopts the stored default style
        self.assertEqual(self._opacity(f"{self.gpkg}|layername=roads"), 0.37)

    def test_apply_to_single_file_writes_sidecar(self):
        import niva

        shp = os.path.join(self.tmp, "pts.shp")
        niva.flow(f'load "{self.gpkg}|layername=roads" | save "{shp}"')
        niva.flow(f'load "{shp}" | style apply "{self.qml}"')
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "pts.qml")))  # sidecar
        self.assertEqual(self._opacity(shp), 0.37)  # QGIS auto-loads the sidecar

    def test_save_metadata_qmd(self):
        import niva

        out = os.path.join(self.tmp, "roads.qmd")
        niva.flow(f'load "{self.gpkg}|layername=roads" | style save "{out}"')
        self.assertTrue(os.path.isfile(out))


if __name__ == "__main__":
    unittest.main()
