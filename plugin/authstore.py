"""Helpers for QGIS's encrypted auth store that need no QGIS import (so they are unit-testable)."""

from __future__ import annotations


def stored_config_id(result, cfg) -> str | None:
    """The auth config ID if ``QgsAuthManager.storeAuthenticationConfig`` succeeded, else None.

    PyQGIS returns ``(ok, stored_config)`` -- a tuple, which is always truthy, so testing the
    result directly treats a failed store as a success. Older bindings returned a plain bool.
    Both shapes are handled. The ID is read from the returned config when there is one (QGIS also
    writes it back into ``cfg``).
    """
    if isinstance(result, tuple):
        ok = bool(result[0]) if result else False
        stored = result[1] if len(result) > 1 else cfg
    else:
        ok, stored = bool(result), cfg
    if not ok:
        return None
    cfg_id = (stored.id() if stored is not None else "") or (
        cfg.id() if cfg is not None else ""
    )
    return cfg_id or None
