"""Fuzzy discovery over niva's verbs and the live QGIS algorithm catalog — the engine
for the `search` and `docs` verbs.

Zero-dependency by design (Oscar E1): ranking uses the stdlib ``difflib`` plus
substring / token matching, so discovery never pulls a search library into QGIS's
Python. The corpus is three sources, all of which ``search`` and ``docs`` cover:

  * **alias verbs** — name, summary, target algorithm id, option/flag names;
  * **built-in verbs** — name + summary from :data:`niva.describe.BUILTINS`;
  * **live QGIS algorithms** — id, display name, group, short description (passed in by
    the caller as ``algorithms``, since enumerating them needs QGIS).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .registry import core_registry
from .registry.synonyms import matches as _synonym_matches

# A curated synonym hit (`mosaic` → `gdal:merge`) is intentional, so it ranks above
# fuzzy-name/description matches but below an exact/substring name match (docs/planning/20 §7:
# exact verb → synonym → fuzzy → description).
_SYNONYM_SCORE = 0.8


@dataclass
class Hit:
    """One ranked search result. ``name`` is the handle you can hand to ``describe`` (a
    verb name or an algorithm id); ``kind`` is ``verb``/``builtin``/``algorithm``."""

    name: str
    kind: str
    summary: str
    score: float


def _score(query: str, *fields: str) -> float:
    """Best match of ``query`` against any of ``fields``. Blends exact/substring hits
    (strong, deterministic) with a fuzzy ``difflib`` ratio (tolerant of typos) and token
    prefix matching, returning the strongest signal in [0, 1]."""
    q = query.lower().strip()
    if not q:
        return 0.0
    best = 0.0
    for f in fields:
        if not f:
            continue
        t = f.lower()
        if q == t:
            return 1.0
        if q in t:
            best = max(best, 0.9)
        for tok in t.replace("_", " ").replace(":", " ").replace("/", " ").split():
            if tok == q:
                best = max(best, 0.85)
            elif tok.startswith(q):
                best = max(best, 0.72)
        best = max(best, difflib.SequenceMatcher(None, q, t).ratio())
    return best


def _entry_score(query: str, *fields: str) -> float:
    """Score with OR-semantics across query words: a multi-word query like
    ``"raster reproject"`` matches an entry that hits *any* of its words, so the user
    can throw several keywords at it. A single word scores normally."""
    words = query.lower().split()
    if len(words) <= 1:
        return _score(query, *fields)
    return max(_score(w, *fields) for w in words)


def search(
    query: str, *, algorithms=(), limit: int = 20, threshold: float = 0.45
) -> list:
    """Rank the corpus against ``query``, returning :class:`Hit` objects sorted by score
    (desc), then verbs before algorithms, then name. ``algorithms`` is the live catalog
    (``[{id, display_name, group, description}, …]`` from ``backend.algorithm_catalog()``);
    pass ``()`` to search only niva verbs (no QGIS). ``threshold`` filters weak matches;
    ``limit`` caps the result count."""
    from .describe import BUILTINS

    reg = core_registry()
    hits: list[Hit] = []
    # Verbs / algorithm ids surfaced by a curated synonym of the query (issue #44).
    syn_targets = set(_synonym_matches(query))

    for verb in reg.verbs():
        alias = reg.get(verb)
        s = _entry_score(
            query,
            verb,
            alias.summary,
            alias.algorithm,
            " ".join(alias.options),
            " ".join(alias.flags),
        )
        if verb in syn_targets:
            s = max(s, _SYNONYM_SCORE)
        if s >= threshold:
            hits.append(Hit(verb, "verb", alias.summary, s))

    for verb, (summary, _example) in BUILTINS.items():
        s = _entry_score(query, verb, summary)
        if verb in syn_targets:
            s = max(s, _SYNONYM_SCORE)
        if s >= threshold:
            hits.append(Hit(verb, "builtin", summary, s))

    for alg in algorithms:
        s = _entry_score(
            query,
            alg.get("id", ""),
            alg.get("display_name", ""),
            alg.get("group", ""),
            alg.get("description", ""),
        )
        if alg.get("id", "") in syn_targets:
            s = max(s, _SYNONYM_SCORE)
        if s >= threshold:
            hits.append(Hit(alg["id"], "algorithm", alg.get("display_name", ""), s))

    # Stable, useful ordering: best score first; on ties prefer niva verbs over raw
    # algorithms (more directly usable), then alphabetical for determinism.
    _kind_rank = {"verb": 0, "builtin": 1, "algorithm": 2}
    hits.sort(key=lambda h: (-h.score, _kind_rank.get(h.kind, 3), h.name))
    return hits[:limit]


def format_results(query: str, hits: list) -> str:
    """A compact Markdown listing of `search` hits — name, kind, summary, score."""
    if not hits:
        return (
            f"# No matches for `{query}`\n\n"
            "Try a shorter or more general keyword (search is fuzzy)."
        )
    lines = [
        f"# {len(hits)} match(es) for `{query}`",
        "",
        "| Match | Kind | Score | Summary |",
        "|---|---|---:|---|",
    ]
    for h in hits:
        summary = h.summary.replace("|", "\\|") if h.summary else ""
        lines.append(f"| `{h.name}` | {h.kind} | {h.score:.2f} | {summary} |")
    lines.append("")
    lines.append(
        f"Run `describe <name>` for any of these, or `docs {query}` for the full "
        "reference of every match."
    )
    return "\n".join(lines)


def format_docs(query: str, hits: list, describe_fn) -> str:
    """A made-to-order mini-guide: the FULL `describe` (args, options, flags, example) of
    every match, concatenated. ``describe_fn`` is :func:`niva.describe.describe`; one entry
    failing to introspect (e.g. an algorithm needing QGIS) degrades to a note, never sinks
    the whole guide."""
    if not hits:
        return (
            f"# No matches for `{query}`\n\n"
            "Try a shorter or more general keyword (search is fuzzy)."
        )
    blocks = [f"# Reference for `{query}` — {len(hits)} match(es)", ""]
    for h in hits:
        blocks.append(f"## `{h.name}`  ({h.kind})")
        try:
            body = describe_fn(h.name)
            blocks += ["```", body, "```", ""]
        except Exception as exc:  # noqa: BLE001 — one bad entry must not sink the guide
            blocks += [f"_{h.summary or ''}_  (could not introspect: {exc})", ""]
    return "\n".join(blocks)
