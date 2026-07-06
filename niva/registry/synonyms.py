"""Curated synonym map (docs/planning/20 §7, issue #44).

Intent keywords → the niva verbs / `provider:id` algorithms they should surface, so a
search finds the right tool even when the user's word differs (`mosaic` → `gdal:merge`,
`append` → `native:mergevectorlayers`). A word that already *is* a verb name (`buffer`,
`clip`, `dissolve`) needs no entry — fuzzy name matching finds those. Layered on top of
the existing name/description search; also attached to each verb in the manifest.

Packaged data (`synonyms.json`); QGIS-free.
"""

from __future__ import annotations

import json
from functools import lru_cache


@lru_cache(maxsize=1)
def synonyms() -> dict:
    """``{keyword: [target, ...]}`` — each target a verb name or a ``provider:id``."""
    try:
        from importlib.resources import files

        text = (
            files("niva.registry").joinpath("synonyms.json").read_text(encoding="utf-8")
        )
        return json.loads(text)
    except Exception:  # noqa: BLE001 — no synonyms shipped / unreadable → empty
        return {}


@lru_cache(maxsize=1)
def by_target() -> dict:
    """Inverted map ``{target: [keyword, ...]}`` — the synonyms that surface each verb/id."""
    out: dict = {}
    for keyword, targets in synonyms().items():
        for target in targets:
            out.setdefault(target, []).append(keyword)
    return {target: sorted(set(words)) for target, words in out.items()}


def matches(keyword: str) -> list:
    """Targets whose synonym keyword contains ``keyword`` (case-insensitive substring)."""
    kw = keyword.lower().strip()
    if not kw:
        return []
    hits: list = []
    for word, targets in synonyms().items():
        if kw in word.lower():
            hits.extend(targets)
    return sorted(set(hits))
