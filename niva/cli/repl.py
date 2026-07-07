"""`niva repl` — an interactive authoring prompt (docs/planning/20 §10 Tier 1, issue #41).

Zero-QGIS authoring: type a flow and get **manifest-driven tab completion** (verbs → their
options/flags → an option's enum values), **live validation**, and quick `?describe` / `/search`.

The rich experience uses ``prompt_toolkit`` (the ``[cli]`` extra: ``pip install qgis-niva[cli]``).
Without it, the repl **degrades gracefully** to a plain ``readline`` loop — the core never
*requires* the extra (Oscar E1 / the design's hard rule). Colour reuses ``niva.color``.
"""

from __future__ import annotations

import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def _index() -> dict:
    """Completion data from the manifest: per-verb option/flag names and each option's enum
    values, plus the sorted set of stage-initial names (verbs + built-ins). QGIS-free."""
    from ..manifest import build_manifest

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


def _current_token(text: str) -> str:
    """The token currently being typed at the end of ``text`` (empty after a space)."""
    stage = text.rsplit("|", 1)[-1]
    if not stage or stage[-1].isspace():
        return ""
    return stage.split()[-1]


def completions(text: str) -> list[str]:
    """Context-aware completions for flow ``text`` up to the cursor — the pure, testable core
    of the repl's tab completion:

    * at a stage start (line start or after ``|``) → verb + built-in names;
    * after a verb → that verb's ``option=`` names and flags;
    * after ``option=`` where the option is an enum → its values (as ``option=value``).
    """
    idx = _index()
    stage = text.rsplit("|", 1)[-1]
    toks = stage.split()
    trailing_space = bool(stage) and stage[-1].isspace()

    # Stage start: still typing (or about to type) the first token → complete verb names.
    if not toks or (len(toks) == 1 and not trailing_space):
        prefix = toks[0] if toks else ""
        return [n for n in idx["names"] if n.startswith(prefix)]

    verb = toks[0]
    info = idx["verbs"].get(verb)
    if info is None:
        return []  # built-in or unknown verb — no option catalogue to offer

    cur = "" if trailing_space else toks[-1]
    if "=" in cur:  # completing an option's value
        key, _, val = cur.partition("=")
        enum = info["enums"].get(key)
        return [f"{key}={v}" for v in (enum or []) if v.startswith(val)]

    cands = [f"{name}=" for name in info["options"]] + list(info["flags"])
    return sorted(c for c in cands if c.startswith(cur))


def _validity(text: str) -> tuple[str, str]:
    """(symbol, message) summarising ``validate`` for a flow line: ✓/✗/⚠ + first issue."""
    from ..validate import validate_text

    t = text.strip()
    if not t:
        return "", ""
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


_HELP = """commands:
  <flow>          validate a flow (e.g. load a.gpkg | buffer 100m | save b.gpkg)
  .explain        show the resolved plan for the last flow
  ?<verb>         describe a verb (e.g. ?buffer)
  /<keyword>      search verbs & the algorithm catalog
  .help  .quit    this help / leave
Tab completes verbs, then their options/flags, then an option's enum values."""


def _handle(line: str, state: dict) -> str:
    """Process one entered ``line``. Returns "quit" to end the loop, else ""."""
    from .. import color

    if line in (".quit", ".exit", ".q"):
        return "quit"
    if line in (".help", ".?", "?"):
        print(_HELP)
        return ""
    if line == ".explain":
        flow = state.get("last")
        if not flow:
            print(color.paint("no flow yet — type one first", "dim"))
            return ""
        from ..grammar import parse
        from ..plan import build_plan, format_plan

        try:
            print(format_plan(build_plan(parse(flow))))
        except Exception as exc:  # noqa: BLE001 — a bad draft must not crash the repl
            print(color.paint(f"✗ {exc}", "red"))
        return ""
    if line.startswith("?"):  # ?verb → describe
        from .. import describe as _describe

        try:
            print(_describe(line[1:].strip()))
        except Exception as exc:  # noqa: BLE001
            print(color.paint(f"✗ {exc}", "red"))
        return ""
    if line.startswith("/"):  # /kw → search
        from ..registry.catalog import catalog
        from ..search import format_results
        from ..search import search as _search

        algs = [
            {"id": e.get("id", aid), "display_name": e.get("name", "")}
            for aid, e in catalog().items()
        ]
        hits = _search(line[1:].strip(), algorithms=algs, limit=15)
        print(format_results(line[1:].strip(), hits, color=True))
        return ""

    # Otherwise: treat the line as a flow → validate + remember it.
    state["last"] = line
    sym, msg = _validity(line)
    sty = "green" if sym == "✓" else ("yellow" if sym == "⚠" else "red")
    print(f"{color.paint(sym, sty)} {msg}")
    return ""


def _banner() -> str:
    from .. import __version__, color

    return color.paint(
        f"niva repl {__version__} — type a flow, Tab to complete, .help for commands, "
        ".quit to leave",
        "dim",
    )


def run(argv=None) -> int:
    """Start the interactive authoring repl (prompt_toolkit if available, else readline)."""
    print(_banner())
    state: dict = {"last": None}
    session = _make_session()
    while True:
        try:
            line = (session.prompt() if session else input("niva ▸ ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if _handle(line, state) == "quit":
            break
    print("bye")
    return 0


def _make_session():
    """A ``prompt_toolkit`` session with completion + a live-validation toolbar, or None when
    the extra isn't installed (the caller then falls back to plain ``input``)."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.application import get_app
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.history import InMemoryHistory
    except ImportError:
        print(
            "  (plain mode — `pip install qgis-niva[cli]` for tab completion & live validation)",
            file=sys.stderr,
        )
        return None

    class _NivaCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            cur = _current_token(text)
            for cand in completions(text):
                yield Completion(cand, start_position=-len(cur))

    def _toolbar():
        sym, msg = _validity(get_app().current_buffer.text)
        return f"{sym} {msg}" if sym else ""

    return PromptSession(
        message="niva ▸ ",
        completer=_NivaCompleter(),
        complete_while_typing=True,
        bottom_toolbar=_toolbar,
        history=InMemoryHistory(),
    )
