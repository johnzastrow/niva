# niva Cookbook

Over a hundred worked recipes, from a single transform to full pipelines — including a large
block of spatial **SQL** for both **SpatiaLite** and **PostGIS**, data **discovery** with
`find` and `catalog`, plus a closing tour that reaches **every QGIS provider** (GDAL, GRASS,
QGIS, PDAL, native, 3D) through the `run` escape hatch.
Pair this with the [Reference](reference.md) for exact signatures and the
[User Guide](user-guide.md) for setup.

**Conventions**
- Replace file paths, layer names, CRS codes, and SQL table/column names with your own.
- A multi-layer GeoPackage layer is addressed as `"file.gpkg|layername=<layer>"`.
- `@name` is a **saved QGIS database connection** (set up in the QGIS Browser or the plugin
  Setup tab) — SpatiaLite or PostGIS. Credentials live in QGIS, never in the flow.
- SQL column names below (`geom`, `geometry`, `id`, …) are illustrative — match your schema.
- Run any recipe with `niva "…"`, `niva run file.niva`, or the plugin Flow tab. Add
  `--dry-run` to validate without touching data.

---

## A. First steps — one transform

**1. Buffer a layer**
```
load roads.gpkg | buffer 100m | save roads_buf.gpkg
```
Distances take a unit (`m`, `km`, `ft`, …); with no unit they're in the layer's CRS units.

**2. Buffer and merge overlaps**
```
load wells.gpkg | buffer 1km dissolve | save well_zones.gpkg
```
`dissolve` merges the overlapping buffers into one feature.

**3. Reproject to another CRS**
```
load parcels.shp | reproject EPSG:2262 | save parcels_spcs.gpkg
```

**4. Clip to an area of interest**
```
load buildings.gpkg | clip aoi.gpkg | save buildings_aoi.gpkg
```

**5. Keep only matching features (attribute filter)**
```
load parcels.gpkg | filter "zoning = 'R1'" | save residential.gpkg
```
The expression is a QGIS expression — quote it.

**6. Repair invalid geometries**
```
load messy.shp | fixgeom | save clean.gpkg
```

**7. Reduce a layer to centroids**
```
load parcels.gpkg | centroid | save parcel_points.gpkg
```

---

## B. Multi-step chains

**8. Filter → reproject → buffer**
```
load roads.gpkg | filter "class = 'primary'" | reproject EPSG:2262 | buffer 100m dissolve | save corridors.gpkg
```

**9. Reproject → fixgeom → buffer with options**
```
load buildings.gpkg | reproject EPSG:26918 | fixgeom | buffer 15m dissolve cap=flat segments=12 | save footprints.gpkg
```

**10. Clip → fixgeom → dissolve**
```
load parcels.gpkg | clip township.gpkg | fixgeom | dissolve zoning | save zoning_blocks.gpkg
```

**11. Simplify then split to single parts**
```
load streets.gpkg | reproject EPSG:26918 | simplify 5m method=area | explode | save street_segments.gpkg
```

**12. Stamp metadata and assess in one pass**
```
load wells.gpkg | metadata set title="Monitoring wells" keywords="wells,gw" | assess deep to docs/wells_quality.md | save wells.gpkg
```
`metadata` and `assess` are pass-through, so the chain still ends at `save`.

---

## C. Attributes, fields & joins

**13. Keep only the fields you need**
```
load parcels.gpkg | keepfields owner,zoning,area | save parcels_slim.gpkg
```

**14. Drop fields / rename a field**
```
load parcels.gpkg | dropfields temp1,temp2 | renamefield zoning zone_code | save parcels.gpkg
```

**15. Attribute join from a table**
```
load homes.gpkg | join with=census.csv field=tract field2=GEOID fields=pop,income prefix=cen_ | save homes_enriched.gpkg
```

**16. Join, keeping only matches**
```
load homes.gpkg | join with=owners.gpkg field=parcel_id field2=pid discard | save owned_homes.gpkg
```
`discard` drops input rows that found no match.

**17. Count points inside each polygon**
```
run native:countpointsinpolygon POLYGONS=parcels.gpkg POINTS=trees.gpkg FIELD=n_trees | save parcels_treecount.gpkg
```
`countpoints` takes both layers as options, so call it without a piped input.

---

## D. Overlay & spatial selection

**18. Intersection of two layers**
```
load parcels.gpkg | intersect floodzone.gpkg | save parcels_in_flood.gpkg
```

**19. Difference (erase)**
```
load parcels.gpkg | fixgeom | difference buildings.gpkg | save open_land.gpkg
```

**20. Select by location (spatial filter)**
```
load buildings.gpkg | selectloc floodzone.gpkg predicate=intersect,within | save at_risk.gpkg
```

**21. Spatial join — attach attributes by location**
```
load incidents.gpkg | spatialjoin with=districts.gpkg predicate=within method=first fields=district_name | save incidents_tagged.gpkg
```

**22. Zonal statistics (raster × polygons)**
```
load watersheds.gpkg | zonalstats raster=dem.tif stats=mean,min,max prefix=elev_ | save watersheds_elev.gpkg
```

---

## E. Batch processing with `each`

**23. Reproject every file in a folder into one GeoPackage**
```
each "in/*.shp" | reproject EPSG:6346 | save out.gpkg
```
Each input becomes its own layer inside `out.gpkg` (named after the file).

**24. Process every layer of a multi-layer GeoPackage**
```
each "basemap.gpkg" | fixgeom | clip aoi.gpkg | save basemap_clip.gpkg
```

**25. Recurse a directory tree**
```
each "data/" | reproject EPSG:6346 | save collected.gpkg
```

**26. Per-item output files with `{name}`**
```
each "rasters/*.tif" | warp EPSG:6346 | save "warped/{name}.tif"
```

**27. Batch-load a folder into a PostGIS schema (one table per file)**
```
each "deliverables/" | reproject EPSG:6346 | save @pg.staging
```
A trailing qualifier on a batch DB save is the **schema** (`staging`); each layer becomes a
table there.

**28. Filter the batch — only the datasets that match**
```
each "data/**/*.gpkg" geom=polygon minfeatures=1 | dissolve | save merged.gpkg
each "tiles/*.tif" newerthan=7d | hillshade | save "out/{name}.tif"
```
`each` takes the same filters as `niva find` (flat `option=value`): offline `ext` / `minsize`
/ `maxsize` / `newerthan` / `format`, and — on QGIS's Python — `geom` / `crs` / `minfeatures`
/ `maxfeatures` / `hasfield`.

**29. Pipe `find` into other tools (non-niva)**
```
niva find "*.gpkg" in ~/data --paths > inventory.txt      # a plain file list
niva find "*.tif" in ~/data --paths | wc -l               # count them
niva find "*.shp" in ~/data -0 | xargs -0 -n1 ogrinfo -so # feed any CLI, spaces-safe
```
`--paths` prints just the absolute paths (one per line, nothing else); `-0` NUL-separates
them for `xargs -0`. Use `--as-flow` instead when you want a runnable `each …` skeleton.

---

## F. Raster & terrain

**30. Reproject (warp) a raster**
```
load dem.tif | warp EPSG:6346 | save dem_utm.tif
```

**31. Warp and resample to a target pixel size**
```
load ortho.tif | warp EPSG:6346 resolution=5 resampling=average | save ortho_5m.tif
```
`average` is the right resampler when down-sampling imagery.

**32. Clip a raster to a mask layer**
```
load dem.tif | clipraster aoi.gpkg | save dem_aoi.tif
```

**33. Hillshade from a DEM**
```
load dem.tif | hillshade z_factor=2 azimuth=315 altitude=45 | save hillshade.tif
```

**34. Slope (in percent) and aspect**
```
load dem.tif | slope percent | save slope_pct.tif
load dem.tif | aspect | save aspect.tif
```

**35. Vectorise a classified raster**
```
load landcover.tif | polygonize field=class | save landcover_zones.gpkg
```

---

## G. Spatial SQL in SpatiaLite

These use a saved **SpatiaLite** connection `@sl`. A `SELECT`/`WITH` returns a layer you can
pipe; anything else runs in the database. Adjust table/column/geometry names to your schema
(SpatiaLite geometry columns are often `geometry` or `geom`).

**36. Read a filtered subset as a layer**
```
sql @sl "SELECT * FROM parcels WHERE zoning = 'R1'" | save residential.gpkg
```

**37. Filter by a spatial measure**
```
sql @sl "SELECT id, zoning, geometry FROM parcels WHERE ST_Area(geometry) > 2000" | save big_parcels.gpkg
```

**38. Compute geometry server-side, then keep processing in niva**
```
sql @sl "SELECT id, ST_Buffer(geometry, 50) AS geometry FROM wells" | reproject EPSG:6346 | save well_buffers.gpkg
```

**39. Spatial join — points within polygons**
```
sql @sl "SELECT p.id, z.zone, p.geometry FROM points p JOIN zones z ON ST_Within(p.geometry, z.geometry)" | save points_zoned.gpkg
```

**40. Aggregate to an attribute table**
```
sql @sl "SELECT zoning, COUNT(*) AS n, SUM(ST_Area(geometry)) AS total_area FROM parcels GROUP BY zoning" | save zoning_summary.gpkg
```

**41. Dissolve by attribute with `ST_Union`**
```
sql @sl "SELECT zoning, ST_Union(geometry) AS geometry FROM parcels GROUP BY zoning" | save zoning_dissolved.gpkg
```

**42. CTE, then hand off to a niva verb**
```
sql @sl "WITH big AS (SELECT * FROM parcels WHERE ST_Area(geometry) > 5000) SELECT * FROM big" | centroid | save big_centroids.gpkg
```

---

## H. Spatial SQL in PostGIS

These use a saved **PostGIS** connection `@pg`. Reads (`SELECT`/`WITH`) return a pipeable
layer; writes (`CREATE`/`UPDATE`/`INSERT`/`CREATE INDEX`/…) run server-side and end the flow.

**43. Read a table (schema-qualified)**
```
load @pg.public.roads | save roads_local.gpkg
```
Equivalent read via SQL: `sql @pg "SELECT * FROM public.roads" | save roads_local.gpkg`.

**44. Filter in the database, finish in niva**
```
sql @pg "SELECT * FROM roads WHERE class = 'primary'" | buffer 50m dissolve | save primary_corridors.gpkg
```

**45. Do the spatial work in SQL (the server-side lever)**
```
sql @pg "SELECT id, ST_Buffer(geom, 100) AS geom FROM homes WHERE has_cat AND NOT has_dog" | save targets.gpkg
```

**46. Cross-table spatial join**
```
sql @pg "SELECT a.id, a.geom FROM parcels a JOIN flood b ON ST_Intersects(a.geom, b.geom)" | save parcels_at_risk.gpkg
```

**47. Write a niva result back into PostGIS**
```
load parcels.gpkg | clip aoi.gpkg | save @pg.public.parcels_clip mode=replace
```
`mode=create` (default) refuses to overwrite; `replace` drops + recreates; `append` inserts.

**48. Analyse-in-place: materialise a derived table**
```
sql @pg "CREATE TABLE roads_buf AS SELECT id, ST_Buffer(geom, 100) AS geom FROM roads"
```
A leading `CREATE` routes server-side (terminal) — even `CREATE TABLE … AS SELECT …`.

**49. Maintenance — update a column and add a spatial index**
```
sql @pg "UPDATE parcels SET area_m2 = ST_Area(geom)"
sql @pg "CREATE INDEX ON roads_buf USING GIST (geom)"
```

---

## I. Projects & templates

**50. Repoint a QGIS project to clipped data**
```
project "city.qgs" to="out/city_aoi.qgs" repoint="out/clipped.gpkg" missing=keep
```
Copies the project and points each layer at the same-named layer in `clipped.gpkg`.

**51. Build a fresh project from a folder of outputs**
```
project new from="out/" to="deliverable.qgz" crs=EPSG:6346 title="Deliverable"
```

**52. Instantiate a styled, laid-out template against your data**
```
project from-template=example to="report.qgz" data="mydata/"
```
The bundled `example` template (boundary/roads/places slots + print layout) repoints to your
same-named data, symbology and layout riding along. Register your own designed project with
`project to-template=<name> from="MyMap.qgz" paths=relative`, then call it by name. See
[Template projects](templates.md).

---

## K. Reaching every provider with `run`

niva gives 45 algorithms friendly verbs; the other ~830 — across **every** Processing
provider (native, gdal, grass, qgis, pdal, otb, 3d — **878** total) — are reachable with
`run <id> KEY=value …`. A few per provider below. Find any algorithm's parameters with
`niva describe <id>` or the [algorithm appendix](../algorithms/README.md).

Beyond the QGIS providers, niva's **native-CLI harness** adds two id families that shell
out to a tool directly (see §L): `pdalcli:<command>` (PDAL on **raw LAS/LAZ/COPC**, no COPC
step) and `saga:<library>:<tool>` (`saga_cmd`).

Two things to know when using `run` directly:
- **Enum options take their integer index**, not the alias word — `format=0`, not
  `format=degrees`. (The index list is in each algorithm's appendix entry.)
- **Some providers (GRASS, PDAL) write *named* outputs** (`output=`, `slope=`, …) instead of
  `OUTPUT`, so the step is terminal — give the output path directly rather than piping to
  `save`. GRASS and PDAL also need their backends installed.

### GDAL (`gdal:`) — raster/vector via GDAL/OGR

**53. Contour lines from a DEM**
```
load dem.tif | run gdal:contour INTERVAL=10 FIELD_NAME=ELEV | save contours.gpkg
```

**54. Rasterize a vector field (10-unit pixels)**
```
load parcels.gpkg | run gdal:rasterize FIELD=value UNITS=1 WIDTH=10 HEIGHT=10 | save parcels_value.tif
```

**55. Proximity (distance-to-target) raster**
```
load targets.tif | run gdal:proximity UNITS=0 MAX_DISTANCE=500 | save distance.tif
```

**56. Fill small NoData gaps by interpolation**
```
load gappy.tif | run gdal:fillnodata DISTANCE=20 | save filled.tif
```

### GRASS (`grass:`) — named outputs (terminal), enums as integers

**57. Slope and aspect from a DEM**
```
run grass:r.slope.aspect elevation=dem.tif format=0 slope=slope.tif aspect=aspect.tif
```

**58. Watershed flow accumulation and basins**
```
run grass:r.watershed elevation=dem.tif threshold=1000 accumulation=flowacc.tif basin=basins.tif
```

**59. Least-cost surface from a start point**
```
run grass:r.cost input=cost_surface.tif start_coordinates=600100,4800100 output=cumulative_cost.tif
```

**60. Viewshed from an observer**
```
run grass:r.viewshed input=dem.tif coordinates=600100,4800100 observer_elevation=1.75 max_distance=5000 output=visible.tif
```

### QGIS (`qgis:`) — the QGIS-Python toolbox

**61. Virtual-layer SQL across files (`input1`, `input2`, …)**
```
run qgis:executesql INPUT_DATASOURCES="roads.gpkg;parcels.gpkg" INPUT_QUERY="SELECT * FROM input1 WHERE class = 'primary'" | save primary.gpkg
```
This is the file-backed SQL form (the `sql` verb itself only queries `@conn` databases).

**62. Concave hull (k-nearest neighbour)**
```
load points.gpkg | run qgis:knearestconcavehull KNEIGHBORS=5 | save hull.gpkg
```

**63. Random sample points inside polygons**
```
load tracts.gpkg | run qgis:randompointsinsidepolygons STRATEGY=0 VALUE=100 MIN_DISTANCE=50 | save sample.gpkg
```

**64. Spread overlapping (stacked) points apart**
```
load stacked.gpkg | run qgis:pointsdisplacement PROXIMITY=5 DISTANCE=10 HORIZONTAL=false | save displaced.gpkg
```

### PDAL (`pdal:`) — point clouds (use `run`; load/save are vector/raster)

> The QGIS `pdal:` provider loads point clouds as **COPC/EPT** layers (raw `.las` may need a
> COPC index first). For **raw LAS/LAZ with no COPC step** — and classification-aware LiDAR
> workflows — use niva's `pdalcli:` harness in **§L** below.

**65. Export a DEM from a LiDAR cloud, then hillshade it**
```
run pdal:exportraster INPUT=lidar.copc.laz ATTRIBUTE=Z RESOLUTION=1 | hillshade z_factor=2 | save lidar_hillshade.tif
```
`exportraster` outputs a raster (`OUTPUT`), so it pipes into niva's raster verbs.

**66. Classify ground returns**
```
run pdal:classifyground INPUT=lidar.laz OUTPUT=ground_classified.laz
```

**67. Extract the cloud's data-boundary polygon**
```
run pdal:boundary INPUT=lidar.laz RESOLUTION=10 THRESHOLD=10 OUTPUT=cloud_extent.gpkg
```

**68. Thin a dense cloud by sampling radius**
```
run pdal:thinbyradius INPUT=lidar.laz SAMPLING_RADIUS=2 OUTPUT=thinned.laz
```

### Native (`native:`) — beyond the alias verbs

**69. Join the nearest feature from another layer**
```
load schools.gpkg | run native:joinbynearest INPUT_2=parcels.gpkg NEIGHBORS=1 MAX_DISTANCE=500 | save schools_parcel.gpkg
```

**70. DBSCAN point clustering**
```
load incidents.gpkg | run native:dbscanclustering MIN_SIZE=5 EPS=250 | save incident_clusters.gpkg
```

**71. Shortest path over a road network**
```
load roads.gpkg | run native:shortestpathpointtopoint STRATEGY=0 START_POINT="600100,4800100" END_POINT="601000,4801000" | save route.gpkg
```

**72. Hub-and-spoke (spider) lines**
```
run native:hublines HUBS=depots.gpkg HUB_FIELD=id SPOKES=stops.gpkg SPOKE_FIELD=depot_id | save spider.gpkg
```

### 3D (`3d:`)

**73. Tessellate polygons into 3D geometry**
```
load buildings.gpkg | run 3d:tessellate | save buildings_3d.gpkg
```
The `3d:` provider ships a single algorithm in QGIS 4.0.3 — `tessellate` — so this is the
whole provider.

---

## L. LiDAR & point clouds

Point clouds are first-class: `each`/`show`/`catalog` recognise `.las`/`.laz`/`.copc.laz`/`.vpc`/
`.e57`/… (so a folder of tiles batches), and the friendly verbs **`dtm`** / **`dsm`** / **`hag`**
wrap niva's `pdalcli:` harness (`pdal_wrench`, reading **raw LAS** — no COPC step). Needs the
point-cloud backend (`niva pdal check`; see the [PDAL/LAStools guide](pdal-lastools-qgis4.md)). The
raw `run pdalcli:<command>` escape hatch is still there for everything the verbs don't cover.

**74. DTM — bare-earth terrain from GROUND returns (class 2)**
```
load "tile.las" | dtm resolution=1 | save dtm.tif
```
`dtm` = `run pdalcli:to_raster attribute=Z filter="Classification==2"` — just friendlier.

**75. DSM — top surface from all returns**
```
load "tile.las" | dsm resolution=1 | save dsm.tif
```

**76. CHM — canopy height, the clean way (`hag` normalises, `dsm` rasterises)**
```
load "tile.las" | hag | dsm resolution=1 | save chm.tif
```
`hag` sets each point's height-above-ground; `dsm` then gives the max height per cell = canopy
height. (Alternative: DSM − DTM via `run grass:r.mapcalc.simple expression="A-B" a=dsm.tif b=dtm.tif output=chm.tif`.)

**77. Batch a whole folder of tiles into DTMs**
```
each "~/lidar/tiles/*.las" | dtm resolution=1 | save "~/lidar/dtm/{name}.tif"
```
One DTM per tile, named after the tile. Add filters: `each "*.las" minsize=50M | dtm | save …`.

**78. Batch → single mosaic DTM (rasterise per tile, then merge)**
```
each "~/lidar/tiles/*.las" | dtm resolution=1 | save "~/lidar/dtm/{name}.tif"
run gdal:merge INPUT="~/lidar/dtm/*.tif" OUTPUT="~/lidar/dtm_mosaic.tif"
```
Per-tile rasterising is parallel-friendly and avoids one giant merged cloud. (Cloud-level merge:
`run pdalcli:merge files="a.las;b.las" output=merged.laz`, then `load "merged.laz" | dtm …`.)

**79. `$VAR` in output paths (portable studies)**
```
export LIDAR=~/lidar
niva 'each "$LIDAR/tiles/*.las" | dtm resolution=1 | save "$LIDAR/dtm/{name}.tif"'
```
`$VAR`/`${VAR}` expand in path values (in `.niva` files and the repl too, not just the shell) —
paths only, so a `filter "$area > 100"` expression is untouched.

**80. Raw-harness extras — extract a class, clip, classify, density**
```
load "tile.las" | run pdalcli:translate filter="Classification==6" output=buildings.laz   # class 6 = buildings
load "merged.laz" | run pdalcli:clip polygon=aoi.gpkg output=study.laz
load "tile.las" | run pdalcli:classify_ground output=classified.laz
load "tile.las" | run pdalcli:density resolution=1 | save point_density.tif                 # coverage QA
```

**81. Inventory a LiDAR folder**
```
show ~/lidar/tiles            # each tile: kind=pointcloud, point count, loadable source
catalog ~/lidar/tiles to=lidar_inventory.md
```
`show`/`catalog` report point clouds (and vector/raster/**mesh**) — discovery spans every data
type QGIS reads.

---

## M. Complex, value-added pipelines

Multi-provider chains that turn raw data into finished products. Each is verified end to end.

**82. LiDAR → a full bare-earth terrain set** (DTM once, then three derivatives)
```
load tile.las | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save dtm.tif
load dtm.tif | hillshade z_factor=2 | save dtm_hillshade.tif
load dtm.tif | slope | save dtm_slope.tif
load dtm.tif | run gdal:contour BAND=1 INTERVAL=5 FIELD_NAME=elev OUTPUT=contours_5m.gpkg
```

**83. Canopy height model → mean tree height per parcel** (PDAL → GRASS → zonal stats)
```
load tile.las | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save dtm.tif
load tile.las | run pdalcli:to_raster attribute=Z resolution=1 | save dsm.tif
run grass:r.mapcalc.simple expression="A-B" a=dsm.tif b=dtm.tif output=chm.tif
load parcels.gpkg | zonalstats raster=chm.tif prefix="canopy_" stats=mean | save parcels_canopy.gpkg
```

**84. Hydrology from LiDAR, with GRASS** — DTM → flow accumulation + direction + streams + basins,
then vector catchments and vector streams. `r.watershed` writes several rasters at once (each is an
output *param*), and `run` now creates the output folders for you.
```
load tile.las | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save dtm.tif
run grass:r.watershed elevation=dtm.tif accumulation=hydro/flow_accum.tif drainage=hydro/flow_dir.tif stream=hydro/stream.tif basin=hydro/basin.tif
run grass:r.to.vect input=hydro/basin.tif type=2 output=catchments.gpkg
run grass:r.stream.extract elevation=dtm.tif accumulation=hydro/flow_accum.tif threshold=20000 stream_vector=streams.gpkg
```

**85. Hydrology with SAGA — Strahler-ordered stream network + drainage basins** (a complete run).
GRASS's Strahler tool (`r.stream.order`) is an addon that isn't always installed; SAGA's channel
network gives vector channels carrying an `ORDER` (Strahler) attribute plus vector basins in one
tool. `saga:<library>:<tool>` reaches `saga_cmd` (set `NIVA_SAGA_CMD` if it isn't on `PATH`).
```
run saga:ta_preprocessor:4 ELEV=dtm.tif FILLED=hydro/filled.tif
run saga:ta_hydrology:0 ELEVATION=hydro/filled.tif FLOW=hydro/flow_accum.tif
run saga:ta_channels:5 DEM=hydro/filled.tif ORDER=hydro/strahler.tif SEGMENTS=streams_ordered.gpkg BASINS=basins.gpkg THRESHOLD=6
```

**86. Landform classification** — geomorphons (valleys, ridges, slopes, pits, peaks) from the DTM
```
load dtm.tif | run grass:r.geomorphon elevation=dtm.tif forms=landforms.tif search=15
```

**87. Building footprint candidates** — extract the building class, then its coverage polygons
```
load tile.las | run pdalcli:translate filter="Classification==6" output=buildings.laz
load buildings.laz | run pdalcli:boundary | fixgeom | simplify 0.5m | save building_footprints.gpkg
```

**88. The simplest possible map** — one layer, one line, no options; `figure` picks a sensible
extent, size, and stretch so it just works for vector *or* raster
```
load dem.tif | figure dem.png
```

**89. Push it — a full thematic map using every knob** — themed primary layer, a raster hillshade
plus two vector overlays, an OSM basemap, field labels, a borrowed extent, and print-scale output
```
load flood_zones.gpkg | style apply=flood.qml
  | figure flood_map.png layers="hillshade.tif;roads.gpkg;places.gpkg" basemap=osm labels=zone_name extent=study_area.gpkg size=2400x1600 dpi=200 bg="#eef3f7"
```
Draw order is top-down: `flood_zones` (styled) over the overlays over the basemap. `extent=` borrows
another layer's bounds; `labels=` labels by an attribute; `dpi=200` sizes symbols/text for print.
Being pass-through, `figure` can also snapshot a mid-pipe step: `… | figure step.png | save out.gpkg`.

### `map` — composed cartographic layouts (tiny → extreme)

Where `figure` is a bare image, **`map`** builds a page **layout** (→ PDF/PNG/SVG) with a legend,
scale bar, and north arrow **on by default** — a proper map with no template required. These six
climb from one line to a full multi-layer plate.

**90. Tiny** — one layer, one line; a complete A4 map (legend + scale bar + north arrow)
```
load dem.tif | map dem.pdf
```

**91. Add a title**
```
load parcels.gpkg | map parcels.pdf title="Parcels — 2026"
```

**92. Label it, pick a page and format** — PNG on US Letter, features labelled by a field
```
load zones.gpkg | map zones.png title="Zoning" labels=zone_type page=Letter dpi=200
```

**93. Themed, with an overlay and a basemap** — styled primary layer over roads over OSM tiles
```
load flood.gpkg | style apply=flood.qml | map flood.pdf title="Flood Risk" layers="roads.gpkg" basemap=osm labels=risk portrait
```

**94. Many layers, many types** — line, two rasters, polygon, and point layers on one A3 plate
```
load contours.gpkg | map terrain.pdf title="Terrain — Multi-Layer" layers="dtm.tif;dsm.tif;building_footprints.gpkg;control_points.gpkg" labels=elev extent=dsm.tif page=A3 landscape dpi=300
```

**95. Extreme** — build every derivative from raw LiDAR, then compose one rich A3 plate that stacks
a hillshade, contours, footprints and markers over a basemap, framed to a study area at print DPI
```
load tile.las | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save dtm.tif
load tile.las | run pdalcli:to_raster attribute=Z resolution=1 | save dsm.tif
load dtm.tif  | hillshade z_factor=2 | save hillshade.tif
load dtm.tif  | run gdal:contour BAND=1 INTERVAL=5 FIELD_NAME=elev OUTPUT=contours.gpkg
load tile.las | run pdalcli:translate filter="Classification==6" output=buildings.laz
load buildings.laz | run pdalcli:boundary | fixgeom | simplify 0.5m | save footprints.gpkg
load contours.gpkg | style apply=contours.qml
  | map plate.pdf title="Bare-Earth Terrain & Structures" layers="hillshade.tif;dsm.tif;footprints.gpkg;control_points.gpkg" basemap=osm labels=elev extent=study_area.gpkg page=A3 landscape dpi=300 legend scalebar northarrow
```
For a fully hand-designed plate (custom frames, insets, an atlas of per-feature pages), design it
once in QGIS and export it verbatim: `load aoi.gpkg | map out.pdf from=study.qgz layout="Overview"`.

---

## N. Data discovery & inventory — `find` and `catalog`

`find` locates data on the filesystem; `catalog` profiles it into a Markdown report. Both are
terminal (they report, they don't transform), and every recipe here is runnable as shown.

### `find` — produce output for various uses

**96. A plain file list (redirect to a file)**
```
niva find "*.gpkg" in ~/data --paths > inventory.txt
```
`--paths` prints just absolute paths, one per line, nothing else — ideal for a manifest.

**97. Count matches**
```
niva find "*.tif" in ~/data --paths | wc -l
```

**98. Feed any external tool, spaces-safe**
```
niva find "*.shp" in ~/data -0 | xargs -0 -n1 ogrinfo -so
```
`-0` (alias `--print0`) NUL-separates paths so `xargs -0` handles names with spaces/newlines.

**99. Machine-readable records for scripts / LLMs (`--json` + `jq`)**
```
niva find "*.gpkg" in ~/data --json | jq -r '.[] | select(.features > 1000) | .path'
```
Each record carries `path`, `format`, `kind`, `size`, and — on QGIS's Python — `geometry`,
`crs`, `features`, `fields`, `fid_column`.

**100. Only polygon layers with data (GDAL filters), as paths**
```
niva find "*.gpkg" in ~/data --geom Polygon --min-features 1 --paths
```

**101. Turn a search into a runnable batch (`--as-flow`)**
```
niva find "*.tif" in ~/rasters --as-flow > batch.txt
```
Emits one `each "<path>" | <stages> | save …` line per match — fill in the stages and run.

### `catalog` — inventory to a report

**102. Inventory a directory tree**
```
niva catalog "data/" to=reports/inventory.md
```
Recurses `data/`, profiling every dataset (type, CRS, geometry/bands, feature count, extent);
multi-layer containers expand per layer. Omit `to=` to write `data/catalog.md`.

**103. Deep profile — add data-quality checks**
```
niva catalog "data/" deep to=reports/inventory_deep.md
```
`deep` adds per-layer invalid/empty/duplicate-geometry counts and per-field null counts.

**104. Catalog one container**
```
niva catalog "basemap.gpkg" to=reports/basemap.md
```

**105. Catalog a database connection**
```
niva catalog @gisdb3 to=reports/db.md
```
`catalog` accepts any source `show` does — a file/container, a directory, an `@conn`
database (optionally `@conn.schema`), or a remote OWS service.

---

## Capstone — full pipelines

Two complete, runnable flows ship in [`examples/`](../../examples):

- **`analyst_plan.niva`** — catalog data sources → reproject/warp everything to a target CRS
  → clip to a study-area bounding box → repoint QGIS projects to the clips. A whole regional
  compilation, batched end to end.
- **`youngstown_cat_canvassing.niva`** — a multi-step analysis: assess → reproject → clip →
  geocode → server-side SQL selection → terrain routing → atlas export.

Run one with `niva run examples/analyst_plan.niva` (set `NIVA_TMPDIR` to a roomy disk first
for the raster steps — see the [User Guide](user-guide.md)).
