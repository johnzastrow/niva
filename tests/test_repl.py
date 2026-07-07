"""Tests for the repl's manifest-driven tab completion (`niva.cli.repl.completions`). Pure
Python, no QGIS, no prompt_toolkit — the completion logic is a plain, testable function."""

import unittest

from niva.cli.repl import completions
from niva.manifest import build_manifest


def _verb(name):
    return next(v for v in build_manifest()["verbs"] if v["name"] == name)


class TestReplCompletion(unittest.TestCase):
    def test_stage_start_completes_verb_names(self):
        c = completions("buf")
        self.assertIn("buffer", c)
        self.assertTrue(all(x.startswith("buf") for x in c))

    def test_stage_start_includes_builtins(self):
        self.assertIn("load", completions("lo"))
        self.assertIn("save", completions("sa"))

    def test_after_pipe_completes_verbs(self):
        self.assertIn("buffer", completions("load a.gpkg | buf"))

    def test_after_verb_completes_its_options_and_flags(self):
        buf = _verb("buffer")
        c = set(completions("buffer "))  # trailing space → the verb's catalogue
        for o in buf["options"]:
            self.assertIn(f"{o['name']}=", c)  # options offered as `name=`
        for f in buf["flags"]:
            self.assertIn(f["name"], c)

    def test_option_prefix_filters(self):
        buf = _verb("buffer")
        opt = buf["options"][0]["name"]
        c = completions(f"buffer {opt[:2]}")
        self.assertTrue(all(x.startswith(opt[:2]) for x in c))
        self.assertIn(f"{opt}=", c)

    def test_enum_option_completes_values(self):
        buf = _verb("buffer")
        enum_opt = next((o for o in buf["options"] if o.get("enum")), None)
        if enum_opt is None:
            self.skipTest("buffer has no enum option to exercise")
        c = completions(f"buffer {enum_opt['name']}=")
        for val in enum_opt["enum"]:
            self.assertIn(f"{enum_opt['name']}={val}", c)

    def test_unknown_verb_offers_nothing(self):
        self.assertEqual(completions("definitelynotaverb "), [])


if __name__ == "__main__":
    unittest.main()
