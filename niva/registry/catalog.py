"""Offline access to the packaged QGIS algorithm catalog (``algorithms.json``).

``scripts/gen_algorithms.py`` introspects the live QGIS registry and writes
``niva/registry/algorithms.json`` — every algorithm's parameters (name, type, default,
enum options), outputs, group, and the niva verb that aliases it. That file is packaged
with niva, so ``describe <id>`` and offline ``run`` validation work with **no QGIS**
(issues #25, #26). Loaded once and cached.
"""

from __future__ import annotations

import json
from functools import lru_cache


@lru_cache(maxsize=1)
def _payload() -> dict:
    """The parsed ``algorithms.json`` (``{}`` if it isn't packaged/readable)."""
    try:
        from importlib.resources import files

        text = (
            files("niva.registry")
            .joinpath("algorithms.json")
            .read_text(encoding="utf-8")
        )
        return json.loads(text)
    except Exception:  # noqa: BLE001 — no catalog shipped / unreadable → empty
        return {}


def catalog() -> dict:
    """``{id: entry}`` for every catalogued algorithm (empty if none shipped)."""
    return _payload().get("algorithms", {})


def qgis_version() -> str:
    """The QGIS version the catalog was generated against (``""`` if unknown)."""
    return _payload().get("qgis_version", "")


def algorithm(algorithm_id: str) -> dict | None:
    """The catalog entry for ``algorithm_id``, or None."""
    return catalog().get(algorithm_id)


def algorithm_info(algorithm_id: str) -> dict | None:
    """The same shape :func:`niva.engine.pyqgis.algorithm_info` returns, built from the
    offline catalog — so ``describe`` can format it identically without QGIS."""
    e = algorithm(algorithm_id)
    if e is None:
        return None
    return {
        "id": e["id"],
        "display_name": e.get("name", e["id"]),
        "provider": e.get("provider", ""),
        "params": e.get("params", []),
        "outputs": e.get("outputs", []),
    }


def param_names(algorithm_id: str) -> set[str] | None:
    """The set of valid parameter names for ``algorithm_id`` (for `run` validation), or
    None if the id isn't in the catalog."""
    e = algorithm(algorithm_id)
    if e is None:
        return None
    names = {p["name"] for p in e.get("params", [])}
    names.update(o["name"] for o in e.get("outputs", []))
    return names
