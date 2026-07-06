"""Fuzzy `search`/`docs` tests — pure (no QGIS). The live algorithm catalog is supplied
explicitly so ranking is exercised without bootstrapping QGIS."""

import unittest

from niva.search import format_docs, format_results, search

# A small fake live catalog, shaped like backend.algorithm_catalog().
CATALOG = [
    {
        "id": "native:buffer",
        "display_name": "Buffer",
        "group": "Vector geometry",
        "description": "Computes a buffer around features.",
    },
    {
        "id": "gdal:warpreproject",
        "display_name": "Warp (reproject)",
        "group": "Raster projections",
        "description": "Reprojects a raster into another CRS.",
    },
    {
        "id": "native:slope",
        "display_name": "Slope",
        "group": "Raster terrain analysis",
        "description": "Slope of a DEM in degrees.",
    },
]


class TestSearchRanking(unittest.TestCase):
    def _names(self, query, **kw):
        return [h.name for h in search(query, **kw)]

    def test_exact_verb_ranks_first(self):
        hits = search("buffer", algorithms=CATALOG)
        self.assertEqual(hits[0].name, "buffer")
        self.assertEqual(hits[0].kind, "verb")
        self.assertEqual(hits[0].score, 1.0)

    def test_fuzzy_typo_still_matches(self):
        # a transposed/typo'd query should still surface the verb (difflib ratio)
        self.assertIn("buffer", self._names("buffer", algorithms=CATALOG))
        self.assertIn("reproject", self._names("reprojetc", algorithms=CATALOG))

    def test_substring_matches_multiple(self):
        names = self._names("project", algorithms=CATALOG)
        self.assertIn("reproject", names)  # verb (substring)
        self.assertIn("project", names)  # built-in verb

    def test_algorithms_included_only_when_catalog_passed(self):
        self.assertIn("gdal:warpreproject", self._names("warp", algorithms=CATALOG))
        # no catalog → verbs/builtins only, never an algorithm id
        self.assertFalse(any(":" in n for n in self._names("warp")))

    def test_multiword_is_or_semantics(self):
        names = self._names("raster slope", algorithms=CATALOG)
        self.assertIn("slope", names)  # matched "slope"
        self.assertIn("native:slope", names)

    def test_no_matches_returns_empty(self):
        self.assertEqual(search("zzzznomatch", algorithms=CATALOG, threshold=0.6), [])

    def test_limit_caps_results(self):
        self.assertLessEqual(
            len(search("e", algorithms=CATALOG, threshold=0.0, limit=3)), 3
        )


class TestSynonymSearch(unittest.TestCase):
    """Synonym-aware ranking (issue #44): a curated keyword surfaces the right tool even
    when the word isn't in its name/description."""

    def _names(self, query, **kw):
        return [h.name for h in search(query, **kw)]

    def test_synonym_surfaces_verbs_offline(self):
        # "generalize" is not a verb name, but a curated synonym for simplify + smooth.
        names = self._names("generalize")  # no catalog → verbs/builtins only
        self.assertIn("simplify", names)
        self.assertIn("smooth", names)

    def test_synonym_surfaces_algorithm_id(self):
        # "mosaic" reaches gdal:merge purely via the synonym map, not name/description.
        cat = [
            {"id": "gdal:merge", "display_name": "Merge", "group": "Raster",
             "description": "Merge rasters into one."},
        ]
        scores = {h.name: h.score for h in search("mosaic", algorithms=cat)}
        self.assertIn("gdal:merge", scores)
        self.assertGreaterEqual(scores["gdal:merge"], 0.8)

    def test_non_synonym_gibberish_still_empty(self):
        self.assertEqual(search("zzzznope", algorithms=CATALOG, threshold=0.6), [])


class TestFormatResults(unittest.TestCase):
    def test_table_lists_hits(self):
        out = format_results("buffer", search("buffer", algorithms=CATALOG))
        self.assertIn("match(es) for `buffer`", out)
        self.assertIn("| `buffer` |", out)
        self.assertIn("describe", out)  # the next-step hint

    def test_no_matches_message(self):
        out = format_results("zzz", [])
        self.assertIn("No matches", out)


class TestFormatDocs(unittest.TestCase):
    def test_full_describe_per_hit(self):
        hits = search("buffer", algorithms=CATALOG)
        # describe_fn stub: returns a marker per name (so this stays pure/no-QGIS)
        out = format_docs("buffer", hits, lambda name: f"DESC<{name}>")
        self.assertIn("Reference for `buffer`", out)
        self.assertIn("## `buffer`", out)
        self.assertIn("DESC<buffer>", out)

    def test_one_failing_entry_does_not_sink_the_guide(self):
        hits = search("buffer", algorithms=CATALOG)

        def flaky(name):
            if name.startswith("native:"):
                raise RuntimeError("needs QGIS")
            return f"DESC<{name}>"

        out = format_docs("buffer", hits, flaky)
        self.assertIn("DESC<buffer>", out)  # good entry survived
        self.assertIn("could not introspect", out)  # bad entry degraded to a note

    def test_no_matches_message(self):
        self.assertIn("No matches", format_docs("zzz", [], lambda n: n))


if __name__ == "__main__":
    unittest.main()
