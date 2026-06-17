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
from niva.engine.pyqgis import PyqgisBackend, scratch_dir


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


if __name__ == "__main__":
    unittest.main()
