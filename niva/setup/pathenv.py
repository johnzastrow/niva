"""PATH + launcher primitives for the setup-core.

Two layers:

* **Pure string logic** (:func:`is_on_path`, :func:`path_append`, :func:`path_remove`) — no I/O,
  fully unit-tested. These never reformat the existing PATH beyond the single change requested:
  ``path_append`` appends the new entry to the end and touches nothing else.
* **OS I/O** (:func:`ensure_on_path`, :func:`remove_from_path`, :func:`write_launcher`,
  :func:`broadcast_env_change`) — the Windows registry / POSIX rc-file side. Kept thin so the risky
  bits are the small pure functions above.

Security notes (see planning doc 21 §5):

* PATH entries are **appended at the end**, never prepended, so the launcher dir can't shadow
  system tools like ``python`` or ``git``.
* On Windows we edit the **per-user** ``HKCU\\Environment`` only (never system ``HKLM``, never
  admin) and preserve the value's registry type so ``%VAR%`` expansion elsewhere keeps working.
* ``setx`` is deliberately avoided — it truncates PATH at ~1024 chars and can corrupt it.
"""

from __future__ import annotations

import os
from pathlib import Path

IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- pure PATH logic
def _norm(entry: str) -> str:
    """Normalize a PATH entry for comparison (case/style-fold per-OS)."""
    return os.path.normcase(os.path.normpath(entry.strip().strip('"')))


def _split(value: str, sep: str) -> list[str]:
    return [e for e in value.split(sep) if e.strip()]


def is_on_path(value: str, directory: str | os.PathLike, sep: str = os.pathsep) -> bool:
    """True if *directory* is already an entry in the PATH string *value*."""
    target = _norm(str(directory))
    return any(_norm(e) == target for e in _split(value, sep))


def path_append(
    value: str, directory: str | os.PathLike, sep: str = os.pathsep
) -> tuple[str, bool]:
    """Return ``(new_value, changed)``. Appends *directory* to the **end** of *value* unless it is
    already present. When unchanged, returns *value* verbatim (no reformatting)."""
    directory = str(directory)
    if is_on_path(value, directory, sep):
        return value, False
    if not value:
        return directory, True
    joiner = "" if value.endswith(sep) else sep
    return value + joiner + directory, True


def path_remove(
    value: str, directory: str | os.PathLike, sep: str = os.pathsep
) -> tuple[str, bool]:
    """Return ``(new_value, changed)`` with every entry equal to *directory* removed."""
    target = _norm(str(directory))
    parts = _split(value, sep)
    kept = [e for e in parts if _norm(e) != target]
    if len(kept) == len(parts):
        return value, False
    return sep.join(kept), True


# --------------------------------------------------------------------------- launcher file
def launcher_body(invocation: str, *, windows: bool | None = None) -> str:
    """The text of the ``niva`` launcher that forwards to QGIS's Python.

    *invocation* is the command the launcher runs — ``python-qgis.bat`` on Windows (which sets up
    the full QGIS environment) or the QGIS ``python3`` on POSIX.
    """
    win = IS_WINDOWS if windows is None else windows
    if win:
        return f'@echo off\r\n"{invocation}" -m niva.cli.main %*\r\n'
    return f'#!/usr/bin/env bash\nexec "{invocation}" -m niva.cli.main "$@"\n'


def launcher_matches(path: Path, invocation: str) -> bool:
    """True if the launcher at *path* already has the exact expected content. Compared as **bytes**
    to avoid platform newline translation making an identical file look changed."""
    try:
        return path.read_bytes() == launcher_body(invocation).encode("utf-8")
    except OSError:
        return False


def write_launcher(path: Path, invocation: str) -> bool:
    """Write the launcher at *path* (creating parent dirs). Returns True if content changed.
    On POSIX the file is made executable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and launcher_matches(path, invocation):
        return False
    path.write_bytes(launcher_body(invocation).encode("utf-8"))
    if not IS_WINDOWS:
        path.chmod(0o755)
    return True


# --------------------------------------------------------------------------- OS PATH I/O
def read_user_path() -> str:
    """Read the persisted **per-user** PATH (registry on Windows, best-effort env elsewhere)."""
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _type = winreg.QueryValueEx(key, "Path")
                return value or ""
        except FileNotFoundError:
            return ""
    return os.environ.get("PATH", "")


def _write_user_path_windows(new_value: str) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
    ) as key:
        # Preserve the existing value's registry type (usually REG_EXPAND_SZ so %VAR% still expands);
        # default to REG_EXPAND_SZ for a fresh value.
        try:
            _old, vtype = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            vtype = winreg.REG_EXPAND_SZ
        winreg.SetValueEx(key, "Path", 0, vtype, new_value)


def ensure_on_path(directory: Path) -> tuple[bool, str]:
    """Append *directory* to the persisted user PATH if absent. Returns ``(changed, prior_value)``;
    *prior_value* is the full PATH before the change (kept so a later remove can be verified)."""
    prior = read_user_path()
    new_value, changed = path_append(prior, str(directory))
    if changed:
        if IS_WINDOWS:
            _write_user_path_windows(new_value)
        else:
            _append_posix_rc(directory)
    return changed, prior


def remove_from_path(directory: Path) -> tuple[bool, str]:
    """Remove *directory* from the persisted user PATH. Returns ``(changed, prior_value)``."""
    prior = read_user_path()
    new_value, changed = path_remove(prior, str(directory))
    if changed and IS_WINDOWS:
        _write_user_path_windows(new_value)
    # POSIX rc edits are left to _append_posix_rc's marker block; removal there is best-effort.
    return changed, prior


def _rc_marker() -> tuple[Path, str]:
    home = Path.home()
    rc = home / (".zshrc" if os.environ.get("SHELL", "").endswith("zsh") else ".bashrc")
    return rc, "# added by `niva setup command`"


def _append_posix_rc(directory: Path) -> None:
    rc, marker = _rc_marker()
    line = f'{marker}\nexport PATH="{directory}:$PATH"\n'
    existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker in existing:
        return
    with rc.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if existing and not existing.endswith("\n") else "") + line)


def broadcast_env_change() -> None:
    """Tell running processes the environment changed (Windows ``WM_SETTINGCHANGE``); no-op else."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x1A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except Exception:
        pass  # cosmetic; a new terminal picks up the change regardless
