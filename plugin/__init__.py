"""niva — QGIS plugin entry point.

QGIS calls ``classFactory(iface)`` when the plugin loads. We make the **niva package
that is vendored inside this plugin** (``libs/niva``) importable, so the engine always
matches this plugin's code. Because niva is zero-dependency pure Python, vendoring
means the plugin works on Windows / macOS / Linux with **no pip step at all** — the
on-ramp that sidesteps the install friction (Oscar E2/E3).

Reload-safe: Python caches modules in ``sys.modules`` across plugin reloads, so a
freshly reinstalled plugin would otherwise keep running the *old* niva until QGIS is
restarted. We purge any cached ``niva`` modules and put the vendored copy first on the
path, so a reinstall + reload picks up the new code without a restart.
"""

import os
import sys


def _ensure_niva_importable():
    libs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs")
    if not os.path.isdir(libs):
        return  # no vendored copy (e.g. running from source with niva already on path)

    # Drop a previously-loaded niva so the vendored copy is re-imported fresh.
    for name in [m for m in list(sys.modules) if m == "niva" or m.startswith("niva.")]:
        del sys.modules[name]

    # Ensure the vendored copy is first on the path (shadows any other niva).
    while libs in sys.path:
        sys.path.remove(libs)
    sys.path.insert(0, libs)


def classFactory(iface):  # noqa: N802 — name required by QGIS
    _ensure_niva_importable()
    from .plugin import NivaPlugin

    return NivaPlugin(iface)
