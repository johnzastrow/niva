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
    # Isolate from the user's real QGIS profile. niva now boots into the desktop profile
    # (so `@conn` names match the GUI), which means tests that create/delete connections
    # would otherwise touch the user's actual profile. Pointing XDG_DATA_HOME at a temp dir
    # *before* QGIS initialises sends QgsSettings/connections to a throwaway profile.
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="niva_xdg_")
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

    def test_polygonize_alias_outputs_vector(self):
        # `polygonize` is raster-in / vector-out — the output must NOT be forced to a .tif
        # (regression: keying the scratch on input facet broke it). See _output_is_raster.
        import niva
        from qgis.core import QgsVectorLayer

        rast = os.path.join(self.tmp, "r.tif")
        _write_raster(rast)
        out = os.path.join(self.tmp, "poly.gpkg")
        niva.flow(f'load "{rast}" | polygonize field=DN | save "{out}"')
        vl = QgsVectorLayer(out, "p", "ogr")
        self.assertTrue(vl.isValid() and vl.featureCount() >= 1)

    def test_save_sqlite_is_spatialite(self):
        # A `.sqlite` save must be a real SpatiaLite database the provider can read.
        import niva
        from qgis.core import QgsProviderRegistry

        sl = os.path.join(self.tmp, "y.sqlite")
        niva.flow(f'load "{self.src}" | save "{sl}" as pts')
        md = QgsProviderRegistry.instance().providerMetadata("spatialite")
        conn = md.createConnection(f"dbname='{sl}'", {})
        self.assertIn("pts", [t.tableName() for t in conn.tables("")])

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

    def test_project_info_report(self):
        import niva

        out = os.path.join(self.tmp, "info.md")
        niva.flow(f'project info "{self.src}" to="{out}"')
        text = open(out).read()
        self.assertIn("roads", text)        # the layer
        self.assertIn("ogr", text)          # provider
        self.assertIn("roads.gpkg", text)   # datasource
        self.assertIn("| Layer |", text)    # the table

    def test_copy_convert_qgs_to_qgz(self):
        import niva

        out = os.path.join(self.tmp, "conv.qgz")
        niva.flow(f'project "{self.src}" to="{out}"')  # no repoint → copy + convert
        self.assertTrue(os.path.isfile(out))
        layers = self._reload(out)
        self.assertEqual(len(layers), 1)
        self.assertIn("roads.gpkg", layers[0].source())  # datasource unchanged

    def test_paths_relative(self):
        import niva

        out = os.path.join(self.tmp, "rel.qgs")  # sibling of roads.gpkg (both in self.tmp)
        niva.flow(f'project "{self.src}" to="{out}" paths=relative')
        self.assertIn("./roads.gpkg", open(out).read())

    def test_bookmark_union_extent(self):
        import niva

        out = os.path.join(self.tmp, "bm.qgs")
        niva.flow(f'project "{self.src}" to="{out}" bookmark="Study Area"')
        self._reload(out)  # keeps the project alive on self._p
        self.assertEqual([b.name() for b in self._p.bookmarkManager().bookmarks()],
                         ["Study Area"])

    def test_bookmark_centred(self):
        import niva

        out = os.path.join(self.tmp, "bm2.qgs")
        niva.flow(f'project "{self.src}" to="{out}" bookmark="AOI" at="0,0" width=10')
        self._reload(out)
        bm = self._p.bookmarkManager().bookmarks()[0]
        self.assertEqual(bm.name(), "AOI")
        self.assertAlmostEqual(bm.extent().width(), 10.0, places=3)
        self.assertAlmostEqual(bm.extent().center().x(), 0.0, places=6)

    def _template(self, *, opacity=0.42):
        """A template project: a styled `roads` vector slot + a `dem` raster slot, both
        pointing at example data under <tmp>/tmpl_src. Returns the template path."""
        from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

        src = os.path.join(self.tmp, "tmpl_src")
        os.makedirs(src, exist_ok=True)
        _write_points(os.path.join(src, "roads.gpkg"), "EPSG:4326", [(0, 0)])
        _write_raster(os.path.join(src, "dem.tif"))
        proj = QgsProject()
        vl = QgsVectorLayer(f"{os.path.join(src, 'roads.gpkg')}|layername=roads", "roads", "ogr")
        vl.setOpacity(opacity)  # the template's distinctive symbology
        proj.addMapLayer(vl)
        proj.addMapLayer(QgsRasterLayer(os.path.join(src, "dem.tif"), "dem"))
        tmpl = os.path.join(self.tmp, "report.qgz")
        self.assertTrue(proj.write(tmpl))
        return tmpl

    def _data_dir(self):
        """A data dir with same-named `roads.gpkg` (2 features) + `dem.tif` to fill slots."""
        data = os.path.join(self.tmp, "mydata")
        os.makedirs(data, exist_ok=True)
        _write_points(os.path.join(data, "roads.gpkg"), "EPSG:4326", [(5, 5), (6, 6)])
        _write_raster(os.path.join(data, "dem.tif"))
        return data

    def test_from_template_repoints_slots_and_keeps_style(self):
        import niva

        tmpl = self._template(opacity=0.42)
        data = self._data_dir()
        out = os.path.join(self.tmp, "instance.qgz")
        niva.flow(f'project from-template="{tmpl}" to="{out}" data="{data}"')
        layers = {layer.name(): layer for layer in self._reload(out)}
        self.assertEqual(set(layers), {"roads", "dem"})
        roads = layers["roads"]
        self.assertIn(os.path.join("mydata", "roads.gpkg"), roads.source())  # repointed
        self.assertEqual(roads.featureCount(), 2)                            # to the user's data
        self.assertTrue(roads.isValid())
        self.assertAlmostEqual(roads.opacity(), 0.42, places=3)             # style rode along
        self.assertIn(os.path.join("mydata", "dem.tif"), layers["dem"].source())  # raster slot

    def test_from_template_named_via_env(self):
        import niva

        lib = os.path.join(self.tmp, "lib")
        os.makedirs(lib, exist_ok=True)
        tmpl = self._template()
        os.replace(tmpl, os.path.join(lib, "atlas.qgz"))
        data = self._data_dir()
        out = os.path.join(self.tmp, "named.qgz")
        os.environ["NIVA_TEMPLATES"] = lib
        try:
            niva.flow(f'project from-template=atlas to="{out}" data="{data}"')
        finally:
            del os.environ["NIVA_TEMPLATES"]
        self.assertIn(os.path.join("mydata", "roads.gpkg"),
                      {layer.name(): layer.source() for layer in self._reload(out)}["roads"])

    def test_from_template_unmatched_slot_kept_by_default(self):
        import niva

        tmpl = self._template()
        # data has only `dem`, not `roads` → the roads slot is unmatched.
        data = os.path.join(self.tmp, "partial")
        os.makedirs(data, exist_ok=True)
        _write_raster(os.path.join(data, "dem.tif"))
        out = os.path.join(self.tmp, "partial_out.qgz")
        niva.flow(f'project from-template="{tmpl}" to="{out}" data="{data}"')
        names = {layer.name() for layer in self._reload(out)}
        self.assertEqual(names, {"roads", "dem"})  # roads kept (default missing=keep)

    def _existing_project(self):
        """An *existing* real project: a styled slot whose **display name** (`parcels`)
        differs from its datasource layername (`src`), plus a named print layout — the
        case where a user reuses one of their own projects as a template."""
        from qgis.core import (QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutPoint,
                               QgsLayoutSize, QgsPrintLayout, QgsProject, QgsUnitTypes,
                               QgsVectorLayer)

        srcgpkg = os.path.join(self.tmp, "src.gpkg")
        _write_points(srcgpkg, "EPSG:4326", [(0, 0)])
        proj = QgsProject()
        proj.setTitle("My Report")
        vl = QgsVectorLayer(f"{srcgpkg}|layername=src", "parcels", "ogr")  # name ≠ layername
        vl.setOpacity(0.42)
        proj.addMapLayer(vl)
        lay = QgsPrintLayout(proj)
        lay.initializeDefaults()
        lay.setName("Report")
        lbl = QgsLayoutItemLabel(lay)
        lbl.setText("My Report")
        lbl.attemptMove(QgsLayoutPoint(10, 5, QgsUnitTypes.LayoutMillimeters))
        lay.addLayoutItem(lbl)
        mp = QgsLayoutItemMap(lay)
        mp.attemptMove(QgsLayoutPoint(10, 20, QgsUnitTypes.LayoutMillimeters))
        mp.attemptResize(QgsLayoutSize(180, 130, QgsUnitTypes.LayoutMillimeters))
        lay.addLayoutItem(mp)
        proj.layoutManager().addLayout(lay)
        path = os.path.join(self.tmp, "existing.qgz")
        self.assertTrue(proj.write(path))
        return path

    def test_from_template_existing_project_keeps_layout_and_matches_display_name(self):
        import niva

        existing = self._existing_project()
        data = os.path.join(self.tmp, "mydata")
        os.makedirs(data, exist_ok=True)
        # user data named for the slot's DISPLAY name (`parcels`), not its old layername.
        _write_points(os.path.join(data, "parcels.gpkg"), "EPSG:4326", [(5, 5), (6, 6), (7, 7)])
        out = os.path.join(self.tmp, "instance.qgz")
        niva.flow(f'project from-template="{existing}" to="{out}" data="{data}"')
        layers = self._reload(out)
        self.assertEqual([lay.name() for lay in self._p.layoutManager().layouts()], ["Report"])
        parcels = {layer.name(): layer for layer in layers}["parcels"]
        self.assertIn(os.path.join("mydata", "parcels.gpkg"), parcels.source())  # display-name match
        self.assertEqual(parcels.featureCount(), 3)                              # the user's data
        self.assertAlmostEqual(parcels.opacity(), 0.42, places=3)               # style preserved

    def test_to_template_then_from_template_by_name(self):
        import niva

        existing = self._existing_project()
        lib = os.path.join(self.tmp, "lib")
        data = os.path.join(self.tmp, "mydata2")
        os.makedirs(data, exist_ok=True)
        _write_points(os.path.join(data, "parcels.gpkg"), "EPSG:4326", [(1, 1), (2, 2)])
        out = os.path.join(self.tmp, "by_name.qgz")
        os.environ["NIVA_TEMPLATES"] = lib
        try:
            niva.flow(f'project to-template=report from="{existing}" paths=relative')
            self.assertTrue(os.path.isfile(os.path.join(lib, "report.qgz")))  # registered
            niva.flow(f'project from-template=report to="{out}" data="{data}"')
        finally:
            del os.environ["NIVA_TEMPLATES"]
        layers = {layer.name(): layer for layer in self._reload(out)}  # sets self._p
        self.assertEqual([lay.name() for lay in self._p.layoutManager().layouts()], ["Report"])
        self.assertIn(os.path.join("mydata2", "parcels.gpkg"), layers["parcels"].source())

    def test_bundled_example_instantiates(self):
        import niva

        # The shipped `example` template: resolve by name (no env), repoint its three slots,
        # and carry its layout + bookmark + title through to the output.
        data = os.path.join(self.tmp, "exdata")
        os.makedirs(data, exist_ok=True)
        for slot in ("boundary", "roads", "places"):
            _write_points(os.path.join(data, f"{slot}.gpkg"), "EPSG:4326",
                          [(-79.06, 43.09), (-79.05, 43.10)])
        out = os.path.join(self.tmp, "example_out.qgz")
        niva.flow(f'project from-template=example to="{out}" data="{data}"')
        layers = {layer.name(): layer for layer in self._reload(out)}  # sets self._p
        self.assertEqual(set(layers), {"boundary", "roads", "places"})
        for slot in ("boundary", "roads", "places"):
            self.assertIn(os.path.join("exdata", f"{slot}.gpkg"), layers[slot].source())
            self.assertTrue(layers[slot].isValid())
        self.assertEqual([lay.name() for lay in self._p.layoutManager().layouts()], ["Map"])
        self.assertEqual([b.name() for b in self._p.bookmarkManager().bookmarks()],
                         ["Study Area"])
        self.assertEqual(self._p.title(), "Example Map")


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

    def test_apply_chains_after_save(self):
        # `… | save out.gpkg | style apply x.qml` — save returns a path-backed handle;
        # style must load it rather than crash on a str. (Regression for a documented chain.)
        import niva

        out = os.path.join(self.tmp, "saved.gpkg")
        niva.flow(f'load "{self.gpkg}|layername=roads" | save "{out}" | style apply "{self.qml}"')
        self.assertEqual(self._opacity(out), 0.37)

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

    def test_save_sld(self):
        import niva

        out = os.path.join(self.tmp, "roads.sld")
        niva.flow(f'load "{self.gpkg}|layername=roads" | style save "{out}"')
        self.assertTrue(os.path.isfile(out))

    def test_save_qlr_includes_datasource(self):
        import niva

        out = os.path.join(self.tmp, "roads.qlr")
        niva.flow(f'load "{self.gpkg}|layername=roads" | style save "{out}"')
        self.assertTrue(os.path.isfile(out))
        with open(out) as fh:  # a QLR bundles the datasource, so it names the gpkg
            self.assertIn("roads.gpkg", fh.read())


class TestPyqgisEnvironmentReport(unittest.TestCase):
    """`info` — the real environment report against a live QGIS (the part MockBackend
    can't exercise: actual versions, provider list, connection probing)."""

    def test_report_has_the_expected_sections(self):
        from niva.environment import report_markdown

        report = report_markdown()
        for heading in ("# niva — environment", "## niva", "## Verbs & algorithms",
                        "## Database connections", "## QGIS profiles",
                        "## Environment (niva variables)", "## QGIS & geo stack",
                        "## Python & platform"):
            self.assertIn(heading, report)
        # The reachable-algorithm count must resolve to a real number, and QGIS must
        # report a version (not the "unavailable" fallback).
        self.assertNotIn("**unavailable** algorithms", report)
        self.assertNotIn("QGIS: unavailable", report)
        # The geo stack must include the SpatiaLite/SQLite and PyQt lines.
        self.assertIn("SpatiaLite/SQLite:", report)
        self.assertIn("PyQt", report)
        self.assertIn("sys.base_prefix", report)

    def test_report_reads_a_real_qgis_profile_not_the_generic_store(self):
        # The whole point of the profile fix: a standalone niva must read the QGIS
        # desktop profile, never the generic "Unknown Organization" Qt store (which holds
        # none of the user's connections).
        from niva.environment import report_markdown

        report = report_markdown()
        self.assertNotIn("Unknown Organization", report)
        self.assertIn("Active profile:", report)

    def test_report_masks_secret_env_vars(self):
        import os

        from niva.environment import report_markdown

        os.environ["NIVA_SMTP_PASSWORD"] = "hunter2-should-not-appear"
        try:
            report = report_markdown()
        finally:
            del os.environ["NIVA_SMTP_PASSWORD"]
        self.assertNotIn("hunter2-should-not-appear", report)
        self.assertIn("`NIVA_SMTP_PASSWORD` = **set**", report)

    def test_info_verb_writes_report(self):
        import niva

        out = os.path.join(tempfile.mkdtemp(prefix="niva_info_"), "env.md")
        niva.flow(f'info to="{out}"')
        self.assertTrue(os.path.isfile(out))
        with open(out) as fh:
            self.assertIn("niva — environment", fh.read())


if __name__ == "__main__":
    unittest.main()
