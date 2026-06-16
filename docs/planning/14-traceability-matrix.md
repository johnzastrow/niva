# 14 · Traceability matrix

Maps every niva verb to the QGIS algorithm/function it drives, its original
QGIS signature, the niva signature, and implementation status. **Status legend:**
✅ implemented + tested · 🟡 partial · ⬜ planned.

> Grounded in live QGIS introspection — **QGIS 4.0.3-Norrköping**. Alias signatures are read
> from `niva/registry/definitions.py`; original signatures from the QGIS Processing
> registry. Regenerate with `scripts/gen_traceability_matrix.py`. Param notation:
> `NAME(type)[=default]`, a trailing `?` marks an optional QGIS parameter; niva
> notation: `<required>`, `[optional]`, `key=a/b/c` (enum choices).

## Built-in verbs (engine-handled, not registry aliases)

| niva verb | niva signature | backed by | status |
|-----------|----------------|-----------|--------|
| `load` | `load <file>` · `load "<file>\|layername=<layer>"` · `load @conn[.schema].table` | QgsVectorLayer / QgsRasterLayer; multi-layer source without a layer name is a clear error; `tableUri` for `@conn` | ✅ |
| `save` | `save <path>` | QgsVectorFileWriter (driver by extension) + metadata/lineage persistence | ✅ |
| `sql` | `sql @conn "<query>"` | QgsAbstractDatabaseProviderConnection.createSqlVectorLayer | ✅ |
| `run` | `run <algorithm-id> KEY=value …` | processing.run (raw escape hatch; scalar-coerced params) | ✅ |
| `call` | `call <file.niva>` | engine file composition (relative resolve, cycle-checked) | ✅ |
| `metadata` | `metadata set key=value …` | QgsLayerMetadata setters (title/abstract/keywords/identifier/license), persisted on save | ✅ |
| `assess` | `assess [deep] to <report.md>` | QgsVectorLayer/QgsRasterLayer introspection → markdown; `deep` adds validity/empty/duplicate/null | ✅ |
| `describe` | `describe <verb-or-algorithm-id>` (CLI/API, not a flow stage) | registry + Processing registry introspection | ✅ |

Auto-lineage: every `save` records the flow's stages into the output's
`QgsLayerMetadata.history` (prefixed `niva: `) — no verb required.

## Multi-layer sources (GeoPackage, SpatiaLite, databases)

A `.gpkg` / `.sqlite` is **not one layer** — it is a container of many vector
layers, attribute tables, and views; a database schema likewise. niva addresses
them explicitly — it never assumes one layer per file:

- **Pick a layer/table/view in a file:** `load "data.gpkg|layername=roads"`
  (the `|layername=` fragment is OGR's; it selects a vector layer, an attribute
  table, or a view by name).
- **Loading a multi-layer file with no layer name is a hard error** that lists the
  available layers — niva will not silently grab the first (a quiet wrong-layer is
  the kind of silent error niva exists to prevent). A single-layer file (e.g. a
  shapefile, or a one-layer GeoPackage) loads without a name.
- **Database tables/views:** `load @conn.table` / `load @conn.schema.table`; run a
  view or an ad-hoc query with `sql @conn "SELECT …"`.

> **Save caveat (v1):** today each `save <file>` writes **one** layer, named from
> the file (so `save out.gpkg` → a layer `out`). Writing several layers *into one*
> GeoPackage (an `as <layer>` name / `append`) is designed (03-§2.5) but not yet
> implemented — for now use one output file per layer, or a database connection.

## Verb aliases (registry → `native:*`)

The verbose original QGIS signature is the **last** column so the niva signature
and status stay visible without scrolling.

| niva verb | algorithm | niva signature | status | original QGIS signature |
|-----------|-----------|----------------|--------|-------------------------|
| `aspect` | `gdal:aspect` | `aspect [trig] [zero_flat] [band=int]` | ✅ | INPUT(raster), BAND(band)=1, TRIG_ANGLE(boolean)=False, ZERO_FLAT(boolean)=False, COMPUTE_EDGES(boolean)=False, ZEVENBERGEN(boolean)=False, OPTIONS(string)=?, CREATION_OPTIONS(string)=?, EXTRA(string)?, OUTPUT(rasterDestination) → OUTPUT(outputRaster) |
| `boundingbox` | `native:boundingboxes` | `boundingbox` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `buffer` | `native:buffer` | `buffer <distance> [dissolve] [separate] [segments=int] [cap=round/flat/square] [join=round/miter/bevel] [miter=number]` | ✅ | INPUT(source), DISTANCE(distance)=10, SEGMENTS(number)=5, END_CAP_STYLE(enum)=0, JOIN_STYLE(enum)=0, MITER_LIMIT(number)=2, DISSOLVE(boolean)=False, SEPARATE_DISJOINT(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) |
| `centroid` | `native:centroids` | `centroid` | ✅ | INPUT(source), ALL_PARTS(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) |
| `clip` | `native:clip` | `clip <overlay>` | ✅ | INPUT(source), OVERLAY(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `clipraster` | `gdal:cliprasterbymasklayer` | `clipraster <mask> [nodata=number]` | ✅ | INPUT(raster), MASK(source), SOURCE_CRS(crs)?, TARGET_CRS(crs)?, TARGET_EXTENT(extent)?, NODATA(number)?, ALPHA_BAND(boolean)=False, CROP_TO_CUTLINE(boolean)=True, KEEP_RESOLUTION(boolean)=False, SET_RESOLUTION(boolean)=False, X_RESOLUTION(number)?, Y_RESOLUTION(number)?, MULTITHREADING(boolean)=False, OPTIONS(string)=?, CREATION_OPTIONS(string)=?, DATA_TYPE(enum)=0, EXTRA(string)?, OUTPUT(rasterDestination) → OUTPUT(outputRaster) |
| `collect` | `native:collect` | `collect [field]` | ✅ | INPUT(source), FIELD(field)?, OUTPUT(sink) → OUTPUT(outputVector) |
| `convexhull` | `native:convexhull` | `convexhull` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `countpoints` | `native:countpointsinpolygon` | `countpoints points=layer [field=string] [weight=field] [classfield=field]` | ✅ | POLYGONS(source), POINTS(source), WEIGHT(field)?, CLASSFIELD(field)?, FIELD(string)=NUMPOINTS, OUTPUT(sink) → OUTPUT(outputVector) |
| `delaunay` | `native:delaunaytriangulation` | `delaunay` | ✅ | INPUT(source), TOLERANCE(number)=0?, ADD_ATTRIBUTES(boolean)=True, OUTPUT(sink) → OUTPUT(outputVector) |
| `densify` | `native:densifygeometriesgivenaninterval` | `densify <interval>` | ✅ | INPUT(source), INTERVAL(distance)=1, OUTPUT(sink) → OUTPUT(outputVector) |
| `difference` | `native:difference` | `difference <overlay>` | ✅ | INPUT(source), OVERLAY(source), OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) |
| `dissolve` | `native:dissolve` | `dissolve [field] [separate]` | ✅ | INPUT(source), FIELD(field)?, SEPARATE_DISJOINT(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) |
| `dropfields` | `native:deletecolumn` | `dropfields <fields>` | ✅ | INPUT(source), COLUMN(field), OUTPUT(sink) → OUTPUT(outputVector) |
| `explode` | `native:multiparttosingleparts` | `explode` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `filter` | `native:extractbyexpression` | `filter <expression>` | ✅ | INPUT(source), EXPRESSION(expression), OUTPUT(sink), FAIL_OUTPUT(sink)? → OUTPUT(outputVector), FAIL_OUTPUT(outputVector) |
| `fix` | `native:fixgeometries` | `fix` | ✅ | INPUT(source), METHOD(enum)=1, OUTPUT(sink) → OUTPUT(outputVector) |
| `forcerhr` | `native:forcerhr` | `forcerhr` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `hillshade` | `native:hillshade` | `hillshade [z_factor=number] [azimuth=number] [altitude=number]` | ✅ | INPUT(raster), Z_FACTOR(number)=1.0, AZIMUTH(number)=300, V_ANGLE(number)=40, NODATA(number)=-9999.0, CREATION_OPTIONS(string)?, OUTPUT(rasterDestination) → OUTPUT(outputRaster) |
| `intersect` | `native:intersection` | `intersect <overlay>` | ✅ | INPUT(source), OVERLAY(source), INPUT_FIELDS(field)?, OVERLAY_FIELDS(field)?, OVERLAY_FIELDS_PREFIX(string)?, OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) |
| `join` | `native:joinattributestable` | `join [discard] with=layer field=field field2=field [fields=fields] [prefix=string] [method=one-to-many/one-to-one] [unmatched=string]` | ✅ | INPUT(source), FIELD(field), INPUT_2(source), FIELD_2(field), FIELDS_TO_COPY(field)?, METHOD(enum)=1, DISCARD_NONMATCHING(boolean)=False, PREFIX(string)?, OUTPUT(sink)?, NON_MATCHING(sink)? → OUTPUT(outputVector), NON_MATCHING(outputVector), JOINED_COUNT(outputNumber), UNJOINABLE_COUNT(outputNumber) |
| `keepfields` | `native:retainfields` | `keepfields <fields>` | ✅ | INPUT(source), FIELDS(field), OUTPUT(sink) → OUTPUT(outputVector) |
| `minrect` | `native:orientedminimumboundingbox` | `minrect` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `offset` | `native:offsetline` | `offset <distance> [segments=int] [join=round/miter/bevel] [miter=number]` | ✅ | INPUT(source), DISTANCE(distance)=10.0, SEGMENTS(number)=8, JOIN_STYLE(enum)=0, MITER_LIMIT(number)=2, OUTPUT(sink) → OUTPUT(outputVector) |
| `pointonsurface` | `native:pointonsurface` | `pointonsurface [all_parts]` | ✅ | INPUT(source), ALL_PARTS(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) |
| `pointsalong` | `native:pointsalonglines` | `pointsalong <distance> [start=distance] [end=distance]` | ✅ | INPUT(source), DISTANCE(distance)=1.0, START_OFFSET(distance)=0.0, END_OFFSET(distance)=0.0, OUTPUT(sink) → OUTPUT(outputVector) |
| `polygonize` | `gdal:polygonize` | `polygonize [eight] [band=int] [field=string]` | ✅ | INPUT(raster), BAND(band)=1, FIELD(string)=DN, EIGHT_CONNECTEDNESS(boolean)=False, EXTRA(string)?, OUTPUT(vectorDestination) → OUTPUT(outputVector) |
| `promote` | `native:promotetomulti` | `promote` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `renamefield` | `native:renametablefield` | `renamefield <field> <name>` | ✅ | INPUT(source), FIELD(field), NEW_NAME(string), OUTPUT(sink) → OUTPUT(outputVector) |
| `reproject` | `native:reprojectlayer` | `reproject <target_crs> [convert_curved] [transform_z] [operation=string]` | ✅ | INPUT(source), TARGET_CRS(crs)=EPSG:4326, CONVERT_CURVED_GEOMETRIES(boolean)=False, TRANSFORM_Z(boolean)=False, OPERATION(coordinateoperation)?, OUTPUT(sink) → OUTPUT(outputVector) |
| `sample` | `native:randomextract` | `sample <number> [method=count/percent]` | ✅ | INPUT(source), METHOD(enum)=0, NUMBER(number)=10, OUTPUT(sink) → OUTPUT(outputVector) |
| `selectloc` | `native:extractbylocation` | `selectloc <against> [predicate=intersect/contain/disjoint/equal/touch/overlap/within/cross]` | ✅ | INPUT(source), PREDICATE(enum)=[0], INTERSECT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `simplify` | `native:simplifygeometries` | `simplify <tolerance> [method=douglas/grid/area]` | ✅ | INPUT(source), METHOD(enum)=0, TOLERANCE(distance)=1.0, OUTPUT(sink) → OUTPUT(outputVector) |
| `slope` | `gdal:slope` | `slope [percent] [band=int] [scale=number]` | ✅ | INPUT(raster), BAND(band)=1, SCALE(number)=1.0, AS_PERCENT(boolean)=False, COMPUTE_EDGES(boolean)=False, ZEVENBERGEN(boolean)=False, OPTIONS(string)=?, CREATION_OPTIONS(string)=?, EXTRA(string)?, OUTPUT(rasterDestination) → OUTPUT(outputRaster) |
| `smooth` | `native:smoothgeometry` | `smooth [iterations=int] [offset=number] [max_angle=number]` | ✅ | INPUT(source), ITERATIONS(number)=1, OFFSET(number)=0.25, MAX_ANGLE(number)=180.0, OUTPUT(sink) → OUTPUT(outputVector) |
| `snap` | `native:snapgeometries` | `snap <reference> <tolerance> [behavior=align/closest/align-keep/closest-keep/ends-align/ends-closest/ends-only/anchor]` | ✅ | INPUT(source), REFERENCE_LAYER(source), TOLERANCE(distance)=10.0, BEHAVIOR(enum)=[0], OUTPUT(sink) → OUTPUT(outputVector) |
| `spatialjoin` | `native:joinattributesbylocation` | `spatialjoin [discard] with=layer [predicate=intersect/contain/equal/touch/overlap/within/cross] [method=one-to-many/first/largest] [fields=fields] [prefix=string]` | ✅ | INPUT(source), PREDICATE(enum)=0, JOIN(source), JOIN_FIELDS(field)?, METHOD(enum)=0, DISCARD_NONMATCHING(boolean)=False, PREFIX(string)?, OUTPUT(sink)?, NON_MATCHING(sink)? → OUTPUT(outputVector), NON_MATCHING(outputVector), JOINED_COUNT(outputNumber) |
| `subdivide` | `native:subdivide` | `subdivide [max_nodes=int]` | ✅ | INPUT(source), MAX_NODES(number)=256, OUTPUT(sink) → OUTPUT(outputVector) |
| `swapxy` | `native:swapxy` | `swapxy` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `symdifference` | `native:symmetricaldifference` | `symdifference <overlay>` | ✅ | INPUT(source), OVERLAY(source), OVERLAY_FIELDS_PREFIX(string)?, OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) |
| `union` | `native:union` | `union [overlay]` | ✅ | INPUT(source), OVERLAY(source)?, OVERLAY_FIELDS_PREFIX(string)?, OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) |
| `vertices` | `native:extractvertices` | `vertices` | ✅ | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) |
| `voronoi` | `native:voronoipolygons` | `voronoi [buffer=number]` | ✅ | INPUT(source), BUFFER(number)=0, TOLERANCE(number)=0?, COPY_ATTRIBUTES(boolean)=True, OUTPUT(sink) → OUTPUT(outputVector) |
| `warp` | `gdal:warpreproject` | `warp <target_crs> [source_crs=crs] [resampling=nearest/bilinear/cubic/cubicspline/lanczos/average/mode/max/min/median/q1/q3] [nodata=number] [resolution=number]` | ✅ | INPUT(raster), SOURCE_CRS(crs)?, TARGET_CRS(crs)?, RESAMPLING(enum)=0, NODATA(number)?, TARGET_RESOLUTION(number)?, OPTIONS(string)=?, CREATION_OPTIONS(string)=?, DATA_TYPE(enum)=0, TARGET_EXTENT(extent)?, TARGET_EXTENT_CRS(crs)?, MULTITHREADING(boolean)=False, EXTRA(string)?, OUTPUT(rasterDestination) → OUTPUT(outputRaster) |
| `zonalstats` | `native:zonalstatisticsfb` | `zonalstats [band=int] raster=raster [stats=count/sum/mean/median/stdev/min/max/range/minority/majority/variety/variance] [prefix=string]` | ✅ | INPUT(source), INPUT_RASTER(raster), RASTER_BAND(band)=1, COLUMN_PREFIX(string)=_, STATISTICS(enum)=[0, 1, 2], OUTPUT(sink) → OUTPUT(outputVector) |

## The long tail: reaching any algorithm with `run`

The aliases above are the *curated* verbs. But QGIS installs hundreds more algorithms — **769** in this build — across providers (native, gdal, grass,
pdal, qgis, 3d). **You do not need a niva alias to use any of them.** The `run`
verb takes an algorithm id and its parameters directly:

- Find the id and its parameters with **`describe <id>`** (e.g. `niva describe native:slope`).
- niva **auto-fills two things** so you usually omit them: `INPUT` (the layer coming down the pipe) and `OUTPUT` (a temporary result that flows to the next
  stage). Pass an explicit `OUTPUT=path` to write a file directly — needed for raster outputs, which `save` does not handle yet.
- Everything else is `KEY=value`, exactly as QGIS names the parameters (see the `describe` output or the *original signature* column above).

So a curated alias is just sugar over `run` — these are equivalent:

```
buffer 100m segments=8                  # curated alias
run native:buffer DISTANCE=100 SEGMENTS=8   # the raw escape hatch
```

### Examples — native algorithms with no curated alias yet

- **Convex hull around one layer of a multi-layer GeoPackage** (`native:convexhull`):

  ```
  load "city.gpkg|layername=trees" | run native:convexhull | save hull.gpkg
  ```

- **Simplify geometry (Douglas–Peucker)** (`native:simplifygeometries`):

  ```
  load roads.gpkg | run native:simplifygeometries METHOD=0 TOLERANCE=15 | save simple.gpkg
  ```

- **Smooth lines/polygons** (`native:smoothgeometry`):

  ```
  load roads.gpkg | run native:smoothgeometry ITERATIONS=3 OFFSET=0.25 MAX_ANGLE=180 | save smooth.gpkg
  ```

- **Place points spaced along lines** (`native:pointsalonglines`):

  ```
  load route.gpkg | run native:pointsalonglines DISTANCE=50 START_OFFSET=0 END_OFFSET=0 | save stops.gpkg
  ```

- **Keep features by spatial relation to another layer (PREDICATE 0 = intersects)** (`native:extractbylocation`):

  ```
  load buildings.gpkg | run native:extractbylocation PREDICATE=0 INTERSECT=floodzone.gpkg | save at_risk.gpkg
  ```

- **Add a computed field (FORMULA is a QGIS expression)** (`native:fieldcalculator`):

  ```
  load parcels.gpkg | run native:fieldcalculator FIELD_NAME=area_m2 FIELD_TYPE=0 FIELD_LENGTH=12 FIELD_PRECISION=2 FORMULA="$area" | save out.gpkg
  ```

- **Sample raster values at point locations** (`native:rastersampling`):

  ```
  load pts.gpkg | run native:rastersampling RASTERCOPY=dem.tif | save sampled.gpkg
  ```

- **Slope raster from a DEM — raster output, so give an explicit OUTPUT path** (`native:slope`):

  ```
  run native:slope INPUT=dem.tif Z_FACTOR=1 NODATA=-9999 OUTPUT=slope.tif
  ```

- **Count points in each polygon — two explicit inputs, no pipe** (`native:countpointsinpolygon`):

  ```
  run native:countpointsinpolygon POLYGONS=zones.gpkg POINTS=incidents.gpkg FIELD=n OUTPUT=counts.gpkg
  ```

Browse everything in your install with `niva describe <id>`. Database geoprocessing (SpatiaLite/PostGIS) is reachable via `sql @conn "…"`.

## Proof: ten complex `run`-only pipelines (verified on real data)

These are the receipts for the Oscar verdict below: ten **multi-stage pipelines
that use only built-ins + `run` — zero curated aliases** — each **executed against
the marimo_qgis Youngstown dataset** (`example.gpkg`, 24 layers; QGIS 4.0.3) with
the output feature count recorded. (`run`-only means even `buffer`/`clip`/etc. are
spelled as `run native:…`, proving the escape hatch alone is enough for real work.)

**1. Building footprint — reproject → fix → buffer+dissolve**

```
load "example.gpkg|layername=ny_ytown_buildings"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:fixgeometries
  | run native:buffer DISTANCE=15 DISSOLVE=true
  | save footprint.gpkg
```
→ verified: **1 dissolved polygon**.

**2. Convex hull of all parcels inside town — reproject → clip → dissolve → hull**

```
load "example.gpkg|layername=parcels"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:fixgeometries
  | run native:clip OVERLAY="example.gpkg|layername=ny_youngstown"
  | run native:dissolve
  | run native:convexhull
  | save hull.gpkg
```
→ verified: **1 hull**.

**3. 100 m service areas around named places — reproject → buffer → dissolve**

```
load "example.gpkg|layername=gnis"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:buffer DISTANCE=100
  | run native:dissolve
  | save service_areas.gpkg
```
→ verified: **1 merged area**.

**4. Street segments — reproject → simplify → explode to single parts**

```
load "example.gpkg|layername=ny_ytown_streets"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:simplifygeometries METHOD=0 TOLERANCE=5
  | run native:multiparttosingleparts
  | save street_segments.gpkg
```
→ verified: **214 segments**.

**5. Large parcels — add an area field, then filter by it**

```
load "example.gpkg|layername=parcels"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:fixgeometries
  | run native:fieldcalculator FIELD_NAME=area_m2 FIELD_TYPE=0 FIELD_LENGTH=12 FIELD_PRECISION=2 FORMULA="$area"
  | run native:extractbyexpression EXPRESSION="area_m2 > 2000"
  | save big_parcels.gpkg
```
→ verified: **1346 of 2790 parcels**.

**6. Building centroids inside town — spatial extract → centroids**

```
load "example.gpkg|layername=ny_ytown_buildings"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:fixgeometries
  | run native:extractbylocation PREDICATE=0 INTERSECT="example.gpkg|layername=ny_youngstown"
  | run native:centroids
  | save centroids.gpkg
```
→ verified: **497 centroids**.

**7. Count named places per parcel — two explicit inputs, no pipe**

```
run native:countpointsinpolygon POLYGONS="example.gpkg|layername=parcels" \
    POINTS="example.gpkg|layername=gnis" FIELD=n_names
  | save parcels_counted.gpkg
```
→ verified: **2790 parcels (with a count column)**.

**8. Open land — parcels minus building footprints (difference)**

```
load "example.gpkg|layername=parcels"
  | run native:fixgeometries
  | run native:difference OVERLAY="example.gpkg|layername=ny_ytown_buildings"
  | save open_land.gpkg
```
→ verified: **2761 features**.

**9. Sample points every 100 m along the street network**

```
load "example.gpkg|layername=ny_ytown_streets"
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:multiparttosingleparts
  | run native:pointsalonglines DISTANCE=100 START_OFFSET=0 END_OFFSET=0
  | save sample_points.gpkg
```
→ verified: **478 points**.

**10. Wandering-cat territory — run-only, with provenance (metadata + assess)**

```
load wandering_cat.shp
  | run native:reprojectlayer TARGET_CRS=EPSG:26918
  | run native:buffer DISTANCE=50 DISSOLVE=true
  | metadata set title="Cat territory (run-only)" keywords=cat
  | assess to cat.md
  | save cat_territory.gpkg
```
→ verified: **1 polygon + a quality report + lineage**.

Also run end-to-end as a raster, cross-provider example: `run gdal:merge` (13 DEM tiles → one raster) then `run gdal:cliprasterbymasklayer` (clip to an Area-of-Interest) — see `build_ytown_dem.niva`. Both `gdal:` algorithms, no alias.

## Does `run` meet Oscar's bar?

> Oscar's bar (`Oscar_the_Grouch.md` §12): **"Success = built, works on real
> data, released, AND actually used."** Oscar's Top-7 failure modes #6 and #7 are
> *registry rot* and *scope-creep / bus-factor-of-one*.

The `run` escape hatch is the design choice that lets niva be **complete** — every
installed algorithm (769 here) reachable — *without* aliasing them all. That is
exactly what defuses the failure modes Oscar fears most:

- **Registry rot — Top-7 #6 / A4 (🟥):** *"769 algorithms × every QGIS release
  quietly breaks aliases."* The long tail reached via `run` has **no aliases to
  rot** — `run` resolves the id against the *live* installed registry and `describe`
  reads the *live* signature; nothing about the tail is hardcoded. Only the curated
  aliases need the linter. → **eliminated for the tail.**
- **Scope creep / bus-factor — Top-7 #7 / P5 (🟧):** *"a giant registry maintained
  by one tired person never ships or rots."* niva ships **complete with a dozen
  aliases**; the maintainer never has to chase the whole surface. → **makes the solo
  project viable.**
- **Type-system coverage gaps — C6 (🟧):** Oscar's *own* mitigation names this verb
  ("`run id KEY=value` reaches them raw"). Exotic param types (matrix, datetime,
  multilayer, coordinate-operation…) are reachable directly. → **no algorithm is
  unreachable for lack of a niva type.**
- **Multi-output loss — C7 (🟨):** secondary outputs are reachable by naming them in
  `run` (and `join`'s `NON_MATCHING` is now a first-class `unmatched=` option). ✅
- **Testing the 769-surface — C14 (🟧):** *"hopeless."* `run` is **one** tested
  engine path (INPUT/OUTPUT auto-fill, scalar coercion, failure → `OpError`) — you
  test the *path*, not 769 algorithms. ✅ unit-tested + a real `run native:centroids`
  in the integration suite.
- **Loaded gun / injection — C5 (🟧):** `run` builds a parameter **dict** for
  `processing.run` — no shell, no string-built SQL, paths passed verbatim. No
  injection surface (security model §12).
- **Install can break QGIS — E1 (🟥):** `run` calls QGIS's *own* `processing` — it
  adds **no dependency**. Consistent with niva's `dependencies = []` rule.
- **The escape hatch is a cliff — U2 / Top-7 #5 (🟥), the honest one:** *"`run
  native:slope INPUT=… RESAMPLING=1` is the exact misery niva sold you away from."*
  Oscar calls this **inherent**; `run` can only *soften* it — and does, three ways:
  (1) `describe <id>` surfaces every parameter so you don't guess; (2) niva auto-fills
  `INPUT`/`OUTPUT` so you write only the algorithm-specific params; (3) values are
  scalar-coerced so `RESAMPLING=1` just works. Curated aliases keep you off the cliff
  for common work. → **mitigated, not eliminated — and labelled as such.**

**Verdict.** Against Oscar's bar, `run` is **built, tested, and proven on real data**
— see the **ten verified `run`-only pipelines above** (plus the DEM raster build),
every one executed against the Youngstown dataset with recorded results. It converts
two of Oscar's Top-7 existential risks
(#6 rot, #7 scope) into negligible ones, and softens the third (#5 cliff) as far as
Oscar concedes is possible — while adding zero dependencies and zero new attack
surface. The one thing `run` cannot buy is *actually used* (M1); that is for users,
not the escape hatch.

