# TODO

Parked work. See [`docs/planning/04-roadmap.md`](docs/planning/04-roadmap.md),
[`docs/planning/15-postgis-and-project-design.md`](docs/planning/15-postgis-and-project-design.md),
and [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md) for context.

## Environment-inspection verb (`info`)

- [ ] **An `info` verb that inspects the local QGIS environment and reports details a CLI user needs**
  before writing a flow (when working outside QGIS, where the Browser/connection UI isn't in
  front of you). The single most useful thing: the **registered database connection names** —
  the valid `@conn` references for PostGIS and SpatiaLite — since a flow references them by name
  but a user can't guess them. Also worth surfacing:
  - Processing **providers** present and the reachable **algorithm count** — including whether
    optional providers (GRASS, PDAL) are installed, so `run grass:…`/`run pdal:…` are known to work.
  - **Versions** — QGIS, GDAL, PROJ, GEOS, Python — and the QGIS prefix path + active profile.
  - The **environment variables niva honours** and their current values: `NIVA_TMPDIR` (+ the
    resolved scratch dir), `NIVA_TEMPLATES`, `NIVA_NTFY_*`, `NIVA_SMTP_*` (mask secrets).
  - niva's own version + import path (bundled-in-plugin vs pip), and the verb/alias list.

  This is the **CLI counterpart of the plugin's Setup-tab "Environment report"**
  (`plugin/environment.py::report_markdown`) — factor that logic into the niva package so the
  verb and the plugin share one source. Terminal verb (writes/prints a Markdown report); e.g.
  `info` or `info to=<report.md>`. (Distinct from `project info <src.qgs>`, which inventories a
  *project file* — this `info` inventories the *QGIS environment*; the bare `info` with no args
  is unambiguous.) Fold in the planning doc's aspirational `doctor` command
  (`docs/planning/11-cli-and-api-reference.md`). Two-tier tests (MockBackend records the call;
  live-QGIS checks the real report contents).

## Project & layer-file operations (new scope)

All use a standalone `QgsProject()` / `QgsMapLayer` off the main thread (per
`docs/planning/15` §3 and `16`), with two-tier tests (MockBackend + live-QGIS).

**Lower priority — assess; minimal forms are low value**
- [ ] **Map themes** — visibility presets (`project.mapThemeCollection()`). A single
  all-visible theme is near-useless; only worth it with per-layer visibility control (a
  richer grammar) or baked into **template projects**.
- [ ] **Legend tweaks** — layer ordering / group nodes in the tree
  (`project.layerTreeRoot()`). Likewise marginal alone; better via templates.
- [ ] **Print layouts (`.qpt`)** — *superseded by template projects* (a template carries the
  layout). Keep only if direct `.qpt` export/import is later wanted.

## Done
- [x] **Real end-to-end run of the analyst plan** (v0.25.0) — `examples/analyst_plan.niva`
  ran headless on the real data through Task 5: outputs valid, `/tmp` flat (scratch fix held),
  the repointed `.qgs` projects open and resolve to the clips.
- [x] **Test-hardening pass** (v0.18.3) — live-QGIS + PostGIS tier now gates CI on the
  `qgis/qgis` image with a Postgres service; real-Postgres test tier; found & fixed the
  PostGIS-append PK bug.
- [x] **Raster-layer repointing in `project`** (v0.19.0) — `project … rasters=<dir>`.
- [x] **`style` verb** (v0.20.0) — `style apply|save <.qml|.qmd>`, persisting into a
  GeoPackage `layer_styles` table or a sidecar.
- [x] **`project new from=<dir> to=<out.qgs>`** (v0.21.0) — create a project from outputs.
- [x] **`style save <.sld|.qlr>`** (v0.22.0) — SLD + QGIS Layer Definition export.
- [x] **`project info <src.qgs>`** (v0.23.0) — inventory a project to Markdown.
- [x] **`project` copy/convert + `paths=`** (v0.24.0) — `repoint=` optional, `.qgs`↔`.qgz`,
  relative/absolute path rewrite.
- [x] **`project … bookmark=<name>`** (v0.25.0) — union-extent or centred (`at=`+`scale=`/`width=`).
- [x] **Template projects** (v0.26.0) — `project from-template=<name|path> to=<out> data=<dir|glob>`;
  copies a stock `.qgz` (layouts + styled slots) and repoints each slot (vector or raster) to
  the same-named dataset under `data=`, style + layout riding along. Templates resolve by name
  (`$NIVA_TEMPLATES`/`~/.niva/templates`) or path; unmatched slots follow `missing=` (default
  `keep`). Supersedes the print-layout item below.
- [x] **Existing projects as templates + `project to-template=`** (v0.27.0) — any existing
  `.qgs`/`.qgz` is a template (layouts verified to survive instantiation); slots match by the
  layer's **display name** (fallback datasource name). `project to-template=<name|path>
  from=<src> [paths=]` registers an existing project into the library so `from-template=<name>`
  finds it. Ships a bundled `example` template (`from-template=example`) + the authoring guide
  `docs/guide/templates.md` (element reference: what a template carries).

## Roadmap-noted follow-ups (not yet scoped)
- `project` / `style` `apply` to a **database-backed** layer (DB style table).
- `.qmd` metadata `apply` persistence into a container (currently sidecar only).
