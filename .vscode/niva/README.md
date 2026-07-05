# niva — VSCode extension

Syntax highlighting + tab-completion snippets for `.niva` geospatial pipeline files.

## Quick install

```bash
# Copy to VSCode extensions and restart
cp -r .vscode/niva ~/.vscode/extensions/niva
```

Or open `.vscode/niva/` in VSCode and press **F5**.

## Features

- **Syntax highlighting** — comments, strings, pipes, built-in & alias verbs, `key=value` options, `@conn` refs, `EPSG:NNNN`, distances, flags
- **Tab-completion snippets** — type a prefix and Tab to expand with placeholders for each parameter. Covers all 22 built-ins, all 45 aliases, common pipeline patterns (`buf`, `pipeline`, `each-reproject`, `sql-pipe`, …), and the **PDAL/SAGA LiDAR harness** (`pdalcli`, `pdalcli-dtm`, `pdalcli-dsm`, `pdalcli-class`, `chm`, `saga`)
- **Comment toggle** — `Ctrl+/` / `Cmd+/`
- **Auto-closing quotes**

### What "completion" means here

Completion is **snippet- and word-based**, not full IntelliSense:

- ✅ **Snippet expansion** — a prefix (a verb name or a pattern like `pdalcli-dtm`) expands to a templated line you tab through. The `pdalcli` snippet even offers a **dropdown of the 12 wrench commands**.
- ✅ **Word suggestions** — VS Code suggests identifiers already present in the file.
- ❌ **Context-aware IntelliSense** — the extension is declarative (grammar + snippets, no language server), so it does **not** yet complete the 878 algorithm ids after `run`, an algorithm's parameter names/enum values, or `@connection`/layer/file names. That would need a `CompletionItemProvider` driven by the [algorithm catalog](../../docs/algorithms/README.md) + the verb registry — a possible future enhancement.

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
