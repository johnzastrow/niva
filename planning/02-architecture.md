# Niva — Architecture & Technical Design (v1)

_Status: draft for review. Resolves the return-type model and the dual-backend
abstraction that the starting materials left open._

## 1. Layering

```
niva (public API)            import niva; niva.buffer(...), niva.run(...), niva.find(...)
  └─ core/
       ops.py                operation definitions (specs) + generated functions
       registry.py           friendly-name -> algorithm-id aliases + param specs
       engine.py             run(alg_id, params, backend) -> Result
       layer.py              Layer wrapper (the input/output contract)
       result.py             Result / OpError types
       qgis_env.py           interpreter + QGIS init (shared w/ marimo-qgis idea)
       logging.py            structured logging, --timing
  └─ backends/
       base.py               Backend ABC: run_algorithm(alg_id, params) -> RawResult
       pyqgis_backend.py     in-process processing.run(...)
       qgis_process_backend.py   subprocess qgis_process + JSON
       select.py             auto-selection (in-QGIS? -> pyqgis, else qgis_process)
  └─ cli/
       main.py               argparse app generated from op specs
       emit.py               human vs --json output, exit codes
```

Deferred to v2 (directories reserved, empty in v1): `flows/`, `sql/`.

## 2. The return-type contract (the central decision)

Every operation returns a **`Result`**; its `.output` is a **`Layer`**.

```python
@dataclass
class Result:
    ok: bool
    output: "Layer | None"     # primary output as a Layer
    outputs: dict[str, Any]    # all raw outputs by Processing key
    algorithm: str             # resolved alg id, e.g. "native:buffer"
    params: dict[str, Any]     # resolved params actually sent
    elapsed: float | None
    backend: str               # "pyqgis" | "qgis_process"
    message: str = ""
    def __fspath__(self): ...   # so a Result can be used where a path is expected
    def load(self, name=None): ...  # add to the current QGIS project (in-process)
```

`Layer` is a thin, dual-natured handle so niva is ergonomic in every context:

```python
class Layer:
    """Wraps EITHER an on-disk source (path/URI/PostGIS) OR a live QgsVectorLayer.
    Accepted as input anywhere; produced as output everywhere."""
    @classmethod
    def coerce(cls, value) -> "Layer": ...  # str path | QgsMapLayer | Layer | Result
    @property
    def source(self) -> str: ...            # path/URI usable by both backends
    def as_qgs(self) -> "QgsVectorLayer": ... # materialize a live layer (in-process)
    feature_count, crs, geometry_type, fields   # lazy metadata
```

**Why this works for v1 with pipelines deferred:** each op takes inputs (coerced via
`Layer.coerce`) and an optional `output`. If `output` is omitted it defaults to a
managed temporary (`TEMPORARY_OUTPUT` in-process; a temp file for `qgis_process`),
surfaced as `result.output`. Because `Result.__fspath__` returns the output path,
you can still hand a result to the next call manually — which gives 80% of chaining's
value without building a chain engine yet. Formal chaining lands in v2 on top of this
exact contract, so nothing here gets thrown away.

## 2a. Interoperability (escape hatches are first-class)

The grammar must never trap the user. Each level exposes the one below:

| niva value | drop down to … | how |
| :-- | :-- | :-- |
| `Result` | the raw Processing outputs | `result.outputs` (dict), `result.algorithm`, `result.params` |
| `Result` / `Layer` | a file path/URI | `os.fspath(result)`, `layer.source` |
| `Layer` | a live `QgsVectorLayer` | `layer.as_qgs()` |
| `Layer` | GeoPandas / Shapely / SQL | via `.source` (path/URI) → `gpd.read_file(...)`, etc. |
| any op | a not-yet-aliased algorithm | `niva.run("provider:alg", **params)` |

Conversely, niva **accepts** what those layers produce: `Layer.coerce()` takes a path,
a `QgsMapLayer`, a `Result`, or another `Layer`. So a user can interleave niva and raw
PyQGIS/GeoPandas freely:

```python
buf = niva.buffer("roads.gpkg", distance=100)      # niva grammar
gdf = geopandas.read_file(buf.source)              # drop into GeoPandas
gdf["len"] = gdf.length
niva.dissolve(gdf.to_file("tmp.gpkg") or "tmp.gpkg", field="zone")  # back into niva
```

This is what "concise grammar, interwoven with PyQGIS/other libraries when more
granularity is needed" means concretely, and it is a v1 requirement, not a v2 nicety.

## 3. Backend abstraction (the cost of "both backends")

```python
class Backend(ABC):
    name: str
    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def run_algorithm(self, alg_id: str, params: dict) -> RawResult: ...
    @abstractmethod
    def list_algorithms(self) -> list[AlgInfo]: ...
    @abstractmethod
    def describe(self, alg_id: str) -> AlgInfo: ...
```

- **PyqgisBackend** — calls `processing.run(alg_id, params)` in-process. Requires a
  live/initialized QGIS app (we are inside QGIS, or we `qgis_env.ensure_app()` on
  QGIS's Python). Outputs are real `QgsVectorLayer`s or paths.
- **QgisProcessBackend** — shells out to `qgis_process run <alg> --json` with a JSON
  parameter payload, parses the JSON result. No live session needed; ideal for
  CLI/batch/CI.

**Normalization is the key engineering task:** both backends must return a `RawResult`
with the same shape (`{outputs, ok, message, elapsed}`) so `engine.run()` builds an
identical `Result` regardless of backend. Param serialization differs (Python objects
vs JSON), so each backend owns a `_serialize(params)` that converts a `Layer` to the
right form (live layer/path for pyqgis; path/URI string for qgis_process).

**Selection** (`backends/select.py`): default = auto.
- Inside a running QGIS (iface present) or an initialized in-process app → `pyqgis`.
- Otherwise, if `qgis_process` is on PATH → `qgis_process`.
- Override: `niva.use_backend("pyqgis"|"qgis_process")`, env `NIVA_BACKEND`, or per-call
  `backend=` kwarg / CLI `--backend`.

## 4. Operation specs (one source of truth for lib + CLI)

Each operation is declared once as a spec; both the Python function and the CLI
subcommand are generated from it, so they never drift.

```python
OPS = [
  Op("buffer", "native:buffer",
     params=[
        P("input",   required=True,  to="INPUT",    kind="layer"),
        P("distance",required=True,  to="DISTANCE", kind="float"),
        P("dissolve",default=False,  to="DISSOLVE", kind="bool"),
        P("segments",default=5,      to="SEGMENTS", kind="int"),
        P("output",  default=None,   to="OUTPUT",   kind="sink"),
     ],
     summary="Buffer features by a distance."),
  # clip, intersection, dissolve, reproject, ...
]
```

`niva.buffer(...)` is generated from this; `niva vector buffer ...` is the same spec
fed to argparse. Adding an op = adding a spec.

## 5. Errors & exit codes

- Library raises `niva.OpError` (with alg id, params, backend, underlying message) on
  failure; `Result.ok` is also set for callers who prefer checking.
- CLI maps to exit codes (from the materials, retained): `0` ok, `1` runtime failure,
  `2` usage error, `3` missing QGIS/dependency, `4` connection/SQL (reserved for v2).
- Logs/timing → stderr; data/`--json` → stdout.

## 6. Runtime & distribution

- **Runs on QGIS's own Python** — the exact constraint solved in marimo-qgis. niva
  reuses that interpreter-detection idea (`qgis_env.py` ~ `runtime.qgis_python()`),
  so it can also locate `qgis_process` and initialize a standalone app.
- **Packaging:** a normal `pyproject.toml` package, `pip install`ed into QGIS's
  Python (e.g. OSGeo4W Python on Windows, system python3 on Linux). No vendored QGIS.
- **Entry point:** `niva = "niva.cli.main:main"` console script.
- **PyPI name `niva`** — verify availability before publishing; fallback names noted
  in the naming docs (`pyniva`, `nivagis`, etc.).

## 7. Testing / CI

- Tests run on QGIS's Python (headless). Prefer the **`qgis_process` backend** for
  most CI tests (no app init), plus a small in-process suite.
- **Fixtures:** tiny GeoPackages committed under `tests/data/` (a few features each).
- **Layers of tests:** (a) registry/spec + param-mapping unit tests (no QGIS),
  (b) backend-parity tests asserting pyqgis and qgis_process give equivalent outputs
  for the same op, (c) CLI arg-parsing/exit-code tests.
- CI mirrors marimo-qgis: invoke via QGIS's interpreter (`python-qgis.bat` on Windows
  / system python3 on Linux); a GitHub Actions job using a QGIS container on Linux.

## 8. Relationship to marimo-qgis

niva is the natural geoprocessing layer inside marimo-qgis notebooks. Shared concepts
(QGIS-Python detection, headless init) could become a tiny common module, but to avoid
premature coupling, v1 keeps niva self-contained and simply *reimplements the small
detection helper*, revisiting extraction once both are stable.
