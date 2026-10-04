"""The plugin's auth-store helper (``plugin/authstore.py``).

``QgsAuthManager.storeAuthenticationConfig`` returns ``(ok, config)`` in PyQGIS. A tuple is always
truthy, so the plugin used to treat a *failed* store as success (and could record a dangling config
ID). The unit tests need no QGIS; the live tests run against a real, throwaway QGIS auth database
and skip cleanly when QGIS is unavailable.
"""

import os
import tempfile
import unittest

from plugin.authstore import stored_config_id


class _Cfg:
    """Stand-in for QgsAuthMethodConfig: only ``id()`` matters here."""

    def __init__(self, cfg_id=""):
        self._id = cfg_id

    def id(self):
        return self._id


class TestStoredConfigId(unittest.TestCase):
    def test_success_tuple_returns_id_from_returned_config(self):
        self.assertEqual(stored_config_id((True, _Cfg("abc1234")), _Cfg("")), "abc1234")

    def test_success_tuple_falls_back_to_original_config_id(self):
        # QGIS also writes the ID into the config it was given.
        self.assertEqual(stored_config_id((True, _Cfg("")), _Cfg("xyz9876")), "xyz9876")

    def test_failed_tuple_is_not_success_even_though_tuple_is_truthy(self):
        result = (False, _Cfg("dangling"))
        self.assertTrue(bool(result))  # the original bug: this tuple is truthy
        self.assertIsNone(stored_config_id(result, _Cfg("dangling")))

    def test_success_without_any_id_is_not_success(self):
        self.assertIsNone(stored_config_id((True, _Cfg("")), _Cfg("")))

    def test_legacy_bool_result_is_supported(self):
        self.assertEqual(stored_config_id(True, _Cfg("old0001")), "old0001")
        self.assertIsNone(stored_config_id(False, _Cfg("old0001")))

    def test_degenerate_results(self):
        self.assertIsNone(stored_config_id((), _Cfg("abc")))
        self.assertIsNone(stored_config_id(None, _Cfg("abc")))
        self.assertEqual(stored_config_id((True,), _Cfg("abc")), "abc")


class TestAgainstRealQgisAuthManager(unittest.TestCase):
    """Pin the helper to the real binding's return shape, in a throwaway auth DB."""

    @classmethod
    def setUpClass(cls):
        # Never touch the user's real qgis-auth.db or profile.
        os.environ["QGIS_AUTH_DB_DIR_PATH"] = tempfile.mkdtemp(prefix="niva_auth_")
        os.environ.setdefault("XDG_DATA_HOME", tempfile.mkdtemp(prefix="niva_xdg_"))
        try:
            from niva.engine.pyqgis import ensure_qgis

            ensure_qgis()
            from qgis.core import QgsApplication
        except Exception as exc:  # ImportError, or a QGIS init failure
            raise unittest.SkipTest(f"QGIS not available: {exc}")
        cls.am = QgsApplication.authManager()
        if not cls.am.setMasterPassword("niva-test-master-only", True):
            raise unittest.SkipTest(
                "could not set a master password on the temp auth DB"
            )

    def _cfg(self, method="Basic"):
        from qgis.core import QgsAuthMethodConfig

        cfg = QgsAuthMethodConfig()
        cfg.setName("niva test")
        if method:
            cfg.setMethod(method)
        cfg.setConfig("password", "not-a-real-secret")
        return cfg

    def test_successful_store_yields_a_retrievable_id(self):
        cfg = self._cfg()
        cfg_id = stored_config_id(self.am.storeAuthenticationConfig(cfg), cfg)
        self.assertTrue(cfg_id)
        self.assertIn(cfg_id, self.am.configIds())

    def test_failed_store_yields_none(self):
        # Invalid: no auth method, so QGIS refuses to store it.
        cfg = self._cfg(method="")
        result = self.am.storeAuthenticationConfig(cfg)
        self.assertIsInstance(result, tuple)
        self.assertFalse(result[0])
        self.assertIsNone(stored_config_id(result, cfg))


if __name__ == "__main__":
    unittest.main()
