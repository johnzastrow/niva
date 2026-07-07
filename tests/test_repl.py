"""Tests for the repl's manifest-driven tab completion (`niva.cli.repl.completions`). Pure
Python, no QGIS, no prompt_toolkit — the completion logic is a plain, testable function."""

import contextlib
import io
import unittest

from niva.cli.repl import _handle, completions
from niva.manifest import build_manifest


def _run(line, state=None):
    """Drive one repl line; return (rc, printed-text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _handle(line, state if state is not None else {"last": None})
    return rc, buf.getvalue()


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


class TestReplCommands(unittest.TestCase):
    def test_quit_variants_all_quit(self):
        for q in (".quit", ".exit", ".q", "quit", "exit", "q", r"\q", ":q"):
            self.assertEqual(_run(q)[0], "quit", q)

    def test_help_variants_print_help(self):
        for h in (".help", ".?", ".h", "?", "help", r"\?", ":h", ":help"):
            rc, out = _run(h)
            self.assertEqual(rc, "", h)
            self.assertIn("commands:", out, h)

    def test_mistyped_dot_command_is_flagged_not_parsed(self):
        rc, out = _run(".quti")
        self.assertEqual(rc, "")
        self.assertIn("unknown command", out)

    def test_flow_line_is_validated_and_remembered(self):
        state = {"last": None}
        _run("load a.gpkg | save b.gpkg", state)
        self.assertEqual(state["last"], "load a.gpkg | save b.gpkg")


class TestHighlight(unittest.TestCase):
    def test_classify(self):
        from niva.cli.repl import _classify

        verbs = {"load", "buffer", "save"}
        self.assertEqual(_classify("load", True, verbs), "verb")
        self.assertEqual(_classify("nope", True, verbs), "unknown")
        self.assertEqual(_classify("@gisdb3.parcels", False, verbs), "conn")
        self.assertEqual(_classify("field=county", False, verbs), "optkey")
        self.assertEqual(_classify("roads.gpkg", False, verbs), "path")
        self.assertEqual(_classify("100m", False, verbs), "num")
        self.assertEqual(_classify("2.5", False, verbs), "num")
        self.assertEqual(
            _classify("dissolve", False, verbs), "flag"
        )  # bareword, not stage-start

    def test_highlight_flow_is_transparent_without_color(self):
        # With colour disabled, the highlighter must round-trip the text byte-for-byte
        # (whitespace and pipes preserved) — it only *adds* invisible ANSI when enabled.
        import os

        from niva.cli.repl import highlight_flow

        old = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"
        try:
            for flow in (
                "load a.gpkg | buffer 100m | save b.gpkg",
                'sql @c "SELECT 1"',
            ):
                self.assertEqual(highlight_flow(flow), flow)
        finally:
            if old is None:
                del os.environ["NO_COLOR"]
            else:
                os.environ["NO_COLOR"] = old


if __name__ == "__main__":
    unittest.main()
