# Analysts Tasks

Tasked with compiling high quality for a region in Northern Western New York State. Create a repeatable niva script that does the following tasks. Use only niva script. Alert if a niva native function is needed but not available.

1. Create directory /home/jcz/Github/niva/data

2. Catalog these data sources into the new directory
   * /home/jcz/Downloads/NiagaraBasemap/
   * /home/jcz/Downloads/NiagaraOverture/
   * ~/Downloads/ytown_dem_deflate.tif
   * /home/jcz/Downloads/twn_Porter_sp24/porter_ortho.jp2
   * /home/jcz/Github/marimo_qgis/example/example.gpkg
3. Project and warp all the data to "EPSG:6346 - NAD83(2011) / UTM zone 17N" as copies into the new directory into new files and geopackages as follows
   	* /home/jcz/Downloads/NiagaraBasemap/ --> basemap.gpkg
   	* /home/jcz/Downloads/NiagaraOverture/ --> overture.gpkg
   * ~/Downloads/ytown_dem_deflate.tif --> dem.tif
   * /home/jcz/Downloads/twn_Porter_sp24/porter_ortho.jp2 --> orthophoto.jp2
   * /home/jcz/Github/marimo_qgis/example/example.gpkg --> collected.gpkg
4. Clip all the geodata in the new directory to the bounding box of this layer, which is the study area:
   * [/home/jcz/Github/marimo_qgis/example/example.gpkg](file:///home/jcz/Github/marimo_qgis/example/example.gpkg) layer AOISM
5. Copy the QGIS project files from this places into the new directory and repoint the layer references to the newly clipped data
   * /home/jcz/Downloads/NiagaraOverture/
   * /home/jcz/Downloads/NiagaraBasemap/
   * /home/jcz/Github/marimo_qgis/example/example.gpkg