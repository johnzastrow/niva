"""`niva setup wizard` — the interactive config walk-through. Input is scripted and the config
dir is redirected to a temp dir, so the real user config is never touched and no TTY is needed."""

import builtins
import contextlib
import io
import tempfile
import unittest
from unittest import mock

import niva.config as cfg
from niva.cli.main import _setup_wizard


class TestSetupWizard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_wiz_")

    def _run(self, responses):
        it = iter(responses)

        def fake_input(_prompt=""):
            try:
                return next(it)
            except StopIteration as e:
                raise EOFError from e  # end of scripted input → wizard stops

        with (
            mock.patch("niva.config.config_dir", return_value=self.tmp),
            mock.patch.object(builtins, "input", fake_input),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            rc = _setup_wizard()
            return rc, out.getvalue()

    def _load(self):
        with mock.patch("niva.config.config_dir", return_value=self.tmp):
            return cfg.load()

    def test_typed_values_are_set_blanks_kept(self):
        # key 1 (qgis_python) kept blank; key 2 (log_dir) set; then EOF
        rc, _ = self._run(["", "~/logs"])
        self.assertEqual(rc, 0)
        data = self._load()
        self.assertEqual(data.get("log_dir"), "~/logs")
        self.assertNotIn("qgis_python", data)

    def test_dash_clears_an_existing_key(self):
        with mock.patch("niva.config.config_dir", return_value=self.tmp):
            cfg.set_key("log_dir", "~/logs")
        self._run(["", "-"])  # keep qgis_python, clear log_dir
        self.assertNotIn("log_dir", self._load())

    def test_secrets_are_never_written(self):
        self._run([""] * len(cfg.KNOWN_KEYS))  # keep everything
        data = self._load()
        for skey in cfg.SECRET_KEYS:
            self.assertNotIn(skey, data)

    def test_reminds_about_secret_env_vars(self):
        _, out = self._run([])  # immediate EOF → straight to the summary
        for senv in cfg.SECRET_KEYS.values():
            self.assertIn(senv, out)


if __name__ == "__main__":
    unittest.main()
