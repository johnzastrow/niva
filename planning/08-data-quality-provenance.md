# Niva — Data Quality, Provenance & Lineage

_How niva logs operations, assesses incoming data quality, and records processing
steps as formal lineage metadata. Status: design draft — niva is not built. Driven
by `use_cases.md` and three requirements: **log operations**; **document steps
that alter data in formal metadata**; **assess the starting state of data and
document its quality and lineage**. Builds on `06-§2.5` (the surface), `02`
(engine, logging, the layer handle), `03` (verbs)._

---

## 1. Why this is first-class, not a nicety

The `use_cases.md` analyst is explicitly tasked to *"convey the quality of the
data found and used, document the data, document the methods used to prepare the
data."* In a normal data-science workflow that is the **Inspect/Prepare** and
**Communicate** stages. Today QGIS makes all of it manual and GUI-bound.

niva's opportunity: make provenance a **byproduct of doing the work**. Three
connected needs:

1. **Operation log** — a runtime record of every op niva runs (§2).
2. **Lineage in formal metadata** — data-altering steps written into the layer's
   `QgsLayerMetadata.history` (§3).
3. **Starting-state assessment** — profile and quality-check incoming data and
   document it (§4).

The through-line: **the operation log is the raw material for both the methods
documentation and the formal lineage.** Do the work once; get the provenance free.

---

## 2. The operation log (runtime)

Every op the engine runs emits a structured **OpRecord**:

```
OpRecord:
  ts            ISO-8601 UTC
  verb          buffer
  algorithm     native:buffer            # or sql / built-in
  params        {DISTANCE: 50, ...}      # resolved, post-registry
  inputs        [<handle ref>]           # sources / @conn.table
  output        <handle ref>             # temp or saved
  backend       pyqgis | qgis_process
  rows_in/out   1240 / 1240
  elapsed_ms    83
  status        ok | error(message)
```

- Most of this already exists on `Result` (`02-§3`: algorithm, params, elapsed,
  backend) — the log is `Result` made durable and ordered.
- **Two sinks:** a concise **human** line to stderr (per `02-§6`), and a
  structured **JSONL run journal** (`--log run.jsonl` / `NIVA_LOG`).
- A flow's journal is an ordered list of OpRecords — that ordered list **is** the
  machine-readable "methods used" the analyst must document, and the input to §3.
- Lives with `core/logging.py` (`02-§1` package layout).
- **Stable, versioned schema (closes G8).** The journal is **JSON Lines**: one JSON
  object per `OpRecord`, preceded by a header line
  `{"niva_journal": 1, "niva_version": "x.y", "flow": "<path|inline>", "started": "<ts>"}`.
  The `niva_journal` integer is the schema version — a published contract tools can
  parse; fields are added (minor) but not renamed/removed without a bump. Secrets
  in `params`/connections are **redacted** (`12`).

---

## 3. Lineage → formal metadata (on `save`)

When `save` materializes a layer, niva writes the flow's **data-altering** steps
into that layer's formal metadata as history/lineage entries
(`native:addhistorymetadata` → `QgsLayerMetadata.history`):

- **One history entry per data-altering step** (buffer, clip, reproject, fix,
  dissolve, `sql UPDATE`, …). Read-only/derived steps (load, a `filter` that only
  narrows, `describe`) are summarized or omitted (config).
- Each entry: a human-readable line **plus** structured detail (algorithm id, key
  params) so it is both readable and re-runnable.
- Plus a provenance stamp: **source(s)**, niva version, QGIS/GDAL/PROJ versions,
  timestamp, and CRS changes.
- **Chaining:** niva reads any history already on the input layer (so provenance
  carries across tools and sessions) and appends to it rather than replacing.

```
load roads.gdb | reproject EPSG:26918 | fix | buffer 50 | save out.gpkg
# out.gpkg  QgsLayerMetadata.history gains:
#   2026-06-12T14:02Z  reproject → EPSG:26918      (native:reprojectlayer TARGET_CRS=EPSG:26918)
#   2026-06-12T14:02Z  fix geometries              (native:fixgeometries METHOD=structure)
#   2026-06-12T14:02Z  buffer 50                   (native:buffer DISTANCE=50)
#   source: roads.gdb · niva 0.x · QGIS 4.0.3 / GDAL 3.12.2 · CRS 4629→26918
```

> **❓ Open:** lineage-on-`save` **on by default** (the differentiator) with
> `save out.gpkg nolineage` to opt out — or off by default? Proposal: on.

---

## 4. Assessing the starting state — the `assess` verb

`load x | assess` produces a **data-quality + provenance report without altering
the data** — the Inspect stage as one command:

- **Structure:** CRS (and *is it set?* — a common defect), extent, geometry type,
  feature count, field schema (names/types), driver/format. (introspection /
  `layer_property()`)
- **Quality:** invalid geometries (`native:checkvalidity`), duplicate geometries
  (`native:checkgeometryduplicate`), per-field null/empty counts, basic field
  statistics (`native:basicstatisticsforfields`), unique-value cardinality
  (`native:listuniquevalues`).
- **Existing provenance:** any `metadata.history`/lineage already on the layer
  (so the analyst can judge where the data came from).
- **Output:** a printed summary, plus `assess … to report.md|json` for the
  documentation deliverable.
- **`assess --deep`** runs the heavier **Check-geometry** battery (gaps, overlaps,
  slivers, self-intersections, dangles, …) for topological QA.

```
load cats.gdb | assess to data/cat_parcels_quality.md
#  CRS: EPSG:4629 (set) · 2,431 features · MultiPolygon · 18 fields
#  validity: 12 invalid geometries · 3 duplicate geometries
#  nulls: owner_name 41 · parcel_id 0 · zone 7
#  lineage: (none recorded on source)
```

---

## 5. Proposed verbs

| verb | kind | does | backed by |
|------|------|------|-----------|
| `assess` | built-in | data-quality + provenance report (no mutation); `--deep` for topo checks; `to <file>` to save | introspection + `checkvalidity` / `basicstatisticsforfields` / `listuniquevalues` / Check-geometry group |
| `metadata` | built-in | **read** formal metadata (`metadata`), **set** (`metadata set title=… keywords=…`), **apply** (`metadata from x.qmd`), **export** (`metadata export out.xml`) | `layer_property` + `native:set/update/copy/exportlayermetadata` |
| *(auto-lineage)* | engine | record data-altering steps into `metadata.history` on `save` | the run journal (§2) + `native:addhistorymetadata` |
| `checks` | alias group (Tier 2) | run an individual geometry check | `native:checkgeometry*` (21) + `native:checkvalidity` |

---

## 6. Scope / roadmap placement

- **v1:** the **operation log / run journal** (§2) — every op recorded; the journal
  as methods documentation. `assess` (structure + validity + basic stats + read
  existing lineage). These need no metadata-writing and are pure value.
- **v0.2:** **auto-lineage to formal metadata** on `save` (§3); the `metadata`
  read/set/export verbs; `assess --deep` Check-geometry battery.
- **v2:** quality **rules/constraints** (assert + fail a flow on bad data),
  metadata templates, and catalog/search integration
  (`QgsLayerMetadataProviderRegistry`).

(Reconcile with `03-mvp-scope.md` / `04-roadmap.md`: `assess` likely earns a place
in the v1 verb set; full metadata writing is v0.2.)

---

## 7. Open questions

1. **Lineage default** — on or off (§3)?
2. **Granularity** — one history entry per step (verbose, precise) vs one summary
   entry per flow (compact). Proposal: per step, with a flow summary line.
3. **Read-only steps in lineage** — omit, or record as "inspected"?
4. **`assess` output** — the canonical report format for the deliverable (Markdown
   for humans + JSON for machines?).
5. **How much of the 21-algorithm Check-geometry battery** belongs in `assess
   --deep` vs an explicit `checks` verb (some are expensive on large data).
6. **Where lineage lives for non-metadata formats** — Shapefile has no metadata
   store; write a `.qmd` sidecar? GeoPackage/PostGIS embed it natively.
