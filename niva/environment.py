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
import re
import sys
import tempfile

# Environment variables niva reads (see docs/guide/reference.md §8). `secret=True` values are
# never printed — only whether they are set.
_ENV_VARS = [
    ("NIVA_TMPDIR", False), ("CPL_TMPDIR", False), ("NIVA_LOG", False),
    ("NIVA_TEMPLATES", False), ("NIVA_QGIS_PROFILE", False),
    ("QGIS_PREFIX_PATH", False), ("QT_QPA_PLATFORM", False),
    ("NIVA_NTFY_TOPIC", False), ("NIVA_NTFY_SERVER", False), ("NIVA_NTFY_TOKEN", True),
    ("NIVA_NTFY_ON_ERROR", False), ("NIVA_NTFY_ON_WARNING", False),
    ("NIVA_SMTP_HOST", False), ("NIVA_SMTP_PORT", False), ("NIVA_SMTP_USER", False),
    ("NIVA_SMTP_PASSWORD", True), ("NIVA_SMTP_FROM", False),
]

# QGIS settings-ini sections that hold *database* connections (the `@conn` kind), mapped to
# the provider label niva shows. Each connection appears as `connections\<name>\<key>=…`
# under its section. We parse these per profile so the report can show connections across
# *all* profiles, not just the active one (the live provider API only sees the active one).
# Each DB provider keeps connections in its OWN ini section as `connections\<name>\…`.
_DB_SECTIONS = {
    "PostgreSQL": "postgres", "SpatiaLite": "spatialite", "MSSQL": "mssql",
    "Oracle": "oracle", "DB2": "db2", "HANA": "hana",
}
_SECTION_RE = re.compile(r"^\[(.+)\]\s*$")
_CONN_RE = re.compile(r"^connections\\([^\\]+)\\")
# GeoPackage/OGR connections instead live under the shared `[connections]` section as
# `ogr\GPKG\connections\<name>\…`. (provider label, regex) pairs scanned in that section.
_SHARED_CONN_RES = [("ogr", re.compile(r"^ogr\\GPKG\\connections\\([^\\]+)\\"))]


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


def _pyqt_version():
    from qgis.PyQt.QtCore import PYQT_VERSION_STR

    return PYQT_VERSION_STR


def _sqlite_version():
    import sqlite3

    return sqlite3.sqlite_version


def _spatialite_version():
    """SpatiaLite library version, via GDAL's SQLite driver (a temp in-memory db). Best
    effort — returns the raw error string through ``_safe`` if GDAL lacks SpatiaLite."""
    from osgeo import ogr

    mem = "/vsimem/niva_spatialite_probe.sqlite"
    drv = ogr.GetDriverByName("SQLite")
    ds = drv.CreateDataSource(mem, options=["SPATIALITE=YES"])
    try:
        lyr = ds.ExecuteSQL("SELECT spatialite_version()")
        feat = lyr.GetNextFeature()
        version = feat.GetField(0)
        ds.ReleaseResultSet(lyr)
        return version
    finally:
        ds = None
        drv.DeleteDataSource(mem)


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


def _connections_in_ini(path: str) -> dict:
    """{provider label: sorted([connection names])} of the *database* connections defined
    in one profile's settings ini, by a line scan (no QGIS needed; read-only). Lets the
    report list connections for *every* profile, not just the active one."""
    found: dict = {}
    section = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _SECTION_RE.match(line)
                if m:
                    section = m.group(1)
                    continue
                label = _DB_SECTIONS.get(section)
                if label is not None:
                    cm = _CONN_RE.match(line)
                    if cm:
                        found.setdefault(label, set()).add(cm.group(1))
                elif section == "connections":
                    for shared_label, rx in _SHARED_CONN_RES:
                        sm = rx.match(line)
                        if sm:
                            found.setdefault(shared_label, set()).add(sm.group(1))
                            break
    except OSError:
        return {}
    return {label: sorted(names) for label, names in sorted(found.items())}


def _profiles():
    """(profiles root, active profile name, {profile: {provider: [conn names]}}).

    The active profile is whatever the running app actually booted with
    (``qgisSettingsDirPath`` → its parent is the profiles root); siblings are the other
    profiles. Each profile's database connections come from parsing its settings ini, so
    the report shows them all even though only the active profile's connections are live."""
    from qgis.core import Qgis, QgsApplication

    active_folder = QgsApplication.qgisSettingsDirPath().rstrip("/\\")
    root = os.path.dirname(active_folder)
    active = os.path.basename(active_folder)
    major = Qgis.QGIS_VERSION_INT // 10000
    profiles: dict = {}
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            pdir = os.path.join(root, name)
            if os.path.isdir(pdir):
                profiles[name] = _connections_in_ini(
                    os.path.join(pdir, "QGIS", f"QGIS{major}.ini"))
    return root, active, profiles


def _settings_file():
    from qgis.core import QgsSettings

    return QgsSettings().fileName()


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

    # database connections — the most useful thing for CLI work. These are the connections
    # of the *active* profile: exactly what `@conn` resolves to in a flow right now.
    add("## Database connections (`@conn`)")
    prof = _safe(_profiles, default=None)
    root, active, profiles = prof if isinstance(prof, tuple) else (None, None, {})
    sfile = _safe(_settings_file)
    if active:
        add(f"Active profile: **{active}** — read from `{sfile}`.")
        add("")
    conns = _safe(_connections, default={})
    if isinstance(conns, dict) and conns:
        for name in sorted(conns):
            add(f"- `@{name}` — {conns[name]}")
    elif isinstance(conns, dict):
        add("- none configured — add one in QGIS (Data Source Manager), then `load @name.table`")
    else:
        add(f"- {conns}")
    add("")

    # how to discover what's loadable — concrete `show` examples, using a real connection
    # name from the active profile when there is one.
    add("## Listing data (`show`)")
    add("`show` lists what you can `load` at a location — a file, a directory, a database "
        "connection, or a remote service:")
    add("")
    add("- File / directory: `show data.gpkg` · `show data/ deep` (recurse)")
    if isinstance(conns, dict) and conns:
        first = sorted(conns)[0]
        add(f"- Database: `show @{first}` (all tables) · `show @{first}.<schema>` (one schema)")
    else:
        add("- Database: `show @<conn>` (configure a connection in QGIS first)")
    add("- Remote: `show \"https://…/wfs?service=WFS\"` — WFS, WMS, ArcGIS REST, or an XYZ "
        "`{z}/{x}/{y}` template")
    add("")

    # all profiles + their connections — niva uses ONE profile at a time (the active one,
    # or `$NIVA_QGIS_PROFILE`), so this shows what's reachable if you switch.
    add("## QGIS profiles")
    if isinstance(profiles, dict) and profiles:
        add(f"niva reads from **one** profile at a time — the active one (**{active}**), or set "
            "`NIVA_QGIS_PROFILE=<name>` to use another. Connections by profile:")
        add("")
        for name in sorted(profiles):
            mark = " *(active)*" if name == active else ""
            dbconns = profiles[name]
            if dbconns:
                parts = "; ".join(f"{label}: " + ", ".join(f"`{n}`" for n in names)
                                  for label, names in sorted(dbconns.items()))
            else:
                parts = "_(no database connections)_"
            add(f"- **{name}**{mark} — {parts}")
        if root:
            add("")
            add(f"Profiles directory: `{root}`")
    elif active:
        add(f"- only the active profile (**{active}**) — set `NIVA_QGIS_PROFILE` to target another")
    else:
        add(f"- {profiles}")
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

    # QGIS / geo stack
    add("## QGIS & geo stack")
    add(f"- QGIS: {_safe(_qgis_version)}")
    add(f"- Qt bindings: Qt {_safe(_qt_version)} / PyQt {_safe(_pyqt_version)}")
    add(f"- GDAL: {_safe(_gdal_version)}")
    add(f"- PROJ: {_safe(_proj_version)}")
    add(f"- GEOS: {_safe(_geos_version)}")
    add(f"- SpatiaLite/SQLite: SpatiaLite {_safe(_spatialite_version)} "
        f"(SQLite {_safe(_sqlite_version)})")
    add("")

    add("## Python & platform")
    add(f"- Python: {sys.version.splitlines()[0]}")
    add(f"- Interpreter: `{sys.executable}`")
    add(f"- sys.prefix: `{sys.prefix}`")
    add(f"- sys.base_prefix: `{sys.base_prefix}`")
    add(f"- Platform: {platform.platform()}")
    add("")

    return "\n".join(lines)
