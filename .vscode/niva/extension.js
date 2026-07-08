// niva VS Code extension — starts the niva Language Server (`niva lsp`) and connects it as an
// LSP client, so `.niva` files get real completion, diagnostics, and hover. The grammar and
// snippets (declared in package.json) work independently; this only adds the language server.
//
// The server command is configurable (`niva.lsp.command` / `niva.lsp.args`) so you can point at a
// specific interpreter's niva — it MUST be the one installed into QGIS's Python for hover on
// live-only algorithm ids, though completion and diagnostics are fully offline.

const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const cfg = vscode.workspace.getConfiguration("niva");
  const command = cfg.get("lsp.command") || "niva";
  const args = cfg.get("lsp.args") || ["lsp"];

  const server = { command, args, transport: TransportKind.stdio };
  const serverOptions = { run: server, debug: server };

  const clientOptions = {
    documentSelector: [
      { scheme: "file", language: "niva" },
      { scheme: "untitled", language: "niva" },
    ],
  };

  client = new LanguageClient(
    "niva",
    "niva Language Server",
    serverOptions,
    clientOptions,
  );
  client.start(); // spawns `niva lsp`; failures surface in Output → "niva Language Server"
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
