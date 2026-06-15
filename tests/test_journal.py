"""Run-journal tests (planning/08-§2). Mock-backed — no QGIS.

Verifies both artifacts: the machine-readable JSONL and the human-readable .log.
"""

import json
import os
import tempfile
import unittest

from niva import flow
from niva.engine import MockBackend
from niva.errors import FlowError


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.base = os.path.join(tempfile.mkdtemp(prefix="niva_journal_"), "run")

    def _run(self, text):
        flow(text, backend=MockBackend(), log=self.base)

    def test_writes_both_files(self):
        self._run("load a.gpkg | buffer 100m | save out.gpkg")
        self.assertTrue(os.path.exists(self.base + ".jsonl"))
        self.assertTrue(os.path.exists(self.base + ".log"))

    def test_jsonl_header_records_footer(self):
        self._run("load a.gpkg | buffer 100m | save out.gpkg")
        lines = [json.loads(x) for x in open(self.base + ".jsonl") if x.strip()]
        self.assertEqual(lines[0]["niva_journal"], 1)
        self.assertIn("started", lines[0])
        self.assertIn("niva_version", lines[0])
        records = [r for r in lines if "kind" in r]
        self.assertEqual([r["kind"] for r in records], ["load", "buffer", "save"])
        for r in records:
            self.assertIn("ts", r)
            self.assertTrue(r["ok"])
        self.assertEqual(lines[-1]["operations"], 3)  # footer

    def test_jsonl_records_algorithm_for_alias(self):
        self._run("load a.gpkg | buffer 100m | save out.gpkg")
        recs = [json.loads(x) for x in open(self.base + ".jsonl") if x.strip()]
        buf = next(r for r in recs if r.get("kind") == "buffer")
        self.assertEqual(buf["algorithm"], "native:buffer")

    def test_human_log_is_readable_with_full_paths(self):
        self._run("load a.gpkg | buffer 100m | save out/b.gpkg")
        text = open(self.base + ".log").read()
        self.assertIn("# run:", text)                   # one-line run header
        self.assertIn("buffer 100m", text)              # the stage text
        self.assertIn("native:buffer", text)            # the algorithm
        self.assertIn(os.path.abspath("out/b.gpkg"), text)  # FULL path for the save
        self.assertIn("# done:", text)                  # one-line footer
        self.assertNotIn("{", text)                     # not JSON

    def test_one_line_per_operation(self):
        self._run("load a.gpkg | buffer 100m | save out.gpkg")
        text = open(self.base + ".log").read()
        op_lines = [ln for ln in text.splitlines()
                    if ln and not ln.startswith("#")]
        self.assertEqual(len(op_lines), 3)  # load, buffer, save — one line each

    def test_session_append_accumulates_runs(self):
        flow("load a.gpkg | save a.gpkg", backend=MockBackend(), log=self.base, log_append=True)
        flow("load b.gpkg | save b.gpkg", backend=MockBackend(), log=self.base, log_append=True)
        text = open(self.base + ".log").read()
        self.assertEqual(text.count("# run:"), 2)        # both runs in one file
        self.assertIn("load a.gpkg", text)
        self.assertIn("load b.gpkg", text)

    def test_failure_inline_one_line(self):
        with self.assertRaises(FlowError):
            flow("buffer 100m", backend=MockBackend(), log=self.base)  # op before load
        lines = [ln for ln in open(self.base + ".log").read().splitlines()
                 if "FAILED" in ln]
        self.assertEqual(len(lines), 1)  # the failure is a single line

    def test_timestamps_present(self):
        self._run("load a.gpkg | save out.gpkg")
        text = open(self.base + ".log").read()
        import re
        self.assertRegex(text, r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d")

    def test_failure_is_recorded(self):
        with self.assertRaises(FlowError):
            flow("buffer 100m", backend=MockBackend(), log=self.base)  # op before load
        self.assertIn("FAILED", open(self.base + ".log").read())
        recs = [json.loads(x) for x in open(self.base + ".jsonl") if x.strip()]
        self.assertTrue(any(r.get("ok") is False for r in recs))


if __name__ == "__main__":
    unittest.main()
