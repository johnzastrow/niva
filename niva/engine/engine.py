"""The engine (docs/planning/05-architecture.md).

Walks a parsed program and runs it stage by stage, threading one layer handle down
each flow's pipe. It owns the *orchestration* — built-in vs alias routing, feeding
the upstream layer into each op, resolving distances against the layer's CRS — and
delegates everything that touches geodata to a ``Backend``. No QGIS import here.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from ..errors import FlowError, NivaError
from ..grammar import Call, Flow, parse
from ..registry import bind, core_registry
from ..values import Distance
from .backend import Backend
from .connections import is_connection_ref, parse_connection_ref
from .layer import Layer
from .units import resolve_distance


class Engine:
    def __init__(self, backend: Backend, registry=None, journal=None):
        self.backend = backend
        self.registry = registry or core_registry()
        self.journal = journal  # optional run journal (jsonl + human log); see niva.journal

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
        if self.journal is not None:
            self.journal.record(text=(call.raw or f"call {target}").strip(), kind="call")
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
        lineage: list = []  # niva stages that built `current`, for save → history
        for stage in flow.stages:
            text = (stage.raw or stage.verb).strip()
            t0 = time.monotonic()
            try:
                current = self._run_stage(stage, current, lineage)
            except NivaError as exc:
                self._record(stage, text, ok=False, error=str(exc), t0=t0)
                raise
            self._record(stage, text, ok=True, t0=t0)
            # history lineage entries are timestamped too (planning 08-§3)
            lineage.append(f"{_now()} {text}")
        return current

    def _record(self, stage, text, *, ok, t0, error=None) -> None:
        if self.journal is None:
            return
        self.journal.record(
            text=text, kind=stage.verb, algorithm=self._algorithm_of(stage),
            summary=self._paths_of(stage), ok=ok, error=error,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )

    def _algorithm_of(self, stage):
        if stage.verb == "run":
            return stage.args[0] if stage.args else None
        alias = self.registry.get(stage.verb)
        return alias.algorithm if alias is not None else None

    def _paths_of(self, stage) -> str:
        """The file path(s) a stage reads/writes, as **absolute** paths — so the log
        always tells you where a file actually went (a relative path resolves against
        the process cwd, which is where niva wrote it). Connection refs (@conn) are
        not file paths and are left out."""
        verb, paths = stage.verb, []
        if verb in ("load", "save") and stage.args and not stage.args[0].startswith("@"):
            paths.append(stage.args[0].split("|", 1)[0])
        elif verb == "assess":
            rest = [a for a in stage.args if a.lstrip("-") != "deep"]
            if len(rest) == 2 and rest[0] == "to":
                paths.append(rest[1])
        elif verb == "run":
            # just the produced file — the inputs are already in the command text
            value = stage.options.get("OUTPUT")
            if isinstance(value, str) and value and not value.startswith("@"):
                paths.append(value.split("|", 1)[0])
        return ", ".join(os.path.abspath(p) for p in paths)

    # --- per-stage dispatch --------------------------------------------------

    def _run_stage(self, stage, current: Layer | None, lineage: list) -> Layer | None:
        verb = stage.verb
        if verb == "load":
            return self._load(stage)
        if verb == "save":
            return self._save(stage, current, lineage)
        if verb == "sql":
            return self._sql(stage)
        if verb == "metadata":
            return self._metadata(stage, current)
        if verb == "assess":
            return self._assess(stage, current)
        if verb == "run":
            return self._run_raw(stage, current)

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
                "`load` takes one source: `load <path-or-uri>` or `load @conn.table`",
                line=stage.line, stage=stage.raw,
            )
        source = stage.args[0]
        if is_connection_ref(source):
            # `@` is for SAVED database connections, not files. `@example.gpkg` is a
            # common slip — catch a filename-looking ref and point at the path form.
            if source.lower().endswith(_FILE_EXTS):
                path = source[1:]
                raise FlowError(
                    f"`{source}` looks like a file, but `@` is for saved QGIS database "
                    f"connections. Load a file by path instead (GeoPackages hold many "
                    f'layers, so name one): `load "{path}|layername=<layer>"`.',
                    line=stage.line, stage=stage.raw,
                )
            try:
                conn, schema, table = parse_connection_ref(source)
            except ValueError as exc:
                raise FlowError(f"`load`: {exc}", line=stage.line, stage=stage.raw)
            if table is None:
                raise FlowError(
                    f"`load @conn.table` needs a table — `{source}` is a bare "
                    "connection (use `sql @conn \"…\"` to query it)",
                    line=stage.line, stage=stage.raw,
                )
            return self.backend.load_table(conn, schema, table)
        return self.backend.load(source)

    def _sql(self, stage) -> Layer:
        if len(stage.args) != 2 or stage.options:
            raise FlowError(
                '`sql` takes a connection and a query: `sql @conn "SELECT …"`',
                line=stage.line, stage=stage.raw,
            )
        ref, query = stage.args
        if not is_connection_ref(ref):
            raise FlowError(
                f'`sql` needs a connection first: `sql @conn "…"` (got `{ref}`)',
                line=stage.line, stage=stage.raw,
            )
        conn, schema, table = parse_connection_ref(ref)
        if schema or table:
            raise FlowError(
                f"`sql` takes a bare connection `@{conn}`, not a table reference (`{ref}`)",
                line=stage.line, stage=stage.raw,
            )
        return self.backend.run_sql(conn, query)

    def _save(self, stage, current: Layer | None, lineage: list) -> Layer:
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
        return self.backend.save(current, stage.args[0], lineage=lineage)

    def _metadata(self, stage, current: Layer | None) -> Layer:
        # `metadata set key=value …` — attach descriptive metadata to the current
        # layer; persisted to disk by the next `save` (08-§3).
        if current is None:
            raise FlowError(
                "`metadata` sets metadata on the current layer — load one first",
                line=stage.line, stage=stage.raw,
            )
        if stage.args != ["set"]:
            raise FlowError(
                '`metadata` supports one form: `metadata set key=value …`',
                line=stage.line, stage=stage.raw,
            )
        if not stage.options:
            raise FlowError(
                '`metadata set` needs at least one field, e.g. `title="…"`',
                line=stage.line, stage=stage.raw,
            )
        unknown = [k for k in stage.options if k not in _METADATA_FIELDS]
        if unknown:
            raise FlowError(
                f"`metadata set`: unknown field(s) {', '.join(unknown)} — supported: "
                + ", ".join(sorted(_METADATA_FIELDS)),
                line=stage.line, stage=stage.raw,
            )
        return self.backend.set_metadata(current, dict(stage.options))

    def _assess(self, stage, current: Layer | None) -> Layer | None:
        # `assess [deep] to <report.md>` — profile the current layer and write a
        # data-quality report (08-§4). A pass-through, so it can sit mid-pipe.
        if current is None:
            raise FlowError(
                "`assess` profiles the current layer — load one first",
                line=stage.line, stage=stage.raw,
            )
        if stage.options:
            raise FlowError(
                "`assess` takes no key=value options — `assess [deep] to <report.md>`",
                line=stage.line, stage=stage.raw,
            )
        deep = False
        rest = []
        for arg in stage.args:
            if arg.lstrip("-") == "deep":
                deep = True
            else:
                rest.append(arg)
        if len(rest) != 2 or rest[0] != "to":
            raise FlowError(
                "`assess` needs an output: `assess [deep] to <report.md>`",
                line=stage.line, stage=stage.raw,
            )
        dest = rest[1]
        profile = self.backend.profile(current, deep)
        report = _format_assessment(profile, deep)
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(report)
        return current

    def _run_raw(self, stage, current: Layer | None) -> Layer | None:
        # `run <algorithm> KEY=value …` — the escape hatch (07-§8). Params are passed
        # to the algorithm verbatim (no registry, no alias). Values are best-effort
        # scalar-coerced (int/float/bool) so e.g. RESAMPLING=1 reaches QGIS as 1, not
        # "1". The backend injects INPUT (from the upstream layer) and OUTPUT (temp)
        # when absent.
        if not stage.args:
            raise FlowError(
                "`run` needs an algorithm id: `run native:slope KEY=value`",
                line=stage.line, stage=stage.raw,
            )
        if len(stage.args) > 1:
            extra = ", ".join(repr(a) for a in stage.args[1:])
            raise FlowError(
                f"`run` takes one algorithm id, then KEY=value options; got extra: {extra}",
                line=stage.line, stage=stage.raw,
            )
        algorithm = stage.args[0]
        params = {key: _run_value(value) for key, value in stage.options.items()}
        return self.backend.run_raw(algorithm, params, input_layer=current)

    # --- distance resolution -------------------------------------------------

    def _resolve_distances(self, params: dict, layer: Layer, stage) -> dict:
        if not any(isinstance(v, Distance) for v in params.values()):
            return params
        crs = self.backend.crs_of(layer)
        return {
            key: (resolve_distance(value, crs, stage=stage) if isinstance(value, Distance) else value)
            for key, value in params.items()
        }


_METADATA_FIELDS = {"title", "abstract", "keywords", "identifier", "license"}

# Extensions that mean "this `@ref` is really a file, not a connection name".
_FILE_EXTS = (".gpkg", ".shp", ".geojson", ".json", ".tif", ".tiff", ".sqlite",
              ".db", ".gml", ".kml", ".csv", ".gpx", ".fgb", ".parquet")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_assessment(profile: dict, deep: bool) -> str:
    """Render a profile dict (from Backend.profile) as a markdown quality report."""
    name = profile.get("name") or "(unnamed)"
    lines = [f"# Data quality assessment — {name}", "", "_Generated by niva `assess`._", ""]

    crs = profile.get("crs") or {}
    crs_kind = "geographic" if crs.get("geographic") else "projected"
    crs_set = "set" if crs.get("valid") else "**NOT set**"
    lines += ["## Overview", ""]
    if profile.get("facet") == "raster":
        lines += [
            f"- **Type:** raster",
            f"- **Size:** {profile.get('width')} × {profile.get('height')} px, "
            f"{profile.get('bands')} band(s)",
        ]
    else:
        lines += [
            f"- **Type:** vector ({profile.get('geometry_type') or 'unknown geometry'})",
            f"- **Features:** {profile.get('feature_count')}",
        ]
    lines.append(f"- **CRS:** {crs.get('authid', '(none)')} ({crs_kind}) — {crs_set}")
    extent = profile.get("extent")
    if extent:
        lines.append(
            "- **Extent:** "
            f"{extent['xmin']:.6g}, {extent['ymin']:.6g} → "
            f"{extent['xmax']:.6g}, {extent['ymax']:.6g}"
        )
    else:
        lines.append("- **Extent:** (empty / none)")
    lines.append("")

    meta = profile.get("metadata") or {}
    if any([meta.get("title"), meta.get("abstract"), meta.get("keywords"), meta.get("history")]):
        lines += ["## Metadata", ""]
        if meta.get("title"):
            lines.append(f"- **Title:** {meta['title']}")
        if meta.get("abstract"):
            lines.append(f"- **Abstract:** {meta['abstract']}")
        if meta.get("keywords"):
            lines.append(f"- **Keywords:** {', '.join(meta['keywords'])}")
        history = meta.get("history") or []
        if history:
            lines.append("- **Lineage:**")
            lines += [f"    - {h}" for h in history]
        lines.append("")

    fields = profile.get("fields")
    if fields is not None:
        lines += [f"## Fields ({len(fields)})", "", "| name | type |", "|------|------|"]
        lines += [f"| {f['name']} | {f['type']} |" for f in fields]
        lines.append("")

    if deep:
        lines += ["## Quality checks", ""]
        lines.append(f"- **Invalid geometries:** {profile.get('invalid_geometries', 'n/a')}")
        lines.append(f"- **Empty geometries:** {profile.get('empty_geometries', 'n/a')}")
        lines.append(f"- **Duplicate geometries:** {profile.get('duplicate_geometries', 'n/a')}")
        nulls = profile.get("null_counts") or {}
        if nulls:
            flagged = {k: v for k, v in nulls.items() if v}
            if flagged:
                detail = ", ".join(f"{k}: {v}" for k, v in flagged.items())
                lines.append(f"- **Null values:** {detail}")
            else:
                lines.append("- **Null values:** none")
        lines.append("")
    else:
        lines += ["_Run `assess deep to …` for geometry-validity and null checks._", ""]

    return "\n".join(lines)


def _run_value(value: str):
    """A `run` option value. A `;`-joined value becomes a list — QGIS's own layer-list
    separator — so multilayer params (e.g. `gdal:merge INPUT="a.tif;b.tif"`) work;
    otherwise a single scalar."""
    if ";" in value:
        return [_scalar(part.strip()) for part in value.split(";") if part.strip()]
    return _scalar(value)


def _scalar(value: str):
    """Best-effort coercion of a raw `run` option value to int / float / bool,
    falling back to the original string (paths, CRS strings, field names, …)."""
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
