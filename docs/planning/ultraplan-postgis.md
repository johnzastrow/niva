# Plan — PostGIS as a first-class read/write/analyse target (Phase 1, v0.17.0)

## Context
niva already **reads** from named QGIS database connections — `load @conn.table`
(`engine.py:346` `_load`) and `sql @conn "SELECT …"` (`engine.py:377` `_sql`) — behind a
hard security boundary: only the connection *name* crosses into niva; credentials live in
QGIS's store and are never seen, stored, or logged (`niva/engine/pyqgis.py:857`
`_find_connection`, `docs/planning/12-security-model.md`). It cannot **write** to a database
(`save` only writes files) nor run **non-SELECT** SQL.

The user wants PostGIS first-class: **read, write, analyse in-database**. This is the
foundation for "compile a region into PostGIS" workflows and the upcoming `project` verb
(Phase 2). Work is phased: **Phase 1 = PostGIS write + SQL analyse (this plan)**; **Phase 2 =
the `project` verb (separate release v0.18, sketched at the end, not built here).**

Decisions already taken with the user (carried into this plan):
- **Write is fail-closed:** `save @conn.table` creates a new table; if it exists it errors
  unless `mode=replace` (drop+recreate) or `mode=append` (INSERT).
- The credentials-stay-in-QGIS boundary is preserved end-to-end.

## What ships in Phase 1
1. `save @conn[.schema].table [mode=create|replace|append]` — write a layer into a DB table.
2. `each … | save @conn` — batch: one table per item, named after the item (default schema).
3. `sql @conn "<non-SELECT>"` — execute DDL/DML server-side (`CREATE TABLE AS …`, `UPDATE`,
   `INSERT`, `DROP`, spatial `ST_*` writes). SELECT-style queries return a layer as today.

## Dispatch shape (the change at a glance)

```mermaid
flowchart TD
    SAVE["_save (engine.py:397)"] -->|args[0] is @conn ref| DB["_save_to_db (new helper)"]
    SAVE -->|else, unchanged| FILE["existing file branch
    (QgsVectorFileWriter)"]
    DB --> ST["backend.save_table(layer, conn, schema, table, mode, lineage)"]

    SQL["_sql (engine.py:377)"] -->|_is_query: SELECT/WITH/VALUES/TABLE/EXPLAIN/SHOW| RUN["backend.run_sql(conn, query) → Layer"]
    SQL -->|else| EXEC["backend.execute_sql(conn, query) → None (terminal)"]

    ST -.->|PyqgisBackend| EXP["QgsVectorLayerExporter / connection API
    (credentials from live QGIS connection)"]
    EXEC -.->|PyqgisBackend| CES["connection.executeSql(query)"]
```

## Design

### A. `save` to a connection — `niva/engine/engine.py` `_save` (L397)
`_save` rejects **all** options at L403, so the DB target must branch **before** that. Add an
early dispatch right after the `current is None` guard (L398–402):

```python
if stage.args and is_connection_ref(stage.args[0]):
    return self._save_to_db(stage, current, lineage)
```
(`is_connection_ref`/`parse_connection_ref` are already imported and used by `_load`/`_sql`.)
The existing file branch (L403–460) stays **unchanged**.

New helper `_save_to_db(self, stage, current, lineage)`:
- **Parse target.** `parse_connection_ref(stage.args[0])` → `(conn, schema, table)`. Reject
  `as <layer>` (i.e. `len(stage.args) != 1`) and `{name}` templating for DB targets with a
  clear `FlowError`.
- **Table required (non-batch).** If not in a batch and `table is None` (bare `@conn`) →
  `FlowError` ("`save @conn.table` needs a table name").
- **Batch.** When `self._batch_item` is set and the ref is bare `@conn`: `table =
  _safe_name(self._batch_item)` (reuse `engine.py:750`), `schema` = whatever the ref carried
  (normally None → provider default). A schema-qualified batch (`@conn.schema`) is acceptable;
  a batch ref that already names a table is an error (one table per item). Document that
  bare-`@conn` batch uses the item name.
- **Options.** Allow exactly one: `mode` ∈ {`create` (default), `replace`, `append`}; any
  other option key, or a bad `mode` value → `FlowError`.
- **Raster guard.** If `current.facet == "raster"` → `FlowError` ("saving rasters to a
  database is not supported — use a file target"). PG-raster is out of scope for v1.
- **Call backend:** `return self.backend.save_table(current, conn, schema, table, mode=mode,
  lineage=lineage)`.

### B. Backend surface — `niva/engine/backend.py`
Add two abstract methods to `Backend` (only `MockBackend` and `PyqgisBackend` subclass it —
verified — so this is safe):
- `save_table(self, layer, conn, schema, table, *, mode="create", lineage=None) -> Layer`
- `execute_sql(self, conn, query) -> None`

`MockBackend` (mirror the existing `load_table`/`save` patterns at L152/L183):
- `save_table`: append `("save_table", conn, schema, table, mode)` to `self.calls`; also append
  a dict to a new `self.db_saves` list (mirroring `self.saves`); record `self.last_lineage`;
  return `Layer(DB_TABLE, "@{conn}." + (f"{schema}.{table}" if schema else table),
  facet="vector", name=table)` — same ref convention as `load_table` (L154).
- `execute_sql`: append `("execute_sql", conn, query)` to `self.calls`; return `None`.

### C. PyQGIS implementation — `niva/engine/pyqgis.py`
Reuse `self._find_connection(conn)` → `(md, connection)` (L857), as `load_table` (L879) and
`run_sql` (L898) already do. Keep all QGIS imports lazy (inside method bodies).

- `execute_sql(self, conn, query)`: `_md, connection = self._find_connection(conn)`; call
  `connection.executeSql(query)`; on failure raise `OpError` **without** the query in the
  message/params — copy the redaction `run_sql` uses (L907–912: params carry only
  `{"connection": conn}`, never the query text). Return `None`.

- `save_table(self, layer, conn, schema, table, *, mode, lineage)`:
  - `md, connection = self._find_connection(conn)`; provider key = `md.key()`.
  - Default `schema` to the provider's default (`"public"` for postgres) when None.
  - **Existence check** against the live connection: enumerate `connection.tables(schema)` and
    match `table` by name (or `try: connection.table(schema, table)`), so `create` can fail
    fast.
    - `create`: if it exists → `OpError` ("table `<schema>.<table>` exists — use mode=replace
      or mode=append").
    - `replace`: if it exists, `connection.dropVectorTable(schema, table)` (fallback:
      `executeSql("DROP TABLE …")`), then export fresh.
    - `append`: export with overwrite disabled so features INSERT into the existing table.
  - **Build the destination URI from the live connection** so host/credentials come from QGIS,
    never the flow: `QgsDataSourceUri(connection.uri())`, set `schema`, `table`, and the
    geometry column (from `layer.ref`); provider key = `md.key()`.
  - **Write:** `QgsVectorLayerExporter.exportLayer(layer.ref, uri, providerKey,
    layer.ref.crs(), False, options)`; check the returned error code and raise `OpError` on
    failure with **no credentials/URI** in the message (match the `save`-file error style at
    `pyqgis.py:660`). **Verify the exact `QgsVectorLayerExporter.exportLayer` /
    `connection.tables` / `dropVectorTable` signatures and the overwrite-disabling option
    against the installed QGIS (4.0.3 here) during implementation** — these provider APIs vary
    by version.
  - **Lineage (best-effort):** `COMMENT ON TABLE <schema>.<table> IS '<niva lineage>'` via
    `connection.executeSql`; never include credentials; failure is non-fatal (swallow).
  - **Return** `Layer(DB_TABLE, layer_or_uri, facet="vector", name=table)` so the result is
    still pipeable/inspectable (consistent with `load_table` returning a `DB_TABLE` layer).

### D. `sql` non-SELECT routing — `niva/engine/engine.py` `_sql` (L377)
Keep parsing identical (`sql @conn "query"`, bare connection only — L378–394). Replace the
single `return self.backend.run_sql(conn, query)` (L395) with a branch on the query's leading
keyword via a small module-level helper:

```python
def _is_query(sql: str) -> bool:
    head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    return head in {"SELECT", "WITH", "VALUES", "TABLE", "EXPLAIN", "SHOW"}
```
- `_is_query(query)` → `return self.backend.run_sql(conn, query)` (unchanged; returns a layer).
- else → `self.backend.execute_sql(conn, query); return None` (terminal step).

`CREATE TABLE AS SELECT …` correctly routes to **execute** (leading word `CREATE`); `WITH …
SELECT` routes to **run_sql**. A `None` return makes any following stage fail with the existing
"needs an input layer" error, which is the right behaviour for a terminal write. Add a one-line
doc comment noting the heuristic.

### E. Cross-cutting
- **Journal** (`niva/journal.py`): no change — it records stage text + `kind`, never resolved
  params or credentials. `save @conn…` / `sql` rows carry the user's own flow text only.
- **Export** (`niva/transpile.py`): `sql` is already skipped with a comment (L162–165), which
  covers execute-mode — no change needed there. For `save @conn`, guard the two `save`
  touch-points so we don't emit wrong `processing.run` OUTPUT:
  - The next-stage lookahead at L169–170: if `stages[i+1].args[0]` is a connection ref, do
    **not** treat it as a file `save_dest` — fall through to annotate.
  - The standalone-save branch at L156–160: if the dest is a connection ref, emit a distinct
    note (e.g. `#   save -> @conn.table (database write — no processing.run equivalent)`).
  Low priority; the goal is "don't regress export," not full fidelity.
- **Docs:** `docs/planning/13-verb-reference.md` (document `save @conn` modes + `sql` execute
  mode in §3/§8); `docs/planning/04-roadmap.md` (move "SQL writes & connection management"
  L122–136 from v2.0 → shipped for write/analyse); `docs/planning/12-security-model.md` (note
  the write path preserves the credential boundary — URI built from the live connection, never
  the flow); `README.md` (one line at L32–33 on PostGIS write/analyse).
  `plugin/environment.py` built-in verb list (L129) is unchanged — we extend `save`/`sql`, no
  new verb name.
- **Version:** bump `0.16.3 → 0.17.0` (MINOR) in `niva/__init__.py:19`, `pyproject.toml:7`,
  `plugin/metadata.txt:7`; add a `## [0.17.0] - 2026-06-18` entry to `CHANGELOG.md` (Added:
  DB write via `save @conn`; non-SELECT `sql`). Rebuild the plugin with
  `plugin/build_plugin.sh` → regenerates `plugin/niva_qgis.zip`.

## Tests
- **MockBackend, no QGIS** — extend `tests/test_sql.py` (use the existing `run(text)` helper at
  L8–17; assert on `backend.calls` tuples as at L38/L65). Add (here or in a new
  `tests/test_db_write.py`):
  - `save @conn.table` and `save @conn.schema.table` → `("save_table", conn, schema, table,
    "create")`; `mode=replace`/`append` flow through.
  - Bad `mode=` value → `FlowError`; an extra option on a DB save → `FlowError`; options still
    rejected on file saves (existing behaviour preserved).
  - `as <layer>` / `{name}` on a DB target → `FlowError`; bare `@conn` non-batch → `FlowError`.
  - batch `each … | save @conn` → one `save_table` per item, `table == _safe_name(item)`.
  - raster → DB target → `FlowError`.
  - `sql @conn "SELECT …"` → `("sql", …)` (run_sql); `"CREATE TABLE …"` / `"UPDATE …"` /
    `"INSERT …"` → `("execute_sql", …)`; `"WITH … SELECT …"` → `("sql", …)`;
    `"CREATE TABLE t AS SELECT …"` → `("execute_sql", …)`.
- **Real round-trip (QGIS), best-effort** — `tests/test_pyqgis.py`: reuse the SpatiaLite
  fixture/connection pattern already in `TestPyqgisConnections` (L166–229; SpatiaLite ships
  with QGIS) and the `setUpModule` skip (L15–21). Round-trip: build a tiny memory layer
  (`_write_points`, L24) → `save @conn.t` → `load @conn.t` → assert feature count; then
  `mode=create` collision → error, `mode=replace` → succeeds, `mode=append` → row count grows.
  Add a `sql` execute test: `sql @conn "CREATE TABLE t2 AS SELECT …"` then `load @conn.t2`.
  Skip cleanly if no usable DB connection.

## Verification (end-to-end)
1. `uv run python -m unittest discover -s tests -t .` — pure-Python suite (no QGIS), all green.
2. `uv run --with ruff ruff check .` — clean.
3. Headless against real QGIS (PostGIS or temp SpatiaLite):
   - `niva.flow('load roads.gpkg | clip aoi.gpkg | save @pg.public.roads_clip')` → table created.
   - re-run → errors (exists); `mode=replace` succeeds; `mode=append` adds rows.
   - `niva.flow('sql @pg "CREATE TABLE t AS SELECT 1 AS a"')` then `load @pg.t` → 1 row.
   - Confirm no credential/URI text appears in the `.log`/`.jsonl` journal and `/tmp` is clean.

## Phase 2 (next release, v0.18 — sketch only, NOT built here)
`project "<src.qgs|qgz>" to="<out>" repoint="<target>" [missing=fail|keep|drop]`:
- New built-in verb: dispatch in `_run_stage` (engine.py:292) + a `_project` method modelled on
  `_catalog` (engine.py:658); add to `plugin/environment.py` built-in list and the verb ref.
- Use a **standalone** `QgsProject()` (never `QgsProject.instance()`) for off-main-thread
  safety: `proj.read(src)` → per layer `layer.setDataSource(new_uri, name, provider)` →
  `proj.write(out)` (.qgs/.qgz by extension).
- One `<target>` per call — a `.gpkg` path **or** `@conn[.schema]` (ties into Phase 1). Derive
  each layer's name from the old datasource (`|layername=`, else file stem), preserve `subset=`
  filters, point at `<target>|layername=<name>` (gpkg) or the `<name>` table (DB). Unmatched
  layers fail loudly; `missing=keep|drop` overrides. Never silently break a project file.
- Then de-flag Task 5 in `examples/analyst_plan.niva` and add a worked `project`/`save @conn`
  example.

## Summary

Plan — PostGIS as a first-class read/write/analyse target (Phase 1, v0.17.0)
Context
niva already reads from named QGIS database connections — load @conn.table (engine.py:346 _load) and sql @conn "SELECT …" (engine.py:377 _sql) — behind a hard security boundary: only the connection name crosses into niva; credentials live in QGIS's store and are never seen, stored, or logged. It cannot write to a database (save only writes files) nor run non-SELECT SQL. The user wants PostGIS first-class: read, write, analyse in-database. Phased: Phase 1 = PostGIS write + SQL analyse (this plan); Phase 2 = the project verb (separate release v0.18, sketch only).

Decisions: write is fail-closed (save @conn.table creates; errors if exists unless mode=replace/mode=append); credentials-stay-in-QGIS boundary preserved end-to-end.

What ships in Phase 1
save @conn[.schema].table [mode=create|replace|append] — write a layer into a DB table.
each … | save @conn — batch: one table per item, named after the item (default schema).
sql @conn "<non-SELECT>" — execute DDL/DML server-side. SELECT-style queries return a layer as today.
Design
A. _save (engine.py:397): rejects all options at the top, so DB target branches before that — early dispatch if stage.args and is_connection_ref(stage.args[0]): return self._save_to_db(...); file branch unchanged. New _save_to_db helper: parse ref, reject as/{name}, table required (non-batch), batch bare-@conn → _safe_name(item), allow only mode= ∈ {create/replace/append}, raster→FlowError, call backend.save_table.
B. backend.py: two new abstract methods save_table(...), execute_sql(...) (only MockBackend/PyqgisBackend subclass). MockBackend records ("save_table", conn, schema, table, mode) + db_saves list; ("execute_sql", conn, query).
C. pyqgis.py: reuse _find_connection. execute_sql → connection.executeSql(query), redacted errors. save_table → existence check via connection.tables(schema), drop on replace, build dest URI from live connection (QgsDataSourceUri(connection.uri())), QgsVectorLayerExporter.exportLayer(...), lineage via COMMENT ON TABLE, reload as live layer. Verify exporter/connection API against installed QGIS.
D. _sql (engine.py:377): parsing identical; branch on _is_query(query) (leading word ∈ SELECT/WITH/VALUES/TABLE/EXPLAIN/SHOW) → run_sql, else execute_sql + return None (terminal).
E. Cross-cutting: journal unchanged; transpile guards save @conn (no wrong OUTPUT); docs (13-verb-reference, 04-roadmap, 12-security-model, README); version bump 0.16.3→0.17.0 (niva/__init__.py, pyproject.toml, plugin/metadata.txt, CHANGELOG); rebuild plugin/niva_qgis.zip.
Tests
MockBackend (no QGIS): dispatch + mode parsing/validation, as/{name}/bare-@conn rejection, batch one-table-per-item, raster→FlowError, sql SELECT vs non-SELECT routing (incl. WITH…SELECT → run, CREATE…AS SELECT → execute).
Real round-trip (QGIS, best-effort): SpatiaLite fixture, save→load→count, mode collision/replace/append, sql execute. Skips cleanly without QGIS.
Verification
uv run python -m unittest discover -s tests -t .; ruff check .; headless QGIS round-trip.

Phase 2 (v0.18, sketch only — NOT built here)
project "<src.qgs>" to=… repoint=… [missing=…] — standalone QgsProject(), repoint layers to a .gpkg or @conn.
