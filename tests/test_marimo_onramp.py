"""Tests for niva.setup.marimo — the optional marimo on-ramp (planning doc 21 §10).

Stdlib ``unittest``. QGIS-specific bits (version, plugins dir, ``pyplugin_installer``, the marimo-qgis
import + its ``install_marimo()`` call) are mocked; the real in-QGIS install needs a live QGIS 4.x.
"""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from niva.setup import marimo


class TestPreflight(unittest.TestCase):
    def test_not_in_qgis(self):
        with mock.patch.object(marimo, "_qgis_version_int", return_value=None):
            res = marimo.preflight()
        self.assertIsNotNone(res)
        self.assertIn("inside QGIS", res.message)

    def test_below_qgis_4(self):
        with mock.patch.object(marimo, "_qgis_version_int", return_value=30400):
            res = marimo.preflight()
        self.assertIsNotNone(res)
        self.assertIn("4.0+", res.message)

    def test_ok_returns_none(self):
        with (
            mock.patch.object(marimo, "_qgis_version_int", return_value=40200),
            mock.patch.object(marimo, "_plugins_dir", return_value=Path("x")),
        ):
            self.assertIsNone(marimo.preflight())


class TestDetection(unittest.TestCase):
    def test_find_plugin_dir(self):
        with tempfile.TemporaryDirectory() as d:
            plugins = Path(d)
            proc = plugins / "marimo_launcher" / "ui" / "process.py"
            proc.parent.mkdir(parents=True)
            proc.write_text("class MarimoProcessManager:\n    pass\n", encoding="utf-8")
            self.assertEqual(marimo._find_plugin_dir(plugins), plugins / "marimo_launcher")

    def test_is_installed(self):
        with (
            mock.patch.object(marimo, "_plugins_dir", return_value=Path("p")),
            mock.patch.object(marimo, "_find_plugin_dir", return_value=Path("p/marimo_launcher")),
        ):
            self.assertTrue(marimo.is_installed())
        with (
            mock.patch.object(marimo, "_plugins_dir", return_value=Path("p")),
            mock.patch.object(marimo, "_find_plugin_dir", return_value=None),
        ):
            self.assertFalse(marimo.is_installed())


class TestDownloadRelease(unittest.TestCase):
    @staticmethod
    def _fake_urlopen(data):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return data

        return lambda *a, **k: FakeResp()

    def test_downloads_to_dest(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "marimo_launcher.zip"
            with mock.patch("urllib.request.urlopen", side_effect=self._fake_urlopen(b"ZIPBYTES")):
                err = marimo.download_release(dest)
            self.assertIsNone(err)
            self.assertEqual(dest.read_bytes(), b"ZIPBYTES")

    def test_download_failure_returns_message(self):
        def boom(*a, **k):
            raise OSError("no network")

        with tempfile.TemporaryDirectory() as d:
            with mock.patch("urllib.request.urlopen", side_effect=boom):
                err = marimo.download_release(Path(d) / "z.zip")
            self.assertIn("no network", err)


class TestInstallFromZip(unittest.TestCase):
    def test_uses_qgis_plugin_installer(self):
        fake = types.ModuleType("pyplugin_installer")
        calls = {}
        inst = types.SimpleNamespace(installFromZipFile=lambda p: calls.setdefault("path", p))
        fake.instance = lambda: inst
        with mock.patch.dict(sys.modules, {"pyplugin_installer": fake}):
            ok = marimo.install_from_zip(Path("marimo_launcher.zip"))
        self.assertTrue(ok)
        self.assertEqual(calls["path"], "marimo_launcher.zip")

    def test_returns_false_without_qgis(self):
        # No pyplugin_installer available -> False (not an exception).
        with mock.patch.dict(sys.modules, {"pyplugin_installer": None}):
            self.assertFalse(marimo.install_from_zip(Path("z.zip")))


class TestOrchestration(unittest.TestCase):
    def test_dry_run_reports_without_acting(self):
        with (
            mock.patch.object(marimo, "preflight", return_value=None),
            mock.patch.object(marimo, "is_installed", return_value=False),
            mock.patch.object(marimo, "download_release") as dl,
            mock.patch.object(marimo, "install_from_zip") as inst,
            mock.patch.object(marimo, "start_marimo_install") as start,
        ):
            res = marimo.install_marimo_qgis(dry_run=True)
        self.assertTrue(res.ok)
        self.assertIn("Would", res.message)
        dl.assert_not_called()
        inst.assert_not_called()
        start.assert_not_called()

    def test_already_installed_just_starts_marimo(self):
        with (
            mock.patch.object(marimo, "preflight", return_value=None),
            mock.patch.object(marimo, "is_installed", return_value=True),
            mock.patch.object(marimo, "download_release") as dl,
            mock.patch.object(marimo, "install_from_zip") as inst,
            mock.patch.object(marimo, "start_marimo_install", return_value=(True, "marimo installing.")),
        ):
            res = marimo.install_marimo_qgis()
        self.assertTrue(res.ok)
        dl.assert_not_called()
        inst.assert_not_called()

    def test_absent_downloads_installs_then_starts(self):
        with (
            mock.patch.object(marimo, "preflight", return_value=None),
            mock.patch.object(marimo, "is_installed", return_value=False),
            mock.patch.object(marimo, "download_release", return_value=None) as dl,
            mock.patch.object(marimo, "install_from_zip", return_value=True) as inst,
            mock.patch.object(marimo, "start_marimo_install", return_value=(True, "marimo installing.")) as start,
        ):
            res = marimo.install_marimo_qgis()
        self.assertTrue(res.ok)
        dl.assert_called_once()
        inst.assert_called_once()
        start.assert_called_once()

    def test_download_failure_aborts(self):
        with (
            mock.patch.object(marimo, "preflight", return_value=None),
            mock.patch.object(marimo, "is_installed", return_value=False),
            mock.patch.object(marimo, "download_release", return_value="boom"),
            mock.patch.object(marimo, "install_from_zip") as inst,
        ):
            res = marimo.install_marimo_qgis()
        self.assertFalse(res.ok)
        inst.assert_not_called()


if __name__ == "__main__":
    unittest.main()
