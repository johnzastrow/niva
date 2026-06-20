# niva Reference

The complete reference for **niva v0.30.0** — every verb, alias, option, type, environment
variable, CLI command, and Python entry point. For a task-oriented tour see the
[Cookbook](cookbook.md); for setup and day-to-day use see the [User Guide](user-guide.md).

### Algorithm coverage at a glance

niva gives **45 alias verbs** friendly names; **every** QGIS Processing algorithm — **769**
in QGIS 4.0.3 — is reachable through the [`run`](#6-the-run-escape-hatch--describe) escape
hatch. The complete, per-algorithm appendix (parameters, defaults, enum options, descriptions,
and which verb aliases each) is in [`docs/algorithms/`](../algorithms/README.md).

| Provider | Algorithms | niva alias verbs |
|---|---|---|
| `native:` | 339 | 40 |
| `gdal:` | 59 | 5 |
| `grass:` | 307 | 0 |
| `qgis:` | 39 | 0 |
| `pdal:` | 24 | 0 |
| `3d:` | 1 | 0 |
| **Total** | **769** | **45** |

- [1. The flow model](#1-the-flow-model)
- [2. Syntax](#2-syntax)
- [3. Value types & units](#3-value-types--units)
- [4. Built-in verbs](#4-built-in-verbs)
- [5. Alias verbs (the registry)](#5-alias-verbs-the-registry)
- [6. The `run` escape hatch & `describe`](#6-the-run-escape-hatch--describe)
- [7. Database connections (`@conn`)](#7-database-connections-conn)
- [8. Environment variables](#8-environment-variables)
- [9. Command-line interface](#9-command-line-interface)
- [10. Python API](#10-python-api)

---

## 1. The flow model

A niva program is one or more **flows**, one per line. A flow is a chain of **stages**
separated by the pipe `|`. Each stage is a **verb** with optional arguments and options. A
layer handle flows left-to-right: a stage receives the upstream layer, transforms it, and
passes the result on.

```
load roads.gpkg | reproject EPSG:2262 | buffer 100m dissolve | save roads_buf.gpkg
```

Verbs fall into three behavioural classes:

| Class | Meaning | Examples |
|---|---|---|
| **Producing** | returns a new layer to pipe onward | `load`, `run`, `split`, `sql` (SELECT), and every alias verb |
| **Pass-through** | returns the upstream layer unchanged, so it chains | `save`, `assess`, `metadata`, `style`, `notify`, `email` |
| **Terminal** | returns nothing; a following stage is an error | `catalog`, `show`, `info`, `project`, `sql` (write) |

A flow normally begins with `load` (or `run`/`sql`, which produce a layer), or with `each`
to run the rest of the flow once per dataset in a directory/glob/container.

---

## 2. Syntax

### Stages, args, options, flags

A stage is `verb [positional-args…] [key=value options…] [flags…]`, whitespace-separated.

- **Positional arguments** are bound in order (e.g. `buffer 100m` → the distance).
- **Options** are `key=value` (e.g. `segments=12`, `cap=flat`).
- **Flags** are bare words that switch a boolean on (e.g. `dissolve`, `percent`).

```
buffer 100m dissolve cap=flat segments=12
#      ^arg  ^flag    ^option  ^option
```

### Quoting, comments, line joins

- **Quotes** keep a value with spaces or special characters atomic:
  `filter "landuse = 'R'"`, `load "my data.gpkg|layername=roads"`. Single or double quotes;
  the outer pair is stripped.
- `#` starts a **comment** to end of line. A line that is only a comment is ignored.
- A trailing `\` **joins** the next line (for long flows).
- Blank lines are ignored. Each non-blank line is its own flow.

### Paths

A path argument has a leading `~` expanded to your home directory (`clip "~/aoi.gpkg"`).
A layer inside a multi-layer container is addressed with the OGR suffix
`|layername=<name>`: `load "data.gpkg|layername=roads"`.

### Per-item placeholder `{name}`

Inside an `each` batch, `{name}` in a `save` path or `as` clause is replaced with the
current item's (sanitised) name — `save "out/{name}.tif"`. Outside a batch it is an error.

### Option keys

Option keys are identifier-like and may contain internal hyphens (`from-template=`,
`to-template=`). Only tokens containing `=` are treated as options, so flags such as
`-deep` are never mistaken for options.

---

## 3. Value types & units

Argument and option values are coerced by **type** (the binder in `niva/registry/binder.py`):

| Type | Accepts | Notes |
|---|---|---|
| `distance` | number + optional unit, e.g. `100`, `100m`, `1km`, `0.5deg` | unit resolved against the layer CRS at run time; **no unit = the layer's own CRS units** |
| `number` | decimal, e.g. `2`, `0.25`, `-9999` | |
| `int` | integer, e.g. `12` | |
| `enum` | one word from a fixed vocab, e.g. `cap=flat` | word → QGIS code; invalid word lists the valid set |
| `enumlist` | comma-separated enum words, e.g. `stats=mean,min,max` | |
| `fields` / `list` | comma-separated list, e.g. `fields=pop,income` | |
| `layer` / `raster` | a dataset path or `@conn.table` | `~` expanded; `@conn` passes through |
| `crs` | a CRS string, e.g. `EPSG:2262` | verbatim |
| `field` | an attribute field name | verbatim |
| `string` | any text | verbatim |
| `expression` | a QGIS expression, e.g. `"area > 2000"` | verbatim; quote it |

**Supported distance units:** `m`, `km`, `cm`, `mm`, `ft`, `yd`, `mi`, `nmi`, `deg`. An
unknown unit is a clear error. A distance with no unit is interpreted in the layer's CRS
units (so on a geographic CRS, `buffer 100` means 100 *degrees* — usually you want `100m`).

**Enum-by-word:** options that map to a QGIS dropdown take a readable word, not a number —
`simplify 5m method=area`, not `method=2`. Each alias below lists its vocab.

---

## 4. Built-in verbs

Built-in verbs are handled directly by the engine (not the alias registry).

### `load` — read a dataset *(producing)*

```
load <path-or-uri>
load "<container.gpkg>|layername=<layer>"
load @conn[.schema].table
```

Exactly one argument; no options. `~` is expanded. A bare multi-layer container
(`load data.gpkg`) errors and lists its layers — name one with `|layername=`. The `@`
form reads a table from a **saved database connection** (§7); a bare `@conn` with no table
errors (use `sql` to query it), and an `@` pointing at a file extension is rejected (use the
path form).

```
load "parcels.gpkg|layername=residential"
load @pg.public.roads
```

### `save` — write the current layer *(pass-through)*

```
save <path>
save <path> as <layer>                     # named layer inside a .gpkg/.sqlite/.db
save @conn[.schema].table [mode=create|replace|append]
```

- **File form:** extension chooses the format; parent directories are created. No options.
  `as <layer>` writes a named layer into a container (GeoPackage/SQLite only); writing into
  an existing container with a layer name **appends**.
- **Database form:** `mode` is the only option — `create` (default; **fails if the table
  exists** — never a silent overwrite), `replace` (drop + recreate), or `append` (insert,
  fields matched by name, CRS-transformed as needed). Rasters cannot be saved to a database.
- `save` chains: `… | save out.gpkg | style apply s.qml | notify "done"`.
- **In an `each` batch:** a file container gets **one layer per item** (named after the
  source); a `{name}` path gives **one file per item**; `save @conn` writes **one table per
  item** (a trailing qualifier is the schema, e.g. `save @pg.niagara`).

```
load roads.gpkg | clip aoi.gpkg | save out/roads_clip.gpkg
load roads.gpkg | save data.gpkg as roads
load roads.gpkg | save @pg.public.roads_clip mode=replace
```

### `sql` — query or mutate a database connection *(producing OR terminal)*

```
sql @conn "<statement>"
```

Exactly two arguments — a **bare** connection ref and a quoted statement — and no options.
The leading keyword routes it:

- **`SELECT` / `WITH` / `VALUES` / `TABLE` / `EXPLAIN` / `SHOW`** → a **query layer** you can
  pipe onward (producing). `CREATE TABLE … AS SELECT …` reads as a **write** (leading
  `CREATE`); `WITH … SELECT …` reads as a query (leading `WITH`).
- **anything else** (`CREATE`/`INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/…) → runs
  server-side and returns nothing (terminal).

Works against any saved connection — **SpatiaLite** or **PostGIS** — using that engine's
spatial SQL (`ST_Buffer`, `ST_Area`, spatial joins, …). Only the connection *name* leaves
the flow; credentials never appear in flow text, errors, or logs (§7).

```
sql @cats_pg "SELECT id, ST_Buffer(geom, 100) AS geom FROM homes WHERE has_cat" | save targets.gpkg
sql @pg "CREATE TABLE roads_buf AS SELECT id, ST_Buffer(geom,100) AS geom FROM roads"
```

### `run` — call any QGIS algorithm directly *(producing)*

```
run <algorithm-id> [KEY=value …]
```

The escape hatch: one positional (the algorithm id, e.g. `native:slope`), then QGIS
parameters as `KEY=value`. Values are coerced (`true`/`false` → bool, numbers → int/float,
else string); `~` is expanded; a `;`-joined value becomes a list; a path with `*`/`?`/`[` is
globbed. `INPUT` (from the pipe) and `OUTPUT` (a temp file) are supplied automatically when
omitted. See §6.

```
load dem.tif | run native:slope Z_FACTOR=2 | save slope.tif
run gdal:merge INPUT="a.tif;b.tif;c.tif" DATA_TYPE=5 | save mosaic.tif
```

### `split` — keep one geometry type *(producing)*

```
split <point|line|polygon>
```

Extract a single geometry type from a mixed layer (`native:filterbygeometry`). Accepts
singular or plural (`points`, `lines`, `polygons`). Pipe again to extract another type.
Multipart features are preserved; `GeometryCollection` features match none of the sinks.

```
load mixed.gpkg | split line | save lines.gpkg
```

### `metadata` — stamp descriptive metadata *(pass-through)*

```
metadata set <field=value> [field=value …]
```

Fields: `title`, `abstract`, `keywords` (comma-separated), `identifier`, `license`. The
metadata persists on the next `save`.

```
load parcels.gpkg | metadata set title="Residential parcels" keywords="parcels,zoning" | save parcels.gpkg
```

### `assess` — data-quality report *(pass-through)*

```
assess [deep] to <report.md>
```

Profiles the current layer to a Markdown report: type, CRS, extent, fields, metadata, and —
with `deep` — invalid/empty/duplicate-geometry counts and per-field null counts. Sits
mid-pipe (returns the layer unchanged). `deep` may also be written `-deep`.

```
load raw_parcels.gpkg | assess deep to docs/raw_quality.md
```

### `catalog` — inventory a directory *(terminal)*

```
catalog <dir> [to=<out.md>]
```

Recursively profiles every geospatial dataset under `<dir>` (multi-layer containers expand
per layer) to a Markdown inventory — type, CRS, geometry/bands, feature count, extent —
listing unreadable files separately. Default output is `<dir>/catalog.md`.

```
catalog "data/" to=reports/inventory.md
```

### `show` — list available data at a location *(terminal)*

```
show <path|@conn[.schema[.table]]|WFS/WMS-url> [deep] [to=<out.md>]
```

Lists the loadable layers/tables at **one** location and what each is — a quick *"what can I
load here, and what's its name?"* glance, the lighter cousin of `catalog` (which deep-profiles
CRS/extent/fields/counts). Per entry: the **name**, **kind** (vector/raster/table), **type**
(geometry like `MultiPolygon`, or a raster's `N band · Float32`), **format** (the file driver
`GPKG` / `GTiff` / `SQLite` / …, or the DB provider), and a copy-pasteable **source** you can
hand straight to `load` (or `ogrinfo` for files). No feature counts — that keeps it instant
even on big databases.

`<location>` may be:

- a **file** — `show roads.shp`, `show dem.tif`, or a multi-layer container `show data.gpkg`
  (one row per layer);
- a **directory** — `show data/` lists the immediate children; add the **`deep`** flag
  (`show data/ deep`) to recurse the whole tree. **Any QGIS-readable format is picked up** —
  not just a fixed extension list — so SpatiaLite (`.sqlite`/`.db`), FileGDB (`.gdb`), and any
  other GDAL/OGR driver appear; dataset sidecars (a shapefile's `.dbf`/`.shx`/…) and obviously
  non-geospatial files are skipped. Directory-based datasets like `.gdb` are listed as a
  container, not descended into;
- a **database connection** — `show @conn` (every table), `show @conn.schema` (one schema),
  `show @conn.schema.table` (one table). Connection names containing dots (e.g.
  `@actual_spatialite.sqlite`) resolve correctly. Only the connection **name** is used —
  credentials stay in QGIS;
- a **remote OWS service** — a **WFS** endpoint lists its feature types, a **WMS** endpoint its
  layers. Pass the URL (the service is read from a `service=WFS`/`service=WMS` query parameter,
  the path, or a `WFS:`/`WMS:` prefix; if it can't be told, `show` asks you to specify it).
  Standard library HTTP only — public services, no credentials sent; the response is fetched
  with a timeout and size cap, and parsed with DOCTYPE/entity expansion refused (no XXE).

```
show "data/basemap.gpkg"          # layers in a GeoPackage
show data/                         # everything directly under data/
show data/ deep                    # recurse the whole tree
show @gisdb3                       # all PostGIS tables
show @gisdb3.public to=tables.md   # one schema, written to a file
show "https://demo.mapserver.org/cgi-bin/wfs?service=WFS"   # WFS feature types
show "https://ows.terrestris.de/osm/service?service=WMS"    # WMS layers
```

`show` is terminal and can't be piped (neither it nor `catalog` produce or consume a layer);
for a deep per-dataset report (CRS, extent, fields, feature counts) run `catalog` on the same
location.

### `info` — inspect the local QGIS environment *(terminal)*

```
info [to=<report.md>]
```

Reports what a CLI user needs to know before writing a flow, especially when working
**outside** QGIS where the Browser and connection dialogs aren't in front of you. Most
useful: the **registered database connection names** — the valid `@conn` references for
PostGIS and SpatiaLite — since a flow names them but you can't guess them. Because connections
are **per QGIS profile**, `info` also lists **every profile and the connections in each**, and
marks the active one (niva reads the active profile by default; `NIVA_QGIS_PROFILE=<name>`
targets another). Also surfaces the Processing **providers** and reachable **algorithm count**
(so you know `run grass:…` / `run pdal:…` will work), the **versions** (QGIS, Qt/PyQt, GDAL,
PROJ, GEOS, SpatiaLite/SQLite, Python), niva's own build + import path, the verb list, and the
**environment variables** niva honours (secrets masked — only *set* / *unset* is shown). With
`to=`, writes the Markdown to a file; otherwise prints it to stdout. This is the CLI
counterpart of the plugin's Setup-tab **Environment report**.

```
info                       # print the report
info to=env-report.md      # save it
```

(Not to be confused with `project info <src.qgs>`, which inventories a *project file*; bare
`info` inventories the *QGIS environment*.)

### `project` — manipulate QGIS project files *(terminal)*

Five forms; all use a standalone `QgsProject` (safe off the GUI thread) and all are terminal.

**Repoint / copy / convert** — copy a project, optionally repointing layer datasources:
```
project <src.qgs|qgz> to=<out.qgs|qgz> [repoint=<target>]
        [missing=fail|keep|drop] [rasters=<dir>] [paths=relative|absolute]
        [bookmark=<name> [at="x,y"] [scale=<N>] [width=<W>]]
```
`repoint=` is a `.gpkg` path **or** an `@conn[.schema]` connection; vector layers match by
name, subset filters preserved. `missing=` (default **`fail`**) handles a layer absent from
the target. `rasters=<dir>` repoints raster layers by basename. `paths=` rewrites datasource
path storage. `bookmark=<name>` adds a spatial bookmark — the layers' **union** extent, or a
centred box via `at="x,y"` with `width=` (exact) or `scale=` (approx). Omit `repoint=` to
just copy/convert (`.qgs`↔`.qgz` by extension).

**`project new`** — build a fresh project from a folder of outputs:
```
project new from=<dir|glob> to=<out.qgs|qgz> [crs=<crs>] [title=<text>]
```

**`project info`** — inventory a project to Markdown:
```
project info <src.qgs|qgz> [to=<out.md>]
```

**`project from-template=`** — instantiate a template against your data (see
[Template projects](templates.md)):
```
project from-template=<name|path> to=<out.qgs|qgz> data=<dir|glob> [missing=keep|fail|drop]
```
The template is any existing project; each layer **slot** is repointed to the same-(display)-
named dataset under `data=`, symbology and print layouts riding along. Resolves a bare name
from `$NIVA_TEMPLATES` → `~/.niva/templates` → bundled (`example`). `missing=` default `keep`.

**`project to-template=`** — register an existing project as a reusable template:
```
project to-template=<name|path> from=<src.qgs|qgz> [paths=relative|absolute]
```

```
project "basemap.qgs" to="out/basemap.qgs" repoint="out/basemap_clip.gpkg" missing=keep
project from-template=example to="region_atlas.qgz" data="data/clips/"
```

### `style` — apply or export a layer style *(pass-through)*

```
style apply <file.qml|.qmd>
style save  <file.qml|.qmd|.sld|.qlr>
```

`apply` reads a QGIS sidecar and **persists** it (a GeoPackage layer style goes into the
container's `layer_styles` table; a single-file layer gets a same-basename sidecar). `save`
exports the current layer's style/metadata — `.qml` (symbology), `.qmd` (metadata), and
export-only `.sld` (OGC) and `.qlr` (portable layer definition). Chains after `save`.

```
load roads.gpkg | clip aoi.gpkg | save roads_clip.gpkg | style apply house.qml
```

### `notify` — push a message via ntfy *(pass-through)*

```
notify "<message>" [to=<topic>] [title=<t>] [priority=<p>] [server=<url>] [tags=<tags>]
```

Posts to an [ntfy](https://ntfy.sh) topic. `to=` falls back to `NIVA_NTFY_TOPIC`; `server=`
to `NIVA_NTFY_SERVER` (default `https://ntfy.sh`); a bearer token comes only from
`NIVA_NTFY_TOKEN`. The message interpolates `{elapsed}`, `{last}`, `{now}`, `{started}`,
`{ops}`, `{errors}`. See also the auto-alert env vars in §8.

```
… | save out.gpkg | notify "done in {elapsed}, {errors} errors" to=geo-jobs priority=high
```

### `email` — send via SMTP *(pass-through)*

```
email to=<address> [subject=<s>] [body=<b>] [attach=<file>]
```

SMTP host/credentials come only from the environment (`NIVA_SMTP_*`, §8); a `@gmail.com`
sender auto-uses `smtp.gmail.com:587` (needs a Gmail App Password). TLS is mandatory.

```
load r.gpkg | assess to q.md | email to=ops@example.com subject="Daily run" attach=q.md
```

### `each` — batch over many datasets *(flow prefix)*

```
each "<dir>"  | <stages…> | save <target>
each "<glob>" | <stages…> | save out.gpkg
each <file.gpkg> | <stages…> | save out.gpkg
```

Must be the **first** stage. Resolves a directory (recursed), a glob, or a multi-layer
container (expanded per layer) to a list of datasets, then runs the rest of the flow once
per dataset. A failing item is **skipped** (logged, counted, warned) so one bad file can't
abort the batch; a usage error (bad option/target) still stops everything. See `save` for
per-item output behaviour.

```
each "in/*.shp" | reproject EPSG:6346 | save out.gpkg
```

### `call` — run another `.niva` file inline *(statement)*

```
call <other.niva>
```

A top-level statement (not a piped stage): runs another flow file's flows in place, resolved
relative to the calling file, with cycle detection — for composing reusable flow libraries.

---

## 5. Alias verbs (the registry)

Each alias maps one verb to one QGIS algorithm, hiding its parameter names behind readable
args/options/flags. The primary input is the piped layer; the output is the temp/saved
destination. Source of truth: `niva/registry/definitions.py`. Run `niva describe <verb>` for
the live signature.

**Reading the tables:** *Args* are positional (in order); a `[name]` is optional. *Options*
are `key=` with the default in parentheses. *Flags* are bare switches (off by default).
Enum options list their words.

### Vector — core overlay & selection

| Verb | Algorithm | Args | Options | Flags |
|---|---|---|---|---|
| `clip` | `native:clip` | `overlay` (layer) | — | — |
| `intersect` | `native:intersection` | `overlay` (layer) | — | — |
| `difference` | `native:difference` | `overlay` (layer) | — | — |
| `union` | `native:union` | `[overlay]` (layer) | — | — |
| `symdifference` | `native:symmetricaldifference` | `overlay` (layer) | — | — |
| `dissolve` | `native:dissolve` | `[field]` | — | `separate` |
| `filter` | `native:extractbyexpression` | `expression` | — | — |
| `selectloc` | `native:extractbylocation` | `against` (layer) | `predicate=` (intersect) ⟨intersect, contain, disjoint, equal, touch, overlap, within, cross⟩ — comma-list | — |
| `spatialjoin` | `native:joinattributesbylocation` | — | `with=`(req, layer) · `predicate=`(intersect) ⟨intersect, contain, equal, touch, overlap, within, cross⟩ · `method=`(one-to-many) ⟨one-to-many, first, largest⟩ · `fields=` · `prefix=` | `discard` |
| `join` | `native:joinattributestable` | — | `with=`(req) · `field=`(req) · `field2=`(req) · `fields=` · `prefix=` · `method=`(one-to-one) ⟨one-to-many, one-to-one⟩ · `unmatched=` | `discard` |
| `sample` | `native:randomextract` | `number` (int) | `method=`(count) ⟨count, percent⟩ | — |

### Vector — buffering & geometry

| Verb | Algorithm | Args | Options | Flags |
|---|---|---|---|---|
| `buffer` | `native:buffer` | `distance` | `segments=`(5) · `cap=`(round) ⟨round, flat, square⟩ · `join=`(round) ⟨round, miter, bevel⟩ · `miter=`(2) | `dissolve` · `separate` |
| `offset` | `native:offsetline` | `distance` | `segments=`(8) · `join=`(round) ⟨round, miter, bevel⟩ · `miter=`(2) | — |
| `simplify` | `native:simplifygeometries` | `tolerance` | `method=`(douglas) ⟨douglas, grid, area⟩ | — |
| `smooth` | `native:smoothgeometry` | — | `iterations=`(1) · `offset=`(0.25) · `max_angle=`(180) | — |
| `densify` | `native:densifygeometriesgivenaninterval` | `interval` | — | — |
| `subdivide` | `native:subdivide` | — | `max_nodes=`(256) | — |
| `centroid` | `native:centroids` | — | — | — |
| `pointonsurface` | `native:pointonsurface` | — | — | `all_parts` |
| `convexhull` | `native:convexhull` | — | — | — |
| `boundingbox` | `native:boundingboxes` | — | — | — |
| `minrect` | `native:orientedminimumboundingbox` | — | — | — |
| `vertices` | `native:extractvertices` | — | — | — |
| `explode` | `native:multiparttosingleparts` | — | — | — |
| `promote` | `native:promotetomulti` | — | — | — |
| `collect` | `native:collect` | `[field]` | — | — |
| `fix` | `native:fixgeometries` | — | — | — |
| `swapxy` | `native:swapxy` | — | — | — |
| `forcerhr` | `native:forcerhr` | — | — | — |
| `snap` | `native:snapgeometries` | `reference` (layer), `tolerance` | `behavior=`(align) ⟨align, closest, align-keep, closest-keep, ends-align, ends-closest, ends-only, anchor⟩ | — |

### Vector — CRS, attributes, counting

| Verb | Algorithm | Args | Options | Flags |
|---|---|---|---|---|
| `reproject` | `native:reprojectlayer` | `target_crs` | `operation=` | `convert_curved` · `transform_z` |
| `renamefield` | `native:renametablefield` | `field`, `name` | — | — |
| `dropfields` | `native:deletecolumn` | `fields` (list) | — | — |
| `keepfields` | `native:retainfields` | `fields` (list) | — | — |
| `countpoints` | `native:countpointsinpolygon` | — | `points=`(req, layer) · `field=`(NUMPOINTS) · `weight=` · `classfield=` | — |
| `zonalstats` | `native:zonalstatisticsfb` | — | `raster=`(req) · `band=`(1) · `stats=`(count,sum,mean) ⟨count, sum, mean, median, stdev, min, max, range, minority, majority, variety, variance⟩ — comma-list · `prefix=`(_) | — |

### Vector — point creation

| Verb | Algorithm | Args | Options | Flags |
|---|---|---|---|---|
| `voronoi` | `native:voronoipolygons` | — | `buffer=`(0) | — |
| `delaunay` | `native:delaunaytriangulation` | — | — | — |
| `pointsalong` | `native:pointsalonglines` | `distance` | `start=` · `end=` | — |

### Raster

Raster verbs default `CREATION_OPTIONS` to lossless `COMPRESS=DEFLATE|TILED=YES` so
intermediates aren't left huge; the final product's compression is governed by `save`.

| Verb | Algorithm | Args | Options | Flags |
|---|---|---|---|---|
| `warp` | `gdal:warpreproject` | `target_crs` | `source_crs=` · `resampling=`(nearest) ⟨nearest, bilinear, cubic, cubicspline, lanczos, average, mode, max, min, median, q1, q3⟩ · `nodata=` · `resolution=` | — |
| `clipraster` | `gdal:cliprasterbymasklayer` | `mask` (layer) | `nodata=` | — |
| `hillshade` | `native:hillshade` | — | `z_factor=`(1) · `azimuth=`(300) · `altitude=`(40) | — |
| `slope` | `gdal:slope` | — | `band=`(1) · `scale=`(1) | `percent` |
| `aspect` | `gdal:aspect` | — | `band=`(1) | `trig` · `zero_flat` |
| `polygonize` | `gdal:polygonize` | — | `band=`(1) · `field=`(DN) | `eight` |

Anything not aliased is still reachable with `run <algorithm-id> …` (§6). For the full
catalogue of all 769 algorithms — parameters, defaults, enum options, and descriptions — see
the [algorithm appendix](../algorithms/README.md).

---

## 6. The `run` escape hatch & `describe`

`run <id> KEY=value …` calls any installed QGIS Processing algorithm with its native
parameter names — the full catalogue (1000+ `native:`, `gdal:`, `qgis:`, `grass:`, `pdal:`,
`saga:` algorithms), not just the aliased verbs. Use it for anything without an alias, or
when you need a parameter an alias doesn't expose.

- `INPUT` is filled from the piped layer; `OUTPUT` from a temp file — supply either to
  override.
- Multi-input parameters take a `;`-separated list: `INPUT="a.tif;b.tif"`.
- A value with `*`/`?`/`[` is globbed relative to the flow file: `INPUT="tiles/*.jp2"`.
- Values coerce: `true`/`false` → bool, integers → int, decimals → float, else string.

```
load dem.tif | run native:slope Z_FACTOR=2 NODATA=-9999 | save slope.tif
run gdal:translate INPUT=in.vrt OUTPUT=out.jp2 CREATION_OPTIONS="QUALITY=25"
```

`niva describe <name>` introspects either a niva verb (its alias mapping, args, options,
flags — no QGIS needed) or a QGIS algorithm id (its live parameters and outputs — QGIS
needed):

```
niva describe buffer
niva describe gdal:warpreproject
```

The **[algorithm appendix](../algorithms/README.md)** lists all 769 algorithms by provider —
each with its parameters (type, required, default, enum options), description, outputs, and
niva alias (⭐) — so you can find and copy a `run <id> …` for anything without an alias.

---

## 7. Database connections (`@conn`)

niva reads and writes databases through **saved QGIS connections**. A reference is:

```
@conn                  # the connection itself (for sql)
@conn.table            # a table in the connection's default schema
@conn.schema.table     # a schema-qualified table
```

`@` always means a saved DB connection — never a file (a path is just a path). Used by
`load @conn.table`, `save @conn.table`, `sql @conn "…"`, and `project … repoint=@conn`.

**Default schema:** explicit wins; otherwise `public` for PostgreSQL/PostGIS, and the
provider default (`''`) for SpatiaLite/file databases.

**Credentials never enter a flow.** Only the connection *name* crosses from the flow into
niva; host, database, user, and password are resolved from QGIS's own connection store (the
single source of truth, configured in the QGIS Browser or the plugin Setup tab). niva never
stores, logs, or transmits credentials — errors carry only the connection name and table,
never the URI, password, or query text. SpatiaLite and PostGIS connections are used
identically; the only difference is which engine's spatial SQL functions you write.

---

## 8. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NIVA_TMPDIR` | system temp | **Disk-backed scratch dir for raster intermediates.** Point it at a roomy real-disk folder so a multi-GB raster pipeline doesn't exhaust a small RAM-backed `/tmp`. Strongly recommended for raster work. |
| `CPL_TMPDIR` | follows `NIVA_TMPDIR` | GDAL's own scratch dir; niva points it at `NIVA_TMPDIR` unless you set it. |
| `NIVA_LOG` | unset | Default journal base path; writes `<base>.jsonl` + `<base>.log`. CLI `--log` overrides. |
| `NIVA_TEMPLATES` | `~/.niva/templates` | Extra directory for named project templates; shadows the user library and bundled templates. Also where `project to-template=<name>` writes. |
| `NIVA_QGIS_PROFILE` | active desktop profile | **Which QGIS user profile to read** for database connections (the `@conn` names) and other settings, when running standalone. By default niva uses the profile your QGIS desktop last used; set this to another profile's name to target its connections. Run `info` to see all profiles and their connections. |
| `QGIS_PREFIX_PATH` | `/usr` | QGIS install prefix for standalone bootstrap. |
| `QT_QPA_PLATFORM` | `offscreen` (set if unset) | Headless Qt platform for standalone runs. |
| `NIVA_NTFY_TOPIC` | unset | Default ntfy topic for `notify`. |
| `NIVA_NTFY_SERVER` | `https://ntfy.sh` | ntfy server URL. |
| `NIVA_NTFY_TOKEN` | unset | Bearer token for protected ntfy topics (never logged). |
| `NIVA_NTFY_ON_ERROR` | unset | When truthy, auto-send a high-priority ntfy when a run fails. |
| `NIVA_NTFY_ON_WARNING` | unset | When truthy, auto-send an ntfy on warnings (mixed geometry, datum transforms, skipped batch items), de-duplicated per run. |
| `NIVA_SMTP_HOST` | unset (auto for Gmail) | SMTP server for `email`. |
| `NIVA_SMTP_PORT` | `587` | SMTP port; `465` = implicit TLS. |
| `NIVA_SMTP_USER` | unset | SMTP username. |
| `NIVA_SMTP_PASSWORD` | unset | SMTP password (Gmail: an App Password). |
| `NIVA_SMTP_FROM` | = `NIVA_SMTP_USER` | From address; a `@gmail.com` value auto-selects the Gmail host. |

Truthy = `1`, `true`, `yes`, `on` (case-insensitive). Inside QGIS, the plugin's **Setup**
tab sets these for you (and can store secrets in the QGIS encrypted store).

---

## 9. Command-line interface

The package installs a `niva` console script (`niva.cli.main`).

```
niva run <file.niva> [--dry-run | --explain] [--log <base>]
niva "<flow>"        [--dry-run | --explain] [--log <base>]
niva describe <verb-or-algorithm-id>
niva export <file.niva> [-o <file.py>]
niva import <file.py>   [-o <file.niva>]
```

| Command / flag | Effect |
|---|---|
| `niva run flow.niva` | execute a `.niva` file (real, via PyQGIS) |
| `niva "load a.gpkg \| buffer 100m \| save b.gpkg"` | execute an inline flow |
| `--dry-run` | print the plan and validate it over the mock backend (no QGIS, no data touched) |
| `--explain` | parse + bind only; print the resolved algorithm + parameters per stage |
| `--log <base>` | also write the journal `<base>.jsonl` + `<base>.log` |
| `niva describe <name>` | introspect a verb or algorithm id |
| `niva export flow.niva [-o out.py]` | transpile a flow to a standalone PyQGIS script |
| `niva import script.py [-o out.niva]` | recover a flow from a niva-shaped PyQGIS script |

**Exit codes:** `0` ok · `1` runtime error (`OpError`) · `2` usage / parse error
(`FlowError`) · `3` QGIS not importable. Progress and errors go to stderr; result markers to
stdout. A real run needs QGIS's Python (see the [User Guide](user-guide.md)).

---

## 10. Python API

The public API (`import niva`) is small and stable:

```python
flow(text, *, backend=None, file=None, log=None, log_append=False, progress=None, cancel=None)
run_file(path, *, backend=None)
describe(name)
__version__
NivaError, FlowError, OpError          # exception types
```

### `flow(text, …)`

Parse and execute a flow string; returns the final layer handle (its `.ref` is an on-disk
path for a saved file, or a live `QgsMapLayer`), or `None` for a terminal flow.

| Parameter | Default | Meaning |
|---|---|---|
| `text` | — | the flow string |
| `backend` | real `PyqgisBackend` (needs QGIS) | pass `MockBackend()` to dry-run without QGIS |
| `file` | `None` | path of the source `.niva` file — sets the base dir for relative paths / `call` |
| `log` | `NIVA_LOG` | journal base path → `<log>.jsonl` + `<log>.log` |
| `log_append` | `False` | `True` appends to the journal; `False` truncates |
| `progress` | `None` | `callable(str)` — a `▶ <stage>` line per stage plus `   45%` ticks |
| `cancel` | `None` | `callable() -> bool` — return `True` to abort a long step |

```python
import niva
layer = niva.flow('load "data.gpkg|layername=roads" | buffer 100m dissolve | save out.gpkg')
print(layer.ref)            # '/abs/path/out.gpkg'
```

### `run_file(path, *, backend=None)`

Read a `.niva` file and execute it (sets `file=path` so relative paths resolve).

```python
import niva
niva.run_file("myflow.niva")
```

### `describe(name)`

Return a formatted description string for a verb or an algorithm id (see §6). Pure for a
verb; needs QGIS for an algorithm id.

Importing `niva` is safe on any interpreter — QGIS is imported lazily only when a real run
executes. To run for real outside QGIS you need QGIS's Python on `PYTHONPATH`; see the
[User Guide](user-guide.md) for the exact recipe.
