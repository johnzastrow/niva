"""The engine (docs/planning/05-architecture.md).

Walks a parsed program and runs it stage by stage, threading one layer handle down
each flow's pipe. It owns the *orchestration* — built-in vs alias routing, feeding
the upstream layer into each op, resolving distances against the layer's CRS — and
delegates everything that touches geodata to a ``Backend``. No QGIS import here.
"""

from __future__ import annotations

import glob
import os
import time
from datetime import datetime, timezone

from ..errors import FlowError, NivaError, OpError
from ..grammar import Call, Flow, parse
from ..registry import bind, core_registry
from ..values import Distance
from .backend import Backend
from .connections import is_connection_ref, parse_connection_ref
from .layer import Layer
from .units import resolve_distance


class Engine:
    def __init__(self, backend: Backend, registry=None, journal=None, progress=None, cancel=None):
        self.backend = backend
        self.registry = registry or core_registry()
        self.journal = journal  # optional run journal (jsonl + human log); see niva.journal
        self.progress = progress  # optional callable(str): live status during a run
        self.cancel = cancel  # optional callable() -> bool: abort the running algorithm
        self._pending_call = None  # processing.run(...) echo for the stage being run
        self._batch_item = None  # current item name while running an `each` batch
        self._batch_gpkgs = None  # GeoPackage targets written during a batch, to compact
        # Run state, for `notify` message variables and auto-alerts:
        self._run_t0 = None       # monotonic clock at run start (total elapsed)
        self._run_started = ""    # ISO datetime of run start
        self._last_elapsed = 0.0  # seconds the previous stage took ({last})
        self._op_count = 0        # operations recorded so far ({ops})
        self._err_count = 0       # failures so far ({errors})
        self._alerted = set()     # warning messages already alerted (dedup per run)

    def _emit(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def execute(self, program: list, *, base_dir: str | None = None,
                _stack: tuple = ()) -> Layer | None:
        """Run every statement; return the final layer of the last flow.

        ``base_dir`` is the directory ``call`` targets are resolved against (the
        calling file's directory, or the cwd for an inline program). ``_stack`` is
        the chain of files currently being executed, for cycle detection."""
        base_dir = base_dir or os.getcwd()
        prev_base = getattr(self, "_base_dir", None)
        self._base_dir = base_dir  # relative globs/paths resolve against this
        top_level = not _stack
        if top_level:  # stamp the niva version + wall-clock start; reset run state
            from .. import __version__

            self._run_t0 = time.monotonic()
            self._run_started = _human_time()
            self._last_elapsed = 0.0
            self._op_count = self._err_count = 0
            self._alerted = set()
            self._emit(f"niva {__version__} — run started {self._run_started}")
        result: Layer | None = None
        ok = False
        try:
            for stmt in program:
                if isinstance(stmt, Call):
                    result = self._run_call(stmt, base_dir, _stack)
                else:
                    result = self.run_flow(stmt)
            ok = True
            return result
        except NivaError as exc:
            result = None  # the run failed — keep nothing, free every scratch file
            if top_level:  # the run aborted — optionally ping ntfy (NIVA_NTFY_ON_ERROR)
                self._alert_error(exc)
            raise
        finally:
            self._base_dir = prev_base
            if top_level:
                # Delete this run's scratch (sparing the final layer's own file). Runs
                # even on failure, so a crash mid-pipeline strands no gigabytes; on a
                # clean run (``ok``) the empty scratch *directory* is removed too.
                purge = getattr(self.backend, "purge_scratch", None)
                if callable(purge):
                    purge(keep=result, remove_dir=ok)
                self._emit(f"niva — run finished {_human_time()}")

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
        # A flow that begins with `each` is a batch: the remaining stages run once
        # per source (file/layer). Otherwise it is a single linear pass.
        if flow.stages and flow.stages[0].verb == "each":
            return self._run_batch(flow.stages)
        current: Layer | None = None
        lineage: list = []  # niva stages that built `current`, for save → history
        for stage in flow.stages:
            current = self._execute_stage(stage, current, lineage)
        return current

    def _execute_stage(self, stage, current: Layer | None, lineage: list) -> Layer | None:
        """Run one stage: announce it, time it, dispatch, journal it, extend lineage."""
        text = (stage.raw or stage.verb).strip()
        self._emit(f"▶ {text}")
        t0 = time.monotonic()
        try:
            current = self._run_stage(stage, current, lineage)
        except NivaError as exc:
            self._record(stage, text, ok=False, error=str(exc), t0=t0)
            raise
        self._last_elapsed = time.monotonic() - t0  # for the `{last}` notify variable
        self._record(stage, text, ok=True, t0=t0)
        self._emit(f"  ✓ {_fmt_elapsed(self._last_elapsed)}")
        # history lineage entries are timestamped too (planning 08-§3)
        lineage.append(f"{_now()} {text}")
        return current

    def _run_batch(self, stages) -> Layer | None:
        """Run `each <source> | …` once per resolved source. `save` inside a batch
        names each output after its source: into a multi-layer `.gpkg` (one layer per
        item) or to a path with a `{name}` placeholder. A failing item is skipped (the
        batch continues), so one bad file can't abort the whole run."""
        each_stage, rest = stages[0], stages[1:]
        if not rest:
            raise FlowError(
                '`each` needs stages after it, e.g. '
                '`each "dir/*.shp" | reproject EPSG:6346 | save out.gpkg`',
                line=each_stage.line, stage=each_stage.raw,
            )
        items = self._resolve_each(each_stage)
        self._batch_gpkgs = set()  # collect .gpkg/.sqlite targets to compact at the end
        self._emit(f"▶ {each_stage.raw}  → {len(items)} item(s)")
        if self.journal is not None:
            self.journal.record(text=each_stage.raw, kind="each",
                                summary=f"{len(items)} item(s)")
        done = 0
        for i, (name, uri) in enumerate(items, 1):
            if self.cancel and self.cancel():
                self._emit("  batch canceled")
                break
            self._batch_item = name
            self._emit(f"  [{i}/{len(items)}] {name}")
            try:
                current = self.backend.load(uri)
                lineage = [f"{_now()} each {name}"]
                for st in rest:
                    current = self._execute_stage(st, current, lineage)
                done += 1
            except OpError as exc:  # this item's data failed — skip it, keep going
                self._emit(f"    skipped {name}: {exc}")
                self._err_count += 1
                self._alert_warning(f"batch skipped {name}: {exc}")
                if self.journal is not None:
                    self.journal.record(text=f"each item {name}", kind="each",
                                        ok=False, error=str(exc))
            # A FlowError (usage/config — e.g. a bad save target) would fail every
            # item identically, so it is NOT caught here: it propagates and aborts the
            # batch rather than silently doing nothing.
        self._batch_item = None
        # Multi-layer append leaves free pages; compact each container once at the end
        # so the GeoPackage isn't bloated (rather than VACUUMing after every layer).
        for gpkg in sorted(self._batch_gpkgs):
            try:
                self.backend.compact(gpkg)
                self._emit(f"  compacted {os.path.basename(gpkg)}")
            except Exception as exc:  # best effort — a failed VACUUM is not fatal
                self._emit(f"  (could not compact {os.path.basename(gpkg)}: {exc})")
        self._batch_gpkgs = None
        self._emit(f"  batch done: {done}/{len(items)} item(s)")
        return None

    def _resolve_each(self, stage) -> list:
        """Resolve `each <source>` to an ordered list of (name, load-uri): a glob of
        files, a directory (recursed), or a single file. Multi-layer containers
        (GeoPackages) expand to one item per layer."""
        from ..utilities import CATALOG_MULTILAYER_EXTS, facet_for_ext

        if not stage.args:
            raise FlowError('`each` needs a source: `each "<dir>"`, `each "<glob>"`, '
                            "or `each <file.gpkg>`", line=stage.line, stage=stage.raw)
        raw = os.path.expanduser(stage.args[0])
        items: list = []

        def add(path):
            ext = os.path.splitext(path)[1]
            if facet_for_ext(ext) is None:
                return
            if ext.lower() in CATALOG_MULTILAYER_EXTS:
                names = self.backend.sublayers(path)
                if names:
                    items.extend((n, f"{path}|layername={n}") for n in names)
                    return
            items.append((os.path.splitext(os.path.basename(path))[0], path))

        if any(c in raw for c in "*?["):  # glob pattern
            matches = sorted(glob.glob(raw))
            if not matches:
                raise FlowError(f"`each`: no files match `{stage.args[0]}`",
                                line=stage.line, stage=stage.raw)
            for m in matches:
                if os.path.isfile(m):
                    add(m)
        elif os.path.isdir(raw):  # recurse a directory
            for dirpath, _dirs, files in os.walk(raw):
                for fn in sorted(files):
                    add(os.path.join(dirpath, fn))
        elif os.path.isfile(raw):  # a single file (maybe multi-layer)
            add(raw)
        else:
            raise FlowError(f"`each`: no such file or directory: {raw}",
                            line=stage.line, stage=stage.raw)
        if not items:
            raise FlowError(f"`each`: no geospatial datasets found in `{stage.args[0]}`",
                            line=stage.line, stage=stage.raw)
        return items

    def _record(self, stage, text, *, ok, t0, error=None) -> None:
        note = getattr(self.backend, "_note", None)
        self._op_count += 1
        if not ok:
            self._err_count += 1
        if note:  # surface handling notices (mixed geometry, datum transform) via ntfy
            self._alert_warning(note)
        if self.journal is not None:
            self.journal.record(
                text=text, kind=stage.verb, algorithm=self._algorithm_of(stage),
                summary=self._paths_of(stage), ok=ok, error=error,
                duration_ms=round((time.monotonic() - t0) * 1000),
                pyqgis=self._pending_call, note=note,
            )

    def _algorithm_of(self, stage):
        if stage.verb == "run":
            return stage.args[0] if stage.args else None
        if stage.verb == "split":
            return "native:filterbygeometry"
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
        elif verb == "catalog":
            out = stage.options.get("to")
            root = stage.args[0] if stage.args else None
            paths.append(out if out else (os.path.join(root, "catalog.md") if root else ""))
            paths = [p for p in paths if p]
        return ", ".join(os.path.abspath(os.path.expanduser(p)) for p in paths)

    # --- per-stage dispatch --------------------------------------------------

    def _run_stage(self, stage, current: Layer | None, lineage: list) -> Layer | None:
        self._pending_call = None  # set only when this stage actually runs an algorithm
        if hasattr(self.backend, "_note"):
            self.backend._note = None  # a per-op handling notice (e.g. mixed geometry)
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
        if verb == "notify":
            return self._notify(stage, current)
        if verb == "email":
            return self._email(stage, current)
        if verb == "catalog":
            return self._catalog(stage)
        if verb == "split":
            return self._split(stage, current)
        if verb == "each":
            raise FlowError(
                "`each` must be the first stage of a flow — `each \"<dir>\" | … | save out.gpkg`",
                line=stage.line, stage=stage.raw,
            )

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
        self._pending_call = self.backend.render_call(
            op.algorithm, params,
            input_param=op.input_param, input_layer=current, output_param=op.output_param,
        )
        return self.backend.run(
            op.algorithm, params,
            input_param=op.input_param, input_layer=current, output_param=op.output_param,
            progress=self.progress, cancel=self.cancel,
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
        return self.backend.load(os.path.expanduser(source))

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
        if stage.options:
            raise FlowError(
                "`save` takes no key=value options — `save <path>` or "
                "`save <path> as <layer>`",
                line=stage.line, stage=stage.raw,
            )
        args = stage.args
        explicit_name = None
        if len(args) == 3 and args[1] == "as":  # save <path> as <layer>
            path, explicit_name = args[0], args[2]
        elif len(args) == 1:
            path = args[0]
        else:
            raise FlowError(
                "`save` takes `save <path>` or `save <path> as <layer>`",
                line=stage.line, stage=stage.raw,
            )

        batch = self._batch_item
        dest = os.path.expanduser(path)
        templated = "{name}" in dest
        if templated and not batch:
            raise FlowError(
                "`{name}` in a save path only works inside an `each` batch",
                line=stage.line, stage=stage.raw,
            )
        if templated:
            dest = dest.replace("{name}", _safe_name(batch))
        # `{name}` is also honoured in an explicit `as <layer>` so `save out.gpkg as
        # {name}` does the obvious thing inside a batch.
        if explicit_name and "{name}" in explicit_name:
            if not batch:
                raise FlowError("`{name}` only works inside an `each` batch",
                                line=stage.line, stage=stage.raw)
            explicit_name = explicit_name.replace("{name}", batch)

        # The layer name to write: explicit `as`, else the batch item's name.
        layer_name = explicit_name or (batch if (batch and not templated) else None)
        ext = os.path.splitext(dest)[1].lower()
        is_container = ext in (".gpkg", ".sqlite", ".db")

        if explicit_name and not is_container:
            raise FlowError(
                "`save … as <layer>` writes a named layer into a multi-layer "
                "container — use a .gpkg/.sqlite path",
                line=stage.line, stage=stage.raw,
            )
        if batch and not templated and not is_container:
            raise FlowError(
                "a batch (`each`) save needs a multi-layer .gpkg target (one layer per "
                "item) or a `{name}` placeholder in the path, e.g. `save \"out/{name}.tif\"`",
                line=stage.line, stage=stage.raw,
            )
        append = is_container and layer_name is not None
        if self._batch_gpkgs is not None and is_container:
            self._batch_gpkgs.add(dest)  # compact this container when the batch ends
        return self.backend.save(current, dest, lineage=lineage,
                                 layer_name=layer_name, append=append)

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
        dest = os.path.expanduser(rest[1])
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
        params = {key: self._expand_value(value, stage) for key, value in stage.options.items()}
        self._pending_call = self.backend.render_call(algorithm, params, input_layer=current)
        return self.backend.run_raw(algorithm, params, input_layer=current,
                                    progress=self.progress, cancel=self.cancel)

    # --- utility verbs (side effects; not QGIS algorithms, see niva.utilities) ---

    def _notify(self, stage, current: Layer | None) -> Layer | None:
        """`notify "message" [to=<topic>] [title=…] [priority=…] [server=…] [tags=…]`
        — push a message via ntfy. Pass-through: returns the upstream layer so it
        chains, e.g. `… | save out.gpkg | notify "done"`."""
        from ..utilities import send_ntfy

        message = stage.args[0] if stage.args else stage.options.get("message", "")
        if not message:
            raise FlowError('notify needs a message: `notify "your message" to=<topic>`',
                            line=stage.line, stage=stage.raw)
        opts = stage.options
        target = send_ntfy(
            self._interpolate(message), topic=opts.get("to"), server=opts.get("server"),
            title=opts.get("title"), priority=opts.get("priority"), tags=opts.get("tags"),
        )
        self._emit(f"  notified → {target}")
        return current

    def _interpolate(self, message: str) -> str:
        """Substitute job variables in a notify message: ``{elapsed}`` (total job time),
        ``{last}`` (the previous stage's time), ``{now}``, ``{started}``, ``{ops}``
        (operations so far), ``{errors}`` (failures so far)."""
        if "{" not in message:
            return message
        total = (time.monotonic() - self._run_t0) if self._run_t0 else 0.0
        values = {
            "elapsed": _fmt_elapsed(total),
            "last": _fmt_elapsed(self._last_elapsed),
            "now": _human_time(),
            "started": self._run_started,
            "ops": str(self._op_count),
            "errors": str(self._err_count),
        }
        for key, value in values.items():
            message = message.replace("{" + key + "}", value)
        return message

    # --- ntfy auto-alerts on errors / warnings (opt-in via env flags) --------

    def _alert(self, message: str, *, kind: str, priority: str | None = None) -> None:
        """Best-effort ntfy alert, gated by an env flag. ``kind`` is "error" or
        "warning"; warnings are de-duplicated per run so a batch can't spam. Never
        raises — an alert must not break (or abort) the run."""
        flag = "NIVA_NTFY_ON_ERROR" if kind == "error" else "NIVA_NTFY_ON_WARNING"
        if str(os.environ.get(flag, "")).strip().lower() not in ("1", "true", "yes", "on"):
            return
        if kind == "warning":
            if message in self._alerted:
                return
            self._alerted.add(message)
        try:
            from ..utilities import send_ntfy

            send_ntfy(message, priority=priority)
        except Exception:  # no topic configured, network error, … — stay silent
            pass

    def _alert_error(self, exc) -> None:
        total = _fmt_elapsed((time.monotonic() - self._run_t0) if self._run_t0 else 0.0)
        self._alert(f"niva ERROR after {total}: {exc}", kind="error", priority="high")

    def _alert_warning(self, note: str) -> None:
        self._alert(f"niva warning: {note}", kind="warning")

    def _email(self, stage, current: Layer | None) -> Layer | None:
        """`email to=<address> [subject=…] [body=…] [attach=<file>]` — send an email
        via SMTP (config + credentials from the environment). Pass-through."""
        from ..utilities import send_email

        opts = stage.options
        to = opts.get("to") or (stage.args[0] if stage.args else None)
        recipient = send_email(
            to=to, subject=opts.get("subject", ""), body=opts.get("body", ""),
            attach=os.path.expanduser(opts["attach"]) if opts.get("attach") else None,
        )
        self._emit(f"  emailed → {recipient}")
        return current

    # The geometry kinds `split` understands → the native:filterbygeometry output sink.
    _SPLIT_SINKS = {"point": "POINTS", "points": "POINTS", "line": "LINES",
                    "lines": "LINES", "polygon": "POLYGONS", "polygons": "POLYGONS"}

    def _split(self, stage, current: Layer | None) -> Layer | None:
        """`split <point|line|polygon>` — keep only the features of one geometry type
        (via native:filterbygeometry), so a mixed-geometry layer can be separated and
        each type processed on its own. Pipe-friendly: one type out per call, e.g.
        `load mixed.gpkg | split line | save lines.gpkg`. Note: whole multipart
        features are preserved; `GeometryCollection` features are not decomposed by
        this filter (they route to none of the single-type sinks)."""
        if current is None:
            raise FlowError("`split` needs an input layer — load one first",
                            line=stage.line, stage=stage.raw)
        if len(stage.args) != 1 or stage.options:
            raise FlowError("`split` takes one geometry type: `split <point|line|polygon>`",
                            line=stage.line, stage=stage.raw)
        kind = stage.args[0].lower()
        sink = self._SPLIT_SINKS.get(kind)
        if sink is None:
            raise FlowError(
                f"`split` geometry type must be point, line or polygon (got `{stage.args[0]}`)",
                line=stage.line, stage=stage.raw)
        self._pending_call = self.backend.render_call(
            "native:filterbygeometry", {}, input_param="INPUT",
            input_layer=current, output_param=sink)
        return self.backend.run(
            "native:filterbygeometry", {}, input_param="INPUT",
            input_layer=current, output_param=sink,
            progress=self.progress, cancel=self.cancel)

    def _catalog(self, stage) -> Layer | None:
        """`catalog <dir> [to=<out.md>]` — recurse a directory, inventory every
        geospatial dataset found (CRS, extent, geometry/fields or raster bands), and
        write a Markdown report. Terminal: produces a report, not a pipeable layer."""
        from ..utilities import CATALOG_MULTILAYER_EXTS, facet_for_ext, format_catalog

        if not stage.args:
            raise FlowError("catalog needs a directory: `catalog <dir> [to=out.md]`",
                            line=stage.line, stage=stage.raw)
        root = os.path.expanduser(stage.args[0])
        if not os.path.isdir(root):
            raise FlowError(f"catalog: not a directory: {root}",
                            line=stage.line, stage=stage.raw)
        out = stage.options.get("to")
        out = os.path.expanduser(out) if out else os.path.join(root, "catalog.md")

        entries = []
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                ext = os.path.splitext(fn)[1]
                facet = facet_for_ext(ext)
                if facet is None:
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root)
                # A multi-layer container (GeoPackage, …) becomes one entry per layer.
                targets = [(rel, path)]
                if facet == "vector" and ext.lower() in CATALOG_MULTILAYER_EXTS:
                    names = self.backend.sublayers(path)
                    if names:
                        targets = [(f"{rel} :: {n}", f"{path}|layername={n}") for n in names]
                for display, source in targets:
                    try:
                        layer = self.backend.load(source, facet=facet)
                        entries.append((display, facet, self.backend.profile(layer), None))
                    except Exception as exc:  # unreadable / locked / unsupported — note it
                        entries.append((display, facet, None, str(exc)))
                    self._emit(f"  catalog: {display}")

        report = format_catalog(root, entries)
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(report)
        self._emit(f"  catalogued {len(entries)} dataset(s) → {out}")
        return None  # terminal

    def _expand_value(self, value: str, stage):
        """A `run` option value, with **`~` and glob expansion**. A `;`-joined value
        is a list (QGIS's layer separator); a path segment containing `*`/`?`/`[` is
        globbed (relative to the flow's directory) into the sorted matching files — so
        `INPUT="tiles/*.jp2"` reaches every tile without listing them. A glob that
        matches nothing is a clear error. Non-path values (e.g. an expression with `*`)
        are left alone."""
        base = getattr(self, "_base_dir", None) or os.getcwd()
        items, globbed = [], False
        for seg in (s.strip() for s in value.split(";") if s.strip()):
            seg = os.path.expanduser(seg)
            is_path_glob = any(c in seg for c in "*?[") and ("/" in seg or os.sep in seg or " " not in seg)
            if is_path_glob:
                pattern = seg if os.path.isabs(seg) else os.path.join(base, seg)
                matches = sorted(glob.glob(pattern))
                if not matches:
                    raise FlowError(f"no files match `{seg}`", line=stage.line, stage=stage.raw)
                items.extend(matches)
                globbed = True
            else:
                items.append(_scalar(seg))
        if globbed or len(items) > 1:
            return items
        return items[0] if items else value

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


def _safe_name(name: str) -> str:
    """Make a batch item name safe to drop into a file path (`{name}` template)."""
    out = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name)
    return out.strip("._") or "item"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _human_time() -> str:
    """A friendly local timestamp for output/notifications: ``YYYY-MM-DD HH:MM:SS``
    (no ``T``/timezone clutter, unlike the ISO form used in the machine journal)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_elapsed(seconds: float) -> str:
    """Human elapsed time: '450 ms', '3.2 s', or '1m 05s'."""
    if seconds < 1:
        return f"{round(seconds * 1000)} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


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
            "- **Type:** raster",
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
