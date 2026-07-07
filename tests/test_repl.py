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

    def test_path_argument_completes_files_and_dirs(self):
        import os
        import tempfile

        d = tempfile.mkdtemp(prefix="niva_comp_")
        os.makedirs(os.path.join(d, "subdir"))
        open(os.path.join(d, "roads.gpkg"), "w").close()
        open(os.path.join(d, "rivers.gpkg"), "w").close()
        got = completions(f"show {d}/")
        names = sorted(os.path.basename(p.rstrip("/")) for p in got)
        self.assertEqual(names, ["rivers.gpkg", "roads.gpkg", "subdir"])
        # directories are suffixed with "/"; files are not
        self.assertTrue(any(p.endswith("subdir/") for p in got))
        self.assertTrue(all(not p.endswith("roads.gpkg/") for p in got))

    def test_path_argument_respects_prefix(self):
        import os
        import tempfile

        d = tempfile.mkdtemp(prefix="niva_comp_")
        open(os.path.join(d, "roads.gpkg"), "w").close()
        open(os.path.join(d, "rivers.gpkg"), "w").close()
        got = [os.path.basename(p) for p in completions(f"load {d}/ro")]
        self.assertEqual(got, ["roads.gpkg"])

    def test_verb_position_offers_no_paths(self):
        # At the stage start we complete verbs, never filesystem entries.
        self.assertNotIn("./", completions("sho"))
        self.assertIn("show", completions("sho"))


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

    def test_run_without_prior_flow_hints(self):
        rc, out = _run(".run", {"last": None})
        self.assertEqual(rc, "")
        self.assertIn("no flow yet", out)

    def test_run_is_a_known_command_not_flagged(self):
        # `.run` must be handled, never fall through to the "unknown command" branch.
        _, out = _run(".run", {"last": None})
        self.assertNotIn("unknown command", out)

    def test_info_and_show_autorun_but_transforms_do_not(self):
        # Read-only report verbs execute for real (routed to _run_flow); a transform flow is
        # validated only (never auto-run) — it needs an explicit .run.
        import niva.cli.repl as R

        called = []
        orig = R._run_flow
        R._run_flow = lambda flow, state: called.append(flow)
        try:
            _run("info")
            _run("show somedir")
            _run("load a.gpkg | buffer 100m | save b.gpkg")
            _run("show a.gpkg | buffer 100m | save b.gpkg")  # piped → not a bare report
        finally:
            R._run_flow = orig
        self.assertEqual(called, ["info", "show somedir"])

    def test_valid_flows_are_collected_invalid_excluded(self):
        state = {"last": None}
        _run("load a.gpkg | buffer 100m | save b.gpkg", state)
        _run("load bad | | oops", state)  # invalid → not collected
        _run("load c.gpkg | save d.gpkg", state)
        self.assertEqual(
            state.get("session"),
            ["load a.gpkg | buffer 100m | save b.gpkg", "load c.gpkg | save d.gpkg"],
        )

    def test_history_lists_session_flows(self):
        state = {"last": None}
        _run("load a.gpkg | save b.gpkg", state)
        _, out = _run(".history", state)
        self.assertIn("load a.gpkg | save b.gpkg", out)
        _, empty = _run(".history", {"last": None})
        self.assertIn("no flows yet", empty)

    def test_save_writes_a_runnable_niva_file(self):
        import os
        import tempfile

        state = {"last": None}
        _run("load a.gpkg | buffer 100m | save b.gpkg", state)
        _run("load c.gpkg | save d.gpkg", state)
        d = tempfile.mkdtemp(prefix="niva_save_")
        target = os.path.join(d, "study")  # no extension → .niva appended
        _run(f".save {target}", state)
        path = target + ".niva"
        self.assertTrue(os.path.isfile(path))
        body = open(path, encoding="utf-8").read()
        self.assertIn("load a.gpkg | buffer 100m | save b.gpkg", body)
        self.assertIn("load c.gpkg | save d.gpkg", body)
        self.assertTrue(body.startswith("#"))  # has a header comment

    def test_save_with_nothing_or_no_target(self):
        _, out1 = _run(".save x.niva", {"last": None})  # no session yet
        self.assertIn("nothing to save", out1)
        state = {"last": None}
        _run("load a.gpkg | save b.gpkg", state)
        _, out2 = _run(".save", state)  # missing target
        self.assertIn("usage: .save", out2)

    def test_first_valid_flow_hints_run_once(self):
        state = {"last": None}
        _, out1 = _run("load a.gpkg | save b.gpkg", state)
        self.assertIn(".run to execute", out1)
        _, out2 = _run("load c.gpkg | save d.gpkg", state)  # hint only fires once
        self.assertNotIn(".run to execute", out2)


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
