"""Tests for the resolved-plan IR (`niva.plan`, docs/planning/20 §3). Pure Python, no QGIS.

Run: ``python -m unittest tests.test_plan``.
"""

import json
import unittest

from niva.grammar import parse
from niva.plan import PLAN_VERSION, build_plan


def plan(flow):
    return build_plan(parse(flow))


class TestPlanShape(unittest.TestCase):
    def test_top_level_fields(self):
        p = plan("load a.gpkg | buffer 100m | save b.gpkg")
        self.assertEqual(p["niva_plan"], PLAN_VERSION)
        self.assertIn("niva_version", p)
        self.assertEqual(len(p["steps"]), 3)
        self.assertIn("diagnostics", p)

    def test_is_json_serializable(self):
        p = plan(
            "load a.gpkg | reproject EPSG:6346 | buffer 100m dissolve | save b.gpkg"
        )
        json.dumps(p)  # must not raise — the whole point of an IR

    def test_step_ids_are_sequential(self):
        p = plan("load a.gpkg | buffer 100m | save b.gpkg")
        self.assertEqual([s["id"] for s in p["steps"]], [1, 2, 3])


class TestResolution(unittest.TestCase):
    def test_alias_resolves_to_algorithm(self):
        p = plan("load a.gpkg | buffer 100m dissolve | save b.gpkg")
        buf = p["steps"][1]
        self.assertEqual(buf["op"], "buffer")
        self.assertEqual(buf["kind"], "alias")
        self.assertEqual(buf["algorithm"], "native:buffer")
        self.assertTrue(buf["params"]["DISSOLVE"])

    def test_distance_is_value_unit(self):
        buf = plan("load a.gpkg | buffer 100m | save b.gpkg")["steps"][1]
        self.assertEqual(buf["params"]["DISTANCE"], {"value": 100.0, "unit": "m"})

    def test_injected_defaults_captured(self):
        # SEGMENTS wasn't typed — it must show up as an injected default (reproducibility).
        buf = plan("load a.gpkg | buffer 100m | save b.gpkg")["steps"][1]
        self.assertIn("SEGMENTS", buf["injected_defaults"])
        self.assertEqual(buf["injected_defaults"]["SEGMENTS"], 5)

    def test_user_param_is_not_injected(self):
        buf = plan("load a.gpkg | buffer 100m segments=12 | save b.gpkg")["steps"][1]
        self.assertEqual(buf["params"]["SEGMENTS"], 12)
        self.assertNotIn("SEGMENTS", buf["injected_defaults"])

    def test_run_id_passthrough(self):
        s = plan(
            "load t.las | run pdal:exportraster ATTRIBUTE=Z RESOLUTION=1 | save r.tif"
        )
        run = s["steps"][1]
        self.assertEqual(run["kind"], "run")
        self.assertEqual(run["algorithm"], "pdal:exportraster")
        self.assertEqual(run["params"], {"ATTRIBUTE": "Z", "RESOLUTION": "1"})

    def test_builtin_has_no_algorithm(self):
        load = plan("load a.gpkg | buffer 100m | save b.gpkg")["steps"][0]
        self.assertEqual(load["kind"], "builtin")
        self.assertIsNone(load["algorithm"])
        self.assertEqual(load["params"]["args"], ["a.gpkg"])


class TestDataFlowAndDiagnostics(unittest.TestCase):
    def test_linear_inputs(self):
        p = plan("load a.gpkg | buffer 100m | save b.gpkg")
        self.assertEqual(p["steps"][0]["inputs"], [])  # load has no upstream
        self.assertEqual(p["steps"][1]["inputs"], [1])  # buffer ← load
        self.assertEqual(p["steps"][2]["inputs"], [2])  # save ← buffer

    def test_diagnostics_are_carried(self):
        p = plan("load a.gpkg | compute x=1 | save b.gpkg")  # invalid verb
        self.assertTrue(any(d["severity"] == "error" for d in p["diagnostics"]))

    def test_requires_qgis_true_for_data_flow(self):
        self.assertTrue(
            plan("load a.gpkg | buffer 100m | save b.gpkg")["requires_qgis"]
        )

    def test_requires_qgis_false_for_pure_offline(self):
        self.assertFalse(plan("describe buffer")["requires_qgis"])


if __name__ == "__main__":
    unittest.main()
