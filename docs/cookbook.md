# niva Cookbook

Fifty worked recipes, from a single transform to full pipelines — including a large block of
spatial **SQL** for both **SpatiaLite** and **PostGIS** — plus a closing tour that reaches
**every QGIS provider** (GDAL, GRASS, QGIS, PDAL, native, 3D) through the `run` escape hatch.
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
load messy.shp | fix | save clean.gpkg
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

**9. Reproject → fix → buffer with options**
```
load buildings.gpkg | reproject EPSG:26918 | fix | buffer 15m dissolve cap=flat segments=12 | save footprints.gpkg
```

**10. Clip → fix → dissolve**
```
load parcels.gpkg | clip township.gpkg | fix | dissolve zoning | save zoning_blocks.gpkg
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
load parcels.gpkg | fix | difference buildings.gpkg | save open_land.gpkg
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
each "basemap.gpkg" | fix | clip aoi.gpkg | save basemap_clip.gpkg
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

---

## F. Raster & terrain

**28. Reproject (warp) a raster**
```
load dem.tif | warp EPSG:6346 | save dem_utm.tif
```

**29. Warp and resample to a target pixel size**
```
load ortho.tif | warp EPSG:6346 resolution=5 resampling=average | save ortho_5m.tif
```
`average` is the right resampler when down-sampling imagery.

**30. Clip a raster to a mask layer**
```
load dem.tif | clipraster aoi.gpkg | save dem_aoi.tif
```

**31. Hillshade from a DEM**
```
load dem.tif | hillshade z_factor=2 azimuth=315 altitude=45 | save hillshade.tif
```

**32. Slope (in percent) and aspect**
```
load dem.tif | slope percent | save slope_pct.tif
load dem.tif | aspect | save aspect.tif
```

**33. Vectorise a classified raster**
```
load landcover.tif | polygonize field=class | save landcover_zones.gpkg
```

---

## G. Spatial SQL in SpatiaLite

These use a saved **SpatiaLite** connection `@sl`. A `SELECT`/`WITH` returns a layer you can
pipe; anything else runs in the database. Adjust table/column/geometry names to your schema
(SpatiaLite geometry columns are often `geometry` or `geom`).

**34. Read a filtered subset as a layer**
```
sql @sl "SELECT * FROM parcels WHERE zoning = 'R1'" | save residential.gpkg
```

**35. Filter by a spatial measure**
```
sql @sl "SELECT id, zoning, geometry FROM parcels WHERE ST_Area(geometry) > 2000" | save big_parcels.gpkg
```

**36. Compute geometry server-side, then keep processing in niva**
```
sql @sl "SELECT id, ST_Buffer(geometry, 50) AS geometry FROM wells" | reproject EPSG:6346 | save well_buffers.gpkg
```

**37. Spatial join — points within polygons**
```
sql @sl "SELECT p.id, z.zone, p.geometry FROM points p JOIN zones z ON ST_Within(p.geometry, z.geometry)" | save points_zoned.gpkg
```

**38. Aggregate to an attribute table**
```
sql @sl "SELECT zoning, COUNT(*) AS n, SUM(ST_Area(geometry)) AS total_area FROM parcels GROUP BY zoning" | save zoning_summary.gpkg
```

**39. Dissolve by attribute with `ST_Union`**
```
sql @sl "SELECT zoning, ST_Union(geometry) AS geometry FROM parcels GROUP BY zoning" | save zoning_dissolved.gpkg
```

**40. CTE, then hand off to a niva verb**
```
sql @sl "WITH big AS (SELECT * FROM parcels WHERE ST_Area(geometry) > 5000) SELECT * FROM big" | centroid | save big_centroids.gpkg
```

---

## H. Spatial SQL in PostGIS

These use a saved **PostGIS** connection `@pg`. Reads (`SELECT`/`WITH`) return a pipeable
layer; writes (`CREATE`/`UPDATE`/`INSERT`/`CREATE INDEX`/…) run server-side and end the flow.

**41. Read a table (schema-qualified)**
```
load @pg.public.roads | save roads_local.gpkg
```
Equivalent read via SQL: `sql @pg "SELECT * FROM public.roads" | save roads_local.gpkg`.

**42. Filter in the database, finish in niva**
```
sql @pg "SELECT * FROM roads WHERE class = 'primary'" | buffer 50m dissolve | save primary_corridors.gpkg
```

**43. Do the spatial work in SQL (the server-side lever)**
```
sql @pg "SELECT id, ST_Buffer(geom, 100) AS geom FROM homes WHERE has_cat AND NOT has_dog" | save targets.gpkg
```

**44. Cross-table spatial join**
```
sql @pg "SELECT a.id, a.geom FROM parcels a JOIN flood b ON ST_Intersects(a.geom, b.geom)" | save parcels_at_risk.gpkg
```

**45. Write a niva result back into PostGIS**
```
load parcels.gpkg | clip aoi.gpkg | save @pg.public.parcels_clip mode=replace
```
`mode=create` (default) refuses to overwrite; `replace` drops + recreates; `append` inserts.

**46. Analyse-in-place: materialise a derived table**
```
sql @pg "CREATE TABLE roads_buf AS SELECT id, ST_Buffer(geom, 100) AS geom FROM roads"
```
A leading `CREATE` routes server-side (terminal) — even `CREATE TABLE … AS SELECT …`.

**47. Maintenance — update a column and add a spatial index**
```
sql @pg "UPDATE parcels SET area_m2 = ST_Area(geom)"
sql @pg "CREATE INDEX ON roads_buf USING GIST (geom)"
```

---

## I. Projects & templates

**48. Repoint a QGIS project to clipped data**
```
project "city.qgs" to="out/city_aoi.qgs" repoint="out/clipped.gpkg" missing=keep
```
Copies the project and points each layer at the same-named layer in `clipped.gpkg`.

**49. Build a fresh project from a folder of outputs**
```
project new from="out/" to="deliverable.qgz" crs=EPSG:6346 title="Deliverable"
```

**50. Instantiate a styled, laid-out template against your data**
```
project from-template=example to="report.qgz" data="mydata/"
```
The bundled `example` template (boundary/roads/places slots + print layout) repoints to your
same-named data, symbology and layout riding along. Register your own designed project with
`project to-template=<name> from="MyMap.qgz" paths=relative`, then call it by name. See
[Template projects](templates.md).

---

## K. Reaching every provider with `run`

niva gives 45 algorithms friendly verbs; the other ~720 — across **every** Processing
provider — are reachable with `run <id> KEY=value …`. Four per provider below. Find any
algorithm's parameters with `niva describe <id>` or the [algorithm appendix](algorithms/README.md).

Two things to know when using `run` directly:
- **Enum options take their integer index**, not the alias word — `format=0`, not
  `format=degrees`. (The index list is in each algorithm's appendix entry.)
- **Some providers (GRASS, PDAL) write *named* outputs** (`output=`, `slope=`, …) instead of
  `OUTPUT`, so the step is terminal — give the output path directly rather than piping to
  `save`. GRASS and PDAL also need their backends installed.

### GDAL (`gdal:`) — raster/vector via GDAL/OGR

**51. Contour lines from a DEM**
```
load dem.tif | run gdal:contour INTERVAL=10 FIELD_NAME=ELEV | save contours.gpkg
```

**52. Rasterize a vector field (10-unit pixels)**
```
load parcels.gpkg | run gdal:rasterize FIELD=value UNITS=1 WIDTH=10 HEIGHT=10 | save parcels_value.tif
```

**53. Proximity (distance-to-target) raster**
```
load targets.tif | run gdal:proximity UNITS=0 MAX_DISTANCE=500 | save distance.tif
```

**54. Fill small NoData gaps by interpolation**
```
load gappy.tif | run gdal:fillnodata DISTANCE=20 | save filled.tif
```

### GRASS (`grass:`) — named outputs (terminal), enums as integers

**55. Slope and aspect from a DEM**
```
run grass:r.slope.aspect elevation=dem.tif format=0 slope=slope.tif aspect=aspect.tif
```

**56. Watershed flow accumulation and basins**
```
run grass:r.watershed elevation=dem.tif threshold=1000 accumulation=flowacc.tif basin=basins.tif
```

**57. Least-cost surface from a start point**
```
run grass:r.cost input=cost_surface.tif start_coordinates=600100,4800100 output=cumulative_cost.tif
```

**58. Viewshed from an observer**
```
run grass:r.viewshed input=dem.tif coordinates=600100,4800100 observer_elevation=1.75 max_distance=5000 output=visible.tif
```

### QGIS (`qgis:`) — the QGIS-Python toolbox

**59. Virtual-layer SQL across files (`input1`, `input2`, …)**
```
run qgis:executesql INPUT_DATASOURCES="roads.gpkg;parcels.gpkg" INPUT_QUERY="SELECT * FROM input1 WHERE class = 'primary'" | save primary.gpkg
```
This is the file-backed SQL form (the `sql` verb itself only queries `@conn` databases).

**60. Concave hull (k-nearest neighbour)**
```
load points.gpkg | run qgis:knearestconcavehull KNEIGHBORS=5 | save hull.gpkg
```

**61. Random sample points inside polygons**
```
load tracts.gpkg | run qgis:randompointsinsidepolygons STRATEGY=0 VALUE=100 MIN_DISTANCE=50 | save sample.gpkg
```

**62. Spread overlapping (stacked) points apart**
```
load stacked.gpkg | run qgis:pointsdisplacement PROXIMITY=5 DISTANCE=10 HORIZONTAL=false | save displaced.gpkg
```

### PDAL (`pdal:`) — point clouds (use `run`; load/save are vector/raster)

**63. Export a DEM from a LiDAR cloud, then hillshade it**
```
run pdal:exportraster INPUT=lidar.copc.laz ATTRIBUTE=Z RESOLUTION=1 | hillshade z_factor=2 | save lidar_hillshade.tif
```
`exportraster` outputs a raster (`OUTPUT`), so it pipes into niva's raster verbs.

**64. Classify ground returns**
```
run pdal:classifyground INPUT=lidar.laz OUTPUT=ground_classified.laz
```

**65. Extract the cloud's data-boundary polygon**
```
run pdal:boundary INPUT=lidar.laz RESOLUTION=10 THRESHOLD=10 OUTPUT=cloud_extent.gpkg
```

**66. Thin a dense cloud by sampling radius**
```
run pdal:thinbyradius INPUT=lidar.laz SAMPLING_RADIUS=2 OUTPUT=thinned.laz
```

### Native (`native:`) — beyond the alias verbs

**67. Join the nearest feature from another layer**
```
load schools.gpkg | run native:joinbynearest INPUT_2=parcels.gpkg NEIGHBORS=1 MAX_DISTANCE=500 | save schools_parcel.gpkg
```

**68. DBSCAN point clustering**
```
load incidents.gpkg | run native:dbscanclustering MIN_SIZE=5 EPS=250 | save incident_clusters.gpkg
```

**69. Shortest path over a road network**
```
load roads.gpkg | run native:shortestpathpointtopoint STRATEGY=0 START_POINT="600100,4800100" END_POINT="601000,4801000" | save route.gpkg
```

**70. Hub-and-spoke (spider) lines**
```
run native:hublines HUBS=depots.gpkg HUB_FIELD=id SPOKES=stops.gpkg SPOKE_FIELD=depot_id | save spider.gpkg
```

### 3D (`3d:`)

**71. Tessellate polygons into 3D geometry**
```
load buildings.gpkg | run 3d:tessellate | save buildings_3d.gpkg
```
The `3d:` provider ships a single algorithm in QGIS 4.0.3 — `tessellate` — so this is the
whole provider.

---

## Capstone — full pipelines

Two complete, runnable flows ship in [`examples/`](../examples):

- **`analyst_plan.niva`** — catalog data sources → reproject/warp everything to a target CRS
  → clip to a study-area bounding box → repoint QGIS projects to the clips. A whole regional
  compilation, batched end to end.
- **`youngstown_cat_canvassing.niva`** — a multi-step analysis: assess → reproject → clip →
  geocode → server-side SQL selection → terrain routing → atlas export.

Run one with `niva run examples/analyst_plan.niva` (set `NIVA_TMPDIR` to a roomy disk first
for the raster steps — see the [User Guide](user-guide.md)).
