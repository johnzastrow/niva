# niva

**A concise, readable text-pipeline grammar for QGIS geoprocessing — for people
who don't want to write PyQGIS.**

### Our Motto, "Easy wins every time"

<img src="logos/logo_text.png" width="320" alt="niva">

> ⚠️ **Early days — largely a thought exercise right now.** niva is in the
> design/exploration stage. There is **no working package yet**: this repo holds
> planning notes, a brand, and a tiny QGIS plugin stub that only previews the
> logo. The grammar, API, and architecture described below are **goals and open
> questions**, not shipped features. Expect everything to change.

## The idea

Automating geoprocessing in QGIS today means writing PyQGIS — initialize a
`QgsApplication`, memorize algorithm IDs like `native:buffer`, build `ALL_CAPS`
parameter dicts, juggle `TEMPORARY_OUTPUT`, and thread each tool's output into
the next. That is a *programming* task, which puts everyday automation out of
reach for the GUI-first analysts who most need it — and is tedious even for
those who can.

niva's answer is a **short, readable text grammar** — a whole pipeline on one
line that a non-programmer can write *and* read:

```
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

…running on QGIS's own Processing algorithms underneath.

## Goals

- **Readable over powerful.** Favor a grammar a non-programmer can pick up — not
  a new programming language.
- **Thin over clever.** A wrapper over PyQGIS / QGIS Processing (friendly alias
  names → `native:*` algorithms), not a reimplementation of GIS.
- **Meet people where they are.** Surfaces under exploration: the text-pipeline
  grammar, a Python chain API (`niva.chain(x).buffer().clip()`), a CLI, and YAML
  flows for reproducible pipelines.
- **One backend first.** In-process PyQGIS for v1; headless `qgis_process` later
  for batch.
- **Clean-room.** The grammar is derived from QGIS Processing's own model and
  plain readability — not from any proprietary GIS scripting language.

## Status & open questions

This is a **thought exercise**; the hard parts are deliberately still unsolved.
The thinking lives in [`planning/`](planning/):

| Doc | What it covers |
|-----|----------------|
| `00-critique-and-open-questions.md` | what's strong, what's risky, decisions pending |
| `01-prd.md` | the text-pipeline grammar — product requirements |
| `02-architecture.md` | proposed architecture — layering, lex→parse→run pipeline, backends, and the **layer handle contract** (the value threaded through `\|`, and how it bridges Processing ↔ SQL ↔ expression surfaces) |
| `03-mvp-scope.md` | what a first cut would (and wouldn't) include — the **initial ~40-verb set** (built-ins + Tier 1/2 aliases to real algorithm ids), SQL read passthrough in v1, and the definition of done |
| `04-roadmap.md` | phased direction |
| `05-concepts-captured.md` | concepts gathered from the exploration |
| `06-qgis-surface-reference.md` | **reference**: the full QGIS capability surface niva could reach — 769 Processing algorithms, 406 expression functions, SpatiaLite/PostGIS spatial SQL, SQL drivers, the version stack — with before/after niva examples (machine-readable inventories in `planning/reference/`) |
| `07-alias-registry-design.md` | the **alias registry** — how niva maps friendly verbs onto QGIS algorithms: entry schema, grammar→parameter binding, type coercion, enum vocab, the raw `run` escape hatch, and validation against the live registry |
| `08-data-quality-provenance.md` | **logging, lineage & data quality** — the operation log, the `assess` verb for profiling incoming data, and auto-recording processing steps as formal metadata lineage (provenance as a byproduct of the work) |

Notable undecided questions: library vs CLI as the *primary* surface; whether the
text DSL earns its keep next to a Python chain + YAML; and the output/layer
lifecycle (what does a step return — a file path, a `QgsVectorLayer`, a niva
wrapper?). None of these are settled.

## What's actually here today

- **`planning/`** — the design exploration and open decisions.
- **`logos/`** — the niva brand (`logo.svg`, `logo_text.svg`; earlier concepts in
  `OLD/`).
- **`plugin/`** — a minimal **QGIS plugin stub** that previews the niva logo on
  the toolbar and Plugins menu. It does **no geoprocessing yet** — it's a
  skeleton + branding preview for if niva becomes a QGIS plugin. See
  [`plugin/README.md`](plugin/README.md).

There is **no installable niva package** yet.

## License

[GPLv3](LICENSE) — consistent with the QGIS ecosystem (niva builds on PyQGIS, a
GPL library).
