"""`niva setup doctor` — a one-shot environment health check (issue #36).

Answers *"is my niva install able to run?"* in a single command: niva itself, the QGIS runtime
niva discovered (or why it didn't), Processing providers, the point-cloud backend, the config
file, and the database connections niva can see. Read-only — it never writes config or runs a
flow. Exit 0 when nothing is blocking, 1 when a blocking issue is found (QGIS not importable).

Generalises ``niva pdal check`` (point cloud only) to the whole environment, and shares QGIS
discovery with the engine (:func:`niva.engine.pyqgis.ensure_qgis`), so the runtime it reports is
exactly the one a real ``niva run`` would use.
"""

from __future__ import annotations

import os

PASS, FAIL, WARN, OPT, INFO = "✓", "✗", "⚠", "○", "·"


def run(argv=None) -> int:
    """Print the health report; return 1 if a blocking issue was found, else 0."""
    from . import color

    out: list[str] = []

    def head(t):
        out.append(color.paint(t, "bold"))

    def line(sym, text, c):
        out.append(f"  {color.paint(sym, c)} {text}")

    def note(text):
        out.append(f"      {color.paint(text, 'dim')}")

    fails = 0

    # --- niva ------------------------------------------------------------------
    from . import __version__
    from . import __file__ as _pkg_file

    head("niva")
    line(PASS, f"version {__version__}   ({os.path.dirname(_pkg_file)})", "green")
    out.append("")

    # --- QGIS runtime ----------------------------------------------------------
    head("QGIS runtime")
    qgis_ok, f = _probe_qgis()
    if qgis_ok:
        line(
            PASS,
            f"QGIS {f.get('version', '?')}   (bindings: {f.get('bindings', '?')})",
            "green",
        )
        if f.get("prefix"):
            line(INFO, f"prefix {f['prefix']}", "dim")
        if f.get("providers") is not None:
            line(
                PASS,
                f"Processing: {f['nproviders']} providers, {f['nalgs']} algorithms",
                "green",
            )
            note(", ".join(f["providers"]))
        if f.get("geostack"):
            line(INFO, f["geostack"], "dim")
    else:
        fails += 1
        line(FAIL, "QGIS not importable — niva can't execute flows", "red")
        note("point niva at QGIS's bindings, then re-run:")
        out.append(
            "      "
            + color.paint("export NIVA_QGIS_PYTHONPATH=/path/to/qgis/python", "yellow")
        )
        note("(the directory that holds the `qgis` package — see the Quick start)")
    out.append("")

    # --- Point cloud (PDAL) ----------------------------------------------------
    head("Point cloud (PDAL)")
    wrench, wver = _probe_wrench()
    if wrench:
        line(PASS, f"pdal_wrench  {wrench}" + (f"  ({wver})" if wver else ""), "green")
    else:
        line(
            OPT,
            "pdal_wrench not found — optional; `niva pdal check` to set it up",
            "yellow",
        )
    if qgis_ok and f.get("pdal_provider") is not None:
        if f["pdal_provider"]:
            line(PASS, "pdal: data provider present (reads raw LAS/COPC)", "green")
        else:
            line(OPT, "pdal: provider not registered — `niva pdal check`", "yellow")
    out.append("")

    # --- Config ----------------------------------------------------------------
    head("Config")
    try:
        from . import config as cfg

        cpath = cfg.config_path()
        if os.path.isfile(cpath):
            line(PASS, f"config file: {cpath}", "green")
        else:
            line(
                OPT,
                f"no config file — `niva setup init` to create one ({cpath})",
                "yellow",
            )
    except Exception as exc:  # noqa: BLE001
        line(WARN, f"config unavailable: {exc}", "yellow")
    if qgis_ok and f.get("log") is not None:
        enabled, folder = f["log"]
        line(INFO, f"run log: {('on → ' + folder) if enabled else 'off'}", "dim")
    tmp = os.environ.get("NIVA_TMPDIR")
    line(
        INFO,
        f"scratch (NIVA_TMPDIR): {tmp or 'unset (uses the system temp dir)'}",
        "dim",
    )
    out.append("")

    # --- Database connections (@conn) ------------------------------------------
    head("Database connections (@conn)")
    if qgis_ok:
        conns = f.get("connections") or {}
        if conns:
            line(PASS, f"{len(conns)} connection(s)", "green")
            for name, prov in sorted(conns.items()):
                out.append(
                    f"      {color.paint('@' + name, 'blue')}  {color.paint(prov, 'dim')}"
                )
        else:
            line(
                OPT,
                "no saved connections (add them in QGIS or the plugin Setup tab)",
                "yellow",
            )
    else:
        line(OPT, "needs QGIS — unavailable", "dim")
    out.append("")

    # --- Verdict ---------------------------------------------------------------
    if fails:
        out.append(
            color.paint(f"Verdict: {fails} blocking issue(s) — see ✗ above.", "red")
        )
    else:
        out.append(color.paint("Verdict: ready ✓", "green"))

    print("\n".join(out))
    return 1 if fails else 0


def _probe_qgis() -> tuple[bool, dict]:
    """(importable, facts). Initialises QGIS via the engine's shared discovery, so the runtime
    reported is the one a real run would use. Never raises — a failure just yields (False, …)."""
    facts: dict = {}
    try:
        from .engine.pyqgis import ensure_qgis

        ensure_qgis()
    except Exception as exc:  # noqa: BLE001 — QGIS unavailable is the headline finding, not a crash
        return False, {"error": str(exc)[:160]}

    try:
        import qgis

        facts["bindings"] = os.path.dirname(os.path.dirname(qgis.__file__))
    except Exception:  # noqa: BLE001
        pass
    from . import environment as env

    facts["version"] = env._safe(env._qgis_version)
    try:
        from qgis.core import QgsApplication

        facts["prefix"] = QgsApplication.prefixPath()
    except Exception:  # noqa: BLE001
        pass
    try:
        provs, nalgs = env._processing()
        facts["providers"], facts["nproviders"], facts["nalgs"] = (
            provs,
            len(provs),
            nalgs,
        )
        facts["pdal_provider"] = "pdal" in provs
    except Exception:  # noqa: BLE001
        facts["providers"] = None
    facts["geostack"] = (
        f"geo stack: GDAL {env._safe(env._gdal_version)} · "
        f"PROJ {env._safe(env._proj_version)} · GEOS {env._safe(env._geos_version)}"
    )
    try:
        facts["log"] = env._log_setting()
    except Exception:  # noqa: BLE001
        facts["log"] = None
    try:
        facts["connections"] = env._connections()
    except Exception:  # noqa: BLE001
        facts["connections"] = {}
    return True, facts


def _probe_wrench() -> tuple[str | None, str | None]:
    """(pdal_wrench path, version) or (None, None) — best effort, reusing the pdal doctor."""
    try:
        from .pdal_doctor import _find, _version, _wrench_name

        path, _how = _find(_wrench_name())
        if not path:
            return None, None
        ver = None
        try:
            ver = _version(path, ["--version"])
        except Exception:  # noqa: BLE001
            ver = None
        return path, ver
    except Exception:  # noqa: BLE001
        return None, None
