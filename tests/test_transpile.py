"""Tests for .niva <-> .py transpilation (niva/transpile.py). No QGIS needed —
export is static (grammar + binder) and import is ast-based."""

import ast
import unittest

from niva.transpile import export_script, import_script


class TestExport(unittest.TestCase):
    def test_export_is_valid_python(self):
        py = export_script('load "a.gpkg" | buffer 100m | save "out.gpkg"')
        ast.parse(py)  # raises if invalid

    def test_export_threads_input_output_and_save(self):
        py = export_script(
            'load "a.gpkg" | buffer 100m | run native:centroids '
            'ALL_PARTS=true | save "out.gpkg"'
        )
        # curated verb resolves to its algorithm with resolved params
        self.assertIn("processing.run('native:buffer'", py)
        self.assertIn("'INPUT': 'a.gpkg'", py)
        # the centroids step is piped from the buffer step's output var
        self.assertIn("'INPUT': step1", py)
        # the save destination becomes the final stage's OUTPUT
        self.assertIn("'OUTPUT': 'out.gpkg'", py)

    def test_multiple_flows_get_distinct_vars_and_keep_explicit_output(self):
        # Two independent `run` statements (separate flows). Each must get its own
        # step variable, and an explicit OUTPUT= must NOT be replaced by a temp sink.
        flow = (
            'run gdal:buildvirtualraster INPUT="t/*.tif" OUTPUT=/tmp/m.vrt SEPARATE=False\n'
            'run gdal:translate INPUT=/tmp/m.vrt OUTPUT=/tmp/m.tif OPTIONS="QUALITY=25"'
        )
        py = export_script(flow)
        self.assertIn("step1 = processing.run('gdal:buildvirtualraster'", py)
        self.assertIn("step2 = processing.run('gdal:translate'", py)
        self.assertIn("'OUTPUT': '/tmp/m.vrt'", py)  # explicit output preserved
        self.assertIn("'OUTPUT': '/tmp/m.tif'", py)
        self.assertNotIn("TEMPORARY_OUTPUT", py)  # nothing got clobbered to a temp sink

        niva, warnings = import_script(py)
        self.assertEqual(warnings, [])
        self.assertIn("OUTPUT=/tmp/m.vrt", niva)  # survives the round-trip
        self.assertIn("OUTPUT=/tmp/m.tif", niva)

    def test_export_run_escape_hatch_is_verbatim(self):
        py = export_script(
            'run gdal:translate INPUT=in.vrt OUTPUT=out.jp2 OPTIONS="QUALITY=25"'
        )
        self.assertIn("processing.run('gdal:translate'", py)
        self.assertIn("'OPTIONS': 'QUALITY=25'", py)

    def test_export_header_warns_about_reimport_limits(self):
        py = export_script('load "a.gpkg" | save "b.gpkg"')
        self.assertIn("Arbitrary PyQGIS scripts CANNOT be imported", py)

    def test_export_notes_unconverted_verbs(self):
        py = export_script('load "a.gpkg" | assess')
        self.assertIn("has no processing.run equivalent", py)


class TestImport(unittest.TestCase):
    def test_import_linear_processing_run(self):
        py = (
            "import processing\n"
            "r1 = processing.run('native:buffer', {'INPUT': 'a.gpkg', 'DISTANCE': 5, "
            "'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']\n"
            "r2 = processing.run('native:centroids', {'INPUT': r1, "
            "'OUTPUT': 'out.gpkg'})['OUTPUT']\n"
        )
        niva, warnings = import_script(py)
        self.assertEqual(warnings, [])
        lines = niva.strip().splitlines()
        # an explicit literal INPUT stays on the run line (faithful for files/globs)
        self.assertEqual(lines[0], "run native:buffer INPUT=a.gpkg DISTANCE=5")
        self.assertNotIn("TEMPORARY_OUTPUT", niva)  # temp sink dropped
        self.assertNotIn("INPUT=r1", niva)  # the pipe is implicit
        self.assertIn("OUTPUT=out.gpkg", lines[1])

    def test_round_trip_export_then_import(self):
        original = (
            'load "a.gpkg" | run native:buffer DISTANCE=5 | '
            'run native:centroids ALL_PARTS=true | save "out.gpkg"'
        )
        py = export_script(original)
        niva, warnings = import_script(py)
        self.assertEqual(warnings, [])
        self.assertIn("run native:buffer", niva)
        self.assertIn("run native:centroids", niva)
        self.assertIn("ALL_PARTS=true", niva)

    def test_edit_exported_py_then_import_picks_up_new_params(self):
        # A user exports, hand-edits the .py to add/change processing.run params,
        # then re-imports — the edits must flow back into the .niva.
        py = export_script(
            'load "a.gpkg" | run native:buffer DISTANCE=5 | save "out.gpkg"'
        )
        self.assertNotIn("SEGMENTS", py)  # not in the original flow

        # add SEGMENTS and JOIN_STYLE, and change DISTANCE, as a user would by hand
        edited = py.replace(
            "'DISTANCE': 5", "'DISTANCE': 12, 'SEGMENTS': 24, 'JOIN_STYLE': 1"
        )
        ast.parse(edited)  # still valid Python after the edit

        niva, warnings = import_script(edited)
        self.assertEqual(warnings, [])
        buf = [ln for ln in niva.splitlines() if "native:buffer" in ln][0]
        self.assertIn("DISTANCE=12", buf)  # changed value carried through
        self.assertIn("SEGMENTS=24", buf)  # added param carried through
        self.assertIn("JOIN_STYLE=1", buf)  # added param carried through

    def test_add_whole_new_processing_step_then_import(self):
        # Insert an entirely new processing.run step into the exported script,
        # piped from the previous one, and confirm it imports as a new `run` stage.
        py = export_script(
            'load "a.gpkg" | run native:buffer DISTANCE=5 | save "out.gpkg"'
        )
        new_step = (
            "    step9 = processing.run('native:dissolve', "
            "{'INPUT': step1, 'FIELD': ['region'], 'OUTPUT': 'out.gpkg'})['OUTPUT']\n"
        )
        # splice the new step in just before `return`
        edited = py.replace("    return step1", new_step + "    return step9")
        ast.parse(edited)

        niva, warnings = import_script(edited)
        self.assertEqual(warnings, [])
        self.assertIn("run native:dissolve", niva)
        self.assertIn("FIELD=", niva)
        self.assertNotIn("INPUT=step1", niva)  # piped from step1 -> implicit in niva

    def test_added_param_referencing_a_variable_is_flagged(self):
        # If an added param's value is a bare variable (not a literal), import keeps
        # it but warns the user to check the wiring — it can't be a clean niva value.
        py = export_script("run native:buffer DISTANCE=5")
        edited = py.replace("'DISTANCE': 5", "'DISTANCE': 5, 'EXTRA': some_var")
        niva, warnings = import_script(edited)
        self.assertTrue(any("some_var" in w for w in warnings))
        self.assertIn("EXTRA=some_var", niva)

    def test_import_flags_control_flow(self):
        py = "for i in range(3):\n    print(i)\n"
        niva, warnings = import_script(py)
        self.assertEqual(niva, "")
        self.assertTrue(any("cannot import" in w for w in warnings))

    def test_import_flags_non_literal_params(self):
        py = (
            "import processing\n"
            "params = {'INPUT': 'a'}\n"
            "processing.run('native:buffer', params)\n"
        )
        niva, warnings = import_script(py)
        # the dict is a Name, not a literal -> not importable, reported
        self.assertTrue(any("non-literal" in w for w in warnings))

    def test_import_of_invalid_python_is_reported(self):
        niva, warnings = import_script("def (:\n")
        self.assertEqual(niva, "")
        self.assertTrue(any("not valid Python" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()


class TestGeometryTypeErrorMatcher(unittest.TestCase):
    """The collection-safe reproject fallback triggers on this specific QGIS error."""

    def test_matches_typed_sink_rejection(self):
        from niva.engine.pyqgis import _is_geometry_type_error as m

        self.assertTrue(
            m(
                Exception(
                    "Could not add feature with geometry type "
                    "GeometryCollection to layer of type MultiPolygon"
                )
            )
        )

    def test_ignores_unrelated_errors(self):
        from niva.engine.pyqgis import _is_geometry_type_error as m

        self.assertFalse(m(Exception("connection refused")))
        self.assertFalse(m(Exception("Could not write feature")))  # no 'geometry type'
