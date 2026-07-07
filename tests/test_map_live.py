"""Live-QGIS `map` verb tests — need a real QGIS, and skip cleanly when it isn't importable
(so this file's guard never affects the pure `test_map.py` MockBackend tests). Guards the
composed layout's decorations that only a real render exposes — e.g. the scale bar must have a
non-zero segment size (a regression guard for the "scale bar reads 0" bug)."""

import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_GPKG = os.path.join(_REPO, "examples", "data", "example.gpkg")


def setUpModule():
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="niva_xdg_")
    try:
        from niva.engine.pyqgis import ensure_qgis

        ensure_qgis()
    except (
        Exception
    ) as exc:  # ImportError, or a QGIS init failure → skip the whole file
        raise unittest.SkipTest(f"QGIS not available: {exc}") from exc


class TestMapScaleBarLive(unittest.TestCase):
    def _compose(self, **kw):
        """Build the map layout via the real backend but capture it instead of exporting."""
        from niva.engine.pyqgis import PyqgisBackend

        be = PyqgisBackend()
        layer = be.load(f"{_GPKG}|layername=town")
        captured = {}
        be._export_layout = lambda lay, dest, **_kw: captured.__setitem__("lay", lay)
        be.render_map(
            layer,
            os.path.join(tempfile.gettempdir(), "niva_sb_test.png"),
            legend=False,
            northarrow=False,
            **kw,
        )
        return captured["lay"]

    def test_scalebar_segment_size_is_nonzero(self):
        from qgis.core import QgsLayoutItemScaleBar

        lay = self._compose(scalebar=True)
        bars = [i for i in lay.items() if isinstance(i, QgsLayoutItemScaleBar)]
        self.assertTrue(bars, "no scale bar item in the composed layout")
        # The bug: applyDefaultSettings leaves unitsPerSegment == 0, so every label reads "0".
        self.assertGreater(
            bars[0].unitsPerSegment(),
            0,
            "scale bar segment size is 0 — it would render as an all-zero bar",
        )

    def test_no_scalebar_when_disabled(self):
        from qgis.core import QgsLayoutItemScaleBar

        lay = self._compose(scalebar=False)
        bars = [i for i in lay.items() if isinstance(i, QgsLayoutItemScaleBar)]
        self.assertEqual(bars, [])


if __name__ == "__main__":
    unittest.main()
