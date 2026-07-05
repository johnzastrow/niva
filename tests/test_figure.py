"""`figure` verb tests — quick map-image rendering (pure Python via MockBackend).

Run: ``python -m unittest tests.test_figure``.
"""

import unittest

from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


def run(text):
    be = MockBackend()
    Engine(be).execute(parse(text))
    return be


def figure_call(be):
    return next(c for c in be.calls if c[0] == "figure")


class TestFigureDefaults(unittest.TestCase):
    def test_bare_command_records_sensible_defaults(self):
        be = run("load dem.tif | figure out.png")
        _, name, dest, opts = figure_call(be)
        self.assertEqual(dest, "out.png")
        self.assertIsNone(opts["size"])  # backend derives size from extent
        self.assertEqual(opts["dpi"], 96)
        self.assertIsNone(opts["extent"])  # backend uses the union of layers
        self.assertEqual(opts["layers"], [])
        self.assertIsNone(opts["basemap"])
        self.assertIsNone(opts["labels"])

    def test_pass_through_chains(self):
        # figure returns the upstream layer, so a later `save` still runs.
        be = run("load roads.gpkg | figure preview.png | save out.gpkg")
        self.assertTrue(any(c[0] == "figure" for c in be.calls))
        self.assertTrue(be.saves and be.saves[-1]["dest"].endswith("out.gpkg"))


class TestFigureOptions(unittest.TestCase):
    def test_all_options_parsed(self):
        be = run(
            "load a.gpkg | figure m.png size=1600x900 dpi=150 "
            'extent=10,20,30,40 layers="b.gpkg;c.tif" basemap=osm bg=white labels=name'
        )
        _, _, dest, o = figure_call(be)
        self.assertEqual(o["size"], (1600, 900))
        self.assertEqual(o["dpi"], 150)
        self.assertEqual(o["extent"], (10.0, 20.0, 30.0, 40.0))
        self.assertEqual(
            [x.rsplit("/", 1)[-1] for x in o["layers"]], ["b.gpkg", "c.tif"]
        )
        self.assertEqual(o["basemap"], "osm")
        self.assertEqual(o["bg"], "white")
        self.assertEqual(o["labels"], "name")

    def test_extent_layer_keyword_is_none(self):
        be = run("load a.gpkg | figure m.png extent=layer")
        self.assertIsNone(figure_call(be)[3]["extent"])

    def test_extent_path_kept_as_string(self):
        be = run("load a.gpkg | figure m.png extent=aoi.gpkg")
        self.assertTrue(str(figure_call(be)[3]["extent"]).endswith("aoi.gpkg"))

    def test_size_accepts_unicode_times(self):
        be = run("load a.gpkg | figure m.png size=800×600")
        self.assertEqual(figure_call(be)[3]["size"], (800, 600))


class TestFigureErrors(unittest.TestCase):
    def _err(self, text):
        with self.assertRaises(FlowError):
            run(text)

    def test_needs_a_layer(self):
        self._err("figure out.png")

    def test_needs_output_path(self):
        self._err("load a.gpkg | figure")

    def test_rejects_non_image_extension(self):
        self._err(
            "load a.gpkg | figure out.pdf"
        )  # pdf is `map` territory, not `figure`

    def test_rejects_bad_size(self):
        self._err("load a.gpkg | figure out.png size=big")

    def test_rejects_extra_positional(self):
        self._err("load a.gpkg | figure a.png b.png")

    def test_rejects_unknown_option(self):
        self._err("load a.gpkg | figure out.png rotation=45")


if __name__ == "__main__":
    unittest.main()
