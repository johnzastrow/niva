"""`map` verb tests — composed cartographic layout (pure Python via MockBackend).

Run: ``python -m unittest tests.test_map``.
"""

import unittest

from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


def run(text):
    be = MockBackend()
    Engine(be).execute(parse(text))
    return be


def map_call(be):
    return next(c for c in be.calls if c[0] == "map")


class TestMapDefaults(unittest.TestCase):
    def test_bare_map_turns_decorations_on(self):
        # A map is a cartographic product: legend + scale bar + north arrow default ON.
        be = run("load a.gpkg | map out.pdf")
        _, _, dest, o = map_call(be)
        self.assertEqual(dest, "out.pdf")
        self.assertTrue(o["legend"])
        self.assertTrue(o["scalebar"])
        self.assertTrue(o["northarrow"])
        self.assertEqual(o["page"], "A4")
        self.assertEqual(o["orientation"], "landscape")
        self.assertEqual(o["dpi"], 300)
        self.assertIsNone(o["from_project"])

    def test_bare_flag_strips_all_decorations(self):
        be = run("load a.gpkg | map out.pdf bare")
        o = map_call(be)[3]
        self.assertFalse(o["legend"] or o["scalebar"] or o["northarrow"])

    def test_individual_opt_out(self):
        be = run("load a.gpkg | map out.pdf nolegend nonortharrow")
        o = map_call(be)[3]
        self.assertFalse(o["legend"])
        self.assertTrue(o["scalebar"])
        self.assertFalse(o["northarrow"])

    def test_pass_through_chains(self):
        be = run("load a.gpkg | map out.pdf | save b.gpkg")
        self.assertTrue(any(c[0] == "map" for c in be.calls))
        self.assertTrue(be.saves and be.saves[-1]["dest"].endswith("b.gpkg"))


class TestMapOptions(unittest.TestCase):
    def test_full_option_set(self):
        be = run(
            'load a.gpkg | map plate.pdf title="Terrain" layers="dtm.tif;roads.gpkg" '
            "basemap=osm labels=name page=A3 portrait dpi=200 extent=aoi.gpkg"
        )
        o = map_call(be)[3]
        self.assertEqual(o["title"], "Terrain")
        self.assertEqual(
            [x.rsplit("/", 1)[-1] for x in o["layers"]], ["dtm.tif", "roads.gpkg"]
        )
        self.assertEqual(o["basemap"], "osm")
        self.assertEqual(o["labels"], "name")
        self.assertEqual(o["page"], "A3")
        self.assertEqual(o["orientation"], "portrait")
        self.assertEqual(o["dpi"], 200)
        self.assertTrue(str(o["extent"]).endswith("aoi.gpkg"))

    def test_from_project_mode(self):
        be = run('load a.gpkg | map out.pdf from=study.qgz layout="Overview"')
        o = map_call(be)[3]
        self.assertTrue(str(o["from_project"]).endswith("study.qgz"))
        self.assertEqual(o["layout"], "Overview")


class TestMapErrors(unittest.TestCase):
    def _err(self, text):
        with self.assertRaises(FlowError):
            run(text)

    def test_needs_a_layer(self):
        self._err("map out.pdf")

    def test_needs_output(self):
        self._err("load a.gpkg | map")

    def test_rejects_bad_extension(self):
        self._err("load a.gpkg | map out.gpkg")

    def test_rejects_unknown_flag(self):
        self._err("load a.gpkg | map out.pdf frobnicate")

    def test_rejects_unknown_option(self):
        self._err("load a.gpkg | map out.pdf rotation=45")


if __name__ == "__main__":
    unittest.main()
