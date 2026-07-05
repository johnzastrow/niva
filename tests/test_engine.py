"""Engine tests (docs/planning/05). Pure Python via MockBackend — no QGIS needed.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva.engine import CrsInfo, Engine, MockBackend
from niva.engine.layer import MEMORY, SOURCE
from niva.errors import FlowError
from niva.grammar import parse

PROJECTED_M = CrsInfo(
    "EPSG:3857", is_geographic=False, units_to_meters=1.0, map_units="meters"
)
PROJECTED_FT = CrsInfo(
    "EPSG:2262", is_geographic=False, units_to_meters=0.3048, map_units="feet"
)
GEOGRAPHIC = CrsInfo("EPSG:4326", is_geographic=True, map_units="degrees")


def run(text, crs=PROJECTED_M):
    backend = MockBackend(crs=crs)
    result = Engine(backend).execute(parse(text))
    return backend, result


class TestSaveCreatesParentDir(unittest.TestCase):
    def test_save_makes_nested_parent(self):
        import os
        import tempfile

        tmp = tempfile.mkdtemp(prefix="niva_save_")
        dest = os.path.join(tmp, "a", "b", "c", "out.gpkg")
        run(f'load roads.gpkg | buffer 100m | save "{dest}"')
        self.assertTrue(
            os.path.isdir(os.path.dirname(dest)),
            "save should create the target's parent directory",
        )


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
        backend, _ = run('load a.gpkg | filter "pop > 100" | save b.gpkg')
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
        self.assertAlmostEqual(
            self._distance("load a | buffer 100m", PROJECTED_FT), 328.0839895, places=4
        )

    def test_feet_on_metre_crs(self):
        self.assertAlmostEqual(
            self._distance("load a | buffer 100ft", PROJECTED_M), 30.48, places=6
        )

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


class TestRunEscapeHatch(unittest.TestCase):
    def test_run_passes_algorithm_and_scalar_coerced_params(self):
        backend, _ = run("load dem.tif | run native:slope Z_FACTOR=2 | save slope.tif")
        run_call = next(c for c in backend.calls if c[0] == "run")
        self.assertEqual(run_call[1], "native:slope")
        self.assertEqual(run_call[2], {"Z_FACTOR": 2})  # "2" coerced to int

    def test_run_coerces_float_bool_keeps_strings(self):
        backend, _ = run(
            "load a | run x:y RES=1.5 FLAG=true CRS=EPSG:2262 PATH=a/b.tif"
        )
        params = next(c for c in backend.calls if c[0] == "run")[2]
        self.assertEqual(params["RES"], 1.5)
        self.assertIs(params["FLAG"], True)
        self.assertEqual(params["CRS"], "EPSG:2262")  # not a number → string
        self.assertEqual(params["PATH"], "a/b.tif")

    def test_run_standalone_then_pipe(self):
        # run can start a flow (no upstream) and feed the next stage
        backend, _ = run("run native:something INPUT=a.gpkg | buffer 5m | save o.gpkg")
        kinds = [c[0] for c in backend.calls]
        self.assertEqual(kinds, ["run", "run", "save"])

    def test_run_requires_algorithm(self):
        with self.assertRaises(FlowError):
            run("load a | run")

    def test_run_rejects_extra_positional(self):
        with self.assertRaises(FlowError):
            run("load a | run native:slope native:aspect")

    def test_run_semicolon_value_becomes_list(self):
        # multilayer params (e.g. gdal:merge INPUT) need a list — `;` splits it
        backend, _ = run(
            'run gdal:merge INPUT="a.tif;b.tif;c.tif" DATA_TYPE=5 | save x.tif'
        )
        params = next(c for c in backend.calls if c[0] == "run")[2]
        self.assertEqual(params["INPUT"], ["a.tif", "b.tif", "c.tif"])
        self.assertEqual(params["DATA_TYPE"], 5)

    def test_run_glob_expands_to_sorted_files(self):
        import os
        import tempfile

        d = tempfile.mkdtemp()
        for name in ("b.jp2", "a.jp2", "c.tif"):  # c.tif must NOT match *.jp2
            open(os.path.join(d, name), "w").close()
        backend, _ = run(
            f'run gdal:buildvirtualraster INPUT="{d}/*.jp2" OUTPUT=/tmp/x.vrt'
        )
        params = next(c for c in backend.calls if c[0] == "run")[2]
        self.assertEqual(
            params["INPUT"], [os.path.join(d, "a.jp2"), os.path.join(d, "b.jp2")]
        )

    def test_run_glob_no_match_is_error(self):
        with self.assertRaises(FlowError) as ctx:
            run('run x:y INPUT="/no/such/dir/*.jp2"')
        self.assertIn("no files match", str(ctx.exception))

    def test_run_does_not_glob_an_expression(self):
        backend, _ = run('load a | run native:fieldcalculator FORMULA="area * 2"')
        params = next(c for c in backend.calls if c[0] == "run")[2]
        self.assertEqual(
            params["FORMULA"], "area * 2"
        )  # `*` in an expression is left alone

    def test_run_does_not_glob_a_compact_expression(self):
        # No spaces AND no path separator (e.g. FORMULA="A*1.0", "(A<0.2)*1") — used to be
        # mistaken for a bare glob and error with "no files match"; must pass through as a
        # literal since nothing matches and there's no path separator.
        for formula in ("A*1.0", "(A<0.20)&(B<0.0)*1", "A*tan(B*0.0174533)"):
            backend, _ = run(
                f'run gdal:rastercalculator FORMULA="{formula}" INPUT_A=dem.tif OUTPUT=o.tif'
            )
            params = next(c for c in backend.calls if c[0] == "run")[2]
            self.assertEqual(params["FORMULA"], formula)

    def test_load_expands_home(self):
        import os

        backend, _ = run("load ~/foo.gpkg | save out.gpkg")
        self.assertEqual(backend.calls[0], ("load", os.path.expanduser("~/foo.gpkg")))

    def test_explode_alias(self):
        backend, _ = run("load roads.gpkg | explode | save e.gpkg")
        self.assertEqual(backend.calls[1][1], "native:multiparttosingleparts")


class TestMetadata(unittest.TestCase):
    def test_metadata_set_passes_fields_and_is_passthrough(self):
        backend, _ = run(
            'load a.gpkg | metadata set title="Cats" keywords=a,b abstract="x" | save o.gpkg'
        )
        meta = next(c for c in backend.calls if c[0] == "metadata")
        self.assertEqual(meta[1], {"title": "Cats", "keywords": "a,b", "abstract": "x"})
        self.assertEqual([c[0] for c in backend.calls], ["load", "metadata", "save"])

    def test_metadata_needs_a_layer(self):
        with self.assertRaises(FlowError):
            run('metadata set title="x"')

    def test_metadata_requires_set_subcommand(self):
        with self.assertRaises(FlowError):
            run("load a | metadata get")

    def test_metadata_requires_fields(self):
        with self.assertRaises(FlowError):
            run("load a | metadata set")

    def test_metadata_rejects_unknown_field(self):
        with self.assertRaises(FlowError) as ctx:
            run("load a | metadata set colour=red")
        self.assertIn("colour", str(ctx.exception))


class TestAssess(unittest.TestCase):
    def _assess(self, flow, fname):
        import os
        import tempfile

        d = tempfile.mkdtemp(prefix="niva_assess_")
        path = os.path.join(d, fname)
        backend = MockBackend()
        Engine(backend).execute(parse(flow.format(path=path)))
        with open(path, encoding="utf-8") as fh:
            return backend, fh.read()

    def test_assess_writes_report_and_is_passthrough(self):
        backend, report = self._assess(
            "load a.gpkg | assess to {path} | save o.gpkg", "r.md"
        )
        self.assertEqual([c[0] for c in backend.calls], ["load", "assess", "save"])
        self.assertIn("# Data quality assessment", report)
        self.assertIn("Features:", report)
        self.assertIn("EPSG:3857", report)
        self.assertIn("| id | Integer |", report)
        self.assertNotIn("## Quality checks", report)  # not deep

    def test_assess_deep_adds_quality_section(self):
        backend, report = self._assess("load a.gpkg | assess deep to {path}", "d.md")
        self.assertTrue(backend.calls[-1] == ("assess", "a.gpkg", True))
        self.assertIn("## Quality checks", report)
        self.assertIn("Invalid geometries:", report)
        self.assertIn("Duplicate geometries:", report)

    def test_assess_dashdeep_also_works(self):
        backend, _ = self._assess("load a.gpkg | assess --deep to {path}", "d2.md")
        self.assertTrue(backend.calls[-1][2] is True)

    def test_assess_needs_to_destination(self):
        with self.assertRaises(FlowError):
            run("load a | assess")

    def test_assess_needs_a_layer(self):
        with self.assertRaises(FlowError):
            run("assess to r.md")

    def test_assess_emits_report_path_to_the_dock(self):
        # The report write must be visible in the plugin/CLI, not silent (it used to be).
        import os
        import tempfile

        path = os.path.join(tempfile.mkdtemp(prefix="niva_assess_"), "r.md")
        msgs = []
        Engine(MockBackend(), progress=msgs.append).execute(
            parse(f"load a.gpkg | assess to {path}")
        )
        self.assertTrue(any(m.strip() == f"assessment → {path}" for m in msgs), msgs)


class TestDescribeVerb(unittest.TestCase):
    """`describe` is a terminal flow verb (so it works in the plugin dock), in addition
    to the `niva describe` CLI subcommand."""

    def _run(self, text):
        msgs = []
        result = Engine(MockBackend(), progress=msgs.append).execute(parse(text))
        return result, msgs

    def test_describe_a_verb_streams_the_report_and_is_terminal(self):
        result, msgs = self._run("describe buffer")
        self.assertIsNone(result)  # terminal — no pipeable layer
        body = "\n".join(msgs)
        self.assertIn("buffer", body)
        self.assertIn("→", body)  # the alias→algorithm mapping line

    def test_describe_to_file_writes_and_emits_path(self):
        import os
        import tempfile

        path = os.path.join(tempfile.mkdtemp(prefix="niva_describe_"), "buffer.md")
        _result, msgs = self._run(f"describe buffer to={path}")
        with open(path, encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("buffer", report)
        self.assertTrue(any(m.strip() == f"description → {path}" for m in msgs), msgs)

    def test_describe_requires_exactly_one_target(self):
        with self.assertRaises(FlowError):
            run("describe")
        with self.assertRaises(FlowError):
            run("describe buffer clip")

    def test_describe_rejects_unknown_options(self):
        with self.assertRaises(FlowError):
            run("describe buffer bogus=1")

    def test_describe_unknown_name_is_a_flow_error(self):
        with self.assertRaises(FlowError):
            run("describe frobnicate")


class TestStyleAndMetadataEmit(unittest.TestCase):
    """Pass-through verbs still confirm their action in the dock/CLI."""

    def _msgs(self, text):
        msgs = []
        Engine(MockBackend(), progress=msgs.append).execute(parse(text))
        return msgs

    def test_style_save_confirms(self):
        msgs = self._msgs("load a.gpkg | style save out.qml")
        self.assertTrue(any("style saved → out.qml" in m for m in msgs), msgs)

    def test_metadata_set_confirms(self):
        msgs = self._msgs('load a.gpkg | metadata set title="Roads"')
        self.assertTrue(any(m.strip().startswith("metadata set:") for m in msgs), msgs)


class TestLineage(unittest.TestCase):
    @staticmethod
    def _texts(lineage):
        # each entry is "<ISO-timestamp> <stage text>"; strip the timestamp prefix
        return [e.split(" ", 1)[1] for e in lineage]

    def test_save_receives_build_lineage(self):
        backend, _ = run(
            "load roads.gpkg | reproject EPSG:2262 | buffer 100m dissolve | save out.gpkg"
        )
        self.assertEqual(
            self._texts(backend.last_lineage),
            ["load roads.gpkg", "reproject EPSG:2262", "buffer 100m dissolve"],
        )
        # entries are timestamped (ISO 8601, starts with a year)
        self.assertRegex(backend.last_lineage[0], r"^20\d\d-\d\d-\d\dT")

    def test_lineage_excludes_the_save_stage_itself(self):
        backend, _ = run("load a.gpkg | save b.gpkg")
        self.assertEqual(self._texts(backend.last_lineage), ["load a.gpkg"])

    def test_second_save_accumulates_intermediate_stages(self):
        backend, _ = run(
            "load a.gpkg | save b.gpkg\n\nload c.gpkg | buffer 5m | save d.gpkg"
        )
        # last_lineage reflects the most recent save (second flow)
        self.assertEqual(
            self._texts(backend.last_lineage), ["load c.gpkg", "buffer 5m"]
        )


class TestProgress(unittest.TestCase):
    def test_emits_a_stage_start_event_per_stage(self):
        from niva import flow

        msgs = []
        flow(
            "load a.gpkg | buffer 100m dissolve | save out.gpkg",
            backend=MockBackend(),
            progress=msgs.append,
        )
        self.assertEqual(
            [m for m in msgs if m.startswith("▶")],
            ["▶ load a.gpkg", "▶ buffer 100m dissolve", "▶ save out.gpkg"],
        )

    def test_no_progress_callback_is_fine(self):
        from niva import flow

        flow(
            "load a.gpkg | save b.gpkg", backend=MockBackend()
        )  # progress=None → no-op

    def test_emits_elapsed_after_each_stage(self):
        from niva import flow

        msgs = []
        flow(
            "load a.gpkg | buffer 5m | save b.gpkg",
            backend=MockBackend(),
            progress=msgs.append,
        )
        done = [m for m in msgs if m.strip().startswith("✓")]
        self.assertEqual(len(done), 3)  # one ✓ per stage, with its elapsed

    def test_accepts_cancel_callback(self):
        from niva import flow

        # cancel is a real-QGIS abort hook; with the mock it must just be a no-op
        flow("load a.gpkg | save b.gpkg", backend=MockBackend(), cancel=lambda: False)


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

    def test_conn_ref_as_secondary_layer_is_loaded(self):
        # A @conn.table used as a secondary layer (clip's overlay) is loaded via the backend,
        # not passed through as a bogus string. (MockBackend resolves "pg" by longest prefix.)
        backend, _ = run("load roads.gpkg | clip @pg.public.zones")
        self.assertIn(("load_table", "pg", "public", "zones"), backend.calls)

    def test_bare_conn_as_layer_is_a_flow_error(self):
        with self.assertRaises(FlowError):
            run("load roads.gpkg | clip @pg")  # bare connection, no table

    def test_unknown_crs_fails_closed(self):
        # An unrecognised CRS must raise (not silently produce an empty-CRS layer). MockBackend
        # treats a ≥6-digit EPSG code as invalid; a real code passes.
        with self.assertRaises(FlowError) as ctx:
            run("load roads.gpkg | reproject EPSG:999999 | save out.gpkg")
        self.assertIn("not a recognised CRS", str(ctx.exception))
        backend, _ = run("load roads.gpkg | reproject EPSG:6346 | save out.gpkg")
        self.assertTrue(any(c[0] == "run" for c in backend.calls))

    def test_save_mode_on_a_file_is_a_guiding_error(self):
        # `mode=append` is database-only; on a file the error should point at `as <layer>`.
        with self.assertRaises(FlowError) as ctx:
            run("load a.gpkg | save out.gpkg mode=append")
        msg = str(ctx.exception)
        self.assertIn("database", msg)
        self.assertIn("as <layer>", msg)

    def test_load_arity(self):
        with self.assertRaises(FlowError):
            run("load a.gpkg b.gpkg")

    def test_call_not_executed_yet(self):
        with self.assertRaises(FlowError) as ctx:
            Engine(MockBackend()).execute(parse("call acquire.niva"))
        self.assertIn("call", str(ctx.exception))

    def test_error_names_the_line(self):
        try:
            run(
                "load a.gpkg | save out.gpkg\n\nload b.gpkg | buffer 10m\n  | frobnicate"
            )
        except FlowError as exc:
            self.assertEqual(exc.line, 3)  # the frobnicate flow starts on line 3
        else:
            self.fail("expected FlowError")


if __name__ == "__main__":
    unittest.main()
