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
from .connections import is_connection_ref, parse_connection_ref, resolve_connection_name
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

    def _emit_report(self, report: str, *, to: str | None, label: str) -> None:
        """The ONE way every report verb (`show`/`info`/`describe`, and any future one)
        emits its human-readable text, so they all behave identically:

        - ``to=<file>`` → write the report there (creating parent dirs) and emit a single
          ``  {label} → {path}`` status line (which itself routes to the dock/CLI like any
          other status). Use this to capture a reply in a text file from the CLI.
        - no ``to`` **and** a progress callback set (the plugin, or a `niva` flow run) →
          stream the report into the dock's output panel line-by-line via :meth:`_emit`.
        - no ``to`` **and** no progress callback (a bare ``niva.flow(...)``) → print to
          stdout, so the report stays pipeable / shell-redirectable.

        ``self.progress is not None`` is the reliable "inside a plugin/flow run" signal —
        the plugin always passes ``progress=self.message.emit`` and the CLI a stderr sink.
        """
        if to:
            to = os.path.expanduser(to)
            parent = os.path.dirname(to)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(to, "w", encoding="utf-8") as fh:
                fh.write(report if report.endswith("\n") else report + "\n")
            self._emit(f"  {label} → {to}")
        elif self.progress is not None:
            for line in report.splitlines():
                self._emit(line)
        else:
            print(report)

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
        # `each "<glob>" | remove` is the one batch that deletes rather than transforms — it
        # needs the item *path*, not a loaded layer, so it gets a dedicated no-load path that
        # de-duplicates by file (a multi-layer container expands to many items, one file).
        if len(rest) == 1 and rest[0].verb == "remove":
            return self._run_each_remove(each_stage, rest[0], items)
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

    def _run_each_remove(self, each_stage, remove_stage, items) -> None:
        """`each "<glob>" | remove [force] [-dryrun]` — delete each batched file once. Items
        are de-duplicated by file path (so a multi-layer GeoPackage, which `each` expands to one
        item per layer, is deleted a single time), and no layer is loaded. A refusal (e.g. a
        type that needs `force`) propagates — it would apply to every item the same way."""
        self._emit(f"▶ {each_stage.raw}  → {len(items)} item(s)")
        if self.journal is not None:
            self.journal.record(text=each_stage.raw, kind="each",
                                summary=f"remove {len(items)} item(s)")
        seen, done = set(), 0
        for name, uri in items:
            path = uri.split("|layername=")[0]  # the container/file, not the layer
            if path in seen:
                continue
            seen.add(path)
            self._remove(remove_stage, batch_path=path)
            done += 1
        self._emit(f"  batch done: {done} file(s)")
        return None

    def _resolve_each(self, stage) -> list:
        """Resolve `each <source>` to an ordered list of (name, load-uri): a glob of
        files, a directory (recursed), or a single file. Multi-layer containers
        (GeoPackages) expand to one item per layer."""
        if not stage.args:
            raise FlowError('`each` needs a source: `each "<dir>"`, `each "<glob>"`, '
                            "or `each <file.gpkg>`", line=stage.line, stage=stage.raw)
        items = self._resolve_sources(stage.args[0], verb="each",
                                      line=stage.line, raw=stage.raw)
        if not items:
            raise FlowError(f"`each`: no geospatial datasets found in `{stage.args[0]}`",
                            line=stage.line, stage=stage.raw)
        return items

    def _resolve_sources(self, source: str, *, verb: str, line: int, raw: str) -> list:
        """Resolve a directory / glob / file ``source`` to ordered (name, load-uri) items,
        expanding a multi-layer container (GeoPackage) to one item per layer. Shared by
        `each` and `project new` (``verb`` only labels the errors)."""
        from ..utilities import CATALOG_MULTILAYER_EXTS, facet_for_ext

        src = os.path.expanduser(source)
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

        if any(c in src for c in "*?["):  # glob pattern
            matches = sorted(glob.glob(src))
            if not matches:
                raise FlowError(f"`{verb}`: no files match `{source}`", line=line, stage=raw)
            for m in matches:
                if os.path.isfile(m):
                    add(m)
        elif os.path.isdir(src):  # recurse a directory
            for dirpath, _dirs, files in os.walk(src):
                for fn in sorted(files):
                    add(os.path.join(dirpath, fn))
        elif os.path.isfile(src):  # a single file (maybe multi-layer)
            add(src)
        else:
            raise FlowError(f"`{verb}`: no such file or directory: {src}", line=line, stage=raw)
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

    # Built-in verbs — everything not backed by the alias registry. One entry per verb:
    # the adapter hands each handler exactly the context it needs (the piped `current`
    # layer, and the `lineage` accumulated so far). Adding a built-in verb is one line
    # here plus its `_<verb>` method — see docs/planning/16-anatomy-of-a-verb.md.
    #
    # OUTPUT ROUTING — every verb's text reaches the dock and the CLI the SAME way:
    #   - Report verbs (show, info, describe, search, docs) call
    #     `self._emit_report(report, to=…, label=…)` — the single helper that writes to a
    #     `to=<file>`, else streams to the dock (progress set), else prints to stdout. They
    #     all behave identically by construction.
    #   - Verbs that always write to a file (catalog, assess, project info) and action verbs
    #     (style, metadata, notify, email, remove) call `self._emit(line)` for their
    #     "<did this> → <path>" status, so it shows in the dock and the CLI alike.
    #   - Transform verbs return a Layer; the plugin shows it via the final-run summary.
    _BUILTIN_VERBS = {
        "load":     lambda self, stage, current, lineage: self._load(stage),
        "save":     lambda self, stage, current, lineage: self._save(stage, current, lineage),
        "sql":      lambda self, stage, current, lineage: self._sql(stage),
        "metadata": lambda self, stage, current, lineage: self._metadata(stage, current),
        "assess":   lambda self, stage, current, lineage: self._assess(stage, current),
        "run":      lambda self, stage, current, lineage: self._run_raw(stage, current),
        "notify":   lambda self, stage, current, lineage: self._notify(stage, current),
        "email":    lambda self, stage, current, lineage: self._email(stage, current),
        "catalog":  lambda self, stage, current, lineage: self._catalog(stage),
        "show":     lambda self, stage, current, lineage: self._show(stage),
        "info":     lambda self, stage, current, lineage: self._info(stage),
        "describe": lambda self, stage, current, lineage: self._describe(stage),
        "search":   lambda self, stage, current, lineage: self._search(stage),
        "docs":     lambda self, stage, current, lineage: self._docs(stage),
        "project":  lambda self, stage, current, lineage: self._project(stage),
        "style":    lambda self, stage, current, lineage: self._style(stage, current),
        "split":    lambda self, stage, current, lineage: self._split(stage, current),
        "remove":   lambda self, stage, current, lineage: self._remove(stage),
    }

    def _run_stage(self, stage, current: Layer | None, lineage: list) -> Layer | None:
        self._pending_call = None  # set only when this stage actually runs an algorithm
        if hasattr(self.backend, "_note"):
            self.backend._note = None  # a per-op handling notice (e.g. mixed geometry)
        verb = stage.verb
        handler = self._BUILTIN_VERBS.get(verb)
        if handler is not None:
            return handler(self, stage, current, lineage)
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
        self._resolve_layer_refs(op, stage)  # turn @conn.table secondary layers into layers
        self._validate_crs_params(op, stage)  # fail closed on an unknown CRS, never silently
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
                conn, schema, table = parse_connection_ref(
                    source, self.backend.connection_names())
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
        conn, schema, table = parse_connection_ref(ref, self.backend.connection_names())
        if schema or table:
            raise FlowError(
                f"`sql` takes a bare connection `@{conn}`, not a table reference (`{ref}`)",
                line=stage.line, stage=stage.raw,
            )
        # SELECT-style queries return a layer to pipe; everything else (DDL/DML) runs
        # server-side as a terminal step. `CREATE TABLE … AS SELECT …` reads as a write
        # (leading `CREATE`); `WITH … SELECT …` reads as a query (leading `WITH`).
        if _is_query(query):
            return self.backend.run_sql(conn, query)
        self.backend.execute_sql(conn, query)
        return None

    def _save(self, stage, current: Layer | None, lineage: list) -> Layer:
        if current is None:
            raise FlowError(
                "`save` has nothing to save — the flow has not loaded a layer yet",
                line=stage.line, stage=stage.raw,
            )
        if stage.args and is_connection_ref(stage.args[0]):
            return self._save_to_db(stage, current, lineage)
        if stage.options:
            if "mode" in stage.options:
                raise FlowError(
                    "`mode=` (create/replace/append) only applies to a **database** target — "
                    "`save @conn.table mode=append`. To add a layer to a GeoPackage/SpatiaLite "
                    "container, use `save <file> as <layer>` (writing a named layer into an "
                    "existing container appends it).",
                    line=stage.line, stage=stage.raw,
                )
            raise FlowError(
                "`save` takes no key=value options for a file — `save <path>`, "
                "`save <path> as <layer>`, or a database target "
                "`save @conn.table [mode=create|replace|append]`",
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
        parent = os.path.dirname(dest)  # create the target folder if it doesn't exist yet
        if parent and not os.path.isdir(parent):  # also covers the first item of a batch
            os.makedirs(parent, exist_ok=True)     # save into one container (append=True)
        return self.backend.save(current, dest, lineage=lineage,
                                 layer_name=layer_name, append=append)

    def _save_to_db(self, stage, current: Layer, lineage: list) -> Layer:
        # `save @conn[.schema].table [mode=create|replace|append]` — write the current
        # layer into a database table. Credentials stay in QGIS; the flow passes only
        # the connection name. Write is fail-closed: `create` errors if the table
        # already exists (12-security-model §3 — no silent overwrite).
        ref = stage.args[0]
        if len(stage.args) != 1:
            raise FlowError(
                "a database save takes just `save @conn.table` (with an optional "
                "`mode=`) — `as <layer>` is for file containers only",
                line=stage.line, stage=stage.raw,
            )
        if "{name}" in ref:
            raise FlowError(
                "`{name}` templating works on file paths, not `@conn` targets — in a "
                "batch, `save @conn` names the table after each item",
                line=stage.line, stage=stage.raw,
            )
        try:
            conn, schema, table = parse_connection_ref(
                ref, self.backend.connection_names())
        except ValueError as exc:
            raise FlowError(f"`save`: {exc}", line=stage.line, stage=stage.raw)

        batch = self._batch_item
        if batch:
            # In a batch the table is named after each item, so a single trailing
            # qualifier is the *schema* to write the tables into (not a table name):
            # `each "NiagaraBasemap/" | … | save @pg.niagara` → one table per layer in
            # schema `niagara`; bare `save @pg` → the provider's default schema. A
            # three-part `@conn.schema.table` would name one table — not allowed when
            # there's one table per item.
            if schema is not None:  # @conn.schema.table
                raise FlowError(
                    "a batch (`each`) save writes one table per item — drop the table "
                    f"name and use `save @conn` or `save @conn.<schema>` (got `{ref}`)",
                    line=stage.line, stage=stage.raw,
                )
            schema = table  # the 2-part trailing component, or None for bare `@conn`
            table = _safe_name(batch)
        elif table is None:  # bare `@conn` outside a batch
            raise FlowError(
                f"`save @conn.table` needs a table name — `{ref}` is a bare connection",
                line=stage.line, stage=stage.raw,
            )

        mode = "create"
        for key, value in stage.options.items():
            if key != "mode":
                raise FlowError(
                    f"a database save takes only `mode=` — got `{key}=`",
                    line=stage.line, stage=stage.raw,
                )
            mode = value
        if mode not in ("create", "replace", "append"):
            raise FlowError(
                f"`mode={mode}` is not valid — use create, replace, or append",
                line=stage.line, stage=stage.raw,
            )

        if current.facet == "raster":
            raise FlowError(
                "saving rasters to a database is not supported — use a file target",
                line=stage.line, stage=stage.raw,
            )
        return self.backend.save_table(current, conn, schema, table,
                                       mode=mode, lineage=lineage)

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
        layer = self.backend.set_metadata(current, dict(stage.options))
        self._emit(f"  metadata set: {', '.join(sorted(stage.options))} "
                   "(persisted on next save)")  # confirm the action in the dock/CLI
        return layer

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
        self._emit(f"  assessment → {dest}")  # so the dock/CLI shows where the report went
        return current

    def _remove(self, stage, batch_path: str | None = None) -> None:
        """`remove <path> [force] [-dryrun]` — delete a file output and its sidecar family,
        behind a strict safety gate (see docs/planning/18). Terminal: returns nothing
        downstream. In an `each` batch it deletes the current item's file (``batch_path``).
        Every refused gate raises a `FlowError` with a specific, actionable message — and
        nothing is deleted unless every check passes (fail-closed)."""
        from .. import remove_policy as rp

        force = dryrun = False
        paths: list[str] = []
        for arg in stage.args:
            flag = arg.lstrip("-").lower()
            if flag == "force":
                force = True
            elif flag in ("dryrun", "dry-run"):
                dryrun = True
            else:
                paths.append(arg)
        if stage.options:
            raise FlowError(
                "`remove` takes no key=value options — `remove <path> [force] [-dryrun]`",
                line=stage.line, stage=stage.raw,
            )

        if batch_path is not None:
            if paths:
                raise FlowError(
                    "`remove` after `each` deletes each batched item — don't also name a path "
                    f"(`{paths[0]}`); write `each \"<glob>\" | remove`",
                    line=stage.line, stage=stage.raw,
                )
            target = batch_path
        elif len(paths) != 1:
            raise FlowError(
                "`remove` needs exactly one path — `remove <file>` "
                '(to delete many, batch with `each "<glob>" | remove`)',
                line=stage.line, stage=stage.raw,
            )
        else:
            target = paths[0]

        # --- the safety gate, in order, each refusal a specific message --------------------
        if rp.is_conn_ref(target):
            raise FlowError(
                f"`remove` deletes files only — `{target}` is a database reference. "
                'To drop a table use `sql @conn "DROP TABLE <name>"`.',
                line=stage.line, stage=stage.raw,
            )
        if rp.is_glob(target):
            raise FlowError(
                f"`remove` won't expand a glob (`{target}`). Batch it so each file is checked "
                'individually: `each "<glob>" | remove`.',
                line=stage.line, stage=stage.raw,
            )
        path = os.path.abspath(os.path.expanduser(target))
        if os.path.isdir(path):
            raise FlowError(
                f"`remove` deletes files, not directories (`{target}` is a folder). "
                'Name a file, or batch its contents with `each "<dir>" | remove`.',
                line=stage.line, stage=stage.raw,
            )
        forced_ext = False
        if not rp.on_allowlist(path):
            if not force:
                raise FlowError(
                    f"`remove` won't delete `{os.path.basename(path)}` — `{rp.ext_of(path) or '(no extension)'}` "
                    f"isn't a recognised geodata/niva output type. Allowed → {rp.ALLOWLIST_STR}. "
                    "Add `force` to delete this one file anyway.",
                    line=stage.line, stage=stage.raw,
                )
            forced_ext = True

        # --- resolve the concrete files ----------------------------------------------------
        if not os.path.exists(path):  # idempotent: a cleanup verb must be safe to re-run
            self._emit(f"  remove: {target} already absent")
            if self.journal is not None:
                self.journal.record(text=stage.raw, kind="remove", summary="already absent")
            return None
        candidates = [path] if forced_ext else [path, *rp.family(path)]
        existing = [p for p in candidates if os.path.isfile(p)]
        sidecars = len(existing) - 1

        if dryrun:
            shown = ", ".join(os.path.basename(p) for p in existing)
            self._emit(f"  remove -dryrun: would delete {len(existing)} file(s) — {shown}")
            if self.journal is not None:
                self.journal.record(text=stage.raw, kind="remove",
                                    summary=f"dryrun: {len(existing)} file(s)")
            return None

        freed = 0
        for p in existing:
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except FileNotFoundError:
                pass
            except OSError as exc:  # permission / I/O — fail closed, name the file
                raise OpError(
                    f"`remove` could not delete `{p}`: {exc}",
                    algorithm="remove", params={"path": p}, backend="filesystem",
                ) from exc
        extra = f" (+{sidecars} sidecar{'s' if sidecars != 1 else ''})" if sidecars > 0 else ""
        self._emit(f"  removed {target}{extra} — {freed} bytes freed")
        if self.journal is not None:
            self.journal.record(text=stage.raw, kind="remove",
                                summary=f"{len(existing)} file(s), {freed} bytes")
        return None

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

    # `show` ignores these when scanning a directory: dataset sidecars (a shapefile's
    # `.dbf`/`.shx`/…, style/aux files) and obviously-non-geospatial files (code, docs,
    # images, archives). Everything else is probed via the backend, which returns no layers
    # for a file QGIS can't read — so any *readable* dataset is listed regardless of format.
    _SHOW_SKIP_EXTS = frozenset({
        ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx", ".sbx", ".idx", ".ovr",
        ".qml", ".qmd", ".qlr", ".lyr", ".vat", ".cpg", ".aux",
        ".py", ".pyc", ".md", ".rst", ".txt", ".log", ".html", ".htm", ".pdf", ".png",
        ".jpg", ".jpeg", ".gif", ".svg", ".zip", ".gz", ".tar", ".7z", ".rar", ".bz2",
        ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".bat", ".c", ".h", ".cpp", ".o",
    })
    # Formats whose "file" is actually a directory — treated as a container, not descended.
    _SHOW_DIR_DATASETS = frozenset({".gdb", ".gpkg.zip"})

    def _show(self, stage) -> Layer | None:
        """`show <path|@conn[.schema[.table]]> [deep] [to=<out.md>]` — list the loadable
        layers or tables at one location (a file/container, a directory, or a database
        connection), with each layer's kind, geometry/raster type, file type or provider,
        and a copy-pasteable `load` source. Terminal: a quick "what can I load here?" glance
        (no feature counts or deep profiling — that's `catalog`). A directory is listed
        shallowly by default; add the `deep` flag to recurse. Any QGIS-readable format is
        picked up (the backend probes each file). Defers remote services (WFS/WMS)."""
        from ..utilities import format_show

        flags = {a for a in stage.args if a in ("deep", "recursive")}
        locations = [a for a in stage.args if a not in ("deep", "recursive")]
        if len(locations) != 1:
            raise FlowError(
                "show needs one location: `show <path|@conn[.schema]> [deep]` [to=<out.md>]",
                line=stage.line, stage=stage.raw,
            )
        unknown = set(stage.options) - {"to"}
        if unknown:
            raise FlowError(f"`show`: unknown option(s) {', '.join(sorted(unknown))} — "
                            "only `to=<out.md>` is accepted",
                            line=stage.line, stage=stage.raw)
        target = locations[0]
        deep = bool(flags)
        is_db = False

        from ..remote import is_service_url

        is_service = False
        if is_connection_ref(target):
            is_db = True
            conn, schema, table = self._resolve_show_connection(target, stage)
            entries = self.backend.list_tables(conn, schema, table, warn=self._emit)
            label = target
        elif is_service_url(target):
            is_service = True
            label = target
            try:
                entries = self.backend.list_service(target)
            except Exception as exc:  # network / parse / unsupported — a clear flow error
                raise FlowError(f"show: could not list service `{target}`: {exc}",
                                line=stage.line, stage=stage.raw)
        else:
            path = os.path.expanduser(target)
            label = path
            if os.path.isdir(path) and os.path.splitext(path)[1].lower() \
                    not in self._SHOW_DIR_DATASETS:
                entries = self._show_walk(path, deep)
            elif os.path.exists(path):
                entries = self._show_probe(path)  # a file, or a directory-dataset (.gdb)
            else:
                raise FlowError(f"show: no such file, directory, or connection: {target}",
                                line=stage.line, stage=stage.raw)

        report = format_show(label, entries, is_db=is_db, is_service=is_service)
        self._emit_report(report, to=stage.options.get("to"),
                          label=f"listed {len(entries)} item(s)")
        return None  # terminal

    def _resolve_show_connection(self, target, stage):
        """Split `show @ref` into ``(conn, schema, table)`` via the shared
        :func:`resolve_connection_name` (longest registered dotted prefix, so a name
        containing dots like `actual_spatialite.sqlite` works). Under the *listing* grammar
        the components after the connection name are a scope: one trailing part is a schema,
        two are schema + table. Bare `@conn` lists every table."""
        try:
            conn, rest = resolve_connection_name(
                target, self.backend.connection_names())
        except ValueError as exc:
            raise FlowError(f"show: {exc}", line=stage.line, stage=stage.raw)
        schema = rest[0] if len(rest) >= 1 else None
        table = ".".join(rest[1:]) if len(rest) >= 2 else None
        return conn, schema, table

    def _show_probe(self, full):
        """List the layers in one file/container, defensively — an unreadable file just
        contributes nothing (so probing a whole directory never aborts on one bad file)."""
        try:
            rows = self.backend.list_layers(full)
        except Exception as exc:  # noqa: BLE001
            self._emit(f"  show: skipped {os.path.basename(full)}: {exc}")
            return []
        if rows:
            self._emit(f"  show: {os.path.basename(full)} ({len(rows)})")
        return rows

    def _show_walk(self, root, deep):
        """Collect `show` entries under ``root``. Shallow by default; ``deep`` recurses.
        Directory-based datasets (FileGDB ``.gdb``, …) are listed as containers but not
        descended into; sidecar and obviously-non-geospatial files are skipped; every other
        file is probed, so any QGIS-readable format is picked up regardless of extension."""
        entries = []
        for dirpath, dirnames, filenames in os.walk(root):
            # A directory-dataset (.gdb) is a container: list it, don't walk into it.
            keep = []
            for d in sorted(dirnames):
                if os.path.splitext(d)[1].lower() in self._SHOW_DIR_DATASETS:
                    entries.extend(self._show_probe(os.path.join(dirpath, d)))
                else:
                    keep.append(d)
            dirnames[:] = keep if deep else []  # shallow ⇒ don't descend
            for fn in sorted(filenames):
                ext = os.path.splitext(fn)[1].lower()
                if ext in self._SHOW_SKIP_EXTS or fn.lower().endswith(".aux.xml"):
                    continue
                entries.extend(self._show_probe(os.path.join(dirpath, fn)))
        return entries

    def _info(self, stage) -> Layer | None:
        """`info [to=<report.md>]` — inspect the local QGIS environment and report the
        details a CLI user needs before writing a flow (the registered database
        connection names — the valid `@conn` references — plus providers, the reachable
        algorithm count, versions, and the niva environment variables, secrets masked).
        With `to=`, write the Markdown to a file; otherwise print it to stdout. Terminal:
        inspects the *environment* (distinct from `project info`, which inventories a
        project file). The CLI counterpart of the plugin's Setup-tab Environment report."""
        if stage.args:
            raise FlowError(
                "`info` inspects the QGIS environment and takes no input — "
                "just `info [to=<report.md>]` (for a project file, use `project info <src>`)",
                line=stage.line, stage=stage.raw,
            )
        unknown = set(stage.options) - {"to"}
        if unknown:
            raise FlowError(f"`info`: unknown option(s) {', '.join(sorted(unknown))} — "
                            "only `to=<report.md>` is accepted",
                            line=stage.line, stage=stage.raw)
        report = self.backend.environment_report()
        self._emit_report(report, to=stage.options.get("to"), label="environment report")
        return None  # terminal

    def _describe(self, stage) -> Layer | None:
        """`describe <verb|algorithm-id> [to=<report.md>]` — show how a niva verb maps to
        its QGIS algorithm (positional args, options, flags), or introspect a live
        algorithm by id (anything containing `:`). Terminal: returns no pipeable layer.

        The in-flow / plugin counterpart of the `niva describe` CLI subcommand, so the
        same introspection is reachable inside a flow and streams into the dock's output
        panel (the issue that `describe` produced nothing in the plugin). Routing mirrors
        `show`/`info`: with `to=<file>` write the report there; otherwise stream it to the
        dock (progress set) or print to stdout for the CLI (pipeable / redirectable)."""
        unknown = set(stage.options) - {"to"}
        if len(stage.args) != 1 or unknown:
            raise FlowError(
                "`describe` takes one verb or algorithm id (plus optional `to=<file>`): "
                "`describe buffer` or `describe native:buffer to=buffer.md`",
                line=stage.line, stage=stage.raw,
            )
        from ..describe import describe as describe_report

        report = describe_report(stage.args[0])
        self._emit_report(report, to=stage.options.get("to"), label="description")
        return None  # terminal

    def _discovery_keyword(self, stage, verb: str) -> str:
        """Validate `search`/`docs`: exactly one keyword arg, only `to=` allowed."""
        unknown = set(stage.options) - {"to"}
        if len(stage.args) != 1 or unknown:
            raise FlowError(
                f"`{verb}` takes one keyword (plus optional `to=<file>`): "
                f'`{verb} buffer` or `{verb} "raster reproject" to=out.md`',
                line=stage.line, stage=stage.raw,
            )
        return stage.args[0]

    def _search(self, stage) -> Layer | None:
        """`search <keyword> [to=<file>]` — fuzzy-find niva verbs and QGIS algorithms by
        keyword (matched against name, summary, options, and the algorithm id/group/
        description). Lists the ranked matches; run `describe`/`docs` for the detail.
        Terminal report verb (routes via _emit_report)."""
        keyword = self._discovery_keyword(stage, "search")
        from ..search import format_results, search

        hits = search(keyword, algorithms=self.backend.algorithm_catalog())
        self._emit_report(format_results(keyword, hits), to=stage.options.get("to"),
                          label=f"{len(hits)} match(es)")
        return None  # terminal

    def _docs(self, stage) -> Layer | None:
        """`docs <keyword> [to=<file>]` — fuzzy-search, then emit the FULL `describe`
        (args, options, flags, example) for every match: a made-to-order mini-guide for
        whatever you're doing in the moment. `to=<file>` saves it. Terminal report verb."""
        keyword = self._discovery_keyword(stage, "docs")
        from ..describe import describe as describe_report
        from ..search import format_docs, search

        hits = search(keyword, algorithms=self.backend.algorithm_catalog())
        self._emit_report(format_docs(keyword, hits, describe_report),
                          to=stage.options.get("to"), label=f"docs for {len(hits)} match(es)")
        return None  # terminal

    def _project(self, stage) -> Layer | None:
        """`project <src.qgs|qgz> to=<out.qgs|qgz> repoint=<target> [missing=fail|keep|drop]`
        — copy a QGIS project and repoint its vector layers' datasources to a new home
        (a GeoPackage path or an `@conn[.schema]` database connection), matched by layer
        name with subset filters preserved. Terminal: writes a project file, returns no
        pipeable layer (roadmap §"project & layer file manipulation")."""
        if stage.args and stage.args[0] == "new":
            return self._project_new(stage)
        if stage.args and stage.args[0] == "info":
            return self._project_info(stage)
        if "from-template" in stage.options:
            return self._project_from_template(stage)
        if "to-template" in stage.options:
            return self._project_to_template(stage)
        if len(stage.args) != 1:
            raise FlowError(
                "`project` takes one source project — "
                "`project <src.qgs> to=<out.qgs> repoint=<target>`",
                line=stage.line, stage=stage.raw)
        src = os.path.expanduser(stage.args[0])
        if not os.path.isfile(src):
            raise FlowError(f"`project`: not a file: {src}", line=stage.line, stage=stage.raw)
        if os.path.splitext(src)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project` reads a QGIS project (.qgs/.qgz) — `{src}` is not one",
                            line=stage.line, stage=stage.raw)

        known = ("to", "repoint", "missing", "rasters", "paths",
                 "bookmark", "at", "scale", "width")
        extra = [k for k in stage.options if k not in known]
        if extra:
            raise FlowError(
                "`project` takes `to=`, `repoint=`, `missing=`, `rasters=`, `paths=`, "
                f"`bookmark=` (+ `at=`/`scale=`/`width=`) — got `{extra[0]}=`",
                line=stage.line, stage=stage.raw)
        out = stage.options.get("to")
        target = stage.options.get("repoint")  # optional: omit to copy/convert without repointing
        missing = stage.options.get("missing", "fail")
        rasters = stage.options.get("rasters")
        paths = stage.options.get("paths")
        bookmark = self._parse_bookmark(stage)
        if not out:
            raise FlowError("`project` needs an output: `to=<out.qgs>`",
                            line=stage.line, stage=stage.raw)
        if missing not in ("fail", "keep", "drop"):
            raise FlowError(f"`missing={missing}` is not valid — use fail, keep, or drop",
                            line=stage.line, stage=stage.raw)
        if paths is not None and paths not in ("relative", "absolute"):
            raise FlowError(f"`paths={paths}` is not valid — use relative or absolute",
                            line=stage.line, stage=stage.raw)
        out = os.path.expanduser(out)
        if os.path.splitext(out)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project` writes a .qgs or .qgz — `{out}` is neither",
                            line=stage.line, stage=stage.raw)
        if rasters:
            rasters = os.path.expanduser(rasters)
            if not os.path.isdir(rasters):
                raise FlowError(f"`project` rasters= must be a directory — `{rasters}` is not one",
                                line=stage.line, stage=stage.raw)
        # A connection target (@conn[.schema]) is passed through; a file target is expanded.
        if target and not is_connection_ref(target):
            target = os.path.expanduser(target)
        self.backend.repoint_project(src, out, target=target, missing=missing,
                                     rasters=rasters, paths=paths, bookmark=bookmark,
                                     progress=self._emit)
        return None  # terminal

    def _style(self, stage, current: Layer | None) -> Layer | None:
        """`style apply <file>` / `style save <file>` — apply a `.qml` (symbology) or
        `.qmd` (metadata) sidecar to the current layer, persisting it so QGIS picks it up;
        or save the current layer's style/metadata to a sidecar file. Pass-through, so it
        chains after `save`: `… | save out.gpkg | style apply house.qml`."""
        if current is None:
            raise FlowError("`style` operates on the loaded layer — load one first",
                            line=stage.line, stage=stage.raw)
        if stage.options or len(stage.args) != 2 or stage.args[0] not in ("apply", "save"):
            raise FlowError("`style` takes `style apply <file>` or `style save <file>` "
                            "(a .qml style or .qmd metadata sidecar)",
                            line=stage.line, stage=stage.raw)
        action = stage.args[0]
        path = os.path.expanduser(stage.args[1])
        ext = os.path.splitext(path)[1].lower()
        # `apply` reads a QGIS-native sidecar; `save` also exports SLD (interop) and QLR
        # (a portable layer-definition: datasource + style).
        allowed = (".qml", ".qmd", ".sld", ".qlr") if action == "save" else (".qml", ".qmd")
        if ext not in allowed:
            hint = (" — `.sld`/`.qlr` are export-only, use `style save`"
                    if action == "apply" and ext in (".sld", ".qlr") else "")
            raise FlowError(f"`style {action}` takes {', '.join(allowed)} — `{path}` is not one"
                            + hint, line=stage.line, stage=stage.raw)
        if action == "apply" and not os.path.isfile(path):
            raise FlowError(f"`style apply`: not a file: {path}",
                            line=stage.line, stage=stage.raw)
        self.backend.style_layer(current, action, path)
        verb = "applied" if action == "apply" else "saved"
        self._emit(f"  style {verb} → {path}")  # confirm the action in the dock/CLI
        return current  # pass-through

    # A QGIS bookmark stores an extent, not a centre+scale. So `scale=N` is converted to a
    # ground width via a reference on-screen map width (~0.5 m, a typical full-HD canvas) —
    # approximate, and CRS-unit dependent; use `width=` for an exact extent. (15-§project.)
    _BOOKMARK_SCALE_REF_M = 0.5

    def _parse_bookmark(self, stage):
        """Build the `bookmark` spec from the options: ``None``, or
        ``{name, at: (x,y)|None, width: float|None}``. A bare `bookmark=<name>` uses the
        project's union extent; `at=` + `scale=`/`width=` makes a centred bookmark."""
        name = stage.options.get("bookmark")
        at, scale, width = (stage.options.get(k) for k in ("at", "scale", "width"))
        if name is None:
            if at or scale or width:
                raise FlowError("`at=`/`scale=`/`width=` only apply with `bookmark=<name>`",
                                line=stage.line, stage=stage.raw)
            return None
        spec = {"name": name, "at": None, "width": None}
        if at is not None:
            try:
                x, y = (float(v) for v in at.split(","))
            except ValueError:
                raise FlowError(f'`at` must be "x,y" map coordinates — got `{at}`',
                                line=stage.line, stage=stage.raw)
            spec["at"] = (x, y)
            if scale and width:
                raise FlowError("give a centred bookmark `scale=` or `width=`, not both",
                                line=stage.line, stage=stage.raw)
            if width is not None:
                spec["width"] = self._bookmark_float(width, "width", stage)
            elif scale is not None:
                spec["width"] = (self._bookmark_float(scale, "scale", stage)
                                 * self._BOOKMARK_SCALE_REF_M)
            else:
                raise FlowError("a centred `bookmark` with `at=` needs `scale=` or `width=`",
                                line=stage.line, stage=stage.raw)
        elif scale or width:
            raise FlowError('`scale=`/`width=` need a centre `at="x,y"`',
                            line=stage.line, stage=stage.raw)
        return spec

    @staticmethod
    def _bookmark_float(value, what, stage):
        try:
            n = float(value)
        except ValueError:
            raise FlowError(f"`{what}` must be a number — got `{value}`",
                            line=stage.line, stage=stage.raw)
        if n <= 0:
            raise FlowError(f"`{what}` must be positive — got `{value}`",
                            line=stage.line, stage=stage.raw)
        return n

    def _project_new(self, stage) -> Layer | None:
        """`project new from=<dir|glob> to=<out.qgs|qgz> [crs=… title=…]` — create a fresh
        QGIS project that loads every layer found under `from=` (a directory, glob, or
        multi-layer container, like `each`). The complement to repointing: build a project
        for freshly compiled outputs without needing an existing one. Terminal."""
        if len(stage.args) != 1:  # just the `new` keyword
            raise FlowError("`project new` takes options only — "
                            "`project new from=<dir> to=<out.qgs> [crs= title=]`",
                            line=stage.line, stage=stage.raw)
        extra = [k for k in stage.options if k not in ("from", "to", "crs", "title")]
        if extra:
            raise FlowError(
                f"`project new` takes `from=`, `to=`, `crs=`, `title=` — got `{extra[0]}=`",
                line=stage.line, stage=stage.raw)
        source = stage.options.get("from")
        out = stage.options.get("to")
        if not source:
            raise FlowError("`project new` needs `from=<dir|glob>`",
                            line=stage.line, stage=stage.raw)
        if not out:
            raise FlowError("`project new` needs `to=<out.qgs>`",
                            line=stage.line, stage=stage.raw)
        out = os.path.expanduser(out)
        if os.path.splitext(out)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project new` writes a .qgs or .qgz — `{out}` is neither",
                            line=stage.line, stage=stage.raw)
        items = self._resolve_sources(source, verb="project new",
                                      line=stage.line, raw=stage.raw)
        if not items:
            raise FlowError(f"`project new`: no geospatial datasets found in `{source}`",
                            line=stage.line, stage=stage.raw)
        layers = [uri for _name, uri in items]
        self.backend.create_project(layers, out, crs=stage.options.get("crs"),
                                    title=stage.options.get("title"), progress=self._emit)
        return None  # terminal

    def _project_info(self, stage) -> Layer | None:
        """`project info <src.qgs|qgz> [to=<out.md>]` — inventory a project's layers
        (name, datasource, provider, CRS, validity) to a Markdown report. Terminal."""
        if len(stage.args) != 2:
            raise FlowError("`project info` takes one project — "
                            "`project info <src.qgs> [to=<out.md>]`",
                            line=stage.line, stage=stage.raw)
        src = os.path.expanduser(stage.args[1])
        if not os.path.isfile(src):
            raise FlowError(f"`project info`: not a file: {src}",
                            line=stage.line, stage=stage.raw)
        if os.path.splitext(src)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project info` reads a .qgs/.qgz — `{src}` is not one",
                            line=stage.line, stage=stage.raw)
        extra = [k for k in stage.options if k != "to"]
        if extra:
            raise FlowError(f"`project info` takes only `to=` — got `{extra[0]}=`",
                            line=stage.line, stage=stage.raw)
        out = stage.options.get("to")
        out = os.path.expanduser(out) if out else os.path.splitext(src)[0] + "_info.md"
        info = self.backend.read_project(src)
        report = _format_project_info(info, src)
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(report)
        self._emit(f"   project info → {out} ({len(info.get('layers', []))} layer(s))")
        return None  # terminal

    # Where named templates are looked up, in order: `$NIVA_TEMPLATES` (if set), the user
    # library `~/.niva/templates`, then the templates that ship inside the package (e.g.
    # `example`). A template is just a saved QGIS project — register an existing one by name
    # with `project to-template=<name> from=<project>`.
    _TEMPLATES_ENV = "NIVA_TEMPLATES"
    _TEMPLATES_USER = "~/.niva/templates"
    _TEMPLATES_BUNDLED = os.path.join(os.path.dirname(__file__), os.pardir, "templates")

    def _template_roots(self) -> list:
        """The ordered directories searched for a named template: env override first, then
        the user library, then the bundled templates — so a `$NIVA_TEMPLATES` or user entry
        shadows a bundled one of the same name."""
        roots = []
        env = os.environ.get(self._TEMPLATES_ENV)
        if env:
            roots.append(os.path.expanduser(env))
        roots.append(os.path.expanduser(self._TEMPLATES_USER))
        roots.append(os.path.normpath(self._TEMPLATES_BUNDLED))
        return roots

    def _template_library(self) -> str:
        """The directory a `to-template=<name>` registration writes into: `$NIVA_TEMPLATES`
        if set, else the user library `~/.niva/templates`."""
        return self._template_roots()[0]

    def _project_from_template(self, stage) -> Layer | None:
        """`project from-template=<name|path> to=<out.qgs|qgz> data=<dir|glob> [missing=keep|fail|drop]`
        — instantiate a stock QGIS template against your own data. A template is a curated
        `.qgz`/`.qgs` carrying print layouts and styled layer *slots*; niva copies it and
        repoints each slot (vector or raster) to the same-named dataset found under `data=`,
        so the symbology and layouts ride along. The template can be **any existing QGIS
        project** — pass its `.qgs`/`.qgz` path directly — or a name registered in
        `$NIVA_TEMPLATES` / the user library `~/.niva/templates` (see `project to-template`).
        Unmatched slots follow `missing=` (default `keep`, to preserve layout structure).
        Terminal."""
        extra = [k for k in stage.options if k not in ("from-template", "to", "data", "missing")]
        if stage.args or extra:
            bad = f"`{extra[0]}=`" if extra else f"`{stage.args[0]}`"
            raise FlowError(
                "`project from-template=` takes `to=`, `data=`, `missing=` only — "
                f"`project from-template=<name|path> to=<out.qgs> data=<dir|glob>` (got {bad})",
                line=stage.line, stage=stage.raw)
        template = self._resolve_template(stage.options["from-template"], stage)
        out = stage.options.get("to")
        data = stage.options.get("data")
        missing = stage.options.get("missing", "keep")
        if not out:
            raise FlowError("`project from-template` needs an output: `to=<out.qgs>`",
                            line=stage.line, stage=stage.raw)
        if not data:
            raise FlowError("`project from-template` needs `data=<dir|glob>` to fill the "
                            "template's layer slots", line=stage.line, stage=stage.raw)
        if missing not in ("fail", "keep", "drop"):
            raise FlowError(f"`missing={missing}` is not valid — use fail, keep, or drop",
                            line=stage.line, stage=stage.raw)
        out = os.path.expanduser(out)
        if os.path.splitext(out)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project from-template` writes a .qgs or .qgz — `{out}` is neither",
                            line=stage.line, stage=stage.raw)
        items = self._resolve_sources(data, verb="project from-template",
                                      line=stage.line, raw=stage.raw)
        if not items:
            raise FlowError(f"`project from-template`: no geospatial datasets found in `{data}`",
                            line=stage.line, stage=stage.raw)
        # name → load-uri; last wins on a duplicate slot name (a flat-dir convention).
        layer_map = {name: uri for name, uri in items}
        self.backend.repoint_project(template, out, target=layer_map, missing=missing,
                                     progress=self._emit)
        return None  # terminal

    def _project_to_template(self, stage) -> Layer | None:
        """`project to-template=<name|path> from=<src.qgs|qgz> [paths=relative|absolute]`
        — register an **existing** QGIS project as a reusable template. A template is just a
        saved project (its print layouts + styled layer slots), so this copies `from=` into
        the template library — `$NIVA_TEMPLATES` or `~/.niva/templates` when `to-template=` is
        a bare **name** (then `from-template=<name>` finds it), or to a **path** when it looks
        like one. `paths=relative` (recommended for a portable template) rewrites datasource
        path storage. The slots keep their current data as *example* data, repointed on
        instantiation. Terminal."""
        extra = [k for k in stage.options if k not in ("to-template", "from", "paths")]
        if stage.args or extra:
            bad = f"`{extra[0]}=`" if extra else f"`{stage.args[0]}`"
            raise FlowError(
                "`project to-template=` takes `from=`, `paths=` only — "
                f"`project to-template=<name|path> from=<src.qgs>` (got {bad})",
                line=stage.line, stage=stage.raw)
        src = stage.options.get("from")
        if not src:
            raise FlowError("`project to-template` needs the project to register: "
                            "`from=<src.qgs|qgz>`", line=stage.line, stage=stage.raw)
        src = os.path.expanduser(src)
        if not os.path.isfile(src):
            raise FlowError(f"`project to-template`: not a file: {src}",
                            line=stage.line, stage=stage.raw)
        if os.path.splitext(src)[1].lower() not in (".qgs", ".qgz"):
            raise FlowError(f"`project to-template` reads a .qgs/.qgz — `{src}` is not one",
                            line=stage.line, stage=stage.raw)
        paths = stage.options.get("paths")
        if paths is not None and paths not in ("relative", "absolute"):
            raise FlowError(f"`paths={paths}` is not valid — use relative or absolute",
                            line=stage.line, stage=stage.raw)
        dest = self._resolve_template_dest(stage.options["to-template"], stage)
        # Reuse the copy/convert path (no repoint): target=None copies the project as-is,
        # carrying its layouts + styled slots, optionally rewriting path storage.
        self.backend.repoint_project(src, dest, target=None, missing="keep",
                                     paths=paths, progress=self._emit)
        self._emit(f"   registered template → {dest}")
        return None  # terminal

    def _resolve_template_dest(self, value: str, stage) -> str:
        """Resolve a `to-template=` value to the destination project path: a direct path
        (`~`-expanded; must be `.qgs`/`.qgz`), or a bare name written into the template
        library as `<library>/<name>.qgz`."""
        looks_like_path = (
            os.sep in value
            or (os.altsep and os.altsep in value)
            or os.path.splitext(value)[1].lower() in (".qgs", ".qgz")
        )
        if looks_like_path:
            dest = os.path.expanduser(value)
            if os.path.splitext(dest)[1].lower() not in (".qgs", ".qgz"):
                raise FlowError(
                    f"`project to-template` writes a .qgs or .qgz — `{dest}` is neither",
                    line=stage.line, stage=stage.raw)
            return dest
        return os.path.join(self._template_library(), value + ".qgz")

    def _resolve_template(self, value: str, stage) -> str:
        """Resolve a `from-template=` value to a project-file path: a direct path
        (`~`-expanded), or a bare name looked up in the templates library."""
        expanded = os.path.expanduser(value)
        looks_like_path = (
            os.sep in value
            or (os.altsep and os.altsep in value)
            or os.path.splitext(value)[1].lower() in (".qgs", ".qgz")
            or os.path.isfile(expanded)
        )
        if looks_like_path:
            if not os.path.isfile(expanded):
                raise FlowError(f"`project from-template`: not a file: {expanded}",
                                line=stage.line, stage=stage.raw)
            if os.path.splitext(expanded)[1].lower() not in (".qgs", ".qgz"):
                raise FlowError(
                    f"`project from-template` reads a .qgs/.qgz — `{expanded}` is not one",
                    line=stage.line, stage=stage.raw)
            return expanded
        roots = self._template_roots()
        for root in roots:
            for ext in (".qgz", ".qgs"):
                cand = os.path.join(root, value + ext)
                if os.path.isfile(cand):
                    return cand
        avail = sorted({os.path.splitext(os.path.basename(p))[0]
                        for root in roots
                        for p in glob.glob(os.path.join(root, "*.qgz"))
                        + glob.glob(os.path.join(root, "*.qgs"))})
        hint = (f" — available: {', '.join(avail)}" if avail
                else f" — none found (set ${self._TEMPLATES_ENV}, drop .qgz templates in "
                     f"{self._TEMPLATES_USER}, or pass a path)")
        raise FlowError(f"`project from-template`: no template named `{value}`{hint}",
                        line=stage.line, stage=stage.raw)

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

    def _resolve_layer_refs(self, op, stage) -> None:
        """Resolve any `@conn.table` value bound to a *secondary-layer* param (e.g. clip's
        OVERLAY, `intersect`/`difference`/`union`'s overlay, `spatialjoin`'s `with=`) into a
        loaded layer. The binder is QGIS-free so it passes a `@conn` ref through as a string;
        here we load it via the backend (a plain path is left untouched). Lets a database table
        be used as the second layer in an overlay/join, not just a file."""
        for pname in op.layer_params:
            val = op.params.get(pname)
            if not (isinstance(val, str) and is_connection_ref(val)):
                continue
            try:
                conn, schema, table = parse_connection_ref(val, self.backend.connection_names())
            except ValueError as exc:
                raise FlowError(f"`{stage.verb}`: {exc}", line=stage.line, stage=stage.raw)
            if table is None:
                raise FlowError(
                    f"`{stage.verb}`: `{val}` is a bare connection — name a table "
                    "(`@conn.table`) to use it as a layer",
                    line=stage.line, stage=stage.raw,
                )
            op.params[pname] = self.backend.load_table(conn, schema, table).ref

    def _validate_crs_params(self, op, stage) -> None:
        """Reject an unknown CRS before running, so a bad code fails closed with a clear message
        instead of silently producing a layer with an invalid/empty CRS. The backend owns the
        actual validity check (it has QGIS's CRS database)."""
        check = getattr(self.backend, "valid_crs", None)
        if check is None:
            return
        for pname in op.crs_params:
            val = op.params.get(pname)
            if isinstance(val, str) and val.strip() and not check(val):
                raise FlowError(
                    f"`{val}` is not a recognised CRS — use an EPSG code (`EPSG:6346`), a WKT/PROJ "
                    "string, or an authority id QGIS knows",
                    line=stage.line, stage=stage.raw,
                )

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


# Leading keywords that mean a `sql` statement reads (returns a layer) rather than
# writes. Anything else (CREATE/UPDATE/INSERT/DROP/…) is a server-side write.
_QUERY_KEYWORDS = {"SELECT", "WITH", "VALUES", "TABLE", "EXPLAIN", "SHOW"}


def _is_query(sql: str) -> bool:
    """True when ``sql`` is a SELECT-style read (its first keyword is a query keyword).
    Leading whitespace, ``--``/``/* */`` comments, and opening parens are skipped first,
    so ``-- note\\nSELECT …``, ``/* c */ SELECT …`` and ``(SELECT …)`` still read as
    queries rather than being misrouted to a write."""
    s = sql.lstrip()
    while s:
        if s.startswith("--"):
            nl = s.find("\n")
            s = "" if nl < 0 else s[nl + 1:]
        elif s.startswith("/*"):
            end = s.find("*/")
            s = "" if end < 0 else s[end + 2:]
        elif s.startswith("("):
            s = s[1:]
        else:
            break
        s = s.lstrip()
    if not s:
        return False
    return s.split(None, 1)[0].upper() in _QUERY_KEYWORDS


def _format_project_info(info: dict, src: str) -> str:
    """Render `project info` — project title/CRS and a layer table — as Markdown."""
    lines = [f"# Project: {os.path.basename(src)}", ""]
    lines.append(f"- **File:** `{os.path.abspath(src)}`")
    if info.get("title"):
        lines.append(f"- **Title:** {info['title']}")
    lines.append(f"- **CRS:** {info.get('crs') or '(none)'}")
    layers = info.get("layers", [])
    lines.append(f"- **Layers:** {len(layers)}")
    lines.append("")
    if layers:
        lines.append("| Layer | Type | Provider | CRS | Source | Valid |")
        lines.append("|---|---|---|---|---|---|")
        for layer in layers:
            source = (layer.get("source") or "").replace("|", "\\|")
            lines.append(
                f"| {layer.get('name', '')} | {layer.get('type', '')} "
                f"| {layer.get('provider', '')} | {layer.get('crs', '')} "
                f"| `{source}` | {'✓' if layer.get('valid') else '✗'} |")
        lines.append("")
    return "\n".join(lines)


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
