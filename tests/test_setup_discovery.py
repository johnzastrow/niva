"""Locating QGIS from the setup core (``niva/setup/core.py``) on every OS, from one machine.

The Windows/macOS/Linux branches only run on their own OS in normal use, so a regression in one
would go unnoticed elsewhere. These fake ``os.name`` / ``sys.prefix`` / ``sys.executable`` and the
environment, and build real directory trees in a temp dir, so each branch is exercised anywhere.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from niva.setup import core


class _OsAs:
    """``os`` as seen by setup.core only, with a different ``name``. Patching the real
    ``os.name`` would make pathlib build WindowsPath objects, which cannot exist on POSIX."""

    def __init__(self, name):
        self.name = name

    def __getattr__(self, attr):
        return getattr(os, attr)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("@echo off\n", encoding="utf-8")
    return path


class _Windows(unittest.TestCase):
    """Run as if on Windows, with a clean environment and a fake install root."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="niva_win_"))
        env = {"SystemDrive": str(self.root / "nodrive")}
        self._patches = [
            mock.patch.object(core, "os", _OsAs("nt")),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(
                core.sys, "prefix", str(self.root / "unrelated" / "python")
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()


class TestFindQgisLauncherWindows(_Windows):
    def test_osgeo4w_root_wins(self):
        bat = _touch(self.root / "osgeo" / "bin" / "python-qgis.bat")
        _touch(self.root / "pf" / "QGIS 4.2.0" / "bin" / "python-qgis.bat")
        os.environ["OSGEO4W_ROOT"] = str(self.root / "osgeo")
        os.environ["ProgramFiles"] = str(self.root / "pf")
        self.assertEqual(core.find_qgis_launcher(), bat)

    def test_found_by_walking_up_from_qgis_python(self):
        # Inside QGIS: sys.prefix is <install>/apps/Python312; the .bat is <install>/bin/.
        bat = _touch(self.root / "QGIS" / "bin" / "python-qgis.bat")
        with mock.patch.object(
            core.sys, "prefix", str(self.root / "QGIS" / "apps" / "Python312")
        ):
            self.assertEqual(core.find_qgis_launcher(), bat)

    def test_program_files_prefers_the_newest_install(self):
        pf = self.root / "pf"
        _touch(pf / "QGIS 3.44.2" / "bin" / "python-qgis.bat")
        newest = _touch(pf / "QGIS 4.2.0" / "bin" / "python-qgis.bat")
        os.environ["ProgramFiles"] = str(pf)
        self.assertEqual(core.find_qgis_launcher(), newest)

    def test_newest_install_is_chosen_by_version_not_alphabetically(self):
        pf = self.root / "pf"
        _touch(pf / "QGIS 3.4.15" / "bin" / "python-qgis.bat")
        newer = _touch(pf / "QGIS 3.10.0" / "bin" / "python-qgis.bat")
        os.environ["ProgramFiles"] = str(pf)
        self.assertEqual(core.find_qgis_launcher(), newer)

    @unittest.skipUnless(
        sys.platform.startswith("win"), "drive-letter paths only exist on Windows"
    )
    def test_osgeo4w_default_location_on_the_system_drive(self):
        bat = _touch(self.root / "nodrive" / "OSGeo4W" / "bin" / "python-qgis.bat")
        self.assertEqual(core.find_qgis_launcher(), bat)

    def test_none_when_nothing_is_installed(self):
        os.environ["ProgramFiles"] = str(self.root / "empty-pf")
        self.assertIsNone(core.find_qgis_launcher())


class TestInvocationAndTargetWindows(_Windows):
    def test_invocation_refuses_without_a_qgis_launcher(self):
        # Never point the `niva` launcher at a non-QGIS interpreter on Windows.
        self.assertIsNone(core.qgis_invocation())

    def test_invocation_uses_the_launcher_when_found(self):
        bat = _touch(self.root / "osgeo" / "bin" / "python-qgis.bat")
        os.environ["OSGEO4W_ROOT"] = str(self.root / "osgeo")
        self.assertEqual(core.qgis_invocation(), str(bat))

    def test_launcher_target_is_under_localappdata(self):
        os.environ["LOCALAPPDATA"] = str(self.root / "local")
        self.assertEqual(
            core.launcher_target(), self.root / "local" / "niva" / "bin" / "niva.cmd"
        )

    def test_qgis_python_prefers_python_exe_in_the_prefix(self):
        prefix = self.root / "apps" / "Python312"
        exe = _touch(prefix / "python.exe")
        with (
            mock.patch.object(core.sys, "prefix", str(prefix)),
            mock.patch.object(
                core.sys, "executable", str(self.root / "bin" / "qgis-bin.exe")
            ),
        ):
            self.assertEqual(core.qgis_python(), exe)

    def test_qgis_python_falls_back_to_the_running_interpreter(self):
        with mock.patch.object(
            core.sys, "executable", str(self.root / "python3.12.exe")
        ):
            self.assertEqual(core.qgis_python(), self.root / "python3.12.exe")


class TestPosix(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="niva_posix_"))
        self._name = mock.patch.object(core, "os", _OsAs("posix"))
        self._name.start()

    def tearDown(self):
        self._name.stop()

    def test_no_bat_launcher_outside_windows(self):
        self.assertIsNone(core.find_qgis_launcher())

    def test_qgis_python_is_the_interpreter_when_it_is_python(self):
        with mock.patch.object(core.sys, "executable", "/usr/bin/python3"):
            self.assertEqual(core.qgis_python(), Path("/usr/bin/python3"))

    def test_inside_the_qgis_app_python_is_found_in_the_prefix(self):
        # e.g. macOS: sys.executable is the QGIS app binary, not python.
        py = _touch(self.root / "bin" / "python3")
        with (
            mock.patch.object(
                core.sys, "executable", str(self.root / "MacOS" / "QGIS")
            ),
            mock.patch.object(core.sys, "prefix", str(self.root)),
        ):
            self.assertEqual(core.qgis_python(), py)

    def test_invocation_is_the_qgis_python(self):
        with mock.patch.object(core.sys, "executable", "/usr/bin/python3"):
            self.assertEqual(core.qgis_invocation(), "/usr/bin/python3")

    def test_launcher_target_is_in_local_bin(self):
        with mock.patch.object(core.Path, "home", return_value=self.root):
            self.assertEqual(
                core.launcher_target(), self.root / ".local" / "bin" / "niva"
            )


class TestPlatformName(unittest.TestCase):
    def test_platform_names(self):
        for sysplat, expected in (
            ("win32", "windows"),
            ("darwin", "macos"),
            ("linux", "linux"),
        ):
            with (
                self.subTest(sysplat=sysplat),
                mock.patch.object(core.sys, "platform", sysplat),
            ):
                self.assertEqual(core._platform(), expected)


if __name__ == "__main__":
    unittest.main()
