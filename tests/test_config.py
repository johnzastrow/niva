"""Tests for the portable config store (`niva.config`, docs/planning/20 §9). Pure Python,
no QGIS. Each test points the config dir at a temp directory."""

import os
import tempfile
import tomllib
import unittest
from unittest import mock

from niva import config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            config, "config_dir", return_value=self._tmp.name
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_path_is_config_toml_under_dir(self):
        self.assertTrue(config.config_path().endswith("config.toml"))
        self.assertTrue(config.config_path().startswith(self._tmp.name))

    def test_missing_file_loads_empty(self):
        self.assertEqual(config.load(), {})

    def test_set_get_roundtrip(self):
        config.set_key("log_dir", "/var/niva/logs")
        self.assertEqual(config.get("log_dir"), "/var/niva/logs")
        self.assertEqual(config.load()["log_dir"], "/var/niva/logs")

    def test_written_file_is_valid_toml(self):
        config.set_key("qgis_python", "/usr/bin/python3")
        with open(config.config_path(), "rb") as fh:
            data = tomllib.load(fh)  # must parse — proves we wrote valid TOML
        self.assertEqual(data["qgis_python"], "/usr/bin/python3")

    def test_secret_key_is_refused(self):
        with self.assertRaises(ValueError):
            config.set_key("ntfy_token", "secret123")
        self.assertIsNone(config.get("ntfy_token"))  # nothing written

    def test_unset_removes_key(self):
        config.set_key("smtp_host", "smtp.example.com")
        config.unset_key("smtp_host")
        self.assertIsNone(config.get("smtp_host"))

    def test_special_chars_roundtrip(self):
        weird = 'C:\\Program Files\\QGIS "3.40"\\python.exe'
        config.set_key("qgis_python", weird)
        self.assertEqual(config.get("qgis_python"), weird)  # escaping is correct

    def test_template_lists_every_known_key(self):
        t = config.template()
        for key in config.KNOWN_KEYS:
            self.assertIn(key, t)
        self.assertIn("do NOT belong here", t)  # the secrets note

    def test_init_writes_when_absent(self):
        path, written = config.write_template()
        self.assertTrue(written)
        self.assertTrue(os.path.exists(path))
        self.assertIn("qgis_python", open(path, encoding="utf-8").read())
        self.assertEqual(
            config.load(), {}
        )  # template is all-commented → nothing active

    def test_init_does_not_clobber_existing(self):
        config.set_key("log_dir", "/keep/me")
        _path, written = config.write_template()
        self.assertFalse(written)
        self.assertEqual(config.get("log_dir"), "/keep/me")

    def test_init_force_overwrites(self):
        config.set_key("log_dir", "/gone")
        _path, written = config.write_template(force=True)
        self.assertTrue(written)
        self.assertIsNone(
            config.get("log_dir")
        )  # replaced by the all-commented template


if __name__ == "__main__":
    unittest.main()
