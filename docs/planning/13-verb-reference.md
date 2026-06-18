# Niva — Verb Reference (worked)

_Fully explains the verb model, then walks verbs from simple to complex and
composes them. Companion to `03` (the verb list), `07` (the registry that powers
verbs), and `10` (the grammar). The niva flows are **illustrative** — niva isn't
built yet — but every **algorithm id, parameter, default, and enum-by-word mapping
shown was verified against the live QGIS 4.0.3 registry** (the grammar is the
proposal; the QGIS call it resolves to is real)._

---

## 0. What exercising the design surfaced (synthesis)

Six worked rounds (§§5–11: vector composite, raster, SQL, `call`, provenance,
interactive `add`) turned up **34 concrete issues**. Most were folded straight back
into the specs — this is the box score so the conclusions aren't buried in the
round tables.

**Decisions the exercise forced** (round in brackets):

- **Grammar / verbs** — the simplified `filter` is *essential*, not optional, and its
  expression still needs outer quotes [§5]; list options are comma-joined
  (`fields=a,b`) [§5]; stages stay one line, flows wrap only at `|` [§5].
- **Sinks** — `save` defaults to GeoPackage, infers format, **won't overwrite a
  same-flow source**, creates parent dirs [§5]; **sinks pass through**, so `save …
  | add` chains [§11]; `add` is **live-session-only** (headless warns/skips), adds a
  *temporary* layer, default styling, main-thread only [§11].
- **The layer handle** — needs a **vector/raster facet** (band/resolution metadata,
  kind-correct `as_qgs()`) and **piped-input type-checking** [§7, §11 → Oscar A10];
  a raster secondary is **never silently warped** [§7].
- **SQL** — `sql` has **three forms/engines** (query-layer / `gdal:executesql` /
  `qgis:executesql`); the write-only `*executesql` algorithms are **not** the read
  path [§8]; a `SELECT` isn't self-describing (`key=`/`geom=`/`crs=`) [§8]; inputs
  are `input1`, `input2` [§8]; prefer `ST_*` in-query for DB-resident data [§8].
  **As of v0.17.0 `sql @conn` also runs non-SELECT statements** (DDL/DML) server-side
  as a terminal step; the leading keyword routes read vs. write [§8].
- **DB write** — `save @conn[.schema].table` writes the result into a database table
  (v0.17.0); **fail-closed** (`mode=create` errors if it exists; `mode=replace`/
  `mode=append` otherwise); credentials stay in QGIS [§3 (save), §8].
- **`call`** — a **statement, not a pipeable stage**; files share data only via
  `save`/`add` (no shared layer) [§9]; `call` target is caller-relative, data paths
  are run-`work_dir` [§9]; cycles error + max-depth [§9].
- **Provenance** — lineage **survives non-algorithm steps** (`sql`/`load`) [§10];
  multi-input ops **merge** all inputs' histories (flattened, role-tagged) [§10];
  `filter`/`extract` **count as data-altering** and are recorded [§10]; the journal
  tags ops by source file and lineage records the call chain across `call`s [§9, §10].

**The design held** — the `buffer`/`join`/`zonalstats` enum-by-word vocab matches
the live QGIS registry exactly, so the registry + linter premise (`07`) works
[§7, verified].

**Still open** (tracked in `00` / Oscar): stage line-wrapping [§5]; surfacing
secondary outputs in a text flow [§5]; ratifying the vector/raster handle facet
[§7]; flat-log vs structured provenance (PROV/DAG) [§10]; robust read-only-SQL
classification [§8].

**Box score:** 34 surfaced · ~26 folded into specs (`02`/`03`/`06`/`08`/`10`) ·
1 verified-positive · ~5 still open · 8 logged as Oscar risks (A10, C15/C16,
D8–D10, U11/U12).

---

## 1. What a verb is

A niva **verb** is a friendly name for **one** QGIS algorithm. The grammar binds a
stage's parts to that algorithm's parameters; niva supplies the boring defaults
and threads the data, so **you write intent, not boilerplate**.

**Anatomy of a stage:**

```
verb   <positional…>   <flag…>   <key=value…>
```

| Part | What | Example |
|------|------|---------|
| **verb** | the operation | `buffer` |
| **positional** | the primary argument(s), in a fixed per-verb order | `buffer 100m` |
| **flag** | a bare word = a boolean turned **on** | `dissolve` |
| **option** `key=value` | any other parameter, only when you need it | `segments=12` |
| **the pipe `\|`** | threads the previous stage's layer into this verb's **primary input**, and sends this verb's output onward | `… \| buffer 100m \| …` |

You **never** write `INPUT`/`OUTPUT` — the pipe handles them (`02-§2a`).

**How a verb maps down** (`07`): niva keeps a registry entry mapping each verb to a
`provider:algorithm` id + a parameter mapping + defaults + word-valued enums.
`describe <verb>` prints the exact mapping; `--dry-run` prints the resolved call.

**Cross-cutting rules every verb obeys:**
- **Units** on distances — `100m`, `2km`; bare = CRS units; a metric distance on a
  degrees CRS errors (`03-§1.1`).
- **Enum-by-word** — `cap=flat`, not a magic integer.
- **Sensible defaults** — niva fills required-but-boring params (segments, …).
- **Native-first** — verbs resolve to `native:*` where possible; GRASS/SAGA last
  (`07-§12.1`).
- **Escape hatch** — any algorithm without a verb: `run <id> KEY=value` (`07-§8`).
- **CRS is never silently changed** (`03-§1.2`); **`save` never silently
  overwrites a source** (`03-§2.5`).

Each signature below lists arguments as **name · kind · maps to · default · notes**,
the target algorithm, and a worked example with the resulting `processing.run`
call so you can see exactly what niva hides.

---

## 2. Simple — `reproject` (one argument)

### Signature
```
reproject <target_crs> [operation=<proj-pipeline>]
```

### Arguments
| arg | kind | maps to | default | notes |
|-----|------|---------|---------|-------|
| `target_crs` | positional **(required)** | `TARGET_CRS` | — | an EPSG code (`EPSG:2262`) or a WKT/PROJ string |
| `operation` | option | `OPERATION` | none | explicit coordinate-operation (advanced) |
| *(piped layer)* | primary input | `INPUT` | — | the layer to reproject |

**Algorithm:** `native:reprojectlayer`. **niva hides:**
`CONVERT_CURVED_GEOMETRIES=false`, `TRANSFORM_Z=false`, `OUTPUT` (temp).

### Worked
```
load parcels.shp | reproject EPSG:2262
```
```python
processing.run("native:reprojectlayer", {
  "INPUT": <parcels>, "TARGET_CRS": "EPSG:2262",
  "CONVERT_CURVED_GEOMETRIES": False, "TRANSFORM_Z": False,
  "OPERATION": None, "OUTPUT": "TEMPORARY_OUTPUT"})
```
One readable token vs five params — and niva won't silently reproject anywhere
*else* (`03-§1.2`), so this verb is how you change CRS on purpose.

---

## 3. Medium — `buffer` (positional + flag + options; units + enum-by-word)

### Signature
```
buffer <distance> [dissolve] [separate]
       [segments=<n>] [cap=round|flat|square] [join=round|miter|bevel] [miter=<n>]
```

### Arguments
| arg | kind | maps to | default | notes |
|-----|------|---------|---------|-------|
| `distance` | positional **(required)** | `DISTANCE` | — | a distance with units (`100m`, `2km`); unit/CRS rules `03-§1.1` |
| `dissolve` | flag | `DISSOLVE` | off | merge overlapping buffers into one |
| `separate` | flag | `SEPARATE_DISJOINT` | off | keep disjoint parts separate |
| `segments` | option (int) | `SEGMENTS` | 5 | arc approximation |
| `cap` | option (enum) | `END_CAP_STYLE` | `round` | `round`/`flat`/`square` → 0/1/2 |
| `join` | option (enum) | `JOIN_STYLE` | `round` | `round`/`miter`/`bevel` → 0/1/2 |
| `miter` | option (number) | `MITER_LIMIT` | 2 | used when `join=miter` |
| *(piped layer)* | primary input | `INPUT` | — | |

**Algorithm:** `native:buffer`.

### Worked
```
… | buffer 100m dissolve cap=flat segments=12
```
```python
processing.run("native:buffer", {
  "INPUT": <prev>, "DISTANCE": 100,        # 100 m → CRS units (03-§1.1)
  "SEGMENTS": 12, "END_CAP_STYLE": 1,      # cap=flat → 1
  "JOIN_STYLE": 0, "MITER_LIMIT": 2,       # defaults niva filled
  "DISSOLVE": True, "SEPARATE_DISJOINT": False,
  "OUTPUT": "TEMPORARY_OUTPUT"})
```
Shows it all: a units-bearing positional, a flag, an int option, **enum-by-word**
(`cap=flat`→1), and the four defaults niva supplies so you don't have to.

---

## 4. Complex — `join` (multi-input + options + enum + multi-output)

### Signature
```
join with=<layer> field=<a> field2=<b>
     [fields=<f,f,…>] [prefix=<p>] [method=one-to-one|one-to-many] [discard]
```

### Arguments
| arg | kind | maps to | default | notes |
|-----|------|---------|---------|-------|
| `with` | option (layer) **(required)** | `INPUT_2` | — | the second table/layer — a file, `@conn.table`, or an upstream branch |
| `field` | option (field) **(required)** | `FIELD` | — | join key on the **current** (left) layer |
| `field2` | option (field) **(required)** | `FIELD_2` | — | join key on the `with` layer |
| `fields` | option (field list) | `FIELDS_TO_COPY` | all | which columns to copy from `with` |
| `prefix` | option (string) | `PREFIX` | none | prefix the copied column names |
| `method` | option (enum) | `METHOD` | `one-to-one` | `one-to-one`/`one-to-many` → 1/0 |
| `discard` | flag | `DISCARD_NONMATCHING` | off | drop rows with no match |
| *(piped layer)* | primary input | `INPUT` | — | the left layer |

**Algorithm:** `native:joinattributestable`.

**Multiple outputs.** This algorithm returns more than a layer: `JOINED_COUNT`,
`UNJOINABLE_COUNT`, and an optional `NON_MATCHING` layer. niva sends the **joined
layer** onward as the flow's output; the counts ride on `Result.outputs` (and
appear under `--json`) — see `07-§7`.

### Worked
```
… | join with=census.csv field=tract field2=GEOID fields=pop,income prefix=cen_ discard
```
```python
res = processing.run("native:joinattributestable", {
  "INPUT": <prev>, "FIELD": "tract",
  "INPUT_2": "census.csv", "FIELD_2": "GEOID",
  "FIELDS_TO_COPY": ["pop", "income"], "METHOD": 1,   # one-to-one
  "DISCARD_NONMATCHING": True, "PREFIX": "cen_",
  "OUTPUT": "TEMPORARY_OUTPUT"})
# res also carries JOINED_COUNT / UNJOINABLE_COUNT
```
Shows the hard cases: a **required secondary input** (`with=`), field-matching, a
list option, **enum-by-word**, a flag, and **secondary outputs** the registry keeps
reachable.

---

## 5. Putting it together — a composite operation

**Goal:** from county parcels (NAD83 lat/long), take residential parcels, make 100 m
buffers, attach census attributes, and save — documented.

```
# composite.niva
load parcels.shp                                   # county parcels, NAD83 geographic (EPSG:4269)
  | filter "landuse = 'R'"                          # residential only (simplified filter, 03-§3)
  | reproject EPSG:2262                             # SIMPLE — to NY State Plane West (ftUS), a *projected* CRS…
  | buffer 100m dissolve cap=flat                   # MEDIUM — …so `buffer 100m` works (a metric buffer on a
                                                     #          geographic CRS would error — 03-§1.2)
  | join with=census.csv field=tract field2=GEOID fields=pop,income prefix=cen_   # COMPLEX — attach census
  | save outputs/residential_buffers.gpkg           # GeoPackage; lineage recorded (08)
```

> Each **stage** is on one line; the **flow** wraps only at `|` (`10-§2`). A long
> stage like the `join` stays on a single line — see §6 on whether that should
> change. The `filter` argument is quoted (`"landuse = 'R'"`): the **simplified**
> form (`03-§3`) drops the field double-quotes, but the expression still needs
> outer quotes because its `=` and spaces would otherwise collide with `key=value`
> option syntax.

**What niva did, in order:** `extractbyexpression` → `reprojectlayer` → `buffer` →
`joinattributestable` → write a GeoPackage — threading each temp output into the
next input, converting `100m` to feet, filling defaults, and recording every step
as lineage on `save`. The `reproject` **before** `buffer` isn't decoration: the
metric buffer on a geographic CRS would be a hard error, so the simple verb sets up
the medium one.

The same intent in raw PyQGIS is ~25 lines of `ALL_CAPS` dicts and manual output
threading (`06-§7`). Here:
- `niva describe buffer` prints §3's mapping;
- `niva run composite.niva --dry-run` prints the four resolved algorithm calls
  without running anything;
- the saved `residential_buffers.gpkg` carries the four-step lineage in its
  metadata (`08-§3`).

---

## 6. What writing this surfaced (design issues)

Working three real signatures and one composite exercised the design and turned up
genuine issues — some now fixed/specified, some newly open:

| # | What surfaced | Verdict |
|---|---------------|---------|
| 1 | **Filter quoting is the make-or-break.** The raw form `filter "\"landuse\" = 'R'"` (escaped field-quotes) is unreadable; the **simplified** form `filter "landuse = 'R'"` is fine. **Confirms the simplified `filter` (`03-§3`) is essential to v1, not optional** — and that even simplified, the expression needs *outer* quotes (its `=`/spaces collide with `key=value`). | validated; doc fixed |
| 2 | **List-valued options weren't specified.** `fields=pop,income` (comma list) had no grammar rule. | **closed** — added to `10-§2.1`: a list-typed option's value may be comma-separated |
| 3 | **`save` parent-directory creation was undefined.** `save outputs/…` — does niva make `outputs/`? | **closed** — `save` creates missing parent dirs (`03-§2.5`) |
| 4 | **Stage line-wrapping is undefined.** A flow wraps at `|` (`10-§2`), but a long *single* stage (the 5-option `join`) has no continuation. | **open** — keep stages one-line (verbs are meant to be short), or add stage continuation? (`00`) |
| 5 | **Secondary outputs vanish in a text flow.** `join` yields `JOINED_COUNT`/`UNJOINABLE_COUNT`, but a `.niva` flow can only pass the joined layer onward; the counts live only in `Result.outputs` / `--json` / the journal — a non-programmer running the flow can't see "how many matched." | **open** — surface scalar outputs in the run summary? capture syntax? (relates to Oscar C7, v2 named intermediates) |
| 6 | **Silent join-key type mismatch.** `field=tract` (often numeric) vs a CSV `field2=GEOID` (string) yields **zero matches, silently**. | **open** — `join`/`assess` should warn on key-type mismatch (a new data-correctness risk, Oscar D8) |

(1–3 are folded back into the specs; 4–6 are logged as open questions / risks.)

---

## 7. Round 2 — `zonalstats` (raster × vector)

A different shape: the piped layer is the **vector zones**, the **raster** is a
secondary input, and `stats` is an **enumlist**.

### Signature
```
zonalstats <raster> [band=<n>] [stats=count,sum,mean,…] [prefix=<p>]
```

| arg | kind | maps to | default | notes |
|-----|------|---------|---------|-------|
| `raster` | positional **(required)** | `INPUT_RASTER` | — | the raster to summarize (path → a raster source) |
| `band` | option (int) | `RASTER_BAND` | 1 | which band |
| `stats` | option (enumlist) | `STATISTICS` | `count,sum,mean` | any of `count sum mean median stdev min max range minority majority variety variance` — **verified vs live QGIS** |
| `prefix` | option (string) | `COLUMN_PREFIX` | `_` | prefix for the new columns |
| *(piped layer)* | primary input | `INPUT` | — | the **vector zones** — gains new stat columns |

**Algorithm:** `native:zonalstatisticsfb` (the new-output variant — never mutates
in place).

### Worked
```
load watersheds.gpkg | zonalstats dem.tif band=1 stats=mean,min,max prefix=elev_ | save wsheds_elev.gpkg
```
```python
processing.run("native:zonalstatisticsfb", {
  "INPUT": <watersheds>,                 # the piped VECTOR zones
  "INPUT_RASTER": "dem.tif", "RASTER_BAND": 1,
  "STATISTICS": [2, 5, 6],               # mean,min,max → live enum indices (verified)
  "COLUMN_PREFIX": "elev_",
  "OUTPUT": "TEMPORARY_OUTPUT"})
# output = watersheds + columns elev_mean, elev_min, elev_max
```

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 7 | **The layer handle is vector-centric.** `02-§3` models a `Layer` by `geometry_type`/`fields`/`feature_count`, with `as_qgs()`→`QgsVectorLayer`. A raster (`dem.tif`, and the whole lidar→DEM→slope path) has **bands/resolution/extent, no features**, and `as_qgs()` must return a `QgsRasterLayer`. | **open (significant)** — the handle needs a **vector/raster facet**: raster metadata, vector fields `None` for rasters, kind-correct `as_qgs()` (note added to `02-§3.1`) |
| 8 | **CRS reconcile for a *raster* secondary.** `03-§1.2` says "reproject the secondary to the primary's CRS" — cheap for a vector overlay, but **warping a raster is expensive/lossy**. | **open** — raster caveat added to `03-§1.2`: prefer reprojecting the *vector zones* to the raster, or error rather than silently warp |
| 9 | **Piped-input type isn't checked.** `zonalstats` needs a **vector** primary; in a raster-heavy flow it's easy to pipe a raster into `INPUT`. | **open** — the engine should type-check the piped handle against the verb's primary-input type and error clearly (`00`) |
| 10 | **Field-name truncation.** `prefix=elevation_` + `mean` exceeds a **Shapefile's 10-char** field limit → silent truncation/collision. | **open** — warn when the output format limits field names; GeoPackage (the default, `03-§2.5`) avoids it (Oscar D9) |
| ✓ | **Enum vocab — VERIFIED.** `stats=mean,min,max` → `[2,5,6]` matches `native:zonalstatisticsfb`'s live `STATISTICS` options exactly. | **positive** — the enum-by-word vocab (`07-§6`) reconciles with the installed QGIS; the linter passes |

Also a **consistency** fix this turned up: doc `06`'s `zonalstats` example used the
space form (`band 1 stats …`); corrected to the canonical `key=value` (`03-§2`).

---

## 8. Round 3 — the SQL path (`sql` + cross-surface)

The richest, messiest surface. The same `sql` verb has **three forms**, each a
different engine and a different way the result becomes a layer (spec'd in
`03-§2.6`):

| Form | Engine | Mechanism | Result handle |
|------|--------|-----------|---------------|
| `sql @conn "SELECT …"` | PostGIS / SpatiaLite | a **query layer** over the SELECT (no copy) | `db_table` |
| `sql "SELECT …" from file.gpkg` | OGR **SQLITE** | `gdal:executesql` → temp vector | `source` |
| `sql "SELECT … FROM input1 …"` | QGIS **virtual layer** | `qgis:executesql` over piped + loaded layers | `source` |

### Worked — round-trip a DB query back into a verb
```
sql @cats_pg "SELECT id, geom FROM homes WHERE has_cat AND NOT has_dog"
  | buffer 100m
  | save targets.gpkg
```
- `sql @cats_pg …` → a **PostGIS query layer** (`db_table` handle), roughly
  `QgsVectorLayer("dbname=… table=\"(SELECT id, geom FROM homes WHERE …)\" (geom) key='id'")`.
- `| buffer 100m` → `native:buffer` reads it — which **pulls the matching rows from
  PostGIS into the in-process buffer** (correct, but client-side).
- `| save targets.gpkg` → temp → GeoPackage; lineage records the SQL + the buffer.

### …or do the geo-work in SQL (the lever)
```
sql @cats_pg "SELECT id, ST_Buffer(geom, 100) AS geom FROM homes WHERE has_cat AND NOT has_dog"
  | save targets.gpkg
```
Buffers **server-side** (`ST_Buffer`, indexed, no client pull) — far faster on big
data (Oscar L4). The grammar makes both one line; niva should *teach* the second
for DB-resident data.

### Write & analyse in the database (v0.17.0)

The same security boundary that makes reads safe (the connection **name** is all niva
sees; QGIS owns the credentials) now also covers writes.

**Write a result into a table** — `save @conn[.schema].table`:
```
load roads.gpkg | clip aoi.gpkg | save @pg.public.roads_clip
```
- The destination URI (host/database/login) is built from the **live** connection, so
  no credential ever appears in the flow, the log, or an error message.
- **Fail-closed.** `save` defaults to `mode=create` and **errors if the table exists** —
  matching "no silent overwrite of an input" (`12-§3`). Use `mode=replace` (drop +
  recreate) or `mode=append` (INSERT into the existing table) to opt in.
- In an `each` batch, `save @conn` writes **one table per item**, named after the item.
  A trailing qualifier is the **schema** to write them into (there is no single table to
  name): `each "NiagaraBasemap/" | … | save @pg.niagara` puts each layer in schema
  `niagara`; bare `save @pg` uses the provider's default schema. (`@conn.schema.table`
  is rejected in a batch — that names one table.)
- Rasters to a database are out of scope for v1 — use a file target.

**Analyse server-side** — `sql @conn "<non-SELECT>"`:
```
sql @pg "CREATE TABLE roads_buf AS SELECT id, ST_Buffer(geom, 100) AS geom FROM roads"
```
- A SELECT-style statement (`SELECT`/`WITH`/`VALUES`/`TABLE`/`EXPLAIN`/`SHOW`) still
  returns a **pipeable layer**; anything else (DDL/DML) runs as a **terminal** step and
  returns nothing. The **leading keyword** decides: `CREATE TABLE … AS SELECT …` runs as
  a write, `WITH … SELECT …` as a read.

**Create a project from outputs** — `project new from=<dir|glob> to=<out.qgs|qgz>` (v0.21.0):
```
project new from="data/" to="region.qgs" crs=EPSG:6346 title="Niagara Region"
```
Writes a fresh QGIS project that loads every layer found under `from=` (a directory, glob,
or multi-layer container — resolved like `each`, GeoPackages expanded per layer), optionally
setting the project CRS and title. The complement to repointing: build a ready-to-open
project for freshly compiled outputs without needing one to already exist. Terminal.

**Copy / convert / rewrite paths** — `repoint=` is optional (v0.24.0). `project <src> to=<out>`
copies a project, converting `.qgs`↔`.qgz` by the `to=` extension; add `paths=relative` (or
`absolute`) to rewrite datasource path storage (e.g. make a project portable). Combine with
`repoint=`/`rasters=` to repoint *and* rewrite in one pass.

**Bookmark a region** — `bookmark=<name>` (v0.25.0). `project <src> to=<out> bookmark="Study
Area"` adds a spatial bookmark covering the **union** of the project's layers (a jump-to for
compiled outputs). For a centred bookmark, add `at="x,y"` with either `width=<w>` (an exact
extent in map units) or `scale=<N>` (converted to a width via a ~0.5 m reference map view —
approximate; prefer `width=` for an exact extent). Composes with `repoint=`/`paths=`.

**Inventory a project** — `project info <src.qgs|qgz> [to=<out.md>]` (v0.23.0):
```
project info "region.qgs" to="region_layers.md"
```
Reads a project and writes a Markdown report of its layers — name, type, provider, CRS,
datasource, and validity — plus the project's title and CRS. A `catalog` for project files;
handy for auditing what a `.qgs` points at. Terminal.

**Repoint a project** — `project <src.qgs|qgz> to=<out> repoint=<target>` (v0.18.0):
```
project "NiagaraBasemap/data.qgs" to="data/basemap.qgs" repoint="data/basemap_clip.gpkg" missing=keep
```
Copies a QGIS project and repoints each **vector** layer's datasource to one `<target>` —
a GeoPackage path **or** an `@conn[.schema]` database (the v0.17.0 DB write) — matched by
the layer's name (its old `|layername=`, else the file stem), **subset filters preserved**.
A standalone `QgsProject()` is used (off the main thread; never the GUI singleton). A layer
whose name isn't in the target is handled by `missing=` — `fail` (default, never silently
break a project), `keep` (leave it), or `drop` (remove it). This is the last piece of
"compile a region" (analyst-plan Task 5).

**`rasters=<dir>`** (v0.19.0) repoints **raster** layers too — they live in separate files,
not the vector container/DB, so each raster is repointed to a **same-basename file in
`<dir>`** (e.g. a project's `dem.tif` → `<dir>/dem.tif`), via the `gdal` provider. Without
`rasters=`, raster layers are left unchanged; with it, an unmatched raster follows the same
`missing=` policy.

**Instantiate a template** — `project from-template=<name|path> to=<out> data=<dir|glob>` (v0.26.0):
```
project from-template="my_basemap.qgz" to="region_atlas.qgz" data="data/clips/"
```
**Any existing QGIS project is a template** — it already carries **print layouts** and
**styled layers**; pass its `.qgs`/`.qgz` path and niva copies it, then repoints each layer
**slot** — **vector *or* raster** — to the **same-named dataset** found under `data=`
(resolved like `each`/`project new`: a directory, glob, or container), so the **symbology and
layouts ride along** (a repoint preserves a layer's style). This is "compile a region" with a
designed map *and* layout, not just data — and it means you author templates the normal way,
in QGIS, then reuse them against fresh data.

Slots match by the layer's **display name** (what you labelled it in the layer panel),
falling back to the datasource name — so a slot shown as `parcels` is filled by `parcels.gpkg`
in `data=`, regardless of the placeholder it currently points at. Unmatched slots follow
`missing=` (default **`keep`**, so the layout's structure survives; `drop` to prune, `fail` to
be strict). Terminal. (Supersedes the separate "print layout" roadmap items: a template *is*
the layout + styles, applied in one pass.)

Templates resolve by **name** from `$NIVA_TEMPLATES` or the user library `~/.niva/templates`,
or by **path**. To register one of your projects under a name (so `from-template=<name>` finds
it), use **`project to-template=<name|path> from=<src.qgs|qgz> [paths=relative]`** (v0.27.0):
```
project to-template=parcel_map from="MyParcelMap.qgz" paths=relative
project from-template=parcel_map to="acme.qgz" data="acme/parcels/"
```
`to-template` copies an existing project into the library as a reusable template (its layouts
+ styled slots intact); a bare **name** lands in the library, a **path** writes anywhere, and
`paths=relative` makes the template portable. The slots keep their current data as *example*
data, repointed on instantiation. niva also **ships a bundled `example` template**
(`from-template=example`) with three styled slots + a print layout + a bookmark. See
[docs/templates.md](../templates.md) for the full element reference (what a template carries)
and an authoring walkthrough.

**Style a layer** — `style apply <file>` / `style save <file>` (v0.20.0):
```
load roads.gpkg | clip aoi.gpkg | save roads_clip.gpkg | style apply house.qml
```
Applies a `.qml` (symbology) or `.qmd` (metadata) sidecar to the current layer and
**persists** it so QGIS shows it: a GeoPackage layer's style goes into the container's
`layer_styles` table (a re-loaded layer adopts it as default); a single-file layer gets a
same-basename `.qml`/`.qmd` sidecar QGIS auto-loads. `style save <file>` exports the current
layer's style/metadata to a sidecar instead. Both are **pass-through**, so `style` chains
after `save` (which returns the saved layer). `apply` needs a file-backed layer — save
first. (`apply` to a database-backed layer isn't supported yet.)

`style save` also exports two more formats (v0.22.0): **`.sld`** (OGC Styled Layer
Descriptor, for GeoServer/interop) and **`.qlr`** (a portable QGIS *Layer Definition* —
datasource **+** style in one file, drag-droppable into any project). Both are
export-only; `apply` stays `.qml`/`.qmd`.

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 11 | **Three forms, three mechanisms** — and the `*executesql` algorithms are **write-only** (no output), so a `SELECT` does *not* use them; reads use a query layer / `gdal:executesql` / `qgis:executesql`. | **fixed** — `03-§2.6`; `06-§4` corrected |
| 12 | **A SELECT result isn't self-describing.** Virtual-layer SQL **requires** uid + geometry + geometry-type + **CRS**; a DB query layer needs a unique key + geometry column. | **spec'd** — auto-detect, else `sql … key= geom= crs=` (`03-§2.6`) |
| 13 | **Table naming.** Bare `sql` references the piped/loaded layers as **`input1`**, `input2`, … (QGIS convention). | **spec'd** — `03-§2.6` |
| 14 | **Read vs. write routing.** "Starts with SELECT" misses `WITH … SELECT`; and writes were deferred. | **shipped (v0.17.0)** — leading keyword routes read (`SELECT`/`WITH`/`VALUES`/`TABLE`/`EXPLAIN`/`SHOW` → query layer) vs. write (everything else → terminal `execute_sql`); see "Write & analyse" above |
| 15 | **The round-trip pulls data client-side**, losing the DB index/planner. | **guidance** — prefer `ST_*` in the query for DB data (Oscar L4) |
| 16 | **Result CRS** = the geometry SRID (a `ST_Transform` changes it); virtual SQL must **declare** it. | **spec'd** — `03-§2.6` |
| 17 | **`sql` syntax had drifted** — doc `06` used `use @conn` + `\| load`; doc `03` used `sql @conn`. | **fixed** — canonical `sql @conn "…"` everywhere; `06-§4.4` corrected |

---

## 9. Round 4 — the `call` path (multi-file composition)

`call` runs another `.niva` file's flows inline (`03-§4.1`). A reusable helper and
a parent that uses it:

```
# acquire.niva — reusable: fetch + clean the base layers
load "nys.gdb|layername=buildings" | reproject EPSG:2262 | fix | clip village.gpkg | save work/buildings.gpkg
load "niagara/roads.shp"           | reproject EPSG:2262 | fix | clip village.gpkg | save work/roads.gpkg
```
```
# analyze.niva
call acquire.niva                                                  # runs acquire's two flows here
load work/buildings.gpkg | filter "landuse = 'R'" | buffer 100m | save out/res_buffers.gpkg
call report.niva
```

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 18 | **`call` is a statement, not a pipeable stage.** "Anywhere in the parent" (`03-§4.1`) means *any line among the flows*, **not inside a `\|`** — a called file runs its own self-contained flows; it doesn't take/return the current layer (parameterless in v1). The grammar already makes `call` top-level (`10-§3`). | **clarified** — `03-§4.1` |
| 19 | **No in-memory handoff.** A parent and a called file share data **only via saved files** (`acquire.niva` writes `work/*.gpkg`; `analyze.niva` `load`s them) or the live project (`add`) — there is no shared `current` layer. | **by design** — the procedural-include model; **parameterized `call` (v2)** adds in-memory handoff (`04`) |
| 20 | **Path-resolution split.** The **`call` target** resolves relative to the **caller**; but **data paths inside flows** (`work/buildings.gpkg`) resolve against the **run's working dir** (`09-§6a`), so `work/` means the same thing in `acquire.niva` and `analyze.niva`. | **spec'd** — `03-§4.1` |
| 21 | **Provenance across calls.** The run **journal** should be one continuous record with each op tagged by **source file**; a saved layer's **lineage** should note the **call chain** (`analyze.niva → acquire.niva`). | **spec'd** — `08-§2/§3` |
| 22 | **Error location across files.** A failure in `acquire.niva` must name **that file + line/stage**, not just the parent. | **spec'd** — extends `02-§6` |
| 23 | **Nesting & cycles.** `a → b → c` is allowed; `a → b → a` is a hard error (call-stack), with a **max-depth** backstop. | **spec'd** — `03-§4.1` |

---

## 10. Round 5 — the `assess` / lineage round-trip (provenance)

Provenance must survive steps that **aren't a single QGIS algorithm**, and survive
**across runs**. Worked across two:

**Run 1 — prepare, recording lineage on `save`:**
```
load raw_parcels.gpkg | assess to docs/raw_quality.md
load raw_parcels.gpkg | filter "landuse = 'R'" | reproject EPSG:2262 | buffer 100m | save mid/res_buffers.gpkg
```
`mid/res_buffers.gpkg` `metadata.history` gains (`08-§3`):
```
filter landuse='R'        (native:extractbyexpression)
reproject → EPSG:2262     (native:reprojectlayer)
buffer 100m               (native:buffer DISTANCE=328.08)
source: raw_parcels.gpkg · niva x.y · QGIS 4.0.3 / GDAL 3.12.2 · CRS 4269→2262
```

**Run 2 — consume, with a `sql` step and a multi-input `clip`:**
```
load mid/res_buffers.gpkg | assess                            # surfaces Run-1's 3-step lineage
load mid/res_buffers.gpkg
  | sql "SELECT *, ST_Area(geometry) AS area FROM input1"     # virtual SQL — NO QGIS algorithm
  | clip city.gpkg                                            # multi-input — whose lineage?
  | save final/result.gpkg
```

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 24 | **Non-algorithm steps in lineage.** `sql` has no `native:*` id; `load` is a read. | **spec'd** — a `sql` `OpRecord`/lineage entry records the **SQL text + engine + connection** (secrets redacted), `algorithm="sql"`; `load` records the **source**, not a step (`08-§2`) |
| 25 | **Multi-input lineage merge.** `clip`/`join`/`intersect` derive the output from **2+ inputs**; the result's history should reflect **all** contributors, not just the primary. | **spec'd** — flatten each input's history into the output, tagged by role (`input:`/`overlay:`…), then the op — a flattened audit log, since `QgsLayerMetadata.history` is a list, not a DAG (`08-§3`) |
| 26 | **What counts as "data-altering"?** `08-§3` said a "narrowing `filter`" is omitted — but a `filter` *defines what the output IS* ("residential parcels"), so it's provenance-relevant. | **fixed** — record steps that change geometry, attributes, **or the feature set** (`filter`/`extract` included); only non-modifying steps (`assess`/`describe`) are omitted (`08-§3`) |
| 27 | **DB sources carry no lineage store.** A `@conn`/`db_table` read has no `QgsLayerMetadata.history`; `assess` shows "(none)". | **noted** — v1 writes lineage to the **file** output on `save`; DB-side lineage is a v2 (DB-writes) concern (`08`) |
| 28 | **The `assess` report should be self-documenting.** | **spec'd** — `assess to report.md` stamps source(s) + niva/QGIS/GDAL versions + timestamp (`08-§4`) |

---

## 11. Round 6 — the `add`-to-live-project path (interactive)

The one path that needs a **running QGIS** — it stresses `as_qgs()`, project state,
threading, and styling. Worked in the QGIS Python Console (a live session):

```
# QGIS Python Console — a project is open
niva.flow("""
load parcels.gpkg | filter "landuse = 'R'" | buffer 100m
  | save out/res_buffers.gpkg      # persist…
  | add residential_buffers        # …and register the saved layer in the open project
""")
```

…and the **same flow headless**:
```
$ niva run that_flow.niva
# `add` step → "skipping add (no live QGIS session); the result was saved to out/res_buffers.gpkg"
```

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 29 | **`add` needs a live session.** Headless (`niva run`, CI) there's no project/canvas. | **spec'd** — headless `add` **warns and skips**; a flow whose **only** sink is `add` **errors** headless ("no persistent output; use `save`") (`03-§2.7`) |
| 30 | **`add` registers a *temporary* layer** — a pipeline temp becomes a scratch project layer, **lost on QGIS close** unless also saved. | **spec'd** — `save … \| add` (or add a saved file) persists; documented (`03-§2.7`) |
| 31 | **Are sinks terminal or pass-through?** `save … \| add` needs `save` to pass the layer on. | **decided** — **sinks pass through**: `save`/`add` return the current layer unchanged and **chain** (`03-§2.7`; `02-§2a` corrected) |
| 32 | **Default name + styling.** What's the project layer called, and how is it styled? | **spec'd** — name defaults to the derived name (`add <name>` overrides); the layer gets QGIS's **default style** — **no niva styling verb in v1** (symbology is v2.x, `06-§6`) |
| 33 | **Threading.** `add` mutates `QgsProject` — **main-thread only**; an `add`-flow can't run on a background `QgsTask` and blocks the GUI on long ops. | **noted** — plugin does heavy work on a task, the `add` on the main thread at the end (Oscar A9/L9) |
| 34 | **`as_qgs()` across kinds.** `add` of a raster (e.g. a slope output) must return a `QgsRasterLayer`. | **ties to A10** — needs the vector/raster handle facet (`02-§3.1`) |

---

> **Pattern to take away:** every verb is *one positional for the main thing,
> flags for on/off, `key=value` for the rest* — and `describe`/`--dry-run` always
> show the real QGIS call underneath. Learn that shape once and all ~40 verbs read
> the same. (Rasters — §7; SQL — §8; `call` composes files — §9; provenance
> survives all of it — §10; `add` needs a live QGIS — §11.)
