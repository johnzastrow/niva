"""Shared language-services core for `.niva` files — the *intelligence* behind the repl, the
LSP, and (later) the studio: **completion**, **diagnostics**, and the verb/option index.

Pure and QGIS-free (built from the manifest + the offline validator), so every front-end calls
these directly, in-process. The LSP (`niva lsp`) is a thin JSON-RPC wrapper around the same
functions for external editors; the repl imports them for its own prompt. Keeping this one
module authoritative means completion and diagnostics can never drift between front-ends.
"""

from __future__ import annotations

import glob as _glob
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def index() -> dict:
    """Completion data from the manifest: per-verb option/flag names and each option's enum
    values, plus the sorted set of stage-initial names (verbs + built-ins). QGIS-free."""
    from .manifest import build_manifest

    m = build_manifest()
    verbs: dict = {}
    for v in m["verbs"]:
        verbs[v["name"]] = {
            "options": [o["name"] for o in v["options"]],
            "flags": [f["name"] for f in v["flags"]],
            "enums": {o["name"]: o["enum"] for o in v["options"] if o.get("enum")},
        }
    names = sorted(set(verbs) | set(m["builtins"]))
    return {"verbs": verbs, "names": names}


def verb_names() -> set:
    """The set of stage-initial names (verbs + built-ins) — for highlighters/classifiers."""
    return set(index()["names"])


def current_token(text: str) -> str:
    """The token currently being typed at the end of ``text`` (empty right after a space)."""
    stage = text.rsplit("|", 1)[-1]
    if not stage or stage[-1].isspace():
        return ""
    return stage.split()[-1]


def fs_complete(token: str) -> list[str]:
    """Filesystem completions for a partial path ``token``: matching files and directories,
    directories suffixed with ``/`` so you can keep tabbing into them. ``~`` is expanded; an
    empty token lists the current directory. Capped so a huge directory can't flood the menu."""
    out = []
    try:
        for m in sorted(_glob.glob(os.path.expanduser(token) + "*")):
            out.append(m + "/" if os.path.isdir(m) else m)
    except OSError:
        return []
    return out[:200]


def completions(text: str) -> list[str]:
    """Context-aware completions for flow ``text`` up to the cursor — the pure, testable core
    of tab completion shared by the repl and the LSP:

    * at a stage start (line start or after ``|``) → verb + built-in names;
    * after a verb → that verb's ``option=`` names and flags, **plus filesystem paths** (so
      ``load``/``show``/``save`` etc. complete files and directories);
    * after ``option=`` → the option's enum values, else filesystem paths (for path-valued
      options like ``raster=``/``with=``).
    """
    idx = index()
    stage = text.rsplit("|", 1)[-1]
    toks = stage.split()
    trailing_space = bool(stage) and stage[-1].isspace()

    # Stage start: still typing (or about to type) the first token → complete verb names.
    if not toks or (len(toks) == 1 and not trailing_space):
        prefix = toks[0] if toks else ""
        return [n for n in idx["names"] if n.startswith(prefix)]

    verb = toks[0]
    cur = "" if trailing_space else toks[-1]

    # `run <provider:id> KEY=value` — the escape hatch reaches every QGIS algorithm, so complete
    # the 878 catalogued ids (the "native ones"), then that algorithm's KEY= params and enum values.
    if verb == "run":
        return _run_completions(toks, cur, trailing_space)

    if (
        verb not in idx["names"]
    ):  # a real verb (built-in or alias)? — else offer nothing
        return []
    info = idx["verbs"].get(verb)  # None for built-in verbs (no alias option catalogue)

    if "=" in cur:  # completing an option's value
        key, _, val = cur.partition("=")
        enum = info["enums"].get(key) if info else None
        if enum:
            return [f"{key}={v}" for v in enum if v.startswith(val)]
        return [f"{key}={p}" for p in fs_complete(val)]  # path-valued option

    # A positional argument: offer the verb's options/flags (if any) AND filesystem paths, so a
    # path argument (load/show/save/clip/each/catalog/…) completes files and directories.
    cands: list = []
    if info:
        cands += [f"{name}=" for name in info["options"]] + list(info["flags"])
    cands = [c for c in cands if c.startswith(cur)]
    cands += fs_complete(cur)
    seen, out = set(), []
    for c in cands:  # de-dupe, preserve order (options/flags first, then paths)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _run_completions(toks: list, cur: str, trailing_space: bool) -> list[str]:
    """Completion inside a ``run`` stage: the algorithm id first (from the offline 878-id
    catalogue), then that algorithm's ``KEY=`` parameter names and enum values. QGIS-free."""
    from .registry import catalog as _cat

    try:
        cat = _cat.catalog()
    except Exception:  # noqa: BLE001 — no packaged catalogue → nothing to offer
        return []

    # Still on the id itself: only `run` typed, or typing the id with no trailing space yet.
    if len(toks) == 1 or (len(toks) == 2 and not trailing_space):
        return sorted(aid for aid in cat if aid.startswith(cur))[:200]

    entry = cat.get(toks[1])  # toks[1] is the algorithm id
    if not entry:
        return []
    params = entry.get("params") or []
    if "=" in cur:  # completing a parameter value → enum options, if any
        key, _, val = cur.partition("=")
        for p in params:
            if p.get("name") == key and p.get("enum"):
                return [f"{key}={v}" for v in p["enum"] if str(v).startswith(val)]
        return []
    return [f"{p['name']}=" for p in params if p.get("name", "").startswith(cur)]


def diagnostics(text: str) -> list[dict]:
    """Structured diagnostics for a whole ``.niva`` document — the offline validator's findings
    as ``{line, severity, message}`` (line is **1-based**; severity is ``"error"``/``"warning"``).
    The same closed-set + binding checks as ``niva validate``; QGIS-free. Consumed by the LSP
    (mapped to LSP ranges) and available to any other front-end."""
    from .validate import validate_text

    t = text.strip()
    if not t:
        return []
    _ok, issues = validate_text(text)
    out = []
    for line, severity, message in issues:
        out.append({"line": line or 1, "severity": severity, "message": message})
    return out


def validity(text: str) -> tuple[str, str]:
    """(symbol, message) summarising a single flow line for an inline prompt: ``✓``/``✗``/``⚠``
    plus the first issue. Used by the repl's echo/toolbar."""
    t = text.strip()
    if not t:
        return "", ""
    from .validate import validate_text

    ok, issues = validate_text(t)
    errs = [i for i in issues if i[1] == "error"]
    if errs:
        ln, _sev, msg = errs[0]
        return "✗", f"{'line ' + str(ln) + ': ' if ln else ''}{msg}"
    if issues:
        return "⚠", issues[0][2]
    if ok:
        return "✓", "valid"
    return "✗", "invalid"
