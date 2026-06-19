#!/usr/bin/env python3
"""Build one coherent PDF of the niva user guide (``docs/guide/``) with pandoc.

Concatenates the guide documents in reading order into a single PDF — a title page, a
table of contents, and one chapter per document. Requires ``pandoc`` and a PDF engine
(``xelatex`` preferred, then ``lualatex``/``pdflatex``/``wkhtmltopdf``).

Regenerate:

    python3 scripts/build_guide_pdf.py              # -> docs/guide/niva-guide.pdf
    python3 scripts/build_guide_pdf.py -o /tmp/g.pdf
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

# Emoji the source docs use (great on GitHub) that the PDF font (DejaVu) lacks → a
# monochrome equivalent it does have. Applied to temp copies; the source is untouched.
EMOJI_FALLBACKS = {
    "⭐": "★",   # ⭐ star  -> ★
    "✅": "✓",   # ✅ check -> ✓
    "\U0001f501": "↻",  # 🔁 repeat -> ↻
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "docs", "guide")
# Reading order; any other docs/guide/*.md is appended after these.
ORDER = ["about.md", "user-guide.md", "reference.md", "cookbook.md", "templates.md"]
DEFAULT_OUT = os.path.join(GUIDE, "niva-guide.pdf")
ENGINES = ("xelatex", "lualatex", "pdflatex", "wkhtmltopdf")


def _version() -> str:
    init = os.path.join(ROOT, "niva", "__init__.py")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', open(init, encoding="utf-8").read())
    return m.group(1) if m else "?"


def _has_font(name: str) -> bool:
    if not shutil.which("fc-list"):
        return False
    try:
        return name in subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    except Exception:  # noqa: BLE001
        return False


def _guide_files() -> list[str]:
    present = [f for f in ORDER if os.path.isfile(os.path.join(GUIDE, f))]
    extra = sorted(
        f for f in os.listdir(GUIDE)
        if f.endswith(".md") and f not in ORDER
    )
    return [os.path.join(GUIDE, f) for f in present + extra]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a unified PDF of docs/guide/.")
    ap.add_argument("-o", "--output", default=DEFAULT_OUT, help="output PDF path")
    args = ap.parse_args()

    if not shutil.which("pandoc"):
        sys.exit("error: pandoc not found — install pandoc (https://pandoc.org).")
    engine = next((e for e in ENGINES if shutil.which(e)), None)
    if not engine:
        sys.exit("error: no PDF engine found — install a LaTeX engine "
                 "(e.g. texlive-xetex) or wkhtmltopdf.")

    files = _guide_files()
    if not files:
        sys.exit(f"error: no .md files under {GUIDE}")

    out = os.path.abspath(os.path.expanduser(args.output))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # Substitute PDF-unfriendly emoji into temp copies (source markdown stays as-is).
    tmpdir = tempfile.mkdtemp(prefix="niva_guide_pdf_")
    inputs = []
    for f in files:
        text = open(f, encoding="utf-8").read()
        for emoji, repl in EMOJI_FALLBACKS.items():
            text = text.replace(emoji, repl)
        tmp = os.path.join(tmpdir, os.path.basename(f))
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        inputs.append(tmp)

    cmd = [
        "pandoc", *inputs,
        "--from", "gfm",
        "--output", out,
        f"--pdf-engine={engine}",
        "--toc", "--toc-depth=2",
        "--top-level-division=chapter",
        "--metadata", "title=niva",
        "--metadata", f"subtitle=User Guide · Reference · Cookbook (v{_version()})",
        "--metadata", f"date={date.today().isoformat()}",
        "--metadata", "author=",
        "-V", "documentclass=report",
        "-V", "geometry:margin=2.2cm",
        "-V", "fontsize=10pt",
        "-V", "colorlinks=true",
        "-V", "linkcolor=blue",
        "-V", "urlcolor=blue",
        "-V", "toccolor=black",
    ]
    # A Unicode-rich font (so →, ✓, ✗, ▶, ⭐ render) when using a unicode TeX engine.
    if engine in ("xelatex", "lualatex") and _has_font("DejaVu Sans"):
        cmd += ["-V", "mainfont=DejaVu Sans",
                "-V", "sansfont=DejaVu Sans",
                "-V", "monofont=DejaVu Sans Mono"]

    print(f"building {out}\n  engine: {engine}\n  inputs: "
          + ", ".join(os.path.basename(f) for f in files))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: pandoc failed (exit {exc.returncode}).")
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
