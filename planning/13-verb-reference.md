# Niva — Verb Reference (worked)

_Fully explains the verb model, then walks three verbs from simple to complex and
composes them in one flow. Companion to `03` (the verb list), `07` (the registry
that powers verbs), and `10` (the grammar). Examples are illustrative — niva isn't
built yet._

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

> **Pattern to take away:** every verb is *one positional for the main thing,
> flags for on/off, `key=value` for the rest* — and `describe`/`--dry-run` always
> show the real QGIS call underneath. Learn that shape once and all ~40 verbs read
> the same.
