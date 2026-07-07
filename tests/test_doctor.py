"""`niva setup doctor` — the environment health check. QGIS-free: the QGIS probe is stubbed so
both the healthy and the missing-QGIS paths are exercised without a real (or mismatched) QGIS."""

import contextlib
import io
import unittest

import niva.doctor as D


def _run():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D.run([])
    return rc, buf.getvalue()


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self._q, self._w = D._probe_qgis, D._probe_wrench
        D._probe_wrench = lambda: (None, None)

    def tearDown(self):
        D._probe_qgis, D._probe_wrench = self._q, self._w

    def test_missing_qgis_is_a_blocking_failure(self):
        D._probe_qgis = lambda: (False, {"error": "no module named qgis"})
        rc, out = _run()
        self.assertEqual(rc, 1)
        self.assertIn("QGIS not importable", out)
        self.assertIn("NIVA_QGIS_PYTHONPATH", out)  # tells the user how to fix it
        self.assertIn("blocking issue", out)

    def test_healthy_environment_reports_ready(self):
        D._probe_qgis = lambda: (
            True,
            {
                "version": "4.2.0-Test",
                "bindings": "/usr/share/qgis/python",
                "prefix": "/usr",
                "providers": ["gdal", "native", "qgis"],
                "nproviders": 3,
                "nalgs": 700,
                "pdal_provider": True,
                "geostack": "geo stack: GDAL 3 · PROJ 9 · GEOS 3",
                "log": (True, "/tmp/logs"),
                "connections": {"gisdb3": "postgres"},
            },
        )
        rc, out = _run()
        self.assertEqual(rc, 0)
        self.assertIn("Verdict: ready", out)
        self.assertIn("4.2.0-Test", out)
        self.assertIn("3 providers, 700 algorithms", out)
        self.assertIn("@gisdb3", out)

    def test_always_reports_niva_version(self):
        from niva import __version__

        D._probe_qgis = lambda: (False, {})
        _, out = _run()
        self.assertIn(__version__, out)


if __name__ == "__main__":
    unittest.main()
