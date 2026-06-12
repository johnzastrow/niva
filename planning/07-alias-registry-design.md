# Niva — Alias Registry Design

_How niva maps its friendly verbs onto QGIS Processing algorithms: the data
model, the grammar→parameter binding, type coercion, validation against the live
registry, and the raw escape hatch. Status: design draft — niva is not built.
Builds on `01-prd.md` (grammar), `06-qgis-surface-reference.md` (the surface),
and the open questions in `00-…`._

---

## 1. What the registry is, and why

The alias registry is the curated layer between niva's readable grammar and
QGIS's raw Processing API. Recall the gap (`06-§2.3`): a one-sentence intent
("buffer by 100, dissolve, clip to the city") is, in PyQGIS, a pile of `ALL_CAPS`
params, magic enum integers, an explicit `OUTPUT` sink, and manual output
threading:

```python
buf = processing.run("native:buffer", {"INPUT":"roads.gpkg","DISTANCE":100,
  "SEGMENTS":5,"END_CAP_STYLE":0,"JOIN_STYLE":0,"MITER_LIMIT":2,
  "DISSOLVE":True,"SEPARATE_DISJOINT":False,"OUTPUT":"TEMPORARY_OUTPUT"})["OUTPUT"]
processing.run("native:clip", {"INPUT":buf,"OVERLAY":"city.gpkg","OUTPUT":"roads_local.gpkg"})
```

The registry is what turns that into:

```
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

It does four jobs:
1. **Name** — `buffer` → `native:buffer` (a friendly verb per common algorithm).
2. **Shape** — positionals/options/flags → the `ALL_CAPS` param dict.
3. **Default** — fill QGIS's required-but-boring params (segments, cap style…).
4. **Translate** — words → enum integers, `EPSG:3857` → a CRS, etc.

It is **data, not code**: a declarative table that can be diffed, linted against
the installed QGIS, and edited by someone who isn't a niva core dev.

---

## 2. Scope — what the registry covers (and what it doesn't)

The registry maps **Processing algorithms only** (surface 1 in `06-§1`). The other
surfaces are reached by a small set of **built-in verbs** that are *not* registry
entries, because they don't wrap a single algorithm:

| Verb | Kind | Backed by |
|------|------|-----------|
| `load` / `save` | built-in | layer I/O + output materialization |
| `filter` | built-in | a raw QGIS **expression** → `native:extractbyexpression` |
| `compute` | built-in | field calculator (raw expression) |
| `sql` | built-in | DB / OGR / virtual-layer **SQL** passthrough (`06-§4`) |
| `run` | built-in | the **raw escape hatch** — any algorithm by id (§8) |
| `buffer`, `clip`, `dissolve`, … | **registry alias** | one `native:*`/`gdal:*` algorithm |

This honours the namespace decision from `06-§8.1`: `buffer` is always the
**algorithm**; `ST_Buffer` is reached only via the explicit `sql` verb; the
`buffer()` expression function only inside `filter`/`compute` strings. One name,
one meaning, per surface.

> **Relationship to existing QGIS automation.** QGIS already ships two multi-step
> automation surfaces — the **Graphical Modeler** (visual node graph) and **Batch
> Processing** — both built on the same algorithm/parameter/`processing.run`
> model this registry wraps ([QGIS Processing manual][qgis-proc]). niva's pipeline
> is a **readable text counterpart to the Modeler**: same engine, same algorithm
> ids, same `TEMPORARY_OUTPUT` sink convention, expressed as one line instead of a
> diagram. The alias registry is what makes the text form concise where the
> Modeler leans on dialogs and the toolbox on search.
>
> [qgis-proc]: https://docs.qgis.org/3.44/en/docs/user_manual/processing/index.html

---

## 3. Anatomy of an alias entry

A declarative schema (shown as YAML; TOML/JSON equivalent). Full `buffer` entry,
grounded in its real signature (`06-§2.3`):

```yaml
buffer:
  algorithm: native:buffer
  summary: Expand (or shrink) geometries by a distance.
  primary_input:  INPUT          # receives the piped upstream layer
  primary_output: OUTPUT         # the produced layer (temp, or materialized by `save`)
  args:                          # ordered positionals: `buffer 100`
    - { name: distance, param: DISTANCE, type: distance, required: true }
  options:                       # `key value`: `buffer 100 segments 8 cap flat`
    segments: { param: SEGMENTS,      type: int,    default: 5 }
    cap:      { param: END_CAP_STYLE, type: enum,   default: round,
                values: { round: 0, flat: 1, square: 2 } }
    join:     { param: JOIN_STYLE,    type: enum,   default: round,
                values: { round: 0, miter: 1, bevel: 2 } }
    miter:    { param: MITER_LIMIT,   type: number, default: 2 }
  flags:                         # bare words that set a boolean: `... dissolve`
    dissolve: { param: DISSOLVE }
    separate: { param: SEPARATE_DISJOINT }
  forced: {}                     # params pinned by niva, never user-facing
```

Field reference:

| Field | Meaning |
|-------|---------|
| key (`buffer`) | the niva verb |
| `algorithm` | the QGIS algorithm id it wraps |
| `summary` | one-line help (also drives `niva help buffer`) |
| `primary_input` | the param that the **upstream pipe** feeds (a `source`/`raster`) |
| `primary_output` | the **sink** param niva manages (temp between steps; path on `save`) |
| `args` | ordered **positional** arguments → params |
| `options` | `key value` named parameters → params (with `default`) |
| `flags` | bare-word **booleans** → params (present = `true`) |
| `forced` | params niva always sets to a fixed value (not surfaced) |
| each binding | `param` (QGIS name), `type` (niva type, §5), `required`, `default`, `values` (enum vocab) |

Algorithms with a **second input** bind it as a positional of type `layer`
(e.g. `clip`'s overlay):

```yaml
clip:
  algorithm: native:clip
  primary_input: INPUT
  primary_output: OUTPUT
  args:
    - { name: overlay, param: OVERLAY, type: layer, required: true }   # `clip city.gpkg`
```

---

## 4. Grammar → parameter binding

A pipeline step is:

```
verb  [positional ...]  [option value ...]  [flag ...]
```

The binder builds the `processing.run` dict by walking the entry:

1. **`primary_input`** ← the upstream layer handle (the previous step's output, or
   the `load`ed source for the first step).
2. **positionals** ← consumed in `args` order. A token is a positional if it is
   not a known option key or flag word. `buffer 100` → `DISTANCE=100`.
3. **options** ← `key value` pairs where `key ∈ options`. `segments 8` →
   `SEGMENTS=8`. Unspecified options fall back to their `default`.
4. **flags** ← bare words in `flags`. `dissolve` → `DISSOLVE=true`; absent → `false`.
5. **defaults & forced** ← every remaining required param gets its `default`
   (from options/args) or `forced` value.
6. **`primary_output`** ← `TEMPORARY_OUTPUT` for intermediate steps; the `save`
   destination for the terminal step. **niva owns the output lifecycle** — the
   user never writes `OUTPUT=` (this is the threading the registry removes).

Worked binding — `buffer 100 segments 8 cap flat dissolve`:

```python
{"INPUT": <upstream>, "DISTANCE": 100, "SEGMENTS": 8,
 "END_CAP_STYLE": 1, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
 "DISSOLVE": True, "SEPARATE_DISJOINT": False, "OUTPUT": "TEMPORARY_OUTPUT"}
```

Ambiguity rules (to keep the parser predictable):
- Option keys and flag words share a namespace per verb and must be unique.
- Positionals are **required and ordered**; a verb has few (usually 0–2). Rich
  configuration goes through named options, never long positional lists.
- An unknown token for a verb is an **error with a suggestion**, never silently
  dropped.

---

## 5. The niva type system & coercion

Each binding has a niva `type` that maps a grammar token to a QGIS parameter
value. The type set deliberately mirrors QGIS's parameter types (`06-§2.3`):

| niva type | grammar token | coerces to | QGIS param types |
|-----------|---------------|------------|------------------|
| `distance` / `number` | `100`, `2.5` | float | `distance`, `number` |
| `int` | `8` | int | `number` (integer) |
| `boolean` | flag presence | bool | `boolean` |
| `enum` | word | int via `values` | `enum` |
| `enumlist` | `mean,min,max` | list[int] via `values` | `enum` (multiple) |
| `crs` | `EPSG:3857` | CRS string | `crs` |
| `field` | `pop` | field name (validated vs schema if known) | `field` |
| `layer` | path / `@name` / upstream ref | source | `source`, `vector`, `raster` |
| `raster` | path | raster source | `raster` |
| `string` | quoted / bareword | string | `string` |
| `expression` | quoted QGIS expression | passthrough | `expression` |
| `extent` | `xmin,ymin,xmax,ymax[ crs]` | extent | `extent` |
| `coordop` | PROJ pipeline string | string | `coordinateoperation` |

Coercion is **fail-closed**: a token that doesn't parse for its type is a clear
error (`cap flatish → unknown value 'flatish'; expected round|flat|square`),
never a silent default.

---

## 6. Enum handling — words, not magic integers

QGIS enums are integer-indexed (`END_CAP_STYLE`: 0/1/2). The registry's `values`
map gives each a word. Two principles:

- **Vocabulary is curated but checkable.** The word→int map is hand-authored for
  readability, but the validator (§9) confirms each integer is a valid index for
  that algorithm's enum **and**, where QGIS exposes the option strings, that the
  words line up — so a QGIS update that reorders an enum is caught, not silently
  mis-mapped.
- **`enumlist` for multi-value enums** (e.g. `STATISTICS=[0,1,2]`): the user writes
  `stats mean,min,max`; the registry maps each word and emits the int list.

```yaml
zonalstats:
  algorithm: native:zonalstatisticsfb
  primary_input: INPUT
  primary_output: OUTPUT
  args:
    - { name: raster, param: INPUT_RASTER, type: raster, required: true }
  options:
    band:   { param: RASTER_BAND,  type: int,    default: 1 }
    prefix: { param: COLUMN_PREFIX, type: string, default: "_" }
    stats:  { param: STATISTICS, type: enumlist, default: [count, sum, mean],
              values: { count: 0, sum: 1, mean: 2, median: 3, stdev: 4,
                        min: 5, max: 6, range: 7, minority: 8, majority: 9,
                        variety: 10, variance: 11 } }
```
`load zones.gpkg | zonalstats dem.tif band 1 stats mean,min,max prefix elev_`.

---

## 7. Input / output wiring

- **Primary input** is the one `source`/`raster` param fed by the pipe. Most algos
  have exactly one obvious input; the registry names it explicitly (no guessing).
- **Secondary inputs** (clip's `OVERLAY`, join's `INPUT_2`/`FIELD_2`) are bound as
  positionals or options of type `layer`/`field`. They can reference a file, a
  `@connection`, or a **named upstream branch** (for non-linear pipelines — a
  later grammar concern).
- **Primary output** is the sink niva threads. Algorithms with **extra outputs**
  (e.g. `native:joinattributestable` also returns `JOINED_COUNT`,
  `UNJOINABLE_COUNT`) declare only the primary in the alias; the others are
  available via `run` (§8) or a future `outputs` extension. This keeps the common
  path simple.

---

## 8. The raw escape hatch — full-coverage guarantee

Curating 769 algorithms is neither possible nor necessary on day one. The `run`
built-in calls **any** algorithm by id with raw param names, so the entire
surface is always reachable even with zero aliases:

```
run native:pointsalonggeometry INPUT=@upstream DISTANCE=50 | save pts.gpkg
run gdal:warpreproject INPUT=dem.tif TARGET_CRS=EPSG:3857 RESAMPLING=1 OUTPUT=out.tif
```

`run` still benefits from the engine's input/output threading (`INPUT=@upstream`,
implicit `OUTPUT`), but does **no** aliasing, defaulting, or enum translation —
it's the literal Processing call in pipeline clothing. Aliases are then a
**progressive enhancement**: curate the common 80, leave the long tail to `run`.

This also defines a clean **promotion path**: a frequently-used `run` invocation
is the signal to add a curated alias.

---

## 9. Generation & validation against the live registry

The registry must never drift from the installed QGIS. Two tools:

**Scaffolder** — reads the live Processing registry and emits a *starter* alias
entry per algorithm: verb = last id segment, `primary_input` = first `source`/
`raster` param, `primary_output` = first `sink`, options = remaining params with
the algorithm's own defaults, enums listed with their option strings as candidate
words. A human then curates (rename verb, choose positionals, pick enum words).
This bootstraps coverage from the `06` inventory rather than hand-typing 769 dicts.

**Linter (`niva doctor` / CI)** — validates every alias against the live registry:

1. `algorithm` id exists.
2. `primary_input` / `primary_output` exist and are of input/sink type.
3. every `param` referenced in args/options/flags/forced exists on the algorithm.
4. **every REQUIRED algorithm param is covered** by an arg, option(+default),
   flag, forced value, or the primary input/output — so a niva call can never
   omit a required param and fail at runtime.
5. every `enum` integer is a valid index; word labels reconciled with the
   algorithm's option strings where available.
6. no duplicate verb; no option/flag name collision within a verb.

Run in CI across a **matrix of QGIS versions** (and provider sets — GRASS/GDAL
present or not). A failure means "this alias is invalid on QGIS X.Y", caught
before release, not by a user.

---

## 10. Worked examples (entry → niva → run dict)

| niva | resulting `processing.run` |
|------|----------------------------|
| `… \| buffer 100 dissolve` | `native:buffer {INPUT,DISTANCE:100,SEGMENTS:5,END_CAP_STYLE:0,JOIN_STYLE:0,MITER_LIMIT:2,DISSOLVE:True,SEPARATE_DISJOINT:False,OUTPUT}` |
| `… \| clip city.gpkg` | `native:clip {INPUT,OVERLAY:'city.gpkg',OUTPUT}` |
| `… \| dissolve by zone` | `native:dissolve {INPUT,FIELD:'zone',SEPARATE_DISJOINT:False,OUTPUT}` |
| `… \| reproject EPSG:3857` | `native:reprojectlayer {INPUT,TARGET_CRS:'EPSG:3857',CONVERT_CURVED_GEOMETRIES:False,TRANSFORM_Z:False,OUTPUT}` |
| `… \| zonalstats dem.tif stats mean,max prefix elev_` | `native:zonalstatisticsfb {INPUT,INPUT_RASTER:'dem.tif',RASTER_BAND:1,STATISTICS:[2,6],COLUMN_PREFIX:'elev_',OUTPUT}` |
| `… \| filter "area($geometry) > 1000"` | `native:extractbyexpression {INPUT,EXPRESSION:'area($geometry) > 1000',OUTPUT}` |
| `sql @city "UPDATE roads SET geom=ST_Buffer(geom,100)"` | `native:spatialiteexecutesql {DATABASE:'city',SQL:…}` |

(`dissolve by zone` shows an option whose key word is `by` → `FIELD`; alias
options can use natural words, not just the param name.)

---

## 11. Storage & layout

```
niva/registry/
  core.yaml          # curated aliases: buffer, clip, dissolve, reproject, …
  raster.yaml        # raster-group aliases
  enums.yaml         # shared enum vocabularies (cap/join/resampling/stats…)
  _generated.yaml    # full scaffolded stubs (uncurated long tail; optional)
  schema.py          # dataclasses + loader + validator
```

- Curated files are small, reviewable, and grouped by domain.
- Shared enum vocabularies live once and are referenced, so `resampling` words are
  consistent across every raster alias.
- The loader parses YAML into dataclasses; the validator (§9) runs on load (dev)
  and in CI (release).

Why data files over hardcoded Python: diffable in review, editable by domain
experts, lintable against multiple QGIS builds, and serializable for a future
`niva aliases` introspection command.

---

## 12. Open questions

1. **Provider preference order (decided).** When more than one provider offers a
   capability, the registry resolves to the **most-preferred available** one:
   `native` → `gdal` → `qgis` → `pdal` → … → **`grass` / `saga` last**. GRASS and
   SAGA are heavier, externally dependent, and use different conventions, so a
   curated verb **never** resolves to them when a native/gdal option exists; they
   stay reachable via `run grass:*` / `run saga:*` or an explicit qualified alias
   (e.g. a deliberate `gbuffer`). Same-name natives (`native:buffer` vs
   `gdal:buffer`) prefer `native`. (Open: where a GRASS/SAGA-only capability like
   TSP earns a *curated* verb vs staying `run`-only.)
2. **Enum drift.** Reconciling curated words with QGIS's option strings
   automatically vs by hand — how much can be generated (§9.5)?
3. **Multi-output algorithms** (join counts, fail outputs): keep them `run`-only,
   or add an `outputs:` block and a grammar for capturing secondary outputs?
4. **Field/CRS validation timing.** Validate `field` names against the actual
   layer schema at parse time (needs the layer loaded) or defer to runtime?
5. **Localization.** QGIS param descriptions are translated; niva verbs/words are
   English. Keep the registry English-only, or allow localized alias packs?
6. **Where does the line sit** between a curated alias and `run`? A size target
   (e.g. the ~80 algorithms covering 95% of everyday use) would scope the MVP
   registry (`03-mvp-scope.md`).

---

_Next: `02-architecture.md` should absorb the input/output handle contract this
design depends on (what a "layer handle" is as it threads algorithm → sql →
algorithm), and `03-mvp-scope.md` should pick the initial curated verb set._
