"""The environment report (``niva/environment.py``) — the data behind `info` and the plugin's
Setup-tab report. QGIS-free: the QGIS probes are stubbed, so these pin the report's content and
its guarantees (secrets are never printed; a failing probe never breaks the report)."""

import os
import tempfile
import unittest
from unittest import mock

from niva import environment as E

INI = """\
[General]
foo=bar

[PostgreSQL]
connections\\prod_db\\host=db.example.com
connections\\prod_db\\port=5432
connections\\analytics\\host=10.0.0.5
selected=prod_db

[SpatiaLite]
connections\\local_sl\\sqlitepath=/data/x.sqlite

[connections]
ogr\\GPKG\\connections\\parcels\\path=/data/parcels.gpkg
ogr\\GPKG\\connections\\parcels\\other=1
ogr\\Shapefile\\connections\\ignored\\path=/x

[Other]
connections\\not_a_db\\x=1
"""


def _write(text):
    fd, path = tempfile.mkstemp(suffix=".ini", prefix="niva_qgis_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestConnectionsInIni(unittest.TestCase):
    def test_database_connections_are_grouped_by_provider_and_sorted(self):
        found = E._connections_in_ini(_write(INI))
        self.assertEqual(
            found,
            {
                "ogr": ["parcels"],
                "postgres": ["analytics", "prod_db"],
                "spatialite": ["local_sl"],
            },
        )

    def test_non_database_sections_and_keys_are_ignored(self):
        found = E._connections_in_ini(_write(INI))
        names = {n for names in found.values() for n in names}
        self.assertNotIn("not_a_db", names)
        self.assertNotIn("ignored", names)  # only GPKG connections in [connections]
        self.assertNotIn("selected", names)

    def test_missing_file_yields_empty(self):
        self.assertEqual(E._connections_in_ini("/nonexistent/QGIS4.ini"), {})

    def test_undecodable_bytes_do_not_break_the_scan(self):
        fd, path = tempfile.mkstemp(suffix=".ini")
        with os.fdopen(fd, "wb") as fh:
            fh.write(
                b"[PostgreSQL]\nconnections\\caf\xe9_db\\host=x\nconnections\\ok\\host=y\n"
            )
        found = E._connections_in_ini(path)
        self.assertIn("ok", found["postgres"])
        self.assertEqual(len(found["postgres"]), 2)


class TestSafe(unittest.TestCase):
    def test_returns_value_or_a_labelled_default(self):
        self.assertEqual(E._safe(lambda: 42), 42)
        self.assertEqual(E._safe(lambda: 1 / 0), "unavailable (division by zero)")
        self.assertEqual(
            E._safe(lambda: [][1], default=None), "None (list index out of range)"
        )


def _stub_probes(**overrides):
    """Patch every QGIS probe so report_markdown runs without QGIS."""
    probes = {
        "_log_setting": lambda: (True, "/tmp/niva_logs"),
        "_processing": lambda: (["native", "gdal"], 1234),
        "_profiles": lambda: (
            "/home/u/.local/share/QGIS/QGIS4/profiles",
            "default",
            {"default": {"postgres": ["prod_db"]}, "work": {}},
        ),
        "_settings_file": lambda: (
            "/home/u/.local/share/QGIS/QGIS4/profiles/default/QGIS/QGIS4.ini"
        ),
        "_connections": lambda: {"prod_db": "postgres", "parcels": "ogr"},
        "_qgis_version": lambda: "4.2.3",
        "_qt_version": lambda: "6.8",
        "_pyqt_version": lambda: "6.8",
        "_gdal_version": lambda: "3.12.2",
        "_proj_version": lambda: "9.6",
        "_geos_version": lambda: "3.13",
        "_spatialite_version": lambda: "5.1",
        "_sqlite_version": lambda: "3.46",
    }
    probes.update(overrides)
    return [mock.patch.object(E, name, fn) for name, fn in probes.items()]


class TestReportMarkdown(unittest.TestCase):
    def report(self, env=None, **overrides):
        patches = _stub_probes(**overrides) + [
            mock.patch.dict(os.environ, env or {}, clear=False)
        ]
        for p in patches:
            p.start()
        try:
            return E.report_markdown()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_core_sections_are_present(self):
        text = self.report()
        for heading in (
            "# niva — environment",
            "## niva",
            "## Verbs & algorithms",
            "## Database connections (`@conn`)",
            "## QGIS profiles",
            "## Environment (niva variables)",
            "## QGIS & geo stack",
            "## Python & platform",
        ):
            self.assertIn(heading, text)

    def test_connections_and_show_examples_use_real_names(self):
        text = self.report()
        self.assertIn("- `@parcels` — ogr", text)
        self.assertIn("- `@prod_db` — postgres", text)
        self.assertIn("`show @parcels`", text)  # first connection alphabetically

    def test_profiles_mark_the_active_one(self):
        text = self.report()
        self.assertIn("- **default** *(active)* — postgres: `prod_db`", text)
        self.assertIn("- **work** — _(no database connections)_", text)

    def test_secret_values_are_never_printed(self):
        secrets = {
            "NIVA_SMTP_PASSWORD": "hunter2-secret",  # pragma: allowlist secret
            "NIVA_NTFY_TOKEN": "tk_live_abc123",  # pragma: allowlist secret
        }
        text = self.report(env={**secrets, "NIVA_SMTP_HOST": "smtp.example.com"})
        for value in secrets.values():
            self.assertNotIn(value, text)
        self.assertIn("- `NIVA_SMTP_PASSWORD` = **set**", text)
        self.assertIn("- `NIVA_NTFY_TOKEN` = **set**", text)
        self.assertIn(
            "- `NIVA_SMTP_HOST` = `smtp.example.com`", text
        )  # non-secrets are shown

    def test_unset_variables_are_marked(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NIVA_TMPDIR", None)
            text = self.report()
        self.assertIn("- `NIVA_TMPDIR` = _(unset)_", text)

    def test_no_connections_gives_guidance(self):
        text = self.report(_connections=lambda: {})
        self.assertIn("none configured", text)
        self.assertIn("`show @<conn>`", text)

    def test_failing_probes_never_break_the_report(self):
        def boom():
            raise RuntimeError("no QGIS here")

        text = self.report(
            _connections=boom,
            _profiles=boom,
            _processing=boom,
            _qgis_version=boom,
            _log_setting=boom,
        )
        self.assertIn("## Python & platform", text)  # the report still completes
        self.assertIn("QGIS: unavailable (no QGIS here)", text)
        self.assertIn("Reachable via `run <id>`: **unavailable** algorithms", text)

    def test_reports_algorithm_count_and_providers(self):
        text = self.report()
        self.assertIn("**1234** algorithms", text)
        self.assertIn("`native`, `gdal`", text)


if __name__ == "__main__":
    unittest.main()
