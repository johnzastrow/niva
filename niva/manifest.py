"""The machine-readable niva manifest (docs/planning/20 §7, issue #44).

``build_manifest`` emits one JSON describing **every verb** — canonical name, the resolved
`provider:id`, a one-line summary, its parameters (name/type/default/enum/required), an
example, and curated **synonyms** — so IDEs, an LSP, and LLM agents can consume niva's
surface as *structured data* instead of scraping ``describe`` text. This is what lets an
agent query the real catalog and lint its draft rather than hallucinate a verb (the #28
failure mode, structurally prevented).

Built from the alias registry + the packaged synonym map. QGIS-free.
"""

from __future__ import annotations

MANIFEST_VERSION = "1"


def build_manifest() -> dict:
    """The full manifest (a JSON-serialisable dict)."""
    from . import __version__
    from .engine.engine import Engine
    from .registry import core_registry
    from .registry.synonyms import by_target

    reg = core_registry()
    syn = by_target()
    verbs = [_verb_entry(reg.get(name), syn) for name in sorted(reg.verbs())]
    builtins = sorted(set(Engine._BUILTIN_VERBS) | {"each", "call"})
    return {
        "niva_manifest": MANIFEST_VERSION,
        "niva_version": __version__,
        "counts": {"aliases": len(verbs), "builtins": len(builtins)},
        "verbs": verbs,
        "builtins": builtins,
    }


def _verb_entry(alias, syn: dict) -> dict:
    synonyms = sorted(set(syn.get(alias.verb, []) + syn.get(alias.algorithm, [])))
    return {
        "name": alias.verb,
        "algorithm": alias.algorithm,
        "summary": alias.summary,
        "example": alias.example,
        "synonyms": synonyms,
        "args": [
            {"name": a.name, "param": a.param, "type": a.type, "required": a.required}
            for a in alias.args
        ],
        "options": [
            {
                "name": key,
                "param": opt.param,
                "type": opt.type,
                "default": opt.default,
                "enum": sorted(opt.values) if opt.values else None,
                "required": opt.required,
            }
            for key, opt in alias.options.items()
        ],
        "flags": [
            {"name": key, "param": flag.param} for key, flag in alias.flags.items()
        ],
        "forced": alias.forced,
    }
