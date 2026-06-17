"""Raster scratch relocation + cleanup (no QGIS needed).

``scratch_dir`` / ``_temp_path`` / ``PyqgisBackend.purge_scratch`` are all pure
os/tempfile logic with no ``qgis`` import, so they run on a plain interpreter. These
guard the fix for the "disk quota exceeded" crash: big raster intermediates must be
relocatable off a small tmpfs (``NIVA_TMPDIR``) and deleted when a run ends.
"""

import os
import tempfile
import unittest

from niva.engine.layer import SOURCE, Layer
from niva.engine.pyqgis import PyqgisBackend, _command_failure, scratch_dir
from niva.errors import OpError


class TestScratchDir(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("NIVA_TMPDIR", "CPL_TMPDIR")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_falls_back_to_system_temp_when_unset(self):
        os.environ.pop("NIVA_TMPDIR", None)
        self.assertEqual(scratch_dir(), tempfile.gettempdir())

    def test_honours_niva_tmpdir_and_points_gdal_at_it(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "scratch")
            os.environ["NIVA_TMPDIR"] = target
            os.environ.pop("CPL_TMPDIR", None)
            got = scratch_dir()
            self.assertEqual(got, target)
            self.assertTrue(os.path.isdir(target))  # created on demand
            self.assertEqual(os.environ.get("CPL_TMPDIR"), target)  # GDAL scratch too

    def test_unwritable_niva_tmpdir_falls_back(self):
        # A path under an existing *file* can't be made into a dir → graceful fallback.
        with tempfile.NamedTemporaryFile() as f:
            os.environ["NIVA_TMPDIR"] = os.path.join(f.name, "nope")
            self.assertEqual(scratch_dir(), tempfile.gettempdir())


class TestPurgeScratch(unittest.TestCase):
    def _touch(self, path):
        with open(path, "w") as fh:
            fh.write("x")

    def test_purges_intermediates_but_spares_the_final_layer(self):
        with tempfile.TemporaryDirectory() as d:
            inter = os.path.join(d, "inter.tif")
            final = os.path.join(d, "final.tif")
            self._touch(inter)
            self._touch(inter + ".aux.xml")  # sidecar should go too
            self._touch(final)

            be = PyqgisBackend()
            be._scratch = [inter, final]
            be.purge_scratch(keep=Layer(SOURCE, final, facet="raster"))

            self.assertFalse(os.path.exists(inter))
            self.assertFalse(os.path.exists(inter + ".aux.xml"))
            self.assertTrue(os.path.exists(final))         # the kept final survives
            self.assertEqual(be._scratch, [final])         # tracking trimmed to survivors

    def test_keep_none_purges_everything(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.tif"), os.path.join(d, "b.tif")
            self._touch(a)
            self._touch(b)
            be = PyqgisBackend()
            be._scratch = [a, b]
            be.purge_scratch(keep=None)  # e.g. a failed run — strand nothing
            self.assertFalse(os.path.exists(a))
            self.assertFalse(os.path.exists(b))
            self.assertEqual(be._scratch, [])

    def test_missing_file_is_not_an_error(self):
        be = PyqgisBackend()
        be._scratch = [os.path.join(tempfile.gettempdir(), "niva-does-not-exist.tif")]
        be.purge_scratch(keep=None)  # must not raise
        self.assertEqual(be._scratch, [])

    def test_remove_dir_drops_empty_niva_scratch_dir_on_success(self):
        with tempfile.TemporaryDirectory() as parent:
            scratch = os.path.join(parent, "niva_scratch")
            os.makedirs(scratch)
            f = os.path.join(scratch, "a.tif")
            with open(f, "w") as fh:
                fh.write("x")
            os.environ["NIVA_TMPDIR"] = scratch
            try:
                be = PyqgisBackend()
                be._scratch = [f]
                be.purge_scratch(keep=None, remove_dir=True)  # clean, successful run
            finally:
                os.environ.pop("NIVA_TMPDIR", None)
            self.assertFalse(os.path.exists(scratch))  # empty niva dir removed too

    def test_remove_dir_never_touches_a_nonempty_or_system_dir(self):
        with tempfile.TemporaryDirectory() as scratch:
            mine = os.path.join(scratch, "mine.tif")
            other = os.path.join(scratch, "user-file.txt")  # not niva's
            for p in (mine, other):
                with open(p, "w") as fh:
                    fh.write("x")
            os.environ["NIVA_TMPDIR"] = scratch
            try:
                be = PyqgisBackend()
                be._scratch = [mine]
                be.purge_scratch(keep=None, remove_dir=True)
            finally:
                os.environ.pop("NIVA_TMPDIR", None)
            self.assertTrue(os.path.isdir(scratch))      # not removed — still has user-file
            self.assertTrue(os.path.exists(other))       # the unrelated file is untouched

    def test_remove_dir_no_op_without_niva_tmpdir(self):
        # NIVA_TMPDIR unset → scratch is the shared system temp; must never be rmdir'd.
        os.environ.pop("NIVA_TMPDIR", None)
        be = PyqgisBackend()
        be._scratch = []
        be.purge_scratch(keep=None, remove_dir=True)  # must not raise / must be harmless
        self.assertTrue(os.path.isdir(tempfile.gettempdir()))

    def test_temp_path_is_tracked_so_it_gets_purged(self):
        # Every niva-allocated intermediate (raster output AND lossless-retry .gpkg)
        # must be tracked, else it leaks into the scratch dir (the mixed-geometry case).
        be = PyqgisBackend()
        with tempfile.TemporaryDirectory() as d:
            os.environ["NIVA_TMPDIR"] = d
            try:
                p = be._temp_path(".gpkg")
            finally:
                os.environ.pop("NIVA_TMPDIR", None)
            self.assertIn(p, be._scratch)
            self.assertEqual(os.path.dirname(p), d)


class _FakeFeedback:
    """Duck-typed stand-in for _NivaFeedback (which needs QGIS to construct)."""

    def __init__(self, err):
        self._err = err

    def command_failure(self):
        return self._err


class TestCommandFailureDetection(unittest.TestCase):
    """A GDAL/OGR algorithm can exit nonzero yet still return a result from
    processing.run; niva must treat 'Process returned error code N' as a failure
    rather than reporting a false success (the orthophoto-clip corruption case)."""

    def test_detects_nonzero_gdal_exit(self):
        errors = ["ERROR 1: Stream too short", "Process returned error code 1"]
        self.assertEqual(_command_failure(errors), "Process returned error code 1")

    def test_ignores_zero_exit_and_plain_errors(self):
        self.assertIsNone(_command_failure([]))
        self.assertIsNone(_command_failure(["Process returned error code 0"]))
        self.assertIsNone(_command_failure(["ERROR 1: some recoverable warning"]))

    def test_raise_on_command_failure_raises_for_nonzero(self):
        with self.assertRaises(OpError) as ctx:
            PyqgisBackend._raise_on_command_failure(
                "gdal:warpreproject", {"x": 1},
                _FakeFeedback("Process returned error code 1"))
        self.assertIn("did not complete", str(ctx.exception))

    def test_raise_on_command_failure_is_quiet_when_clean(self):
        PyqgisBackend._raise_on_command_failure("gdal:warpreproject", {}, _FakeFeedback(None))
        PyqgisBackend._raise_on_command_failure("gdal:warpreproject", {}, None)  # no feedback


if __name__ == "__main__":
    unittest.main()
