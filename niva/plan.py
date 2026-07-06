"""The resolved-plan IR (intermediate representation) — the compiler's public output
(docs/planning/20 §3).

An *intermediate representation* is a stable, structured form that sits between the source
(`.niva` text) and execution — like a compiler's bytecode between source and CPU. Consumers
read the IR, never the raw text or internal objects, so the front-end and back-end can each
change independently as long as this shape stays stable.

``build_plan`` compiles a parsed niva program into a **versioned, QGIS-free plan**: an
ordered list of resolved operations (verb → algorithm + params + injected defaults) plus
the same diagnostics ``validate`` produces. This dict is the *contract* every downstream
consumer reads — the executor, ``explain``, ``export``, and machine consumers (LSP/LLM) —
so the front-end's language and packaging can change without touching them.

Deliberately minimal for Phase 0 (issue #41): data-flow is linear (``inputs`` is the
previous producing step); ``each``/``split`` fan-out is represented per-stage but its
batching is a future IR revision. Bump ``PLAN_VERSION`` on any breaking change; the field
travels in every plan so consumers can guard on it.
"""

from __future__ import annotations

from .errors import FlowError
from .grammar import Call
from .values import Distance

PLAN_VERSION = "1"

# Verb behaviour classes (docs/guide/reference.md §1). Small + stable; used ONLY to derive
# `produces`/`inputs` for the IR — never a second source of truth for dispatch.
_TERMINAL = {"catalog", "show", "info", "describe", "search", "docs", "project"}
_NO_UPSTREAM = {
    "load",
    "each",
} | _TERMINAL  # verbs that don't consume the upstream layer
_OFFLINE_OPS = {"describe", "search", "docs"}  # runnable with no QGIS at all


def build_plan(program: list, *, file: str | None = None) -> dict:
    """Compile a parsed ``program`` into the plan IR (a JSON-serialisable dict)."""
    from . import __version__
    from .registry import core_registry
    from .validate import validate_program

    reg = core_registry()
    steps: list = []
    sid = 0
    prev = None  # id of the step whose layer feeds the next (linear pipe)
    for stmt in program:
        if isinstance(stmt, Call):
            sid += 1
            steps.append(
                {
                    "id": sid,
                    "stage": (stmt.raw or f"call {stmt.target}").strip(),
                    "op": "call",
                    "kind": "call",
                    "algorithm": None,
                    "params": {"target": stmt.target},
                    "inputs": [],
                    "produces": "varies",
                }
            )
            continue
        for stage in stmt.stages:
            sid += 1
            steps.append(_step(stage, sid, prev, reg))
            if stage.verb not in _TERMINAL:  # producing / pass-through threads the pipe
                prev = sid

    issues = validate_program(program)
    return {
        "niva_plan": PLAN_VERSION,
        "niva_version": __version__,
        "source": {"file": file},
        "steps": steps,
        "diagnostics": [
            {"line": ln, "severity": sev, "message": msg} for (ln, sev, msg) in issues
        ],
        "requires_qgis": bool(steps)
        and not all(s["op"] in _OFFLINE_OPS for s in steps),
    }


def _step(stage, sid: int, prev, reg) -> dict:
    from .registry import bind

    op = stage.verb
    text = (stage.raw or op).strip()
    inputs = [] if (op in _NO_UPSTREAM or prev is None) else [prev]

    if op == "run":
        return {
            "id": sid,
            "stage": text,
            "op": "run",
            "kind": "run",
            "algorithm": stage.args[0] if stage.args else None,
            "params": {k: _jsonable(v) for k, v in stage.options.items()},
            "inputs": inputs,
            "produces": "layer",
        }

    alias = reg.get(op)
    if alias is not None:
        params: dict = {}
        injected: dict = {}
        try:
            bound = bind(stage, alias)
            params = {k: _jsonable(v) for k, v in bound.params.items()}
            injected = _injected(stage, alias, params)
        except FlowError:
            pass  # the stage is invalid — diagnostics carry it; keep the step shape
        return {
            "id": sid,
            "stage": text,
            "op": op,
            "kind": "alias",
            "algorithm": alias.algorithm,
            "params": params,
            "injected_defaults": injected,
            "inputs": inputs,
            "produces": "layer",
        }

    # builtin (load / save / sql / split / show / …): engine-handled, no QGIS algorithm.
    return {
        "id": sid,
        "stage": text,
        "op": op,
        "kind": "builtin",
        "algorithm": None,
        "params": {"args": list(stage.args), "options": dict(stage.options)},
        "inputs": inputs,
        "produces": "none" if op in _TERMINAL else "layer",
    }


def _injected(stage, alias, params: dict) -> dict:
    """The resolved params the user did NOT type — the alias's option/flag defaults and
    forced values. This is the reproducibility payload: the exact method niva applied."""
    user: set = set()
    positionals = [a for a in stage.args if a not in alias.flags]
    for i, spec in enumerate(alias.args):
        if i < len(positionals):
            user.add(spec.param)
    for arg in stage.args:
        flag = alias.flags.get(arg)
        if flag is not None:
            user.add(flag.param)
    for key in stage.options:
        opt = alias.options.get(key)
        if opt is not None:
            user.add(opt.param)
    return {k: v for k, v in params.items() if k not in user}


def _jsonable(value):
    """Make a bound param value JSON-serialisable (a `Distance` → ``{value, unit}``)."""
    if isinstance(value, Distance):
        return {"value": value.value, "unit": value.unit}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return str(value)
