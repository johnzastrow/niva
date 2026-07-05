"""Offline algorithm-catalog tests — `describe <id>` and `run` validation with NO QGIS
(issues #25, #26). These exercise the packaged `niva/registry/algorithms.json`.

Run: ``python -m unittest tests.test_catalog``.
"""

import unittest

from niva import describe
from niva.registry import catalog


class TestCatalog(unittest.TestCase):
    def test_catalog_is_packaged_and_populated(self):
        self.assertGreater(len(catalog.catalog()), 500)  # ~878 algorithms shipped

    def test_param_names_and_defaults_present(self):
        e = catalog.algorithm("native:buffer")
        self.assertIsNotNone(e)
        by = {p["name"]: p for p in e["params"]}
        self.assertEqual(by["SEGMENTS"]["default"], 5)  # a default you never type
        self.assertEqual(by["END_CAP_STYLE"]["enum"], ["Round", "Flat", "Square"])

    def test_unknown_id_is_none(self):
        self.assertIsNone(catalog.algorithm("native:nope"))
        self.assertIsNone(catalog.param_names("native:nope"))


class TestDescribeOffline(unittest.TestCase):
    def test_describe_algorithm_offline(self):
        out = describe("native:buffer")  # no QGIS on the path
        self.assertIn('algorithm native:buffer — "Buffer"', out)
        self.assertIn("SEGMENTS (number, optional, default 5)", out)

    def test_describe_pdal_offline(self):
        out = describe("pdal:exportraster")
        self.assertIn("ATTRIBUTE", out)
        self.assertIn("RESOLUTION", out)

    def test_describe_unknown_id_offline_errors_clearly(self):
        from niva.errors import FlowError

        with self.assertRaises(FlowError):
            describe("native:definitely-not-real")


class TestRunValidation(unittest.TestCase):
    def _warn(self, algo, opts):
        from niva.cli.main import _run_warnings

        return _run_warnings(algo, opts)

    def test_good_params_no_warning(self):
        self.assertEqual(
            self._warn("native:buffer", {"DISTANCE": "100", "SEGMENTS": "12"}), []
        )

    def test_unknown_param_warns_with_suggestion(self):
        w = self._warn("native:buffer", {"SEGMENTZ": "12"})
        self.assertEqual(len(w), 1)
        self.assertIn("SEGMENTZ", w[0])
        self.assertIn("SEGMENTS", w[0])  # did-you-mean

    def test_unknown_id_warns(self):
        w = self._warn("native:nonexistent", {"FOO": "1"})
        self.assertTrue(w and "not in niva's algorithm catalog" in w[0])

    def test_harness_ids_are_skipped(self):
        self.assertEqual(self._warn("pdalcli:to_raster", {"attribute": "Z"}), [])
        self.assertEqual(self._warn("saga:ta_morphometry:0", {"UNIT_SLOPE": "1"}), [])


class TestExplainVerbValidation(unittest.TestCase):
    """`--explain` must reject an invented verb in built-in position (issue #29)."""

    def _plan(self, flow):
        import contextlib
        import io

        from niva.cli.main import _print_plan
        from niva.grammar import parse

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            unknown = _print_plan(parse(flow), "<t>")
        return unknown, buf.getvalue()

    def test_invented_verb_is_flagged(self):
        unknown, out = self._plan('load a.gpkg | compute foo="1" | save b.gpkg')
        self.assertTrue(unknown)  # → CLI exits non-zero
        self.assertIn("UNKNOWN VERB", out)

    def test_typo_gets_suggestion(self):
        _, out = self._plan("load a.gpkg | reproj EPSG:3857 | save b.gpkg")
        self.assertIn("did you mean `reproject`?", out)

    def test_valid_flow_passes(self):
        unknown, _ = self._plan(
            'load a.gpkg | filter "x>1" | buffer 100m | save b.gpkg'
        )
        self.assertFalse(unknown)

    def test_run_id_not_treated_as_unknown_verb(self):
        # a run <id> is validated separately (soft warning), never an unknown-verb error
        unknown, _ = self._plan(
            "load a.las | run pdalcli:to_raster attribute=Z | save b.tif"
        )
        self.assertFalse(unknown)


if __name__ == "__main__":
    unittest.main()
