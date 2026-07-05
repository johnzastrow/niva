"""Output-routing tests — every verb's text must reach the user the SAME way.

Three sinks, one mechanism (`Engine._emit_report` for report verbs, `_emit` for action
verbs):

  1. ``to=<file>``        → the report is written to a text file (CLI/plugin file capture),
                            and a single ``  <label> → <path>`` status line is emitted.
  2. progress callback set → the report streams to the dock / CLI line-by-line (no stdout).
  3. no progress, no ``to`` → the report is printed to stdout (pipeable / redirectable).

These run over MockBackend — no QGIS — so they exercise the routing, not the backend.
"""

import contextlib
import io
import os
import tempfile
import unittest

from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


def _run(text, *, progress=None):
    """Execute `text` over a MockBackend, capturing stdout. Returns (stdout, messages)."""
    msgs = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Engine(
            MockBackend(),
            progress=(msgs.append if progress is None else progress)
            if progress is not False
            else None,
        ).execute(parse(text))
    return buf.getvalue(), msgs


# (verb label, flow text, a substring that must appear in the report, the to= status label)
# `search`/`docs` use the keyword "dissolve": it matches the dissolve VERB but none of the
# algorithm ids in MockBackend.algorithm_catalog(), so docs introspects only the pure verb
# (no QGIS bootstrap) — keeping these routing tests fast and QGIS-free.
REPORT_VERBS = [
    ("show", "show @pg", "Data at", "listed"),
    ("info", "info", "niva — environment", "environment report"),
    ("describe", "describe buffer", "buffer", "description"),
    ("search", "search dissolve", "dissolve", "match(es)"),
    ("docs", "docs dissolve", "dissolve", "docs for"),
]


class TestReportVerbsRouteIdentically(unittest.TestCase):
    """show / info / describe must all support the same three output options, identically."""

    def test_to_file_writes_report_and_emits_one_status_line(self):
        for name, text, needle, label in REPORT_VERBS:
            with self.subTest(verb=name):
                out = os.path.join(tempfile.mkdtemp(prefix=f"niva_{name}_"), "r.md")
                msgs = []
                stdout, _ = _run(f'{text} to="{out}"', progress=msgs.append)
                # report went to the FILE, not stdout
                self.assertEqual(stdout, "", f"{name}: nothing should print to stdout")
                self.assertTrue(os.path.exists(out))
                with open(out, encoding="utf-8") as fh:
                    report = fh.read()
                self.assertIn(needle, report)
                # exactly one "  <label> → <path>" status line, naming the file
                status = [m for m in msgs if "→" in m and out in m]
                self.assertEqual(len(status), 1, f"{name}: {msgs}")
                self.assertIn(label, status[0])

    def test_progress_set_streams_report_to_the_dock(self):
        for name, text, needle, _label in REPORT_VERBS:
            with self.subTest(verb=name):
                msgs = []
                stdout, _ = _run(text, progress=msgs.append)
                self.assertEqual(stdout, "", f"{name}: should stream, not print")
                body = "\n".join(msgs)
                self.assertIn(needle, body, f"{name}: report not streamed: {msgs}")

    def test_no_progress_prints_report_to_stdout(self):
        for name, text, needle, _label in REPORT_VERBS:
            with self.subTest(verb=name):
                stdout, _ = _run(text, progress=False)  # progress=None on the Engine
                self.assertIn(needle, stdout, f"{name}: report not on stdout")

    def test_same_text_regardless_of_sink(self):
        # The whole point of "emit the same way": the report BODY is identical whether it
        # goes to stdout or a file. (The streamed/dock sink wraps the same body in run/stage
        # chrome — ▶/✓/run-started — so it's a superset, checked separately.)
        for name, text, _needle, _label in REPORT_VERBS:
            with self.subTest(verb=name):
                stdout, _ = _run(text, progress=False)  # stdout sink (no progress)
                from_stdout = stdout.strip()
                out = os.path.join(tempfile.mkdtemp(prefix=f"niva_{name}_"), "r.md")
                _run(f'{text} to="{out}"', progress=[].append)  # file sink
                with open(out, encoding="utf-8") as fh:
                    from_file = fh.read().strip()
                self.assertEqual(
                    from_stdout, from_file, f"{name}: stdout vs file differ"
                )
                # and the body really is carried inside the streamed sink too
                msgs = []
                _run(text, progress=msgs.append)
                self.assertIn(
                    from_stdout.splitlines()[0],
                    "\n".join(msgs),
                    f"{name}: report body missing from stream",
                )


class TestActionVerbsEmitToTheDock(unittest.TestCase):
    """Verbs that act rather than report still confirm what they did, so the action is
    visible in the dock and the CLI (not silent)."""

    def _status(self, text):
        msgs = []
        Engine(MockBackend(), progress=msgs.append).execute(parse(text))
        return msgs

    def test_assess_emits_report_path(self):
        out = os.path.join(tempfile.mkdtemp(prefix="niva_assess_"), "r.md")
        msgs = self._status(f"load a.gpkg | assess to {out}")
        self.assertTrue(any(m.strip() == f"assessment → {out}" for m in msgs), msgs)

    def test_style_emits_confirmation(self):
        msgs = self._status("load a.gpkg | style save out.qml")
        self.assertTrue(any("style saved → out.qml" in m for m in msgs), msgs)

    def test_metadata_emits_confirmation(self):
        msgs = self._status('load a.gpkg | metadata set title="Roads"')
        self.assertTrue(any(m.strip().startswith("metadata set:") for m in msgs), msgs)

    def test_catalog_emits_report_path(self):
        d = tempfile.mkdtemp(prefix="niva_catalog_")
        out = os.path.join(d, "cat.md")
        msgs = self._status(f'catalog "{d}" to={out}')
        self.assertTrue(any("→" in m and out in m for m in msgs), msgs)

    def test_notify_emits_target(self):
        from niva import utilities

        orig = utilities.send_ntfy
        utilities.send_ntfy = lambda message, **kw: "https://ntfy.sh/mytopic"  # noqa: E731
        try:
            msgs = self._status('notify "done" to=mytopic')
        finally:
            utilities.send_ntfy = orig
        self.assertTrue(any(m.strip().startswith("notified →") for m in msgs), msgs)


class TestReportVerbValidation(unittest.TestCase):
    def test_describe_requires_one_target(self):
        for bad in ("describe", "describe a b"):
            with self.subTest(flow=bad), self.assertRaises(FlowError):
                Engine(MockBackend()).execute(parse(bad))

    def test_report_verbs_reject_unknown_options(self):
        for bad in ("show @pg bogus=1", "info bogus=1", "describe buffer bogus=1"):
            with self.subTest(flow=bad), self.assertRaises(FlowError):
                Engine(MockBackend()).execute(parse(bad))


if __name__ == "__main__":
    unittest.main()
