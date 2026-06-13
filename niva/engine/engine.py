"""The engine (planning/05-architecture.md).

Walks a parsed program and runs it stage by stage, threading one layer handle down
each flow's pipe. It owns the *orchestration* — built-in vs alias routing, feeding
the upstream layer into each op, resolving distances against the layer's CRS — and
delegates everything that touches geodata to a ``Backend``. No QGIS import here.
"""

from __future__ import annotations

import os

from ..errors import FlowError
from ..grammar import Call, Flow, parse
from ..registry import bind, core_registry
from ..values import Distance
from .backend import Backend
from .layer import Layer
from .units import resolve_distance


class Engine:
    def __init__(self, backend: Backend, registry=None):
        self.backend = backend
        self.registry = registry or core_registry()

    def execute(self, program: list, *, base_dir: str | None = None,
                _stack: tuple = ()) -> Layer | None:
        """Run every statement; return the final layer of the last flow.

        ``base_dir`` is the directory ``call`` targets are resolved against (the
        calling file's directory, or the cwd for an inline program). ``_stack`` is
        the chain of files currently being executed, for cycle detection."""
        base_dir = base_dir or os.getcwd()
        result: Layer | None = None
        for stmt in program:
            if isinstance(stmt, Call):
                result = self._run_call(stmt, base_dir, _stack)
            else:
                result = self.run_flow(stmt)
        return result

    # --- call (file composition, planning 10/02) -----------------------------

    def _run_call(self, call: Call, base_dir: str, stack: tuple) -> Layer | None:
        target = call.target
        path = target if os.path.isabs(target) else os.path.join(base_dir, target)
        path = os.path.abspath(path)
        if path in stack:
            chain = " → ".join(os.path.basename(p) for p in (*stack, path))
            raise FlowError(f"`call` cycle detected: {chain}", line=call.line, stage=call.raw)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise FlowError(
                f"`call` cannot read `{target}`: {exc.strerror or exc}",
                line=call.line, stage=call.raw,
            )
        sub_program = parse(text, file=path)
        return self.execute(sub_program, base_dir=os.path.dirname(path), _stack=(*stack, path))

    def run_flow(self, flow: Flow) -> Layer | None:
        current: Layer | None = None
        for stage in flow.stages:
            current = self._run_stage(stage, current)
        return current

    # --- per-stage dispatch --------------------------------------------------

    def _run_stage(self, stage, current: Layer | None) -> Layer | None:
        verb = stage.verb
        if verb == "load":
            return self._load(stage)
        if verb == "save":
            return self._save(stage, current)

        alias = self.registry.get(verb)
        if alias is None:
            raise FlowError(f"unknown verb `{verb}`", line=stage.line, stage=stage.raw)
        if current is None:
            raise FlowError(
                f"`{verb}` needs an input layer — start the flow with `load`",
                line=stage.line, stage=stage.raw,
            )

        op = bind(stage, alias)
        params = self._resolve_distances(op.params, current, stage)
        return self.backend.run(
            op.algorithm, params,
            input_param=op.input_param, input_layer=current, output_param=op.output_param,
        )

    # --- built-in verbs ------------------------------------------------------

    def _load(self, stage) -> Layer:
        if len(stage.args) != 1 or stage.options:
            raise FlowError(
                "`load` takes one source: `load <path-or-uri>`",
                line=stage.line, stage=stage.raw,
            )
        return self.backend.load(stage.args[0])

    def _save(self, stage, current: Layer | None) -> Layer:
        if current is None:
            raise FlowError(
                "`save` has nothing to save — the flow has not loaded a layer yet",
                line=stage.line, stage=stage.raw,
            )
        if len(stage.args) != 1 or stage.options:
            raise FlowError(
                "`save` takes one destination: `save <path>`",
                line=stage.line, stage=stage.raw,
            )
        return self.backend.save(current, stage.args[0])

    # --- distance resolution -------------------------------------------------

    def _resolve_distances(self, params: dict, layer: Layer, stage) -> dict:
        if not any(isinstance(v, Distance) for v in params.values()):
            return params
        crs = self.backend.crs_of(layer)
        return {
            key: (resolve_distance(value, crs, stage=stage) if isinstance(value, Distance) else value)
            for key, value in params.items()
        }
