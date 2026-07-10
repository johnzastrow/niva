# Editor / IDE integration

niva flows are plain `.niva` text files. This guide sets up **syntax highlighting** in whatever
editor you use (the definitions live in [`.vscode/niva/`](../../.vscode/niva) — despite the folder
name they cover far more than VS Code) — and, via the **language server**, real completion,
diagnostics, and hover docs.

## Language server — `niva lsp` (real completion, diagnostics, hover)

The syntax files below only *colour* a `.niva` file. **`niva lsp`** gives your editor the same
intelligence the repl has, in any editor that speaks LSP:

- **completion** — verbs → their options/flags → enum values → **filesystem paths**;
- **diagnostics** — the offline validator's errors/warnings, live as you type (unknown verb,
  bad option/enum, a flow with no `save`), before you ever run;
- **hover** — `describe` docs for the verb under the cursor.

It's the *same* engine as the repl (`niva.intelligence`), so the two never disagree, and it stays
correct as verbs evolve because it's generated from niva's manifest. It runs over stdio with **no
extra dependencies** — you just need niva installed on the interpreter the command runs
(`niva lsp` starts the server; it needs QGIS only for hover on live-only algorithm ids, everything
else is offline).

**Neovim** (built-in LSP, `init.lua`):

```lua
vim.filetype.add({ extension = { niva = "niva" } })
vim.api.nvim_create_autocmd("FileType", {
  pattern = "niva",
  callback = function(args)
    vim.lsp.start({ name = "niva", cmd = { "niva", "lsp" }, root_dir = vim.fn.getcwd() })
  end,
})
```

**Helix** (`~/.config/helix/languages.toml`):

```toml
[[language]]
name = "niva"
scope = "source.niva"
file-types = ["niva"]
language-servers = ["niva-lsp"]

[language-server.niva-lsp]
command = "niva"
args = ["lsp"]
```

**VS Code / VSCodium**: the bundled extension already includes the language-server client — build
and install it (needs Node/npm):

```bash
bash .vscode/niva/install.sh    # packages a .vsix and installs it via the `code` CLI
```

then reload the window. (Manual install: `cd .vscode/niva && npm install && npx @vscode/vsce
package`, then Extensions ⇒ ⋯ ⇒ *Install from VSIX…*.) If the `niva` on VS Code's PATH isn't the
one you want, set **`niva.lsp.command`** in Settings to an absolute path (and **`niva.lsp.args`** to
match). See the extension's [README](../../.vscode/niva/README.md). **Kate / KWrite**: `bash .vscode/niva/install.sh` writes the
LSP server config for you (`~/.config/kate/lspclient/settings.json`); then enable it once via
*Settings → Configure Kate → Plugins → "LSP Client"* and reopen a `.niva` file. (Manual equivalent:
add `{"servers":{"niva":{"command":["niva","lsp"],"highlightingModeRegex":"^niva$"}}}` under
*Settings → LSP Client → User Server Settings*.)

> Make sure the `niva` command on your `PATH` is the one you installed (see the [Quick
> start](quickstart.md)); `niva lsp` uses that interpreter's niva.
>
> **Windows (Git Bash users):** the `niva()` function you added to `~/.bashrc` (see the [Quick
> start](quickstart.md#make-niva-a-terminal-command)) is a *shell* function — a GUI editor that
> spawns `niva lsp` never sees it. Give the editor a real command instead. Either **(a)**
> `pip install qgis-niva` into QGIS's Python so a `niva.exe` lands on `PATH`, or **(b)** point the
> LSP client straight at QGIS's Python. In VS Code, set:
>
> ```jsonc
> // settings.json — runs the server through QGIS's own Python
> "niva.lsp.command": "C:\\OSGeo4W\\bin\\python-qgis.bat",
> "niva.lsp.args": ["-m", "niva.cli.main", "lsp"]
> ```
>
> (Standalone installer? Use its `...\\bin\\python-qgis.bat`. Running from a git clone rather than a
> pip install? Add the repo to the environment — set `PYTHONPATH` to the repo root in the editor's
> integrated-terminal/env, or just `pip install qgis-niva` to avoid the issue.)

## One command (Linux / macOS / Windows Git Bash)

```bash
bash .vscode/niva/install.sh
```

Idempotent, per-user, no root. It detects VS Code/VSCodium, Vim/Neovim, nano, the GtkSourceView
family (Mousepad, gedit, …), and Kate, and installs into each. Restart your editor afterward.

**On Windows**, run it from **Git Bash / MSYS2** (the same bash you use in Windows Terminal) — the
script drives the `code` CLI, so it installs the VS Code extension **with** the language server as
long as `code` and `npm` are on your `PATH` (they are if you enabled *"Add to PATH"* when installing
VS Code / Node). The Linux-only branches (GtkSourceView, Kate) simply no-op.

**No bash on Windows?** Use the PowerShell port instead — same idea, native paths:

```powershell
powershell -ExecutionPolicy Bypass -File .vscode\niva\install.ps1
```

It installs the **VS Code** extension + language server (needs `code` and `npm` on `PATH`), sets up
**Vim** (`%USERPROFILE%\vimfiles`) and **Neovim** (`%LOCALAPPDATA%\nvim`) if present, and — a Windows
bonus the bash script can't do — drops the **Notepad++** User Defined Language straight into
`%APPDATA%\Notepad++\userDefineLangs\` so it auto-loads with no manual *Import…* step. The
`-ExecutionPolicy Bypass` runs it for that one call without changing your machine's policy.

It also **auto-points the VS Code language server at QGIS's Python**: since a bare `niva` isn't on
Windows `PATH`, the script finds your `python-qgis.bat` (OSGeo4W or a *Program Files* QGIS) and sets
`niva.lsp.command` / `niva.lsp.args` for you. If a VS Code `settings.json` already exists it isn't
rewritten — the script prints the two lines to paste, preserving your file. (This is why VS Code
"couldn't find niva/python": the extension spawns `niva lsp`, which needs to resolve to QGIS's
Python — see the [language-server note](#language-server--niva-lsp-real-completion-diagnostics-hover)
above.)

## Coverage at a glance

niva ships syntax in **five formats**, which between them cover essentially every editor:

| Editor | Format used | Highlighting | Snippets / completion |
|---|---|---|---|
| **VS Code / VSCodium** | TextMate + snippets | ✅ | ✅ (see [completion notes](../../.vscode/niva/README.md#what-completion-means-here)) |
| **Sublime Text** | TextMate (`.tmLanguage.json`) | ✅ | — |
| **Zed** | TextMate | ✅ | — |
| **JetBrains** (PyCharm/IDEA/…) | TextMate | ✅ | — |
| **bat** (pager) | TextMate | ✅ | — |
| **Vim / Neovim** | Vim syntax | ✅ | — |
| **nano** | `.nanorc` | ✅ | — |
| **Mousepad / gedit / GNOME Builder / Pluma / xed** | GtkSourceView `.lang` | ✅ | — |
| **Kate / KWrite / KDevelop** | KSyntaxHighlighting XML | ✅ | — |
| **Notepad++** (Windows) | UDL XML | ✅ | — |
| **GitHub** | Linguist (`.gitattributes`) | ✅ | — |
| **Emacs / Helix** | — (not yet) | — | — |

The principle: **most editors accept one of these five formats.** For any editor not listed,
find which format it understands (TextMate, GtkSourceView, KSyntaxHighlighting, Vim, or a
nano-style regex list) and point it at the matching file below.

---

## VS Code / VSCodium

The richest integration — highlighting **plus** snippets and command-dropdown completion.

```bash
cp -r .vscode/niva ~/.vscode/extensions/niva     # VSCodium: ~/.vscodium/extensions
```

Then reload the window (**Ctrl/Cmd+Shift+P → Developer: Reload Window**). Type a verb prefix
(`load`, `pipeline`, `pdalcli-dtm`, `chm`, …) and Tab to expand. See the
[extension README](../../.vscode/niva/README.md) for the snippet list and what "completion" covers.

**Paths by OS:** Linux/macOS `~/.vscode/extensions/` · Windows `%USERPROFILE%\.vscode\extensions\`.

## Any TextMate-compatible editor (Sublime, Zed, JetBrains, bat)

They all consume `syntaxes/niva.tmLanguage.json`:

- **Sublime Text** — copy it into `Packages/User/` (Preferences → Browse Packages).
- **JetBrains** — Settings → Editor → TextMate Bundles → **+** → add the `.vscode/niva/syntaxes/` folder.
- **Zed** — add the grammar via a language extension, or reference the TextMate file in settings.
- **bat** — `mkdir -p ~/.config/bat/syntaxes && cp syntaxes/niva.tmLanguage.json ~/.config/bat/syntaxes/ && bat cache --build`.

## Vim / Neovim

```bash
mkdir -p ~/.vim/syntax ~/.vim/ftdetect                 # Neovim: ~/.config/nvim/{syntax,ftdetect}
cp .vscode/niva/vim/niva.vim ~/.vim/syntax/niva.vim
echo 'au BufRead,BufNewFile *.niva set filetype=niva' > ~/.vim/ftdetect/niva.vim
```

The `ftdetect` file is what makes Vim recognise `*.niva`; without it you'd `:set ft=niva` by hand.

## nano

```bash
mkdir -p ~/.nano
cp .vscode/niva/nano/niva.nanorc ~/.nano/niva.nanorc
echo 'include "~/.nano/niva.nanorc"' >> ~/.nanorc
```

nano ≥ 2.9 required. System-wide alternative: copy to `/usr/share/nano/` (the stock `~/.nanorc`
usually already `include`s that folder).

## Mousepad / gedit / GNOME Builder / Pluma / xed (GtkSourceView)

```bash
mkdir -p ~/.local/share/gtksourceview-4/language-specs
cp .vscode/niva/gtksourceview/niva.lang ~/.local/share/gtksourceview-4/language-specs/niva.lang
```

Use `gtksourceview-3.0` for older apps (gedit 3, Pluma, xed) and `gtksourceview-5` for the newest.
Restart the editor; it picks up `*.niva` from the `.lang` file's `globs`.

## Kate / KWrite / KDevelop (KSyntaxHighlighting)

```bash
mkdir -p ~/.local/share/org.kde.syntax-highlighting/syntax
cp .vscode/niva/kate/niva.xml ~/.local/share/org.kde.syntax-highlighting/syntax/niva.xml
```

Restart Kate — it indexes that folder at startup. (Older KDE: `~/.local/share/katepart5/syntax/`.)

## Notepad++ (Windows)

Easiest — let the PowerShell installer place it: `powershell -ExecutionPolicy Bypass -File
.vscode\niva\install.ps1` copies the UDL into `%APPDATA%\Notepad++\userDefineLangs\`, which
Notepad++ auto-loads. Or do it by hand: **Language → User Defined Language → Define your language…
→ Import…** and choose `.vscode\niva\npp\niva.udl.xml`. Either way, restart Notepad++.

## GitHub

`.gitattributes` maps `*.niva` to the `Niva` language via Linguist, so niva files render with
highlighting in the GitHub web UI and diffs — nothing to install.

## Emacs / Helix — not yet

No mode ships yet. Emacs would want a `niva-mode` (derive from `prog-mode`, reuse the verb lists
here); Helix would want a Tree-sitter grammar. Contributions welcome — the verb/alias lists in any
of the files above are the source of truth.

---

## Keeping the definitions in sync

All formats encode the same three lists — **23 built-in verbs**, **45 alias verbs**, and the
token rules (options `key=`, `@conn`, `EPSG:`, distances, pipe, `{template}`). When verbs change,
update every file under `.vscode/niva/`. The lists mirror niva's registry
([`niva/registry/definitions.py`](../../niva/registry/definitions.py)) and the built-in dispatch
in [`niva/engine/engine.py`](../../niva/engine/engine.py).
