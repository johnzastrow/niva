# QGIS algorithm appendix

Every QGIS Processing algorithm reachable from niva via `run <id> KEY=value …` — **878 algorithms** across 7 providers (QGIS 4.0.3). For each: its parameters (with types, defaults, and enum options), description, outputs, a worked **Example usage**, and which niva **alias verb** (if any) wraps it (⭐).

This is auto-generated — regenerate with `scripts/gen_algorithms.py` after a QGIS upgrade. Most users only need the 45 [alias verbs](../reference.md#5-alias-verbs-the-registry); this appendix is for reaching everything else through `run`. Discover one live with `niva describe <id>`.

| Provider | Algorithms | niva alias verbs | Reference |
|---|---|---|---|
| `3d:` | 1 | 0 | [3d.md](3d.md) |
| `gdal:` | 59 | 5 | [gdal.md](gdal.md) |
| `grass:` | 307 | 0 | [grass.md](grass.md) |
| `native:` | 339 | 40 | [native.md](native.md) |
| `otb:` | 109 | 0 | [otb.md](otb.md) |
| `pdal:` | 24 | 0 | [pdal.md](pdal.md) |
| `qgis:` | 39 | 0 | [qgis.md](qgis.md) |
| **Total** | **878** | **45** | |

> **Beyond QGIS providers:** niva's native-CLI harness adds `pdalcli:<command>` (PDAL on raw LAS/LAZ/COPC) and `saga:<library>:<tool>` (`saga_cmd`). These are not QGIS algorithms, so they are not listed above — see [the harness reference](../guide/pdal-lastools-qgis4.md#the-native-cli-harness--pdalcli-and-saga).

