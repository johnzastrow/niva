# Niva — Critique of Starting Materials & Open Decisions

_Critical review of `starting_materials/` (16 Perplexity exports), written to drive
proper planning. Status: awaiting decisions on the open questions at the bottom._

## 1. What the starting materials are

A design exploration (Q&A with an LLM) that converged on a consistent concept:

- **niva** = a Python wrapper over **PyQGIS / QGIS Processing** for concise,
  high-level geoprocessing.
- Package layout: `cli/`, `core/` (engine, registry, types, logging),
  `backends/` (pyqgis, qgis_process), `flows/`, `sql/`.
- An **alias registry** mapping friendly names → `native:*` algorithm IDs.
- Three usage surfaces: a **Python chain API** (`niva.chain(x).buffer().clip()`),
  a **CLI** (`niva vector buffer ...`), and a **flow DSL** (`niva flow exec "buffer | clip | save"`) plus YAML flows.
- Two execution **backends**: in-process PyQGIS and headless `qgis_process`.
- A later **SQL/PostGIS** "live layer" family.

## 2. What's genuinely strong

- **Language call is correct** (doc 10): the bottleneck is GDAL/GEOS/PROJ + QGIS
  startup, not Python glue. Rust/Go would buy packaging, not speed.
- **Core mechanism is right**: alias → `native:*`, chain by feeding `OUTPUT` into
  the next `INPUT`. That is exactly how Processing chaining actually works.
- **CLI hygiene instincts are sound** (clig.dev): shallow verb families, consistent
  flags, stdout-for-data / stderr-for-logs, defined exit codes.
- **Correctly rejects literal shell-piping of geodata** between processes.
- **Honest about its own gaps**: `save` and `sql` are flagged as placeholders.

## 3. Critical issues the exploration glossed over

### 3.1 Identity crisis: library vs CLI
The stated motivation — _PyQGIS is too verbose for everyday geoprocessing_ — is about
a **Python API you script in**, not a command line. Yet most of the design energy went
into a CLI and a bespoke flow-string language. These are two different products with
different ergonomics. **Which is primary?** This single choice reshapes everything else.

### 3.2 The flow-exec string DSL is the riskiest, least-valuable piece
`niva flow exec "buffer --input x | clip --overlay y | save --output z"`:
- **Quoting hell** is already visible in the docs: `'\"CLASS\" = ''local'''`.
- A **hand-rolled parser** to build, document, error-message, and maintain.
- **Redundant**: the Python chain is better for interactive use; YAML is better for
  reproducible pipelines. The string DSL sits awkwardly between them.
- Recommendation: **drop or defer**; keep the Python chain + YAML flows.

### 3.3 Two backends on day one doubles the surface area
In-process PyQGIS vs `qgis_process` differ in parameter serialization, output
handling, error reporting, and temp-file lifecycle. Supporting both from v1 doubles
the work and the bug surface. Pick **one** for v1 (in-process PyQGIS matches the
interactive library goal and reuses the QGIS-interpreter work already done in
marimo-qgis); add `qgis_process` later for headless batch.

### 3.4 The real hard problem — output/layer lifecycle — is unsolved
This is where niva will live or die ergonomically, and the docs barely touch it:
- `save` is a placeholder (doc 15 admits it doesn't materialize output).
- `TEMPORARY_OUTPUT` vs in-memory vs on-disk; temp cleanup; CRS propagation; layer
  naming/styling; loading results into a live QGIS project vs returning them.
- **Return-type contract is undecided**: does `niva.buffer(...)` return a file path,
  a `QgsVectorLayer`, a niva `Layer` wrapper, or a Processing result dict? Chaining
  requires one consistent answer. (Recommendation: a thin `Layer` wrapper that holds
  either a path or a live layer and knows how to be both source and sink.)
- **Eager vs lazy** chains: the docs show eager (each step runs immediately). Lazy
  would enable dry-run/preview/optimization but adds complexity. Decide explicitly.

### 3.5 Value proposition is asserted, not specified
Versus raw PyQGIS Processing, GeoPandas, and R's `qgisprocess`, what is niva's
wedge? Name the **specific** PyQGIS pains it removes, e.g.:
- QGIS app init / `QgsApplication` boilerplate,
- having to know exact algorithm IDs,
- building `ALL_CAPS` parameter dicts,
- manual `OUTPUT → INPUT` threading,
- CRS handling.
A concrete before/after (verbose PyQGIS → one niva line) belongs in the PRD.

### 3.6 Scope sprawl
`run + flow + vector + raster + select + sql + inspect + config` + chain API + YAML
+ PostGIS live layers + Processing-script integration + plugin integration is many
products at once. v1 needs a ruthless MVP boundary.

### 3.7 SQL/PostGIS "live layers" is a separate product
Valuable given your PostGIS background, but orthogonal to geoprocessing wrapping.
Strong candidate for **v2**, not v1.

### 3.8 Testing/CI in a QGIS environment is unaddressed
PyQGIS code needs a QGIS interpreter to test (the exact constraint just solved in
marimo-qgis). niva needs a test strategy from the start: headless run on QGIS's
Python, fixtures with tiny GeoPackages, and the interpreter-detection logic that
already exists in marimo-qgis (`qgis_python()`).

### 3.9 The materials are AI-validated, not pruned
Every Perplexity answer opens with "Yes — that's the right call" and then adds
features. Planning must now make the cuts the exploration avoided.

## 4. Cross-project opportunity
niva is a natural **geoprocessing layer inside the marimo-qgis notebooks** you just
built — `niva.chain(layer).buffer().clip()` in a marimo cell is exactly the
the concise ergonomics you want. Shared code is plausible: QGIS-Python detection,
headless init, the bridge. Worth deciding whether niva and marimo-qgis are siblings
that share a small core.

## 5. Decisions needed (these drive the PRD / architecture / roadmap)
1. **Primary form factor** — library-first, CLI-first, or co-equal?
2. **v1 backend** — in-process PyQGIS only, or both?
3. **Pipelines in v1** — Python chain + YAML only (drop the string DSL), include the
   string DSL, or defer all pipelines?
4. **Primary usage context(s)** — marimo/QGIS notebooks & console, standalone
   scripts, terminal CLI batch?
5. **MVP operation set** — which ~8–12 operations must v1 cover to be useful to you?
6. **SQL/PostGIS** — v1 or v2?
7. **Distribution/runtime** — pip into QGIS's Python (same model as marimo-qgis)?
   PyPI name `niva` availability?
8. **Return-type / layer model** — your preference, or should I propose one?

## 6. Decisions made (2026-06-11)

| # | Decision | Choice |
| :-- | :-- | :-- |
| 1 | Primary form factor | **Library-first** — the Python API is the product; CLI is a thin wrapper over the same functions |
| 2 | v1 backend | **Both** in-process PyQGIS *and* `qgis_process` (interactive vs headless) |
| 3 | Pipelines in v1 | **Deferred** — v1 ships direct one-shot calls only; chaining/flows are v2 |
| 4 | Usage contexts | **All four**: marimo-qgis notebooks, QGIS Python Console, standalone scripts, terminal CLI/batch |

Implications carried into the planning docs:
- Deferring pipelines removes the hardest v1 problem (temp-output chaining lifecycle);
  each op simply produces one output and returns it.
- "Both backends" means a clean `Backend` abstraction is now load-bearing from day one.
- Library-first + CLI-needed means the CLI is generated from the same per-operation
  parameter specs, so the two surfaces never drift.
- Items still proposed (not yet ratified) in the docs below: MVP operation set (03),
  return-type/`Layer` model (02), SQL/PostGIS → v2 (04), distribution model (02).

