"""Registry + binder tests (planning/07). Pure Python — no QGIS needed.

Each case parses a one-stage flow, looks the verb up in the core registry, binds
it, and checks the resulting ``processing.run`` params. Run with
``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva.errors import FlowError
from niva.grammar import parse
from niva.registry import bind, core_registry
from niva.values import Distance

REG = core_registry()


def bound(text):
    """Parse a single-stage flow and bind that stage against the core registry."""
    stage = parse(text)[0].stages[0]
    alias = REG.get(stage.verb)
    assert alias is not None, f"{stage.verb!r} is not a registered verb"
    return bind(stage, alias)


class TestRegistry(unittest.TestCase):
    def test_core_verbs_present(self):
        for verb in ("buffer", "clip", "reproject", "dissolve", "join", "zonalstats"):
            self.assertIn(verb, REG)
        self.assertIsNone(REG.get("load"))  # built-in, not an alias

    def test_no_duplicate_verbs(self):
        # core_registry() would raise on a duplicate; reaching here means it didn't.
        self.assertEqual(len(REG.verbs()), len(set(REG.verbs())))


class TestBinder(unittest.TestCase):
    # --- the full spread: positionals, flags, options, enums, defaults -------

    def test_buffer_full(self):
        op = bound("buffer 100m dissolve cap=flat segments=12")
        self.assertEqual(op.algorithm, "native:buffer")
        self.assertEqual(op.input_param, "INPUT")
        self.assertEqual(op.output_param, "OUTPUT")
        self.assertEqual(op.params["DISTANCE"], Distance(100.0, "m"))
        self.assertEqual(op.params["DISSOLVE"], True)
        self.assertEqual(op.params["SEPARATE_DISJOINT"], False)  # flag defaults False
        self.assertEqual(op.params["END_CAP_STYLE"], 1)          # flat -> 1
        self.assertEqual(op.params["JOIN_STYLE"], 0)             # default round -> 0
        self.assertEqual(op.params["SEGMENTS"], 12)
        self.assertEqual(op.params["MITER_LIMIT"], 2.0)          # default

    def test_buffer_defaults_only(self):
        op = bound("buffer 100")
        self.assertEqual(op.params["DISTANCE"], Distance(100.0, None))  # CRS units
        self.assertEqual(op.params["SEGMENTS"], 5)
        self.assertEqual(op.params["END_CAP_STYLE"], 0)
        self.assertEqual(op.params["DISSOLVE"], False)

    def test_distance_units(self):
        self.assertEqual(bound("buffer 2.5km").params["DISTANCE"], Distance(2.5, "km"))
        self.assertEqual(bound("buffer -10ft").params["DISTANCE"], Distance(-10.0, "ft"))

    def test_clip_positional_layer(self):
        op = bound("clip city.gpkg")
        self.assertEqual(op.algorithm, "native:clip")
        self.assertEqual(op.params["OVERLAY"], "city.gpkg")

    def test_reproject_crs_and_forced(self):
        op = bound("reproject EPSG:2262")
        self.assertEqual(op.params["TARGET_CRS"], "EPSG:2262")
        self.assertEqual(op.params["CONVERT_CURVED_GEOMETRIES"], False)  # forced

    def test_dissolve_optional_positional_omitted(self):
        op = bound("dissolve")
        self.assertNotIn("FIELD", op.params)        # optional positional, absent
        self.assertEqual(op.params["SEPARATE_DISJOINT"], False)
        self.assertEqual(bound("dissolve landuse").params["FIELD"], "landuse")

    def test_join_options_and_listvalue(self):
        op = bound("join with=census.csv field=tract field2=GEOID fields=pop,income prefix=cen_ discard")
        self.assertEqual(op.algorithm, "native:joinattributestable")
        self.assertEqual(op.params["INPUT_2"], "census.csv")
        self.assertEqual(op.params["FIELD"], "tract")
        self.assertEqual(op.params["FIELD_2"], "GEOID")
        self.assertEqual(op.params["FIELDS_TO_COPY"], ["pop", "income"])
        self.assertEqual(op.params["PREFIX"], "cen_")
        self.assertEqual(op.params["DISCARD_NONMATCHING"], True)
        self.assertEqual(op.params["METHOD"], 1)    # default one-to-one

    def test_zonalstats_enumlist(self):
        op = bound("zonalstats raster=dem.tif band=2 stats=mean,min,max prefix=elev_")
        self.assertEqual(op.params["INPUT_RASTER"], "dem.tif")
        self.assertEqual(op.params["RASTER_BAND"], 2)
        self.assertEqual(op.params["STATISTICS"], [2, 5, 6])   # mean,min,max
        self.assertEqual(op.params["COLUMN_PREFIX"], "elev_")

    def test_zonalstats_enumlist_default(self):
        op = bound("zonalstats raster=dem.tif")
        self.assertEqual(op.params["STATISTICS"], [0, 1, 2])   # count,sum,mean default

    # --- errors --------------------------------------------------------------

    def test_missing_required_positional(self):
        with self.assertRaises(FlowError):
            bound("buffer")            # no distance

    def test_too_many_positionals(self):
        with self.assertRaises(FlowError):
            bound("clip a.gpkg b.gpkg")

    def test_unknown_option(self):
        with self.assertRaises(FlowError):
            bound("buffer 100m colour=red")

    def test_bad_enum_word(self):
        with self.assertRaises(FlowError) as ctx:
            bound("buffer 100m cap=triangle")
        self.assertIn("round", str(ctx.exception))  # error lists valid words

    def test_missing_required_option(self):
        with self.assertRaises(FlowError):
            bound("join field=tract field2=GEOID")  # missing with=

    def test_bad_number(self):
        with self.assertRaises(FlowError):
            bound("buffer 100m segments=many")

    def test_bad_distance(self):
        with self.assertRaises(FlowError):
            bound("buffer wide")

    def test_unknown_unit(self):
        with self.assertRaises(FlowError) as ctx:
            bound("buffer 100furlongs")
        self.assertIn("unit", str(ctx.exception))

    def test_error_names_the_stage_line(self):
        # adjacent non-pipe lines are separate flows; the bad stage is on line 2.
        prog = parse("load x.gpkg | save y.gpkg\nbuffer 100m cap=triangle")
        bad = prog[1].stages[0]
        try:
            bind(bad, REG.get("buffer"))
        except FlowError as exc:
            self.assertEqual(exc.line, 2)
        else:
            self.fail("expected FlowError")


if __name__ == "__main__":
    unittest.main()
