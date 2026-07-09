"""CLI argument routing (`niva.cli.main._read_source`) — no QGIS."""

import os
import tempfile
import unittest

from niva.cli.main import _read_source


class TestReadSource(unittest.TestCase):
    def _niva_file(self, body="load a.gpkg | buffer 5m | save b.gpkg\n"):
        fd, path = tempfile.mkstemp(suffix=".niva")
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        return path

    def test_run_subcommand_reads_file(self):
        path = self._niva_file()
        source, text = _read_source(["run", path])
        self.assertEqual(source, path)
        self.assertTrue(text.startswith("load"))

    def test_lone_niva_file_runs_without_run(self):
        # `niva flow.niva` (no `run`) should execute the file, not read it as a verb.
        path = self._niva_file()
        source, text = _read_source([path])
        self.assertEqual(source, path)
        self.assertTrue(text.startswith("load"))

    def test_missing_niva_file_is_a_clear_error_not_inline(self):
        source, text = _read_source(["definitely_not_here.niva"])
        self.assertIsNone(text)  # main() turns text=None into a non-zero exit

    def test_inline_flow_is_unchanged(self):
        # A real inline flow never ends in .niva, so it still joins to an inline program.
        source, text = _read_source(["show", "/data"])
        self.assertEqual(source, "<inline>")
        self.assertEqual(text, "show /data")

    def test_single_quoted_inline_flow_unchanged(self):
        source, text = _read_source(["load x.gpkg | save y.gpkg"])
        self.assertEqual(source, "<inline>")
        self.assertEqual(text, "load x.gpkg | save y.gpkg")


if __name__ == "__main__":
    unittest.main()
