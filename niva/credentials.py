"""Resolve niva's runtime secrets (ntfy token, SMTP password) uniformly across every surface —
CLI, repl, TUI, and plugin.

A secret is taken from the **environment** if set (an explicit override), otherwise from QGIS's
**encrypted auth store** (``QgsAuthManager``) — the same store the plugin's "Save secrets to QGIS
encrypted store" button writes to. So a user who saved their SMTP password / ntfy token in QGIS
once gets it everywhere, without exporting it into every shell.

Hard rules (global CLAUDE.md Part B): secrets never live in niva's config file, are never logged,
and reading the auth store **never blocks or prompts**. On a headless CLI where the QGIS auth
master password is not unlocked (and ``QGIS_AUTH_PASSWORD_FILE`` is not set), we quietly fall back
to ``None`` rather than trigger an interactive prompt.
"""

from __future__ import annotations

import os
from typing import Optional

# QgsSettings keys under which the plugin records the (non-secret) authcfg IDs; the secrets
# themselves live encrypted in QGIS's auth DB. Single source of truth — the plugin imports these.
SMTP_AUTHCFG_KEY = "niva/smtp_authcfg"
NTFY_AUTHCFG_KEY = "niva/ntfy_authcfg"

# secret kind -> (QgsSettings key holding the authcfg id, field name inside QgsAuthMethodConfig)
_KINDS: dict[str, tuple[str, str]] = {
    "smtp_password": (SMTP_AUTHCFG_KEY, "password"),
    "ntfy_token": (NTFY_AUTHCFG_KEY, "password"),
}


def get_secret(env_var: str, kind: str, env=None) -> Optional[str]:
    """Return the secret: the environment variable *env_var* if set (override), else QGIS's
    encrypted auth store, else ``None``. Never raises, never prompts."""
    env = os.environ if env is None else env
    value = env.get(env_var)
    if value:
        return value
    return _from_authstore(kind)


def ntfy_token(env=None) -> Optional[str]:
    return get_secret("NIVA_NTFY_TOKEN", "ntfy_token", env)


def smtp_password(env=None) -> Optional[str]:
    return get_secret("NIVA_SMTP_PASSWORD", "smtp_password", env)


def _from_authstore(kind: str) -> Optional[str]:
    """Read a secret from QGIS's encrypted auth DB, or ``None`` if unavailable/locked. Guarded so
    it is safe to call with no QGIS (offline CLI) and never triggers a master-password prompt."""
    spec = _KINDS.get(kind)
    if spec is None:
        return None
    settings_key, field = spec
    try:
        from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings
    except Exception:
        return None  # no QGIS in this interpreter — the environment is the only source
    try:
        authid = QgsSettings().value(settings_key, "") or ""
        if not authid:
            return None
        am = QgsApplication.authManager()
        # Only read when the auth store is already unlocked (a plugin session, or the CLI with
        # QGIS_AUTH_PASSWORD_FILE set). Never force an interactive prompt on a headless run.
        if hasattr(am, "masterPasswordIsSet") and not am.masterPasswordIsSet():
            return None
        cfg = QgsAuthMethodConfig()
        am.loadAuthenticationConfig(authid, cfg, True)  # full=True -> include secrets
        return cfg.config(field) or None
    except Exception:
        return None
