# Oscar the Grouch — the niva Failure Register

> *"Scram! …fine, you're here, so let me tell you EVERY way this thing falls in
> the trash. I love this part."* — Oscar

A deliberately grouchy, **comprehensive** catalogue of how niva could fail —
across the premise itself, architecture, engineering, packaging/environment, data
correctness, users, and the project's long-term survival. Each **grumble** is a
failure mode with a **severity** (likelihood × impact) and a **mitigation** (how
to make Oscar slightly less grouchy), plus a pointer to where it's addressed.

This is a *living* document: niva isn't built, so the job is to keep beating the
design against this list. A risk is "retired" only when its mitigation is **built
and tested**, not merely designed.

Severity: 🟥 High · 🟧 Medium · 🟨 Low.

---

## 0. Oscar's Top 7 (the ways niva most likely dies)

1. **The premise is wrong** — non-programmers don't actually want to write text
   pipelines; they want a button, or they never automate at all. (§1)
2. **The target user can't install it** — pip into QGIS's Python is brutal, and
   that user is exactly who can't do it. (§4)
3. **Installing niva (or notebook deps) breaks QGIS itself** — version conflicts
   in QGIS's own Python. We have the scars (`SRE module mismatch`). (§4)
4. **Silent wrong results** — an aliased default, an enum drift, a CRS slip, or
   the wrong SQL dialect produces a plausible, confidently-wrong answer. (§6)
5. **The grammar still reads like code** the moment you hit a filter expression or
   a CRS, and the escape hatch is a cliff back into the mess. (§5)
6. **Registry rot** — 769 algorithms × every QGIS release quietly breaks aliases. (§3)
7. **Scope creep + bus-factor-of-one** — five surfaces and a giant registry,
   maintained by one tired person, never ships or rots. (§7)

---

## 1. Premise / product–market risks (the whole idea could be wrong)

| # | Oscar's grumble | Sev | Mitigation / where |
|---|-----------------|:--:|--------------------|
| M1 | **Non-programmers don't want a text DSL.** GUI-first users want *the GUI*; they'll use the Modeler or click tools, not learn a grammar. The wedge may be imaginary. | 🟥 | Validate with real analysts **early** (paper prototypes of flows); the plugin GUI serves the click crowd; if text isn't wanted, pivot to "Modeler-as-text." (`01-§2`) |
| M2 | **The people who'll learn a DSL would rather learn Python.** niva's audience may be a thin slice between "GUI only" and "just write PyQGIS." | 🟧 | Keep the grammar genuinely smaller/readable than Python; the Python API is right there for graduates (`02-§3.6`). |
| M3 | **"Provenance for free" doesn't move anyone.** Users want a result, not a lineage file; the differentiator falls flat. | 🟧 | Make provenance *invisible until wanted*; lead with the one-line wedge, not the metadata (`08`, `01-§2`). |
| M4 | **The niche is too small to sustain a project.** Not enough QGIS automators who can't code to justify the maintenance. | 🟧 | Also serve power users (brevity) and headless/CI devs; keep maintenance cheap (registry-as-data) (`01-§3`). |
| M5 | **Readable ≠ teachable.** The claim that text pipelines teach geoprocessing better than the GUI may just be false. | 🟨 | Test with learners; if false, drop the teaching claim — the automation value can stand alone. |

---

## 2. Architecture risks

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| A1 | **In-process startup tax.** Each headless run boots QGIS+Processing (seconds). 500 tiny jobs = death by startup. | 🟧 | v2 **service/daemon** amortizes startup; fine interactively (`04`, `09`). |
| A2 | **Welded to a working QGIS Python.** If that interpreter is broken/missing, niva is a brick. | 🟧 | `qgis_env` detection + clear errors; the plugin guarantees the env (`09`). |
| A3 | **Cross-surface round-trips explode** on big data (temp GeoPackages, CRS/schema mangling at boundaries). | 🟥 | Materialize **only at boundaries**, expose cheaply first; benchmark it (`02-§3.3`). |
| A4 | **Registry rot across QGIS versions** — aliases map to renamed params / reordered enums and silently misbehave. | 🟥 | **Linter vs the installed QGIS** + CI matrix + introspect-never-assume (`07-§9`). |
| A5 | **Leaning on semi-public QGIS internals** (provider connections, metadata, param model). | 🟧 | Documented APIs only; pin with tests; regenerate the surface per build (`06`). |
| A6 | **The `sql` surface is three dialects in a trench coat** (PostGIS / SpatiaLite / virtual-layer); wrong engine = wrong results. | 🟧 | v1 read-only; engine explicit/by-source; writes deferred (`06-§4`, `03-§6`). |
| A7 | **The layer-handle contract is load-bearing and unproven.** Get it wrong, everything downstream is wrong. | 🟥 | Most-reviewed design; prototype it first; ratify in v0.1 (`02-§3`). |
| A8 | **Single QgsApplication per process is a straitjacket.** Long-lived hosts (console, service) accumulate state, leak memory, and can't reset cleanly. | 🟧 | Treat the process as disposable for batch; document interactive caveats; service mode manages worker lifecycles (`09`). |
| A9 | **No concurrency story.** PyQGIS/Qt isn't thread-safe; running flows in parallel (or inside a threaded notebook) corrupts state. | 🟥 | One QgsApplication per process; **flows are serial within a process**; parallelism via separate processes; document the rule loudly (it bit marimo-qgis). |

---

## 3. Engineering / computer-science risks

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| C1 | **Grammar ambiguity** — positionals vs options vs flags collide; quoting bites. | 🟧 | Few positionals, unique option/flag names, errors-with-suggestions (`07-§4`). |
| C2 | **Filter expressions are a leaky abstraction** — they *are* code (`"ZONE"='R1'`, `$geometry`). | 🟥 | Simplified translator + raw fallback (`03-§3`). Partial — GIS filtering is expression-shaped. |
| C3 | **niva inherits QGIS's performance**, warts and all (per-feature loops, GDAL quirks). | 🟧 | Prefer native algos; push to SQL; avoid temps (`05-§6`). |
| C4 | **Temp files leak** on crash; disk fills. | 🟧 | Run-owned temps, cleanup on exit; test the crash path (`02-§3.2`). |
| C5 | **`sql`/`run` are loaded guns** — arbitrary SQL, arbitrary params, arbitrary file paths; injection if niva ever string-builds SQL. | 🟧 | Never interpolate into SQL; validate identifiers; credentials stay in QGIS (`09`, §6 below). |
| C6 | **Type-system coverage gaps.** QGIS has exotic param types (matrix, point, color, layout, datetime, range, multilayer, aggregate, coordinate-operation). niva's types won't cover all → some algorithms un-aliasable. | 🟧 | `run id KEY=value` reaches them raw; alias only what the type system supports; grow types as needed (`07-§5/§8`). |
| C7 | **Multi-output algorithms lose data.** Aliases expose only the primary output; join counts, fail-outputs, secondary sinks vanish. | 🟨 | Documented; reach extras via `run`; an `outputs:` block later (`07-§7`). |
| C8 | **Save/destination semantics are underspecified.** Layer name inside a GeoPackage, overwrite vs append, output CRS, format inference from extension — all ways to surprise or clobber. | 🟧 | Define `save` semantics explicitly; default to safe (no silent overwrite); confirm in design. *(Open.)* |
| C9 | **Grammar/registry versioning.** Renaming a verb or changing a default **breaks every `.niva` file in the wild**. | 🟥 | **Grammar freeze at v1.0** + SemVer on the verb/flag/param surface; deprecation path; the registry is the contract (`04`). |
| C10 | **Machine-output / journal format drift.** Tools parsing `--json` or the run journal break when the shape changes. | 🟨 | Version the JSON/journal schema; treat as a contract (`02-§6`, `08-§2`). |
| C11 | **Errors are cryptic to the target user** (GDAL "Could not open layer", `ALL_CAPS` dicts). | 🟧 | A friendly error layer naming the failing stage + a fix — flagged, **not yet designed** (`00` open Qs). More work than it looks. |
| C12 | **Lazy planner is a complexity trap** — clever fusion/push-down breeds subtle correctness bugs. | 🟨 | Explicitly deferred; v1 is eager (`02-§3.4`). |
| C13 | **i18n/encoding.** QGIS param descriptions are translated; niva is English-only. Non-ASCII paths/fields, shapefile CP1252, locale-dependent number parsing all break things. | 🟨 | Decide English-only for verbs; normalize encodings; test non-ASCII fixtures. *(Open.)* |
| C14 | **Testing the 769-surface is hopeless.** | 🟧 | Test engine + curated verbs + linter; linter guards the tail (`02-§8`, `07-§9`). |

---

## 4. Packaging, environment & operations risks

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| E1 | **Installing niva can break QGIS itself.** pip into QGIS's Python may pull deps that conflict with QGIS's bundled libraries (numpy, GDAL bindings, PyQt) → the `SRE module mismatch` / `undefined symbol` class. niva could brick the user's QGIS. | 🟥 | **Near-zero, pure-Python, loosely-pinned dependencies**; never bundle binary libs QGIS already ships; test install against real QGIS builds; the plugin installs carefully (`09`). This is the scariest operational risk. |
| E2 | **pip-into-QGIS-Python is awful** (no pip on Linux system Python, PEP 668, OSGeo4W shell, macOS SIP/`--user`). The non-programmer can't do it. | 🟥 | The **plugin does the install** (Phase 2) — the real on-ramp; document the manual path per OS (`09-§2`). |
| E3 | **Cross-platform variance.** Windows (OSGeo4W) vs macOS bundle vs Linux system Python differ in paths, pip behavior, and interpreter location — every one a separate bug surface (we lived this with marimo-qgis). | 🟧 | Derive everything live from the running QGIS; test on all three; the plugin abstracts it (`09`, marimo-qgis prior art). |
| E4 | **QGIS upgrades move the Python.** A new QGIS = a fresh site-packages with no niva; users think it "stopped working." | 🟧 | The plugin re-offers install after upgrades (the marimo-qgis pattern); niva re-introspects the new interpreter (`09-§6`). |
| E5 | **File locking / single-writer.** GeoPackage/SQLite allow one writer; concurrent flows or an open QGIS holding a lock = "database is locked" failures. | 🟧 | Serial writes; clear lock errors; document not to write a layer that's open in QGIS. *(Operational.)* |
| E6 | **Network dependence where you don't expect it** — the Nominatim geocoder is online and rate-limited; offline/air-gapped sites can't use parts of the example workflow. | 🟨 | Flag online steps; offer offline alternatives (address-join); fail clearly (`03-§2.4`). |
| E7 | **Disk/temp pressure** on big jobs (materialized intermediates, lidar→raster). | 🟨 | Boundary-only materialization; configurable temp dir; clean up (`02-§3.3`). |

---

## 5. User / use risks

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| U1 | **Still reads like code** to a real non-programmer (pipes, quotes, `EPSG:2262`, paths, expressions). | 🟧 | Tiny prose-like surface; cookbook recipes; plugin GUI hides syntax (`01-§2a`, `09`). |
| U2 | **The escape hatch is a cliff.** `run native:slope INPUT=… RESAMPLING=1` is the exact misery niva sold you away from. | 🟥 | Grow curated coverage; `describe`/`find` ease the drop; inherent. |
| U3 | **Provider variance breaks shared flows.** A `run grass:*` or `pdal:*` flow dies on installs lacking GRASS/PDAL. | 🟧 | `niva doctor` capability report; native-first; clear "not installed" errors (`06-§8.4`). |
| U4 | **Discoverability.** Users won't know which verb/algorithm to use; if `find`/`describe` aren't excellent, they're lost. | 🟧 | Invest in `find`/`describe`, the cookbook, and good error suggestions (`03-§2`). |
| U5 | **A `.niva` file is executable** — running one you got by email runs arbitrary algorithms, SQL, and file reads/writes. Social-engineering / supply-chain risk. | 🟧 | Document that flows are code-equivalent; `--dry-run` to preview; no auto-run of untrusted files (`01-§2a`). |
| U6 | **False confidence from `assess`/lineage** — green ≠ correct; lineage records *what ran*, not *that it was right*. | 🟧 | Frame `assess` as a checklist; quality *rules* are a separate v2 thing (`08`). |
| U7 | **Partial-failure UX.** A 6-stage flow dies at stage 5 — what's saved? what's half-written? The user is confused. | 🟧 | Define failure semantics (nothing partial is `save`d; temps discarded); clear "failed at stage N" message. *(Open.)* |
| U8 | **Migration inertia.** Users with PyQGIS scripts or Modeler models won't rewrite them in niva. | 🟨 | Interop both ways; don't demand rewrites; niva for *new* work (`02-§3.6`). |
| U9 | **Support burden.** Non-programmers ask a lot of questions; thin docs or no community = abandonment. | 🟧 | Great docs + recipes + friendly errors from day one; community-friendly repo. |
| U10 | **Yet another DSL** to learn vs 10 lines of Python. | 🟨 | Small surface; Python API for the unconvinced (`01`). |

---

## 6. Data & correctness risks (the scary, silent ones)

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| D1 | **Silent wrong results from aliased defaults.** A friendly default (buffer segments, cap style, a `METHOD` enum) differs from what the user assumed; the answer is plausibly wrong. | 🟥 | `describe`/`--dry-run` show the *exact* call; document every defaulted param; lineage records them (`07`, `08`). |
| D2 | **CRS foot-guns.** A layer with a missing/wrong CRS, on-the-fly reprojection assumptions, units (feet vs metres) in `buffer 100` — all produce confidently wrong geometry. | 🟥 | `assess` flags "CRS not set"; be explicit about units; never silently assume a CRS (`08-§4`). |
| D3 | **Enum/param drift = wrong op.** A QGIS update reorders an enum; `cap=flat` now means something else. | 🟥 | Linter reconciles enum words with the algorithm's option strings (`07-§6/§9`). |
| D4 | **Geometry validity / topology** — invalid inputs make overlay ops produce garbage or crash. | 🟧 | `assess`/`fix` surface and repair; the Check-geometry battery (`08-§4`, `06-§2.5`). |
| D5 | **Encoding-mangled attributes** (CP1252 shapefiles, non-ASCII) silently corrupt joins/filters. | 🟨 | Normalize/declare encodings; test non-ASCII (`C13`). |
| D6 | **Reproducibility asterisk** — same flow, different QGIS/GDAL, different result. | 🟧 | Lineage stamps the version stack; recommend pinning (`08-§3`). |
| D7 | **Float/precision & grid-size** issues in overlay (`GRID_SIZE`, snapping) give non-deterministic edges. | 🟨 | Expose the relevant params; document; sensible defaults. |

---

## 7. Project / strategic / sustainability risks

| # | Grumble | Sev | Mitigation / where |
|---|---------|:--:|--------------------|
| P1 | **Bus factor of one + a giant surface.** One maintainer curating aliases across every QGIS release burns out. | 🟥 | Registry as **data** (contributable); linter automates drift; recruit contributors (`07`). |
| P2 | **QGIS version treadmill** — every release can move things. | 🟧 | CI matrix + introspection + version stamps (`07-§9`). |
| P3 | **Governance of the registry.** A bad community-contributed alias mapping ships silent wrong results to *everyone*. | 🟧 | Linter + review gate + tests on alias PRs; treat the registry as safety-critical (`07-§9`). |
| P4 | **QGIS builds it themselves.** A future QGIS "Processing as text" or an enhanced Modeler makes niva redundant. | 🟧 | Move fast on the niche; aim to be *upstreamable* or complementary, not a rival (clean-room helps). |
| P5 | **Scope creep eats the project.** Five surfaces, provenance, SQL, rendering, routing — polish forever, ship never. | 🟥 | Tiered MVP + hard non-goals; Tier 1 first; `run` for the rest (`03`, `04`). |
| P6 | **Clean-room slip** — inadvertent similarity to a proprietary GIS scripting language. | 🟨 | Derive only from QGIS Processing + readability; documented in every header (`01`, `05`). |
| P7 | **`niva` name taken** (PyPI, and other "niva" projects exist — a Smalltalk lang, a Tauri framework). Branding confusion / can't publish. | 🟨 | Verify PyPI early; fallbacks; clear positioning (`05-§7`). |
| P8 | **No funding / sustainability.** OSS with no resourcing stalls after the founder's enthusiasm fades. | 🟧 | Keep maintenance cheap; seek a QGIS-ecosystem home; modest scope. |
| P9 | **License constraint.** GPL (via PyQGIS) limits some integrations/commercial uses. | 🟨 | Accepted and documented; consistent with the QGIS ecosystem (`README`). |

---

## 8. Residual grumbles (no clean fix — Oscar stays mad)

- **GIS is inherently technical.** CRS, validity, topology, projections — no
  grammar makes those *not* concepts the user must grasp. niva lowers the syntax
  bar, not the domain bar.
- **The escape hatch is always a step down** in friendliness; that's the nature of
  "cover 95%, punt the rest."
- **niva is only as correct as QGIS/GDAL/GEOS underneath** — it inherits their
  bugs and can only document, not fix, them.
- **Provenance proves *what ran*, never *that it was the right analysis*.** A
  beautifully documented wrong answer is still wrong.
- **You can make a thing easy to *run* and still leave it easy to *misuse*.**
  Lowering the barrier to geoprocessing also lowers the barrier to bad
  geoprocessing.

---

## 9. Oscar reviews the planning docs — the gaps

> *"You wrote a DOZEN documents and still left holes you could drive a garbage
> truck through. Let me point at the empty spots."* — Oscar

A blocker means you can't build/ship v1 without deciding it. "Home" = where it
should be written.

### Undecided fundamentals (these block design, not just docs)

| # | The hole | Why it bites | Blocker? | Home |
|---|----------|--------------|:--:|------|
| G1 | **Distance units.** `buffer 100` — 100 *what*? Metres? Feet? Degrees? Still open (`00`, `03-§1`). | A non-programmer assumes metres; data may be feet or lat/long degrees → silently wrong buffers. Core grammar semantics, undecided. | 🟥 yes | `03` |
| G2 | **`save` semantics.** Format/extension inference, overwrite vs append, layer name inside a GeoPackage, output CRS. Open (`00`, Oscar C8). | Data loss / clobbering on a verb everyone uses. | 🟥 yes | `03` |
| G3 | **CRS handling policy.** On-the-fly reprojection? A default CRS? What if a layer has none? (tied to G1.) | Wrong-CRS geometry is the classic silent error (Oscar D2). | 🟧 | `02`/`03` |
| G4 | **Error UX.** Flagged repeatedly (`00`, Oscar C11) but never designed — and it's *central* to a non-programmer tool. | Cryptic GDAL errors = the user is stuck and gone. | 🟧 | own treatment |

### Missing specifications

| # | The hole | Why it bites | Home |
|---|----------|--------------|------|
| G5 | **Formal grammar.** Described by example, not specified — no EBNF, no precise tokenization / quoting / escaping / comment / line-continuation rules. | You can't build (or keep stable) a parser from prose; ambiguities surface as bugs. | a `grammar` spec |
| G6 | **Consolidated CLI + Python-API reference.** Commands, global flags (`--dry-run`/`--json`/`--backend`/`--log`), exit codes, and the `niva.*` surface are scattered across `02`/`03`/`09`. | No single contract for users or tooling. | a reference doc |
| G7 | **Config spec.** "minimal config" and `NIVA_*` are name-dropped, never specified — what's configurable, file location/format, precedence. | Inconsistent behavior; nothing to implement against. | `09` / config spec |
| G8 | **Logging/journal schema.** `OpRecord` is sketched (`08-§2`) but not a finalized, versioned schema others can parse. | The provenance promise needs a stable format. | `08` |
| G9 | **Security / threat model.** Exists only as Oscar risks (sql/run loaded guns; `.niva` is executable). No model of trust boundaries, what's validated, safe defaults. | Injection / arbitrary execution surprises. | own doc |

### Missing project / process docs

| # | The hole | Why it bites | Home |
|---|----------|--------------|------|
| G10 | **Governance & contribution.** No CONTRIBUTING / registry-PR review model. | A bad community alias = silent wrong results for everyone (Oscar P3). | CONTRIBUTING + governance |
| G11 | **Acceptance criteria beyond the MVP.** Only v1 has a Definition of Done (`03-§7`); v0.2 / v1.0 / v2.0 have none. | "Done" is undefined for every milestone but the first. | `04` |
| G12 | **Product success metrics.** The PRD has *technical* success criteria but no *adoption/outcome* metrics (can a non-programmer finish task X? retention? installs?). | You won't know if the premise (Oscar M1) held. | `01` |
| G13 | **Competitive / positioning analysis.** Modeler, GeoPandas, FME, ArcPy, rasterio are mentioned in passing, never analyzed. | "Why not X?" (Oscar U6/M1) is unanswered with evidence. | `01` / own doc |
| G14 | **Glossary.** flow / stage / handle / surface / provider / backend are used precisely but defined nowhere in one place. | New readers (and contributors) guess. | a glossary |

### Thin coverage

| # | The hole | Why it bites |
|---|----------|--------------|
| G15 | **One use case, one persona.** `use_cases.md` is a single analyst story; the PRD claims 4 use-case types and 3 audiences. No worked developer / teacher / quick-exploration cases. | The design is tuned to one workflow; others may not fit the grammar. |
| G16 | **Testing plan is a sketch** (`02-§8`) — no fixtures spec, coverage targets, or concrete multi-version CI plan. | The linter/parity claims are unbacked until this exists. |
| G17 | **i18n & accessibility unplanned** (Oscar C13) — English-only grammar; plugin-GUI a11y untouched. | Excludes non-English users and a11y needs. |

**Oscar's verdict on the gaps:** the *design* docs (`02`/`06`/`07`/`08`) are
solid; the **undecided fundamentals (G1–G4) and the contract specs (G5–G7) are the
real holes** — you can't build a stable parser or avoid data loss without them.
G1 (units) and G2 (`save`) **block v1 today**; the process docs (G10–G13) can wait
until there's code, but they decide whether anyone *adopts* the thing.

---

## 10. How to use this register

- Re-read Oscar **before each milestone**; demote a risk only when its mitigation
  is built *and tested*.
- The 🟥 High risks — **M1, A3, A4, A7, A9, C2, C9, E1, E2, U2, D1, D2, D3, P1,
  P5** — are the ones that decide whether niva is a real tool or a clever demo.
  Keep them visible.
- Treat **E1 (breaking QGIS), D1–D3 (silent wrong results), and M1 (premise)** as
  the existential trio: a tool that breaks your QGIS, lies about results, or
  nobody wants is dead regardless of how elegant the grammar is.

> *"…huh. That's a respectable pile of garbage. Now GET LOST — I've got a project
> to keep being suspicious of."* — Oscar
