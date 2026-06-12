"""niva (logo demo) — QGIS plugin entry point.

QGIS calls classFactory() with the `iface` (QgisInterface) when the plugin is
loaded. Keep this file tiny; the real plugin lives in plugin.py.
"""


def classFactory(iface):  # noqa: N802 — name required by QGIS
    from .plugin import NivaPlugin

    return NivaPlugin(iface)
