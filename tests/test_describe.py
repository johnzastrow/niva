"""`describe` tests (planning 11). The verb path is pure (no QGIS); the algorithm
path is covered by the PyQGIS smoke tests.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import unittest

from niva import describe
from niva.errors import FlowError


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


if __name__ == "__main__":
    unittest.main()
