# niva — VSCode extension

Syntax highlighting, snippets, **and a language server** (real completion, diagnostics, hover)
for `.niva` geospatial pipeline files.

## Quick install

```bash
# Build the language-server client (fetches vscode-languageclient) + copy into VS Code:
bash .vscode/niva/install.sh
```

That runs `npm install` here and copies the extension (with `extension.js` + `node_modules`) into
your VS Code extensions dir. Reload VS Code (**Developer: Reload Window**) and open a `.niva` file.
No npm? The installer still gives you highlighting + snippets, just not the language server.

For development, open `.vscode/niva/` in VS Code and press **F5** (run `npm install` here first).

## Features

- **Language server** (`niva lsp`) — **context-aware completion** (verbs → their options/flags →
  enum values → **filesystem paths**), **live diagnostics** (the offline validator: unknown verb,
  bad option/enum, a flow with no `save`), and **hover** (`describe` docs). Same engine as the
  niva repl, generated from niva's manifest — so it stays correct as verbs evolve. It launches
  `niva lsp`; set **`niva.lsp.command`** if the `niva` on your PATH isn't the one you want (it
  should be the niva installed into QGIS's Python).
- **Syntax highlighting** — comments, strings, pipes, built-in & alias verbs, `key=value` options, `@conn` refs, `EPSG:NNNN`, distances, flags
- **Snippets** — type a prefix and Tab to expand with placeholders. Covers all built-ins, all aliases, common pipeline patterns (`buf`, `pipeline`, `each-reproject`, `sql-pipe`, …), and the **PDAL/SAGA LiDAR harness** (`pdalcli`, `pdalcli-dtm`, `chm`, `saga`, …)
- **Comment toggle** — `Ctrl+/` / `Cmd+/`; **auto-closing quotes**

> The completion/diagnostics/hover come from the language server; the snippets and highlighting
> work even if the server isn't running (e.g. no Node, or `niva` not on PATH). If IntelliSense
> isn't appearing, check **Output → "niva Language Server"** for how the `niva lsp` process started.

## Support for other editors

**One command (Linux/macOS)** installs into every editor found on your machine:

```bash
bash install.sh
```

Or set them up by hand — niva ships syntax in five formats:

| Editor | How to enable highlighting | File |
|--------|--------------------------|------|
| **Vim/Neovim** | Copy `vim/niva.vim` → `~/.vim/syntax/` + an `ftdetect` line | source |
| **nano** | Copy `nano/niva.nanorc` → `~/.nano/`, `include` it in `~/.nanorc` | nanorc |
| **Mousepad / gedit / GNOME Builder / Pluma / xed** | Copy `gtksourceview/niva.lang` → `~/.local/share/gtksourceview-4/language-specs/` | GtkSourceView |
| **Kate / KWrite / KDevelop** | Copy `kate/niva.xml` → `~/.local/share/org.kde.syntax-highlighting/syntax/` | KSyntaxHighlighting |
| **Notepad++** (Windows) | Language → User Defined Language → Import → `npp/niva.udl.xml` | UDL XML |
| **Sublime Text** | Copy `syntaxes/niva.tmLanguage.json` to Packages/User | TextMate |
| **JetBrains** (PyCharm/IDEA) | Settings → Editor → TextMate Bundles → add `syntaxes/` | TextMate |
| **Zed** | `extensions/` — or use TextMate grammar in settings | TextMate |
| **bat** (Rust pager) | Add `syntaxes/` to `~/.config/bat/syntaxes/` then `bat cache --build` | TextMate |
| **GitHub** | `.gitattributes` maps `*.niva` → Niva via Linguist | attribs |
| **Emacs / Helix** | Not yet — Emacs needs a major mode, Helix a Tree-sitter grammar | — |

Full per-editor instructions, cross-platform paths, and how to cover any other editor are in
**[docs/guide/editor-integration.md](../../docs/guide/editor-integration.md)**. Want another
editor supported? Open an issue or contribute — the verb lists in these files are the source of truth.
