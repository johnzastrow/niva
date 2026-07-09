"""`niva lsp` — a Language Server for `.niva` files (docs/planning/20 §11).

Speaks LSP over stdio (stdlib JSON-RPC, zero dependencies) so **any** editor — VS Code, Neovim,
Kate, … — gets niva's real intelligence on a `.niva` file:

* **completion** — verbs → options/flags → enum values → filesystem paths;
* **diagnostics** — the offline validator's errors/warnings, live as you type;
* **hover** — `describe` docs for the verb under the cursor.

All of it comes from :mod:`niva.intelligence` (and :func:`niva.describe.describe`) — the *same*
engine the repl uses — so an editor and the repl never disagree. The handlers below are pure and
unit-tested; :func:`run` is the thin stdio transport around them.
"""

from __future__ import annotations

import json
import sys

# LSP CompletionItemKind (subset). https://microsoft.github.io/language-server-protocol/
_KIND_FUNCTION = 3
_KIND_FIELD = 5
_KIND_FILE = 17
_KIND_FOLDER = 19
_KIND_ENUM_MEMBER = 20
_KIND_KEYWORD = 14

_CAPABILITIES = {
    "textDocumentSync": 1,  # full-document sync (client resends the whole text on change)
    "completionProvider": {"triggerCharacters": [" ", "|", "=", "/"]},
    "hoverProvider": True,
}


def _kind(candidate: str) -> int:
    """Map a completion string to an LSP CompletionItemKind icon."""
    if candidate.endswith("/"):
        return _KIND_FOLDER
    if "=" in candidate:
        return _KIND_ENUM_MEMBER if not candidate.endswith("=") else _KIND_FIELD
    if "/" in candidate or "." in candidate:
        return _KIND_FILE
    return _KIND_FUNCTION


def _line_at(text: str, line_no: int) -> str:
    lines = text.split("\n")
    return lines[line_no] if 0 <= line_no < len(lines) else ""


def completion_items(text: str, position: dict) -> list[dict]:
    """LSP completion items for the cursor ``position`` in document ``text``. Each item carries a
    precise ``textEdit`` replacing the current token, so path tokens (with ``/``) complete cleanly
    regardless of the client's word rules."""
    from .intelligence import completions, current_token

    line_no, char = position.get("line", 0), position.get("character", 0)
    prefix = _line_at(text, line_no)[:char]
    tok = current_token(prefix)
    start = char - len(tok)
    items = []
    for c in completions(prefix):
        items.append(
            {
                "label": c,
                "kind": _kind(c),
                "textEdit": {
                    "range": {
                        "start": {"line": line_no, "character": start},
                        "end": {"line": line_no, "character": char},
                    },
                    "newText": c,
                },
            }
        )
    return items


def _word_at(line: str, char: int) -> str:
    """The whitespace/pipe-delimited word under ``char`` in ``line`` (for hover)."""
    if char > len(line):
        char = len(line)
    seps = " \t|"
    start = char
    while start > 0 and line[start - 1] not in seps:
        start -= 1
    end = char
    while end < len(line) and line[end] not in seps:
        end += 1
    return line[start:end].strip()


def hover(text: str, position: dict) -> dict | None:
    """Hover info for the verb under the cursor — the `describe` docs as a Markdown code block,
    or None when the word isn't a describable verb/algorithm."""
    import re

    word = _word_at(
        _line_at(text, position.get("line", 0)), position.get("character", 0)
    )
    if not word:
        return None
    from .describe import describe

    try:
        doc = describe(word)
    except Exception:  # noqa: BLE001 — not a known verb/id, or QGIS-only id offline
        return None
    if not doc or not doc.strip():
        return None
    doc = re.sub(r"\x1b\[[0-9;]*m", "", doc)  # strip any ANSI colour
    return {"contents": {"kind": "markdown", "value": f"```niva\n{doc.strip()}\n```"}}


def diagnostics_params(uri: str, text: str) -> dict:
    """`textDocument/publishDiagnostics` params for ``text`` — the validator's findings mapped to
    LSP ranges (whole-line, since niva diagnostics are line-scoped)."""
    from .intelligence import diagnostics

    lines = text.split("\n")
    diags = []
    for d in diagnostics(text):
        ln = max(0, d["line"] - 1)  # 1-based → 0-based
        end = len(lines[ln]) if ln < len(lines) else 0
        diags.append(
            {
                "range": {
                    "start": {"line": ln, "character": 0},
                    "end": {"line": ln, "character": end},
                },
                "severity": 1 if d["severity"] == "error" else 2,  # Error / Warning
                "source": "niva",
                "message": d["message"],
            }
        )
    return {"uri": uri, "diagnostics": diags}


# ---------------------------------------------------------------- stdio JSON-RPC transport


def _read_message(stream) -> dict | None:
    """Read one framed LSP message (``Content-Length`` header + JSON body). None at EOF."""
    headers: dict = {}
    while True:
        raw = stream.readline()
        if not raw:
            return None  # EOF
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line in ("\r\n", "\n"):
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", 0))
    body = stream.read(length)
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _send(stream, msg: dict) -> None:
    data = json.dumps(msg).encode("utf-8")
    stream.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
    stream.write(data)
    stream.flush()


def run(argv=None) -> int:
    """The LSP event loop over stdio. Runs until the client sends ``exit`` (or stdin closes)."""
    from . import __version__

    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    docs: dict[str, str] = {}

    def reply(mid, result):
        _send(stdout, {"jsonrpc": "2.0", "id": mid, "result": result})

    def publish(uri):
        _send(
            stdout,
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": diagnostics_params(uri, docs.get(uri, "")),
            },
        )

    while True:
        msg = _read_message(stdin)
        if msg is None:
            break
        method = msg.get("method")
        if method == "exit":
            break
        mid = msg.get("id")
        params = msg.get("params") or {}
        # Field accesses are defensive (real editors send message shapes we don't fully model),
        # and the whole dispatch is wrapped so ONE malformed message can never kill the server —
        # an unhandled exception here used to take the whole LSP down until an editor restart.
        try:
            uri = (params.get("textDocument") or {}).get("uri", "")
            if method == "initialize":
                reply(
                    mid,
                    {
                        "capabilities": _CAPABILITIES,
                        "serverInfo": {"name": "niva-lsp", "version": __version__},
                    },
                )
            elif method == "shutdown":
                reply(mid, None)
            elif method == "textDocument/didOpen":
                docs[uri] = (params.get("textDocument") or {}).get("text", "")
                publish(uri)
            elif method == "textDocument/didChange":
                changes = params.get("contentChanges") or []
                if changes:  # full sync → the last change holds the whole document
                    docs[uri] = changes[-1].get("text", "")
                publish(uri)
            elif method == "textDocument/didClose":
                docs.pop(uri, None)
            elif method == "textDocument/completion":
                items = completion_items(
                    docs.get(uri, ""), params.get("position") or {}
                )
                reply(mid, {"isIncomplete": False, "items": items})
            elif method == "textDocument/hover":
                reply(mid, hover(docs.get(uri, ""), params.get("position") or {}))
            elif mid is not None:
                reply(
                    mid, None
                )  # unknown request → empty result (keeps the client happy)
            # unknown notifications are ignored
        except Exception as exc:  # noqa: BLE001 — resilience: never let one message end the loop
            sys.stderr.write(f"niva-lsp: error handling {method!r}: {exc!r}\n")
            sys.stderr.flush()
            if mid is not None:  # don't leave a request hanging
                try:
                    reply(mid, None)
                except Exception:  # noqa: BLE001
                    pass

    return 0
