#!/usr/bin/env python3
"""Build one coherent PDF of the niva user guide (``docs/guide/``) with pandoc.

Concatenates the guide documents in reading order, then the per-provider algorithm
reference (``docs/algorithms/``) as lettered **appendices**, into a single PDF — a title
page, a table of contents, and one chapter per document. Long code lines wrap and wide
tables are shrunk so nothing is cut off. Requires ``pandoc`` and a PDF engine (``xelatex``
preferred, then ``lualatex``/``pdflatex``/``wkhtmltopdf``).

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "docs", "guide")
APPENDIX = os.path.join(ROOT, "docs", "algorithms")
# Reading order; any other docs/guide/*.md is appended after these.
GUIDE_ORDER = ["about.md", "user-guide.md", "reference.md", "cookbook.md", "templates.md"]
# Appendix order (the index first, then providers; grass is huge, so last).
APPENDIX_ORDER = ["README.md", "native.md", "gdal.md", "qgis.md", "pdal.md", "3d.md", "grass.md"]
DEFAULT_OUT = os.path.join(GUIDE, "niva-guide.pdf")
ENGINES = ("xelatex", "lualatex", "pdflatex", "wkhtmltopdf")

# Emoji the source docs use (great on GitHub) that the PDF font (DejaVu) lacks → a
# monochrome equivalent it does have. Applied to temp copies; the source is untouched.
EMOJI_FALLBACKS = {
    "⭐": "★",
    "✅": "✓",
    "\U0001f501": "↻",
}

# LaTeX preamble that fixes the cut-off content: wrap long code lines, let inline code
# and URLs break, and render tables smaller/tighter so wide ones fit the page width.
HEADER_TEX = r"""
\usepackage{fvextra}
% Wrap long lines in code blocks (the main cause of cut-off text). Done at begin-document
% so it overrides pandoc's own Highlighting definition regardless of preamble order.
\AtBeginDocument{%
  \DefineVerbatimEnvironment{Highlighting}{Verbatim}%
    {breaklines,breakanywhere,fontsize=\small,commandchars=\\\{\}}%
  \DefineVerbatimEnvironment{verbatim}{Verbatim}{breaklines,breakanywhere,fontsize=\small}%
}
\fvset{breaklines=true,breakanywhere=true}
% Let inline code (\texttt) and URLs break, and let TeX stretch a line rather than overflow
% (kills the minor overhangs from long unbreakable code tokens in prose).
\usepackage[htt]{hyphenat}
\usepackage{xurl}
\setlength{\emergencystretch}{3em}
% Table packages (the table filter emits raw longtables, so load these ourselves) + a
% smaller, tighter style so wide tables fit.
\usepackage{longtable}
\usepackage{array}
\usepackage{booktabs}
\usepackage{etoolbox}
\AtBeginEnvironment{longtable}{\footnotesize}
\setlength{\tabcolsep}{3pt}
\renewcommand{\arraystretch}{1.15}
% Rotate genuinely-wide tables onto landscape pages (the table filter wraps them too).
\usepackage{pdflscape}
"""

# A raw-LaTeX block (needs the raw_attribute extension) that starts the appendices, so the
# algorithm chapters become "Appendix A", "Appendix B", … .
APPENDIX_DIVIDER = "```{=latex}\n\\appendix\n```\n"

# pandoc keeps GFM pipe tables as non-wrapping `l` columns, so wide tables run off the page.
# This filter, per table:
#   * leaves a comfortably-narrow table as-is;
#   * otherwise gives each column a relative width (∝ its longest cell, capped so one long
#     cell can't starve the others) → the LaTeX writer emits wrapping `p{…}` columns;
#   * and rotates a genuinely-wide, multi-column table onto its own **landscape** page.
LUA_TABLES = r"""
-- Rewrite every table to a raw-LaTeX longtable with WRAPPING p{} columns and a
-- horizontal rule (\hline) after every row, so cells never overflow and rows are easy to
-- read across. Genuinely-wide GUIDE tables (not the hundreds of narrow appendix ones) are
-- rotated onto landscape pages.
local in_appendix = false
function RawBlock(el)
  if el.format == "latex" and el.text:find("appendix") then in_appendix = true end
end

-- Let a LONG inline-code token (e.g. gdal:cliprasterbymasklayer) break at any character, so
-- it doesn't overhang the margin in prose. Only long, ASCII tokens are touched (fast).
local CODE_ESC = {
  ["\\"] = "\\textbackslash{}", ["{"] = "\\{", ["}"] = "\\}", ["$"] = "\\$",
  ["&"] = "\\&", ["#"] = "\\#", ["%"] = "\\%", ["_"] = "\\_",
  ["^"] = "\\textasciicircum{}", ["~"] = "\\textasciitilde{}",
}
function Code(el)
  if #el.text < 18 or el.text:find("[\128-\255]") then return nil end
  local parts = {}
  for i = 1, #el.text do
    local c = el.text:sub(i, i)
    parts[#parts + 1] = (CODE_ESC[c] or c) .. "\\discretionary{}{}{}"
  end
  return pandoc.RawInline("latex", "\\texttt{" .. table.concat(parts) .. "}")
end

local function cell_latex(cell)
  local s = pandoc.write(pandoc.Pandoc(cell.contents), "latex")
  return (s:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", ""))
end

local function render_rows(rows, bold)
  local out = {}
  for _, row in ipairs(rows) do
    local cells = {}
    for i, cell in ipairs(row.cells) do
      local c = cell_latex(cell)
      cells[i] = bold and ("\\textbf{" .. c .. "}") or c
    end
    out[#out + 1] = table.concat(cells, " & ") .. " \\\\ \\hline"
  end
  return table.concat(out, "\n")
end

function Table(tbl)
  local ncol = #tbl.colspecs
  if ncol == 0 then return nil end
  -- measure columns by their longest cell
  local maxlen = {}
  for i = 1, ncol do maxlen[i] = 3 end
  local function scan(rows)
    for _, row in ipairs(rows) do
      for i, cell in ipairs(row.cells) do
        local l = #pandoc.utils.stringify(cell.contents)
        if l > maxlen[i] then maxlen[i] = l end
      end
    end
  end
  scan(tbl.head.rows)
  for _, b in ipairs(tbl.bodies) do scan(b.body) end
  local natural = 0
  for i = 1, ncol do natural = natural + maxlen[i] end
  -- proportional, capped widths summing to 0.93\linewidth (room for rules + colsep)
  local capped, total = {}, 0
  for i = 1, ncol do capped[i] = math.min(maxlen[i], 45); total = total + capped[i] end
  local cols = {}
  for i = 1, ncol do
    cols[i] = string.format("p{%.3f\\linewidth}", 0.93 * capped[i] / total)
  end
  local colspec = "|" .. table.concat(cols, "|") .. "|"

  local body = {}
  for _, b in ipairs(tbl.bodies) do body[#body + 1] = render_rows(b.body, false) end
  local latex = "\\begin{longtable}{" .. colspec .. "}\n\\hline\n"
      .. render_rows(tbl.head.rows, true) .. "\n\\endhead\n"
      .. table.concat(body, "\n") .. "\n\\end{longtable}"

  if (not in_appendix) and ncol >= 4 and natural > 90 then
    latex = "\\begin{landscape}\n" .. latex .. "\n\\end{landscape}"
  end
  return pandoc.RawBlock("latex", latex)
end
"""


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


def _ordered(directory: str, order: list[str]) -> list[str]:
    present = [f for f in order if os.path.isfile(os.path.join(directory, f))]
    extra = sorted(f for f in os.listdir(directory) if f.endswith(".md") and f not in order)
    return [os.path.join(directory, f) for f in present + extra]


def _stage(path: str, tmpdir: str, tag: str, i: int) -> str:
    """Copy a source .md into tmpdir with emoji substituted; return the temp path."""
    text = open(path, encoding="utf-8").read()
    for emoji, repl in EMOJI_FALLBACKS.items():
        text = text.replace(emoji, repl)
    tmp = os.path.join(tmpdir, f"{tag}{i:02d}_{os.path.basename(path)}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    return tmp


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a unified PDF of docs/guide/ + algorithm appendices.")
    ap.add_argument("-o", "--output", default=DEFAULT_OUT, help="output PDF path")
    ap.add_argument("--no-appendix", action="store_true", help="skip the docs/algorithms/ appendices")
    args = ap.parse_args()

    if not shutil.which("pandoc"):
        sys.exit("error: pandoc not found — install pandoc (https://pandoc.org).")
    engine = next((e for e in ENGINES if shutil.which(e)), None)
    if not engine:
        sys.exit("error: no PDF engine found — install a LaTeX engine "
                 "(e.g. texlive-xetex) or wkhtmltopdf.")

    guide = _ordered(GUIDE, GUIDE_ORDER)
    if not guide:
        sys.exit(f"error: no .md files under {GUIDE}")
    appendix = [] if args.no_appendix else _ordered(APPENDIX, APPENDIX_ORDER)

    out = os.path.abspath(os.path.expanduser(args.output))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="niva_guide_pdf_")

    # header include + table filter
    header = os.path.join(tmpdir, "header.tex")
    with open(header, "w", encoding="utf-8") as fh:
        fh.write(HEADER_TEX)
    lua = os.path.join(tmpdir, "tables.lua")
    with open(lua, "w", encoding="utf-8") as fh:
        fh.write(LUA_TABLES)

    # staged inputs: guide chapters, then \appendix, then algorithm appendices
    inputs = [_stage(f, tmpdir, "g", i) for i, f in enumerate(guide)]
    if appendix:
        divider = os.path.join(tmpdir, "z00_appendix.md")
        with open(divider, "w", encoding="utf-8") as fh:
            fh.write(APPENDIX_DIVIDER)
        inputs.append(divider)
        inputs += [_stage(f, tmpdir, "a", i) for i, f in enumerate(appendix)]

    cmd = [
        "pandoc", *inputs,
        "--from", "gfm+raw_attribute",
        "--output", out,
        f"--pdf-engine={engine}",
        "--include-in-header", header,
        "--lua-filter", lua,
        "--toc", "--toc-depth=2",
        "--top-level-division=chapter",
        "--metadata", "title=niva",
        "--metadata", f"subtitle=User Guide · Reference · Cookbook · Algorithm Appendix (v{_version()})",
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
    if engine in ("xelatex", "lualatex") and _has_font("DejaVu Sans"):
        cmd += ["-V", "mainfont=DejaVu Sans",
                "-V", "sansfont=DejaVu Sans",
                "-V", "monofont=DejaVu Sans Mono"]

    print(f"building {out}\n  engine: {engine}\n  guide: "
          + ", ".join(os.path.basename(f) for f in guide)
          + ("\n  appendix: " + ", ".join(os.path.basename(f) for f in appendix) if appendix else ""))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: pandoc failed (exit {exc.returncode}).")
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
