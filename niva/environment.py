"""The local-environment report — the data behind the `info` verb and the plugin's
Setup-tab "Environment report".

Gathers everything a niva user might need to know about *where* their flows run, and is
especially useful from a bare shell outside QGIS: the niva build, QGIS/Python/Qt and the geo
stack (GDAL/PROJ/GEOS), the Processing providers and how many algorithms `run` can reach, the
**database connection names** (the `@conn` values a flow can reference), the registered verbs,
the environment variables niva honours, and where run journals land.

Importing this module is safe on any interpreter — QGIS is imported lazily only when the report
is built. Every probe is wrapped so one failure never breaks the report (niva runs in QGIS's
own Python, which differs across Windows / macOS / Linux).
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile

# Environment variables niva reads (see docs/guide/reference.md §8). `secret=True` values are
# never printed — only whether they are set.
_ENV_VARS = [
    ("NIVA_TMPDIR", False), ("CPL_TMPDIR", False), ("NIVA_LOG", False),
    ("NIVA_TEMPLATES", False), ("QGIS_PREFIX_PATH", False), ("QT_QPA_PLATFORM", False),
    ("NIVA_NTFY_TOPIC", False), ("NIVA_NTFY_SERVER", False), ("NIVA_NTFY_TOKEN", True),
    ("NIVA_NTFY_ON_ERROR", False), ("NIVA_NTFY_ON_WARNING", False),
    ("NIVA_SMTP_HOST", False), ("NIVA_SMTP_PORT", False), ("NIVA_SMTP_USER", False),
    ("NIVA_SMTP_PASSWORD", True), ("NIVA_SMTP_FROM", False),
]


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


def _builtin_verbs():
    from niva.engine.engine import Engine

    return sorted(Engine._BUILTIN_VERBS)


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
        add(f"- Source: {'bundled with the QGIS plugin' if vendored else 'pip / source'}")
    except Exception as exc:  # noqa: BLE001
        add(f"- niva not importable: {exc}")
    setting = _safe(_log_setting, default=None)
    if isinstance(setting, tuple):
        enabled, folder = setting
        add(f"- Run journals: {'on' if enabled else 'off'} → `{folder}`")
    add("")

    # verbs + reachable algorithms
    add("## Verbs & algorithms")
    builtins = _safe(_builtin_verbs, default=None)
    if isinstance(builtins, list):
        add("- Built-in verbs: " + " ".join(f"`{v}`" for v in builtins)
            + "  (plus `each`, `call`, `describe`)")
    try:
        from niva.registry import core_registry

        verbs = core_registry().verbs()
        add(f"- Aliased verbs ({len(verbs)}): " + ", ".join(f"`{v}`" for v in verbs))
    except Exception as exc:  # noqa: BLE001
        add(f"- registry unavailable: {exc}")
    proc = _safe(_processing, default=None)
    provs, n_alg = proc if isinstance(proc, tuple) else ([], "unavailable")
    add(f"- Reachable via `run <id>`: **{n_alg}** algorithms")
    add(f"- Processing providers: {', '.join('`' + p + '`' for p in provs) or 'unavailable'}")
    add("")

    # database connections — the most useful thing for CLI work
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

    # environment variables niva honours
    add("## Environment (niva variables)")
    for var, secret in _ENV_VARS:
        val = os.environ.get(var)
        if val is None:
            shown = "_(unset)_"
        elif secret:
            shown = "**set**"
        else:
            shown = f"`{val}`"
        add(f"- `{var}` = {shown}")
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
