"""`niva lsp` — the Language Server. Pure handlers are tested directly; the transport loop is
driven end-to-end by feeding framed messages through a BytesIO stdin and parsing stdout. QGIS-free
(completion/diagnostics/hover all come from the offline manifest + validator)."""

import io
import json
import unittest
from unittest import mock

from niva import lsp


def _frame(msg) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def _parse_all(data: bytes) -> list[dict]:
    """Parse a stream of framed LSP messages into a list of dicts."""
    out, i = [], 0
    while i < len(data):
        header_end = data.find(b"\r\n\r\n", i)
        if header_end == -1:
            break
        header = data[i:header_end].decode("utf-8")
        length = 0
        for line in header.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1])
        start = header_end + 4
        out.append(json.loads(data[start : start + length]))
        i = start + length
    return out


class TestLspHandlers(unittest.TestCase):
    def test_completion_items_have_precise_textedit(self):
        doc = "load a.gpkg | buffer 5m cap="
        items = lsp.completion_items(doc, {"line": 0, "character": len(doc)})
        labels = [i["label"] for i in items]
        self.assertIn("cap=flat", labels)
        rng = items[0]["textEdit"]["range"]
        self.assertEqual(rng["start"]["character"], len(doc) - len("cap="))
        self.assertEqual(rng["end"]["character"], len(doc))

    def test_completion_verb_at_stage_start(self):
        items = lsp.completion_items("lo", {"line": 0, "character": 2})
        self.assertIn("load", [i["label"] for i in items])

    def test_diagnostics_map_errors_and_warnings(self):
        p = lsp.diagnostics_params("file:///x.niva", "load a.gpkg | bufffer 5m")
        sevs = {d["severity"] for d in p["diagnostics"]}
        self.assertIn(1, sevs)  # an error (unknown verb)
        self.assertTrue(all(d["source"] == "niva" for d in p["diagnostics"]))
        self.assertEqual(p["uri"], "file:///x.niva")

    def test_hover_describes_a_verb(self):
        hv = lsp.hover("load a.gpkg | buffer 100m", {"line": 0, "character": 14})
        self.assertIsNotNone(hv)
        self.assertIn("buffer", hv["contents"]["value"].lower())

    def test_hover_none_on_non_verb(self):
        self.assertIsNone(lsp.hover("   zzzznotaverb", {"line": 0, "character": 2}))

    def test_word_at_and_kind(self):
        self.assertEqual(lsp._word_at("load a.gpkg | buffer", 15), "buffer")
        self.assertEqual(lsp._kind("out/"), lsp._KIND_FOLDER)
        self.assertEqual(lsp._kind("cap=flat"), lsp._KIND_ENUM_MEMBER)
        self.assertEqual(lsp._kind("segments="), lsp._KIND_FIELD)


class TestLspSession(unittest.TestCase):
    def _run(self, messages):
        stdin = io.BytesIO(b"".join(_frame(m) for m in messages))
        stdout = io.BytesIO()
        fake_in = mock.Mock(buffer=stdin)
        fake_out = mock.Mock(buffer=stdout)
        with (
            mock.patch.object(lsp.sys, "stdin", fake_in),
            mock.patch.object(lsp.sys, "stdout", fake_out),
        ):
            rc = lsp.run([])
        return rc, _parse_all(stdout.getvalue())

    def test_initialize_open_complete_shutdown(self):
        rc, replies = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": "file:///s.niva",
                            "text": "load a.gpkg | bufffer 5m",
                        }
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "textDocument/completion",
                    "params": {
                        "textDocument": {"uri": "file:///s.niva"},
                        "position": {"line": 0, "character": 2},
                    },
                },
                {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit"},
            ]
        )
        self.assertEqual(rc, 0)
        by_id = {m["id"]: m for m in replies if "id" in m}
        # initialize advertises completion + hover
        caps = by_id[1]["result"]["capabilities"]
        self.assertIn("completionProvider", caps)
        self.assertTrue(caps["hoverProvider"])
        # didOpen pushed diagnostics (a notification, no id)
        diags = [
            m for m in replies if m.get("method") == "textDocument/publishDiagnostics"
        ]
        self.assertTrue(diags)
        self.assertTrue(diags[0]["params"]["diagnostics"])  # the unknown-verb error
        # completion returned items including `load`
        labels = [i["label"] for i in by_id[2]["result"]["items"]]
        self.assertIn("load", labels)


if __name__ == "__main__":
    unittest.main()
