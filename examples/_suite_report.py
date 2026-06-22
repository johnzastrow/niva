"""Portable summary-report writer shared by the niva suite runners.

Writes a Markdown summary into the user's home directory — `~/niva-test-results/` — so results
from different computers (Linux, macOS, Windows) can be gathered and compared. Each report carries
an environment fingerprint (computer, OS, CPU, RAM), niva and QGIS versions, run timing, and a
per-test results table. Pure standard library; no third-party dependencies.
"""
from __future__ import annotations

import contextlib
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path


def _total_ram_mb():
    """Total physical RAM in MB, cross-platform and best-effort (None if undiscoverable)."""
    # Linux & macOS expose this via sysconf.
    try:
        return round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024))
    except (ValueError, AttributeError, OSError):
        pass
    # Windows: GlobalMemoryStatusEx via ctypes.
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = _MemStatus()
        stat.dwLength = ctypes.sizeof(_MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
        return round(stat.ullTotalPhys / (1024 * 1024))
    except Exception:  # noqa: BLE001
        return None


def environment() -> dict:
    """A fingerprint of the machine + software stack, for cross-computer comparison."""
    env = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": platform.node() or "unknown",
        "os": platform.system(),
        "os_release": platform.release(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_total_mb": _total_ram_mb(),
        "python": platform.python_version(),
        "niva_version": None,
        "qgis_version": None,
    }
    with contextlib.suppress(Exception):
        import niva
        env["niva_version"] = niva.__version__
    with contextlib.suppress(Exception):
        from qgis.core import Qgis
        env["qgis_version"] = Qgis.QGIS_VERSION
    return env


def results_dir() -> Path:
    """`~/niva-test-results`, created if needed (cross-platform via pathlib)."""
    d = Path.home() / "niva-test-results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_ENV_ORDER = ("host", "os", "os_release", "platform", "machine", "processor", "cpu_count",
              "ram_total_mb", "python", "niva_version", "qgis_version")


def env_table(env: dict) -> list[str]:
    """The shared `## Environment` Markdown block (computer / niva / QGIS details)."""
    lines = ["## Environment", "", "| key | value |", "|---|---|"]
    lines += [f"| {k} | {env.get(k, '')} |" for k in _ENV_ORDER]
    return lines


def write_summary(suite: str, env: dict, columns, rows, summary_lines,
                  started_utc: str, elapsed_s: float) -> Path:
    """Write `<suite>_<host>_<UTCstamp>.md` and refresh `<suite>_latest.md` in ~/niva-test-results.

    `columns` are header strings; `rows` are equal-length lists of cell values. Returns the path
    of the timestamped report. Best-effort — a reporting failure must never fail a test run.
    """
    host = re.sub(r"\W+", "_", env.get("host") or "host")
    lines = [
        f"# niva — {suite}", "",
        f"**{env.get('timestamp_utc')}** · host `{env.get('host')}` · "
        f"niva `{env.get('niva_version')}` · QGIS `{env.get('qgis_version')}` · "
        f"{env.get('os')} {env.get('machine')}", "",
    ]
    lines += env_table(env)
    lines += [f"| run started (UTC) | {started_utc} |",
              f"| total elapsed (s) | {round(elapsed_s, 2)} |", ""]
    lines += ["## Results", "", "| " + " | ".join(columns) + " |",
              "|" + "|".join("---" for _ in columns) + "|"]
    for r in rows:
        lines.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    lines += ["", "## Summary", ""] + [f"- {s}" for s in summary_lines]
    md = "\n".join(lines) + "\n"

    d = results_dir()
    primary = d / f"{suite}_{host}_{_stamp()}.md"
    primary.write_text(md, encoding="utf-8")
    (d / f"{suite}_latest.md").write_text(md, encoding="utf-8")
    return primary
