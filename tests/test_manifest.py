"""Tests for the machine-readable manifest + synonym map (`niva.manifest`,
`niva.registry.synonyms`; docs/planning/20 §7, issue #44). Pure Python, no QGIS.

Run: ``python -m unittest tests.test_manifest``.
"""

import json
import unittest

from niva.manifest import MANIFEST_VERSION, build_manifest
from niva.registry import synonyms as syn


class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = build_manifest()

    def test_shape(self):
        self.assertEqual(self.m["niva_manifest"], MANIFEST_VERSION)
        self.assertEqual(self.m["counts"]["aliases"], len(self.m["verbs"]))
        self.assertGreaterEqual(self.m["counts"]["aliases"], 40)
        self.assertIn("buffer", [v["name"] for v in self.m["verbs"]])
        self.assertIn("load", self.m["builtins"])

    def test_is_json_serializable(self):
        json.dumps(self.m)  # the whole point — IDEs/LLMs consume this

    def test_verb_entry_has_params_defaults_enums(self):
        buf = next(v for v in self.m["verbs"] if v["name"] == "buffer")
        self.assertEqual(buf["algorithm"], "native:buffer")
        by = {o["name"]: o for o in buf["options"]}
        self.assertEqual(by["segments"]["default"], "5")
        self.assertEqual(by["cap"]["enum"], ["flat", "round", "square"])
        self.assertTrue(buf["args"] and buf["args"][0]["required"])  # distance

    def test_synonyms_attached(self):
        collect = next(v for v in self.m["verbs"] if v["name"] == "collect")
        self.assertIn("merge", collect["synonyms"])

    def test_verb_without_synonyms_is_empty_list(self):
        # fixgeom has no curated synonym → an explicit empty list, never missing.
        fix = next(v for v in self.m["verbs"] if v["name"] == "fixgeom")
        self.assertEqual(fix["synonyms"], [])


class TestSynonyms(unittest.TestCase):
    def test_map_loads(self):
        self.assertIn("mosaic", syn.synonyms())

    def test_matches_resolves_intent(self):
        # 'mosaic' isn't a verb, but should surface the raster-merge algorithms.
        self.assertIn("gdal:merge", syn.matches("mosaic"))

    def test_by_target_inverts(self):
        self.assertIn("merge", syn.by_target().get("collect", []))

    def test_unknown_keyword_is_empty(self):
        self.assertEqual(syn.matches("zzz-not-a-thing"), [])


if __name__ == "__main__":
    unittest.main()
