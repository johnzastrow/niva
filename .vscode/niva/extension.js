// niva VS Code extension — starts the niva Language Server (`niva lsp`) and connects it as an
// LSP client, so `.niva` files get real completion, diagnostics, and hover. The grammar and
// snippets (declared in package.json) work independently; this only adds the language server.
//
// The server command is configurable (`niva.lsp.command` / `niva.lsp.args`) so you can point at a
// specific interpreter's niva — it MUST be the one installed into QGIS's Python for hover on
// live-only algorithm ids, though completion and diagnostics are fully offline. On Windows that
// command is usually QGIS's `python-qgis.bat` with args `["-m","niva.cli.main","lsp"]`; the
// installer writes those settings for you when it can find QGIS.

const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const cfg = vscode.workspace.getConfiguration("niva");
  let command = cfg.get("lsp.command") || "niva";
  const args = cfg.get("lsp.args") || ["lsp"];

  // On Windows the QGIS launcher is a batch file (e.g. python-qgis.bat). Modern Node/Electron
  // refuse to spawn .bat/.cmd without a shell (EINVAL, since the 2024 CVE-2024-27980 fix), so run
  // those through the shell. Under shell:true a path containing spaces (…\QGIS 3.40\bin\…) has to
  // be quoted, since the shell — not Node — parses the command line.
  const isWin = process.platform === "win32";
  const needsShell = isWin && /\.(bat|cmd)"?$/i.test(command.trim());
  if (needsShell && /\s/.test(command) && !command.trim().startsWith('"')) {
    command = `"${command}"`;
  }
  const options = needsShell ? { shell: true } : undefined;

  const server = { command, args, transport: TransportKind.stdio, options };
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

  // start() rejects if the process can't be launched (command not found, .bat without a shell, …).
  // Surface that as an actionable notification instead of a silent failure buried in the Output tab.
  Promise.resolve(client.start()).catch((err) => reportStartupFailure(command, err));

  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function reportStartupFailure(command, err) {
  const detail = err && err.message ? ` (${err.message})` : "";
  const msg =
    `niva language server couldn't start${detail}. It tried to run: ${command}. ` +
    `Point it at QGIS's Python: set "niva.lsp.command" to your python-qgis.bat and ` +
    `"niva.lsp.args" to ["-m","niva.cli.main","lsp"]. Syntax highlighting still works.`;
  vscode.window.showErrorMessage(msg, "Open niva settings", "Docs").then((choice) => {
    if (choice === "Open niva settings") {
      vscode.commands.executeCommand("workbench.action.openSettings", "niva.lsp");
    } else if (choice === "Docs") {
      vscode.env.openExternal(
        vscode.Uri.parse("https://github.com/johnzastrow/niva/blob/main/docs/guide/editor-integration.md"),
      );
    }
  });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
