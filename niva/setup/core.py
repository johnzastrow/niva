"""Public setup-core API. Pure data in/out — no printing, prompting, or exiting.

Currently implements environment detection and the ``niva`` command launcher (``install_command`` /
``uninstall_command``). Package install, editor integration, and the marimo on-ramp are specified in
planning doc 21 and land in later increments.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import pathenv

PYPI_NAME = "qgis-niva"  # pinned; never taken from input


@dataclass
class StepResult:
    ok: bool
    changed: bool
    message: str
    detail: str = ""
    undo_hint: str = ""


@dataclass
class EnvReport:
    platform: str
    qgis_python: Path
    qgis_launcher: Optional[Path]
    niva_installed: Optional[str] = None
    on_path: bool = False
    launcher_path: Optional[Path] = None
    sandboxed: bool = False
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- detection
def _platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def qgis_python() -> Path:
    """Resolve QGIS's Python interpreter from the **live** process, so it tracks QGIS across version
    upgrades with no hardcoded version (same strategy as marimo-qgis' ``qgis_python()``)."""
    if os.name == "nt":
        for name in ("python.exe", "pythonw.exe"):
            cand = Path(sys.prefix) / name
            if cand.exists():
                return cand
        exe = Path(sys.executable)
        return (
            exe
            if exe.name.lower().startswith("python")
            else Path(sys.prefix) / "python.exe"
        )
    exe = Path(sys.executable)
    if exe.name.startswith("python"):
        return exe
    for name in ("python3", "python"):
        cand = Path(sys.prefix) / "bin" / name
        if cand.exists():
            return cand
    return exe


def find_qgis_launcher() -> Optional[Path]:
    """On Windows, locate ``python-qgis.bat`` (sets up the full QGIS env). None elsewhere / if
    not found. Probes, in order: ``OSGEO4W_ROOT``; a walk up from ``sys.prefix`` (correct when run
    *inside* QGIS's Python, e.g. the plugin); then well-known install locations (so the standalone
    CLI on a non-QGIS interpreter can still find QGIS)."""
    if os.name != "nt":
        return None
    candidates: list[Path] = []
    root = os.environ.get("OSGEO4W_ROOT")
    if root:
        candidates.append(Path(root) / "bin" / "python-qgis.bat")
    p = Path(sys.prefix)
    for parent in (p, *p.parents):
        candidates.append(parent / "bin" / "python-qgis.bat")
        candidates.append(parent.parent / "bin" / "python-qgis.bat")
    # Well-known locations — mirrors the PowerShell installer's Find-QgisBat.
    sysdrive = (os.environ.get("SystemDrive") or "C:") + "\\"
    for base in (Path(sysdrive) / "OSGeo4W", Path(sysdrive) / "OSGeo4W64"):
        candidates.append(base / "bin" / "python-qgis.bat")
    for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if pf:
            try:
                candidates.extend(
                    sorted(Path(pf).glob("QGIS*/bin/python-qgis.bat"), reverse=True)
                )
            except OSError:
                pass
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def qgis_invocation() -> Optional[str]:
    """The command the launcher should forward to: ``python-qgis.bat`` on Windows (full QGIS env);
    the QGIS ``python3`` on POSIX. Returns None on Windows when no ``python-qgis.bat`` can be found —
    the caller must refuse rather than write a launcher pointing at a non-QGIS interpreter."""
    launcher = find_qgis_launcher()
    if launcher:
        return str(launcher)
    if os.name != "nt":
        return str(qgis_python())
    return None


def launcher_target() -> Path:
    """Where the ``niva`` launcher file lives on this OS."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return Path(base) / "niva" / "bin" / "niva.cmd"
    return Path.home() / ".local" / "bin" / "niva"


def _installed_niva_version() -> Optional[str]:
    try:
        from .. import __version__

        return __version__
    except Exception:
        return None


def detect_environment(check_pypi: bool = False) -> EnvReport:
    target = launcher_target()
    report = EnvReport(
        platform=_platform(),
        qgis_python=qgis_python(),
        qgis_launcher=find_qgis_launcher(),
        niva_installed=_installed_niva_version(),
        on_path=pathenv.is_on_path(pathenv.read_user_path(), target.parent),
        launcher_path=target if target.exists() else None,
    )
    if os.name == "nt" and report.qgis_launcher is None:
        report.warnings.append(
            "python-qgis.bat not found; the launcher will call the Python exe directly, which may "
            "lack the QGIS environment for `run`. Set OSGEO4W_ROOT or install QGIS via OSGeo4W."
        )
    return report


# --------------------------------------------------------------------------- command launcher
def install_command(*, dry_run: bool = False) -> StepResult:
    """Create the ``niva`` launcher and add its dir to the per-user PATH. Idempotent."""
    target = launcher_target()
    bindir = target.parent
    invocation = qgis_invocation()
    if invocation is None:
        return StepResult(
            ok=False,
            changed=False,
            message="Couldn't find QGIS's python-qgis.bat, so I won't write a launcher pointing at a "
            "non-QGIS Python. Run this from the QGIS plugin, or set OSGEO4W_ROOT to your QGIS folder.",
        )

    file_current = target.exists() and pathenv.launcher_matches(target, invocation)
    already_on_path = pathenv.is_on_path(pathenv.read_user_path(), bindir)
    would_change = (not file_current) or (not already_on_path)

    if dry_run:
        path_note = (
            "PATH already includes it"
            if already_on_path
            else f"add {bindir} to your PATH"
        )
        return StepResult(
            ok=True,
            changed=would_change,
            message=f"Would write `niva` launcher at {target} and {path_note}.",
            detail=f"launcher invokes: {invocation}",
            undo_hint="niva setup command --remove",
        )

    file_changed = pathenv.write_launcher(target, invocation)
    path_changed, prior = pathenv.ensure_on_path(bindir)
    if path_changed:
        pathenv.broadcast_env_change()

    changed = file_changed or path_changed
    if not changed:
        return StepResult(
            ok=True,
            changed=False,
            message=f"`niva` command already set up at {target}.",
        )
    tail = " Open a new terminal to use it." if path_changed else ""
    return StepResult(
        ok=True,
        changed=True,
        message=f"Installed `niva` command -> {target}.{tail}",
        detail=f"invokes: {invocation}\nprior PATH: {prior}",
        undo_hint="niva setup command --remove",
    )


def uninstall_command(*, dry_run: bool = False) -> StepResult:
    """Remove the launcher and take its dir back off the per-user PATH."""
    target = launcher_target()
    bindir = target.parent
    on_path = pathenv.is_on_path(pathenv.read_user_path(), bindir)
    exists = target.exists()

    if dry_run:
        if not exists and not on_path:
            return StepResult(
                ok=True, changed=False, message="`niva` command is not installed."
            )
        return StepResult(
            ok=True,
            changed=True,
            message=f"Would remove {target} and take {bindir} off your PATH.",
            undo_hint="niva setup command",
        )

    if exists:
        try:
            target.unlink()
        except OSError:
            pass
    path_changed, _prior = pathenv.remove_from_path(bindir)
    if path_changed:
        pathenv.broadcast_env_change()
    changed = exists or path_changed
    msg = (
        "Removed the `niva` command."
        if changed
        else "`niva` command was not installed."
    )
    return StepResult(
        ok=True, changed=changed, message=msg, undo_hint="niva setup command"
    )
