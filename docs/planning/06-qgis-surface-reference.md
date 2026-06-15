# Niva — QGIS Capability Surface: Reference & niva Mapping

_A reference catalogue of the geoprocessing surface niva could reach, and how
each surface is accessed **today** (human and programmatic) versus **through
niva** (proposed grammar). Status: reference + design exploration — niva's
grammar is illustrative and not yet built. See `01-prd.md` for the grammar
intent and `00-critique-and-open-questions.md` for open decisions._

> **Snapshot.** All counts and signatures below were **enumerated from a live
> QGIS install** (see version stack), not from memory. They are build-specific:
> a different QGIS, or one with GRASS/SAGA/Oracle absent or present, exposes a
> different set. Machine-readable inventories accompany this doc:
> - [`reference/qgis-algorithms-4.0.3.tsv`](reference/qgis-algorithms-4.0.3.tsv) — all 769 Processing algorithms
> - [`reference/qgis-expression-functions-4.0.3.tsv`](reference/qgis-expression-functions-4.0.3.tsv) — all 406 expression functions

---

## 0. Version stack (reference environment)

The reachable surface is a function of these versions. niva should report this
stack (it determines which algorithms, drivers, CRS operations and SQL functions
exist).

| Component | Version | Role |
|-----------|---------|------|
| QGIS | **4.0.3-Norrköping** | Processing framework, PyQGIS API, expression engine |
| Python | **3.14.4** | the interpreter QGIS/niva run on |
| Qt / PyQt | **6.10.2 / 6.10.2** | GUI + bindings |
| GDAL/OGR | **3.12.2** | raster/vector I/O (210 raster + 80 vector drivers), `gdal:*` algorithms |
| PROJ | **9.7.1** | CRS + coordinate operations |
| GEOS | **3.13.1** | planar geometry predicates/overlay (buffer, intersection, …) |
| SQLite | **3.46.1** | embedded DB engine |
| SpatiaLite | **5.1.0** | spatial SQL over SQLite (1131 SQL functions, 238 `ST_*`) |

> These are this Linux dev box's versions; they differ from other machines (e.g.
> a Windows OSGeo4W box reports a different GDAL/PROJ/Qt). niva must read them
> live, never assume.

---

## 1. The automation surfaces — overview

QGIS is not one API. niva potentially spans **five distinct surfaces**, each with
its own access method, naming, and ergonomics today:

| # | Surface | Size (this build) | Reached today by a human | Reached today by a program |
|---|---------|-------------------|--------------------------|----------------------------|
| 1 | **Processing algorithms** | 769 algs / 8 providers | Processing Toolbox dialogs | `processing.run("id", {DICT})` |
| 2 | **Expression functions** | 406 fns / 23 groups | Field Calculator, expression builder | `QgsExpression(...).evaluate()` |
| 3 | **Database spatial SQL** (SpatiaLite/PostGIS) | 238 `ST_*` (SpatiaLite) + PostGIS | DB Manager SQL window | provider connection `.executeSql()` |
| 4 | **PyQGIS API** (rendering, layouts, symbology, project) | hundreds of classes | GUI only (mostly) | direct PyQGIS — verbose, expert-only |
| 5 | **Data providers / drivers** (I/O, connections) | 33 providers, 80+210 OGR/GDAL drivers | Browser, Data Source Manager | provider keys, `QgsVectorLayer(uri, …)` |

niva's core bet (`01-prd.md`) is a single readable text grammar over **surface 1**
first, then **2** and **3** — with **4** and **5** as the "hard-to-reach" frontier
(§7). The rest of this doc details each.

---

## 2. Processing algorithms (769)

The primary automatable surface: a registry of algorithms, each with a stable
`provider:name` id and a typed parameter set.

### 2.1 Providers (this build)

| Provider id | Algorithms | Notes |
|-------------|-----------:|-------|
| `native` | 339 | QGIS native C++ — the core, fastest, best-maintained set |
| `grass` | 307 | GRASS GIS (only if GRASS is installed) |
| `gdal` | 59 | GDAL/OGR command wrappers (raster + vector) |
| `qgis` | 39 | older Python QGIS algorithms (incl. `qgis:executesql`) |
| `pdal` | 24 | point-cloud (PDAL) |
| `3d` | 1 | 3D tiling |
| `model` / `project` / `script` | 0 | user-defined; empty here |
| **Total** | **769** | |

### 2.2 `native` group taxonomy (27 groups)

Where the everyday work lives:

| Count | Group | | Count | Group |
|------:|-------|-|------:|-------|
| 82 | Vector geometry | | 9 | Raster creation |
| 39 | Raster analysis | | 9 | Vector selection |
| 29 | Vector general | | 8 | Database |
| 21 | Check geometry | | 7 | Raster terrain analysis |
| 14 | Vector creation | | 7 | Network analysis |
| 14 | Vector analysis | | 6 | Metadata tools |
| 13 | Cartography | | 6 | Raster tools |
| 13 | Modeler tools | | 4 | GPS |
| 11 | Vector table | | 3 | Vector coverage / tiles / Layer tools |
| 11 | Vector overlay | | 2 | 3D Tiles |
| 10 | Mesh / Fix geometry | | 1 | Plots / Interpolation |

### 2.3 Signatures — how an algorithm is actually shaped

Every algorithm is `provider:name` + a dict of **`ALL_CAPS` parameters**, each
typed (`source`, `sink`, `distance`, `number`, `enum`, `field`, `crs`,
`expression`, `raster`, `band`, `coordinateoperation`, …), most **required**,
several with non-obvious defaults and `enum` integer codes. Representative
signatures (enumerated live):

```
native:buffer        — Buffer  [Vector geometry]
  INPUT             source     required
  DISTANCE          distance   required  default=10
  SEGMENTS          number     required  default=5
  END_CAP_STYLE     enum       required  default=0      # 0=round,1=flat,2=square
  JOIN_STYLE        enum       required  default=0      # 0=round,1=miter,2=bevel
  MITER_LIMIT       number     required  default=2
  DISSOLVE          boolean    required  default=False
  SEPARATE_DISJOINT boolean    required  default=False
  OUTPUT            sink       required                 # -> outputVector

native:clip          — Clip  [Vector overlay]
  INPUT  source required   OVERLAY source required   OUTPUT sink required

native:dissolve      — Dissolve  [Vector geometry]
  INPUT source required   FIELD field optional   SEPARATE_DISJOINT boolean   OUTPUT sink

native:reprojectlayer — Reproject layer  [Vector general]
  INPUT source required   TARGET_CRS crs required default='EPSG:4326'
  CONVERT_CURVED_GEOMETRIES boolean   TRANSFORM_Z boolean
  OPERATION coordinateoperation optional   OUTPUT sink

native:intersection  — Intersection  [Vector overlay]
  INPUT source   OVERLAY source   INPUT_FIELDS field?   OVERLAY_FIELDS field?
  OVERLAY_FIELDS_PREFIX string?   GRID_SIZE number?   OUTPUT sink

native:joinattributestable — Join attributes by field value  [Vector general]
  INPUT source   FIELD field   INPUT_2 source   FIELD_2 field
  FIELDS_TO_COPY field?   METHOD enum   DISCARD_NONMATCHING boolean   PREFIX string?
  OUTPUT sink?   NON_MATCHING sink?     # + outputs: JOINED_COUNT, UNJOINABLE_COUNT

native:zonalstatisticsfb — Zonal statistics  [Raster analysis]
  INPUT source   INPUT_RASTER raster   RASTER_BAND band default=1
  COLUMN_PREFIX string default='_'   STATISTICS enum default=[0,1,2]   OUTPUT sink

gdal:warpreproject   — Warp (reproject)  [Raster projections]
  INPUT raster   SOURCE_CRS crs?   TARGET_CRS crs?   RESAMPLING enum
  NODATA number?   TARGET_RESOLUTION number?   DATA_TYPE enum
  TARGET_EXTENT extent?   MULTITHREADING boolean   EXTRA string?   OUTPUT rasterDestination
```

**The ergonomics problem niva targets:** the names are `ALL_CAPS`, the enums are
magic integers, `OUTPUT` must be an explicit sink/path or the sentinel
`'TEMPORARY_OUTPUT'`, and chaining means manually threading `result["OUTPUT"]`
into the next call's `INPUT`. This is a programming task even when the *intent*
("buffer by 100, dissolve, clip to the city") is one sentence.

### 2.4 Today vs niva

**Human today** — Processing Toolbox → search "Buffer" → fill a modal dialog →
Run; repeat per step, manually feeding each output into the next tool.

**Program today (PyQGIS):**
```python
import processing
buf = processing.run("native:buffer", {
    "INPUT": "roads.gpkg", "DISTANCE": 100, "SEGMENTS": 5,
    "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
    "DISSOLVE": True, "SEPARATE_DISJOINT": False,
    "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
processing.run("native:clip", {
    "INPUT": buf, "OVERLAY": "city.gpkg", "OUTPUT": "roads_local.gpkg"})
```

**niva (proposed):**
```
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

niva's job here: an **alias registry** (`buffer` → `native:buffer`), sensible
**defaults** (segments, cap/join styles), **named flags** for the common toggles
(`dissolve`), automatic **output lifecycle** (temp between steps, materialize on
`save`), and **enum-by-word** (`cap=flat` not `END_CAP_STYLE=1`).

### 2.5 Metadata, data quality & lineage

A cross-surface capability the analyst workflow leans on (`use_cases.md`: *assess
the data, convey its quality, document the data and the methods*). QGIS already
provides three pieces — niva's job is to make them automatic and connected
(designed in [`08-data-quality-provenance.md`](08-data-quality-provenance.md)).

**(a) Formal layer metadata** — the "Metadata tools" Processing group (6 algos),
backed by the ISO-19115-style `QgsLayerMetadata` model (PyQGIS), readable inline
via the `layer_property()` expression function:

| algorithm | signature | does |
|-----------|-----------|------|
| `native:setlayermetadata` | `INPUT, METADATA:file(.qmd), DEFAULT:bool` | set metadata from a `.qmd` |
| `native:setmetadatafields` | `INPUT, TITLE?, ABSTRACT?, IDENTIFIER?, TYPE?, LANGUAGE?, ENCODING?, CRS?, FEES?` | set individual fields |
| `native:updatelayermetadata` / `native:copylayermetadata` | `SOURCE, TARGET[, DEFAULT]` | merge / copy metadata between layers |
| `native:addhistorymetadata` | `INPUT, HISTORY:string` | **append a lineage / history entry** |
| `native:exportlayermetadata` | `INPUT, OUTPUT:file` | export ISO metadata XML |

`QgsLayerMetadata` fields: title, abstract, keywords, categories, contacts, links,
licenses, rights, constraints, **history** (lineage), language, encoding, fees,
crs, extent, identifier, type.

**(b) Data-quality assessment** — the **Check geometry** group (21 algorithms:
duplicate geometries/vertices, gaps, overlaps, slivers, self-intersections,
dangles, holes, small angles/areas…), `native:checkvalidity`, and profiling algos
`native:basicstatisticsforfields`, `native:listuniquevalues`,
`native:rasterlayerstatistics`. Structural facts (CRS, extent, feature count,
field schema, driver) come from `QgsVectorLayer` / `layer_property()`.

**(c) Reached today:** metadata is mostly **GUI-only** (Layer Properties ▸
Metadata tab, `.qmd` sidecars); the 6 algorithms automate parts; quality checks
run as individual Processing dialogs. There is **no single "assess this dataset"
command, and nothing auto-records what you did.**

**niva (proposed):**
```
load cats.gdb | assess          # quality report: CRS, extent, schema, validity, duplicates, nulls
load x.gpkg   | metadata        # show formal metadata (title/abstract/keywords/lineage)
…             | metadata set title="Cat parcels" keywords=cats,canvass
…             | save out.gpkg    # niva auto-writes the pipeline as lineage history
```

This is niva's **provenance differentiator: the operation log becomes formal
lineage** — every data-altering step is recorded and, on `save`, written into the
layer's metadata `history` (`native:addhistorymetadata`). Full design in
`08-data-quality-provenance.md`.

---

## 3. Expression functions (406)

A second, separate surface: the QGIS expression engine — the functions you use in
the Field Calculator, labels, rule-based symbology, data-defined overrides, and
`native:extractbyexpression`. **406 functions in 23 groups**:

| Count | Group | | Count | Group |
|------:|-------|-|------:|-------|
| 152 | GeometryGroup (`$area`, `buffer`, `intersects`, `centroid`, `transform`, …) | | 21 | Date and Time |
| 36 | Arrays | | 19 | Conversions |
| 27 | Math | | 17 | Record and Attributes |
| 27 | String | | 16 | Maps |
| 24 | Color | | 9 | Files and Paths |
| 23 | Aggregates | | + | Conditionals, Fuzzy, Rasters, Layers, … |

These overlap conceptually with Processing (there is both a `buffer` **algorithm**
and a `buffer()` **expression function**) but operate per-feature/inline rather
than layer-to-layer. Examples (live signatures): `buffer(geom, dist, …)`,
`area($geometry)`, `intersects(a, b)`, `transform(geom, src, dest)`,
`aggregate(layer, agg, expr, …)`, `array_filter(array, expr)`,
`format_date(date, fmt)`.

**Today:** human → Field Calculator dialog; program →
`QgsExpression("area($geometry)").evaluate(context)`.

**niva (proposed):** expressions appear *inline* in the pipeline as filters and
computed fields, reusing QGIS's own expression syntax verbatim (no second
language to learn):
```
load parcels.gpkg | filter "area($geometry) > 1000 and \"zone\" = 'R1'" \
  | compute density = "\"pop\" / area($geometry)" | save big_residential.gpkg
```
`filter` maps to `native:extractbyexpression`; `compute` to the field-calculator
algorithm — both just carry a raw QGIS expression string through.

---

## 4. Database spatial-SQL geoprocessing (SpatiaLite & PostGIS)

**This is a third, large geoprocessing surface, parallel to Processing** — and a
primary reason niva wants SQL passthrough. SpatiaLite and PostGIS each ship a full
`ST_*` spatial function library that does buffering, overlay, measurement,
validity, transforms, and topology **inside the database**, often faster and
closer to the data than round-tripping through Processing.

### 4.1 SpatiaLite 5.1.0 — enumerated live

- **1131** total registered SQL functions (via `PRAGMA function_list`); **238**
  under `ST_` names; 16 `gpkg*` GeoPackage functions.
- **The `ST_` count understates the spatial surface.** Cross-checked against the
  [official SpatiaLite 5.1.0 SQL reference][sl-ref] (~300+ functions in ~50
  categories): SpatiaLite registers most spatial functions under **both** the
  OGC `ST_` name **and** a legacy non-prefixed alias (`Area()` *and* `ST_Area()`,
  `Buffer()` *and* `ST_Buffer()`) — all 25 legacy names probed here are present —
  **plus** SpatiaLite-only extensions with no `ST_` form. So the real geoprocessing
  surface ≈ the ~300+ documented spatial functions; the 1131 total adds SQLite
  built-ins and the duplicate alias set.
- **Extensions beyond core OGC** (confirmed present on this install): tessellation
  **grids** (`SquareGrid`/`HexagonalGrid`/`TriangularGrid`, 8 fns), **topology**
  TopoGeo/TopoNet (62 fns), **routing/network** (7), **GeoPackage** compat
  (24 `gpkg*`), format converters (`AsKml`/`AsGeoJSON`/`AsEWKB`/`AsTWKB`),
  **RasterLite2** (RL2), KNN, geodesic, and metadata/catalog functions. The
  [SpatiaLite topics][sl-topics] cookbook organizes these (Topology — ISO, 8
  tutorials; tessellations; DE-9IM relationship matrices; spatial indexing).
- **Virtual Tables** ([topics][sl-topics]) — a distinctive SpatiaLite capability:
  external sources are attached as SQL-queryable tables — `VirtualShape`
  (shapefiles), `VirtualText` (CSV), `VirtualXL` (Excel), `VirtualOGR` (any OGR
  source), `VirtualPostgres` (PostGIS), plus algorithmic ones `VirtualRouting`
  (SQL routing), `VirtualKNN` (nearest-neighbour). This lets `ST_*` SQL run over
  files that have no SQL engine of their own — relevant to niva's `sql` verb (§5.3).
- Core coverage mirrors Processing's vector geometry/overlay groups:

[sl-ref]: https://www.gaia-gis.it/gaia-sins/spatialite-sql-5.1.0.html
[sl-topics]: https://www.gaia-gis.it/gaia-sins/spatialite_topics.html

| ~Count | `ST_*` family | Examples |
|-------:|---------------|----------|
| ~23 | overlay / processing | `ST_Buffer`, `ST_Intersection`, `ST_Union`, `ST_Difference`, `ST_SymDifference`, `ST_ConvexHull`, `ST_ConcaveHull`, `ST_VoronoiPolygons`, `ST_OffsetCurve`, `ST_Split` |
| ~17 | accessors / editing | `ST_NumPoints`, `ST_StartPoint`, `ST_PointN`, `ST_ExteriorRing`, `ST_AddPoint`, `ST_Simplify`, `ST_Snap` |
| ~16 | measurement | `ST_Area`, `ST_Length`, `ST_Distance`, `ST_Perimeter`, `ST_Azimuth` |
| ~14 | relationships | `ST_Intersects`, `ST_Contains`, `ST_Within`, `ST_Touches`, `ST_Crosses`, `ST_Overlaps`, `ST_Covers`, `ST_Relate` |
| ~6 | transform / CRS | `ST_Transform`, `ST_SetSRID`, `ST_Shift`, `ST_Scale`, `ST_Rotate` |
| ~4 | constructors | `ST_GeomFromText`, `MakePoint`, `ST_MakeLine`, `ST_BuildArea` |

### 4.2 PostGIS

Not enumerated live here (no PostGIS on this box), but cross-checked against the
[official PostGIS function reference][pg-ref] — and the parallel to SpatiaLite is
near one-to-one. The reference documents **300+ functions across 23 sections**;
the *installed* count is larger (~1000+ with overloads, raster and topology). Same
families, same `ST_` names:

| Family | Examples |
|--------|----------|
| constructors / accessors / editors | `ST_MakePoint`, `ST_Boundary`, `ST_AddPoint`, `ST_Reverse` |
| validation | `ST_IsValid`, `ST_MakeValid` |
| SRS / I/O | `ST_Transform`, `ST_SRID`, WKT/WKB/GeoJSON/KML/GML |
| relationships / measurement | `ST_Intersects`, `ST_Contains`, `ST_DWithin`, `ST_Distance`, `ST_Area` |
| overlay | `ST_Union`, `ST_Intersection`, `ST_Difference` |
| processing | `ST_Buffer`, `ST_Simplify`, `ST_ConvexHull`, `ST_ConcaveHull`, `ST_Subdivide`, `ST_VoronoiPolygons`, `ST_DelaunayTriangles` |
| clustering | `ST_ClusterKMeans`, `ST_ClusterDBSCAN` |
| linear referencing / trajectory | `ST_LineInterpolatePoint`, `ST_ClosestPointOfApproach` |
| 3D / SFCGAL | `ST_3DIntersects`, `ST_3DDistance` |
| KNN operators | `<->`, `<#>` (index-assisted nearest neighbour) |

Separate extensions (own schemas): **raster** (`postgis_raster`), **topology**
(`postgis_topology`), **address standardizer + Tiger geocoder**. The **set is
version-dependent**, so niva must introspect a connection (`SELECT
postgis_full_version()`) rather than assume.

[pg-ref]: https://postgis.net/docs/reference.html

> **Correlation note.** SpatiaLite and PostGIS are both OGC SQL/MM
> implementations, so their `ST_*` surfaces are close to interchangeable — and
> both mirror QGIS Processing's vector-geometry/overlay groups (§2.2). The *same*
> "buffer" is reachable as `native:buffer` (algorithm), `buffer()` (expression),
> and `ST_Buffer` (either DB). This three-way overlap is the central naming
> decision for niva (§8.1), and the strong DB-to-DB parallel means one niva `sql`
> verb can target either engine with the same grammar.

### 4.3 How this is reached today

**Human:** DB Manager → SQL Window → type SQL. Or the Browser → right-click a
PostGIS/SpatiaLite connection → Execute SQL. GUI-bound and connection-bound.

**Program (PyQGIS):** via a provider connection or a Processing SQL algorithm:
```python
from qgis.core import QgsProviderRegistry
md = QgsProviderRegistry.instance().providerMetadata("postgres")
conn = md.findConnection("my_db")            # a saved connection
conn.executeSql("UPDATE roads SET geom = ST_Buffer(geom, 5) WHERE class='local'")

# or as a Processing step (loads result as a layer):
processing.run("native:postgisexecuteandloadsql",
               {"DATABASE": "my_db",
                "SQL": "SELECT id, ST_Buffer(geom,5) AS geom FROM roads"})
```
SpatiaLite equivalents: `native:spatialiteexecutesql`,
`native:spatialiteexecutesqlregistered`. For *any* OGR source (incl. GeoPackage),
GDAL offers `gdal:executesql` with the **OGRSQL** or **SQLITE** dialect.

### 4.4 niva (proposed)

niva treats spatial SQL as a first-class pipeline verb — passing SQL **through** to
the backing engine, against a file or a named connection:

```
# GeoPackage / OGR source, SQLITE dialect under the hood (gdal:executesql):
sql "SELECT *, ST_Buffer(geom, 100) AS geom FROM roads WHERE class='local'"
    from data.gpkg | save local_buffer.gpkg

# Against a registered PostGIS connection — the SELECT becomes a query layer:
sql @prod_db "SELECT gid, ST_Subdivide(geom) AS geom FROM parcels" | save subdivided.gpkg
```

> Canonical `sql` syntax and forms are spec'd in `03-§2.6`. **Reads** (a `SELECT`)
> become a layer via a query layer / `gdal:executesql` / `qgis:executesql`. **Writes**
> (`UPDATE`/DDL — *no layer returned*) use `native:postgisexecutesql` /
> `native:spatialiteexecutesql` and are a **v2** capability, not v1 read-passthrough.

Design questions this raises (tracked for `02-architecture.md`):
- **Which engine runs the SQL?** OGR `SQLITE` dialect (portable, works on any
  source) vs the native provider (`postgisexecutesql`/`spatialiteexecutesql`,
  full `ST_*` + writes). niva likely picks by source type.
- **Connection model:** `@name` referencing QGIS's saved provider connections
  (`QgsProviderRegistry … findConnection`) vs an inline URI.
- **Mixing surfaces:** can a pipeline flow from a Processing step into a `sql`
  step and back? (It can, if niva materializes to a temp GeoPackage between
  engines — the output-lifecycle problem again.)

---

## 5. SQL drivers, data providers & connections

What niva can read, write, and run SQL against. Two layers:

### 5.1 QGIS data providers (this build — 33)

SQL/connection-capable providers (expose `QgsAbstractDatabaseProviderConnection`
→ `executeSql`, `tables`, `createVectorTable`, …):

| Provider | SQL/connections | Spatial SQL geoprocessing |
|----------|:---------------:|---------------------------|
| `postgres` | ✅ | PostGIS `ST_*` (full) |
| `spatialite` | ✅ | SpatiaLite `ST_*` (238) |
| `mssql` | ✅ | SQL Server geometry methods |
| `hana` | ✅ | SAP HANA spatial |
| `ogr` | ✅ | GeoPackage/SQLite via OGR `SQLITE` dialect |
| `sensorthings`, `tiledscene`, `vectortile` | ✅ (connection only) | not relational SQL |

> Note: **Oracle is not compiled into this build** (no `oracle` provider).
> `virtual` (QGIS virtual layers) is its own SQL surface — see 5.3.

Read-only / non-SQL providers present: `wms`, `wcs`, `wfs`, `arcgis*`,
`delimitedtext`, `gpx`, `memory`, `mesh`, `mdal`, `gdal`, `copc`/`ept`/`pdal`
(point cloud), `xyz/mbtiles/vtpk vector tiles`, `cesiumtiles`, `quantizedmesh`.

### 5.2 GDAL/OGR drivers

- **80 OGR vector drivers**, **210 GDAL raster drivers**.
- DB/remote OGR drivers (carry their own SQL or remote access): `PostgreSQL`,
  `MySQL`, `MSSQLSpatial`, `SQLite`, `GPKG`, `ODBC`, `PGeo`, `Carto`,
  `Elasticsearch`, `WFS`, `PGDUMP`.
- Any OGR source supports **OGR SQL** and the **SQLITE** dialect via
  `gdal:executesql` / `ExecuteSQL`, even formats with no native SQL engine.

### 5.3 Three SQL dialects niva must distinguish

1. **PostGIS SQL** — full server-side `ST_*`, writes, transactions (provider `postgres`).
2. **SpatiaLite SQL** — `ST_*` over SQLite/GeoPackage (provider `spatialite`, or OGR `SQLITE` dialect).
3. **QGIS virtual-layer SQL** (`qgis:executesql`, provider `virtual`) — run
   SpatiaLite-flavoured SQL **across already-loaded QGIS layers** regardless of
   their source, e.g. join a shapefile to a CSV to a PostGIS table in one query.

Two engines deliver that last "SQL across heterogeneous sources" trick: QGIS
virtual layers (above) and **SpatiaLite Virtual Tables** (`VirtualShape`/`Text`/
`OGR`/`Postgres`, §4.1) — both let `ST_*` SQL reach files with no native SQL
engine. niva's `sql` verb should make the dialect/engine explicit or inferable,
because the same `ST_*` call behaves differently across them.

### 5.4 SQL-execution algorithms (inventory)

`qgis:executesql` · `gdal:executesql` · `native:postgisexecutesql` ·
`native:postgisexecuteandloadsql` · `native:spatialiteexecutesql` ·
`native:spatialiteexecutesqlregistered` · plus import/export:
`native:importintopostgis`, `native:importintospatialite`,
`gdal:importvectorintopostgisdatabase*`.

---

## 6. The hard-to-reach surface (niva's frontier)

Capabilities that are **GUI-only or expert-only PyQGIS today** — no clean
algorithm, no one-liner. These are where niva could add the most, and where the
"functions humans cannot reach easily" live:

| Capability | Why it's hard today | niva opportunity |
|------------|---------------------|------------------|
| **Render a styled map to PNG/PDF** | No Processing alg; requires `QgsMapSettings` + `QgsMapRendererCustomPainterJob` or a `QgsLayout` + `QgsLayoutExporter` (dozens of lines) | `render city.qgz extent … size 1200x800 to map.png` |
| **Apply/derive symbology & styling** | `QgsSymbol`/`QgsRenderer` classes; `.qml` files; no algorithm | `style roads.gpkg by class using styles/roads.qml` |
| **Print layouts / atlases** | `QgsPrintLayout`, `QgsLayoutItemMap`, atlas iteration — entirely PyQGIS/GUI | `atlas template.qpt over regions.gpkg to pdf/` |
| **Manage DB connections / schema** | provider connection API, GUI Browser | `connections list`, `tables @prod_db` |
| **Field calculator at scale / batch** | per-layer GUI, or scripting | covered by `compute`/`filter` (§3) |
| **Project assembly** (add layers, set CRS, save `.qgz`) | `QgsProject` API, GUI | `project new crs EPSG:3857 add *.gpkg save city.qgz` |
| **Multi-step temp lifecycle** | manual `TEMPORARY_OUTPUT` threading + cleanup | implicit in the pipeline |

These are **proposals**, not commitments — several (rendering, layouts) are large
enough to be out of an MVP (`03-mvp-scope.md`).

---

## 7. Before / after — worked examples

**A. Buffer → dissolve → clip → save** (Processing surface)
```python
# before (PyQGIS): 8 magic params + manual output threading
buf = processing.run("native:buffer", {"INPUT":"roads.gpkg","DISTANCE":100,"SEGMENTS":5,
  "END_CAP_STYLE":0,"JOIN_STYLE":0,"MITER_LIMIT":2,"DISSOLVE":True,
  "SEPARATE_DISJOINT":False,"OUTPUT":"TEMPORARY_OUTPUT"})["OUTPUT"]
processing.run("native:clip", {"INPUT":buf,"OVERLAY":"city.gpkg","OUTPUT":"roads_local.gpkg"})
```
```
# after (niva)
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

**B. Reproject** (Processing surface)
```python
processing.run("native:reprojectlayer", {"INPUT":"x.gpkg","TARGET_CRS":"EPSG:3857",
  "CONVERT_CURVED_GEOMETRIES":False,"TRANSFORM_Z":False,"OUTPUT":"y.gpkg"})
```
```
load x.gpkg | reproject EPSG:3857 | save y.gpkg
```

**C. Zonal statistics** (raster × vector)
```python
processing.run("native:zonalstatisticsfb", {"INPUT":"zones.gpkg","INPUT_RASTER":"dem.tif",
  "RASTER_BAND":1,"COLUMN_PREFIX":"elev_","STATISTICS":[0,1,2],"OUTPUT":"out.gpkg"})  # 0,1,2 = count,sum,mean
```
```
load zones.gpkg | zonalstats dem.tif band=1 stats=mean,min,max prefix=elev_ | save out.gpkg
```

**D. Spatial SQL** (database surface — SpatiaLite/PostGIS `ST_*`)
```python
processing.run("native:spatialiteexecutesql", {"DATABASE":"city.sqlite",
  "SQL":"UPDATE roads SET geom = ST_Buffer(geom, 100) WHERE class='local'"})
```
```
sql @city "UPDATE roads SET geom = ST_Buffer(geom, 100) WHERE class='local'"
```

**E. Filter + compute** (expression surface)
```python
sel = processing.run("native:extractbyexpression",
  {"INPUT":"parcels.gpkg","EXPRESSION":"area($geometry) > 1000","OUTPUT":"TEMPORARY_OUTPUT"})["OUTPUT"]
# + a separate field-calculator run for the density column…
```
```
load parcels.gpkg | filter "area($geometry) > 1000" \
  | compute density = "\"pop\" / area($geometry)" | save big.gpkg
```

**F. Render a map** (hard-to-reach surface — ~30 lines of PyQGIS today)
```python
# before: QgsMapSettings + QgsMapRendererParallelJob + QImage save … (omitted, long)
```
```
# after (proposed)
render city.qgz extent 350000,5800000,360000,5810000 size 1200x800 to city.png
```

---

## 8. Implications for niva's design

The surface survey sharpens the open questions in `00-…`:

1. **Three function namespaces collide.** `buffer` exists as a Processing
   algorithm, an expression function, **and** `ST_Buffer` in SQL. niva needs a
   coherent story: is `buffer` always the algorithm, with SQL reached only via
   the explicit `sql` verb? (Recommended — keep the alias registry pointing at
   `native:*`, and treat SQL as a distinct, explicit surface.)
2. **The alias registry is the heart.** A curated map of friendly verb → `native:*`
   id + defaulted params + word-valued enums. Generated/validated against the
   live inventory TSV so it can't drift from the installed QGIS.
3. **Output lifecycle is unavoidable and cross-surface.** Pipelines must thread
   temp outputs not just between algorithms but **between surfaces** (algorithm →
   `sql` → algorithm), which means a defined "what is a layer handle" contract
   (path vs `QgsVectorLayer` vs niva wrapper) — the issue flagged in `00-§3.4`.
4. **Introspect, never assume.** Provider set, algorithm list, CRS operations,
   and SQL `ST_*` availability are all build/connection-specific. niva should
   ship a `niva doctor` / capability report built from live enumeration (the same
   queries that produced this doc).
5. **Scope.** MVP = surfaces 1–3 (Processing + expressions + SQL passthrough) for
   vector. Rendering/layouts (surface 4) and full driver/connection management
   (surface 5) are post-MVP.

---

## Appendix — how this was generated

All figures came from the live QGIS install via PyQGIS:
`QgsApplication.processingRegistry()` (algorithms + parameter definitions),
`QgsExpression.Functions()` (expression functions),
`QgsProviderRegistry` (data providers + connection capability),
`osgeo.ogr`/`gdal` (drivers), and `PRAGMA function_list` on a `mod_spatialite`
connection (SpatiaLite `ST_*`). The full machine-readable inventories are in
[`reference/`](reference/). Re-run against any QGIS to regenerate for that build.

### Official references (cross-checked)

- QGIS Processing framework — <https://docs.qgis.org/3.44/en/docs/user_manual/processing/index.html>
  (algorithms/providers/parameters model, `processing.run`, Modeler, batch)
- QGIS expression functions — the QGIS user manual "Expressions" chapter
- SpatiaLite 5.1.0 SQL functions — <https://www.gaia-gis.it/gaia-sins/spatialite-sql-5.1.0.html>
- SpatiaLite topics (cookbook, topology, Virtual Tables) — <https://www.gaia-gis.it/gaia-sins/spatialite_topics.html>
- PostGIS function reference — <https://postgis.net/docs/reference.html>
- GDAL/OGR drivers — <https://gdal.org/drivers/>

The counts/signatures above are this build's; the references are the
version-independent source of truth for what each surface can do.
