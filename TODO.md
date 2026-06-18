# TODO

Parked work. See [`docs/planning/04-roadmap.md`](docs/planning/04-roadmap.md),
[`docs/planning/15-postgis-and-project-design.md`](docs/planning/15-postgis-and-project-design.md),
and [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md) for context.

- [ ] **Real end-to-end run of the analyst plan (now including Task 5).** Run
  `examples/analyst_plan.niva` against the real data headless (the python3.14 + QGIS
  recipe), through the new Task 5 `project` lines, and confirm: outputs valid, `/tmp`
  flat (scratch fix holds), the repointed `.qgs` projects open and resolve to the clips.
  This is a verification/ops task, not a feature.

## Project & layer-file operations (new scope)

All use a standalone `QgsProject()` / `QgsMapLayer` off the main thread (per
`docs/planning/15` §3 and `16`), with two-tier tests (MockBackend + live-QGIS).

**Next up**
- [ ] **Template projects** — `project from-template=<name|path> to=<out> data=<dir|glob>`.
  Curate a few stock `.qgz` templates that already contain **print layouts + styled layer
  slots**; niva instantiates one against the user's data (copy the template, load/repoint
  the layers, optionally apply styles). This is the *practical* path to print layouts +
  consistent styling — far better than editing layouts programmatically — and subsumes the
  print-layout items below. Design: a templates dir convention, name→path resolution, and
  layer-slot matching (by name, like `project repoint`). **(Agreed: do after the current
  cartographic set.)**

**Lower priority — assess; minimal forms are low value**
- [ ] **Map themes** — visibility presets (`project.mapThemeCollection()`). A single
  all-visible theme is near-useless; only worth it with per-layer visibility control (a
  richer grammar) or baked into **template projects**.
- [ ] **Legend tweaks** — layer ordering / group nodes in the tree
  (`project.layerTreeRoot()`). Likewise marginal alone; better via templates.
- [ ] **Print layouts (`.qpt`)** — *superseded by template projects* (a template carries the
  layout). Keep only if direct `.qpt` export/import is later wanted.

## Done
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

## Roadmap-noted follow-ups (not yet scoped)
- `project` / `style` `apply` to a **database-backed** layer (DB style table).
- `.qmd` metadata `apply` persistence into a container (currently sidecar only).
