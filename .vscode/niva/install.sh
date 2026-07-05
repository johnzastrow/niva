#!/usr/bin/env bash
# Install niva syntax highlighting for every editor found on this machine.
# Idempotent: safe to re-run. Per-user only (no root). Linux/macOS.
#   bash .vscode/niva/install.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
did=0
note() { printf '  ✓ %s\n' "$1"; did=1; }

# --- VS Code / VSCodium (TextMate grammar + snippets + completion) ---
for ext in "$HOME/.vscode/extensions" "$HOME/.vscode-server/extensions" \
           "$HOME/.vscode-oss/extensions" "$HOME/.vscodium/extensions"; do
  if [ -d "$(dirname "$ext")" ]; then
    mkdir -p "$ext/niva"
    cp -r "$HERE"/{package.json,language-configuration.json,syntaxes,snippets,README.md} "$ext/niva/" 2>/dev/null || true
    note "VS Code family → $ext/niva"
  fi
done

# --- Vim / Neovim (syntax + filetype detection) ---
for d in "$HOME/.vim" "$HOME/.config/nvim"; do
  if command -v vim >/dev/null 2>&1 || command -v nvim >/dev/null 2>&1; then
    mkdir -p "$d/syntax" "$d/ftdetect"
    cp "$HERE/vim/niva.vim" "$d/syntax/niva.vim"
    printf 'au BufRead,BufNewFile *.niva set filetype=niva\n' > "$d/ftdetect/niva.vim"
    note "Vim/Neovim → $d/{syntax,ftdetect}/niva.vim"
  fi
done

# --- nano ---
if command -v nano >/dev/null 2>&1; then
  mkdir -p "$HOME/.nano"
  cp "$HERE/nano/niva.nanorc" "$HOME/.nano/niva.nanorc"
  touch "$HOME/.nanorc"
  grep -q 'niva.nanorc' "$HOME/.nanorc" || echo 'include "~/.nano/niva.nanorc"' >> "$HOME/.nanorc"
  note "nano → ~/.nano/niva.nanorc (+ include in ~/.nanorc)"
fi

# --- GtkSourceView family (Mousepad, gedit, GNOME Builder, Pluma, xed) ---
for v in gtksourceview-4 gtksourceview-3.0 gtksourceview-5; do
  dst="$HOME/.local/share/$v/language-specs"
  mkdir -p "$dst"
  cp "$HERE/gtksourceview/niva.lang" "$dst/niva.lang"
done
note "GtkSourceView (Mousepad/gedit/…) → ~/.local/share/gtksourceview-*/language-specs/niva.lang"

# --- Kate / KWrite / KDevelop ---
dst="$HOME/.local/share/org.kde.syntax-highlighting/syntax"
mkdir -p "$dst"
cp "$HERE/kate/niva.xml" "$dst/niva.xml"
note "Kate family → ~/.local/share/org.kde.syntax-highlighting/syntax/niva.xml"

[ "$did" = 1 ] && echo "Done — restart your editor(s)." || echo "No supported editors detected."
echo "Windows / Notepad++ / other editors: see docs/guide/editor-integration.md"
