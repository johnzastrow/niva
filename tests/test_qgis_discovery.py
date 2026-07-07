"""QGIS binding auto-discovery — the pure path logic that lets a bare `pip install qgis-niva`
into a system Python find QGIS's `qgis` package (e.g. Ubuntu's /usr/share/qgis/python) without
a hand-set PYTHONPATH. No QGIS needed: these test the directory selection only."""

import os
import tempfile
import unittest

from niva.engine.pyqgis import _qgis_python_dirs


class TestQgisPythonDirs(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("NIVA_QGIS_PYTHONPATH")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("NIVA_QGIS_PYTHONPATH", None)
        else:
            os.environ["NIVA_QGIS_PYTHONPATH"] = self._saved

    def test_env_override_existing_dir_is_included_first(self):
        d = tempfile.mkdtemp(prefix="niva_qgisdir_")
        os.environ["NIVA_QGIS_PYTHONPATH"] = d
        dirs = _qgis_python_dirs()
        self.assertIn(d, dirs)
        self.assertEqual(dirs[0], d)  # env override ranks ahead of OS defaults

    def test_nonexistent_dirs_are_filtered_out(self):
        os.environ["NIVA_QGIS_PYTHONPATH"] = "/no/such/qgis/python"
        self.assertNotIn("/no/such/qgis/python", _qgis_python_dirs())

    def test_result_has_no_duplicates(self):
        d = tempfile.mkdtemp(prefix="niva_qgisdir_")
        os.environ["NIVA_QGIS_PYTHONPATH"] = os.pathsep.join([d, d])
        dirs = _qgis_python_dirs()
        self.assertEqual(len(dirs), len(set(dirs)))


if __name__ == "__main__":
    unittest.main()
