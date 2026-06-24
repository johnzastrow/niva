# Screenshots

niva in the QGIS plugin dock and on the command line. ([← back to README](../README.md))

## Plugin

### Setup
<img src="screenshots/setup.png" width="250" alt="Plugin setup">

*Install the plugin from ZIP and enable the niva toolbar button in QGIS.*

### Run niva
<img src="screenshots/run_niva.png" width="250" alt="Run niva flow">

*Enter a flow and execute it directly from the plugin UI.*

### Export to PyQGIS
<img src="screenshots/export_to_pyqis.png" width="250" alt="Export to PyQGIS">

*Export a flow to a standalone PyQGIS script for automation or sharing.*

### niva panel
<img src="screenshots/dot_niva.png" width="250" alt="niva plugin panel">

*The niva plugin integrates commands and workflow controls into QGIS.*

### ntfy notifications
<img src="screenshots/ntfy.jpg" width="250" alt="ntfy notification from niva">

*The niva plugin integrates commands and workflow controls into QGIS.*

## Command line

### `info`
<img src="screenshots/cli1.png" width="250" alt="niva info on the command line">

*`niva info` reports the environment: the built-in and aliased verbs, the reachable algorithms, and the registered `@conn` connections per QGIS profile.*

### `show`
<img src="screenshots/cli2.png" width="250" alt="niva show on the command line">

*`niva show @basemap.gpkg` lists the loadable layers at a location — with ready-to-`load` sources and copy-paste example flows.*

### `describe` and a flow run
<img src="screenshots/cli3.png" width="500" alt="niva describe and a flow run on the command line">

*Left: `niva describe buffer` shows the verb → algorithm mapping (args, options, flags). Right: a full flow (`load | reproject | buffer | save`) running with per-stage progress.*
