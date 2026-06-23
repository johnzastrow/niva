# TODO

Parked work. See [`docs/planning/04-roadmap.md`](docs/planning/04-roadmap.md),
[`docs/planning/15-postgis-and-project-design.md`](docs/planning/15-postgis-and-project-design.md),
and [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md) for context.

## Graphical figure generation — render figures at the end of a flow (new scope)

A final-step verb that renders a **map figure** (PNG / PDF / SVG) from a flow's outputs using a
QGIS **print-layout template** (`.qpt`), so a `.niva` run can produce report-ready deliverables
directly. Fixture / default template committed at
[`examples/layout_template.qpt`](examples/layout_template.qpt) (`StandardLayout`, 300 dpi, a map
frame + world-file map).

- [ ] **`figure` verb (working name)** — terminal / pass-through. Sketch:
  `figure to=<out.png|pdf|svg> [template=<.qpt>] [dpi=300] [title=<text>] [layers=current|all]`.
  Load the `.qpt` into a standalone `QgsPrintLayout` (off the main thread, per `docs/planning/15`
  §3 and `16`), bind the flow's current layer(s) — and earlier `save` outputs — into the layout's
  map item(s), set the map extent to the data (or a bookmark), stamp an optional title, and export
  via `QgsLayoutExporter` (`exportToImage` / `exportToPdf` / `exportToSvg`). Default template =
  `examples/layout_template.qpt`, else resolve by name like project templates
  (`$NIVA_TEMPLATES` / `~/.niva/templates`).
- [ ] **Atlas / multi-map** — one figure per feature of a coverage layer (`QgsLayoutAtlas`). Later.
- [ ] Add a final-step `figure …` smoke to the validation (and portable) suites once it ships.
- Two-tier tests (MockBackend records the call; live-QGIS asserts a non-empty image is written).
- Note: distinct from the *print-layouts-in-project-files* item below — that bakes a layout into a
  `.qgs`; **this renders an image**. The `.qpt` is the live input here.

## `show` — remote services (follow-up)

- [ ] **More remote sources for `show`.** Shipped: **WFS/WMS** (v0.30.0), **ArcGIS REST + XYZ**
  (v0.31.0) — all in `niva/remote.py`. Still open: **vector-tile** endpoints, **saved OWS
  connections** referenced by name, **cloud rasters** via GDAL `/vsicurl` / `/vsis3`, and
  **authenticated** services (credentials). Reuse the same entry shape
  (`{name, kind, type, format, ref}`), `format_show`, and the DOCTYPE-refusing safe-XML path.
  See [`docs/planning/17-show-verb-design.md`](docs/planning/17-show-verb-design.md) §"Out of scope".

## niva command history — `bash_history`-style record of executed flows (new scope)

A rolling record of the niva **commands/flows the user runs**, analogous to `~/.bash_history` —
distinct from, and *in addition to*, the per-run [journal](niva/journal.py) (`<base>.jsonl` /
`<base>.log`, which records each *operation* of a single run at a caller-supplied path). The history
is one persistent, append-only file across sessions, keyed to the user (not to a run), recording the
flow text that was invoked so it can be recalled, re-run, or audited later.

- [ ] **History file** — append the executed flow (and a UTC timestamp) to a single rolling file,
  default `~/.niva/history` (overridable via env, e.g. `NIVA_HISTFILE`; honour a `NIVA_HISTSIZE`
  cap / trim like the shell). Append on every CLI invocation and every `niva.flow(...)` /
  `run_file(...)` call. Record the **flow text only** — never resolved parameter dicts, paths from
  the journal, or credentials (same redaction discipline as the journal, `journal.py` line ~16).
- [ ] **Opt-out** — a `--no-history` flag and an env toggle (e.g. `NIVA_HISTFILE=` empty or
  `NIVA_NO_HISTORY=1`) to disable recording; document the privacy implication (flows may name file
  paths / `@conn` names).
- [ ] **Recall surface (later)** — a way to list / search recent flows (a `history` verb or a CLI
  flag), and ideally re-run by index. Keep minimal first; the file itself is the MVP.
- Two-tier tests: MockBackend asserts the history line is appended with the right flow text and no
  secrets; a CLI test asserts the file is created/appended and that `--no-history` suppresses it.
- Open questions: per-session vs. global file; how a multi-stage piped flow is recorded (one line
  for the whole flow vs. per stage — likely one line for the whole flow, matching shell history);
  interaction with the plugin (does a dock run also append?).

## Project & layer-file operations (new scope)

All use a standalone `QgsProject()` / `QgsMapLayer` off the main thread (per
`docs/planning/15` §3 and `16`), with two-tier tests (MockBackend + live-QGIS).

**Lower priority — assess; minimal forms are low value**
- [ ] **Map themes** — visibility presets (`project.mapThemeCollection()`). A single
  all-visible theme is near-useless; only worth it with per-layer visibility control (a
  richer grammar) or baked into **template projects**.
- [ ] **Legend tweaks** — layer ordering / group nodes in the tree
  (`project.layerTreeRoot()`). Likewise marginal alone; better via templates.
- [ ] **Print layouts (`.qpt`) in project files** — *superseded by template projects* (a template
  carries the layout). Keep only if direct `.qpt` export/import is later wanted. (For *rendering an
  image* from a `.qpt`, see "Graphical figure generation" above — a separate, active scope.)

## Done
- [x] **Environment-inspection verb (`info`)** (v0.28.0) — `info [to=<report.md>]` inspects the
  local QGIS environment: registered `@conn` database connection names, Processing providers +
  reachable algorithm count, versions (QGIS/GDAL/PROJ/GEOS/Python), niva build + import path, the
  verb list, and the env vars niva honours (secrets masked). Report logic factored into
  `niva/environment.py`, shared by the verb and the plugin's Setup-tab Environment report
  (`plugin/environment.py` now re-exports it). Two-tier tests (MockBackend records the call;
  live-QGIS checks the real report). Distinct from `project info <src.qgs>`.
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
