"""`niva repl` — an interactive authoring prompt (docs/planning/20 §10 Tier 1, issue #41).

Zero-QGIS authoring: type a flow and get **manifest-driven tab completion** (verbs → their
options/flags → an option's enum values, and **filesystem paths** for path arguments),
**live validation**, **syntax highlighting**, and quick `?describe` / `/search`. Read-only
report verbs (`info`, `show`) and `.run` execute against real QGIS.

The rich experience uses ``prompt_toolkit`` (the ``[cli]`` extra: ``pip install qgis-niva[cli]``)
— live per-keystroke highlighting, a completion menu, and a colour validity toolbar. Without it,
the repl **degrades gracefully** to a plain ``readline`` loop that still colours the prompt, echoes
each flow **syntax-highlighted** (:func:`highlight_flow`), and colours all output — the core never
*requires* the extra (Oscar E1 / the design's hard rule). All colour reuses ``niva.color``, so it
turns off automatically off-TTY / under ``NO_COLOR``.
"""

from __future__ import annotations

import os
import re
import sys


def _history_path() -> str:
    """Path to the persistent repl command-history file, in niva's config dir (XDG on Linux).
    The parent dir is created; on any failure we fall back to ``~/.niva_repl_history`` so a
    read-only config dir never breaks the repl."""
    try:
        from ..config import config_dir

        d = config_dir()
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "repl_history")
    except Exception:  # noqa: BLE001 — history is a nicety; never let it break startup
        return os.path.expanduser("~/.niva_repl_history")


# The language-services core — completion, the verb/option index, path completion, and the
# validity summary — lives in niva.intelligence so the repl, the LSP, and (later) the studio
# share exactly one implementation and can never drift. `completions` is re-exported here for
# back-compatible imports (`from niva.cli.repl import completions`).
from ..intelligence import (  # noqa: E402
    completions,
    current_token as _current_token,
    validity as _validity,
    verb_names,
)


def _readline_completer(text, state):
    """readline completion hook for plain mode. readline replaces the current word (delimited
    by the completer-delims we set) with the chosen match, so we return full-token candidates
    from :func:`completions`, computed from the whole line up to the cursor for verb-aware
    context. Returns the ``state``-th match, or None when exhausted."""
    import readline as _rl

    try:
        line = _rl.get_line_buffer()[: _rl.get_endidx()]
        matches = completions(line)
    except Exception:  # noqa: BLE001 — a completion glitch must never break the prompt
        return None
    return matches[state] if 0 <= state < len(matches) else None


# ----------------------------------------------------------------- flow syntax highlighting

# One tokenizer shared by the ANSI highlighter (readline echo) and the prompt_toolkit lexer:
# keeps quoted strings whole (so a `|` inside "a.gpkg|layername=x" isn't mistaken for a pipe),
# and treats a bare `|` and runs of whitespace as their own tokens.
_TOKEN_RE = re.compile(r"\s+|\"[^\"]*\"|'[^']*'|\||[^\s|]+")

# token class → ANSI styles (for niva.color). The prompt_toolkit lexer maps the same class
# names to a Style below, so the two highlighters agree.
_STYLE_ANSI = {
    "verb": ("cyan", "bold"),
    "unknown": ("red",),
    "optkey": ("yellow",),
    "optval": ("green",),
    "conn": ("blue",),
    "path": ("green",),
    "flag": ("yellow",),
    "num": ("blue",),
    "pipe": ("magenta",),
}


def _classify(tok: str, first: bool, verbs) -> str:
    """The highlight class for one non-space token. ``first`` marks a stage-initial token
    (verb position). Pure — shared by both highlighters."""
    if first:
        return "verb" if tok in verbs else "unknown"
    if tok.startswith("@"):
        return "conn"
    if tok[:1] in "\"'":
        return "path"
    if "=" in tok:
        return "optkey"
    if "/" in tok or "\\" in tok:
        return "path"
    # A number (optionally signed/decimal, with an m/km-style unit suffix) → num; check this
    # before the dotted-filename rule so `2.5` and `100m` stay numeric, `a.gpkg` a path.
    stripped = tok.replace(".", "").replace("-", "").replace("m", "").replace("k", "")
    if stripped.isdigit():
        return "num"
    if "." in tok:  # a dotted bareword is a filename (roads.gpkg, dem.tif)
        return "path"
    return "flag"


def highlight_flow(text: str) -> str:
    """``text`` re-rendered with ANSI colour: verbs cyan (red if unknown), ``option=value``
    yellow/green, pipes magenta, ``@conn`` blue, paths/strings green. Used to echo the flow
    back in readline mode (where there's no live highlighter). Colour auto-off off-TTY."""
    from .. import color

    verbs = verb_names()
    out, at_start = [], True
    for m in _TOKEN_RE.finditer(text):
        tok = m.group()
        if not tok.strip():
            out.append(tok)  # preserve spacing
            continue
        if tok == "|":
            out.append(color.paint("|", "magenta"))
            at_start = True
            continue
        cls = _classify(tok, at_start, verbs)
        at_start = False
        if cls == "optkey" and "=" in tok:
            k, _, v = tok.partition("=")
            out.append(
                color.paint(k, "yellow")
                + color.paint("=", "dim")
                + color.paint(v, "green")
            )
        else:
            out.append(color.paint(tok, *_STYLE_ANSI[cls]))
    return "".join(out)


def _help_text() -> str:
    """The colourised command help (``.help``)."""
    from .. import color

    def row(cmd: str, desc: str) -> str:
        return f"  {color.paint(cmd, 'cyan')}{' ' * (14 - len(cmd))}{desc}"

    return "\n".join(
        [
            color.paint("commands:", "bold"),
            row(
                "<flow>",
                "validate a flow (e.g. load a.gpkg | buffer 100m | save b.gpkg)",
            ),
            row(".run", "execute the last flow against real QGIS (also: .run <flow>)"),
            row(".explain", "show the resolved plan for the last flow"),
            row(".history", "list the flows entered this session"),
            row(".save", "save this session's flows to a file  (.save study.niva)"),
            row("?<verb>", "describe a verb (e.g. ?buffer)"),
            row("/<keyword>", "search verbs & the algorithm catalog"),
            row(".help", "this help          (also: help, ?)"),
            row(".quit", "leave              (also: quit, exit, q, or Ctrl-D)"),
            color.paint(
                "Tab completes verbs, then options/flags, then an option's enum values.",
                "dim",
            ),
        ]
    )


# Accept the variants people actually reach for — with or without the leading
# dot, plus psql/vim muscle memory (\q, :q) — so quitting and help never stump.
_QUIT = {".quit", ".exit", ".q", "quit", "exit", "q", r"\q", ":q"}
_HELP_CMDS = {".help", ".?", ".h", "?", "help", r"\?", ":h", ":help"}

# Bare, read-only report verbs the repl runs for real (not on the validation mock), so `info`
# shows your actual QGIS/providers and `show <path>` lists real layers — the mock would return
# misleading placeholder layers. Both are read-only and write nothing.
_AUTORUN_VERBS = {"info", "show"}


def _remember(state: dict, line: str) -> None:
    """Collect a runnable flow into the session list (for ``.history`` / ``.save``), skipping an
    immediately-repeated identical line so re-running the same draft doesn't pile up."""
    sess = state.setdefault("session", [])
    if not sess or sess[-1] != line:
        sess.append(line)


def _save_session(state: dict, target: str) -> None:
    """Write the session's flows to a ``.niva`` file — harvest the good commands you worked out
    interactively into a runnable script. One flow per line, with a short header; `.niva` is
    appended if missing. The full raw history (every line, across sessions) also persists at the
    repl history file for deeper mining."""
    from .. import color

    flows = state.get("session") or []
    if not flows:
        print(color.paint("nothing to save yet — enter some valid flows first", "dim"))
        return
    if not target:
        print(color.paint("usage: .save <file.niva>", "yellow"))
        return
    path = os.path.expanduser(target)
    if not path.endswith(".niva"):
        path += ".niva"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "# niva flows harvested from a repl session — edit/reorder as needed.\n"
            )
            fh.write(
                f"# {len(flows)} flow(s). Run with: niva run {os.path.basename(path)}\n\n"
            )
            fh.write("\n".join(flows) + "\n")
    except OSError as exc:
        print(color.paint(f"✗ could not write {path}: {exc}", "red"))
        return
    print(color.paint(f"saved {len(flows)} flow(s) → {path}", "green"))


def _handle(line: str, state: dict) -> str:
    """Process one entered ``line``. Returns "quit" to end the loop, else ""."""
    from .. import color

    if line in _QUIT:
        return "quit"
    if line in _HELP_CMDS:
        print(_help_text())
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
    if line == ".run" or line.startswith(".run "):  # execute against real QGIS
        flow = line[5:].strip() if line.startswith(".run ") else state.get("last")
        if not flow:
            print(color.paint("no flow yet — type one first, then .run", "dim"))
            return ""
        _run_flow(flow, state)
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
    if line == ".history":  # review the flows entered this session
        flows = state.get("session") or []
        if not flows:
            print(color.paint("no flows yet this session", "dim"))
        else:
            for i, fl in enumerate(flows, 1):
                print(f"  {color.paint(str(i).rjust(2), 'dim')}  {highlight_flow(fl)}")
        return ""
    if line == ".save" or line.startswith(
        ".save "
    ):  # harvest session flows → a .niva file
        _save_session(state, line[6:].strip() if line.startswith(".save ") else "")
        return ""
    if line.startswith("."):  # a mistyped dot-command shouldn't parse as a flow
        print(color.paint(f"unknown command {line!r} — try .help", "yellow"))
        return ""

    # Otherwise: treat the line as a flow.
    state["last"] = line
    # Read-only report verbs (`info`, `show`) describe your **real** environment/data — running
    # them on the validation mock is actively misleading (the mock returns placeholder layers), so
    # execute them for real against QGIS. Transform/producing flows stay validate-only until an
    # explicit `.run`. Only a bare single-stage `info`/`show …` auto-runs (a piped flow does not).
    first = line.split(None, 1)[0]
    if "|" not in line and first in _AUTORUN_VERBS:
        _run_flow(line, state)
        return ""
    sym, msg = _validity(line)
    sty = "green" if sym == "✓" else ("yellow" if sym == "⚠" else "red")
    print(f"{color.paint(sym, sty)} {highlight_flow(line)}")
    if (
        sym != "✗"
    ):  # a runnable flow (✓ or ⚠ warning) — remember it for `.save`/`.history`
        _remember(state, line)
    if sym != "✓":
        print(f"  {color.paint('→ ' + msg, sty)}")
    elif not state.get("_run_hinted"):
        state["_run_hinted"] = (
            True  # nudge once, so a valid flow's next step is obvious
        )
        print(color.paint("  → .run to execute this against QGIS", "dim"))
    return ""


def _run_flow(flow: str, state: dict) -> None:
    """Execute ``flow`` against **real QGIS**, streaming per-stage progress. QGIS is initialised
    once per session (cached in ``state`` — the first ``.run`` pays the startup cost, later ones
    are instant) and kept alive; the repl's exit path tears it down safely. Every error is caught
    and shown, so a bad flow — or a missing QGIS — never ends the session."""
    import sys
    import time

    from .. import color
    from ..engine import Engine
    from ..engine.native import wrap_native
    from ..errors import FlowError, OpError

    try:
        from ..engine.pyqgis import PyqgisBackend, ensure_qgis
    except ImportError as exc:  # niva installed without the engine? shouldn't happen
        print(color.paint(f"✗ QGIS backend unavailable: {exc}", "red"))
        return

    if "qgis_app" not in state:
        print(color.paint("· starting QGIS (first run)…", "dim"), flush=True)
        try:
            app, owns = ensure_qgis()
        except ImportError as exc:
            print(
                color.paint(
                    "✗ could not import QGIS — run the repl on QGIS's Python, or set "
                    f"NIVA_QGIS_PYTHONPATH to its bindings. [{exc}]",
                    "red",
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 — init can fail many ways; keep the repl alive
            print(color.paint(f"✗ QGIS failed to start: {exc}", "red"))
            return
        state["qgis_app"], state["qgis_owns"] = app, owns

    t0 = time.monotonic()

    def progress(msg):
        print(msg, file=sys.stderr, flush=True)

    try:
        from ..grammar import parse

        program = parse(flow)  # Engine.execute wants parsed statements, not raw text
        result = Engine(wrap_native(PyqgisBackend()), progress=progress).execute(
            program
        )
        from .main import _print_result

        _print_result(result)
        from ..engine.engine import _fmt_elapsed

        print(color.paint(f"# done in {_fmt_elapsed(time.monotonic() - t0)}", "dim"))
    except FlowError as exc:
        print(color.paint(f"✗ {exc}", "red"))
    except OpError as exc:
        print(color.paint(f"✗ {exc}", "red"))
    except Exception as exc:  # noqa: BLE001 — never let a run crash the repl
        print(color.paint(f"✗ unexpected: {type(exc).__name__}: {exc}", "red"))


def _banner() -> str:
    from .. import __version__, color

    head = color.paint(f"niva repl {__version__} — type a flow, Tab to complete", "dim")
    run_ln = (
        f"- {color.paint('Run', 'bold')}: .run  (execute the last flow against QGIS)"
    )
    quit_ln = f"- {color.paint('Quit', 'bold')}: .quit (or Ctrl-D)"
    help_ln = f"- {color.paint('Help', 'bold')}: .help"
    return f"{head}\n{run_ln}\n{quit_ln}\n{help_ln}"


def _readline_prompt() -> str:
    """The plain-mode prompt, cyan+bold when colour is on. The ``\\001``/``\\002`` markers tell
    readline the escapes are zero-width so it measures the line length correctly."""
    from .. import color

    if not color.enabled():
        return "niva ▸ "
    codes = color._CODES
    return f"\001{codes['bold']}{codes['cyan']}\002niva ▸ \001{codes['reset']}\002"


def run(argv=None) -> int:
    """Start the interactive authoring repl (prompt_toolkit if available, else readline)."""
    print(_banner())
    state: dict = {"last": None}
    session = _make_session()
    prompt = _readline_prompt()
    rl = None
    if session is None:
        # Plain fallback: importing readline makes input() a real line editor (arrow keys,
        # backspace, history) AND honours the \001/\002 zero-width markers in the prompt, so a
        # coloured prompt no longer throws off the cursor and garbles what you type. Load past
        # history so ↑ recalls commands from previous sessions too (prompt_toolkit does this via
        # FileHistory); persisted back on exit.
        try:
            import readline as rl

            rl.set_history_length(1000)
            try:
                rl.read_history_file(_history_path())
            except OSError:
                pass  # no history yet
            # Tab completion: verbs → options/flags/enums → and filesystem paths. `/` is removed
            # from the word delimiters so a whole path token completes as one unit.
            rl.set_completer(_readline_completer)
            rl.set_completer_delims(" \t\n|")
            rl.parse_and_bind("tab: complete")
        except ImportError:
            rl = None
    while True:
        try:
            line = (session.prompt() if session else input(prompt)).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if _handle(line, state) == "quit":
            break
    print("bye")
    if rl is not None:  # persist plain-mode history so ↑ works across sessions
        try:
            rl.write_history_file(_history_path())
        except OSError:
            pass
    # If a `.run` started QGIS in this session, tear it down the same way the one-shot CLI does:
    # exit QGIS and hard-exit before Python's GC races QGIS's C++ teardown (which segfaults and
    # would clobber the exit code). Only when we own the app (we initialised it).
    if state.get("qgis_owns") and state.get("qgis_app") is not None:
        import sys

        sys.stdout.flush()
        sys.stderr.flush()
        state["qgis_app"].exitQgis()
        os._exit(0)
    return 0


def _make_session():
    """A ``prompt_toolkit`` session with **live syntax highlighting**, completion, and a
    validity toolbar, or None when the extra isn't installed (the caller then falls back to
    plain ``input`` — which still colours the prompt, the echoed flow, and all output)."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.application import get_app
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.lexers import Lexer
        from prompt_toolkit.styles import Style
    except ImportError:
        print(
            "  (plain mode — `pip install qgis-niva[cli]` for tab completion & live highlighting)",
            file=sys.stderr,
        )
        return None

    verbs = verb_names()

    # Live highlighting: the same token classes the readline echo uses, mapped to a Style so
    # the two paths look identical. Fragments include whitespace so spacing is preserved.
    class _FlowLexer(Lexer):
        def lex_document(self, document):
            def get_line(lineno):
                frags, at_start = [], True
                for m in _TOKEN_RE.finditer(document.lines[lineno]):
                    tok = m.group()
                    if not tok.strip():
                        frags.append(("", tok))
                        continue
                    if tok == "|":
                        frags.append(("class:pipe", tok))
                        at_start = True
                        continue
                    frags.append((f"class:{_classify(tok, at_start, verbs)}", tok))
                    at_start = False
                return frags

            return get_line

    style = Style.from_dict(
        {
            "verb": "#00aaff bold",
            "unknown": "#ff5555",
            "optkey": "#ffcc00",
            "optval": "#33cc66",
            "conn": "#4488ff",
            "path": "#33cc66",
            "flag": "#ffcc00",
            "num": "#4488ff",
            "pipe": "#cc66cc bold",
            "prompt": "#00aaff bold",
            "tb-ok": "bg:#005500 #ffffff",
            "tb-warn": "bg:#665500 #ffffff",
            "tb-err": "bg:#660000 #ffffff",
        }
    )

    class _NivaCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            cur = _current_token(text)
            for cand in completions(text):
                yield Completion(cand, start_position=-len(cur))

    def _toolbar():
        sym, msg = _validity(get_app().current_buffer.text)
        if not sym:
            return ""
        cls = "tb-ok" if sym == "✓" else ("tb-warn" if sym == "⚠" else "tb-err")
        return [(f"class:{cls}", f" {sym} {msg} ")]

    return PromptSession(
        message=[("class:prompt", "niva ▸ ")],
        lexer=_FlowLexer(),
        style=style,
        completer=_NivaCompleter(),
        complete_while_typing=True,
        bottom_toolbar=_toolbar,
        history=FileHistory(_history_path()),  # up-arrow recalls across sessions too
    )
