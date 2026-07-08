#!/usr/bin/env bash
# Install niva syntax highlighting for every editor found on this machine.
# Idempotent: safe to re-run. Per-user only (no root). Linux/macOS.
#   bash .vscode/niva/install.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
did=0
note() { printf '  ✓ %s\n' "$1"; did=1; }

# --- VS Code / VSCodium (TextMate grammar + snippets + LANGUAGE SERVER) ---
# The language server (completion/diagnostics/hover) needs the vscode-languageclient npm package.
# If npm is present we fetch it and ship the full extension; otherwise we install the declarative
# parts only (highlighting + snippets) and note that the LSP needs Node.
vsfiles=(package.json language-configuration.json syntaxes snippets README.md)
if command -v npm >/dev/null 2>&1; then
  ( cd "$HERE" && npm install --omit=dev --no-audit --no-fund >/dev/null 2>&1 ) \
    && vsfiles+=(extension.js node_modules) \
    || echo "  ! npm install failed — VS Code will get highlighting only (no language server)."
else
  echo "  ! npm not found — VS Code gets highlighting only. Install Node.js and re-run for the language server."
fi
for ext in "$HOME/.vscode/extensions" "$HOME/.vscode-server/extensions" \
           "$HOME/.vscode-oss/extensions" "$HOME/.vscodium/extensions"; do
  if [ -d "$(dirname "$ext")" ]; then
    rm -rf "$ext/niva"  # clean stale files (e.g. an old node_modules) so the copy is exact
    mkdir -p "$ext/niva"
    for f in "${vsfiles[@]}"; do cp -r "$HERE/$f" "$ext/niva/" 2>/dev/null || true; done
    note "VS Code family → $ext/niva$( [ -e "$ext/niva/extension.js" ] && echo ' (with language server)' )"
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
