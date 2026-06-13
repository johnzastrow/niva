# niva

**A concise, readable text-pipeline grammar for QGIS geoprocessing — for people
who don't want to write PyQGIS.**

### Our Motto, "Easy wins every time"

<img src="logos/logo_text.png" width="320" alt="niva">

> ⚠️ **Early days — building has started.** The design is worked out in
> [`planning/`](planning/) and the **v0.1 MVP is now under construction.** What
> works today: the **grammar layer** (`niva/grammar/` — lexer + parser) with a
> parse-only CLI and a passing test suite. What's *not* built yet: the registry
> binding, the engine, and the PyQGIS backend — so niva **does not run
> geoprocessing yet**. The grammar and architecture below are largely settled;
> the rest is in progress. Expect change.

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
| `use_cases.md` | the driving example — a GIS analyst's end-to-end, multi-source workflow (Youngstown cat-canvassing) that the design is tested against |
| `00-critique-and-open-questions.md` | what's strong, what's risky, decisions pending (historical — superseded items flagged) |
| `01-prd.md` | **product requirements** — the top-level summary of everything decided: the grammar, native-first verb set, SQL & provenance value props, v1 goals/non-goals, success criteria, risks |
| `02-architecture.md` | proposed architecture — layering, lex→parse→run pipeline, backends, and the **layer handle contract** (the value threaded through `\|`, and how it bridges Processing ↔ SQL ↔ expression surfaces) |
| `03-mvp-scope.md` | what a first cut would (and wouldn't) include — the **initial ~40-verb set** (built-ins + Tier 1/2 aliases to real algorithm ids), SQL read passthrough in v1, and the definition of done |
| `04-roadmap.md` | phased direction — v0.1 MVP → v2.x across three tracks (grammar/engine, coverage/registry, provenance), reconciled with the verb set, SQL, and lineage plans |
| `05-concepts-captured.md` | every concept with its disposition — the original exploration **plus** the surface/registry/handle/provenance work — and what was deliberately rejected |
| `06-qgis-surface-reference.md` | **reference**: the full QGIS capability surface niva could reach — 769 Processing algorithms, 406 expression functions, SpatiaLite/PostGIS spatial SQL, SQL drivers, the version stack — with before/after niva examples (machine-readable inventories in `planning/reference/`) |
| `07-alias-registry-design.md` | the **alias registry** — how niva maps friendly verbs onto QGIS algorithms: entry schema, grammar→parameter binding, type coercion, enum vocab, the raw `run` escape hatch, and validation against the live registry |
| `08-data-quality-provenance.md` | **logging, lineage & data quality** — the operation log, the `assess` verb for profiling incoming data, and auto-recording processing steps as formal metadata lineage (provenance as a byproduct of the work) |
| `09-deployment-and-operation.md` | **deployment & operation** (analyst-friendly) — how niva installs into QGIS's Python, connects to QGIS/databases/files, the human-interface options (CLI, `.niva`, console, marimo, plugin GUI), and how it matures in phases |
| `10-grammar-spec.md` | the **formal grammar** — EBNF + lexical rules (tokens, quoting/escaping, comments, line-continuation, stage binding, reserved words) |
| `11-cli-and-api-reference.md` | the **CLI & Python-API reference** — commands, global flags, exit codes, the `niva.*`/`Layer`/`Result` surface, env vars |
| `12-security-model.md` | the **security & threat model** — trust boundaries, threats + controls (SQL/`run`/credentials/untrusted flows), safe defaults |
| `13-verb-reference.md` | a **worked verb reference** — the verb model fully explained, three signatures simple→complex (`reproject`/`buffer`/`join`), a composite flow, and the design issues that writing them surfaced |
| `Oscar_the_Grouch.md` | the **failure register** — a comprehensive, adversarial catalogue of every way niva could fail (premise, architecture, engineering, packaging/environment, data correctness, users, sustainability) with severities and mitigations |

Notable undecided questions: library vs CLI as the *primary* surface; whether the
text DSL earns its keep next to a Python chain + YAML; and the output/layer
lifecycle (what does a step return — a file path, a `QgsVectorLayer`, a niva
wrapper?). None of these are settled.

## What's actually here today

- **`planning/`** — the design exploration and open decisions.
- **`logos/`** — the niva brand (`logo.svg`, `logo_text.svg`; earlier concepts in
  `OLD/`).
- **`niva/`** — the **package** (v0.1, in progress). Implemented + tested: the
  **grammar** (`niva/grammar/` lexer + parser, `10-grammar-spec.md`), error types,
  and a parse-only CLI (`niva/cli/`). Next: registry binding → engine → PyQGIS
  backend. Run the tests with `python -m unittest discover -s tests`.
- **`examples/`** — an **illustrative** niva flow
  ([`youngstown_cat_canvassing.niva`](examples/youngstown_cat_canvassing.niva))
  that performs the `use_cases.md` workflow end to end in the proposed grammar.
  Not runnable yet — a design artifact to review the grammar against a real task.
- **`plugin/`** — a minimal **QGIS plugin stub** that previews the niva logo on
  the toolbar and Plugins menu. It does **no geoprocessing yet** — it's a
  skeleton + branding preview for if niva becomes a QGIS plugin. See
  [`plugin/README.md`](plugin/README.md).

There is **no installable niva package** yet.

## License

[GPLv3](LICENSE) — consistent with the QGIS ecosystem (niva builds on PyQGIS, a
GPL library).
