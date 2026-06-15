"""niva — QGIS plugin entry point.

QGIS calls ``classFactory(iface)`` when the plugin loads. Before building the GUI we
make sure the **niva package is importable**: prefer a pip-installed `niva` if the
user has one, otherwise fall back to the copy **vendored inside this plugin**
(``libs/niva``). Because niva is zero-dependency pure Python, vendoring means the
plugin works on Windows / macOS / Linux with **no pip step at all** — the on-ramp
that sidesteps the install friction (Oscar E2/E3).
"""

import os
import sys


def _ensure_niva_importable():
    try:
        import niva  # noqa: F401 — prefer a pip-installed niva if present
        return
    except ImportError:
        libs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs")
        if os.path.isdir(libs) and libs not in sys.path:
            sys.path.insert(0, libs)


def classFactory(iface):  # noqa: N802 — name required by QGIS
    _ensure_niva_importable()
    from .plugin import NivaPlugin

    return NivaPlugin(iface)
