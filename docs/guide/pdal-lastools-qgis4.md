# PDAL & LAStools in QGIS 4 on Ubuntu (native install)

How to unlock point cloud processing in QGIS 4 and make LiDAR algorithms available to niva's `run` escape hatch, the Processing Toolbox, and PyQGIS.

Verified on this host: **Ubuntu 26.04 LTS, QGIS 4.0.3-Norrköping**.

**Quick status on this host (after the setup in this guide):**

| Component | State | What it means |
|---|---|---|
| PDAL processing provider (`pdal`) | **Working** — 24 algorithms | Provider is compiled into QGIS; `pdal_wrench` now installed and verified end-to-end |
| `pdal` **data** provider (loading raw LAS/LAZ) | **Not built in** | QGIS here reads only `copc` / `ept` / `vpc` point clouds — raw `.las`/`.laz` must be converted to COPC first |
| Orfeo ToolBox (`otb`) | **Working** — 109 algorithms | OTB 9.1.1 + provider plugin; verified loading in QGIS 4 and running via CLI |
| SAGA (`sagang`) | **CLI only** | `saga_cmd` 9.9.3 installed and works; the QGIS provider plugin is unavailable for QGIS 4 (see below) |
| LAStools plugin + binaries | **Extracted, plugin not installed** | Third-party; binaries at `~/Downloads/LAStools`, still needs the QGIS plugin |

The most important correction versus older notes: **PDAL is not an `apt install pdal` step here.** QGIS 4.0.3 already ships the PDAL *processing* provider built in — the 24 algorithms appear in the Processing Toolbox out of the box. What was actually missing is (1) the `pdal_wrench` command-line helper the algorithms shell out to, and (2) the ability to open raw LAS/LAZ, because this build has **no `pdal` data provider** — only `copc`/`ept`/`vpc`. Both are addressed below and were verified working.

---

## PDAL (native point cloud provider)

PDAL is the open-source point cloud library. QGIS 4 ships a **built-in PDAL processing provider** (`QgsPdalAlgorithms` in `qgis.analysis`). On this host it is **already loaded** — you can confirm 24 algorithms are registered under provider id `pdal` without installing anything.

### How the provider actually works

The provider has two independent pieces:

1. **The provider itself** — `QgsPdalAlgorithms`, compiled into `libqgis_analysis` when QGIS is built `WITH_PDAL`. The Ubuntu 26.04 QGIS 4.0.3 package is built this way, so `from qgis.analysis import QgsPdalAlgorithms` succeeds and the 24 algorithms register at startup. **Nothing to install for this part.**

2. **The `pdal_wrench` executable** — every PDAL algorithm is a thin wrapper that shells out to the [`pdal_wrench`](https://github.com/PDAL/wrench) command-line tool. QGIS finds it on `PATH`, or via the `QGIS_WRENCH_EXECUTABLE` environment variable. If it can't be found, running any PDAL algorithm fails with:

   ```
   wrench executable is not found. Either use QGIS build with PDAL support
   or provide correct path via QGIS_WRENCH_EXECUTABLE environment variable.
   ```

There is currently **no `pdal` package available via apt** on this host (checked: `apt-cache policy pdal` returns nothing, even with `universe` enabled), and Homebrew's `pdal` formula does **not** build the standalone `pdal_wrench`. The reliable source is conda-forge, which ships `pdal_wrench` as its own package.

### Making the algorithms runnable — verified method

This is the exact sequence used and verified on this host. It installs everything under `$HOME` with no root.

**1. Install micromamba** (single static binary, self-contained):

```bash
cd ~ && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
```

**2. Create an env with `pdal_wrench`** (the standalone tool is its own conda-forge package, *not* bundled in `pdal`):

```bash
export MAMBA_ROOT_PREFIX=$HOME/micromamba
~/bin/micromamba create -y -p $HOME/micromamba/envs/pdal -c conda-forge pdal pdal_wrench
# -> ~/micromamba/envs/pdal/bin/pdal_wrench   (v1.5.0, verified working)
```

**3. Point QGIS at it.** Add to `~/.bashrc` so both the QGIS desktop app (when launched from a shell) and the niva CLI inherit it:

```bash
export QGIS_WRENCH_EXECUTABLE="$HOME/micromamba/envs/pdal/bin/pdal_wrench"
```

No plugin, no Processing config — the provider is already there; it just needed the backend binary.

> Note: `untwine` is **not** required on this build. It only matters for the `pdal` *data* provider (raw-LAS indexing), which isn't compiled into this QGIS. Point clouds come in via COPC instead (next section).

### Loading point clouds: convert raw LAS/LAZ to COPC first

This QGIS build has **no `pdal` data provider** — its point-cloud data providers are `copc`, `ept`, and `vpc` only. A raw `.las`/`.laz` therefore fails to load as a layer (`Could not load source layer for INPUT`), which blocks every PDAL algorithm. Convert once to Cloud-Optimized Point Cloud (COPC) using the `pdal` CLI from the same env:

```bash
~/micromamba/envs/pdal/bin/pdal translate input.las output.copc.laz
# ~9 s for a 159 MB / 5.3 M-point tile on this host; 159 MB -> 29 MB
```

`.copc.laz` loads natively (QGIS `copc` provider) and works as the `INPUT` to any PDAL algorithm. Verified end-to-end here: `pdal:info` and `pdal:exportraster` both ran against a COPC layer and `exportraster` produced a valid 1000×1000 Float32 DEM at 2 m resolution.

### Verify the provider (this host's Python)

QGIS's Python isn't on the default `sys.path` here; the PDAL check needs the QGIS bindings **and** the bundled `processing` plugin on `PYTHONPATH`:

```bash
PYTHONPATH=/usr/share/qgis/python:/usr/share/qgis/python/plugins:/usr/lib/python3/dist-packages \
QT_QPA_PLATFORM=offscreen /usr/bin/python3 - <<'PY'
from qgis.core import QgsApplication
QgsApplication.setPrefixPath('/usr', True)
app = QgsApplication([], False); app.initQgis()
from processing.core.Processing import Processing
Processing.initialize()
reg = QgsApplication.processingRegistry()
p = reg.providerById('pdal')
print('PDAL provider loaded:', p is not None)
if p:
    print('algorithms:', len(list(p.algorithms())))
import os; os._exit(0)
PY
```

On this host this prints `PDAL provider loaded: True` and `algorithms: 24` — before installing anything. That confirms the *provider* is wired; it does **not** confirm `pdal_wrench` is present (that only shows up when you actually run an algorithm).

### PDAL algorithms exposed by QGIS 4.0.3

QGIS 4.0.3 registers these **24** PDAL-based algorithms (enumerated live from the registry on this host). All are reachable via `run pdal:<id>`.

**Point cloud conversion**

| Algorithm ID | Name |
|---|---|
| `pdal:convertformat` | Convert point cloud format |
| `pdal:exportraster` | Export point cloud to raster |
| `pdal:exportrastertin` | Export point cloud to raster (using triangulation) |
| `pdal:exportvector` | Export point cloud to vector |

**Point cloud data management**

| Algorithm ID | Name |
|---|---|
| `pdal:assignprojection` | Assign projection |
| `pdal:classifyground` | Classify ground points |
| `pdal:clip` | Clip point cloud |
| `pdal:compare` | Compare point clouds |
| `pdal:createcopc` | Create COPC |
| `pdal:filternoiseradius` | Filter noise (using radius) |
| `pdal:filternoisestatistical` | Filter noise |
| `pdal:heightabovegroundbynearestneighbor` | Height above ground |
| `pdal:heightabovegroundtriangulation` | Height above ground (using triangulation) |
| `pdal:info` | Point cloud information |
| `pdal:merge` | Merge point cloud |
| `pdal:reproject` | Reproject point cloud |
| `pdal:thinbydecimate` | Thin (by skipping points) |
| `pdal:thinbyradius` | Thin (by sampling radius) |
| `pdal:tile` | Create tiles from point cloud |
| `pdal:transformpointcloud` | Transform point cloud |
| `pdal:virtualpointcloud` | Build virtual point cloud (VPC) |

**Point cloud extraction**

| Algorithm ID | Name |
|---|---|
| `pdal:boundary` | Boundary |
| `pdal:density` | Point cloud density |
| `pdal:filter` | Filter point cloud |

See the [QGIS PDAL algorithm docs](https://docs.qgis.org/latest/en/docs/user_manual/processing_algs/qgis/pointcloudconversion.html) (conversion, data management, and extraction pages) for full parameter details.

### Parameter names are UPPERCASE

PDAL algorithms follow the **same uppercase `INPUT`/`OUTPUT` convention as every other QGIS provider** — not a lowercase, provider-specific scheme. They add a few PDAL-specific parameters (`FILTER_EXPRESSION`, `FILTER_EXTENT`, `VPC_OUTPUT_FORMAT`, etc.). Verified signatures for the common ones:

| Algorithm | Parameters |
|---|---|
| `pdal:exportraster` | `INPUT`, `ATTRIBUTE`, `RESOLUTION`, `TILE_SIZE`, `FILTER_EXPRESSION`, `FILTER_EXTENT`, `ORIGIN_X`, `ORIGIN_Y`, `OUTPUT` |
| `pdal:clip` | `INPUT`, `OVERLAY`, `FILTER_EXPRESSION`, `FILTER_EXTENT`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:merge` | `LAYERS`, `FILTER_EXPRESSION`, `FILTER_EXTENT`, `OUTPUT` |
| `pdal:thinbydecimate` | `INPUT`, `POINTS_NUMBER`, `FILTER_EXPRESSION`, `FILTER_EXTENT`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:filter` | `INPUT`, `FILTER_EXPRESSION`, `FILTER_EXTENT`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:classifyground` | `INPUT`, `CELL_SIZE`, `SCALAR`, `SLOPE`, `THRESHOLD`, `WINDOW_SIZE`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:heightabovegroundtriangulation` | `INPUT`, `REPLACE_Z`, `COUNT`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:reproject` | `INPUT`, `CRS`, `OPERATION`, `VPC_OUTPUT_FORMAT`, `OUTPUT` |
| `pdal:info` | `INPUT`, `OUTPUT` |

Run `niva describe pdal:<id>` to see the exact signature for any algorithm before scripting it.

### From niva

niva's `run <algorithm-id> KEY=value` escape hatch passes straight through to `processing.run(...)`. Once `pdal_wrench` is reachable, these work:

```niva
# raster/DEM from the Z attribute at 1 m resolution
run pdal:exportraster INPUT="~/data/lidar.laz" ATTRIBUTE=Z RESOLUTION=1 OUTPUT="~/data/dem.tif"

# clip to a polygon overlay
run pdal:clip INPUT="~/data/lidar.laz" OVERLAY="~/data/aoi.gpkg" OUTPUT="~/data/lidar_clip.laz"

# merge several tiles
run pdal:merge LAYERS="~/data/a.laz;~/data/b.laz" OUTPUT="~/data/merged.laz"

# progressive-morphological ground classification (no CLASSIFY param — tune SLOPE/THRESHOLD/WINDOW_SIZE)
run pdal:classifyground INPUT="~/data/lidar.laz" OUTPUT="~/data/classified.laz"

# height above ground (normalised heights) via triangulation
run pdal:heightabovegroundtriangulation INPUT="~/data/lidar.laz" OUTPUT="~/data/hag.laz"

# statistical outlier / noise removal
run pdal:filternoisestatistical INPUT="~/data/lidar.laz" OUTPUT="~/data/denoised.laz"
```

> Until `pdal_wrench` is on `PATH` (or `QGIS_WRENCH_EXECUTABLE` is set), these fail with a *"wrench executable is not found"* error even though niva finds the algorithm — the algorithm exists, its backend doesn't.

---

## LAStools (rapidlasso) — install & configure

LAStools is a **third-party** command-line LiDAR toolset (proprietary but free for most use; commercial license for unrestricted use). It has **no built-in provider** in QGIS — you need the **LAStools Processing Provider plugin**.

### 1. Extract LAStools

A copy is already at `/home/jcz/Downloads/LAStools.tar.gz` (~59 MB, confirmed present). Extract it:

```bash
mkdir -p ~/lastools
tar xzf /home/jcz/Downloads/LAStools.tar.gz -C ~/lastools
# creates ~/lastools/LAStools/ with bin/, lib/, etc.
```

Verify the tools:

```bash
ls ~/lastools/LAStools/bin/
```

Native 64-bit Linux binaries (no Wine needed): `laszip64`, `lasinfo64`, `las2dem64`, `lasground64`, `lasmerge64`, `blast2dem64`, etc.

### 2. Install the QGIS plugin

**Plugins → Manage and Install Plugins → Search "LAStools" → Install**

Use a version that supports QGIS 3.x/4. The plugin is maintained by rapidlasso at [github.com/rapidlasso/LAStoolsPluginQGIS3](https://github.com/rapidlasso/LAStoolsPluginQGIS3).

### 3. Configure the LAStools folder

In QGIS:
1. **Processing → Options**
2. Scroll to **Providers → LAStools**
3. Set **LAStools folder** to `/home/<you>/lastools/LAStools` (the directory containing `bin/`)
4. Leave **Wine folder** blank — Linux native binaries don't need it
5. Click OK

The Processing Toolbox will now show a **LAStools** section.

### 4. Verify

From the Processing Toolbox, try `lasinfo` on a `.las` file, or from niva:

```niva
run lastools:lasinfo INPUT="~/data/in.laz" OUTPUT="~/data/info.txt"
```

> **License note:** some LAStools tools restrict output (adds noise / diagonal artifacts) without a commercial license. Place `lastoolslicense.txt` in the `bin/` directory or set the `LAStoolsLicenseFile` environment variable.

### LAStools ↔ PDAL: when to use which

Both can now cover the basics natively — QGIS 4's PDAL provider does include ground classification, noise removal, and height-above-ground (contrary to older notes). Choose based on robustness and specialization:

| Task | Suggested | Reason |
|------|-----------|--------|
| Read / write / merge / convert | PDAL (`pdal:merge`, `pdal:convertformat`) | Built into QGIS, no extra plugin |
| Export raster (DEM/DSM) | PDAL (`pdal:exportraster`, `pdal:exportrastertin`) | Controlled resolution, TIN option |
| Ground classification | PDAL (`pdal:classifyground`) or LAStools (`lasground`) | PDAL for free/basic; LAStools more robust on complex terrain |
| Noise / outlier removal | PDAL (`pdal:filternoisestatistical` / `pdal:filternoiseradius`) | Built in, adequate |
| Height above ground | PDAL (`pdal:heightabovegroundtriangulation`) | Built in |
| Canopy metrics / forestry | LAStools (`lascanopy`) | Specialized, not in PDAL provider |
| Building/vegetation classification | LAStools (`lasclassify`) | Mature classifier |
| Tiling / batch | Either (`pdal:tile` or LAStools) | Both support batch workflows |

---

## Orfeo ToolBox & SAGA (extra providers)

QGIS 4 ships neither the **Orfeo ToolBox (OTB)** nor the **SAGA** processing provider in core (verified: `providerById('otb')` and `providerById('saga')`/`providerById('sagang')` all returned `False` before setup). **Providers registered out of the box:** `native` (339), `gdal` (59), `grass` (307), `qgis` (39), `pdal` (24), `3d` (1).

### Orfeo ToolBox — installed & verified working in QGIS 4 ✅

OTB has no apt package here, but a self-contained build was already downloaded to `~/Downloads/OTB-9.1.1-Linux`. Even though the QGIS provider plugin is officially marked for QGIS 3.x, **it loads and runs under QGIS 4.0.3** — verified: 109 OTB algorithms registered, and `otbcli_Smoothing` produced a valid output raster.

**1. Confirm OTB works** (first launch runs one-time post-install steps):

```bash
~/Downloads/OTB-9.1.1-Linux/bin/otbcli_BandMath -help   # prints "version 9.1.1"
```

**2. Install the OTB provider plugin.** The plugin manager won't show it under QGIS 4 (it's tagged max 3.99), so install the zip manually:

```bash
curl -sSL -o /tmp/otbprov.zip \
  "https://plugins.qgis.org/plugins/orfeoToolbox_provider/version/3.0.3/download/"
unzip -o /tmp/otbprov.zip -d ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

Then enable it once in **Plugins → Manage and Install Plugins → Installed → tick "OrfeoToolbox Provider"**.

**3. Point it at the OTB install.** In **Processing → Options → Providers → OTB**:
- **OTB folder** → `/home/<you>/Downloads/OTB-9.1.1-Linux`
- **OTB application folder** → `/home/<you>/Downloads/OTB-9.1.1-Linux/lib/otb/applications`

Restart QGIS. An **OTB** section (~109 algorithms) appears, reachable via `run otb:<id>` — e.g.:

```niva
run otb:Smoothing -in "~/data/image.tif" -out "~/data/smooth.tif" -type mean
```

> The OTB *Python* bindings fail to recompile against system Python 3.14 (a harmless first-launch step). That does **not** affect the CLI apps QGIS calls, so the provider is unaffected.

### SAGA — CLI works, but no QGIS-4 provider plugin ⚠️

The SAGA binaries are installed and current: **`saga_cmd` 9.9.3** at `/usr/bin/saga_cmd` (via the `saga` / `saga-common` apt packages). SAGA computations work fine from the command line.

**What does not work:** getting SAGA into the QGIS 4 Processing Toolbox. QGIS dropped SAGA from core after 3.30, and the community replacement — **Processing Saga NextGen Provider** (`sagang`) — has been **withdrawn from every authoritative source**:

- Not in the QGIS plugin repository feed for QGIS 4 (the plugin-manager search "leads nowhere");
- Direct download from `plugins.qgis.org` returns **404**;
- The maintainer repo `north-road/qgis-processing-saga-nextgen` now **404s**;
- Alexander Bruy's original plugin is no longer in his repository either.

The only copies still circulating are **untrusted third-party redistributions** (random Google Drive folders, unofficial mirrors). A QGIS plugin is arbitrary Python that runs inside QGIS with your privileges, so installing one from an unvetted Drive link is a real supply-chain risk — **not recommended.**

**Practical options for SAGA today:**

1. **Use `saga_cmd` directly** (works now, no QGIS needed):
   ```bash
   saga_cmd ta_morphometry 0 -ELEVATION dem.tif -SLOPE slope.tif -ASPECT aspect.tif
   ```
2. **Reach SAGA via GRASS**, which *is* a working QGIS 4 provider here (307 algorithms) and covers much of the same terrain/hydrology ground.
3. **Wrap `saga_cmd` in a niva backend/harness** so niva calls it directly, bypassing the dead QGIS provider — see the note below.

---

## Troubleshooting on this host (Ubuntu 26.04 — QGIS 4.0.3)

| Symptom | Cause | Fix |
|---------|-------|-----|
| PDAL algorithms visible but `run pdal:*` → *"wrench executable is not found"* | `pdal_wrench` binary missing or not pointed to | Install `pdal_wrench` (conda-forge `pdal_wrench` package) and set `QGIS_WRENCH_EXECUTABLE` |
| `run pdal:*` → *"Could not load source layer for INPUT: … not found"* (file exists) | No `pdal` data provider here — raw LAS/LAZ can't be opened | Convert once: `pdal translate in.las out.copc.laz`, then use the `.copc.laz` as `INPUT` |
| `sudo apt install pdal` → *"Unable to locate package"* | No `pdal` apt package in the current cache | Use micromamba/conda-forge (see above); Homebrew `pdal` lacks `pdal_wrench` |
| `run pdal:groundfilter` / `pdal:smrf` → "algorithm not found" | Those IDs don't exist | Ground classification is `pdal:classifyground`; see the algorithm table for real IDs |
| `pdal:*` point-cloud output → *"Incorrect parameter value for VPC_OUTPUT_FORMAT"* | That enum is required for point-cloud-producing algorithms | Pass a valid `VPC_OUTPUT_FORMAT`; run `niva describe pdal:<id>` for allowed values |
| niva `run pdal:` params rejected | Wrong parameter names | Params are UPPERCASE (`INPUT`, `OUTPUT`, …); run `niva describe pdal:<id>` |
| `run otb:*` → "algorithm not found" | OTB folder not set / plugin not enabled | Install the OTB provider zip, enable it, set OTB folder + application folder |
| OTB provider shows 0 algorithms | `OTB_FOLDER` / `OTB_APP_FOLDER` unset | Set both in Processing → Options → Providers → OTB, then restart |
| `run lastools:*` → "algorithm not found" | LAStools plugin not installed | Install via Plugins manager + set LAStools folder |
| "LAStools folder is not set" | Plugin needs path to `bin/` dir | Processing → Options → Providers → LAStools |
| `lasinfo: command not found` in shell | LAStools not on `PATH` | `export PATH=$PATH:~/Downloads/LAStools/bin` in `~/.bashrc` |
| `run sagang:*` → "algorithm not found" | No SAGA provider available for QGIS 4 | Provider plugin is withdrawn; use `saga_cmd` directly or GRASS instead |

---

## The native-CLI harness — `pdalcli:` and `saga:`

Some tools are best driven by their own command line rather than a QGIS provider: **PDAL** (the QGIS `pdal:` provider needs a COPC conversion first; `pdal_wrench` reads raw LAS directly), and **SAGA** (the QGIS provider is withdrawn — see above). niva ships a delegating adapter, **`NativeToolBackend`** (`niva/engine/native.py`), that wraps the real backend and intercepts two id families in `run`, shelling out to the CLI and wrapping the result as a niva layer so it still pipes. **Every other id — `native:*`, `gdal:*`, `grass:*`, `otb:*`, the QGIS `pdal:*` provider — passes straight through unchanged.** It is wired in transparently, so non-harness flows are unaffected.

Because the engine never imports QGIS (everything goes through the abstract `Backend`), this is just a third `Backend` composed over `PyqgisBackend`. It also teaches `load` to accept raw `.las`/`.laz`/`.copc.laz` as a path handle (they can't open as QGIS layers here).

### `pdalcli:<command>` — PDAL on raw LAS/LAZ/COPC (no COPC step)

Shells to `pdal_wrench <command> --key=value …`. The upstream layer auto-wires to `--input`; the output goes to a scratch path (or an explicit `output=` you give — used to persist a `.laz`). `KEY=value` options become `--key=value`. Reads `.las`, `.laz`, and `.copc.laz` directly. Reuses `$QGIS_WRENCH_EXECUTABLE` (or `$NIVA_PDAL_WRENCH`).

| Command | Output | Purpose |
|---|---|---|
| `pdalcli:to_raster` | raster | Grid an attribute (Z, intensity…) to a 2D raster — **DTM/DSM** |
| `pdalcli:to_raster_tin` | raster | Same, via triangulation (smoother surface) |
| `pdalcli:density` | raster | Point-count-per-cell raster (coverage QA) |
| `pdalcli:to_vector` | vector | Points → GeoPackage (3D points + attributes) |
| `pdalcli:boundary` | vector | Coverage polygon (concave hull) |
| `pdalcli:translate` | point cloud | Convert / reproject / **filter by class** to a new LAS/LAZ |
| `pdalcli:clip` | point cloud | Keep points inside `polygon=<vector>` |
| `pdalcli:thin` | point cloud | Downsample (every-Nth or by radius) |
| `pdalcli:classify_ground` | point cloud | Label ground points (SMRF) |
| `pdalcli:filter_noise` | point cloud | Flag statistical/radius outliers |
| `pdalcli:height_above_ground` | point cloud | Normalise heights to the ground surface |
| `pdalcli:merge` | point cloud | Combine tiles — `files="a.las;b.las"` (positional) |

All classification-aware via `filter="Classification==2"` (or any PDAL expression). **Verified end-to-end on the Youngstown tiles** (DTM from ground, DSM, CHM, class-extract, classify_ground, merge, clip, COPC input). Raster/vector outputs pipe into `| save` and downstream `grass:`/`gdal:`; point-cloud outputs persist via `output=`.

```niva
# DTM from ground class, DSM from all returns, then CHM in GRASS
load "tile.las" | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save "dtm.tif"
load "tile.las" | run pdalcli:to_raster attribute=Z resolution=1 | save "dsm.tif"
run grass:r.mapcalc.simple expression="A-B" a="dsm.tif" b="dtm.tif" output="chm.tif"
```

See [`examples/lidar_pdal_grass.niva`](../../examples/lidar_pdal_grass.niva) for the full, verified workflow set.

### `saga:<library>:<tool>` — SAGA via `saga_cmd`

Shells to `saga_cmd <library> <tool> -FLAG value …` (reuses `$NIVA_SAGA_CMD` or `saga_cmd` on `PATH`). Three reserved keys wire niva's pipe onto the tool's own (per-tool) parameter names:

- `_in=<FLAG>` — feed the upstream layer path to that SAGA input flag (e.g. `_in=ELEVATION`)
- `_out=<FLAG>` — give that output flag a scratch path and pipe it on
- `_outext=<.ext>` — output extension (default `.tif`; a vector ext marks the result vector)

Other `KEY=value` → `-KEY value` (booleans → `1`/`0`). Tool may be an index or a name — **prefer names**, since SAGA's indices shift between versions.

```niva
load "dtm.tif" | run saga:ta_morphometry:0 _in=ELEVATION _out=SLOPE UNIT_SLOPE=1 | save "slope.tif"
```

### Graceful degradation

The harness fails **closed and clear**, and only for the specific call:

- **Tool missing** → an actionable `OpError` ("`saga_cmd` not found … install SAGA, or set `$NIVA_SAGA_CMD`"). Unrelated flows (`native:`/`gdal:`/`grass:`) are unaffected. Check programmatically with `backend.available("saga" | "pdal")`.
- **Wrong SAGA version** → SAGA's tool ids drift between releases, so a failed `saga:*` call appends the **detected version** and a nudge to verify the id for it (e.g. *"detected SAGA 9.9.3; tool ids differ between SAGA versions — verify `saga:ta_morphometry:0` …"*).
- **OTB unconfigured** → a `run otb:*` "not found" is rewritten to point at the OTB folder setup (Processing → Options → Providers → OTB).

### Cross-platform (Windows / macOS / Linux)

The harness is pure Python (`subprocess(shell=False)`, `shutil.which`, `tempfile`, `os.path`) — it runs unchanged on all three. What varies is only how you install the CLIs and set the env var:

- **`pdal_wrench`** — `micromamba/conda install -c conda-forge pdal_wrench` on all three OSes. On Windows/macOS, QGIS often bundles it and includes the full PDAL **data provider**, so the raw-LAS limitation and even the COPC step may not apply there.
- **`grass:`** — ships with QGIS everywhere; nothing to install.
- **`saga_cmd`** — SAGA installer (Windows), Homebrew/conda (macOS), apt (Linux).
- **Env var** — set `QGIS_WRENCH_EXECUTABLE` / `NIVA_SAGA_CMD` in the shell rc on Unix, or as a system/`setx` variable on Windows.

**Security posture** (all branches): fixed executable (never from flow input), `shell=False` with an explicit argv list, allowlist-validated library/tool/command/flag names (so crafted tokens like `--config` are rejected), scratch-dir outputs.
