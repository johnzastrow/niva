"""Tests for the setup-core (planning doc 21).

Stdlib ``unittest`` only (the project convention — runs in QGIS's Python with zero install). The
pure PATH string logic is exercised directly; ``install_command`` / ``uninstall_command`` run
against an **in-memory** PATH store and a tmp launcher, so the real Windows registry / user PATH is
never modified.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from niva.setup import core, pathenv


class TestPurePathLogic(unittest.TestCase):
    def test_append_to_empty(self):
        self.assertEqual(
            pathenv.path_append("", r"C:\niva\bin", sep=";"), (r"C:\niva\bin", True)
        )

    def test_append_adds_at_end(self):
        new, changed = pathenv.path_append(r"C:\a;C:\b", r"C:\niva\bin", sep=";")
        self.assertTrue(changed)
        self.assertEqual(new, r"C:\a;C:\b;C:\niva\bin")  # END, never prepended

    def test_append_idempotent(self):
        cur = r"C:\a;C:\niva\bin;C:\b"
        self.assertEqual(
            pathenv.path_append(cur, r"C:\niva\bin", sep=";"), (cur, False)
        )

    def test_append_preserves_existing_verbatim(self):
        cur = r"C:\a;;C:\b;"  # messy PATH must not be reformatted
        new, changed = pathenv.path_append(cur, r"C:\niva\bin", sep=";")
        self.assertTrue(changed)
        self.assertEqual(new, r"C:\a;;C:\b;C:\niva\bin")

    def test_append_no_double_separator(self):
        new, _ = pathenv.path_append(r"C:\a;", r"C:\niva\bin", sep=";")
        self.assertEqual(new, r"C:\a;C:\niva\bin")

    @unittest.skipUnless(os.name == "nt", "case-insensitive PATH is a Windows behavior")
    def test_contains_case_insensitive_on_windows(self):
        self.assertTrue(pathenv.is_on_path(r"C:\NIVA\BIN", r"c:\niva\bin", sep=";"))

    def test_remove(self):
        new, changed = pathenv.path_remove(
            r"C:\a;C:\niva\bin;C:\b", r"C:\niva\bin", sep=";"
        )
        self.assertTrue(changed)
        self.assertEqual(new, r"C:\a;C:\b")

    def test_remove_absent_is_noop(self):
        cur = r"C:\a;C:\b"
        self.assertEqual(
            pathenv.path_remove(cur, r"C:\niva\bin", sep=";"), (cur, False)
        )


class TestLauncherBody(unittest.TestCase):
    def test_windows_forwards_to_module(self):
        body = pathenv.launcher_body(r"C:\OSGeo4W\bin\python-qgis.bat", windows=True)
        self.assertIn("-m niva.cli.main %*", body)
        self.assertIn(r"C:\OSGeo4W\bin\python-qgis.bat", body)

    def test_posix_forwards_to_module(self):
        body = pathenv.launcher_body("/usr/bin/python3", windows=False)
        self.assertTrue(body.startswith("#!/usr/bin/env bash"))
        self.assertIn('exec "/usr/bin/python3" -m niva.cli.main "$@"', body)

    def test_write_launcher_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "bin" / ("niva.cmd" if os.name == "nt" else "niva")
            self.assertTrue(pathenv.write_launcher(target, "PY"))  # created
            self.assertTrue(target.exists())
            self.assertFalse(pathenv.write_launcher(target, "PY"))  # unchanged
            self.assertTrue(pathenv.write_launcher(target, "PY2"))  # content changed


class TestDetection(unittest.TestCase):
    def test_launcher_target_shape(self):
        target = core.launcher_target()
        self.assertEqual(target.parent.name, "bin")
        self.assertEqual(target.name, "niva.cmd" if os.name == "nt" else "niva")

    def test_detect_environment(self):
        rep = core.detect_environment()
        self.assertIn(rep.platform, {"windows", "macos", "linux"})
        self.assertTrue(str(rep.qgis_python))


@contextlib.contextmanager
def fake_pathstore(tmpdir):
    """Redirect the launcher to tmp and the persisted PATH to an in-memory string."""
    store = {"path": ""}
    target = Path(tmpdir) / "niva" / "bin" / ("niva.cmd" if os.name == "nt" else "niva")
    with contextlib.ExitStack() as es:
        es.enter_context(
            mock.patch.object(core, "launcher_target", return_value=target)
        )
        es.enter_context(
            mock.patch.object(
                pathenv, "read_user_path", side_effect=lambda: store["path"]
            )
        )
        es.enter_context(
            mock.patch.object(
                pathenv,
                "_write_user_path_windows",
                side_effect=lambda v: store.__setitem__("path", v),
            )
        )
        es.enter_context(
            mock.patch.object(
                pathenv,
                "_append_posix_rc",
                side_effect=lambda dcy: store.__setitem__(
                    "path", pathenv.path_append(store["path"], str(dcy))[0]
                ),
            )
        )
        es.enter_context(
            mock.patch.object(
                pathenv,
                "_remove_posix_rc",
                side_effect=lambda dcy: store.__setitem__(
                    "path", pathenv.path_remove(store["path"], str(dcy))[0]
                ),
            )
        )
        es.enter_context(mock.patch.object(pathenv, "broadcast_env_change"))
        yield store, target


class TestOrchestration(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, fake_pathstore(d) as (store, target):
            res = core.install_command(dry_run=True)
            self.assertTrue(res.ok)
            self.assertTrue(res.changed)
            self.assertFalse(target.exists())
            self.assertEqual(store["path"], "")

    def test_install_refuses_without_qgis_launcher(self):
        # If no python-qgis.bat can be found, we must NOT write a launcher to a non-QGIS Python.
        with tempfile.TemporaryDirectory() as d, fake_pathstore(d) as (store, target):
            with mock.patch.object(core, "qgis_invocation", return_value=None):
                res = core.install_command()
            self.assertFalse(res.ok)
            self.assertFalse(res.changed)
            self.assertFalse(target.exists())
            self.assertEqual(store["path"], "")

    def test_install_idempotent_then_uninstall(self):
        with tempfile.TemporaryDirectory() as d, fake_pathstore(d) as (store, target):
            res = core.install_command()
            self.assertTrue(res.ok and res.changed)
            self.assertTrue(target.exists())
            self.assertTrue(pathenv.is_on_path(store["path"], target.parent))

            res2 = core.install_command()  # idempotent
            self.assertTrue(res2.ok)
            self.assertFalse(res2.changed)

            res3 = core.uninstall_command()
            self.assertTrue(res3.ok and res3.changed)
            self.assertFalse(target.exists())
            self.assertFalse(pathenv.is_on_path(store["path"], target.parent))


class TestPosixRc(unittest.TestCase):
    def test_append_then_remove_roundtrip(self):
        # Against a temp rc (never the real ~/.bashrc). Verifies --remove actually cleans POSIX PATH.
        with tempfile.TemporaryDirectory() as d:
            rc = Path(d) / ".bashrc"
            rc.write_text("export FOO=1\n", encoding="utf-8")
            marker = "# added by `niva setup command`"
            bindir = Path("/opt/niva/bin")
            # Assert on the marker + `:$PATH` sentinel, not the dir string — Path() renders with
            # backslashes on Windows, but removal keys on the marker, so this stays OS-independent.
            with mock.patch.object(pathenv, "_rc_marker", return_value=(rc, marker)):
                pathenv._append_posix_rc(bindir)
                after_add = rc.read_text(encoding="utf-8")
                self.assertIn(marker, after_add)
                self.assertIn(":$PATH", after_add)  # our export line was added
                pathenv._remove_posix_rc(bindir)
            txt = rc.read_text(encoding="utf-8")
            self.assertNotIn(marker, txt)
            self.assertNotIn(":$PATH", txt)  # our export line removed
            self.assertIn("export FOO=1", txt)  # unrelated content untouched


if __name__ == "__main__":
    unittest.main()
