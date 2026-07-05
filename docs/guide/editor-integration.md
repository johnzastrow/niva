# Editor / IDE integration

niva flows are plain `.niva` text files. This guide sets up **syntax highlighting** (and, in
VS Code, **snippets + tab-completion**) in whatever editor you use. The definitions live in
[`.vscode/niva/`](../../.vscode/niva) — despite the folder name they cover far more than VS Code.

## One command (Linux / macOS)

```bash
bash .vscode/niva/install.sh
```

Idempotent, per-user, no root. It detects VS Code/VSCodium, Vim/Neovim, nano, the GtkSourceView
family (Mousepad, gedit, …), and Kate, and installs into each. Restart your editor afterward.
Windows and a few editors are manual — see below.

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

**Language → User Defined Language → Define your language… → Import…** and choose
`.vscode\niva\npp\niva.udl.xml`. Restart Notepad++.

## GitHub

`.gitattributes` maps `*.niva` to the `Niva` language via Linguist, so niva files render with
highlighting in the GitHub web UI and diffs — nothing to install.

## Emacs / Helix — not yet

No mode ships yet. Emacs would want a `niva-mode` (derive from `prog-mode`, reuse the verb lists
here); Helix would want a Tree-sitter grammar. Contributions welcome — the verb/alias lists in any
of the files above are the source of truth.

---

## Keeping the definitions in sync

All formats encode the same three lists — **22 built-in verbs**, **45 alias verbs**, and the
token rules (options `key=`, `@conn`, `EPSG:`, distances, pipe, `{template}`). When verbs change,
update every file under `.vscode/niva/`. The lists mirror niva's registry
([`niva/registry/definitions.py`](../../niva/registry/definitions.py)) and the built-in dispatch
in [`niva/engine/engine.py`](../../niva/engine/engine.py).
