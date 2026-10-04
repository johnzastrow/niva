"""CLI commands end to end through ``niva.cli.main.main(argv)`` — no QGIS, no subprocess.

Every command that works without QGIS is driven here with its real arguments, asserting the exit
code (0 ok, 1 op error, 2 flow/usage error, 3 I/O or missing QGIS) and the user-visible output.
Each test gets a throwaway config dir (``XDG_CONFIG_HOME``) and working directory. Paths that
would start a standalone QGIS (and hard-exit the process) are stubbed.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from niva.cli.main import main

FLOW = "load roads.gpkg | buffer 100m | save out.gpkg"


def run_cli(*argv):
    """Run the CLI in-process; return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class _Isolated(unittest.TestCase):
    """A temp working dir and config dir per test; nothing touches the user's files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_cli_")
        self._cwd = os.getcwd()
        os.chdir(self.tmp)
        self._env = mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": os.path.join(self.tmp, "cfg")}
        )
        self._env.start()
        # Never let a test bootstrap a standalone QGIS (it hard-exits the interpreter).
        self._owned = mock.patch("niva.engine.pyqgis.owned_app", return_value=None)
        self._owned.start()

    def tearDown(self):
        self._owned.stop()
        self._env.stop()
        os.chdir(self._cwd)

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


class TestHelpAndDispatch(_Isolated):
    def test_no_arguments_prints_usage(self):
        code, out, _ = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("usage: niva run <file.niva>", out)

    def test_help_flags_print_usage(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                code, out, _ = run_cli(flag)
                self.assertEqual(code, 0)
                self.assertIn("niva validate", out)

    def test_missing_niva_file_is_reported_not_run_inline(self):
        code, _, err = run_cli("nope.niva")
        self.assertEqual(code, 2)
        self.assertIn("no such file: nope.niva", err)

    def test_run_without_a_file(self):
        code, _, err = run_cli("run")
        self.assertEqual(code, 2)
        self.assertIn("missing <file.niva>", err)

    def test_run_with_unreadable_path_is_an_io_error(self):
        code, _, err = run_cli("run", os.path.join(self.tmp, "absent.niva"))
        self.assertEqual(code, 3)
        self.assertIn("absent.niva", err)


class TestDryRunAndExplain(_Isolated):
    def test_dry_run_inline_walks_the_mock_backend(self):
        code, out, _ = run_cli(FLOW, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("buffer → native:buffer", out)
        self.assertIn("# dry-run OK", out)
        self.assertIn("run native:buffer", out)

    def test_unquoted_tokens_are_joined_into_one_flow(self):
        code, out, _ = run_cli("load", "roads.gpkg", "|", "buffer", "100m", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("# dry-run OK", out)

    def test_dry_run_of_a_file_without_run_keyword(self):
        path = self.write("flow.niva", FLOW + "\n")
        code, out, _ = run_cli(path, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn(f"# parsed {path}", out)

    def test_explain_flags_unknown_verbs_and_exits_2(self):
        code, out, err = run_cli("load roads.gpkg | frobnicate 3", "--explain")
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN VERB", out)
        self.assertIn("unknown verb", err)

    def test_explain_of_a_valid_flow_exits_0(self):
        code, out, _ = run_cli(FLOW, "--explain")
        self.assertEqual(code, 0)
        self.assertIn("3 stage(s)", out)

    def test_grammar_error_exits_2(self):
        code, _, err = run_cli("load roads.gpkg | | buffer", "--dry-run")
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_execute_without_qgis_explains_how_to_run_it(self):
        with mock.patch(
            "niva.engine.pyqgis.ensure_qgis",
            side_effect=ImportError("No module named 'qgis'"),
        ):
            code, _, err = run_cli(FLOW)
        self.assertEqual(code, 3)
        self.assertIn("could not import QGIS", err)


class TestValidate(_Isolated):
    def test_valid_file_passes(self):
        path = self.write("ok.niva", FLOW + "\n")
        code, out, _ = run_cli("validate", path)
        self.assertEqual(code, 0)
        self.assertIn(f"✓ {path}", out)
        self.assertIn("1 file(s): 0 error(s)", out)

    def test_unknown_verb_fails_with_line_number(self):
        path = self.write("bad.niva", "load roads.gpkg | frobnicate 3\n")
        code, out, _ = run_cli("validate", path)
        self.assertEqual(code, 1)
        self.assertIn(f"✗ {path}", out)
        self.assertIn("line 1", out)

    def test_missing_file_counts_as_an_error(self):
        code, _, err = run_cli("validate", os.path.join(self.tmp, "gone.niva"))
        self.assertEqual(code, 1)
        self.assertIn("gone.niva", err)

    def test_glob_expands_to_every_matching_file(self):
        self.write("a.niva", FLOW + "\n")
        self.write("b.niva", "load x.gpkg | save y.gpkg\n")
        code, out, _ = run_cli("validate", os.path.join(self.tmp, "*.niva"))
        self.assertEqual(code, 0)
        self.assertIn("# 2 file(s)", out)

    def test_one_bad_file_fails_the_whole_run(self):
        good = self.write("good.niva", FLOW + "\n")
        bad = self.write("worse.niva", "frobnicate\n")
        code, out, _ = run_cli("validate", good, bad)
        self.assertEqual(code, 1)
        self.assertIn("2 file(s)", out)

    def test_usage_without_paths(self):
        self.assertEqual(run_cli("validate")[0], 2)


class TestPlanAndExplainCommands(_Isolated):
    def test_plan_emits_json_ir(self):
        code, out, _ = run_cli("plan", FLOW)
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertEqual(plan["niva_plan"], "1")
        self.assertIn("niva_version", plan)

    def test_plan_reads_a_file_and_records_it(self):
        path = self.write("p.niva", FLOW + "\n")
        code, out, _ = run_cli("plan", path)
        self.assertEqual(code, 0)
        self.assertIn(os.path.basename(path), json.dumps(json.loads(out)["source"]))

    def test_explain_json_matches_plan(self):
        _, plan_out, _ = run_cli("plan", FLOW)
        code, explain_out, _ = run_cli("explain", FLOW, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(plan_out), json.loads(explain_out))

    def test_explain_human_view_names_the_algorithm(self):
        code, out, _ = run_cli("explain", FLOW)
        self.assertEqual(code, 0)
        self.assertIn("native:buffer", out)

    def test_bad_flow_and_missing_args_exit_2(self):
        self.assertEqual(run_cli("plan", "load | |")[0], 2)
        self.assertEqual(run_cli("plan")[0], 2)
        self.assertEqual(run_cli("explain")[0], 2)


class TestManifest(_Isolated):
    def test_manifest_lists_verbs_as_json(self):
        code, out, _ = run_cli("manifest")
        self.assertEqual(code, 0)
        self.assertIn("buffer", out)
        json.loads(out)

    def test_manifest_to_file_creates_parent_dirs(self):
        target = os.path.join(self.tmp, "out", "nested", "manifest.json")
        code, out, err = run_cli("manifest", f"to={target}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn(f"wrote {target}", err)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), json.loads(run_cli("manifest")[1]))


class TestSearch(_Isolated):
    def test_text_results_mention_the_keyword(self):
        code, out, _ = run_cli("search", "buffer")
        self.assertEqual(code, 0)
        self.assertIn("buffer", out)

    def test_json_results_are_ranked_and_limited(self):
        code, out, _ = run_cli("search", "buffer", "limit=3", "--json")
        self.assertEqual(code, 0)
        hits = json.loads(out)
        self.assertTrue(1 <= len(hits) <= 3)
        self.assertEqual(hits[0]["name"], "buffer")
        self.assertEqual({"name", "kind", "summary", "score"}, set(hits[0]))
        scores = [h["score"] for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_bad_limit_is_ignored_not_fatal(self):
        self.assertEqual(run_cli("search", "buffer", "limit=lots")[0], 0)

    def test_results_to_file(self):
        target = os.path.join(self.tmp, "hits.txt")
        code, out, _ = run_cli("search", "clip", f"to={target}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        with open(target, encoding="utf-8") as fh:
            self.assertIn("clip", fh.read())

    def test_usage_without_a_query(self):
        self.assertEqual(run_cli("search")[0], 2)
        self.assertEqual(run_cli("search", "--json")[0], 2)


class TestDescribe(_Isolated):
    def test_verb_is_described(self):
        code, out, _ = run_cli("describe", "buffer")
        self.assertEqual(code, 0)
        self.assertIn("verb `buffer` → native:buffer", out)

    def test_describe_to_file(self):
        target = os.path.join(self.tmp, "docs", "buffer.md")
        code, _, err = run_cli("describe", "buffer", f"to={target}")
        self.assertEqual(code, 0)
        self.assertIn("wrote", err)
        with open(target, encoding="utf-8") as fh:
            self.assertTrue(fh.read().endswith("\n"))

    def test_unknown_verb_is_a_flow_error(self):
        code, _, err = run_cli("describe", "frobnicate")
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_usage(self):
        self.assertEqual(run_cli("describe")[0], 2)
        self.assertEqual(run_cli("describe", "buffer", "clip")[0], 2)


class TestFind(_Isolated):
    def setUp(self):
        super().setUp()
        self.write("data/roads.geojson", '{"type":"FeatureCollection","features":[]}')
        self.write("data/parks.geojson", '{"type":"FeatureCollection","features":[]}')
        self.write("data/notes.txt", "not spatial")
        self.write(
            "data/deep/rivers.geojson", '{"type":"FeatureCollection","features":[]}'
        )
        self.data = os.path.join(self.tmp, "data")

    def _paths(self, *extra):
        code, out, _ = run_cli(
            "find", "*.geojson", "in", self.data, "--paths", "--no-meta", *extra
        )
        self.assertEqual(code, 0)
        return sorted(os.path.basename(p) for p in out.splitlines() if p)

    def test_finds_spatial_files_recursively_and_skips_others(self):
        self.assertEqual(
            self._paths(), ["parks.geojson", "rivers.geojson", "roads.geojson"]
        )

    def test_shallow_and_max_depth_limit_recursion(self):
        self.assertEqual(self._paths("--shallow"), ["parks.geojson", "roads.geojson"])

    def test_pattern_narrows_the_match(self):
        code, out, _ = run_cli("find", "road*", "in", self.data, "--paths", "--no-meta")
        self.assertEqual(code, 0)
        self.assertEqual(
            [os.path.basename(p) for p in out.splitlines()], ["roads.geojson"]
        )

    def test_print0_is_nul_separated_without_trailing_newline(self):
        code, out, _ = run_cli("find", "*.geojson", "in", self.data, "-0", "--no-meta")
        self.assertEqual(code, 0)
        self.assertNotIn("\n", out)
        self.assertEqual(len([p for p in out.split("\0") if p]), 3)

    def test_json_output_is_a_list_of_records(self):
        code, out, _ = run_cli(
            "find", "*.geojson", "in", self.data, "--json", "--no-meta"
        )
        self.assertEqual(code, 0)
        records = json.loads(out)
        self.assertEqual(len(records), 3)

    def test_as_flow_emits_loadable_niva(self):
        code, out, _ = run_cli(
            "find", "roads*", "in", self.data, "--as-flow", "--no-meta"
        )
        self.assertEqual(code, 0)
        self.assertIn("roads.geojson", out)

    def test_limit_caps_results(self):
        self.assertEqual(len(self._paths("limit=1")), 1)

    def test_bad_options_exit_2(self):
        self.assertEqual(run_cli("find", "--bogus")[0], 2)
        self.assertEqual(run_cli("find", "--geom")[0], 2)  # needs a value
        self.assertEqual(run_cli("find", "--min-features", "lots")[0], 2)

    def test_metadata_filters_require_gdal(self):
        with mock.patch("niva.find.have_gdal", return_value=False):
            code, _, err = run_cli("find", "in", self.data, "--geom", "point")
        self.assertEqual(code, 2)
        self.assertIn("need GDAL", err)


class TestSetup(_Isolated):
    def test_path_is_inside_the_config_dir(self):
        code, out, _ = run_cli("setup", "path")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().startswith(os.path.join(self.tmp, "cfg")))

    def test_set_get_unset_round_trip(self):
        self.assertEqual(run_cli("setup", "set", "log_dir", "/tmp/niva logs")[0], 0)
        code, out, _ = run_cli("setup", "get", "log_dir")
        self.assertEqual((code, out.strip()), (0, "/tmp/niva logs"))
        self.assertEqual(run_cli("setup", "unset", "log_dir")[0], 0)
        self.assertEqual(run_cli("setup", "get", "log_dir")[0], 1)

    def test_secrets_are_refused(self):
        code, _, err = run_cli("setup", "set", "ntfy_token", "abc")
        self.assertEqual(code, 2)
        self.assertIn("NIVA_NTFY_TOKEN", err)

    def test_show_lists_known_keys_and_marks_values(self):
        run_cli("setup", "set", "ntfy_topic", "my-topic")
        with mock.patch.dict(os.environ, {"NIVA_LOG": "/var/log/niva"}):
            code, out, _ = run_cli("setup", "show")
        self.assertEqual(code, 0)
        self.assertIn("my-topic", out)
        self.assertIn("(from $NIVA_LOG)", out)
        self.assertIn("(unset)", out)

    def test_init_does_not_overwrite_without_force(self):
        self.assertEqual(run_cli("setup", "init")[0], 0)
        code, _, err = run_cli("setup", "init")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(run_cli("setup", "init", "--force")[0], 0)

    def test_command_dry_run_changes_nothing(self):
        bindir = os.path.join(self.tmp, "bin")
        with mock.patch.dict(os.environ, {"HOME": self.tmp, "PATH": bindir}):
            code, out, _ = run_cli("setup", "command", "--dry-run")
        self.assertIn(code, (0, 1))
        self.assertTrue(out.strip())
        self.assertFalse(os.path.exists(os.path.join(bindir, "niva")))

    def test_usage_errors(self):
        self.assertEqual(run_cli("setup", "frobnicate")[0], 2)
        self.assertEqual(run_cli("setup", "get")[0], 2)
        self.assertEqual(run_cli("setup", "set", "log_dir")[0], 2)
        self.assertEqual(run_cli("setup", "unset")[0], 2)


class TestExportImport(_Isolated):
    def test_export_to_stdout_is_a_pyqgis_script(self):
        path = self.write("f.niva", FLOW + "\n")
        code, out, _ = run_cli("export", path)
        self.assertEqual(code, 0)
        self.assertIn("processing.run", out)
        self.assertIn("native:buffer", out)

    def test_export_then_import_round_trips_the_verb(self):
        path = self.write("f.niva", FLOW + "\n")
        script = os.path.join(self.tmp, "f.py")
        self.assertEqual(run_cli("export", path, "-o", script)[0], 0)
        self.assertTrue(os.path.isfile(script))
        code, out, _ = run_cli("import", script)
        self.assertEqual(code, 0)
        self.assertIn("buffer", out)

    def test_import_without_processing_calls_is_an_error(self):
        script = self.write("plain.py", "print('hello')\n")
        code, _, err = run_cli("import", script)
        self.assertEqual(code, 1)
        self.assertIn("nothing to import", err)

    def test_missing_input_and_usage(self):
        self.assertEqual(run_cli("export", os.path.join(self.tmp, "none.niva"))[0], 3)
        self.assertEqual(run_cli("export")[0], 2)
        self.assertEqual(run_cli("import", "a.py", "b.py")[0], 2)


if __name__ == "__main__":
    unittest.main()
