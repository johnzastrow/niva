# Changelog

All notable changes to **niva** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **On every release** also mirror the new version's highlights into the `changelog=` field of
> [`plugin/metadata.txt`](plugin/metadata.txt) (concise — latest one or two versions only); that
> field is what the QGIS Plugin Manager shows. This file stays the full history.

## [Unreleased]

## [0.31.1] - 2026-06-20

### Fixed
- **A `@conn` Source whose connection name contains a dot now round-trips into `load`.** A
  GeoPackage/SpatiaLite connection registered in QGIS is named after its file (e.g.
  `CNYTriData.gpkg`), so `show @CNYTriData.gpkg` printed a Source like
  `@CNYTriData.gpkg.course_points` — but `load`/`sql`/`save` split it on the first dot and looked
  for a non-existent connection `CNYTriData` ("no saved QGIS connection named `CNYTriData`"). The
  connection-name resolution is now shared: a new `resolve_connection_name(token, known_names)` in
  `engine/connections.py` matches the **longest dotted prefix that is an actually-registered
  connection**, and `load`/`sql`/`save` (and the `project` repoint path) all use it — so every
  Source `show` advertises loads back. `show`'s own resolver now shares the same code. Backward
  compatible: with no registered names the body still splits naively.
- **`show`'s example for an aspatial table is now runnable.** The footer example for a `table`
  (NoGeometry) source was `load <src> | assess`, but `assess` has no stdout form and always needs
  `assess … to <report.md>` — so copying it produced a flow that errored. It now reads
  `load <src> | assess to assessment.md`.

### Tests
- New `tests/test_cascade.py` (live-QGIS): dogfoods the discovery chain `info → show → run every
  Source and example → re-`show`/re-`load` each example's output → a multi-hop
  load→save→show→load chain`, across vector, raster, aspatial-table, and dotted-connection
  sources. Mock-backed regression tests for both fixes added to `test_sql.py` / `test_utilities.py`.

## [0.31.0] - 2026-06-20

### Added
- **`show` reaches ArcGIS REST and XYZ.** Beyond WFS/WMS (0.30), `show <url>` now also lists an
  **ArcGIS REST** service's layers and tables (`…/FeatureServer`, `…/MapServer`, `…/ImageServer`
  — read via `?f=json`, with ESRI geometry types mapped to familiar names and a per-layer
  `…/Server/<id>` source), and treats an **XYZ** `{z}/{x}/{y}` tile template as a single layer
  (no network — the URL is the layer). Service kind is auto-detected from the URL shape; ArcGIS
  JSON is parsed with `json` (no entity risk) under the same timeout/size-cap guards.
- **`show` footer now shows two runnable examples** built from the listing's first row — copy a
  real Source and pipe it onward, e.g. `load "data.gpkg|layername=roads" | buffer 100m | save
  buffered.gpkg` (geometry verbs for vectors, `hillshade`/`warp` for rasters, `assess` for
  tables). Plus a shell-safety tip: the Source cells are Markdown `backticks` — copy the value
  inside, and quote the whole flow (`niva 'load "…"'`) so the shell doesn't run the backticks or
  split on the `|`.
- **`info` gained a “Listing data (`show`)” section** — concrete `show` examples for files,
  directories, a real database connection from the active profile, and remote services.

### Fixed
- **`show` now labels attribute-only layers as `table`, not `vector`.** A `NoGeometry` layer
  (e.g. the tables in a style/SQLite database, or a CSV) was being shown with `kind=vector`;
  it's now `kind=table` / `type=(aspatial)`, matching how database tables are already classified.
- **`show <dir> deep` no longer spams GDAL `ERROR 4: … not recognized` lines.** The
  format-agnostic scan probes every file; GDAL's chatter on the ones it can't read (`.json`,
  config files, …) is now silenced — a failed probe simply contributes no layers.

## [0.30.0] - 2026-06-20

### Added
- **`show` reaches remote OWS services** — `show <url>` lists a **WFS** endpoint's feature
  types or a **WMS** endpoint's layers, alongside the existing files / directories / `@conn`
  sources. The service is detected from a `service=WFS`/`service=WMS` query parameter, the URL
  path, or a `WFS:`/`WMS:` prefix (if undeterminable, `show` asks you to specify). Each row
  carries the name, kind (vector for WFS / raster for WMS), type (default CRS or layer title),
  format (`WFS`/`WMS`), and a GDAL-style `WFS:`/`WMS:` source for `ogrinfo`.

  Implemented as pure standard-library HTTP + XML in a new `niva/remote.py` (no QGIS, no
  third-party deps) — fully unit-testable offline by injecting the fetcher; `PyqgisBackend`
  delegates to it. **Security:** only `http`/`https` URLs are fetched (no `WFS:file://…` local
  reads), responses are timed and size-capped, and the parser **refuses any `<!DOCTYPE>`** so no
  entities are ever expanded (XXE / billion-laughs blocked without `defusedxml`); no credentials
  are sent. See [`docs/planning/17-show-verb-design.md`](docs/planning/17-show-verb-design.md).
  XYZ / vector-tile / ArcGIS REST, `/vsicurl` cloud rasters, and authenticated services remain a
  follow-up.

## [0.29.1] - 2026-06-19

### Fixed
- **Inline commands with unquoted arguments now work.** `niva show /path/to/dir` (and any
  inline verb with arguments) previously read only the first shell token (`show`) and silently
  discarded the rest, producing a confusing error like *"show needs one location"*. The CLI now
  re-joins the remaining `argv` tokens into the inline source, so both unquoted
  (`niva show /path`) and quoted (`niva "show /path"`) forms behave identically.

## [0.29.0] - 2026-06-19

### Added
- **`show` verb** — lists the loadable layers/tables at a location, the lightweight cousin of
  `catalog`: a quick *"what can I load here, and what's its name?"* glance rather than a deep
  recursive inventory. Per entry: name, kind (vector/raster/table), type (geometry like
  `MultiPolygon`, or a raster's `N band · Float32`), format (file driver `GPKG`/`GTiff`/… or DB
  provider), and a copy-pasteable source for `load` (or `ogrinfo`). No feature counts, so it
  stays instant even on large databases. Locations:
  - **files / containers** — GeoPackage, SpatiaLite, shapefile, GeoTIFF, … (a multi-layer
    container expands to one row per layer), via `QgsProviderRegistry.querySublayers`;
  - **directories** — shallow listing of immediate children by default, or the whole tree with
    the **`deep`** flag (`show data/ deep`). Discovery is **format-agnostic** — every file is
    probed, so any QGIS-readable dataset is listed (SpatiaLite `.sqlite`/`.db`, FileGDB `.gdb`,
    MBTiles, … — no fixed extension allowlist); dataset sidecars and non-geospatial files are
    skipped, and directory-based datasets (`.gdb`) are listed as a container, not descended into;
  - **database connections** — `show @conn` (all tables), `show @conn.schema`,
    `show @conn.schema.table`, via the QGIS connection API. Connection names containing dots
    (e.g. `@actual_spatialite.sqlite`) resolve by longest-matching-prefix. Only the connection
    name is ever in scope — credentials stay in QGIS.

  Terminal verb (`to=<out.md>` writes a file, else prints to stdout). New backend methods
  `list_layers`, `list_tables`, `connection_names`; two-tier tests; design doc
  [`docs/planning/17-show-verb-design.md`](docs/planning/17-show-verb-design.md); documented in
  the Reference and FAQ. Remote services (WFS/WMS, ArcGIS REST, `/vsicurl`) are a deliberate
  follow-up.

## [0.28.0] - 2026-06-19

### Added
- **`info` verb** — inspects the local QGIS environment and reports the details a command-line
  user needs before writing a flow (when working outside QGIS, where the Browser and connection
  dialogs aren't in front of you). Most useful: the **registered database connection names** —
  the valid `@conn` references for PostGIS and SpatiaLite. Also surfaces the Processing
  providers + reachable algorithm count (so `run grass:…`/`run pdal:…` are known to work),
  versions (QGIS, GDAL, PROJ, GEOS, Python), niva's own build + import path, the verb list, and
  the environment variables niva honours — with **secrets masked** (`NIVA_NTFY_TOKEN`,
  `NIVA_SMTP_PASSWORD` shown only as *set* / *unset*). `info` prints to stdout; `info
  to=<report.md>` writes a file. Terminal verb; distinct from `project info <src.qgs>` (which
  inventories a project *file*). Documented in the [Reference](docs/guide/reference.md) and
  [FAQ](docs/guide/faq.md).

### Changed
- **One source for the environment report.** The report logic now lives in the niva package
  (`niva/environment.py`), shared by the `info` verb and the plugin's Setup-tab **Environment
  report** button; `plugin/environment.py` is now a thin re-export. The packaged report adds the
  environment-variables section (with secret masking).

### Fixed
- **Standalone niva now reads the QGIS desktop user profile** — so the database connections it
  reports and resolves (`@conn`) match what you see in QGIS. A standalone `QgsApplication`
  previously fell back to a generic Qt settings store (`…/Unknown Organization.ini`) that held
  **none** of the user's connections, so `info` showed the wrong set and `load @conn.table`
  could fail to find a connection that plainly exists in QGIS. `ensure_qgis()` now adopts QGIS's
  own Qt org/app identity and boots into the active profile
  (`~/.local/share/QGIS/QGIS<major>/profiles/<profile>`).

### Added (`info`, continued)
- **Per-profile connection inventory.** `info` lists **every** QGIS profile and the database
  connections in each (parsed read-only from each profile's settings ini), marking the active
  one — since connections are per-profile and niva uses one at a time. New `NIVA_QGIS_PROFILE`
  selects which profile a standalone run reads.
- **More environment detail** in the report: Qt **and** PyQt versions, **SpatiaLite + SQLite**
  versions, and `sys.base_prefix` alongside `sys.prefix`.

## [0.27.6] - 2026-06-19

### Changed
- **Refreshed the pitch deck** (`docs/presentation/`) — the "What's working today" and roadmap
  slides now reflect v0.27: ~45 verbs + raster, `run` → 769 algorithms, PostGIS/SpatiaLite
  read·write·analyse, the `project`/`style` verbs, the QGIS plugin, and the full docs. Both the
  Marp deck and the PowerPoint (and their rendered HTML/PDF/PPTX) regenerated.

### Notes
- TODO: a planned **`info` verb** that inspects the local QGIS environment (registered `@conn`
  database connection names, providers/algorithm count, versions, the env vars niva honours) —
  the CLI counterpart of the plugin's environment report.

## [0.27.5] - 2026-06-19

### Added
- **FAQ** ([`docs/guide/faq.md`](docs/guide/faq.md)) — quick answers including *what software
  libraries niva needs* (essentially just QGIS; niva is pure Python with zero runtime deps),
  how to run it, scratch space, databases, and reaching un-aliased algorithms. Linked from the
  README and included in the guide PDF.
- **README badges** — release, license (GPLv3), QGIS 3.22+/4.x, Python 3.9+, and "no runtime
  deps".
- **Every algorithm in the appendix (`docs/algorithms/`) now has a worked "Example usage"** —
  a complex `run <id> KEY=value …` command (built from the algorithm's required + notable
  optional parameters, with real enum indices and named outputs) followed by a narrative
  explaining each parameter passed. Auto-generated by `scripts/gen_algorithms.py`.
- **`scripts/build_guide_pdf.py`** — builds one coherent PDF of the user guide
  (`docs/guide/`) with pandoc + xelatex: title page, TOC, a chapter per document, and the
  per-provider algorithm reference (`docs/algorithms/`) as lettered **appendices**. Tables are
  rewritten with wrapping `p{}` columns and a horizontal rule on every row so nothing is cut
  off, genuinely-wide guide tables are rotated onto **landscape** pages, long inline-code
  tokens break in prose, and the **PDF bookmark outline goes down to H3** (every algorithm /
  verb is navigable) while the printed TOC stays compact. Regenerable.

### Changed
- **Merged `tools/` into `scripts/`** — `gen_algorithms.py` now lives in `scripts/` alongside
  the other maintenance scripts; references updated.

## [0.27.4] - 2026-06-19

### Fixed
- **`save` now creates its target's parent directory** if it doesn't exist (previously only
  `catalog`/`project`/`assess` did, so `save out/new/x.gpkg` into a fresh tree failed with an
  OGR "unable to open database file" error) — including the first item of an `each` batch that
  saves into one container.
- **`style apply`/`save` now chains after `save`** (the documented `… | save out.gpkg |
  style apply x.qml` pattern). `save` returns a path-backed handle; `style` now loads it
  instead of crashing with `'str' object has no attribute 'loadNamedStyle'`.
- **Saving to `.sqlite` now produces a real SpatiaLite database** (`SPATIALITE=YES`), so QGIS
  SpatiaLite connections and `sql @conn` ST_* functions work against it — previously it was a
  bare OGR SQLite the SpatiaLite provider couldn't read.
- **The `polygonize` alias works again** — a raster-in / vector-out algorithm's output was
  wrongly forced to a `.tif` (the scratch path was keyed on the input facet); it now keys on
  the output facet, so `load r.tif | polygonize | save out.gpkg` produces a vector.

  (All four fixes were surfaced by building and verifying the demo dataset.)

### Added
- **Demonstration dataset + build flows** under `examples/` — a recursive example (niva
  building niva's own demo data): `demo_data_usecase.md` (the analyst plan), `build_demo_data.niva`
  (themed vectors with synthetic columns, per-layer files, a 10 m DEM + derivatives, categorical/
  NoData/target rasters, join CSVs, a SpatiaLite DB, a project + style), and the deferred
  `build_demo_lidar.niva` / `build_demo_postgis.niva`. The generated dataset (`examples/demo/`) is
  **not committed** — it ships as the **`demo.zip`** asset on this release, and is regenerated by
  the build flow.
- **`examples/verify_cookbook.py`** — a harness that runs a representative recipe from every
  cookbook section against `examples/demo/` (registering the SpatiaLite DB, using any reachable
  PostGIS connection) and reports pass/fail. Current result: 39/40 pass (PostGIS skipped without
  a connection).

### Changed
- **The demo vectors are consolidated into one GeoPackage** (`examples/demo/demo.gpkg`, 31
  named layers) instead of ~30 separate `.gpkg` files under `vectors/`/`layers/` — fewer files,
  same coverage. The build/verify/PostGIS flows address layers as `demo.gpkg|layername=<name>`.

## [0.27.3] - 2026-06-19

### Added
- **Cookbook §K — "Reaching every provider with `run`"**: 21 new recipes (4 each from GDAL,
  GRASS, QGIS, PDAL, and native, plus the single 3D algorithm) showing how to use any QGIS
  provider's algorithms through the `run` escape hatch — with the two gotchas it surfaces
  (enum options take integer indices; GRASS/PDAL write named outputs). All ids/parameters are
  from the live QGIS 4.0.3 registry.

## [0.27.2] - 2026-06-19

### Added
- **Full QGIS algorithm appendix** ([`docs/algorithms/`](docs/algorithms/README.md)) —
  every one of the **769** Processing algorithms reachable via `run <id>` (QGIS 4.0.3),
  one Markdown file per provider, each algorithm documented with its parameters (type,
  required, default, enum options), description, outputs, and the niva alias verb that wraps
  it (⭐). Auto-generated by `scripts/gen_algorithms.py`. The Reference now opens with an
  algorithm-coverage summary table and links into the appendix.

## [0.27.1] - 2026-06-19

### Added
- **Comprehensive end-user documentation** — three new guides linked from the README:
  [`docs/guide/reference.md`](docs/guide/reference.md) (every built-in verb, all 45 alias verbs with their
  QGIS algorithm + args/options/flags, value types & units, `@conn` connections, environment
  variables, the CLI, and the Python API), [`docs/guide/cookbook.md`](docs/guide/cookbook.md) (50 worked
  recipes of increasing complexity, including a large block of spatial SQL for both SpatiaLite
  and PostGIS), and [`docs/guide/user-guide.md`](docs/guide/user-guide.md) (running niva inside QGIS and
  standalone, configuration, scratch space, the journal, export-to-PyQGIS, and troubleshooting).

## [0.27.0] - 2026-06-18

### Added
- **Any existing QGIS project is a template.** `project from-template="my_project.qgz"` reuses
  **any** existing `.qgs`/`.qgz` — its print layouts and styled layers — copying it and
  repointing each layer slot to your same-named data under `data=`. You author templates the
  normal way in QGIS, then reuse them against fresh data (layouts verified to survive
  instantiation).
- **`project to-template=<name|path> from=<src.qgs|qgz> [paths=relative|absolute]` — register
  an existing project as a reusable template.** A bare **name** copies the project into the
  template library (`$NIVA_TEMPLATES` or `~/.niva/templates`, so `from-template=<name>` finds
  it); a **path** writes anywhere; `paths=relative` makes the template portable. The slots keep
  their current data as *example* data, repointed on instantiation. Terminal.
- **Bundled `example` template.** niva now ships a fully-populated example template (resolved
  by `from-template=example`, no setup) under `niva/templates/` — three distinctly-styled slots
  (`boundary`/`roads`/`places`), a print layout (title/map/legend/scale bar), a spatial
  bookmark, and a title + CRS — so the feature works out of the box and gives users a project to
  clone. Named templates now resolve across `$NIVA_TEMPLATES` → `~/.niva/templates` → bundled.
- **Template authoring guide** — [`docs/guide/templates.md`](docs/guide/templates.md): a full reference of
  what a template carries (layouts, bookmarks, themes, per-layer symbology/filters/metadata),
  the display-name slot-matching rule, caveats (schema-dependent styling, layout extent), and an
  end-to-end authoring walkthrough.

### Changed
- **`from-template` slots now match by the layer's *display name*** (what it's labelled in the
  layer panel), falling back to the datasource name — so a slot shown as `parcels` is filled by
  `parcels.gpkg` in `data=` regardless of the placeholder it points at. Plain `project repoint`
  is unchanged (still matches by datasource name).

## [0.26.0] - 2026-06-18

### Added
- **`project from-template=<name|path>` — instantiate a stock template against your data.**
  `project from-template=atlas to=region.qgz data="data/clips/"` copies a curated `.qgz`/`.qgs`
  template (carrying **print layouts** and **styled layer slots**) and repoints each slot —
  **vector *or* raster** — to the **same-named dataset** found under `data=` (resolved like
  `each`/`project new`, matched by the slot's layer name), so the **symbology and layouts ride
  along** (a repoint preserves a layer's style). Templates resolve by **name** from
  `$NIVA_TEMPLATES` (or `~/.niva/templates`), or by **path**. Unmatched slots follow `missing=`
  (default **`keep`**, to preserve layout structure; `drop`/`fail` available). Terminal. This
  **supersedes the separate print-layout roadmap items** — a template *is* the layout + styles,
  applied in one pass.

### Changed
- **Option keys may now contain internal hyphens** (e.g. `from-template=`). Only tokens
  containing `=` are tested as option candidates, so flags like `-deep` are unaffected.

## [0.25.0] - 2026-06-18

### Added
- **`project … bookmark=<name>` — add a spatial bookmark.** `project src.qgs to=out.qgs
  bookmark="Study Area"` adds a bookmark covering the **union** of the project's layers (a
  jump-to for compiled outputs). For a centred bookmark, add `at="x,y"` with `width=<w>`
  (exact, in map units) or `scale=<N>` (converted to a width via a ~0.5 m reference map
  view — approximate; prefer `width=` for an exact extent). Composes with `repoint=`/`paths=`.

## [0.24.0] - 2026-06-18

### Added
- **`project` can copy / convert / rewrite paths** — `repoint=` is now optional.
  `project <src> to=<out>` copies a project, converting `.qgs`↔`.qgz` by the `to=`
  extension; `paths=relative` (or `absolute`) rewrites datasource path storage to make a
  project portable. Combine with `repoint=`/`rasters=` to repoint *and* rewrite in one pass.

## [0.23.0] - 2026-06-18

### Added
- **`project info <src.qgs|qgz> [to=<out.md>]` — inventory a project.** Reads a QGIS
  project and writes a Markdown report of its layers (name, type, provider, CRS,
  datasource, validity) plus the project title/CRS — a `catalog` for project files, handy
  for auditing what a `.qgs` points at.

## [0.22.0] - 2026-06-18

### Added
- **`style save` exports `.sld` and `.qlr`.** Beyond `.qml`/`.qmd`, `style save <file>` now
  writes **SLD** (`.sld` — OGC Styled Layer Descriptor, for GeoServer and other tools) and
  **QGIS Layer Definition** (`.qlr` — a portable file bundling the layer's *datasource* and
  style, drag-droppable into any project). Both are export-only; `style apply` stays
  `.qml`/`.qmd`.

## [0.21.0] - 2026-06-18

### Added
- **`project new from=<dir|glob> to=<out.qgs>` — create a project from outputs.** The
  complement to repointing: instead of editing an existing project, `project new` writes a
  fresh QGIS project (`.qgs`/`.qgz`) that loads every layer found under `from=` — a
  directory, glob, or multi-layer container, resolved like `each` (GeoPackages expanded per
  layer) — with optional `crs=` and `title=`. Closes the compile loop (clip → save →
  *generate* a ready-to-open project).

## [0.20.0] - 2026-06-18

### Added
- **`style` verb — apply or save a layer's `.qml` style / `.qmd` metadata.**
  `style apply <file>` loads a `.qml` (symbology) or `.qmd` (metadata) sidecar, applies it
  to the current layer, and **persists** it so QGIS shows it: a GeoPackage layer's style
  goes into the container's `layer_styles` table (a re-loaded layer adopts it as the
  default); a single-file layer (`.shp`/`.tif`) gets a same-basename sidecar QGIS
  auto-loads. `style save <file>` exports the current layer's style/metadata to a sidecar
  instead. Both are **pass-through**, so `style` chains after `save`:
  `… | save roads_clip.gpkg | style apply house.qml`. `apply` needs a file-backed layer
  (save first); applying to a database-backed layer is not supported yet.

## [0.19.0] - 2026-06-18

### Added
- **`project … rasters=<dir>` — repoint raster layers too.** The `project` verb repointed
  vector layers and left rasters alone; it can now repoint **raster** layers (DEM,
  orthophoto, …) as well. Since rasters live in separate files (not the vector
  container/DB), each raster layer is repointed to a **same-basename file in `<dir>`**
  (e.g. a project's `dem.tif` → `<dir>/dem.tif`) via the `gdal` provider. Without
  `rasters=`, raster layers are left unchanged (as before); with it, an unmatched raster
  follows the same `missing=fail|keep|drop` policy as vectors.

## [0.18.3] - 2026-06-18

### Fixed
- **`save @conn … mode=append` to PostGIS no longer collides on the primary key.** A
  GeoPackage source carries an `fid` column; exporting it to a PostGIS table made `fid`
  the table's primary key (with no auto-default), so appending more rows duplicated the
  key and failed (`duplicate key value violates unique constraint`). Append now mints
  fresh values for a single integer primary key instead of copying the source's. (Found
  by the new real-PostGIS test tier — SpatiaLite couldn't surface it because its export
  uses a separate auto-increment key.)

### Added
- **Real-PostGIS test tier + CI.** `tests/test_pyqgis.py` gains a `TestPyqgisPostgres`
  tier (gated on `NIVA_TEST_PG`; skips otherwise) covering create/replace/append,
  schema-qualified writes, `sql` execute, and the **PostgreSQL-only `COMMENT ON TABLE`
  lineage** — paths SpatiaLite can't exercise. CI now runs the **live-QGIS tier on the
  `qgis/qgis` image with a PostGIS service**, so the real backend (the layer that catches
  these bugs) is gated, not just run by hand.

## [0.18.2] - 2026-06-18

### Changed
- **Built-in verb dispatch is now a registry** (`Engine._BUILTIN_VERBS`) instead of a
  hand-maintained `if verb == …` chain. Behaviour is identical; adding a built-in verb is
  now one line plus its method. Paves the road for the verbs still on the roadmap.

### Docs
- **New: [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md)**
  — the paved road for adding verbs: alias vs built-in, the built-in checklist and
  conventions (errors, paths, credentials, journal, off-main-thread), and the **two-tier
  test mandate** (a MockBackend test for logic + a live-QGIS test for behaviour — the
  latter is what catches real backend bugs), with lifecycle diagrams.

## [0.18.1] - 2026-06-18

### Fixed
- **`sql @conn` routing now sees past a leading comment or parenthesis.** A query that
  began with `-- …`, `/* … */`, or `(` (e.g. `/* note */ SELECT …`, `(SELECT …)`) was
  misread as a write and run as a terminal statement; the read/write router now skips
  leading comments and parens before checking the keyword.
- **DB lineage comment hardened.** The `COMMENT ON TABLE` niva writes after a PostgreSQL
  `save @conn` now quotes the `schema.table` identifier (the comment value was already
  escaped), so an unusual table name can't break or inject into the statement.

### Changed
- Internal cleanup (no behaviour change): the provider default-schema rule is now one
  shared `default_schema()` helper instead of being duplicated in `save_table` and the
  `project` repoint target.

## [0.18.0] - 2026-06-18

### Added
- **`project` verb — copy a QGIS project and repoint its layers.**
  `project <src.qgs|qgz> to=<out.qgs|qgz> repoint=<target>` copies a QGIS project file and
  repoints each **vector** layer's datasource to one `<target>` — a GeoPackage path **or**
  an `@conn[.schema]` database connection (the v0.17.0 DB write) — matched by the layer's
  name (its old `|layername=`, else the file stem), with **subset filters preserved**. A
  layer whose name isn't found in the target is handled by `missing=`: **`fail`** (default
  — never silently break a project), **`keep`** (leave it pointing at its old source), or
  **`drop`** (remove it from the project). Uses a standalone `QgsProject()` (off the main
  thread, never the GUI singleton); `.qgs` and `.qgz` are read/written by extension. This
  is the last piece of "compile a region" — it completes analyst-plan Task 5, which the
  bundled `examples/analyst_plan.niva` now performs instead of flagging as unavailable.
  Raster-layer repointing and `.qml`/`.qmd` sidecars remain on the roadmap.

## [0.17.0] - 2026-06-18

### Added
- **Write to a database with `save @conn[.schema].table`.** A flow can now persist its
  result into a PostGIS/SpatiaLite table on a named QGIS connection, not just a file —
  `load roads.gpkg | clip aoi.gpkg | save @pg.public.roads_clip`. Writing is
  **fail-closed**: `save` creates a new table and errors if it already exists, unless you
  ask for `mode=replace` (drop + recreate) or `mode=append` (INSERT into the existing
  table). In an `each` batch, `save @conn` writes one table per item, named after the
  item; a trailing qualifier names the **schema** to write them into
  (`each "NiagaraBasemap/" | … | save @pg.niagara`).
  As with reads, **credentials never leave QGIS** — the destination URI (host, database,
  login) is built from the live connection, and the connection name is all niva ever sees;
  errors never echo the URI or query text.
- **Run non-SELECT SQL with `sql @conn "…"`.** `sql` now executes server-side
  analysis/DDL/DML — `CREATE TABLE … AS SELECT …`, `UPDATE`, `INSERT`, `DROP`, spatial
  `ST_*` writes — as a terminal step. SELECT-style queries (`SELECT`/`WITH`/`VALUES`/
  `TABLE`/`EXPLAIN`/`SHOW`) keep returning a layer to pipe, exactly as before; the leading
  keyword decides the route, so `CREATE TABLE … AS SELECT …` correctly runs as a write
  while `WITH … SELECT …` is read as a query.

## [0.16.3] - 2026-06-17

### Fixed
- **`~` now expands in layer/raster path arguments**, not just `load`/`save`. A path
  passed to a verb that takes a layer — e.g. `clip "~/aoi.gpkg"`,
  `clipraster "~/mask.gpkg"`, `spatialjoin with="~/pts.gpkg"` — was forwarded to QGIS
  verbatim, and QGIS/GDAL do not expand `~`, so it failed to find the file. The binder
  now expands a leading `~` for layer/raster args (an absolute path or a
  `@connection.table` reference is unchanged), matching how `load`/`save` already
  behave. This makes home-relative flows fully portable.

### Changed
- **Bundled example flows use portable `~/…` paths** instead of hardcoded absolute
  paths, so `examples/analyst_plan.niva` and `examples/youngstown_cat_canvassing.niva`
  run on any machine (and no longer embed a specific username/home layout).

## [0.16.2] - 2026-06-17

### Fixed
- **Lossless-retry GeoPackages no longer leak into the scratch dir.** When a layer
  mixes geometry types (e.g. an Overture theme with a stray GeometryCollection), niva
  reprojects it losslessly via a temporary GeoPackage. Those temp files (and the
  raster intermediates) are allocated by `_temp_path`, which wasn't tracked for
  cleanup — so a batch over mixed-geometry data left several `niva_*.gpkg` behind each
  run (previously in the system temp dir; since 0.16.0, in `NIVA_TMPDIR`). `_temp_path`
  now records every allocation so `purge_scratch` removes it when the run ends (the
  run's final layer is still spared). Surfaced by running the full analyst plan.
- **The scratch directory itself is removed after a clean run.** Previously only the
  scratch *files* were deleted, leaving an empty `NIVA_TMPDIR` behind. On a successful
  run niva now also removes the scratch directory — but only when `NIVA_TMPDIR` was set
  (never the shared system temp), and only if it is empty, so a directory holding other
  files is never touched. It is recreated on the next run. On a *failed* run the files
  are still freed but the directory is left in place.

## [0.16.1] - 2026-06-17

### Fixed
- **A failed GDAL/OGR step no longer reports success.** The GDAL algorithms (`warp`,
  `clipraster`, raster `save`, …) run an external command that can exit nonzero — e.g.
  on a truncated/corrupt raster, gdalwarp prints `Process returned error code 1` and
  writes an empty output — yet `processing.run` still returns a result dict without
  raising. niva was forwarding those errors to the log but marking the step ✓ and
  handing on the blank result. It now inspects the algorithm's feedback and raises a
  clear error (`… the underlying command did not complete … the input may be corrupt
  or truncated`) instead of a false success. Surfaced while verifying 0.16.0 against an
  orthophoto that the earlier disk-quota crash had left truncated.

## [0.16.0] - 2026-06-17

### Fixed
- **Big raster pipelines no longer exhaust a small `/tmp` and crash mid-run.** Raster
  steps (`warp`, `clipraster`, `hillshade`, …) write a full intermediate raster —
  often gigabytes — before `save` re-encodes it. These used QGIS's `TEMPORARY_OUTPUT`
  sentinel, which lands in the system temp dir; on many setups that is a small,
  RAM-backed **tmpfs** (e.g. a 16 GB `/tmp`), so a long imagery pipeline could fill it
  and abort with "disk quota exceeded" even when the real disk had hundreds of GB free.
  Niva now writes raster intermediates to a relocatable scratch dir and **deletes them
  when the run ends** — including after a failed run, so a crash no longer strands
  gigabytes of scratch behind it. The run's final layer is spared, so a terminal
  `warp`/`clipraster` with no `save` still resolves on the map.

### Added
- **`NIVA_TMPDIR` — choose where big raster scratch goes.** Set it to a roomy,
  disk-backed folder to keep intermediate rasters (and GDAL's own `CPL_TMPDIR` scratch)
  off a small tmpfs. Unset, behaviour is unchanged (the system temp dir is used). The
  plugin's **Setup tab** gains a *"Raster scratch"* folder field that defaults to a
  disk-backed dir under the QGIS profile (never the tmpfs) and sets `NIVA_TMPDIR` live.

## [0.15.1] - 2026-06-16

### Changed
- **Friendlier timestamps in notifications and run output.** The `{now}` / `{started}`
  notify variables and the "run started/finished" output lines now read
  `YYYY-MM-DD HH:MM:SS` in local time (e.g. `2026-06-16 18:48:51`) instead of ISO
  `2026-06-16T22:45:04+00:00`. The machine journal (`.jsonl`/`.log`) keeps ISO 8601 UTC.

## [0.15.0] - 2026-06-16

### Added
- **`notify` message variables.** A notify message can interpolate job values:
  `{elapsed}` (total job time so far), `{last}` (the previous stage's time), `{now}`,
  `{started}`, `{ops}` (operations so far), `{errors}` (failures so far). E.g.
  `notify "done in {elapsed}"`.
- **Auto-alerts on errors and warnings.** Tick **Notify on errors** / **Notify on
  warnings** in the Setup tab (env `NIVA_NTFY_ON_ERROR` / `NIVA_NTFY_ON_WARNING`) and
  niva pushes an ntfy message automatically: a high-priority alert when a run fails
  (with the error and elapsed time), and a message on warnings (mixed-geometry and
  datum-transform notices, skipped batch items) — **de-duplicated per run** so a batch
  can't spam. Best-effort: an alert can never break or abort the run.

### Changed
- **Detailed UI tooltips** across every control on all three tabs — each now explains
  what it does, how/when to use it, and any caveat (not just a label restatement).

### Fixed
- **A flow's `notify` could go to the wrong topic / not arrive.** In
  `examples/analyst_plan.niva` the Task-4 and completion `notify` statements had become
  joined on one line with a stale `to=niva-analyst`, so the Task-4 message was sent to
  that topic (which you weren't subscribed to) instead of your `NIVA_NTFY_TOPIC` — the
  cause of "Task 3 notified but Task 4 didn't". Split into separate lines using the
  configured topic, and added `{elapsed}` to each.

## [0.14.0] - 2026-06-16

### Added
- **Each run stamps the niva version and wall-clock start/end** — shown at the top of
  the run output (`niva X.Y.Z — run started <time>` … `run finished <time>`) and in the
  journal `.log` header (`# run: … (niva X.Y.Z, started <time>)`) and footer.
- **GeometryCollection / mixed-geometry handling is logged.** When `reproject` keeps a
  mixed layer losslessly (generic-geometry fallback), it emits a clear notice to the run
  output *and* the journal — what happened and the limitations (Shapefile can't store it;
  `clip`/`dissolve` would drop the odd parts; use `split`). The journal gains a per-op
  `note` field (one line in the `.log`, a field in the `.jsonl`).
- **Datum-transform quality notice.** Before/after a `reproject`, niva checks
  `QgsDatumTransform.operations`: if the *preferred* (most accurate) transform needs a
  grid that isn't installed — so a less accurate one is used — it logs which grid is
  missing and the download URL (the same info QGIS's GUI shows as "Cannot use preferred
  transform …"), into the output and journal. Works headless, not just in the GUI. niva
  also forwards QGIS message-log warnings emitted during a run.

### Fixed
- **ntfy notifications in a flow now use the configured topic.** `examples/analyst_plan.niva`
  no longer hard-codes `to=niva-analyst` (a topic you weren't subscribed to); `notify`
  steps use `NIVA_NTFY_TOPIC`/`NIVA_NTFY_SERVER`/`NIVA_NTFY_TOKEN` — the same config as
  the Setup tab's "Send test notification". The plugin now **applies the Setup email/
  notify config to the environment before a run**, so a flow's `notify`/`email` steps
  behave exactly like the Setup test buttons.

## [0.13.0] - 2026-06-16

### Added
- **`split <point|line|polygon>`** — separate a mixed-geometry layer by geometry type,
  keeping only the features of the requested type (via `native:filterbygeometry`).
  Pipe-friendly (one type out per call), so you can process each type on its own:
  `load mixed.gpkg | split line | save lines.gpkg`. This is the way to handle a
  mixed layer through operations that homogenise (like `clip`) without losing the other
  types — split first, process each, keep both outputs. Multipart features are
  preserved; note that whole `GeometryCollection` features are not decomposed by this
  filter (they match none of the single-type sinks).

## [0.12.1] - 2026-06-16

### Changed / clarified — mixed-geometry handling across operations and formats
- **Target formats:** lossless mixed/`GeometryCollection` geometry is preserved when the
  target supports a generic geometry column — **GeoPackage** and **SpatiaLite** (verified
  round-trip), and **PostGIS** (same generic-geometry support, when used as a target).
  **Shapefile cannot** — it stores a single geometry type, so a mixed layer can't be
  written to `.shp`. niva now raises a **clear error** ("Shapefile stores a single
  geometry type … save to .gpkg or .sqlite") instead of letting GDAL silently drop the
  odd parts.
- **Which operations are lossless:** `reproject` preserves mixed geometry losslessly
  (typed path for clean layers; generic-geometry GDAL path for mixed ones). Other
  typed-output operations behave differently and were investigated:
  - `clip`, `dissolve`, and the overlay ops (`intersect`/`union`/`difference`/…) **choose
    their output geometry type from the operation, not the input** (a clip/dissolve of
    polygons yields polygons), and they **coerce silently without error** — so there is no
    failure to catch and no general lossless reimplementation. This is QGIS's intended
    behaviour; for those, the odd non-matching parts are dropped by design. If an op ever
    *does* reject mixed geometry, niva now raises a clear message telling you to `fix`
    first. (Internal: the reproject fallback was refactored to `_lossless_retry`.)

## [0.12.0] - 2026-06-16

### Added
- **`reproject` is collection-safe and lossless — "both, per layer".** A layer that
  mixes geometry types (e.g. an Overture polygon theme with a few Polygon+LineString
  `GeometryCollection` features) used to make `reproject` fail / skip the layer, because
  `native:reprojectlayer` writes a single-typed output sink. niva now tries the typed
  path first (clean layers stay cleanly typed) and, only when QGIS rejects a feature on
  a geometry-type mismatch, falls back to a **lossless generic-geometry reprojection**
  (GDAL `VectorTranslate -nlt GEOMETRY`, via the bundled `osgeo.gdal` — no new
  dependency) that keeps every feature's native type. So clean layers stay typed and
  only the genuinely-mixed ones become generic, with **nothing dropped**. (`save` was
  already lossless.) This removes the need for a lossy `fix` before `reproject`.
- **Encrypted secret storage for `email`/`notify` (QGIS auth store).** The Setup tab can
  now **Save secrets to QGIS encrypted store** and **Load secrets from QGIS store**: the
  SMTP password and ntfy token are kept in QGIS's `QgsAuthManager` (AES-encrypted
  `qgis-auth.db`, unlocked by the QGIS master password), and only the non-secret config
  IDs are stored in settings. No new dependency, no custom crypto — niva never writes the
  secrets to its own files. Loading pushes them into the environment for the verbs.
- **Automatic GeoPackage compaction after a batch.** When an `each` batch writes layers
  into a `.gpkg`/`.sqlite`, niva `VACUUM`s each container once at the end (via
  `Backend.compact`, stdlib `sqlite3`) to reclaim the free pages multi-layer appends
  leave behind.
- **JP2 save defaults to `QUALITY=25`** (GDAL's own default, now set explicitly) so a
  `.jp2` save is never accidentally written near-lossless. Override per format/quality
  with `run gdal:translate … CREATION_OPTIONS=…`.

### Notes
- **Dirty/`GeometryCollection` geometry → use `fix`.** Source layers (e.g. Overture
  themes) can carry stray `GeometryCollection` features that QGIS won't write into a
  typed output, so `reproject`/`clip` would skip those layers. The remedy is the existing
  **`fix`** verb (`native:fixgeometries`), which repairs them into the layer's own type
  (a no-op for clean layers): `each "<dir>" | fix | reproject EPSG:6346 | save out.gpkg`.
  `examples/analyst_plan.niva` now uses this and recovers every layer (0 skips).

## [0.11.0] - 2026-06-16

### Added
- **Directory iteration — `each "<dir|glob|file.gpkg>"`.** Starts a *batch* flow: the
  remaining stages run once per source (every file in a directory/glob, or every layer
  of a GeoPackage). A failing item is skipped (an `OpError`) so one bad file can't
  abort the run; a usage error (`FlowError`) still stops, rather than silently doing
  nothing.
- **Multi-layer write — `save <gpkg> as <layer>`, and batch-aware `save`.** Writes a
  named layer into a GeoPackage, *appending* (the first layer creates the file, later
  ones add to it) instead of overwriting — so many saves accumulate layers in one
  `.gpkg`. Inside an `each` batch, plain `save out.gpkg` names each layer after its
  source; a `save "out/{name}.tif"` path template handles per-item raster outputs.
  Together these do directory-wide reproject/clip into a single GeoPackage (verified:
  every layer of a 25-layer GeoPackage reprojected into one output).

### Changed
- **Hardened against crashing QGIS.** The CLI's standalone runs now route *every* exit
  path — success, handled error, unexpected exception, or Ctrl-C — through
  `QgsApplication.exitQgis()` + `os._exit` in a `finally`, so an unexpected error can
  no longer unwind into QGIS's C++ teardown (a segfault). The plugin's background
  `run_flow` now catches *all* exceptions and returns a result dict, so nothing escapes
  the `QgsTask` worker thread into QGIS. (Audit confirmed niva otherwise never
  `chdir`s, re-inits Processing/Qt inside a live QGIS, or mutates the project beyond
  adding the result layer on the main thread.)

## [0.10.1] - 2026-06-16

### Fixed
- **Raster outputs are no longer left uncompressed.** Raster `save` to GeoTIFF now
  defaults to lossless **DEFLATE + tiling**, with the `PREDICTOR` matched to the data
  type (3 for floats, 2 for other integers, none for Byte); the raster verbs
  (`warp`, `clipraster`, `hillshade`, `slope`, `aspect`) default their
  `CREATION_OPTIONS` the same way so intermediates compress too. Previously products
  were written uncompressed and were often far larger than their inputs (e.g. a 9.4 MB
  DEM tile round-tripped to 1.0 MB after the fix — ~9× smaller, lossless). Override
  with `run gdal:translate … CREATION_OPTIONS=…` for other formats/options.

## [0.10.0] - 2026-06-16

### Added
- **Setup tab guides you through the `email`/`notify` environment.** A new "Email &
  notifications" section with fields for the ntfy (`NIVA_NTFY_*`) and SMTP
  (`NIVA_SMTP_*`) variables, an **Apply for this session** button (sets them in the
  running QGIS so the verbs work immediately), and **Send test notification** / **Send
  test email** buttons for instant feedback. Gmail-friendly placeholders call out the
  App Password. Security: **non-secret fields are remembered** in QGIS settings, but
  the **password and token are applied for the session only and never written to
  disk**; saved non-secret values are pushed into the environment on load. All new
  controls carry tooltips.

## [0.9.0] - 2026-06-16

### Added
- **Utility verbs — side effects that aren't QGIS algorithms** (`niva/utilities.py`):
  - **`notify "message" [to=<topic>] [title=…] [priority=…] [server=…]`** — push via
    ntfy. Server/topic/token resolve from the flow then the environment
    (`NIVA_NTFY_SERVER` default `https://ntfy.sh`, `NIVA_NTFY_TOPIC`, `NIVA_NTFY_TOKEN`).
    Pass-through, so `… | save out.gpkg | notify "done"` chains.
  - **`email to=<address> [subject=…] [body=…] [attach=<file>]`** — send via SMTP.
    Connection + credentials come **only** from the environment (`NIVA_SMTP_HOST`,
    `NIVA_SMTP_PORT` default 587, `NIVA_SMTP_USER`, `NIVA_SMTP_PASSWORD`,
    `NIVA_SMTP_FROM`); TLS is required (STARTTLS, or implicit TLS on 465); fails closed
    if unconfigured. **Gmail-aware:** a `@gmail.com` sender with no host defaults to
    `smtp.gmail.com:587` — set `NIVA_SMTP_PASSWORD` to a Gmail **App Password**.
  - **`catalog <dir> [to=<out.md>]`** — recurse a directory and inventory every
    geospatial dataset (CRS, extent, geometry/fields for vectors; bands for rasters)
    into a Markdown report. Multi-layer GeoPackages are enumerated per layer. Mirrors
    the open-gis-metadata-builder idea.
- Security: secrets for `notify`/`email` are read from the environment only, never the
  flow text, and are never logged or echoed in errors (zero third-party deps — stdlib
  `urllib`/`smtplib`/`ssl`).
- `Backend.sublayers()` — lists layers inside a container (GeoPackage) for `catalog`.

## [0.8.0] - 2026-06-15

### Added
- **Curated verb set expanded from ~12 to ~45**, every alias validated against the
  installed QGIS:
  - *Geometry*: `simplify`, `smooth`, `convexhull`, `boundingbox`, `minrect`,
    `pointonsurface`, `vertices`, `densify`, `subdivide`, `offset`, `swapxy`, `forcerhr`.
  - *Attributes*: `promote`, `collect`, `renamefield`, `dropfields`, `keepfields`,
    `countpoints`.
  - *Overlay / relate*: `union`, `symdifference`, `spatialjoin`, `selectloc`.
  - *Selection*: `snap`, `sample`.
  - *Creation*: `voronoi`, `delaunay`, `pointsalong`.
  - *Raster*: `warp`, `clipraster`, `hillshade`, `slope`, `aspect`, `polygonize`.
- **`save` now writes rasters** as well as vectors — raster results go through
  `gdal:translate` (driver chosen by extension); use `run gdal:translate` for
  format-specific creation options (e.g. JP2 `QUALITY`).
- **`scripts/lint_registry.py`** — the registry linter (planning 07-§9): checks every
  alias's algorithm id and parameter names against the live QGIS Processing registry,
  so the registry fails loud, not silent, when an algorithm or parameter moves.

## [0.7.1] - 2026-06-15

### Changed
- **The Flow tab's `Cancel` button is now labelled `Stop`** (with a tooltip), matching
  what it does — stop the running flow. It stays disabled until a flow is running.
- **Every control in the dock now has an informative tooltip** — across the Flow,
  Convert, and Setup tabs (buttons, the flow editor, the log checkbox/folder, the
  environment report, etc.) — explaining what each one does.

## [0.7.0] - 2026-06-15

### Added
- **Export a flow to a standalone PyQGIS script, and import one back.** `niva export
  <file.niva> [-o out.py]` transpiles a flow into a runnable `.py` (one
  `processing.run(…)` per step, layers piped step-to-step, `save` directing the
  preceding step's OUTPUT) — niva's *eject* path for learning/customising/handing off.
  `niva import <file.py> [-o out.niva]` reverses it. Round-trip works for **niva-shaped
  scripts only** (a flat list of `processing.run` calls); arbitrary PyQGIS can't import
  (loops/conditionals/custom functions are reported, never guessed). The generated
  `.py` carries a header explaining this; import returns warnings for anything it can't
  map. New **Convert** tab in the plugin exposes both with the same caveat spelled out.
  Editing the exported `.py`'s params (or splicing in a new `processing.run` step) and
  re-importing carries the changes back into the flow. Implemented in `niva/transpile.py`.
- **Journal echoes the equivalent `processing.run(...)` call.** Every curated verb and
  every `run` stage now records a copy-pasteable `processing.run('<algorithm>', {…})`
  string in the machine-readable `.jsonl` — the exact algorithm id and fully-resolved
  params (alias defaults, resolved distances, injected `INPUT`/`OUTPUT`) that niva
  hands to QGIS. This lets you reproduce or script any step verbatim. The
  human-readable `.log` is unchanged — it stays **one line per operation** (it already
  shows `[algorithm]`); the full param dict lives in the `.jsonl` only. Built-in verbs
  (`load`/`save`/`assess`/…) carry no `pyqgis` field. Rendering lives in
  `Backend.render_call` so it's shared by every backend; layer handles render as their
  source path/URI rather than a live-object repr.

## [0.6.0] - 2026-06-15

### Changed
- **The plugin runs flows in a background thread — the QGIS UI no longer freezes.** A
  real run now executes in a `QgsTask` off the GUI thread: progress streams in live
  (via a queued signal), **Cancel responds immediately** (no longer only between
  progress ticks), and you can keep using QGIS while a long mosaic builds. The result
  is added to the map on the main thread when the task finishes. Dry-run stays
  synchronous (it's fast and mock-only). Flows remain **serial — one at a time** (the
  dock disables Run while one is in flight), honouring the single-QgsApplication rule
  (Oscar A9).
- **`save` no longer touches `QgsProject`** (uses a standalone
  `QgsCoordinateTransformContext`), so it's safe to call off the main thread. Plugin
  unload cancels any in-flight task. (Engine/grammar unchanged; CLI still synchronous.)

## [0.5.0] - 2026-06-15

### Added
- **Live progress, elapsed time, and cancel.** niva now emits status as a flow runs:
  - **Progress** — a `▶ <stage>` line as each stage starts, throttled **algorithm
    progress %** during long operations (via QGIS's processing feedback), and a
    per-stage `✓ <elapsed>`. Shown live in the plugin dock (it repaints mid-run, so a
    minutes-long mosaic streams `5% 10% …` instead of freezing silently) and on the
    CLI (stderr). API: `niva.flow(progress=callable)`.
  - **Elapsed time** — per stage in the progress, a **total when the job's done** (dock
    + CLI `# done in …`), and in the run-journal footer (`# done: … in 2.3 s`).
  - **Cancel** — a **Cancel** button in the dock aborts the running operation
    (`niva.flow(cancel=callable)`; the dock disables Run while a flow is in flight).
    In-process native algorithms abort promptly; gdal subprocess ops are best-effort
    (a fast one may finish first). A canceled run is reported as `… canceled`.
  - **+5 tests** (141 total); verified live progress %, elapsed, and real cancellation.

## [0.4.0] - 2026-06-15

### Added
- **Wildcards and `~` in paths — no more listing every file.** A `run` option value
  that contains a path glob (`*`, `?`, `[…]`) is expanded to the **sorted matching
  files**, so `run gdal:buildvirtualraster INPUT="tiles/*.jp2" …` reaches every tile
  without naming them. Relative globs resolve against the flow's directory; `;`-lists
  still work and combine with globs; a glob that matches nothing is a clear error; and
  a value that just happens to contain `*` (e.g. an expression `area * 2`) is left
  alone. `~` (home) is expanded in `run` values and in `load`/`save`/`assess` paths.
  **+4 tests** (136 total). Note: a glob in the *output's own folder* can match the
  output — use a specific pattern (e.g. `w_*.jp2`, not `*.jp2`).

## [0.3.1] - 2026-06-15

### Added
- **Friendlier error for `load @file.ext`.** `@` is for *saved database connections*,
  but `load @example.gpkg` is a common slip (it searched for a connection named
  `example`). niva now detects a `@`-ref that ends in a known file extension and points
  at the path form: ``load "example.gpkg|layername=<layer>"``. +1 test (132 total).

## [0.3.0] - 2026-06-15

### Changed
- **One run log per QGIS session (not per run), one line per operation.** The plugin
  now appends every run to a single session journal (`niva-session-<stamp>.{log,jsonl}`)
  until you hit a new **Reset (new file)** button in the Setup tab — and the Setup tab
  shows the current session-log path. The human `.log` is now strictly **one line per
  operation** (`<ts>  <stage>  [algorithm]  → <full path>  (ms)`, errors inlined), with
  a one-line `# run:` marker separating runs and a one-line `# done:` per run (was a
  3-line header + footer). `niva.flow(..., log_append=True)` enables session append;
  the CLI's `--log` still truncates per invocation. **+3 journal tests** (131 total).

## [0.2.1] - 2026-06-15

### Fixed
- **Plugin: `flow() got an unexpected keyword argument 'log'` after reinstalling
  without restarting QGIS.** Python caches modules in `sys.modules` across plugin
  reloads, so a reinstalled plugin kept running the *old* vendored niva. The entry
  point now **purges cached `niva` modules and loads the bundled copy first**, so a
  reinstall + reload picks up the new code with no QGIS restart. The plugin now always
  uses its own vendored niva (matching its runner) rather than preferring an external
  one — no version skew.

## [0.2.0] - 2026-06-15

Plugin maturity + observability: a Setup tab, a timestamped run journal (human +
machine), configurable logging, and QGIS-4/Qt6 fixes. (Engine/grammar unchanged from
0.1.0.)

### Added
- **Plugin: configurable run logging (Setup tab).** A "Write a log for each run"
  toggle + a log-folder field (with Browse), persisted in QGIS settings
  (`niva/log_enabled`, `niva/log_dir`). The dock passes the folder to the runner; the
  environment report shows the effective setting. (Of niva's three env vars, only
  `NIVA_LOG` is meaningful in-plugin — now exposed as a setting; `QGIS_PREFIX_PATH`
  and `QT_QPA_PLATFORM` only affect the standalone CLI bootstrap, so they're not in
  the UI.)
- **Plugin: a Setup tab** showing the environment a niva user cares about — niva
  version + where it's imported from (bundled vs pip), built-in + aliased verbs, the
  number of algorithms `run` can reach + the Processing providers, the available
  database connections (the `@conn` names), QGIS/Qt/GDAL/PROJ/GEOS versions,
  Python/platform, and where run journals land. Rendered as markdown with Refresh +
  Copy buttons (`plugin/environment.py`; the dock is now a Flow + Setup tab widget).
- **Run journal — a timestamped log of every operation** (planning 08-§2), written as
  **two files** because humans don't read JSON:
  - `<base>.jsonl` — machine-readable JSON Lines: a versioned header
    (`niva_journal`/version/flow/started) then one record per op (ts, kind, stage
    text, algorithm, ok, duration, full output path), plus a footer.
  - `<base>.log` — plain text a person reads: a header, one timestamped line per op
    (`<ts>  <stage>  [algorithm]  → <full path>  (12 ms)`), and a `done — N ops` footer.
  - **Full paths everywhere** — outputs are logged as **absolute** paths (resolved
    against the run's cwd), so you can always find what a flow wrote (the fix for the
    relative-path confusion).
  - **The plugin auto-logs every run** to the OS temp dir (`…/niva_logs/niva-<ts>.log`)
    and shows the path in the dock. CLI: `niva run flow.niva --log <base>`; both honor
    the `NIVA_LOG` env var; `niva.flow(text, log=<base>)` in Python.
  - Kept alongside the existing per-`save` lineage in `QgsLayerMetadata.history`
    (**now timestamped too**) — you get *both* the layer's embedded history and the
    run log. Only stage text + resolved paths are logged; never params or credentials.
  - **6 new journal tests** (128 total, all green).

### Fixed
- **Plugin: QGIS 4 / Qt6 compatibility metadata.** QGIS 4 flagged the plugin as
  "designed for QGIS 3.0–3.99" because `metadata.txt` had no maximum version (it
  defaults to `<min-major>.99`) and no Qt6 marker. Set `supportsQt6=True`,
  `qgisMaximumVersion=4.99`, `qgisMinimumVersion=3.22`. Rebuild/reinstall the zip.
- **Plugin: only the input stands out; read-only panels recede.** Instead of forcing
  white everywhere (which made the dock all-white), the dock now lets the theme style
  the editable flow editor as a field and paints the read-only output + Setup report
  with the dialog's window colour (theme-adaptive via the palette — works on light and
  dark themes). The area you type into is visually distinct from the rest.
- **Plugin: Qt6 scoped-enum crash opening the dock.** `Qt.RightDockWidgetArea`
  (Qt5) is `Qt.DockWidgetArea.RightDockWidgetArea` in Qt6 (QGIS 4), so the toolbar
  button raised `AttributeError`. Resolved both ways; the `QFont.StyleHint` hint is
  guarded too. Rebuild/reinstall `niva_qgis.zip`.

### Added
- **QGIS plugin on-ramp** (`plugin/`). A dock to write or open a `.niva` flow and
  **Run** it in the current QGIS session — a saved output lands on the map; a
  **Dry-run** button validates the flow over the mock backend (no geoprocessing) and
  prints the operation sequence. **Cross-platform with no install step:** niva
  (zero-dependency, pure Python) is **vendored** into the plugin and runs
  **in-process** — no `pip`, no subprocess, no interpreter detection — so it behaves
  identically on Windows (OSGeo4W), macOS, and Linux, sidestepping the install
  friction Oscar flags as the top adoption risk (E2/E3). The plugin prefers a
  `pip`-installed `niva` if present, else the vendored `libs/niva`.
  `plugin/build_plugin.sh` vendors niva and builds `niva_qgis.zip` (top-level folder
  `niva_qgis`, so it never shadows the vendored `niva` package). `plugin.py` /
  `dock.py` / `runner.py` go through `qgis.PyQt` (Qt5 + Qt6). Verified on the
  installed layout (repo off `sys.path`): the vendored import resolves with no
  collision and a real flow runs through the dock's runner.

## [0.1.0] - 2026-06-15

First working release — niva runs real geoprocessing. The pipeline is complete end
to end (grammar → registry/binder → engine → PyQGIS backend), validated against real
GIS data (a 24-layer Youngstown GeoPackage + DEM rasters) on QGIS 4.0.3: **122 unit
tests + 19 niva-script integration checks**, all green. Highlights:
verbs `load` (files + `@conn` tables + multi-layer-safe), `save` (with metadata +
auto-lineage), `sql @conn`, `run` (any algorithm, incl. multilayer params), `call`
file composition, `metadata set`, `assess` (quality + topology + lineage),
`describe`; 12 curated `native:*` aliases; a parse/`--dry-run`/`--explain`/`describe`
CLI and a `niva.flow()` Python API; near-zero runtime dependencies.

### Changed
- **`run` reaches multilayer params; fixed a GeoPackage save bug** (both surfaced by
  real raster/vector data):
  - A `run` option value containing `;` is now split into a **list** — QGIS's own
    layer-list separator — so multilayer params work, e.g.
    `run gdal:merge INPUT="a.tif;b.tif;c.tif" …`. (Enabled merging 13 DEM tiles +
    clipping to an AOI entirely via `run`; see `build_ytown_dem.niva`.)
  - **`save` to GeoPackage no longer fails when the layer carries an `fid` field**
    (`UNIQUE constraint failed: fid` — common in `pointsalonglines`, `intersection`,
    joins). niva tells GDAL to mint a fresh primary key and keeps the source `fid`
    as an ordinary attribute (no data loss). +2 tests (122 total).
- **Traceability matrix: ten verified `run`-only pipelines.** Added a "Proof" section
  with **10 multi-stage, alias-free pipelines (built-ins + `run` only)**, each
  **executed against the real Youngstown dataset** with recorded feature counts — the
  concrete evidence behind the Oscar verdict (answers "I don't see the concrete
  tests"). Plus the cross-provider raster build (`gdal:merge` → `gdal:clip…`).
- **Multi-layer sources handled explicitly.** A GeoPackage/SpatiaLite holds many
  layers, tables, and views — niva no longer silently loads the first. `load` of a
  multi-layer source **without** a layer name is now a clear error listing the
  available layers; pick one with `load "file.gpkg|layername=<name>"` (selects a
  layer, attribute table, or view), or a DB table with `load @conn[.schema].table`.
  Single-layer files load unchanged. +2 PyQGIS smoke tests (120 total). The
  traceability matrix gains a "Multi-layer sources" section (and a save caveat:
  one layer per file today; multi-layer write is planned, 03-§2.5).
- **Widened `reproject` and `join` aliases** to expose previously-hidden QGIS params
  (surfaced by the traceability matrix): `reproject` gains `convert_curved` and
  `transform_z` flags (moving `CONVERT_CURVED_GEOMETRIES` out of `forced` so it is
  overridable; both still default off); `join` gains `unmatched=<path>` for the
  `NON_MATCHING` sink (write the input rows that found no match). +2 tests (118 total).
- **Traceability matrix (`docs/planning/14`) reworked:** the alias table now lists the
  verbose original QGIS signature **last**, so the niva-signature and status columns
  stay visible; added a section explaining the `run` escape hatch (how to reach any
  of the installed algorithms — `describe` to find params, auto-filled `INPUT`/
  `OUTPUT`, `KEY=value` for the rest) with **8 worked native examples** verified
  against the live registry; and a section **proving `run` meets Oscar's success
  bar** (defuses Top-7 #6 registry-rot and #7 scope/bus-factor, softens #5 the cliff;
  zero deps, no injection surface). Regenerate with `scripts/gen_traceability_matrix.py`.

### Added
- **`assess` now reports existing metadata/lineage and checks duplicate geometries.**
  The report gains a **Metadata** section (title, abstract, keywords, and the
  lineage/history — 08-§4's "any existing lineage"), and `deep` adds a
  **duplicate-geometry** count (a topology check via WKB hashing) alongside the
  invalid/empty/null checks. This also lets niva verify its own metadata round-trip
  in pure niva (set → save → load → assess shows it).
- **Integration tests are now niva scripts** (`tests/integration/flows/*.niva`),
  run through the real `niva run` CLI against real GIS data and **self-verified by
  grepping the `assess` reports niva produces** — the language tests itself.
  `tests/integration/run.sh` substitutes the data/output paths, runs each flow
  (asserting exit codes — incl. the degrees guard's exit 2), and checks the reports:
  assess+topology, reproject/buffer/dissolve, clip-by-overlay (497 features),
  metadata+lineage round-trip, the `run` escape hatch, and a `call`-composed cat
  territory. **19/19 checks pass** on QGIS 4.0.3. Non-destructive, env-overridable
  data paths, SKIPs cleanly when QGIS/data absent. (Replaces the earlier Python
  integration driver.)
- **`scripts/run_tests.sh`** — runs the unit suite on QGIS's Python (falls back to
  plain Python, where the PyQGIS smoke tests skip). Reads unittest's own `OK`/`FAILED`
  line so the QGIS interpreter-shutdown segfault can't clobber the exit code.
- **v0.1 increment 11 — `describe`: introspection** (planning 11). Makes the `run`
  escape hatch discoverable. `niva describe <verb>` / `niva.describe("buffer")` shows
  how an alias maps to its QGIS algorithm (positionals, options with defaults/enums,
  flags) — pure, no QGIS. `niva describe <algorithm-id>` (anything with `:`)
  introspects the live algorithm: parameters (name, type, optional, default) and
  outputs — describe an algorithm, then `run` it. CLI `describe` subcommand +
  `niva.describe()` API; the algorithm path tears QGIS down cleanly (no shutdown
  segfault). **4 new tests** (103 bare / 116 under QGIS) incl. a real
  `describe native:buffer`.
- **v0.1 increment 10 — auto-lineage to metadata history** (planning 08-§3). Every
  `save` now records the niva stages that built the layer into the output's
  `QgsLayerMetadata.history` (prefixed `niva: `), so a saved layer carries its own
  reproducible recipe — provenance as a byproduct, with no extra verbs. The engine
  accumulates each flow's stage text and passes it to `save`; the PyQGIS backend
  appends history items (alongside any descriptive `metadata set` fields) and writes
  them with `saveDefaultMetadata` (`.qmd` sidecar fallback). **4 new tests** (100
  bare / 112 under QGIS) incl. a real round-trip reading the recipe back out of the
  saved GeoPackage. The Youngstown example header updated: **RUNS (v0.1)**.
- **v0.1 increment 9 — `assess`: data-quality reports** (planning 08-§4). A
  signature niva feature — provenance/quality as a byproduct.
  `assess [deep] to <report.md>` profiles the current layer and writes a markdown
  report (overview: type/feature-count/CRS-set?/extent; full field schema). `deep`
  adds quality checks: invalid + empty geometry counts and per-field null counts.
  A pass-through stage (profile, then keep piping). Backend returns a structured
  profile dict (so markdown formatting is unit-tested with a mock); PyQGIS inspects
  the real layer (vector full, raster basic). **11 new tests** (97 bare / 108 under
  QGIS) incl. a real `assess deep` that catches a null value and reports it.
- **v0.1 increment 8 — `metadata set`** (planning 08-§3). Attach descriptive
  metadata to the current layer and persist it on the next `save`:
  `metadata set title="…" abstract="…" keywords=a,b,c` (also `identifier`, `license`).
  A pass-through stage — sets `QgsLayerMetadata` in memory; `save` writes it to the
  file (GPKG/SpatiaLite via an explicit layer name + `saveDefaultMetadata`, falling
  back to a `.qmd` sidecar). Unknown fields are a FlowError. `save` now sets a layer
  name on multilayer outputs so metadata can be persisted and reloaded. **6 new
  tests** (92 bare / 102 under QGIS) incl. a real round-trip (write title/abstract/
  keywords → reopen → verify).
- **v0.1 increment 7 — database connections: `@conn` loading + `sql`** (planning 02,
  `niva/engine/connections.py`). niva reaches databases through **named QGIS
  connections** the user already configured:
  - `load @conn.table` / `load @conn.schema.table` — load a DB table as a layer.
  - `sql @conn "SELECT …"` — run a query and get a result (query) layer back, pipeable.
  - **Security boundary:** niva passes only the connection *name* to the backend,
    which resolves host/credentials from QGIS's own connection store. niva never
    sees, stores, logs, or transmits credentials (global CLAUDE.md §1/§14); the SQL
    text is not logged either (it stays in the provider). `_find_connection` searches
    all DB providers by name; `load_table` uses `tableUri`, `run_sql` uses
    `createSqlVectorLayer` (the provider parameterises — no string-built creds).
  - **13 new tests** (87 bare / 96 under QGIS) incl. real SpatiaLite smoke tests
    (`load @conn.homes`, `sql @conn "…WHERE id=1"`) that register a temp connection
    and clean it up, plus an unknown-connection → OpError check.
- **v0.1 increment 6 — the `run` escape hatch + `explode` alias** (planning 07-§8).
  `run <algorithm> KEY=value …` reaches **any** QGIS algorithm with no curated alias
  — the long tail the example needs (gdal, grass, pdal, native). Implemented as an
  engine built-in routing to a new `Backend.run_raw`: the backend injects `INPUT`
  from the upstream layer (piped use) and a temporary `OUTPUT` when absent, and
  returns the output as a handle (or `None` for terminal exports like a PDF/folder).
  Option values are best-effort scalar-coerced (`RES=1.5`→float, `FLAG=true`→bool,
  `RESAMPLING=1`→int; paths/CRS/field names stay strings). Added the `explode` alias
  (`native:multiparttosingleparts`). CLI `--explain`/`--dry-run` render `run` stages
  specially. **6 new tests** (74 bare / 80 under QGIS), incl. a real
  `run native:centroids` smoke test.
- **v0.1 increment 5 — `call` execution** (`niva/engine/engine.py`, planning 02/10).
  The file-composition mechanism the design centres on now runs: a `call <file>`
  statement resolves the target **relative to the calling file's directory**, parses
  it, and executes its flows inline (depth-first). `niva.flow`/`run_file` and the CLI
  thread the `base_dir` through so paths resolve correctly; the engine carries a
  call-stack for **cycle detection** (`a → b → a` is a clear FlowError, not a hang),
  and a missing/un-readable target is a FlowError with the offending name. Calling
  the same file twice in sequence is allowed (not a cycle).
- `tests/test_call.py` — **9 new unittest cases** (68 on bare Python, 73 under QGIS):
  composition, relative-path resolution, nesting, result propagation, self/indirect
  cycles, missing file, and error-propagation from a called file.

### Changed
- **Consistency pass over the planning set.** Unified verb names to canonical
  `filter`/`compute` (was `where`/`calc` in 02/06/07); fixed the version scheme so
  `v1.1` → `v0.2` (the roadmap's post-MVP release; `v1.1` contradicted
  `v1.0`=stable) and clarified that the MVP = `v0.1`; flagged doc 00 as historical
  with its superseded decisions (library-first, pipelines-deferred) and answered
  open questions struck through; removed remaining stale "both backends /
  auto-select in v1" wording.
- **Backend decision pinned: PyQGIS-only for v1** (ratifies `00-§3.3`). The
  in-process backend runs both interactively and headless (a headless
  `QgsApplication`), so one backend covers every context with no
  normalization/parity cost. The `Backend` ABC stays as the extension seam;
  `qgis_process` + auto-selection move to v0.2. Updated across docs 00–05.

### Added
- **v0.1 increment 4 — the PyQGIS backend: niva now runs real geoprocessing.**
  (`niva/engine/pyqgis.py`, `niva/__init__.py`, `niva/cli/main.py`, planning 02-§4.)
  - `PyqgisBackend` implements the four `Backend` methods against QGIS:
    `load` → `QgsVectorLayer`/`QgsRasterLayer`; `run` → `processing.run` with the
    upstream layer fed into the input param + `TEMPORARY_OUTPUT`, errors wrapped as
    `OpError`; `save` → `QgsVectorFileWriter` (driver by extension); `crs_of` →
    `CrsInfo` from the layer CRS (`isGeographic()` + metres-per-unit factor) so the
    engine's distance resolution runs against the real CRS. All `qgis` imports are
    lazy, so the package stays importable on any interpreter.
  - `ensure_qgis()` reuses a running QGIS or bootstraps a headless one, working
    around three standalone-PyQGIS traps (all in planning 02-§4.1): the Processing
    registry is empty without an explicit `QgsNativeAlgorithms` provider, and both
    that provider **and** the `QgsApplication` must be retained or GC tears the
    registry down. The CLI's owned-app path hard-exits cleanly to dodge the
    shutdown segfault.
  - **Python API:** `niva.flow("…")` and `niva.run_file(path)` (default real
    backend; pass `backend=MockBackend()` to dry-run without QGIS).
  - **CLI now executes for real** by default; `--dry-run` (mock) and `--explain`
    (plan only) remain QGIS-free.
  - `tests/test_pyqgis.py` — **5 smoke tests** that run actual geoprocessing
    (load→buffer→save produces a real polygon layer; 1km-buffer dissolve; filter;
    the degrees-mismatch FlowError; bad-load OpError). They **skip cleanly** when
    QGIS is absent, so the suite is 59-pass on bare `python3` and **64-pass under
    QGIS's Python** (verified on QGIS 4.0.3 / Python 3.14, PyQGIS at
    `/usr/share/qgis/python`).
- **v0.1 increment 3 — the engine core** (`niva/engine/`, planning 05/06),
  QGIS-free and mock-backed so it is fully unit-testable with plain `python3`:
  - `layer.py` — the `Layer` handle (backing `kind`: source/qgs/db_table/memory +
    vector/raster `facet`) and `CrsInfo`. The engine moves *handles*; only a backend
    ever touches real QGIS objects.
  - `backend.py` — the `Backend` seam (load / run / save / crs_of) and `MockBackend`,
    a no-QGIS double that records calls and returns fake handles (powers `--dry-run`).
  - `units.py` — `resolve_distance`: a unit-bearing distance (`100m`) is converted
    into the layer's CRS units; a linear distance on a **geographic CRS is a hard
    error**, never a silent degrees buffer (03-§1.1); a bare number is trusted as
    CRS units.
  - `engine.py` — `Engine.execute`: walks the program, threads one `Layer` down each
    flow's pipe, routes built-in `load`/`save` vs registry aliases, feeds the
    upstream layer into each op's input param, resolves distances against its CRS,
    and delegates to the backend. Unknown verb / op-before-load / save-with-nothing
    are `FlowError`s with line + stage; `call` is parsed but not yet executed.
  - `tests/test_engine.py` — **18 new unittest cases** (59 total, all passing):
    pipeline threading, filter-as-alias, multi-flow, the full distance/CRS matrix
    (m/ft/km, bare number, deg, and both degrees-mismatch errors), and the error paths.
  - CLI gains **`--dry-run`**: runs the whole flow through the engine over
    `MockBackend` and prints the validated backend operation sequence.
  - `requires-python` bumped to **>=3.12** (QGIS 4.x ships Python 3.12).
- **v0.1 increment 2 — the registry + binder** (`niva/registry/`, planning 07):
  - `model.py` — the declarative `Alias` / `Arg` / `Option` / `Flag` schema.
  - `definitions.py` — `CORE`: the curated verb set (buffer, clip, intersect,
    difference, dissolve, reproject, fix, centroid, join, zonalstats) as Python
    data, every `native:*` id and param name grounded in QGIS 4.0.3.
  - `registry.py` — `Registry` lookup with duplicate detection; `core_registry()`.
  - `binder.py` — `bind(stage, alias) → BoundOp`: splits flags from positionals,
    coerces by type (`distance` → `Distance(value, unit)`, enum word → QGIS int,
    `enumlist`, comma-lists), fills defaults, forces fixed values, validates
    arity / required options / unknown options — all `FlowError`s with line + stage.
  - `values.py` — the `Distance` value type (unit resolved against the layer CRS at
    run time, never silently reprojected).
  - `tests/test_registry.py` — **20 new unittest cases** (41 total, all passing).
  - **Registry format decision:** Python data, **not** YAML — a YAML parser would be
    a runtime dependency and break the zero-dep rule (Oscar E1). Doc 07 §11 revised.
  - CLI upgraded to **parse + bind**: alias verbs now print their resolved QGIS
    algorithm and `processing.run` params (built-ins marked pending the engine).
- **v0.1 MVP — build started (the package).** First code increment, grounded in
  the design docs:
  - `pyproject.toml` (hatchling; **zero runtime deps** per Oscar E1; `niva` console
    script; `dev` extra = pytest).
  - `niva/grammar/` — the **lexer + parser** (`10-grammar-spec.md`): comment
    stripping, quote-aware pipe splitting and stage tokenization (`key="…"`,
    `"expr"`, `@conn`, distances), `|` line-continuation, blank-line flow
    separation, and `call` statements → a `Program` of `Flow`/`Stage`/`Call`.
  - `niva/errors.py` — `FlowError` (exit 2; names file+line+stage) / `OpError`.
  - `niva/cli/` — a **parse-only CLI** (`niva "<flow>"`, `niva run <file>`) that
    prints the parsed structure (the engine/backend aren't built yet).
  - `tests/test_grammar.py` — **21 stdlib-`unittest` tests, all passing**; runs in
    QGIS's own Python with no install (where CI will run them).
- **Worked verb reference** (`docs/planning/13-verb-reference.md`): the verb model
  fully explained (positional/flag/option, defaults, enum-by-word, units,
  input/output threading), three signatures from simple to complex (`reproject` →
  `buffer` → `join`) each with the resulting `processing.run` call, and a composite
  flow that uses all three. Writing it **exercised the design and surfaced issues**:
  fixed back into the specs — list-valued options (`10-§2.1`), `save` creates
  parent dirs (`03-§2.5`); and logged as open — stage line-wrapping and
  text-flow secondary outputs (`00`), plus a new silent join-key-type-mismatch
  risk (Oscar D8). Also confirmed the simplified `filter` (`03-§3`) is essential,
  not optional.
  - **Round 2 — `zonalstats` (raster × vector)** stressed the enumlist + raster
    input: **verified** the `stats` enum vocab matches live QGIS; and surfaced —
    the **layer handle is vector-centric** (needs a vector/raster facet + piped
    type-checking, noted in `02-§3.1`, Oscar A10), a **raster-secondary CRS
    caveat** (don't silently warp, `03-§1.2`), and **field-name truncation** on
    Shapefiles (Oscar D9). Fixed a consistency bug: doc `06`'s `zonalstats`
    example used the space form → corrected to `key=value`.
  - **Round 3 — the SQL path** (`13-§8`) stressed cross-surface bridging and the
    connection model. **Spec'd the `sql` verb** (`03-§2.6`): three forms (`@conn`
    query-layer / `from file` `gdal:executesql` / bare `qgis:executesql` virtual),
    `input1` table naming, `key=`/`geom=`/`crs=` for non-self-describing SELECTs,
    result-CRS from the SRID, and a v1 **read-only rule** (top-level SELECT, run in
    a read-only transaction). **Corrected** the conflation of `SELECT` reads with
    the write-only `*executesql` algorithms, and reconciled the drifted `sql`
    syntax (`06-§4.4` used `use @conn`/`| load`). New risks: Oscar C15 (read-only
    detection), C16 (SELECT not self-describing).
  - **Round 4 — the `call` path** (`13-§9`) stressed multi-file composition.
    Spec'd in `03-§4.1`: `call` is a **statement, not a pipeable stage** (no shared
    `current` layer — handoff is via saved files / the live project); **path
    resolution split** (call-target = caller-relative, data paths = run `work_dir`);
    cycles/nesting with a max-depth backstop; provenance across calls — the journal
    tags each op by **source file** and lineage records the **call chain** (`08`);
    errors name the **file + line** across calls (`02-§6`). New limitation Oscar
    U11 (`call` doesn't transform the current layer; parameterized `call` is v2).
  - **Round 5 — the `assess` / lineage round-trip** (`13-§10`) stressed provenance
    across non-algorithm steps and runs. Spec'd in `08`: `sql`/`load` lineage
    entries (no `native:*` id — record the SQL+engine / source); **multi-input
    lineage merge** (flatten each input's history, role-tagged); sharpened
    "data-altering" to **include `filter`/`extract`** (they define the output, so
    they're recorded, not omitted); DB sources carry no lineage store (v1 records
    on the file output); the `assess` report is self-documenting (version/source
    stamp). New risk Oscar D10 (merge can mislead/bloat); open question on
    structured-provenance representation.
  - **Round 6 — the `add`-to-live-project path** (`13-§11`) stressed the
    interactive backend. Spec'd `add` (`03-§2.7`): **live-session only** (headless
    `add` warns/skips; an add-only flow errors headless); **sinks pass through** so
    `save … | add` chains (`02-§2a` corrected); `add` registers a *temporary*
    project layer (lost on close unless saved); default name + QGIS default
    styling (no styling verb in v1); **main-thread only** (can't background an
    `add`-flow). New limitation Oscar U12; raster `add` ties to A10.
  - **Synthesis (`13-§0`)** rolls up the six exercise rounds into a box score: 34
    issues surfaced, ~26 folded into specs, 1 verified-positive, ~5 still open,
    8 logged as Oscar risks — grouped by theme (grammar/verbs, sinks, the layer
    handle, SQL, `call`, provenance) so the conclusions aren't buried in the rounds.
  - **Verified all of `13`'s signatures against live QGIS 4.0.3** — param names,
    defaults, and enum-by-word mappings (`buffer` cap/join, `join` method,
    `zonalstats` stats) all confirmed; noted in the doc header.
- **Closed the two v1 blockers** flagged by Oscar (G1/G2), now specified in
  `03-mvp-scope.md`:
  - **Distances & units** (§1.1): a bare number = the layer's CRS units; unit
    suffixes (`100m`/`2km`/`ft`/…) convert; a linear distance on a **degrees CRS
    is a hard error** with a reproject fix — niva never silently buffers in
    degrees; auto-reproject convenience deferred to v0.2.
  - **`save` semantics** (§2.5): GeoPackage default + extension-inferred format;
    `as <layer>` naming in a container; replaces the target by default **but
    refuses to overwrite a source read earlier in the same flow**; `append`
    option; never reprojects; lock-aware errors; `--dry-run` preview.
  Marked resolved in `00` and Oscar (G1/G2/C8 closed; MVP-odds gate cleared).
- **Closed the remaining design holes (G3–G9)** — nothing now blocks *building* v1:
  - **CRS handling policy** (`03-§1.2`): work in each layer's CRS, never silently
    reproject; reproject secondary→primary on multi-input ops (logged); no-CRS =
    hard error.
  - **Error UX** (`02-§6`): every error names the failing stage + offending token
    in plain language with a suggested fix; friendly by default, `-v` for detail;
    common-error mapping.
  - **Formal grammar** (`10-grammar-spec.md`): EBNF + lexical rules.
  - **CLI & Python-API reference** (`11-cli-and-api-reference.md`).
  - **Config spec** (`09-§6a`): TOML, locations, precedence, v1 keys.
  - **Journal schema** (`08-§2`): versioned JSONL, secrets redacted.
  - **Security & threat model** (`12-security-model.md`).
  Oscar's gap verdict updated: only process/coverage docs (G10–G17) remain, and
  they can wait for code.
- **Failure register** (`docs/planning/Oscar_the_Grouch.md`): a comprehensive,
  adversarial catalogue of how niva could fail — premise/market, architecture,
  engineering, packaging/environment (incl. breaking QGIS's own Python), data
  correctness (silent wrong results), users, and sustainability — each with a
  severity and a mitigation, plus an existential-risk shortlist. Also includes a
  **performance & computational-limits deep dive** (§9: OOM/memory, scaling
  envelope, materialization I/O, large SQL results, caching, interactivity);
  **Oscar's review of the planning docs for gaps** (§10: undecided fundamentals
  that block v1 — distance units, `save` semantics, CRS policy, error UX — and
  missing specs/process docs); and a **conclusion estimating the probability of
  success of each development phase** (§12: ~60% MVP → ~3% full maturity,
  cumulative, gated by non-technical factors).
- **Deployment & operation doc** (`docs/planning/09-deployment-and-operation.md`),
  analyst-friendly: niva installs into QGIS's own Python (pip now; QGIS plugin
  later); connects to QGIS tools, files, and databases via QGIS's saved
  connections (`@name`, no stored credentials); the human-interface options
  (`.niva` files, CLI, QGIS console, marimo, later a plugin GUI and service mode);
  where it runs (workstation/headless/CI/service); and a phased maturity table.
- **PRD reworked** (`docs/planning/01-prd.md`) as the capstone summary of everything
  decided: the procedural grammar + `call`, the one-grammar-every-surface value
  prop (Processing native-first, expressions, `sql` passthrough), **provenance for
  free** (assess + op-log + lineage), the ~40-verb alias registry, the layer
  handle, and updated v1 goals/non-goals/success-criteria/risks (SQL reads in v1,
  writes v2; backends flagged as the one unsettled call).
- **File composition (`call`)**: a `.niva` file executes procedurally, and a
  `call <file.niva>` may appear anywhere to run another file's flows inline —
  procedural reuse / macros. Documented in `03-§4.1`, placed on the roadmap
  (v0.2 parameterless; v2.0 parameterized), and captured in concepts.
- **Worked example** (`examples/youngstown_cat_canvassing.niva`): the full
  `use_cases.md` workflow expressed in the proposed niva grammar (illustrative,
  not runnable) — multi-source/CRS/format load, assess, reproject, clip, geocode,
  PostGIS select, lidar→DEM→slope, GRASS routing/TSP, atlas handouts, and
  metadata/lineage on save.
- **Provider preference order (decided)**: native > gdal > qgis > pdal > … >
  **GRASS/SAGA last** — documented in `07-§12.1` and applied across the use-case
  walkthrough (`03-§2.4`), roadmap, and concepts. The canonical use case is shown
  to be almost entirely native, with GRASS reached (via `run`) only for
  cost-surface routing / TSP, which native lacks.

- **Planning materials** (`docs/planning/`): critique & open questions, product
  requirements for the non-programmer text-pipeline grammar, architecture, MVP
  scope, roadmap, and captured concepts.
- **QGIS capability surface reference** (`docs/planning/06-qgis-surface-reference.md`
  + `docs/planning/reference/*.tsv`): a snapshot, enumerated live from QGIS 4.0.3, of
  everything niva could reach — 769 Processing algorithms (8 providers), 406
  expression functions, SpatiaLite/PostGIS spatial SQL (cross-checked against the
  official SpatiaLite 5.1.0 and PostGIS function references — ~300+ documented
  spatial functions each, under OGC `ST_` plus legacy/extension names), the
  SQL-capable data providers and OGR/GDAL drivers, and the full version stack —
  with current signatures/access and before/after niva examples. Cross-checked
  against the QGIS Processing manual (framework model, Modeler/batch) and the
  SpatiaLite topics cookbook (Virtual Tables for SQL across heterogeneous
  sources).
- **Alias registry design** (`docs/planning/07-alias-registry-design.md`): how niva
  maps friendly verbs onto QGIS algorithms — the declarative entry schema,
  grammar→parameter binding, type coercion, enum vocabularies, the raw `run`
  escape hatch for full coverage, generation/validation against the live
  registry, and worked examples.
- **Layer handle contract** in `docs/planning/02-architecture.md`: the value threaded
  through the `|` pipeline — one `Layer` type with four backing kinds (source /
  live QgsVectorLayer / db_table / memory), its invariants, and the rules for
  **crossing surfaces** (Processing ↔ SQL ↔ expressions) with materialization
  only at boundaries that need it; connections by `@name`; eager-now/lazy-later.
- **Concepts captured** reworked (`docs/planning/05-concepts-captured.md`): the
  disposition table now spans the original exploration plus the surface (06),
  engine/registry (02/07), and provenance (08) concepts — including the
  five-surface model, the three-way name collision and its resolution, the layer
  handle, and provenance-as-byproduct; backends flagged as the one unsettled call.
- **Roadmap** reworked (`docs/planning/04-roadmap.md`): v0.1 MVP → v2.x sequenced
  across three parallel tracks (grammar/engine, coverage via the registry,
  provenance), reconciled with the ~40-verb set, SQL read-in-v1/writes-in-v2, the
  layer handle contract, and the logging/assess/auto-lineage plan.
- **Metadata, data quality & lineage surface** in `docs/planning/06-§2.5`: the
  "Metadata tools" algorithms (with signatures) + `QgsLayerMetadata` model, the
  21-algorithm Check-geometry group and profiling stats for quality assessment,
  and proposed niva verbs.
- **Data quality, provenance & lineage design** (`docs/planning/08-data-quality-
  provenance.md`): the operation log / run journal, the `assess` verb for
  profiling incoming data (CRS/schema/validity/duplicates/nulls), and
  auto-recording data-altering steps as formal metadata lineage
  (`native:addhistorymetadata` → `QgsLayerMetadata.history`) on save — making
  provenance a byproduct of the work.
- **Initial verb set** in `docs/planning/03-mvp-scope.md`: a curated ~40-verb v1 set
  (9 built-ins incl. `sql` read passthrough; Tier 1 + Tier 2 registry aliases),
  every alias mapped to a real, verified QGIS 4.0.3 algorithm id, tied to the
  `use_cases.md` analyst workflow; verb-naming reconciled across docs and the
  out-of-scope/definition-of-done updated (SQL reads in v1; writes/routing v2+).
- **Brand assets** (`docs/logos/`): the niva mark (`logo.svg` / `logo.png`) and
  wordmark (`logo_text.svg` / `logo_text.png`); earlier logo explorations
  archived under `docs/logos/OLD/`.
- **QGIS plugin stub** (`plugin/`): a minimal plugin that previews the niva logo
  on the toolbar and Plugins menu (no geoprocessing yet), Qt5/Qt6-compatible,
  with a `make package` build for the install zip.
- **README** describing the project goals and current (early, exploratory)
  status.
- This changelog.

[Unreleased]: https://github.com/johnzastrow/niva/commits/main
