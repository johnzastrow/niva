"""The plugin's execution core (``plugin/runner.py``), which runs a flow inside QGIS's own
process. Its contract: it always returns a result dict and never raises (an exception escaping
the worker thread can destabilise QGIS). QGIS-free: dry-run uses the MockBackend and the real
run path stubs ``niva.flow``."""

import os
import tempfile
import unittest
from unittest import mock

from niva.errors import FlowError
from plugin import runner

FLOW = "load roads.gpkg | buffer 100m | save out.gpkg"
RESULT_KEYS = {"ok", "mode", "summary", "layer", "error", "log", "elapsed"}


class TestDryRun(unittest.TestCase):
    def test_valid_flow_lists_backend_operations(self):
        res = runner.run_flow(FLOW, dry_run=True)
        self.assertEqual(set(res), RESULT_KEYS)
        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "dry-run")
        self.assertIn("native:buffer", res["summary"])
        self.assertIsNone(res["error"])
        self.assertGreaterEqual(res["elapsed"], 0)

    def test_invalid_flow_returns_an_error_instead_of_raising(self):
        res = runner.run_flow("load roads.gpkg | frobnicate 3", dry_run=True)
        self.assertFalse(res["ok"])
        self.assertEqual(res["mode"], "dry-run")
        self.assertIn("frobnicate", res["error"])
        self.assertEqual(set(res), RESULT_KEYS)

    def test_grammar_error_is_also_contained(self):
        res = runner.run_flow("load | |", dry_run=True)
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"])


class _Layer:
    def __init__(self, ref, name="out", count=None, count_raises=False):
        self.ref = ref
        self.name = name
        if count is not None or count_raises:

            def feature_count():
                if count_raises:
                    raise RuntimeError("provider gone")
                return count

            # a live QgsVectorLayer exposes featureCount() on the ref
            if not isinstance(ref, str):
                ref.featureCount = feature_count


class _Ref:
    def __init__(self, source):
        self._source = source

    def source(self):
        return self._source


class TestRealRun(unittest.TestCase):
    def test_success_summarises_the_output_and_returns_the_layer(self):
        layer = _Layer("out.gpkg")
        with mock.patch("niva.flow", return_value=layer) as flow:
            res = runner.run_flow(
                FLOW, file="/proj/a.niva", log_base="/tmp/niva_session"
            )
        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "run")
        self.assertIs(res["layer"], layer)
        self.assertEqual(res["log"], "/tmp/niva_session.log")
        self.assertIn(os.path.abspath("out.gpkg"), res["summary"])
        # the plugin appends every run of a session to one journal
        kwargs = flow.call_args.kwargs
        self.assertEqual(kwargs["log"], "/tmp/niva_session")
        self.assertTrue(kwargs["log_append"])
        self.assertEqual(kwargs["file"], "/proj/a.niva")

    def test_progress_and_cancel_callbacks_are_passed_through(self):
        progress, cancel = mock.Mock(), mock.Mock(return_value=False)
        with mock.patch("niva.flow", return_value=None) as flow:
            runner.run_flow(FLOW, progress=progress, cancel=cancel)
        self.assertIs(flow.call_args.kwargs["progress"], progress)
        self.assertIs(flow.call_args.kwargs["cancel"], cancel)

    def test_niva_error_message_is_shown_without_a_traceback(self):
        with mock.patch(
            "niva.flow", side_effect=FlowError("unknown verb `frobnicate`")
        ):
            res = runner.run_flow(FLOW, log_base="/tmp/s")
        self.assertFalse(res["ok"])
        self.assertIn("unknown verb", res["error"])
        self.assertNotIn("Traceback", res["error"])
        self.assertEqual(res["log"], "/tmp/s.log")  # a failed run is still journalled

    def test_unexpected_exception_is_contained_with_its_traceback(self):
        with mock.patch("niva.flow", side_effect=KeyError("boom")):
            res = runner.run_flow(FLOW)
        self.assertFalse(res["ok"])
        self.assertIn("unexpected error: KeyError", res["error"])
        self.assertIn("Traceback", res["error"])
        self.assertIsNone(res["log"])  # logging off when no base is given

    def test_no_output_layer(self):
        with mock.patch("niva.flow", return_value=None):
            res = runner.run_flow(FLOW)
        self.assertEqual(res["summary"], "done — no output layer.")


class TestDescribe(unittest.TestCase):
    def test_saved_file_shows_its_absolute_path(self):
        self.assertEqual(
            runner._describe(_Layer("data/out.gpkg")),
            f"done — {os.path.abspath('data/out.gpkg')}.",
        )

    def test_live_layer_shows_source_and_feature_count(self):
        layer = _Layer(_Ref("/data/x.gpkg|layername=x"), count=42)
        self.assertEqual(
            runner._describe(layer), "done — /data/x.gpkg|layername=x, 42 feature(s)."
        )

    def test_failing_feature_count_is_omitted_not_raised(self):
        layer = _Layer(_Ref("/data/x.gpkg"), count_raises=True)
        self.assertEqual(runner._describe(layer), "done — /data/x.gpkg.")

    def test_ref_without_source_falls_back_to_layer_name(self):
        self.assertEqual(
            runner._describe(_Layer(object(), name="memory_result")),
            "done — memory_result.",
        )


class TestFlowFileBase(unittest.TestCase):
    def test_dry_run_resolves_relative_paths_from_the_flow_file(self):
        d = tempfile.mkdtemp(prefix="niva_runner_")
        with mock.patch("niva.engine.Engine.execute") as execute:
            runner.run_flow(FLOW, file=os.path.join(d, "flow.niva"), dry_run=True)
        self.assertEqual(execute.call_args.kwargs["base_dir"], d)


if __name__ == "__main__":
    unittest.main()
