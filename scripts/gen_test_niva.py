#!/usr/bin/env python3
"""Generate human-readable `.niva` companions for the test suite.

For every ``tests/test_*.py`` this writes ``tests/niva/<module>.niva`` showing, per test,
the niva flow(s) it exercises — so a human can read *what* the suite covers without reading
Python. Tests that are pure Python (no niva flow — e.g. search ranking, binder internals)
get a short comment stanza describing what they check, so nothing is silently omitted.

The companions are **illustrative, not runnable**: flows lifted from f-strings keep their
`{python_expr}` placeholders (e.g. `save "{out}"`), which is honest about what the test runs.

This is the generator behind the project rule: *every test add/change regenerates the
companions.* It is enforced two ways — a CI job (`.github/workflows/ci.yml`) regenerates and
fails on drift, and a Claude Code PostToolUse hook regenerates whenever a `tests/*.py` is
edited. Run manually with:  python scripts/gen_test_niva.py

Pure stdlib (ast) so it runs on a plain interpreter in CI; niva is imported only to widen the
verb vocabulary for flow detection, with a static fallback if it isn't importable.
"""

from __future__ import annotations

import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, "tests")
OUT_DIR = os.path.join(TESTS, "niva")

# Calls whose first string argument is a niva flow (or flow fragment).
FLOW_FUNCS = {"flow", "parse", "run", "run_file", "bound", "_run", "execute"}

# Verb vocabulary, to recognise a single-stage flow string (`show @c`, `load a.gpkg`) that
# isn't piped. Prefer the live registry; fall back to a static list if niva isn't importable.
try:
    sys.path.insert(0, REPO)
    from niva.describe import BUILTINS
    from niva.registry import core_registry

    VERBS = set(core_registry().verbs()) | set(BUILTINS)
except Exception:  # noqa: BLE001 — generator must run even without niva on the path
    VERBS = {
        "load",
        "save",
        "sql",
        "run",
        "split",
        "metadata",
        "assess",
        "catalog",
        "show",
        "info",
        "describe",
        "search",
        "docs",
        "project",
        "style",
        "notify",
        "email",
        "remove",
        "each",
        "call",
        "buffer",
        "clip",
        "reproject",
        "dissolve",
        "filter",
        "intersect",
        "difference",
        "centroid",
        "spatialjoin",
        "join",
        "warp",
        "selectloc",
    }


def _reconstruct(node: ast.AST) -> str | None:
    """Render a str constant or an f-string back to display text, keeping `{expr}` parts."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                parts.append("{" + ast.unparse(v.value) + "}")
            else:
                return None
        return "".join(parts)
    return None


def _looks_like_flow(text: str) -> bool:
    if "|" in text and " " in text:  # a multi-stage pipe — near-certain niva flow
        return True
    first = text.strip().split(" ", 1)[0].strip("\"'").lower()
    return first in VERBS


def _func_basename(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _flows_in(fn: ast.AST) -> list[str]:
    """Ordered, de-duplicated flow strings exercised by one test function."""
    seen, flows = set(), []

    def add(text):
        text = text.strip() if text else text
        if text and text not in seen:
            seen.add(text)
            flows.append(text)

    # ast.walk descends INTO f-strings, so a JoinedStr's literal fragments (e.g. the
    # `"load a.gpkg | assess to "` before `{out}`) would be captured as truncated flows.
    # Collect those inner Constant nodes and skip them — only the whole JoinedStr counts.
    inner = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.JoinedStr):
            for c in ast.walk(n):
                if c is not n:
                    inner.add(id(c))

    for node in ast.walk(fn):
        if id(node) in inner:
            continue
        if isinstance(node, ast.Call):
            name = _func_basename(node)
            if node.args:
                arg = _reconstruct(node.args[0])
                if arg is not None:
                    if name == "describe":
                        add(f"describe {arg}")
                    elif name in FLOW_FUNCS and (
                        _looks_like_flow(arg) or name in {"parse", "flow"}
                    ):
                        add(arg)
        # A piped string literal anywhere is a flow, even if we didn't see the call wrapper.
        text = _reconstruct(node)
        if text and "|" in text and _looks_like_flow(text):
            add(text)
    return flows


def _docline(fn: ast.AST) -> str:
    doc = ast.get_docstring(fn)
    return doc.strip().splitlines()[0].strip() if doc else ""


def _tests_in(node: ast.AST):
    """Yield (qualified_name, fn_node) for every test function, classes first."""
    for item in node.body:
        if isinstance(item, ast.ClassDef):
            for sub in item.body:
                if isinstance(
                    sub, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and sub.name.startswith("test"):
                    yield item.name, sub
        elif isinstance(
            item, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and item.name.startswith("test"):
            yield None, item


def _render(module: str, tree: ast.AST) -> str:
    mod_doc = ast.get_docstring(tree)
    lines = [
        "# " + "=" * 76,
        f"# Companion to tests/{module}.py — what each test exercises, in niva form.",
        "# AUTO-GENERATED by scripts/gen_test_niva.py — do not edit by hand.",
        "# Regenerate:  python scripts/gen_test_niva.py   (CI fails if this is stale)",
        "# Flows lifted from f-strings keep their {python} placeholders — illustrative,",
        "# not directly runnable.",
        "# " + "=" * 76,
    ]
    if mod_doc:
        lines.append("#")
        lines.append("# " + mod_doc.strip().splitlines()[0].strip())
    lines.append("")

    current_class = object()  # sentinel so the first class always prints a header
    for cls, fn in _tests_in(tree):
        if cls != current_class:
            current_class = cls
            if cls:
                lines.append(f"# ── {cls} " + "─" * max(2, 60 - len(cls)))
                lines.append("")
        doc = _docline(fn)
        header = f"# {fn.name}" + (f" — {doc}" if doc else "")
        lines.append(header)
        flows = _flows_in(fn)
        if flows:
            lines.extend(flows)
        else:
            lines.append("#   (pure Python — no niva flow)")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    test_files = sorted(
        f for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py")
    )
    written = []
    for f in test_files:
        module = f[:-3]
        src = open(os.path.join(TESTS, f), encoding="utf-8").read()
        tree = ast.parse(src, filename=f)
        out = os.path.join(OUT_DIR, f"{module}.niva")
        open(out, "w", encoding="utf-8").write(_render(module, tree))
        written.append(os.path.relpath(out, REPO))
    # Drop stale companions whose test file was deleted/renamed.
    valid = {f"{f[:-3]}.niva" for f in test_files}
    for existing in os.listdir(OUT_DIR):
        if existing.endswith(".niva") and existing not in valid:
            os.remove(os.path.join(OUT_DIR, existing))
            print(f"removed stale {os.path.join('tests/niva', existing)}")
    print(f"wrote {len(written)} companion .niva file(s) under tests/niva/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
