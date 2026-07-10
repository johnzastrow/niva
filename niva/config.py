"""Portable, QGIS-free niva configuration (docs/planning/20 §9, issue #36).

A single TOML file — ``$XDG_CONFIG_HOME/niva/config.toml`` on Linux, the platform
equivalent on macOS/Windows — holds niva's **non-secret** settings, so you can view and
edit them **without opening QGIS**, and copy the file to move your setup between machines.

Secrets (tokens, passwords) never live here: they come from the environment, or from QGIS's
encrypted auth store (``QgsAuthManager``, via ``niva.credentials``) shared with the plugin.
``set`` refuses a secret key and says where it belongs.

Zero-dependency: reads with stdlib ``tomllib`` (Python 3.11+); writes a small, commented
TOML by hand (values are strings), so no TOML-writer dependency enters QGIS's Python.
"""

from __future__ import annotations

import os
import sys

_APP = "niva"
_FILENAME = "config.toml"

# Non-secret settings a user may want to set portably: key -> (mirrored env var, comment).
KNOWN_KEYS: dict[str, tuple[str, str]] = {
    "qgis_python": (
        "NIVA_QGIS_PYTHON",
        "Path to QGIS's Python — the runtime `niva run` executes with.",
    ),
    "log_dir": ("NIVA_LOG", "Directory for run journals."),
    "scratch_dir": ("NIVA_TMPDIR", "Scratch/temp directory for intermediate outputs."),
    "templates_dir": (
        "NIVA_TEMPLATES",
        "Directory of QGIS project templates (`project from-template=`).",
    ),
    "qgis_profile": ("NIVA_QGIS_PROFILE", "QGIS profile whose @connections niva uses."),
    "ntfy_topic": ("NIVA_NTFY_TOPIC", "ntfy topic for the `notify` verb."),
    "ntfy_server": ("NIVA_NTFY_SERVER", "ntfy server URL (default https://ntfy.sh)."),
    "smtp_host": ("NIVA_SMTP_HOST", "SMTP host for the `email` verb."),
    "smtp_port": ("NIVA_SMTP_PORT", "SMTP port."),
    "smtp_user": ("NIVA_SMTP_USER", "SMTP username."),
    "smtp_from": ("NIVA_SMTP_FROM", "Default From: address for `email`."),
}

# Secret settings — refused by `set`; they belong in the environment / OS keyring.
SECRET_KEYS: dict[str, str] = {
    # Values are env-var NAMES, not secrets — allowlist the scanner's false positives.
    "ntfy_token": "NIVA_NTFY_TOKEN",  # pragma: allowlist secret
    "smtp_password": "NIVA_SMTP_PASSWORD",  # pragma: allowlist secret
}

# Example values used only by the sample template (`niva setup init`).
_EXAMPLES: dict[str, str] = {
    "qgis_python": "/usr/bin/python3",
    "log_dir": "~/niva/logs",
    "scratch_dir": "~/niva/scratch",
    "templates_dir": "~/niva/templates",
    "qgis_profile": "default",
    "ntfy_topic": "niva-jobs",
    "ntfy_server": "https://ntfy.sh",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": "587",
    "smtp_user": "you@example.com",
    "smtp_from": "niva@example.com",
}


def config_dir() -> str:
    """The platform-appropriate niva config directory (XDG on Linux)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, _APP)


def config_path() -> str:
    """Full path to ``config.toml`` (may not exist yet)."""
    return os.path.join(config_dir(), _FILENAME)


def load() -> dict:
    """The parsed config (``{}`` if the file is missing or unreadable)."""
    import tomllib

    try:
        with open(config_path(), "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _toml_str(value: object) -> str:
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def save(data: dict) -> str:
    """Write ``data`` to the config file (creating its directory), with known keys
    commented and any extra keys preserved. Returns the path."""
    os.makedirs(config_dir(), exist_ok=True)
    path = config_path()
    lines = [
        "# niva configuration — portable and QGIS-free (issue #36).",
        "# Copy this file to move your setup between machines.",
        "# Secrets (tokens, passwords) do NOT belong here — set them in the environment.",
        "",
    ]
    written: set[str] = set()
    for key, (env, comment) in KNOWN_KEYS.items():
        if key in data:
            lines.append(f"# {comment} (env: {env})")
            lines.append(f"{key} = {_toml_str(data[key])}")
            lines.append("")
            written.add(key)
    extras = [k for k in data if k not in written]
    if extras:
        lines.append("# --- other keys ---")
        for key in extras:
            lines.append(f"{key} = {_toml_str(data[key])}")
    text = "\n".join(lines).rstrip() + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def get(key: str):
    """The configured value for ``key``, or None."""
    return load().get(key)


def set_key(key: str, value: str) -> str:
    """Set ``key`` = ``value`` and persist. Raises ``ValueError`` if ``key`` is a secret.
    Returns the config path."""
    if key in SECRET_KEYS:
        raise ValueError(
            f"'{key}' is a secret — set {SECRET_KEYS[key]} in your environment "
            "(or the OS keyring), never the config file."
        )
    data = load()
    data[key] = value
    return save(data)


def unset_key(key: str) -> str:
    """Remove ``key`` if present and persist. Returns the config path."""
    data = load()
    data.pop(key, None)
    return save(data)


def template() -> str:
    """A fully-commented sample config — every known key, commented out, with an example
    value — so a new user can see what they may set. Written by ``niva setup init``."""
    lines = [
        "# niva configuration — portable and QGIS-free (issue #36).",
        "# Copy this file to move your setup between machines. Uncomment a line and set its value.",
        "# `niva setup show` lists what's active; `niva setup set <key> <value>` edits it for you.",
        "#",
        "# Secrets (tokens, passwords) do NOT belong here — set them in the environment:",
        f"#   export {SECRET_KEYS['ntfy_token']}=...        export {SECRET_KEYS['smtp_password']}=...",
        "",
    ]
    for key, (env, comment) in KNOWN_KEYS.items():
        lines.append(f"# {comment}   (env: {env})")
        lines.append(f'# {key} = "{_EXAMPLES.get(key, "")}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_template(force: bool = False) -> tuple[str, bool]:
    """Write the sample config to :func:`config_path` when it does not exist (or ``force``).
    Returns ``(path, written)`` — ``written`` is False if a config was already there."""
    path = config_path()
    if os.path.exists(path) and not force:
        return path, False
    os.makedirs(config_dir(), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(template())
    return path, True
