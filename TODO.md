# TODO

Parked work. See [`docs/planning/04-roadmap.md`](docs/planning/04-roadmap.md),
[`docs/planning/15-postgis-and-project-design.md`](docs/planning/15-postgis-and-project-design.md),
and [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md) for context.

- [ ] **Real end-to-end run of the analyst plan (now including Task 5).** Run
  `examples/analyst_plan.niva` against the real data headless (the python3.14 + QGIS
  recipe), through the new Task 5 `project` lines, and confirm: outputs valid, `/tmp`
  flat (scratch fix holds), the repointed `.qgs` projects open and resolve to the clips.
  This is a verification/ops task, not a feature.

## Project & layer-file operations (new scope, after the e2e run)

The `project` verb (repoint) and `style` verb are the start; these extend the
project/layer-file surface so a niva flow can *produce* the cartographic deliverables of
"compile a region," not just the data. All use a standalone `QgsProject()` /
`QgsMapLayer` off the main thread (per `docs/planning/15` §3 and `16`), and each needs the
two-tier tests (MockBackend + live-QGIS).

**High value**
- [ ] **Create a shell project from outputs** — `project new from=<dir|glob> to=<out.qgs>
  [crs=… title=…]`. The missing half of the project story: `project` can only repoint an
  *existing* `.qgs`; this *generates* one pointing at a directory/glob of output layers
  (standalone `QgsProject()` → `addMapLayer` each → `setCrs`/`setTitle` → `write`). Closes
  the clip → save → project loop without needing a source project.
- [ ] **QLR export (Layer Definition Files)** — emit a portable `.qlr` (datasource + style
  + metadata, one or more layers) so analysts can drag-drop a styled layer with no project.
  `QgsLayerDefinition.exportLayerDefinitionLayers(...)`. Slots in as `style save x.qlr`
  (extension-dispatched) or a small `qlr` action.
- [ ] **SLD style export** — `style save x.sld` (OGC, for GeoServer/interop). Cheap:
  `QgsVectorLayer.saveSldStyle(path)`; just another extension on the `style` verb.
- [ ] **`project info <src.qgs>`** — inventory a project's layers / datasources / CRS to a
  Markdown report (a `catalog` for projects). Read the project, iterate `mapLayers()`.

**Medium value**
- [ ] **Path rewrite + repackage** — rewrite a project's datasource paths relative↔absolute
  (`QgsProject.setFilePathStorage` + `write`), and convert `.qgs` ↔ `.qgz` (read then write
  by extension). Portability fixes.

**Cartography / GUI-side (stub out — assess feasibility + fit; lower priority, may be partial)**
- [ ] **Print layouts (`.qpt`)** — export/import a print-layout template; generate a layout
  from a region (`QgsPrintLayout`, `project.layoutManager()`, `saveAsTemplate` /
  `loadFromTemplate`). Stub: scope what's declarative vs GUI-only.
- [ ] **Adjust print layouts** — tweak an existing layout: title text, the map item's
  extent/scale, swap its layers, page size. Operates on a project's layout(s).
- [ ] **Bookmarks** — add/list spatial bookmarks in a project (`project.bookmarkManager()`,
  `QgsBookmark`); e.g. a bookmark for the study-area bbox.
- [ ] **Map themes** — create/apply visibility presets ("map themes":
  `project.mapThemeCollection()`), e.g. a "basemap only" vs "full" theme over the clips.
- [ ] **Legend tweaks** — layer ordering, group nodes, and legend visibility/labels in the
  project tree (`project.layerTreeRoot()` — `QgsLayerTree`/`QgsLayerTreeGroup`).

## Done
- [x] **Test-hardening pass** (v0.18.3) — live-QGIS + PostGIS tier now gates CI on the
  `qgis/qgis` image with a Postgres service; real-Postgres test tier; found & fixed the
  PostGIS-append PK bug.
- [x] **Raster-layer repointing in `project`** (v0.19.0) — `project … rasters=<dir>`.
- [x] **`style` verb** (v0.20.0) — `style apply|save <.qml|.qmd>`, persisting into a
  GeoPackage `layer_styles` table or a sidecar.

## Roadmap-noted follow-ups (not yet scoped)
- `project` / `style` `apply` to a **database-backed** layer (DB style table).
- `.qmd` metadata `apply` persistence into a container (currently sidecar only).
