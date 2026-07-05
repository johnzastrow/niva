"""Long-running RESILIENCE / soak tests — one per component.

These are deliberately slow (large data, real renders) and are **skipped by default** so
they never slow ordinary development. They exercise the real ``PyqgisBackend`` (not the
MockBackend), so they must run under QGIS's Python.

Run them explicitly:

    NIVA_STRESS=1 PYTHONPATH=$PWD:/usr/share/qgis/python:/usr/share/qgis/python/plugins:/usr/lib/python3/dist-packages \
        QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_stress -v

Scale with NIVA_STRESS_SCALE (default 1 → tens of thousands of features / multi-megapixel
rasters; bump to 4–8 for a real soak). Point-cloud tests use ~/Downloads/17TPH*.las if present,
else they skip. The bar is *resilience*: every pipeline must finish, produce valid output, and
not crash the interpreter — long is fine, silent death is not.
"""

import glob
import os
import unittest

STRESS = os.environ.get("NIVA_STRESS")
SCALE = int(os.environ.get("NIVA_STRESS_SCALE", "1"))

_TILES = sorted(glob.glob(os.path.expanduser("~/Downloads/17TPH*.las")))


@unittest.skipUnless(STRESS, "set NIVA_STRESS=1 to run the long resilience suite")
class StressBase(unittest.TestCase):
    tmp = None
    big_vector = None
    big_raster = None

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.tmp = tempfile.mkdtemp(prefix="niva_stress_")
        cls.big_vector = os.path.join(cls.tmp, "big.gpkg")
        cls.big_raster = os.path.join(cls.tmp, "big.tif")
        cls._make_big_vector(cls.big_vector, n=20000 * SCALE)
        cls._make_big_raster(cls.big_raster, side=2000 * SCALE)

    @staticmethod
    def _make_big_vector(path, n):
        """Write ``n`` point features with a couple of attributes via OGR."""
        from osgeo import ogr, osr

        drv = ogr.GetDriverByName("GPKG")
        if os.path.exists(path):
            drv.DeleteDataSource(path)
        ds = drv.CreateDataSource(path)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        lyr = ds.CreateLayer("points", srs, ogr.wkbPoint)
        lyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
        lyr.CreateField(ogr.FieldDefn("name", ogr.OFTString))
        defn = lyr.GetLayerDefn()
        lyr.StartTransaction()
        for i in range(n):
            f = ogr.Feature(defn)
            f.SetField("id", i)
            f.SetField("name", f"p{i}")
            # a deterministic spread (no RNG needed) across a 100km square
            x = (i * 977) % 100000
            y = (i * 613) % 100000
            g = ogr.Geometry(ogr.wkbPoint)
            g.AddPoint(float(x), float(y))
            f.SetGeometry(g)
            lyr.CreateFeature(f)
        lyr.CommitTransaction()
        ds = None

    @staticmethod
    def _make_big_raster(path, side):
        from osgeo import gdal, osr

        drv = gdal.GetDriverByName("GTiff")
        ds = drv.Create(
            path,
            side,
            side,
            1,
            gdal.GDT_Float32,
            options=["COMPRESS=DEFLATE", "TILED=YES"],
        )
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform([0, 10, 0, 100000, 0, -10])
        band = ds.GetRasterBand(1)
        # fill row-by-row so we never hold a full side×side array for huge scales
        import array

        for row in range(side):
            line = array.array("f", [(row + col) % 255 for col in range(side)])
            band.WriteRaster(0, row, side, 1, line.tobytes())
        band.FlushCache()
        ds = None

    def _run(self, flow):
        """Run a flow with the real backend; fail loudly on any exception."""
        import niva

        niva.flow(flow)


class TestFigureResilience(StressBase):
    def test_large_vector_figure(self):
        out = os.path.join(self.tmp, "bigvec.png")
        self._run(
            f'load "{self.big_vector}" | figure "{out}" size=2000x2000 labels=name'
        )
        self.assertGreater(os.path.getsize(out), 1000)

    def test_large_raster_figure(self):
        out = os.path.join(self.tmp, "bigrast.png")
        self._run(f'load "{self.big_raster}" | figure "{out}" size=2000x2000')
        self.assertGreater(os.path.getsize(out), 1000)


class TestMapResilience(StressBase):
    def test_large_vector_map(self):
        out = os.path.join(self.tmp, "bigvec_map.pdf")
        self._run(
            f'load "{self.big_vector}" | map "{out}" title="Stress" page=A3 dpi=200'
        )
        self.assertGreater(os.path.getsize(out), 1000)

    def test_many_layer_map(self):
        out = os.path.join(self.tmp, "many.pdf")
        self._run(
            f'load "{self.big_vector}" | map "{out}" '
            f'layers="{self.big_raster}" labels=name page=A3 dpi=200'
        )
        self.assertGreater(os.path.getsize(out), 1000)


class TestPipelineResilience(StressBase):
    def test_long_chained_pipeline(self):
        # A deep chain of geometry ops on a large layer must complete and stay valid.
        out = os.path.join(self.tmp, "chained.gpkg")
        self._run(
            f'load "{self.big_vector}" | reproject EPSG:4326 | reproject EPSG:3857 '
            f'| buffer 50m | fixgeom | dissolve | explode | fixgeom | save "{out}"'
        )
        self.assertTrue(os.path.exists(out))


@unittest.skipUnless(STRESS, "set NIVA_STRESS=1")
@unittest.skipUnless(
    _TILES, "no ~/Downloads/17TPH*.las tiles to stress the point-cloud path"
)
class TestPointCloudResilience(unittest.TestCase):
    def test_pdalcli_dtm_and_map(self):
        import tempfile

        import niva

        tmp = tempfile.mkdtemp(prefix="niva_stress_pc_")
        dtm = os.path.join(tmp, "dtm.tif")
        niva.flow(
            f'load "{_TILES[0]}" | run pdalcli:to_raster attribute=Z '
            f'filter="Classification==2" resolution=1 | save "{dtm}"'
        )
        self.assertTrue(os.path.exists(dtm) and os.path.getsize(dtm) > 1000)
        # and render the result — the full point-cloud → raster → map chain
        niva.flow(f'load "{dtm}" | map "{os.path.join(tmp, "dtm.pdf")}" title="DTM"')
        self.assertTrue(os.path.exists(os.path.join(tmp, "dtm.pdf")))


if __name__ == "__main__":
    unittest.main()
