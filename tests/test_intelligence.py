"""niva.intelligence — the shared language-services core (completion + diagnostics) used by the
repl and the LSP. QGIS-free."""

import unittest

from niva import intelligence as intel


class TestCompletions(unittest.TestCase):
    def test_stage_start_offers_verbs(self):
        self.assertIn("load", intel.completions("lo"))

    def test_after_verb_offers_options_and_paths(self):
        cands = intel.completions("load a.gpkg | buffer ")
        self.assertIn("dissolve", cands)  # a flag on buffer

    def test_enum_values(self):
        self.assertEqual(
            [
                c
                for c in intel.completions("load a.gpkg | buffer 5m cap=")
                if c.startswith("cap=")
            ],
            ["cap=flat", "cap=round", "cap=square"],
        )

    def test_unknown_verb_offers_nothing(self):
        self.assertEqual(intel.completions("notaverb "), [])

    def test_run_completes_algorithm_ids(self):
        self.assertIn("native:buffer", intel.completions("run native:buf"))
        self.assertTrue(all(":" in c for c in intel.completions("run nat")[:5]))
        # bare `run ` offers ids, not filesystem paths
        first = intel.completions("run ")
        self.assertTrue(first and all(":" in c for c in first[:5]))

    def test_run_completes_params_then_enum_values(self):
        params = intel.completions("run native:buffer ")
        self.assertIn("INPUT=", params)
        self.assertIn("DISTANCE=", params)
        self.assertEqual(
            intel.completions("run native:buffer END_CAP_STYLE="),
            ["END_CAP_STYLE=Round", "END_CAP_STYLE=Flat", "END_CAP_STYLE=Square"],
        )

    def test_run_completion_works_mid_pipe(self):
        self.assertIn(
            "gdal:warpreproject", intel.completions("load x.tif | run gdal:war")
        )

    def test_current_token(self):
        self.assertEqual(intel.current_token("load a.gpkg | buf"), "buf")
        self.assertEqual(intel.current_token("load a.gpkg | "), "")


class TestDiagnostics(unittest.TestCase):
    def test_unknown_verb_is_an_error_with_line(self):
        diags = intel.diagnostics("load a.gpkg | save b.gpkg\nload c.gpkg | bufffer 5m")
        errs = [d for d in diags if d["severity"] == "error"]
        self.assertTrue(errs)
        self.assertEqual(errs[0]["line"], 2)  # the error is on the second flow

    def test_clean_flow_has_no_errors(self):
        diags = intel.diagnostics("load a.gpkg | buffer 100m | save b.gpkg")
        self.assertEqual([d for d in diags if d["severity"] == "error"], [])

    def test_empty_text_is_clean(self):
        self.assertEqual(intel.diagnostics("   "), [])


if __name__ == "__main__":
    unittest.main()
