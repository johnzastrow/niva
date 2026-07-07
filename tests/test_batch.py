"""Tests for directory iteration (`each`) and multi-layer write (`save … as`).
Mock-backed — no QGIS. Real geospatial reads are simulated via MockBackend."""

import os
import tempfile
import unittest

from niva import flow
from niva.engine import MockBackend
from niva.errors import FlowError


def _touch(path):
    open(path, "w").close()


class TestMultiLayerWrite(unittest.TestCase):
    def test_save_as_names_the_layer_and_appends(self):
        mb = MockBackend()
        flow("load a.gpkg | dissolve | save out.gpkg as regions", backend=mb)
        self.assertEqual(
            mb.saves[-1], {"dest": "out.gpkg", "layer_name": "regions", "append": True}
        )

    def test_plain_save_overwrites_file(self):
        mb = MockBackend()
        flow("load a.gpkg | save out.gpkg", backend=mb)
        self.assertEqual(
            mb.saves[-1], {"dest": "out.gpkg", "layer_name": None, "append": False}
        )

    def test_save_as_requires_a_container(self):
        with self.assertRaises(FlowError):
            flow("load a.gpkg | save out.shp as roads", backend=MockBackend())


class TestEachBatch(unittest.TestCase):
    def _dir_with(self, *names):
        root = tempfile.mkdtemp(prefix="niva_each_")
        for n in names:
            _touch(os.path.join(root, n))
        return root

    def test_each_glob_runs_per_file_into_one_gpkg(self):
        root = self._dir_with("roads.geojson", "rivers.geojson", "notes.txt")
        mb = MockBackend()
        flow(
            f'each "{root}/*.geojson" | reproject EPSG:6346 | save out.gpkg', backend=mb
        )
        # one save per matched file, each as its own layer, appending
        layers = sorted(s["layer_name"] for s in mb.saves)
        self.assertEqual(layers, ["rivers", "roads"])
        self.assertTrue(all(s["append"] and s["dest"] == "out.gpkg" for s in mb.saves))

    def test_each_directory_recurses_and_ignores_non_geo(self):
        root = self._dir_with("a.shp", "b.geojson", "readme.txt")
        os.makedirs(os.path.join(root, "sub"))
        _touch(os.path.join(root, "sub", "c.gpkg"))
        mb = MockBackend()
        flow(f'each "{root}" | save out.gpkg', backend=mb)
        names = sorted(s["layer_name"] for s in mb.saves)
        self.assertEqual(names, ["a", "b", "c"])  # txt ignored, sub/ recursed

    def test_each_expands_multilayer_gpkg(self):
        root = tempfile.mkdtemp(prefix="niva_each_")
        gpkg = os.path.join(root, "bundle.gpkg")
        _touch(gpkg)
        mb = MockBackend()
        mb.sublayer_map[gpkg] = ["town", "parcels", "streets"]
        flow(f'each "{gpkg}" | reproject EPSG:6346 | save collected.gpkg', backend=mb)
        self.assertEqual(
            sorted(s["layer_name"] for s in mb.saves), ["parcels", "streets", "town"]
        )

    def test_each_raster_name_template(self):
        root = self._dir_with("dem1.tif", "dem2.tif")
        mb = MockBackend()
        out = os.path.join(root, "out")
        flow(
            f'each "{root}/*.tif" | warp EPSG:6346 | save "{out}/{{name}}.tif"',
            backend=mb,
        )
        dests = sorted(os.path.basename(s["dest"]) for s in mb.saves)
        self.assertEqual(dests, ["dem1.tif", "dem2.tif"])

    def test_batch_save_to_non_container_without_template_errors(self):
        root = self._dir_with("a.shp", "b.shp")
        with self.assertRaises(FlowError):
            flow(f'each "{root}/*.shp" | save out.shp', backend=MockBackend())

    def test_each_no_match_errors(self):
        root = tempfile.mkdtemp(prefix="niva_each_")
        with self.assertRaises(FlowError):
            flow(f'each "{root}/*.shp" | save out.gpkg', backend=MockBackend())

    def test_batch_compacts_gpkg_targets_once(self):
        root = self._dir_with("a.geojson", "b.geojson")
        mb = MockBackend()
        flow(f'each "{root}/*.geojson" | save out.gpkg', backend=mb)
        # the container is VACUUMed exactly once at the end (not per item)
        compacts = [c for c in mb.calls if c[0] == "compact"]
        self.assertEqual(compacts, [("compact", "out.gpkg")])

    def test_each_must_be_first_stage(self):
        with self.assertRaises(FlowError):
            flow('load a.gpkg | each "x/*.shp"', backend=MockBackend())

    def test_name_placeholder_outside_batch_errors(self):
        with self.assertRaises(FlowError):
            flow('load a.gpkg | save "out/{name}.gpkg"', backend=MockBackend())


if __name__ == "__main__":
    unittest.main()


class TestEachFilters(unittest.TestCase):
    """`each`'s flat filter options (reuse of find's predicates). Offline filters only —
    the GDAL-enriched ones (geom/crs/features/hasfield) are exercised in the live-QGIS tier."""

    def _dir(self):
        return tempfile.mkdtemp(prefix="niva_eachf_")

    def _write(self, root, name, nbytes=0):
        path = os.path.join(root, name)
        with open(path, "w") as fh:
            fh.write("x" * nbytes)
        return path

    def _run(self, source, opts=""):
        mb = MockBackend()
        flow(f'each "{source}" {opts} | save out.gpkg', backend=mb)
        return sorted(s["layer_name"] for s in mb.saves)

    def test_ext_filter(self):
        root = self._dir()
        self._write(root, "a.geojson")
        self._write(root, "b.gpkg")
        self._write(root, "c.geojson")
        self.assertEqual(self._run(root, "ext=geojson"), ["a", "c"])

    def test_minsize_filter(self):
        root = self._dir()
        self._write(root, "small.geojson", 10)
        self._write(root, "big.geojson", 5000)
        self.assertEqual(self._run(f"{root}/*.geojson", "minsize=1k"), ["big"])

    def test_maxsize_filter(self):
        root = self._dir()
        self._write(root, "small.geojson", 10)
        self._write(root, "big.geojson", 5000)
        self.assertEqual(self._run(f"{root}/*.geojson", "maxsize=1k"), ["small"])

    def test_unknown_option_errors(self):
        root = self._dir()
        self._write(root, "a.geojson")
        with self.assertRaises(FlowError):
            flow(f'each "{root}" bogus=1 | save out.gpkg', backend=MockBackend())

    def test_bad_numeric_value_errors(self):
        root = self._dir()
        self._write(root, "a.geojson")
        with self.assertRaises(FlowError):
            flow(
                f'each "{root}" minfeatures=abc | save out.gpkg', backend=MockBackend()
            )

    def test_no_match_after_filter_errors(self):
        root = self._dir()
        self._write(root, "a.geojson", 10)
        with self.assertRaises(FlowError):
            flow(f'each "{root}" minsize=1g | save out.gpkg', backend=MockBackend())

    def test_meta_filter_without_gdal_errors_clearly(self):
        # geom/crs/features/hasfield need OGR; offline (no GDAL) they must raise a clear
        # error, not silently match nothing.
        from niva import find as _find

        if _find.have_gdal():
            self.skipTest("GDAL present — offline-guard path not exercised")
        root = self._dir()
        self._write(root, "a.geojson")
        with self.assertRaises(FlowError):
            flow(f'each "{root}" geom=polygon | save out.gpkg', backend=MockBackend())


class TestSplit(unittest.TestCase):
    def test_split_dispatches_to_filterbygeometry(self):
        mb = MockBackend()
        flow("load a.gpkg | split polygon | save polys.gpkg", backend=mb)
        self.assertIn(("run", "native:filterbygeometry", {}), mb.calls)

    def test_split_accepts_singular_and_plural(self):
        for kind in ("point", "points", "line", "lines", "polygon", "polygons"):
            mb = MockBackend()
            flow(f"load a.gpkg | split {kind} | save out.gpkg", backend=mb)
            self.assertIn(("run", "native:filterbygeometry", {}), mb.calls)

    def test_split_rejects_unknown_type(self):
        with self.assertRaises(FlowError):
            flow("load a.gpkg | split blobs | save out.gpkg", backend=MockBackend())

    def test_split_needs_a_type(self):
        with self.assertRaises(FlowError):
            flow("load a.gpkg | split | save out.gpkg", backend=MockBackend())
