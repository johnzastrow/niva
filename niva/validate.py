"""Offline structural validation of niva flows (issues #26, #29).

Grammar (via ``parse``) + **closed-set verb** check + **`run <id>` id/parameter** check against
the packaged algorithm catalog — **no QGIS needed**. One implementation, shared by
``niva validate <file>`` and the verb/param checks in ``--explain``.

Severity: an **error** is definitively wrong (grammar failure, or a verb outside the closed set —
the set is authoritative). A **warning** may be a false positive (a `run` id/param not in the
catalog could be a third-party plugin), so it never fails validation.
"""

from __future__ import annotations

import difflib
import re
from functools import lru_cache

from .errors import FlowError
from .grammar import Call, parse

# Distance units the grammar understands — a distance-typed value without one of these is
# interpreted in the layer's CRS units (a classic silent gotcha on a geographic CRS).
_BARE_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


@lru_cache(maxsize=1)
def _verb_sets():
    """(`built-ins`, `all verbs`) — authoritative, straight from the engine + registry."""
    from .engine.engine import Engine
    from .registry.registry import core_registry

    builtins = set(Engine._BUILTIN_VERBS) | {"each", "call"}
    return builtins, builtins | set(core_registry().verbs())


def verb_issue(verb: str) -> str | None:
    """A message if ``verb`` is neither a built-in nor an alias (an unknown/invented verb),
    else None. Suggests the closest real verb."""
    _, all_verbs = _verb_sets()
    if verb in all_verbs:
        return None
    near = difflib.get_close_matches(verb, all_verbs, n=1)
    return (
        f"unknown verb `{verb}`"
        + (f" — did you mean `{near[0]}`?" if near else "")
        + " (use `run <provider:id> KEY=value` for a raw algorithm)"
    )


def run_param_issues(algo: str, options: dict) -> list[str]:
    """Warnings for a ``run <id> KEY=value`` step, checked against the catalog: an unknown
    algorithm id, or any `KEY=` that isn't a real parameter. The native-CLI harness ids
    (`pdalcli:`/`saga:`) aren't QGIS algorithms, so they're skipped."""
    from .engine.native import PDAL_PREFIX, SAGA_PREFIX
    from .registry import catalog

    if not algo or algo.startswith((PDAL_PREFIX, SAGA_PREFIX)):
        return []
    valid = catalog.param_names(algo)
    if valid is None:
        return [
            f"`{algo}` is not in niva's algorithm catalog — a third-party plugin id? "
            "double-check it"
        ]
    out = []
    for key in options:
        if key in valid:
            continue
        near = difflib.get_close_matches(key, valid, n=1)
        out.append(
            f"unknown parameter `{key}` for {algo}"
            + (f" — did you mean `{near[0]}`?" if near else "")
        )
    return out


def _bind_issues(stage, alias) -> list[tuple]:
    """Bind an alias stage in isolation — catches a missing required arg, an unknown option,
    a bad value/enum. Reported per-stage (with its line) so ALL are collected, not just the
    first (unlike a dry-run, which stops at the first failure)."""
    from .registry import bind

    try:
        bind(stage, alias)
        return []
    except FlowError as exc:
        return [(stage.line, "error", str(exc))]


def _lint_issues(stage, alias) -> list[tuple]:
    """Style / best-practice warnings for an alias stage (the flow runs, but…)."""
    out = []
    # A distance arg passed as a bare number — no unit ⇒ CRS units (usually not intended).
    dist_args = {a.name for a in alias.args if a.type == "distance"}
    if dist_args:
        for tok in stage.args:
            if _BARE_NUM_RE.match(tok):
                out.append(
                    (
                        stage.line,
                        "warning",
                        f"`{stage.verb} {tok}` has no unit — interpreted as the layer's CRS units; "
                        f"write e.g. `{tok}m` to be explicit",
                    )
                )
                break
    # Suggest a curated verb when the alias's algorithm is reached via `run` elsewhere is
    # handled in run_param path; nothing to add here.
    return out


def validate_program(program: list) -> list[tuple]:
    """All static issues in a parsed program: one ``(line, severity, message)`` per problem
    (``severity`` ``"error"`` | ``"warning"``). Collects **every** issue, not just the first.
    Empty list == clean static pass."""
    from .registry import catalog
    from .registry.registry import core_registry

    reg = core_registry()
    issues: list[tuple] = []
    last_producing = None  # for the no-output lint
    for st in program:
        if isinstance(st, Call):
            continue
        for s in st.stages:
            if s.verb == "run":
                algo = s.args[0] if s.args else None
                if not algo:
                    issues.append((s.line, "error", "`run` needs an algorithm id"))
                    continue
                issues += [
                    (s.line, "warning", w) for w in run_param_issues(algo, s.options)
                ]
                # Prefer a curated verb when one aliases this algorithm.
                entry = catalog.algorithm(algo)
                if entry and entry.get("verb"):
                    issues.append(
                        (
                            s.line,
                            "warning",
                            f"`run {algo}` has a friendly verb — prefer `{entry['verb']}`",
                        )
                    )
                # Provider preference: SAGA/OTB are optional & unmaintained on QGIS 4.
                if algo.startswith(("otb:", "saga:")):
                    issues.append(
                        (
                            s.line,
                            "warning",
                            f"`{algo}` uses SAGA/OTB — prefer native/gdal/qgis/pdal/grass unless required",
                        )
                    )
                last_producing = s.verb
                continue
            alias = reg.get(s.verb)
            if alias is not None:
                issues += _bind_issues(s, alias)
                issues += _lint_issues(s, alias)
                last_producing = s.verb
                continue
            vi = verb_issue(s.verb)
            if vi:
                issues.append((s.line, "error", vi))
            elif s.verb in {"load", "run", "sql", "split"} or s.verb in reg.verbs():
                last_producing = s.verb
            elif s.verb == "save":
                last_producing = None  # output persisted
    if last_producing is not None:
        issues.append(
            (
                0,
                "warning",
                f"flow ends on `{last_producing}` with no `save` — the result isn't written anywhere",
            )
        )
    return issues


# Substrings that mark a dry-run failure as DATA-dependent (the flow is fine; the inputs/files
# just aren't present) — downgraded to a warning so validating a template never false-fails.
_DATA_MARKERS = (
    "no files match",
    "no geospatial",
    "not a file",
    "no such file",
    "cannot find",
)


def _exercise(program: list, file: str | None) -> list[tuple]:
    """Run the flow through the no-QGIS ``MockBackend`` to catch what a static check can't:
    a bad option type, a transform before ``load``, an unresolvable distance, a bad save mode,
    ``each``/``call`` wiring. A genuine logic failure is an **error**; a purely data-dependent
    one (a glob/file that isn't present) is a **warning**, so a valid template still passes."""
    import os

    from .engine import Engine, MockBackend

    base = os.path.dirname(os.path.abspath(file)) if file else None
    try:
        Engine(MockBackend()).execute(program, base_dir=base)
    except FlowError as exc:
        sev = (
            "warning" if any(m in str(exc).lower() for m in _DATA_MARKERS) else "error"
        )
        lead = (
            "needs data to fully validate"
            if sev == "warning"
            else "would fail at runtime"
        )
        return [(getattr(exc, "line", 0), sev, f"{lead}: {exc}")]
    except Exception as exc:  # noqa: BLE001 — OpError and anything else the flow surfaces
        return [(0, "error", f"would fail at runtime: {exc}")]
    return []


def validate_text(
    text: str, file: str | None = None, *, exercise: bool = True
) -> tuple[bool, list[tuple]]:
    """Parse ``text`` (grammar), validate structure (closed-set verbs + `run` params), then —
    unless a hard error was already found — **exercise** it over the MockBackend so a flow that
    passes is genuinely runnable, not just well-formed. Returns ``(ok, issues)``; ``ok`` is False
    on any **error**-severity issue. ``exercise=False`` keeps it to the static pass."""
    try:
        program = parse(text, file=file)
    except FlowError as exc:
        return False, [(getattr(exc, "line", 0), "error", f"grammar: {exc}")]
    issues = validate_program(program)
    # Only dry-run when the static pass is clean — otherwise the engine would just re-raise the
    # same unknown-verb error we already reported.
    if exercise and not any(sev == "error" for _, sev, _ in issues):
        issues += _exercise(program, file)
    ok = not any(sev == "error" for _, sev, _ in issues)
    return ok, issues
