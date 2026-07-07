"""Tests for the zero-dependency ANSI colour helper (`niva.color`). Pure Python."""

import os
import unittest
from unittest import mock

from niva import color


class TestColor(unittest.TestCase):
    def test_no_color_disables_even_with_force_always(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1", "NIVA_COLOR": "always"}):
            self.assertFalse(color.enabled())
            self.assertEqual(color.paint("x", "red"), "x")

    def test_force_always_wraps_in_ansi(self):
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        env["NIVA_COLOR"] = "always"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(color.enabled())
            out = color.paint("x", "red")
            self.assertIn("\033[31m", out)
            self.assertTrue(out.endswith("\033[0m"))
            self.assertIn("x", out)  # the text survives inside the escapes

    def test_force_never_disables(self):
        with mock.patch.dict(os.environ, {"NIVA_COLOR": "never"}):
            self.assertFalse(color.enabled())
            self.assertEqual(color.paint("x", "green"), "x")

    def test_paint_without_styles_is_plain(self):
        with mock.patch.dict(os.environ, {"NIVA_COLOR": "always"}):
            self.assertEqual(color.paint("hello"), "hello")


if __name__ == "__main__":
    unittest.main()
