"""Environment report for the plugin's Setup tab.

Gathers everything a niva user might need to know about *where* their flows run:
the niva build, QGIS/Python/Qt and the geo stack (GDAL/PROJ/GEOS), the Processing
providers and how many algorithms `run` can reach, the available database
connections (the `@conn` names), the registered verbs, and where run journals land.

Every probe is wrapped so one failure never breaks the report — niva runs in QGIS's
own Python, which differs across Windows / macOS / Linux.
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile


def _safe(fn, default="unavailable"):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — a report must never raise
        return f"{default} ({exc})"


def _qgis_version():
    from qgis.core import Qgis

    return Qgis.QGIS_VERSION


def _qt_version():
    from qgis.PyQt.QtCore import QT_VERSION_STR

    return QT_VERSION_STR


def _gdal_version():
    from osgeo import gdal

    return gdal.__version__


def _proj_version():
    from osgeo import osr

    return (f"{osr.GetPROJVersionMajor()}.{osr.GetPROJVersionMinor()}"
            f".{osr.GetPROJVersionMicro()}")


def _geos_version():
    from qgis.core import Qgis

    return Qgis.geosVersion()


def _processing():
    """(sorted provider ids, algorithm count) — ensures QGIS/Processing is ready."""
    from qgis.core import QgsApplication

    from niva.engine.pyqgis import ensure_qgis

    ensure_qgis()
    reg = QgsApplication.processingRegistry()
    return sorted(p.id() for p in reg.providers()), len(reg.algorithms())


def _log_setting():
    """(enabled, folder) for run logging, from QGIS settings (plugin-configurable)."""
    from qgis.core import QgsSettings

    default = os.path.join(tempfile.gettempdir(), "niva_logs")
    s = QgsSettings()
    return s.value("niva/log_enabled", True, type=bool), s.value("niva/log_dir", default, type=str)


def _connections():
    """{connection name: provider} across all DB providers — the usable `@conn`s."""
    from qgis.core import QgsProviderRegistry

    reg = QgsProviderRegistry.instance()
    found = {}
    for provider in reg.providerList():
        md = reg.providerMetadata(provider)
        if md is None:
            continue
        try:
            for name in md.connections(False):
                found[name] = provider
        except Exception:  # noqa: BLE001 — provider has no connections API
            continue
    return found


def report_markdown() -> str:
    lines: list = []
    add = lines.append

    add("# niva — environment")
    add("")

    # niva
    add("## niva")
    try:
        import niva

        add(f"- Version: **{niva.__version__}**")
        add(f"- Imported from: `{os.path.dirname(niva.__file__)}`")
        vendored = "libs" in niva.__file__.split(os.sep)
        add(f"- Source: {'bundled with this plugin' if vendored else 'pip-installed'}")
    except Exception as exc:  # noqa: BLE001
        add(f"- niva not importable: {exc}")
    setting = _safe(_log_setting, default=None)
    if isinstance(setting, tuple):
        enabled, folder = setting
        add(f"- Run journals: {'on' if enabled else 'off'} → `{folder}` "
            "(configurable above)")
    else:
        add(f"- Run journals: `{os.path.join(tempfile.gettempdir(), 'niva_logs')}`")
    add("")

    # verbs + reachable algorithms
    add("## Verbs & algorithms")
    try:
        from niva.registry import core_registry

        verbs = core_registry().verbs()
        add("- Built-in verbs: `load` `save` `sql` `run` `call` `metadata` `assess` "
            "`catalog` `project` `style` `describe`")
        add(f"- Aliased verbs ({len(verbs)}): {', '.join('`' + v + '`' for v in verbs)}")
    except Exception as exc:  # noqa: BLE001
        add(f"- registry unavailable: {exc}")
    proc = _safe(_processing, default=None)
    provs, n_alg = proc if isinstance(proc, tuple) else ([], "unavailable")
    add(f"- Reachable via `run <id>`: **{n_alg}** algorithms")
    add(f"- Processing providers: {', '.join('`' + p + '`' for p in provs) or 'unavailable'}")
    add("")

    # database connections
    add("## Database connections (`@conn`)")
    conns = _safe(_connections, default={})
    if isinstance(conns, dict) and conns:
        for name in sorted(conns):
            add(f"- `@{name}` — {conns[name]}")
    elif isinstance(conns, dict):
        add("- none configured — add one in QGIS (Data Source Manager), then `load @name.table`")
    else:
        add(f"- {conns}")
    add("")

    # QGIS / Python / geo stack
    add("## QGIS & geo stack")
    add(f"- QGIS: {_safe(_qgis_version)}")
    add(f"- Qt: {_safe(_qt_version)}")
    add(f"- GDAL: {_safe(_gdal_version)}")
    add(f"- PROJ: {_safe(_proj_version)}")
    add(f"- GEOS: {_safe(_geos_version)}")
    add("")

    add("## Python & platform")
    add(f"- Python: {sys.version.splitlines()[0]}")
    add(f"- Executable: `{sys.executable}`")
    add(f"- Prefix: `{sys.prefix}`")
    add(f"- Platform: {platform.platform()}")
    add("")

    return "\n".join(lines)
