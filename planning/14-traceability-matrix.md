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
| `load` | `load <path>` or `load @conn[.schema].table` | QgsVectorLayer / QgsRasterLayer; provider-connection `tableUri` for `@conn` | ✅ |
| `save` | `save <path>` | QgsVectorFileWriter (driver by extension) + metadata/lineage persistence | ✅ |
| `sql` | `sql @conn "<query>"` | QgsAbstractDatabaseProviderConnection.createSqlVectorLayer | ✅ |
| `run` | `run <algorithm-id> KEY=value …` | processing.run (raw escape hatch; scalar-coerced params) | ✅ |
| `call` | `call <file.niva>` | engine file composition (relative resolve, cycle-checked) | ✅ |
| `metadata` | `metadata set key=value …` | QgsLayerMetadata setters (title/abstract/keywords/identifier/license), persisted on save | ✅ |
| `assess` | `assess [deep] to <report.md>` | QgsVectorLayer/QgsRasterLayer introspection → markdown; `deep` adds validity/empty/duplicate/null | ✅ |
| `describe` | `describe <verb-or-algorithm-id>` (CLI/API, not a flow stage) | registry + Processing registry introspection | ✅ |

Auto-lineage: every `save` records the flow's stages into the output's
`QgsLayerMetadata.history` (prefixed `niva: `) — no verb required.

## Verb aliases (registry → `native:*`)

| niva verb | algorithm | original QGIS signature | niva signature | status |
|-----------|-----------|-------------------------|----------------|--------|
| `buffer` | `native:buffer` | INPUT(source), DISTANCE(distance)=10, SEGMENTS(number)=5, END_CAP_STYLE(enum)=0, JOIN_STYLE(enum)=0, MITER_LIMIT(number)=2, DISSOLVE(boolean)=False, SEPARATE_DISJOINT(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) | `buffer <distance> [dissolve] [separate] [segments=int] [cap=round/flat/square] [join=round/miter/bevel] [miter=number]` | ✅ |
| `centroid` | `native:centroids` | INPUT(source), ALL_PARTS(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) | `centroid` | ✅ |
| `clip` | `native:clip` | INPUT(source), OVERLAY(source), OUTPUT(sink) → OUTPUT(outputVector) | `clip <overlay>` | ✅ |
| `difference` | `native:difference` | INPUT(source), OVERLAY(source), OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) | `difference <overlay>` | ✅ |
| `dissolve` | `native:dissolve` | INPUT(source), FIELD(field)?, SEPARATE_DISJOINT(boolean)=False, OUTPUT(sink) → OUTPUT(outputVector) | `dissolve [field] [separate]` | ✅ |
| `explode` | `native:multiparttosingleparts` | INPUT(source), OUTPUT(sink) → OUTPUT(outputVector) | `explode` | ✅ |
| `filter` | `native:extractbyexpression` | INPUT(source), EXPRESSION(expression), OUTPUT(sink), FAIL_OUTPUT(sink)? → OUTPUT(outputVector), FAIL_OUTPUT(outputVector) | `filter <expression>` | ✅ |
| `fix` | `native:fixgeometries` | INPUT(source), METHOD(enum)=1, OUTPUT(sink) → OUTPUT(outputVector) | `fix` | ✅ |
| `intersect` | `native:intersection` | INPUT(source), OVERLAY(source), INPUT_FIELDS(field)?, OVERLAY_FIELDS(field)?, OVERLAY_FIELDS_PREFIX(string)?, OUTPUT(sink), GRID_SIZE(number)? → OUTPUT(outputVector) | `intersect <overlay>` | ✅ |
| `join` | `native:joinattributestable` | INPUT(source), FIELD(field), INPUT_2(source), FIELD_2(field), FIELDS_TO_COPY(field)?, METHOD(enum)=1, DISCARD_NONMATCHING(boolean)=False, PREFIX(string)?, OUTPUT(sink)?, NON_MATCHING(sink)? → OUTPUT(outputVector), NON_MATCHING(outputVector), JOINED_COUNT(outputNumber), UNJOINABLE_COUNT(outputNumber) | `join [discard] with=layer field=field field2=field [fields=fields] [prefix=string] [method=one-to-many/one-to-one]` | ✅ |
| `reproject` | `native:reprojectlayer` | INPUT(source), TARGET_CRS(crs)=EPSG:4326, CONVERT_CURVED_GEOMETRIES(boolean)=False, TRANSFORM_Z(boolean)=False, OPERATION(coordinateoperation)?, OUTPUT(sink) → OUTPUT(outputVector) | `reproject <target_crs> [operation=string]` | ✅ |
| `zonalstats` | `native:zonalstatisticsfb` | INPUT(source), INPUT_RASTER(raster), RASTER_BAND(band)=1, COLUMN_PREFIX(string)=_, STATISTICS(enum)=[0, 1, 2], OUTPUT(sink) → OUTPUT(outputVector) | `zonalstats [band=int] raster=raster [stats=count/sum/mean/median/stdev/min/max/range/minority/majority/variety/variance] [prefix=string]` | ✅ |

## The long tail (reachable, no alias needed)

All **769** algorithms in the installed QGIS Processing registry (native, gdal,
grass, pdal, qgis, 3d, …) are reachable today via the `run <id> KEY=value` escape
hatch (status: ✅), with `describe <id>` to surface each one's signature. Curated
aliases are added to the table above as they are promoted from the long tail.
Database geoprocessing (SpatiaLite/PostGIS) is reachable via `sql @conn "…"`.

