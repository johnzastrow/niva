# Niva — v1 MVP Scope

_Status: draft for review. The concrete v1 boundary: the grammar, the verb set, the
runner, the backend. In the roadmap's numbering this MVP ships as **v0.1**; "v1"
below means the first/MVP line (`04-roadmap.md`)._

## 1. The grammar

A **flow** is a chain of **stages** joined by `|`. Each stage is:

```
verb  [positional…]  [flag…]  [key=value…]
```

```mermaid
flowchart LR
    subgraph Stage
      direction LR
      V["verb<br/><b>buffer</b>"]:::v --> POS["positional<br/><b>100</b><br/>(→ distance)"]:::p --> FL["flag<br/><b>dissolve</b><br/>(→ on)"]:::f --> KV["key=value<br/><b>segments=16</b>"]:::k
    end
    classDef v fill:#1f6feb,color:#fff
    classDef p fill:#238636,color:#fff
    classDef f fill:#9a6700,color:#fff
    classDef k fill:#6e40c9,color:#fff
```

Rules (kept simple so the syntax never reads like code):
- **Stages joined by `|`**; whitespace and newlines around `|` are insignificant.
- **First bare value** = the verb's primary argument (per-verb; e.g. `buffer 100` →
  distance, `clip city.gpkg` → overlay).
- **Bare word** = an on/off flag (`dissolve`).
- **`key=value`** = any other parameter, only when needed.
- **`|` is the chain**: each stage's output feeds the next stage's input automatically.
- Quote values containing spaces; `#` starts a comment.

> **❓ Open (see `00 §8`):** Is `load` required to start a flow, or may the first
> stage take a path directly (`buffer roads.gpkg 100 | …`)?

### 1.1 Distances & units (decided — was a v1 blocker, G1)

Every distance/tolerance value (`buffer`, `simplify`, `grid`, …) resolves so:

- **A bare number is in the layer's CRS units** (matches QGIS): `buffer 100` on a
  metre-based layer is 100 m.
- **An explicit unit suffix is the recommended form**, converted to the layer's
  CRS units: `m`, `km`, `cm`, `ft`, `yd`, `mi`, `nmi` (and `deg` for degrees).
  `buffer 100m` on a feet-based layer → 328.08 ft.
- **Geographic-CRS guard — no silent wrong results.** A linear (or bare) distance
  on a **degrees** CRS (e.g. EPSG:4326) is a **hard error** with the fix: *"this
  layer is in degrees; `reproject` to a projected CRS first (niva suggests a UTM
  zone), or pass a `deg` value."* niva **never silently buffers in degrees** — the
  classic beginner footgun (Oscar D2). `100deg` opts into degrees explicitly.
- The unit and any conversion are **recorded in lineage** (`08`).

> **v0.2 convenience:** auto-handle a linear distance on a geographic CRS by
> reprojecting to an appropriate equidistant/UTM CRS, buffering, and reprojecting
> back (recorded in lineage) — so `buffer 100m` on lat/long "just works." v1 errors
> with guidance rather than guessing a projection.

```mermaid
flowchart LR
    L["load roads.gpkg"] -->|output| B["buffer 100 dissolve"]
    B -->|"output → input"| C["clip city.gpkg"]
    C -->|"output → input"| S["save out.gpkg"]
```

### 1.2 CRS handling (decided — closes G3)

- niva **works in each layer's own CRS and never silently reprojects an input.**
  `reproject <crs>` is the only verb that changes a CRS.
- **Multi-input ops** (`clip`, `intersect`, `spatialjoin`, …): if a secondary
  layer's CRS differs from the primary's, niva reprojects the **secondary** to the
  primary's CRS automatically and **records it in lineage** (matches QGIS; the
  common, safe case). A mixed-CRS op emits a one-line note, not an error.
- **A layer with no CRS** is a **hard error** — *"`<layer>` has no CRS; assign one
  before processing"* — niva never guesses a CRS.
- **Distances on a geographic CRS:** the degrees guard from §1.1 (a linear/bare
  distance on a degrees CRS errors with a `reproject` fix).
- **Output CRS = the current layer's CRS** — `save` never reprojects (§2.5).

## 2. The initial verb set

v1 ships a **curated ~40-verb set** — the slice of the 769-algorithm surface
(`06`) that covers the everyday analyst workflow in `use_cases.md` (acquire →
prepare → explore → analyze → produce). Everything else stays reachable via the
`run` escape hatch (`07-§8`). Each verb is a friendly name mapped to one real
algorithm through the alias registry (`07`); all algorithm ids below are verified
present in QGIS 4.0.3 (`reference/qgis-algorithms-4.0.3.tsv`).

> **Naming & grammar note.** These verb names are canonical (`where` and `calc`
> are historical synonyms for `filter` and `compute`). Parameters use
> **`key=value`** (the lexer in `02 §2`); the space-form `key value` in some `07`
> examples is illustrative only. The registry (`07`) is the source of truth for
> each mapping.

### 2.1 Built-in verbs (engine-level, not registry aliases — `07-§2`)

| verb | argument | does |
| :-- | :-- | :-- |
| `load` | path / URI / `@conn.table` | start a flow from a file, OGR source, or DB table |
| `save` | path | materialize the current layer to disk — the persisting step |
| `add` | name? | register the current layer in the live QGIS project |
| `sql` | `"SELECT …"` [`from` src \| `@conn`] | run spatial SQL; a `SELECT` result becomes the current layer (read passthrough — `06-§4`) |
| `filter` | expression | keep features matching an expression → `native:extractbyexpression` |
| `compute` | `field=` `expr=` | add/update a field via the expression engine → `native:fieldcalculator` |
| `run` | `id KEY=value…` | escape hatch — any algorithm by id |
| `find` | term | search verbs / algorithms (`find dissolve`) |
| `describe` | verb | show a verb's mapping + parameters (`describe buffer`) |

### 2.2 Tier 1 — core registry aliases (ship first)

The must-have geoprocessing the canonical use case needs.

| verb | primary arg | key params / flags | algorithm |
| :-- | :-- | :-- | :-- |
| `buffer` | distance | `dissolve`, `segments=`, `cap=`, `join=` | `native:buffer` |
| `clip` | overlay | — | `native:clip` |
| `intersect` | overlay | — | `native:intersection` |
| `union` | overlay | — | `native:union` |
| `difference` | overlay | — | `native:difference` |
| `dissolve` | field? | — | `native:dissolve` |
| `reproject` | target_crs | `operation=` | `native:reprojectlayer` |
| `fix` | — | — | `native:fixgeometries` |
| `explode` | — | — | `native:multiparttosingleparts` |
| `merge` | extra layers | `crs=` | `native:mergevectorlayers` |
| `join` | `with=` | `field=`, `field2=`, `fields=`, `prefix=` | `native:joinattributestable` |
| `spatialjoin` | `with=` | `predicate=`, `prefix=` | `native:joinattributesbylocation` |
| `extract` | — | `field=`, `op=`, `value=` | `native:extractbyattribute` |
| `selectloc` | overlay | `predicate=` | `native:extractbylocation` |
| `centroid` | — | — | `native:centroids` |

### 2.3 Tier 2 — completes the v1 set

| verb | primary arg | algorithm | | verb | primary arg | algorithm |
| :-- | :-- | :-- |:-:| :-- | :-- | :-- |
| `convexhull` | — | `native:convexhull` | | `refactor` | `fields=` | `native:refactorfields` |
| `simplify` | tolerance | `native:simplifygeometries` | | `drop` | `fields=` | `native:deletecolumn` |
| `smooth` | — | `native:smoothgeometry` | | `retain` | `fields=` | `native:retainfields` |
| `pointonsurface` | — | `native:pointonsurface` | | `rename` | `field=` `to=` | `native:renametablefield` |
| `boundingbox` | — | `native:boundingboxes` | | `promote` | — | `native:promotetomulti` |
| `voronoi` | — | `native:voronoipolygons` | | `countpoints` | points | `native:countpointsinpolygon` |
| `grid` | spacing | `native:creategrid` | | `zonalstats` | raster | `native:zonalstatisticsfb` |
| `vertices` | — | `native:extractvertices` | | `sample` | raster | `native:rastersampling` |

That is **9 built-in + 15 Tier 1 + 16 Tier 2 ≈ 40 verbs**. The count is
affordable because each alias is *data* in the registry (`07`), not code — the
engine runs them uniformly. Tier 1 is the ship-first cut; Tier 2 rounds out v1.

> **❓ Open (see `00 §8`):** two-argument verbs. Is `compute area_m2="$area"` the
> form, or `compute field=area_m2 expr="$area"`? Proposal: one bare positional for
> the primary arg (`buffer 100`, `clip city.gpkg`), named `key=value` for the rest.
> Confirm.

### 2.4 The canonical use case, end to end

The `use_cases.md` analyst (cat-canvassing in Youngstown, NY) is a full
multi-source, multi-CRS, multi-format data-science workflow. niva covers it
**native-first** — the provider preference order (`07-§12.1`): prefer `native`,
then `gdal`/`qgis`/`pdal`, and use **GRASS only as a last resort** where nothing
else can.

| step (`use_cases.md`) | niva — preferred provider first |
| :-- | :-- |
| 1. document + assess originals | `assess` + `metadata` (08) — native |
| 2. reproject/warp to a local SRS | `reproject` (native) · `warp` (gdal, v0.2) |
| 3. clip to village bounds | `clip` — native |
| 4. geocode addresses → points | `run native:batchnominatimgeocoder`, or address-`join` to building outlines — native |
| 5. routable street network | native network prep where possible |
| 6. select cat-homes meeting criteria | `load @cats_pg.homes` · `sql` · `join` · `filter` (exclude dog/bird) — native / PostGIS |
| 7. routes (foot/bike, avoid steep slopes) | lidar→DEM `run pdal:exportraster` (PDAL) → `slope` (native) → cost-surface + TSP fall to **GRASS** here only (`r.cost`, `v.net.salesman`) — no native equivalent |
| 8. maps + per-canvasser handouts | `run native:atlaslayouttomultiplepdf` — native (atlas, one page/route) |
| 9. documented repository | lineage/provenance on every `save` (08) — native |

So **only step 7's cost-surface routing/TSP touches GRASS** — everything else is
native/gdal/pdal/PostGIS. Illustrative slice (steps 1–3, 6):

```
load "ny_state.gdb|layername=buildings" | assess to docs/buildings_quality.md
load "ny_state.gdb|layername=buildings" | reproject EPSG:6350 | clip village.gpkg
  | save work/buildings.gpkg
sql @cats_pg "SELECT * FROM human_homes h JOIN cat_homes c USING (address)
              WHERE c.has_cat AND NOT h.has_dog AND NOT h.has_bird"
  | save work/target_homes.gpkg
```

**Provider preference.** GRASS (307 algos) and SAGA are the **least-preferred**
backends — heavier, externally dependent, different conventions — so niva reaches
them **last, only when native/gdal/qgis/pdal cannot do the job** (here: TSP via
`grass:v.net.salesman`, cost surface via `grass:r.cost`). They stay reachable via
`run grass:*`; a curated verb never resolves to GRASS when a native option exists
(`07-§12.1`). True route optimization (TSP) is absent from *native* QGIS but
reachable — so it is not blocked, just not a curated v1 verb (§6).

### Meta verbs
(`run` / `find` / `describe` are the built-ins in §2.1.)

### 2.5 `save` semantics (decided — was a v1 blocker, G2)

`save <path>` writes the current layer. Pinned behavior:

- **Format** is inferred from the extension (`.gpkg`→GeoPackage, `.shp`→Shapefile,
  `.geojson`, `.fgb`→FlatGeobuf, …). **Default = GeoPackage**; a path with no
  extension gets `.gpkg`.
- **Layer name** in a container defaults to the file's base name. Name or add a
  layer in a GeoPackage with `save city.gpkg as roads` — a `.gpkg` holds many
  layers, and this replaces/creates only the `roads` layer, leaving others intact.
- **Overwrite (the data-loss guard).** `save` **replaces the target layer/file by
  default** (re-runnable flows need this), **but refuses to write to a path read as
  a source earlier in the same flow** (don't eat your own input) → hard error.
  `save … append` adds features to an existing layer instead of replacing it.
- **Output CRS is unchanged** — `save` never reprojects; `reproject` first if you
  want a different CRS.
- **Locked target** (open in QGIS / another writer holds the SQLite lock) → a clear
  *"target is locked — close it in QGIS"* error, not a cryptic one (Oscar E5).
- `--dry-run` lists exactly what would be written/replaced before anything happens.

## 3. The `filter` case (keeping expressions non-code-like)

Raw QGIS expressions are the least approachable thing (`"ZONE" = 'R1'` with field
double-quotes). v1's `filter` accepts a **simplified** form and translates it:
- bare field names (no double quotes): `filter ZONE = 'R1'`
- numbers bare, strings single-quoted: `filter POP > 1000`
- `and` / `or`: `filter ZONE = 'R1' and POP > 1000`
- power-user fallback to a raw expression: `filter expr="\"ZONE\" IN ('R1','R2')"`

This is the single most important ergonomics design item in v1 (`01 §8`).

> **❓ Open (see `00 §8`):** How far does the simplified `filter` go in v1 — beyond
> `=`/`<>`/`<`/`>` and `and`/`or`, do we include `IN` / `LIKE` / NULL handling now or
> later? The raw `expr="…"` fallback stays regardless.

## 4. Running a flow (all contexts, same string)

| context | invocation |
| :-- | :-- |
| Headless saved script | `niva run pipeline.niva` |
| Terminal (inline) | `niva "load roads.gpkg \| buffer 100 \| save out.gpkg"` |
| marimo cell / QGIS console | `niva.flow("load roads.gpkg \| buffer 100 \| save out.gpkg")` |
| Power-user Python | `niva.buffer("roads.gpkg", distance=100)` (same engine) |

A **`.niva` script file** holds one or more flows (separated by blank lines), with `#`
comments:

```
# Residential parcels near schools, buffered
load parcels.gpkg
  | filter ZONE = 'R1'
  | buffer 50
  | clip city.gpkg
  | save r1_near.gpkg
```

### 4.1 Calling other `.niva` files (procedural composition)

A `.niva` file **executes procedurally** — top to bottom, one flow after the
next. A **`call <file.niva>`** statement may appear **anywhere** in a parent file;
at that point niva runs the called file's flows inline (procedurally), then
continues. This is how a long workflow is broken into reusable, named pieces — the
plain-language equivalent of an `#include` / `source`, not a programming
construct:

```
# acquire_and_prepare.niva  — reused by several analyses
load "nys.gdb|layername=buildings" | reproject EPSG:2262 | clip village.gpkg | save work/buildings.gpkg
load "niagara/roads.shp"           | reproject EPSG:2262 | fix | clip village.gpkg | save work/roads.gpkg
```

```
# analyze_canvass.niva
call acquire_and_prepare.niva          # runs that file's flows here, then continues
load work/buildings.gpkg | centroid | save work/homes.gpkg
call make_handouts.niva                # a call can sit mid-file, anywhere
```

Rules: calls run in file order at the point they appear; **circular calls are an
error** (niva tracks the call stack); a called file is found relative to the
caller (then a search path). **Passing parameters / the current layer** into a
called file (parameterized macros) is a later extension — see `04-roadmap.md`
(v0.2 plain `call`; v2.0 parameterized) and `00 §8`. v1 keeps calls parameterless
so the grammar stays non-code-like.

## 5. Backend (PyQGIS-only in v1)

- A **single in-process PyQGIS** backend (`processing.run`). It runs both
  **interactively** (a live QGIS session — enables `add`, `as_qgs()`) and
  **headless** (niva initializes a headless `QgsApplication`), so one backend
  covers every context. Decided in `00-§3.3`; see `02-§4`.
- The `qgis_process` backend (+ auto-selection / `--backend`) is **v0.2** — the
  `Backend` ABC is the seam it slots into.

## 6. Explicitly OUT of v1 (see roadmap)

- Control flow in the grammar (variables, branching, loops) → later.
- **SQL writes & connection management** (`UPDATE`/`DELETE`, `CREATE TABLE`,
  import-to-PostGIS, managing `@connections`) → v2. *Read passthrough* (`sql
  "SELECT …"` → layer, `06-§4`) **is in v1** as a built-in (§2.1); it reuses
  QGIS's existing connections by `@name` (`02-§3.5`).
- **Heavy raster processing** (terrain, raster calculator, warp pipelines) →
  v0.2. Raster×vector that the workflow needs (`zonalstats`, `sample`) **is in
  v1** (§2.3).
- **Routing / network optimization** (shortest-path verbs, and TSP — a gap in
  QGIS native algorithms) → later, despite the `use_cases.md` need (§2.4).
- Rendering, layouts, symbology (surface 4, `06-§6`) → later.
- `config` profiles beyond a default-backend setting → v0.2.
- A GUI / QGIS-plugin front end → later.

## 7. Definition of done (v1)

- The grammar (lex/parse/run) executes single- and multi-stage flows; `|` chaining
  threads output→input; `save`/`add` materialize.
- The **~40 curated verbs** (§2: 9 built-in + Tier 1 + Tier 2) run on the PyQGIS
  backend (interactively and headless) with equivalent results on fixtures, and
  every alias passes the registry linter against the installed QGIS (`07-§9`).
- `sql "SELECT …"` read passthrough returns a usable layer from a file (OGR
  `SQLITE` dialect) and from an `@connection`.
- The **same flow string** runs headless (`niva run`), inline (`niva "…"`), and in a
  marimo cell (`niva.flow(...)`).
- `filter` translates the simplified form correctly, with the raw-expression fallback.
- Interop verified: `result.output.as_qgs()` / `.source` / `os.fspath(...)` and a
  GeoPandas round-trip back into a flow via `load`.
- `pip`-installable into QGIS's Python; headless CI green.
