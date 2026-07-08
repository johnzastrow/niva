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
