"""niva's optional marimo on-ramp (planning doc 21 §10).

niva **never installs marimo itself** — it installs the *marimo-qgis plugin* and delegates the actual
marimo install to that plugin's own ``MarimoProcessManager().install_marimo()`` (pip, async, with its
own fallbacks). This keeps marimo's dependency tree, its uv/pip machinery, and its localhost server
entirely inside marimo-qgis's trust boundary.

The plugin is installed **through QGIS's own installer** (``pyplugin_installer.installFromZipFile``)
rather than by hand, so QGIS registers it as a normal user plugin — enabled, and **uninstallable**
from *Plugins → Manage and Install*. Gated to QGIS >= 4.0; a no-op unless the user clicks the button.

Threading (see the plugin's Install tab / QgsTask): :func:`download_release` is the only slow step and
is thread-safe (network + file write, no QGIS calls). :func:`install_from_zip` and
:func:`start_marimo_install` touch QGIS and MUST run on the main (GUI) thread.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .core import StepResult

MARIMO_QGIS_REPO = "https://github.com/johnzastrow/marimo-qgis"
MIN_QGIS_INT = 40000  # marimo-qgis requires QGIS 4.0+
# Pin to a specific marimo-qgis release (each ships a packaged marimo_launcher.zip asset). Bump this
# to adopt a newer marimo-qgis; a tag (not `main`) keeps the on-ramp reproducible.
MARIMO_QGIS_TAG = "v0.6.0"
RELEASE_ASSET = "marimo_launcher.zip"


def _qgis_version_int() -> Optional[int]:
    try:
        from qgis.core import Qgis

        return int(Qgis.QGIS_VERSION_INT)
    except Exception:
        return None


def _plugins_dir() -> Optional[Path]:
    try:
        from qgis.core import QgsApplication

        return Path(QgsApplication.qgisSettingsDirPath()) / "python" / "plugins"
    except Exception:
        return None


def _find_plugin_dir(plugins_dir: Path) -> Optional[Path]:
    """Return the installed marimo-qgis plugin folder (the one whose ``ui/process.py`` defines
    ``MarimoProcessManager``), robust to whatever the folder is named."""
    if not plugins_dir or not plugins_dir.is_dir():
        return None
    for proc in plugins_dir.glob("*/ui/process.py"):
        try:
            if "MarimoProcessManager" in proc.read_text(encoding="utf-8", errors="ignore"):
                return proc.parent.parent  # the plugin root
        except OSError:
            continue
    return None


def _call_install_marimo(plugins_dir: Path, plugin_dir: Path) -> tuple[bool, str]:
    """Import marimo-qgis's process module *as a package* (it uses relative imports, so a
    by-file-path import would fail) and call ``MarimoProcessManager().install_marimo()``."""
    try:
        import importlib

        if str(plugins_dir) not in sys.path:
            sys.path.insert(0, str(plugins_dir))
        mod = importlib.import_module(f"{plugin_dir.name}.ui.process")
        record = mod.MarimoProcessManager().install_marimo()  # async: installs in the background
        log = record.get("log") if isinstance(record, dict) else None
        msg = "marimo is installing in the background"
        return True, (f"{msg} (log: {log})." if log else f"{msg}.")
    except Exception as exc:  # noqa: BLE001 — surface the reason, don't crash the UI
        return False, f"couldn't start marimo's install via marimo-qgis ({exc})"


# --------------------------------------------------------------------------- public building blocks
def release_zip_url() -> str:
    return f"{MARIMO_QGIS_REPO}/releases/download/{MARIMO_QGIS_TAG}/{RELEASE_ASSET}"


def is_installed() -> bool:
    d = _plugins_dir()
    return bool(d and _find_plugin_dir(d))


def preflight() -> Optional[StepResult]:
    """Return a blocking :class:`StepResult` if marimo can't be installed here (not in QGIS, or
    QGIS < 4.0, or no plugins dir), else ``None``."""
    ver = _qgis_version_int()
    if ver is None:
        return StepResult(ok=False, changed=False, message="Marimo integration must run inside QGIS.")
    if ver < MIN_QGIS_INT:
        return StepResult(
            ok=False,
            changed=False,
            message=f"marimo-qgis requires QGIS 4.0+ (this is {ver // 10000}.{(ver // 100) % 100}).",
        )
    if _plugins_dir() is None:
        return StepResult(ok=False, changed=False, message="Couldn't locate the QGIS plugins folder.")
    return None


def download_release(dest: Path) -> Optional[str]:
    """**Thread-safe.** Download the pinned marimo-qgis release asset to *dest*. Returns an error
    message on failure, or ``None`` on success. No QGIS calls — safe to run in a QgsTask worker."""
    import urllib.request

    try:
        # nosec B310 / noqa S310 — release_zip_url() is a fixed https://github.com/… URL (built from
        # module constants), so the scheme is never attacker-controlled.
        with urllib.request.urlopen(release_zip_url(), timeout=60) as resp:  # noqa: S310  # nosec B310
            data = resp.read()
        dest.write_bytes(data)
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def install_from_zip(zip_path: Path) -> bool:
    """**Main-thread only.** Install the plugin through QGIS's own installer so it is registered as a
    normal user plugin — enabled and uninstallable from *Plugins → Manage and Install*. True on ok."""
    try:
        import pyplugin_installer

        pyplugin_installer.instance().installFromZipFile(str(zip_path))
        return True
    except Exception:  # noqa: BLE001
        return False


def start_marimo_install() -> tuple[bool, str]:
    """**Main-thread.** Ask the installed marimo-qgis plugin to install marimo (its own async pip)."""
    plugins_dir = _plugins_dir()
    present = _find_plugin_dir(plugins_dir) if plugins_dir else None
    if present is None:
        return False, "marimo-qgis plugin isn't installed yet"
    return _call_install_marimo(plugins_dir, present)


# --------------------------------------------------------------------------- synchronous all-in-one
def install_marimo_qgis(*, dry_run: bool = False) -> StepResult:
    """Install the marimo-qgis plugin (if absent, via QGIS's installer) and start marimo's install.
    Synchronous — for the CLI or a non-threaded caller; **must run on the GUI main thread** in a
    running QGIS. The plugin's Install tab uses the building blocks above under a QgsTask instead."""
    block = preflight()
    if block:
        return block

    present = is_installed()
    if dry_run:
        where = (
            "the installed marimo-qgis plugin"
            if present
            else f"download {MARIMO_QGIS_TAG} and install it via QGIS's plugin installer"
        )
        return StepResult(
            ok=True,
            changed=True,
            message=f"Would start marimo's install via {where} (marimo-qgis owns the pip step).",
        )

    if not present:
        import tempfile

        zp = Path(tempfile.gettempdir()) / RELEASE_ASSET
        err = download_release(zp)
        if err:
            return StepResult(
                ok=False,
                changed=False,
                message=f"Couldn't download marimo-qgis {MARIMO_QGIS_TAG} ({err}). "
                "Install it manually from the repo's Releases.",
                detail=f"{MARIMO_QGIS_REPO}/releases",
            )
        if not install_from_zip(zp):
            return StepResult(
                ok=False,
                changed=False,
                message="QGIS couldn't install the marimo-qgis zip; install it manually from Releases.",
                detail=f"{MARIMO_QGIS_REPO}/releases",
            )

    ok, msg = start_marimo_install()
    tail = " Open the marimo Launcher dock (Browse / Running)." if ok else ""
    return StepResult(ok=ok, changed=True, message=msg + tail, detail=MARIMO_QGIS_REPO)
