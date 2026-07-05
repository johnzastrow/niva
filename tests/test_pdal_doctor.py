"""Tests for `niva pdal` — the point-cloud backend helper (niva/pdal_doctor.py).

Pure-logic + dispatch coverage; no QGIS and no real pdal_wrench required. A tiny fake
executable stands in for pdal_wrench so discovery/version paths are exercised offline.
"""

import os
import stat
import tempfile
import unittest
from unittest import mock

from niva import pdal_doctor as pd


def _make_fake_exe(dir_: str, name: str, prints: str) -> str:
    path = os.path.join(dir_, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'#!/bin/sh\necho "{prints}"\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class TestDiscovery(unittest.TestCase):
    def test_os_key_is_one_of_three(self):
        self.assertIn(pd._os_key(), ("windows", "macos", "linux"))

    def test_env_var_beats_path(self):
        # QGIS/niva read $QGIS_WRENCH_EXECUTABLE — discovery must prefer it and report it.
        if pd._os_key() == "windows":
            self.skipTest("shell-script fake exe is POSIX-only")
        with tempfile.TemporaryDirectory() as td:
            exe = _make_fake_exe(td, "pdal_wrench", "pdal_wrench version: 9.9.9")
            with mock.patch.dict(
                os.environ, {"QGIS_WRENCH_EXECUTABLE": exe}, clear=False
            ):
                found, how = pd._find(pd._wrench_name())
            self.assertEqual(found, exe)
            self.assertEqual(how, "QGIS_WRENCH_EXECUTABLE")

    def test_version_reads_first_line(self):
        if pd._os_key() == "windows":
            self.skipTest("shell-script fake exe is POSIX-only")
        with tempfile.TemporaryDirectory() as td:
            exe = _make_fake_exe(td, "pdal_wrench", "pdal_wrench version: 9.9.9")
            self.assertEqual(
                pd._version(exe, ["--version"]), "pdal_wrench version: 9.9.9"
            )

    def test_version_none_when_not_executable(self):
        self.assertIsNone(
            pd._version("/definitely/not/here/pdal_wrench", ["--version"])
        )


class TestSynthesize(unittest.TestCase):
    def test_pipeline_json_is_valid_with_backslash_path(self):
        # The faux pipeline must serialize a Windows-style output path as valid JSON
        # (a raw C:\… embed is an invalid \escape). Capture what gets written.
        import json

        written = {}

        def _capture_run(argv, **kw):
            # argv = [pdal, "pipeline", <pipeline.json>] — read + validate it
            with open(argv[2], encoding="utf-8") as fh:
                written["stages"] = json.load(fh)  # raises if invalid JSON
            return mock.Mock(returncode=1)  # force None return; we only want the JSON

        with (
            mock.patch.object(pd, "_find", return_value=("/opt/pdal", "PATH")),
            mock.patch.object(pd, "_os_key", return_value="windows"),
            mock.patch("niva.pdal_doctor.subprocess.run", _capture_run),
            tempfile.TemporaryDirectory() as td,
        ):
            pd._synthesize_las(td)
        types = [s["type"] for s in written["stages"]]
        self.assertEqual(types, ["readers.faux", "writers.las"])
        self.assertTrue(written["stages"][1]["filename"].endswith("faux.las"))


class TestDispatch(unittest.TestCase):
    def test_setup_returns_zero(self):
        self.assertEqual(pd.run(["setup"]), 0)

    def test_unknown_action_returns_two(self):
        self.assertEqual(pd.run(["frobnicate"]), 2)

    def test_default_action_is_check(self):
        # No args → check; returns 0 (wired/ready) or 1 (missing) — never crashes.
        with mock.patch.object(pd, "_cmd_check", return_value=0) as m:
            self.assertEqual(pd.run([]), 0)
            m.assert_called_once()

    def test_check_verdict_ready_when_env_var_set(self):
        if pd._os_key() == "windows":
            self.skipTest("shell-script fake exe is POSIX-only")
        with tempfile.TemporaryDirectory() as td:
            exe = _make_fake_exe(td, "pdal_wrench", "pdal_wrench version: 1.5.1")
            env = {"QGIS_WRENCH_EXECUTABLE": exe, "PATH": "/usr/bin:/bin"}
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(
                    pd, "_qgis_pointcloud_status", return_value=(None, {})
                ),
            ):
                self.assertEqual(pd._cmd_check(), 0)  # ready

    def test_check_reports_missing_when_absent(self):
        # No wrench anywhere: env cleared, PATH empty-ish, no candidate dirs.
        with (
            mock.patch.dict(os.environ, {"PATH": ""}, clear=False),
            mock.patch.object(os.environ, "get", return_value=None),
            mock.patch.object(pd, "_candidate_dirs", return_value=[]),
            mock.patch.object(pd, "_qgis_pointcloud_status", return_value=(None, {})),
        ):
            self.assertEqual(pd._cmd_check(), 1)  # missing → nonzero


if __name__ == "__main__":
    unittest.main()
