# Niva — Verb Reference (worked)

_Fully explains the verb model, then walks verbs from simple to complex and
composes them. Companion to `03` (the verb list), `07` (the registry that powers
verbs), and `10` (the grammar). The niva flows are **illustrative** — niva isn't
built yet — but every **algorithm id, parameter, default, and enum-by-word mapping
shown was verified against the live QGIS 4.0.3 registry** (the grammar is the
proposal; the QGIS call it resolves to is real)._

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

### Issues this round surfaced
| # | What surfaced | Verdict |
|---|---------------|---------|
| 11 | **Three forms, three mechanisms** — and the `*executesql` algorithms are **write-only** (no output), so a `SELECT` does *not* use them; reads use a query layer / `gdal:executesql` / `qgis:executesql`. | **fixed** — `03-§2.6`; `06-§4` corrected |
| 12 | **A SELECT result isn't self-describing.** Virtual-layer SQL **requires** uid + geometry + geometry-type + **CRS**; a DB query layer needs a unique key + geometry column. | **spec'd** — auto-detect, else `sql … key= geom= crs=` (`03-§2.6`) |
| 13 | **Table naming.** Bare `sql` references the piped/loaded layers as **`input1`**, `input2`, … (QGIS convention). | **spec'd** — `03-§2.6` |
| 14 | **Read-only detection for v1.** "Starts with SELECT" misses `WITH … SELECT` / `SELECT … INTO` / side-effecting functions. | **spec'd** — allow top-level `SELECT`/`WITH … SELECT`, run in a **read-only transaction**; else "writes are v2" (`03-§2.6`) |
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

> **Pattern to take away:** every verb is *one positional for the main thing,
> flags for on/off, `key=value` for the rest* — and `describe`/`--dry-run` always
> show the real QGIS call underneath. Learn that shape once and all ~40 verbs read
> the same. (Rasters add a wrinkle — §7; SQL is its own world — §8; `call` composes
> files, not layers — §9.)
