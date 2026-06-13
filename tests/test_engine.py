"""Engine tests (planning/05). Pure Python via MockBackend — no QGIS needed.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva.engine import CrsInfo, Engine, MockBackend
from niva.engine.layer import MEMORY, SOURCE
from niva.errors import FlowError
from niva.grammar import parse

PROJECTED_M = CrsInfo("EPSG:3857", is_geographic=False, units_to_meters=1.0, map_units="meters")
PROJECTED_FT = CrsInfo("EPSG:2262", is_geographic=False, units_to_meters=0.3048, map_units="feet")
GEOGRAPHIC = CrsInfo("EPSG:4326", is_geographic=True, map_units="degrees")


def run(text, crs=PROJECTED_M):
    backend = MockBackend(crs=crs)
    result = Engine(backend).execute(parse(text))
    return backend, result


class TestPipeline(unittest.TestCase):
    def test_load_op_save_threads_the_layer(self):
        backend, result = run("load roads.gpkg | buffer 100m | save out.gpkg")
        kinds = [c[0] for c in backend.calls]
        self.assertEqual(kinds, ["load", "run", "save"])
        # the buffer ran on native:buffer; result is the saved file handle
        self.assertEqual(backend.calls[1][1], "native:buffer")
        self.assertEqual(result.kind, SOURCE)
        self.assertEqual(result.ref, "out.gpkg")

    def test_intermediate_result_is_memory(self):
        backend, result = run("load a.gpkg | buffer 5m")
        self.assertEqual(result.kind, MEMORY)

    def test_filter_routes_as_alias(self):
        backend, _ = run("load a.gpkg | filter \"pop > 100\" | save b.gpkg")
        self.assertEqual(backend.calls[1][1], "native:extractbyexpression")
        self.assertEqual(backend.calls[1][2]["EXPRESSION"], "pop > 100")

    def test_multi_flow_returns_last(self):
        _, result = run("load a.gpkg | save b.gpkg\n\nload c.gpkg | save d.gpkg")
        self.assertEqual(result.ref, "d.gpkg")


class TestDistanceResolution(unittest.TestCase):
    def _distance(self, text, crs):
        backend, _ = run(text, crs=crs)
        return backend.calls[1][2]["DISTANCE"]

    def test_metres_on_metre_crs(self):
        self.assertEqual(self._distance("load a | buffer 100m", PROJECTED_M), 100.0)

    def test_metres_on_feet_crs(self):
        # 100 m expressed in a feet CRS = 100 / 0.3048 ≈ 328.08 ft
        self.assertAlmostEqual(self._distance("load a | buffer 100m", PROJECTED_FT), 328.0839895, places=4)

    def test_feet_on_metre_crs(self):
        self.assertAlmostEqual(self._distance("load a | buffer 100ft", PROJECTED_M), 30.48, places=6)

    def test_kilometres(self):
        self.assertEqual(self._distance("load a | buffer 2km", PROJECTED_M), 2000.0)

    def test_bare_number_is_crs_units(self):
        # No unit: trusted as-is even on a feet CRS (no conversion).
        self.assertEqual(self._distance("load a | buffer 50", PROJECTED_FT), 50.0)

    def test_degrees_on_geographic(self):
        self.assertEqual(self._distance("load a | buffer 0.5deg", GEOGRAPHIC), 0.5)

    def test_linear_on_geographic_is_error(self):
        with self.assertRaises(FlowError) as ctx:
            run("load a | buffer 100m", crs=GEOGRAPHIC)
        msg = str(ctx.exception)
        self.assertIn("degrees", msg)
        self.assertIn("reproject", msg.lower())

    def test_degrees_on_projected_is_error(self):
        with self.assertRaises(FlowError):
            run("load a | buffer 0.5deg", crs=PROJECTED_M)


class TestErrors(unittest.TestCase):
    def test_unknown_verb(self):
        with self.assertRaises(FlowError) as ctx:
            run("load a | frobnicate")
        self.assertIn("frobnicate", str(ctx.exception))

    def test_op_before_load(self):
        with self.assertRaises(FlowError) as ctx:
            run("buffer 100m | save out.gpkg")
        self.assertIn("load", str(ctx.exception))

    def test_save_with_nothing(self):
        with self.assertRaises(FlowError):
            run("save out.gpkg")

    def test_load_arity(self):
        with self.assertRaises(FlowError):
            run("load a.gpkg b.gpkg")

    def test_call_not_executed_yet(self):
        with self.assertRaises(FlowError) as ctx:
            Engine(MockBackend()).execute(parse("call acquire.niva"))
        self.assertIn("call", str(ctx.exception))

    def test_error_names_the_line(self):
        try:
            run("load a.gpkg | save out.gpkg\n\nload b.gpkg | buffer 10m\n  | frobnicate")
        except FlowError as exc:
            self.assertEqual(exc.line, 3)  # the frobnicate flow starts on line 3
        else:
            self.fail("expected FlowError")


if __name__ == "__main__":
    unittest.main()
