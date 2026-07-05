# Point-cloud (PDAL) backend — setup for Windows, macOS & Linux

niva runs LiDAR / point-cloud steps (`run pdal:*` and `run pdalcli:*` — DTM/DSM,
ground classification, clip, merge, boundary, height-above-ground, …) through
**PDAL** via QGIS. Those verbs have an **extra runtime dependency** that the rest of
niva does not: a working PDAL backend. Everything else (`native:`, `gdal:`,
`qgis:`, `grass:`) needs only QGIS.

This page is the **plain, per-platform manual** for getting that backend working —
no agent required. For the deep dive (every algorithm, LAStools/OTB/SAGA, this
project's host specifics) see **[pdal-lastools-qgis4.md](pdal-lastools-qgis4.md)**.

> **TL;DR** — you need two things: (1) the **`pdal_wrench`** executable, which the
> QGIS PDAL algorithms shell out to, pointed at by the **`QGIS_WRENCH_EXECUTABLE`**
> environment variable; and (2) point clouds in **COPC** form (`.copc.laz`), because
> many QGIS builds can't open a raw `.las`/`.laz` as a layer. On **Windows/macOS the
> official QGIS installer usually ships both**; on **Linux you install `pdal` +
> `pdal_wrench` yourself** (one conda-forge command, no compiling).

---

## The dependency, stated plainly

| Piece | Why it's needed | How QGIS/niva finds it |
|---|---|---|
| **`pdal_wrench`** executable (from [PDAL/wrench](https://github.com/PDAL/wrench)) | Every QGIS PDAL algorithm (`pdal:exportraster`, `pdal:merge`, …) is a thin wrapper that shells out to it. QGIS integrated these in **3.32 (June 2023)**. | `PATH`, or the **`QGIS_WRENCH_EXECUTABLE`** env var (niva's `pdalcli:` also honours `NIVA_PDAL_WRENCH`). |
| **COPC** point clouds (`.copc.laz`) | Many QGIS builds have only the `copc`/`ept`/`vpc` **data** providers — no raw-LAS reader. A raw `.las` then fails with *"Could not load source layer for INPUT"*. | Convert once with the `pdal` CLI: `pdal translate in.las out.copc.laz`. (niva's `pdalcli:` reads raw LAS directly and skips this — see below.) |

Miss the first and you get: *"wrench executable is not found. Either use QGIS
build with PDAL support or provide correct path via QGIS_WRENCH_EXECUTABLE
environment variable."* Miss the second and you get: *"Could not load source layer
for INPUT: …"* even though the file is right there.

**`pdal_wrench` is pre-built for every desktop OS** — conda-forge ships `pdal_wrench`
**1.5.1** for `linux-64`, `osx-64`, `osx-arm64`, and `win-64`. **You never have to
compile it.** (Building from source is possible but needs PDAL's full toolchain — see
the appendix — and is not the recommended path on any platform.)

---

## Windows

**Most users need to do nothing.** The official QGIS standalone installer and the
OSGeo4W installer from [qgis.org/download](https://qgis.org/download/) ship the PDAL
stack, including `pdal_wrench` and a raw-LAS reader. Point-cloud algorithms appear in
Processing and work out of the box. If `run pdal:*` already works, stop here.

**If your QGIS lacks it** (older build, minimal install), add it via conda without
touching QGIS:

1. Install **Miniforge** (conda-forge community installer):
   [github.com/conda-forge/miniforge](https://github.com/conda-forge/miniforge#windows)
   → run the `.exe`.
2. Open **"Miniforge Prompt"** from the Start menu and create the tools:
   ```bat
   conda create -y -n pdal -c conda-forge pdal pdal_wrench
   ```
   This installs `pdal_wrench.exe` under
   `%USERPROFILE%\miniforge3\envs\pdal\Library\bin\`.
3. Tell QGIS where it is — set a **permanent** user environment variable (so the QGIS
   app and the niva CLI both inherit it). In a normal Command Prompt:
   ```bat
   setx QGIS_WRENCH_EXECUTABLE "%USERPROFILE%\miniforge3\envs\pdal\Library\bin\pdal_wrench.exe"
   ```
   Then **restart QGIS** (and any terminal) so the variable takes effect.
   (GUI route: *Settings → System → About → Advanced system settings →
   Environment Variables → New…*)

---

## macOS

**Most users need to do nothing.** The official QGIS `.dmg` from
[qgis.org/download](https://qgis.org/download/) ships the PDAL stack including
`pdal_wrench`. If `run pdal:*` works, stop here.

**If it's missing**, install the tools with conda-forge (works on both Intel and
Apple-silicon):

1. Install **Miniforge**:
   [github.com/conda-forge/miniforge](https://github.com/conda-forge/miniforge#macos)
   (or `brew install miniforge`). Note: Homebrew's own `pdal` formula does **not**
   include `pdal_wrench` — use conda-forge.
2. Create the tools:
   ```bash
   conda create -y -n pdal -c conda-forge pdal pdal_wrench
   # -> ~/miniforge3/envs/pdal/bin/pdal_wrench
   ```
3. Point QGIS at it — add to `~/.zshrc` (Apple's default shell):
   ```bash
   export QGIS_WRENCH_EXECUTABLE="$HOME/miniforge3/envs/pdal/bin/pdal_wrench"
   ```
   To make the **QGIS desktop app** (launched from Finder, not a shell) see it too,
   also run once:
   ```bash
   launchctl setenv QGIS_WRENCH_EXECUTABLE "$HOME/miniforge3/envs/pdal/bin/pdal_wrench"
   ```

---

## Linux

Linux QGIS packages (distro repos and the qgis.org apt repo) ship the PDAL
*processing provider* but **frequently omit the `pdal_wrench` binary and a raw-LAS
data provider** — so you install both yourself. There is usually **no `pdal` apt
package** (e.g. Ubuntu 26.04: `apt-cache policy pdal` returns nothing even with
`universe` enabled). conda-forge is the reliable, no-root, no-compile route — this is
the exact sequence **verified on this project's host (Ubuntu 26.04, QGIS 4.0.3)**:

**1. Install micromamba** (one self-contained static binary, no root):
```bash
cd ~ && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
```

**2. Create an env with `pdal` + `pdal_wrench`** (the wrench tool is its *own*
conda-forge package — installing `pdal` alone is **not** enough):
```bash
export MAMBA_ROOT_PREFIX=$HOME/micromamba
~/bin/micromamba create -y -p $HOME/micromamba/envs/pdal -c conda-forge pdal pdal_wrench
# -> ~/micromamba/envs/pdal/bin/{pdal,pdal_wrench}   (pdal 2.10, wrench 1.5.1 — verified)
```

**3. Point QGIS/niva at it** — add to `~/.bashrc`:
```bash
export QGIS_WRENCH_EXECUTABLE="$HOME/micromamba/envs/pdal/bin/pdal_wrench"
# Linux only: the conda binary needs its own libs on the loader path
export LD_LIBRARY_PATH="$HOME/micromamba/envs/pdal/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

> **`LD_LIBRARY_PATH` matters on Linux.** `pdal_wrench` from conda links against libs
> in the env's `lib/`. Without it on the loader path, QGIS spawns wrench and it dies
> with a missing-`.so` error. (Not needed on Windows/macOS.)

> `conda`/Miniforge works identically to micromamba if you already have it — just
> `conda create -n pdal -c conda-forge pdal pdal_wrench` and use `~/miniforge3/envs/pdal/...`.

---

## Verify it works (any platform)

Convert one raw tile to COPC, then grid a DTM through niva:

```bash
# 1. index raw LAS -> COPC (the pdal CLI reads .las natively; ~9 s for a 160 MB tile)
pdal translate your_tile.las /tmp/tile.copc.laz

# 2. DTM from the ground class, through niva
printf 'load /tmp/tile.copc.laz | run pdal:exportraster ATTRIBUTE=Z FILTER_EXPRESSION="Classification > 1.5 and Classification < 2.5" RESOLUTION=1 | save /tmp/dtm.tif\n' > /tmp/dtm.niva
niva run /tmp/dtm.niva

# 3. confirm real elevations
gdalinfo -stats /tmp/dtm.tif | grep -E "Minimum|Maximum"
```

A valid DTM (sensible min/max elevations for your area) means the backend is wired.
On this project's Youngstown NY tiles this yields a bare-earth DTM of **74.5–86.1 m**
(Lake Ontario datum ≈ 74.2 m).

---

## Gotchas

### `FILTER_EXPRESSION` with `==` is silently dropped by QGIS `pdal:` algorithms
QGIS treats `pdal:exportraster`'s `FILTER_EXPRESSION` as a **QGIS expression** and
evaluates it before handing it to wrench. `Classification==2` is **invalid QGIS
syntax** (QGIS equality is a single `=`), so it evaluates to empty and QGIS emits
`--filter=` (nothing) — wrench then fails with *"Argument 'filter' needs a value and
none was provided."* Two forms that survive the evaluator:

- **Range form (recommended, `=`-free):** `FILTER_EXPRESSION="Classification > 1.5 and Classification < 2.5"` — selects integer class 2 only; QGIS rewrites `and`→`&&` and passes it through correctly.
- **Double-quoted literal:** the value must reach QGIS wrapped in `"…"` so it's passed verbatim (awkward to quote through the niva grammar; prefer the range form).

`niva`'s own **`pdalcli:`** verbs shell straight to `pdal_wrench` and are **not**
affected — there `filter="Classification==2"` works directly.

### `run pdal:*` → "Could not load source layer for INPUT"
Your QGIS has no raw-LAS reader. Convert to COPC first
(`pdal translate in.las out.copc.laz`), or use **`pdalcli:`** which reads raw LAS/LAZ
directly and skips the COPC step entirely:
```niva
load "tile.las" | run pdalcli:to_raster attribute=Z filter="Classification==2" resolution=1 | save "dtm.tif"
```

### Which to use — `pdal:` vs `pdalcli:`
| | `run pdal:*` | `run pdalcli:*` |
|---|---|---|
| Backend | QGIS PDAL provider → `pdal_wrench` | niva harness → `pdal_wrench` directly |
| Raw `.las`/`.laz` input | needs COPC conversion first | **reads directly** |
| Filter syntax | QGIS-expression quirks (see above) | native PDAL `filter="Classification==2"` |
| Pipes into `\| save`, `gdal:`, `grass:` | yes | yes |
| Needs `QGIS_WRENCH_EXECUTABLE` | yes | yes (or `NIVA_PDAL_WRENCH`) |

Both need `pdal_wrench`. Prefer **`pdalcli:`** for raw-LAS-heavy work (no COPC step,
cleaner filters); use **`pdal:`** when you already have COPC/EPT and want the standard
QGIS provider. See [`examples/lidar_pdal_grass.niva`](../../examples/lidar_pdal_grass.niva).

---

## Appendix — building from source (not recommended)

Only if you cannot use conda/QGIS-bundled binaries. `pdal_wrench` needs **PDAL ≥ 2.5**
and **GDAL ≥ 3.0**, both with development files, plus a C++ toolchain (CMake, a C++17
compiler). Where PDAL itself isn't packaged (e.g. Ubuntu 26.04 has neither `pdal` nor
`libpdal-dev`), you must build PDAL first and then wrench against it —
`cmake -DPDAL_DIR=<prefix>/lib/cmake/PDAL .. && make`. This is a heavy, error-prone
build; on Windows/macOS especially, **use the QGIS-bundled or conda-forge binaries
instead.**
