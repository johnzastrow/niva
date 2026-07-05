"""SagaCliBackend harness tests (docs/guide/pdal-lastools-qgis4.md, appendix).

Pure Python: the wrapped backend is a MockBackend and ``saga_cmd`` is stubbed, so no
QGIS and no real SAGA are needed. Run: ``python -m unittest tests.test_native``.
"""

import os
import unittest
from unittest import mock

from niva.engine import MockBackend
from niva.engine.layer import SOURCE, Layer
from niva.engine.native import NativeToolBackend, SagaCliBackend, wrap_native
from niva.errors import OpError


def _ok(create_output=True):
    """A fake subprocess.run: return code 0, and (optionally) create whatever file was
    passed after a `-SLOPE`/`-OUT`-style flag so the output-existence check passes."""

    def _run(argv, **kwargs):
        if create_output:
            for i, tok in enumerate(argv):
                if (
                    tok.startswith("-")
                    and i + 1 < len(argv)
                    and "niva-saga-" in str(argv[i + 1])
                ):
                    with open(argv[i + 1], "w") as fh:
                        fh.write("x")
        return mock.Mock(returncode=0, stdout="done", stderr="")

    return _run


class TestDelegation(unittest.TestCase):
    def test_non_saga_id_passes_through(self):
        inner = MockBackend()
        be = wrap_native(inner)
        be.run_raw(
            "native:buffer", {"DISTANCE": 5}, input_layer=Layer(SOURCE, "a.gpkg")
        )
        # The wrapped backend recorded the call — the harness did not intercept it.
        self.assertEqual(inner.calls[-1], ("run", "native:buffer", {"DISTANCE": 5}))

    def test_delegates_unknown_methods(self):
        inner = MockBackend()
        be = wrap_native(inner)
        # `load` is not defined on the adapter — __getattr__ forwards it.
        be.load("roads.gpkg")
        self.assertEqual(inner.calls[-1], ("load", "roads.gpkg"))


class TestSagaRouting(unittest.TestCase):
    def setUp(self):
        self.be = SagaCliBackend(MockBackend(), saga_cmd="saga_cmd")

    def test_builds_expected_argv(self):
        seen = {}

        def _capture(argv, **kwargs):
            seen["argv"] = argv
            # create the output file (the -SLOPE path) so the result wraps
            for i, tok in enumerate(argv):
                if tok == "-SLOPE":
                    with open(argv[i + 1], "w") as fh:
                        fh.write("x")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with (
            mock.patch("niva.engine.native.subprocess.run", _capture),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
            ),
        ):
            out = self.be.run_raw(
                "saga:ta_morphometry:0",
                {"_in": "ELEVATION", "_out": "SLOPE", "UNIT_SLOPE": 1},
                input_layer=Layer(SOURCE, "/data/dem.tif"),
            )
        argv = seen["argv"]
        self.assertEqual(argv[:3], ["/usr/bin/saga_cmd", "ta_morphometry", "0"])
        self.assertIn("-ELEVATION", argv)
        self.assertEqual(argv[argv.index("-ELEVATION") + 1], "/data/dem.tif")
        self.assertIn("-UNIT_SLOPE", argv)
        self.assertEqual(
            argv[argv.index("-UNIT_SLOPE") + 1], "1"
        )  # scalar coerced to token
        # Output wrapped as a raster Layer at the generated scratch path.
        self.assertIsInstance(out, Layer)
        self.assertEqual(out.facet, "raster")
        os.unlink(out.ref)

    def test_terminal_tool_without_out_returns_none(self):
        with (
            mock.patch("niva.engine.native.subprocess.run", _ok(False)),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
            ),
        ):
            out = self.be.run_raw(
                "saga:io_grid:0", {"GRID": "/data/x.tif"}, input_layer=None
            )
        self.assertIsNone(out)

    def test_bool_flag_becomes_one_zero(self):
        with (
            mock.patch("niva.engine.native.subprocess.run", _ok(False)),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
            ),
        ):
            # exercise the private flag renderer directly (deterministic, no process)
            self.assertEqual(self.be._saga_flag("FOO", True), ["-FOO", "1"])
            self.assertEqual(self.be._saga_flag("FOO", False), ["-FOO", "0"])

    def test_nonzero_exit_raises_operror_with_tail(self):
        def _fail(argv, **kwargs):
            return mock.Mock(returncode=1, stdout="", stderr="Error: no such tool\n")

        with (
            mock.patch("niva.engine.native.subprocess.run", _fail),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
            ),
        ):
            with self.assertRaises(OpError) as ctx:
                self.be.run_raw(
                    "saga:ta_morphometry:0", {"_out": "SLOPE"}, input_layer=None
                )
        self.assertIn("no such tool", str(ctx.exception))


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.be = SagaCliBackend(MockBackend())

    def test_malformed_id(self):
        for bad in ("saga:ta_morphometry", "saga::0", "saga:ta_morphometry:0:extra"):
            with self.assertRaises(OpError):
                self.be.run_raw(bad, {}, input_layer=None)

    def test_rejects_injection_style_flag(self):
        with mock.patch(
            "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
        ):
            with self.assertRaises(OpError):
                # a flag name that would smuggle an option into argv
                self.be.run_raw(
                    "saga:ta_morphometry:0",
                    {"--config": "x", "_out": "SLOPE"},
                    input_layer=None,
                )

    def test_in_flag_without_upstream_layer_errors(self):
        with mock.patch(
            "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
        ):
            with self.assertRaises(OpError):
                self.be.run_raw(
                    "saga:ta_morphometry:0",
                    {"_in": "ELEVATION", "_out": "SLOPE"},
                    input_layer=None,
                )


class TestPdalRouting(unittest.TestCase):
    def setUp(self):
        self.be = NativeToolBackend(MockBackend(), pdal_wrench="pdal_wrench")

    def _run(self, algorithm, params, input_layer=None, rc=0, stderr=""):
        seen = {}

        def _capture(argv, **kwargs):
            seen["argv"] = argv
            # create the file passed to --output=… so the result wraps
            for tok in argv:
                if tok.startswith("--output="):
                    with open(tok.split("=", 1)[1], "w") as fh:
                        fh.write("x")
            return mock.Mock(returncode=rc, stdout="", stderr=stderr)

        with (
            mock.patch("niva.engine.native.subprocess.run", _capture),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/opt/pdal_wrench"
            ),
        ):
            out = self.be.run_raw(algorithm, params, input_layer=input_layer)
        return seen.get("argv"), out

    def test_dtm_from_ground_builds_argv_and_raster_layer(self):
        argv, out = self._run(
            "pdalcli:to_raster",
            {"attribute": "Z", "resolution": 1, "filter": "Classification==2"},
            input_layer=Layer(SOURCE, "/data/tile.las"),
        )
        self.assertEqual(argv[:2], ["/opt/pdal_wrench", "to_raster"])
        self.assertIn("--input=/data/tile.las", argv)  # upstream layer auto-wired
        self.assertIn("--attribute=Z", argv)
        self.assertIn("--filter=Classification==2", argv)  # single argv token; no shell
        outs = [a.split("=", 1)[1] for a in argv if a.startswith("--output=")]
        self.assertEqual(len(outs), 1)
        # raster/vector products are returned via inner.load (a real layer downstream);
        # the produced file exists at the scratch --output path.
        self.assertTrue(os.path.exists(outs[0]))
        self.assertIsNotNone(out)
        os.unlink(outs[0])

    def test_explicit_output_is_honored_for_pointcloud(self):
        dest = os.path.join(os.path.dirname(__file__), "_probe_ground.laz")
        try:
            argv, out = self._run(
                "pdalcli:translate",
                {"filter": "Classification==2", "output": dest},
                input_layer=Layer(SOURCE, "/data/tile.las"),
            )
            self.assertIn(f"--output={dest}", argv)
            self.assertEqual(out.ref, dest)
            self.assertEqual(out.facet, "pointcloud")
        finally:
            if os.path.exists(dest):
                os.unlink(dest)

    def test_unknown_command_errors(self):
        with self.assertRaises(OpError) as ctx:
            self.be.run_raw(
                "pdalcli:frobnicate", {}, input_layer=Layer(SOURCE, "a.las")
            )
        self.assertIn("unknown pdal_wrench command", str(ctx.exception))

    def test_missing_input_errors(self):
        with mock.patch(
            "niva.engine.native.shutil.which", return_value="/opt/pdal_wrench"
        ):
            with self.assertRaises(OpError):
                self.be.run_raw(
                    "pdalcli:to_raster", {"attribute": "Z"}, input_layer=None
                )

    def test_rejects_bad_flag_key(self):
        with mock.patch(
            "niva.engine.native.shutil.which", return_value="/opt/pdal_wrench"
        ):
            with self.assertRaises(OpError):
                self.be.run_raw(
                    "pdalcli:to_raster",
                    {"--sneaky": "x"},
                    input_layer=Layer(SOURCE, "a.las"),
                )

    def test_nonzero_exit_surfaces_tail(self):
        with self.assertRaises(OpError) as ctx:
            self._run(
                "pdalcli:to_raster",
                {"attribute": "Z"},
                input_layer=Layer(SOURCE, "/data/tile.las"),
                rc=1,
                stderr="readers.las: bad file\n",
            )
        self.assertIn("bad file", str(ctx.exception))

    def test_bool_flag_rendering(self):
        self.assertEqual(self.be._pdal_flag("collar", True), "--collar")
        self.assertEqual(self.be._pdal_flag("collar", False), "--collar=false")
        self.assertEqual(self.be._pdal_flag("resolution", 1), "--resolution=1")


class TestGracefulDegradation(unittest.TestCase):
    def test_available_false_when_exe_missing(self):
        be = NativeToolBackend(MockBackend(), saga_cmd="definitely_not_a_real_tool_xyz")
        self.assertFalse(be.available("saga"))

    def test_missing_tool_gives_actionable_error_not_crash(self):
        be = NativeToolBackend(MockBackend(), saga_cmd="definitely_not_a_real_tool_xyz")
        with mock.patch("niva.engine.native.shutil.which", return_value=None):
            with self.assertRaises(OpError) as ctx:
                be.run_raw("saga:ta_morphometry:0", {"_out": "SLOPE"}, input_layer=None)
        self.assertIn("not found", str(ctx.exception))

    def test_non_native_flows_unaffected_when_tool_missing(self):
        # A missing saga_cmd must not break unrelated (delegated) flows.
        inner = MockBackend()
        be = NativeToolBackend(inner, saga_cmd="definitely_not_a_real_tool_xyz")
        be.run_raw(
            "native:buffer", {"DISTANCE": 5}, input_layer=Layer(SOURCE, "a.gpkg")
        )
        self.assertEqual(inner.calls[-1], ("run", "native:buffer", {"DISTANCE": 5}))

    def test_saga_failure_appends_version_hint(self):
        be = NativeToolBackend(MockBackend(), saga_cmd="saga_cmd")

        def _fake(argv, **kwargs):
            if "--version" in argv:
                return mock.Mock(
                    returncode=0, stdout="SAGA Version: 9.9.3\n", stderr=""
                )
            return mock.Mock(returncode=1, stdout="", stderr="tool not found\n")

        with (
            mock.patch("niva.engine.native.subprocess.run", _fake),
            mock.patch(
                "niva.engine.native.shutil.which", return_value="/usr/bin/saga_cmd"
            ),
        ):
            with self.assertRaises(OpError) as ctx:
                be.run_raw("saga:ta_morphometry:0", {"_out": "SLOPE"}, input_layer=None)
        msg = str(ctx.exception)
        self.assertIn("9.9.3", msg)  # detected version surfaced
        self.assertIn("differ between SAGA versions", msg)

    def test_otb_not_found_error_gets_setup_hint(self):
        inner = MockBackend()

        def _boom(algorithm, params, **kwargs):
            raise OpError(
                "algorithm 'otb:Foo' not found", algorithm=algorithm, backend="pyqgis"
            )

        inner.run_raw = _boom
        be = NativeToolBackend(inner)
        with self.assertRaises(OpError) as ctx:
            be.run_raw("otb:Foo", {}, input_layer=None)
        self.assertIn("OTB may be unconfigured", str(ctx.exception))


class TestRenderCall(unittest.TestCase):
    def test_saga_echo_is_saga_cmd_line(self):
        be = SagaCliBackend(MockBackend(), saga_cmd="saga_cmd")
        echo = be.render_call(
            "saga:ta_morphometry:0",
            {"_in": "ELEVATION", "_out": "SLOPE", "UNIT_SLOPE": 1},
        )
        self.assertEqual(echo, "saga_cmd ta_morphometry 0 -UNIT_SLOPE 1")

    def test_non_saga_echo_delegates(self):
        be = SagaCliBackend(MockBackend())
        echo = be.render_call("native:buffer", {"DISTANCE": 5})
        self.assertIn("processing.run", echo)  # inner backend's echo format


if __name__ == "__main__":
    unittest.main()
