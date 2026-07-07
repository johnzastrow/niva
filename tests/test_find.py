"""Tests for `niva find` (issue #43). The offline layer — walking, base records, both filter
predicates, the parsers and formatters — is exercised deterministically with temp files. GDAL
enrichment is tested only when `osgeo` imports (skipped otherwise), so the suite stays green on
any interpreter."""

import os
import tempfile
import time
import unittest

from niva import find as F


class TestParsers(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(F.parse_size("512"), 512)
        self.assertEqual(F.parse_size("10k"), 10 * 1024)
        self.assertEqual(F.parse_size("2.5M"), int(2.5 * 1024**2))
        self.assertEqual(F.parse_size("1g"), 1024**3)
        self.assertEqual(F.parse_size("5MB"), 5 * 1024**2)  # trailing b ignored
        with self.assertRaises(ValueError):
            F.parse_size("")

    def test_parse_age(self):
        self.assertEqual(F.parse_age("30s"), 30)
        self.assertEqual(F.parse_age("15m"), 15 * 60)
        self.assertEqual(F.parse_age("24h"), 24 * 3600)
        self.assertEqual(F.parse_age("7d"), 7 * 86400)
        self.assertEqual(F.parse_age("2"), 2 * 86400)  # bare number → days

    def test_human_size(self):
        self.assertEqual(F.human_size(0), "0 B")
        self.assertEqual(F.human_size(512), "512 B")
        self.assertEqual(F.human_size(1536), "1.5 KB")
        self.assertTrue(F.human_size(5 * 1024**3).endswith("GB"))

    def test_exts_for_pattern(self):
        self.assertEqual(F.exts_for_pattern("*.gpkg", all_files=False), {"gpkg"})
        self.assertEqual(F.exts_for_pattern("roads.SHP", all_files=False), {"shp"})
        # a bare/wildcard pattern → the full spatial corpus, unless --all-files
        self.assertEqual(F.exts_for_pattern("*", all_files=False), set(F.SPATIAL_EXTS))
        self.assertIsNone(F.exts_for_pattern("*", all_files=True))


class TestScanAndBase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        # a small tree: root has a.gpkg + notes.txt; sub/ has b.shp; sub/deep/ has c.tif
        open(os.path.join(self.td, "a.gpkg"), "w").close()
        open(os.path.join(self.td, "notes.txt"), "w").close()
        os.makedirs(os.path.join(self.td, "sub", "deep"))
        open(os.path.join(self.td, "sub", "b.shp"), "w").close()
        open(os.path.join(self.td, "sub", "deep", "c.tif"), "w").close()

    def _names(self, paths):
        return sorted(os.path.basename(p) for p in paths)

    def test_walk_recursive(self):
        got = self._names(F.walk([self.td], recursive=True))
        self.assertEqual(got, ["a.gpkg", "b.shp", "c.tif", "notes.txt"])

    def test_walk_shallow(self):
        got = self._names(F.walk([self.td], recursive=False))
        self.assertEqual(got, ["a.gpkg", "notes.txt"])

    def test_walk_max_depth(self):
        got = self._names(F.walk([self.td], recursive=True, max_depth=1))
        self.assertEqual(got, ["a.gpkg", "b.shp", "notes.txt"])  # not c.tif (depth 2)

    def test_walk_single_file(self):
        p = os.path.join(self.td, "a.gpkg")
        self.assertEqual(list(F.walk([p])), [p])

    def test_base_record(self):
        rec = F.base_record(os.path.join(self.td, "a.gpkg"))
        self.assertEqual(rec["name"], "a.gpkg")
        self.assertEqual(rec["ext"], "gpkg")
        self.assertEqual(rec["format"], "GeoPackage")
        self.assertEqual(rec["kind"], "vector")
        self.assertIn("size", rec)


class TestFilters(unittest.TestCase):
    def test_match_base_pattern_and_exts(self):
        rec = F.base_record("/x/roads.gpkg")
        self.assertTrue(F.match_base(rec, {"pattern": "*.gpkg", "exts": {"gpkg"}}))
        self.assertFalse(F.match_base(rec, {"pattern": "*.shp"}))
        self.assertFalse(F.match_base(rec, {"exts": {"shp"}}))

    def test_match_base_size_and_format(self):
        rec = {
            "name": "a.gpkg",
            "ext": "gpkg",
            "format": "GeoPackage",
            "size": 2048,
            "mtime": 0,
        }
        self.assertTrue(F.match_base(rec, {"min_size": 1024}))
        self.assertFalse(F.match_base(rec, {"min_size": 4096}))
        self.assertFalse(F.match_base(rec, {"max_size": 1024}))
        self.assertTrue(F.match_base(rec, {"format": "geopackage"}))  # case-insensitive
        self.assertFalse(F.match_base(rec, {"format": "shapefile"}))

    def test_match_base_newer_than(self):
        now = time.time()
        rec = {"name": "a.gpkg", "ext": "gpkg", "format": "", "size": 1, "mtime": now}
        self.assertTrue(F.match_base(rec, {"newer_than": now - 100}))
        self.assertFalse(F.match_base(rec, {"newer_than": now + 100}))

    def test_match_meta(self):
        rec = {
            "geometry": "Multi Polygon",
            "crs": "EPSG:6346",
            "features": 10,
            "fields": ["id", "parcel_id"],
        }
        self.assertTrue(
            F.match_meta(rec, {"geom": "polygon"})
        )  # substring, case-insensitive
        self.assertFalse(F.match_meta(rec, {"geom": "point"}))
        self.assertTrue(F.match_meta(rec, {"crs": "epsg:6346"}))
        self.assertFalse(F.match_meta(rec, {"crs": "EPSG:4326"}))
        self.assertTrue(F.match_meta(rec, {"min_features": 5, "max_features": 20}))
        self.assertFalse(F.match_meta(rec, {"min_features": 50}))
        self.assertTrue(F.match_meta(rec, {"has_field": "parcel_id"}))
        self.assertFalse(F.match_meta(rec, {"has_field": "nope"}))

    def test_match_meta_missing_probe_fails_feature_filter(self):
        # A record with no features probed can't satisfy a feature-count filter.
        self.assertFalse(F.match_meta({}, {"min_features": 1}))


class TestFindAndFormat(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        for name in ("a.gpkg", "b.gpkg", "c.shp", "ignore.txt"):
            with open(os.path.join(self.td, name), "w") as fh:
                fh.write("x" * 100)

    def test_find_defaults_to_spatial_only(self):
        recs = F.find(
            [self.td], {"pattern": "*", "exts": set(F.SPATIAL_EXTS)}, do_enrich=False
        )
        names = sorted(r["name"] for r in recs)
        self.assertEqual(names, ["a.gpkg", "b.gpkg", "c.shp"])  # ignore.txt excluded

    def test_find_pattern_and_limit(self):
        crit = {"pattern": "*.gpkg", "exts": {"gpkg"}}
        recs = F.find([self.td], crit, do_enrich=False, limit=1)
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]["name"].endswith(".gpkg"))

    def test_format_table_empty_and_nonempty(self):
        self.assertIn("no matching", F.format_table([]))
        recs = F.find([self.td], {"pattern": "*.shp", "exts": {"shp"}}, do_enrich=False)
        out = F.format_table(recs)
        self.assertIn("c.shp", out)
        self.assertIn("match(es)", out)

    def test_format_json_roundtrips(self):
        import json

        recs = F.find(
            [self.td], {"pattern": "*.gpkg", "exts": {"gpkg"}}, do_enrich=False
        )
        data = json.loads(F.format_json(recs))
        self.assertEqual(len(data), 2)
        self.assertIn("path", data[0])

    def test_format_as_flow_emits_valid_each_lines(self):
        recs = F.find(
            [self.td], {"pattern": "*.gpkg", "exts": {"gpkg"}}, do_enrich=False
        )
        flow = F.format_as_flow(recs)
        each_lines = [ln for ln in flow.splitlines() if ln.startswith("each ")]
        self.assertEqual(len(each_lines), 2)
        self.assertTrue(all("| save " in ln for ln in each_lines))
        self.assertIn("nothing to build", F.format_as_flow([]))


@unittest.skipUnless(F.have_gdal(), "GDAL/OGR not importable on this interpreter")
class TestEnrichment(unittest.TestCase):
    def test_enrich_vector_surfaces_fields_and_fid(self):
        from osgeo import ogr, osr

        td = tempfile.mkdtemp()
        path = os.path.join(td, "pts.gpkg")
        drv = ogr.GetDriverByName("GPKG")
        ds = drv.CreateDataSource(path)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        lyr = ds.CreateLayer("pts", srs, ogr.wkbPoint)
        lyr.CreateField(ogr.FieldDefn("parcel_id", ogr.OFTString))
        feat = ogr.Feature(lyr.GetLayerDefn())
        feat.SetGeometry(ogr.CreateGeometryFromWkt("POINT (1 2)"))
        lyr.CreateFeature(feat)
        ds = None

        rec = F.base_record(path)
        F.enrich(rec)
        self.assertEqual(rec["kind"], "vector")
        self.assertIn("Point", rec["geometry"])
        self.assertEqual(rec["crs"], "EPSG:4326")
        self.assertEqual(rec["features"], 1)
        self.assertIn("parcel_id", rec["fields"])
        self.assertEqual(rec["fid_column"], "fid")  # GeoPackage PK column


if __name__ == "__main__":
    unittest.main()
