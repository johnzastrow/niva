"""Tests for niva.credentials — the shared secret resolver (env override, else QGIS auth store).

Stdlib ``unittest`` only. The QGIS auth-store side is mocked so these run without QGIS and never
touch a real auth DB.
"""

from __future__ import annotations

import unittest
from unittest import mock

from niva import credentials


class TestGetSecret(unittest.TestCase):
    def test_env_var_wins_as_override(self):
        with mock.patch.object(
            credentials, "_from_authstore", return_value="FROM_STORE"
        ):
            got = credentials.get_secret(
                "NIVA_NTFY_TOKEN", "ntfy_token", {"NIVA_NTFY_TOKEN": "FROM_ENV"}
            )
        self.assertEqual(got, "FROM_ENV")

    def test_falls_back_to_auth_store(self):
        with mock.patch.object(
            credentials, "_from_authstore", return_value="FROM_STORE"
        ):
            got = credentials.get_secret("NIVA_NTFY_TOKEN", "ntfy_token", {})
        self.assertEqual(got, "FROM_STORE")

    def test_none_when_both_absent(self):
        with mock.patch.object(credentials, "_from_authstore", return_value=None):
            got = credentials.get_secret("NIVA_SMTP_PASSWORD", "smtp_password", {})
        self.assertIsNone(got)

    def test_empty_env_value_falls_through_to_store(self):
        # An empty string in the environment must not shadow a real stored secret.
        with mock.patch.object(credentials, "_from_authstore", return_value="STORE"):
            got = credentials.get_secret(
                "NIVA_NTFY_TOKEN", "ntfy_token", {"NIVA_NTFY_TOKEN": ""}
            )
        self.assertEqual(got, "STORE")

    def test_convenience_wrappers(self):
        with mock.patch.object(credentials, "_from_authstore", return_value="S"):
            self.assertEqual(credentials.ntfy_token({}), "S")
            self.assertEqual(credentials.smtp_password({}), "S")


class TestFromAuthStore(unittest.TestCase):
    def test_unknown_kind_is_none(self):
        self.assertIsNone(credentials._from_authstore("not_a_kind"))

    def test_no_qgis_returns_none(self):
        # Simulate an interpreter without QGIS: the import inside _from_authstore fails.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "qgis.core" or name.startswith("qgis"):
                raise ImportError("no qgis here")
            return real_import(name, *a, **k)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            self.assertIsNone(credentials._from_authstore("ntfy_token"))


class TestKeysShared(unittest.TestCase):
    def test_authcfg_keys_match_plugin_contract(self):
        # These QgsSettings keys are the contract the plugin writes and the CLI reads.
        self.assertEqual(credentials.SMTP_AUTHCFG_KEY, "niva/smtp_authcfg")
        self.assertEqual(credentials.NTFY_AUTHCFG_KEY, "niva/ntfy_authcfg")


if __name__ == "__main__":
    unittest.main()
