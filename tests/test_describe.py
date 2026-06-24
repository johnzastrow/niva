"""`describe` tests (planning 11). The verb path is pure (no QGIS); the algorithm
path is covered by the PyQGIS smoke tests.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva import describe
from niva.describe import BUILTINS, _example_for, _example_for_algorithm
from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse
from niva.registry import core_registry


class TestDescribeVerb(unittest.TestCase):
    def test_describe_alias_shows_mapping(self):
        out = describe("buffer")
        self.assertIn("verb `buffer` → native:buffer", out)
        self.assertIn("distance (distance, required) → DISTANCE", out)
        self.assertIn("cap=<round|flat|square", out)   # enum vocab
        self.assertIn("dissolve → DISSOLVE", out)       # flag

    def test_describe_join_required_option(self):
        out = describe("join")
        self.assertIn("with=<", out)
        self.assertIn("required", out)

    def test_unknown_name_is_flowerror(self):
        with self.assertRaises(FlowError) as ctx:
            describe("frobnicate")
        self.assertIn("Known verbs", str(ctx.exception))

    def test_curated_example_is_shown(self):
        out = describe("buffer")
        self.assertIn("example:", out)
        self.assertIn("load roads.gpkg | buffer 100m dissolve", out)  # the curated one

    def test_synthesized_example_when_no_curated(self):
        # `vertices` carries no example=; describe must synthesise a load→verb→save one.
        out = describe("vertices")
        self.assertIn("example:", out)
        self.assertIn("load roads.gpkg | vertices | save out.gpkg", out)

    def test_describe_builtin_verb(self):
        out = describe("save")
        self.assertIn("verb `save` (built-in)", out)
        self.assertIn("example:", out)


class TestExamplesActuallyRun(unittest.TestCase):
    """Every verb's example must be a *valid, runnable* flow — caught here over the mock
    backend, so a bad curated example (typo'd option, missing arg) fails CI loudly."""

    def test_every_alias_example_parses_and_executes(self):
        reg = core_registry()
        for verb in reg.verbs():
            alias = reg.get(verb)
            example = alias.example or _example_for(alias)
            with self.subTest(verb=verb, example=example):
                # parse + execute over the mock backend: this exercises the binder
                # (required args/options, enum vocab, CRS validation) without real data.
                Engine(MockBackend()).execute(parse(example))

    def test_every_builtin_example_parses(self):
        for verb, (_summary, example) in BUILTINS.items():
            with self.subTest(verb=verb, example=example):
                program = parse(example)  # must be syntactically valid niva
                self.assertTrue(program)

    def test_algorithm_example_is_synthesized_and_runs(self):
        # The `run <id> …` example for an algorithm: required params named, INPUT/OUTPUT
        # omitted (piped/temp), and the whole thing is a runnable flow.
        info = {
            "id": "native:buffer",
            "display_name": "Buffer",
            "provider": "native",
            "params": [
                {"name": "INPUT", "type": "source", "optional": False, "default": None,
                 "description": ""},
                {"name": "DISTANCE", "type": "distance", "optional": False, "default": None,
                 "description": ""},
                {"name": "SEGMENTS", "type": "number", "optional": True, "default": 5,
                 "description": ""},
                {"name": "OUTPUT", "type": "sink", "optional": False, "default": None,
                 "description": ""},
            ],
            "outputs": [],
        }
        ex = _example_for_algorithm(info)
        self.assertIn("run native:buffer", ex)
        self.assertIn("DISTANCE=", ex)       # required param surfaced
        self.assertNotIn("INPUT=", ex)       # comes from the pipe
        self.assertNotIn("OUTPUT=", ex)      # temp sink
        self.assertNotIn("SEGMENTS=", ex)    # optional → omitted
        Engine(MockBackend()).execute(parse(ex))  # runnable


if __name__ == "__main__":
    unittest.main()
