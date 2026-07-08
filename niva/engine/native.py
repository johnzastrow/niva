"""A native command-line harness backend (docs/guide/pdal-lastools-qgis4.md, appendix).

Some geoprocessing engines are best driven by their own command-line tool rather than
through a QGIS Processing provider:

* **SAGA** — QGIS dropped it from core after 3.30 and the ``sagang`` provider plugin
  has been withdrawn from every trusted source, so ``run sagang:*`` cannot resolve on
  QGIS 4. But ``saga_cmd`` is installed and works.
* **PDAL** — the QGIS ``pdal:`` provider works, but only after a raw ``.las``/``.laz``
  is converted to COPC (this build has no ``pdal`` *data* provider). ``pdal_wrench``
  reads raw LAS directly and is classification-aware, so a direct CLI path skips the
  COPC dance entirely — the natural home for LiDAR-with-classifications workflows.

``NativeToolBackend`` is a *delegating adapter* over any real :class:`Backend`. It
forwards every method to the wrapped backend unchanged, **except** ``run_raw``: when
the algorithm id names a native tool it shells out to that tool's CLI and returns the
output wrapped as a :class:`Layer`, so the result still pipes into the next niva stage.

Two id families are claimed:
  * ``saga:<library>:<tool>``  -> ``saga_cmd <library> <tool> -FLAG value …``
  * ``pdalcli:<command>``      -> ``pdal_wrench <command> --key=value …`` (raw LAS ok)

Every other id (``native:*``, ``gdal:*``, ``grass:*``, the QGIS ``pdal:*`` provider, …)
is handed straight to the wrapped backend. GRASS in particular needs nothing here — it
is a working QGIS 4 provider, so ``run grass:r.slope.aspect …`` already flows through
the wrapped :class:`PyqgisBackend`.

Security posture (mirrors the rest of the engine): the executable is fixed (from an
env var or found on ``PATH``, never from flow input); the process is spawned with
``shell=False`` and an explicit argv list, so a value can never break out into the
shell; library/tool/command/flag names are allowlist-validated; output paths are
generated in niva's scratch dir.
"""

from __future__ import annotations

import os

from ..utilities import expand_path
import re
import shutil
import subprocess
import tempfile

from ..errors import OpError
from .layer import SOURCE, Layer

# --- id prefixes this harness claims ----------------------------------------
SAGA_PREFIX = "saga:"
PDAL_PREFIX = "pdalcli:"

# Allowlist for every token that reaches argv as a name. Values are separate argv items
# (no shell), so only names need this — a name like `--config` or `; rm` would otherwise
# be read by the tool as an option/command.
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# A SAGA tool may be addressed by numeric index (`0`, `27`) or by name.
_TOOL_RE = re.compile(r"^(?:\d+|[A-Za-z][A-Za-z0-9_]*)$")
# pdal_wrench flags are lowercase_with_underscores.
_PDAL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# SAGA reserved control keys (stripped from the flag list) — they wire niva's pipe onto
# each tool's own (per-tool) parameter names, which vary and cannot be guessed.
_IN_KEY = "_in"  # `_in=ELEVATION` -> feed the upstream layer path to -ELEVATION
_OUT_KEY = "_out"  # `_out=SLOPE`    -> assign -SLOPE a temp path, return it
_OUTEXT_KEY = "_outext"  # output extension, default `.tif`
_RASTER_EXT = {".tif", ".tiff", ".sdat", ".asc"}

# pdal_wrench commands -> (default output extension, layer facet). Point-cloud outputs
# use the "pointcloud" facet: they chain into the next pdalcli stage by path, or are
# persisted by passing an explicit `output=<path>` (they do not pipe into niva `save`,
# which loads via QGIS and has no raw-LAS provider here).
_PDAL_COMMANDS = {
    "to_raster": (".tif", "raster"),
    "to_raster_tin": (".tif", "raster"),
    "density": (".tif", "raster"),
    "to_vector": (".gpkg", "vector"),
    "boundary": (".gpkg", "vector"),
    "translate": (".laz", "pointcloud"),
    "clip": (".laz", "pointcloud"),
    "thin": (".laz", "pointcloud"),
    "classify_ground": (".laz", "pointcloud"),
    "filter_noise": (".laz", "pointcloud"),
    "height_above_ground": (".laz", "pointcloud"),
    "merge": (".laz", "pointcloud"),
}


class NativeToolBackend:
    """Wrap ``inner`` and intercept ``saga:*`` / ``pdalcli:*`` ids in :meth:`run_raw`;
    delegate everything else.

    Not a :class:`Backend` subclass — it composes one and forwards by ``__getattr__``,
    so it stays correct as the ``Backend`` interface grows without re-listing every
    pass-through. The engine duck-types the backend, so the wrapper is a drop-in.
    """

    def __init__(
        self,
        inner,
        *,
        saga_cmd: str | None = None,
        pdal_wrench: str | None = None,
        scratch_dir: str | None = None,
    ):
        self._inner = inner
        self._saga_cmd = saga_cmd or os.environ.get("NIVA_SAGA_CMD") or "saga_cmd"
        # Reuse QGIS_WRENCH_EXECUTABLE (already set for the QGIS pdal: provider) so one
        # env var configures both paths to pdal_wrench.
        self._pdal_wrench = (
            pdal_wrench
            or os.environ.get("NIVA_PDAL_WRENCH")
            or os.environ.get("QGIS_WRENCH_EXECUTABLE")
            or "pdal_wrench"
        )
        self._scratch = (
            scratch_dir or os.environ.get("NIVA_TMPDIR") or tempfile.gettempdir()
        )
        self._versions: dict = {}  # family -> detected version string (probed once)

    def __getattr__(self, name):
        # Everything not defined here (run, save, profile, render_call, …) delegates.
        return getattr(self._inner, name)

    # --- graceful degradation: capability + version probing -------------------

    def available(self, family: str) -> bool:
        """Is the CLI for ``family`` (``'saga'`` | ``'pdal'``) installed and runnable?
        Cheap, exception-free — for callers/docs that want to check before dispatching."""
        exe = self._saga_cmd if family == "saga" else self._pdal_wrench
        try:
            self._resolve(exe, family, "")
            return True
        except OpError:
            return False

    def _tool_version(self, exe_path: str, family: str) -> str:
        """Best-effort version string for a CLI (cached). Empty if it can't be read —
        never raises, so it is safe to call while building an error message."""
        if family not in self._versions:
            ver = ""
            try:
                proc = subprocess.run(
                    [exe_path, "--version"],
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                lines = (proc.stdout or proc.stderr or "").strip().splitlines()
                ver = lines[0].strip() if lines else ""
            except Exception:  # noqa: BLE001 — a version probe must never break the run
                ver = ""
            self._versions[family] = ver
        return self._versions[family]

    # --- load: pass raw point clouds through as a path handle -----------------

    def load(self, source: str, *, facet: str = "vector") -> Layer:
        """Raw ``.las``/``.laz``/``.copc.laz`` cannot open as a QGIS layer here (no
        ``pdal`` data provider), so return a path handle the ``pdalcli:*`` tools read via
        ``--input`` — no QGIS involved. Every other source delegates to the wrapped
        backend unchanged."""
        path = expand_path(source)
        low = path.lower()
        if low.endswith((".las", ".laz")):  # covers .copc.laz too
            return Layer(SOURCE, path, facet="pointcloud", name=os.path.basename(path))
        return self._inner.load(source, facet=facet)

    # --- dispatch ------------------------------------------------------------

    def run(
        self,
        algorithm: str,
        params: dict,
        *,
        input_param=None,
        input_layer: Layer | None = None,
        output_param=None,
        progress=None,
        cancel=None,
    ):
        """Alias dispatch. Point-cloud verbs (``dtm``/``dsm``/``hag``) bind to ``pdalcli:*`` ids,
        and terrain SAGA verbs to ``saga:*`` — route those to the native-CLI harness (input
        auto-wired from the piped layer, output to a scratch path; ``input_param``/``output_param``
        don't apply). Everything else delegates to the wrapped QGIS backend unchanged."""
        if algorithm.startswith(SAGA_PREFIX):
            return self._run_saga(algorithm, params, input_layer, progress, cancel)
        if algorithm.startswith(PDAL_PREFIX):
            return self._run_pdal(algorithm, params, input_layer, progress, cancel)
        return self._inner.run(
            algorithm,
            params,
            input_param=input_param,
            input_layer=input_layer,
            output_param=output_param,
            progress=progress,
            cancel=cancel,
        )

    def run_raw(
        self,
        algorithm: str,
        params: dict,
        *,
        input_layer: Layer | None = None,
        progress=None,
        cancel=None,
    ):
        if algorithm.startswith(SAGA_PREFIX):
            return self._run_saga(algorithm, params, input_layer, progress, cancel)
        if algorithm.startswith(PDAL_PREFIX):
            return self._run_pdal(algorithm, params, input_layer, progress, cancel)
        if algorithm.startswith("otb:"):
            # OTB stays a QGIS provider (delegated), but its plugin is unmaintained for
            # QGIS 4 and easy to leave unconfigured. Turn the cryptic "algorithm not
            # found" into an actionable message when the provider isn't set up.
            try:
                return self._inner.run_raw(
                    algorithm,
                    params,
                    input_layer=input_layer,
                    progress=progress,
                    cancel=cancel,
                )
            except OpError as exc:
                if (
                    "not found" in str(exc).lower()
                    or "not available" in str(exc).lower()
                ):
                    raise OpError(
                        f"{exc} — OTB may be unconfigured: install the OTB provider plugin "
                        "and set the OTB folder + application folder (Processing → Options → "
                        "Providers → OTB). See docs/guide/pdal-lastools-qgis4.md.",
                        algorithm=algorithm,
                        backend="otb",
                    ) from exc
                raise
        return self._inner.run_raw(
            algorithm, params, input_layer=input_layer, progress=progress, cancel=cancel
        )

    def render_call(
        self,
        algorithm: str,
        params: dict,
        *,
        input_param=None,
        input_layer: Layer | None = None,
        output_param=None,
    ) -> str:
        """Journal echo: a copy-pasteable CLI line for our ids; else the wrapped
        backend's ``processing.run(...)`` echo."""
        if algorithm.startswith(SAGA_PREFIX):
            library, tool = self._parse_saga_id(algorithm)
            parts = [self._saga_cmd, library, tool]
            for k, v in params.items():
                if not k.startswith("_"):
                    parts += self._saga_flag(k, v)
            return " ".join(parts)
        if algorithm.startswith(PDAL_PREFIX):
            cmd = algorithm[len(PDAL_PREFIX) :]
            parts = [os.path.basename(self._pdal_wrench), cmd]
            parts += [self._pdal_flag(k, v) for k, v in params.items()]
            return " ".join(parts)
        return self._inner.render_call(
            algorithm,
            params,
            input_param=input_param,
            input_layer=input_layer,
            output_param=output_param,
        )

    # --- SAGA branch ---------------------------------------------------------

    def _run_saga(self, algorithm, params, input_layer, progress, cancel):
        library, tool = self._parse_saga_id(algorithm)
        flags = {k: v for k, v in params.items() if not k.startswith("_")}
        in_flag = params.get(_IN_KEY)
        out_flag = params.get(_OUT_KEY)
        out_ext = str(params.get(_OUTEXT_KEY, ".tif"))

        argv = [
            self._resolve(self._saga_cmd, "saga_cmd", "SAGA (`apt install saga`)"),
            library,
            tool,
        ]
        if in_flag is not None:
            self._check_name(in_flag, "input flag (_in)")
            src = self._source_of(input_layer)
            if src is None:
                raise OpError(
                    f"`{algorithm}` has `_in={in_flag}` but no upstream layer to feed it",
                    algorithm=algorithm,
                    backend="saga-cli",
                )
            argv += [f"-{in_flag}", src]
        out_path = None
        if out_flag is not None:
            self._check_name(out_flag, "output flag (_out)")
            out_path = self._temp_path(out_ext)
            argv += [f"-{out_flag}", out_path]
        for key, value in flags.items():
            self._check_name(key, "parameter")
            argv += self._saga_flag(key, value)

        if progress:
            progress(f"   saga_cmd {library} {tool}")
        # SAGA's tool ids (library + index/name) drift between versions, so on failure
        # surface the detected version and nudge the user to check the id for it.
        ver = self._tool_version(argv[0], "saga")
        hint = (
            (
                f"detected SAGA {ver}; tool ids differ between SAGA versions — verify "
                f"`saga:{library}:{tool}` (prefer tool *names* over indices) with "
                f"`saga_cmd {library}`"
            )
            if ver
            else ""
        )
        self._spawn(argv, algorithm, cancel, "saga-cli", hint=hint)
        if out_path is None:
            return None
        self._require_output(out_path, algorithm, "saga-cli")
        facet = (
            "raster"
            if os.path.splitext(out_path)[1].lower() in _RASTER_EXT
            else "vector"
        )
        return Layer(SOURCE, out_path, facet=facet, name=algorithm)

    # --- PDAL (pdal_wrench) branch -------------------------------------------

    def _run_pdal(self, algorithm, params, input_layer, progress, cancel):
        cmd = algorithm[len(PDAL_PREFIX) :]
        spec = _PDAL_COMMANDS.get(cmd)
        if spec is None:
            raise OpError(
                f"unknown pdal_wrench command {cmd!r}. Supported: "
                + ", ".join(sorted(_PDAL_COMMANDS)),
                algorithm=algorithm,
                backend="pdal-cli",
            )
        out_ext, facet = spec
        flags = dict(params)
        # `merge` takes its inputs as positional files, not --input. `files="a.las;b.las"`
        # (semicolon- or newline-separated) expands to positional argv tokens.
        positional = []
        files = flags.pop("files", None)
        if files is not None:
            # niva expands a `;`-joined value into a list; a single value stays a string.
            raw = (
                files
                if isinstance(files, (list, tuple))
                else re.split(r"[;\n]", str(files))
            )
            for f in raw:
                f = expand_path(str(f).strip())
                if not f:
                    continue
                if f.startswith("-"):  # never let a path be read as an option
                    raise OpError(
                        f"invalid input path {f!r}",
                        algorithm=algorithm,
                        backend="pdal-cli",
                    )
                positional.append(f)
        # Auto-wire the pipe: --input from the upstream layer, --output to a scratch path
        # (unless the flow gave an explicit one — used to persist a .laz product).
        if not positional and "input" not in flags:
            src = self._source_of(input_layer)
            if src is None:
                raise OpError(
                    f"`{algorithm}` needs `input=<path>`, `files=…`, or an upstream layer",
                    algorithm=algorithm,
                    backend="pdal-cli",
                )
            flags["input"] = src
        out_path = flags.get("output") or self._temp_path(out_ext)
        flags["output"] = out_path

        argv = [
            self._resolve(
                self._pdal_wrench,
                "pdal_wrench",
                "PDAL wrench (conda-forge `pdal_wrench`) + $QGIS_WRENCH_EXECUTABLE",
            ),
            cmd,
        ]
        for key, value in flags.items():
            self._check_pdal_key(key)
            argv.append(self._pdal_flag(key, value))
        argv += positional  # merge's input files go after the flags

        if progress:
            progress(f"   pdal_wrench {cmd}")
        self._spawn(argv, algorithm, cancel, "pdal-cli")
        self._require_output(out_path, algorithm, "pdal-cli")
        # Raster/vector products ARE loadable by QGIS — return a real layer so they pipe
        # into `save` and downstream QGIS algorithms. Point clouds are not loadable here,
        # so hand back a path handle (chains to the next pdalcli stage, or is persisted via
        # an explicit `output=`).
        if facet in ("raster", "vector"):
            try:
                return self._inner.load(out_path)
            except Exception:  # noqa: BLE001 — fall back to a path handle
                return Layer(SOURCE, out_path, facet=facet, name=algorithm)
        return Layer(SOURCE, out_path, facet="pointcloud", name=algorithm)

    # --- id parsing / validation ---------------------------------------------

    def _parse_saga_id(self, algorithm: str) -> tuple[str, str]:
        bits = algorithm[len(SAGA_PREFIX) :].split(":")
        if len(bits) != 2 or not all(bits):
            raise OpError(
                f"SAGA id must be `saga:<library>:<tool>` (got {algorithm!r}); "
                "e.g. `saga:ta_morphometry:0`",
                algorithm=algorithm,
                backend="saga-cli",
            )
        library, tool = bits
        self._check_name(library, "library")
        if not _TOOL_RE.match(tool):
            raise OpError(
                f"invalid SAGA tool {tool!r} — a tool index (e.g. 0) or a name",
                algorithm=algorithm,
                backend="saga-cli",
            )
        return library, tool

    @staticmethod
    def _check_name(name: str, what: str) -> None:
        if not _NAME_RE.match(str(name)):
            raise OpError(
                f"invalid SAGA {what} {name!r} — must match [A-Za-z][A-Za-z0-9_]*",
                backend="saga-cli",
            )

    @staticmethod
    def _check_pdal_key(key: str) -> None:
        if not _PDAL_KEY_RE.match(str(key)):
            raise OpError(
                f"invalid pdal_wrench flag {key!r} — must match [a-z][a-z0-9_]*",
                backend="pdal-cli",
            )

    # --- flag rendering ------------------------------------------------------

    @staticmethod
    def _saga_flag(key: str, value) -> list[str]:
        if isinstance(value, bool):
            return [f"-{key}", "1" if value else "0"]
        return [f"-{key}", str(value)]

    @staticmethod
    def _pdal_flag(key: str, value) -> str:
        # wrench takes `--key=value`; a bare `--key` for a present boolean.
        if isinstance(value, bool):
            return f"--{key}" if value else f"--{key}=false"
        return f"--{key}={value}"

    # --- process + fs helpers ------------------------------------------------

    @staticmethod
    def _source_of(layer: Layer | None) -> str | None:
        """The on-disk path/URI of an upstream layer. A string ref is used as-is; a live
        QgsMapLayer reports ``.source()``. A pure in-memory layer has no file for a CLI
        tool to read, so this returns None and the caller errors."""
        if layer is None:
            return None
        ref = layer.ref
        if isinstance(ref, str):
            return ref
        getter = getattr(ref, "source", None)
        return getter() if callable(getter) else None

    def _resolve(self, exe: str, name: str, install_hint: str) -> str:
        found = (
            shutil.which(exe)
            if os.path.basename(exe) == exe
            else (exe if os.path.exists(exe) else None)
        )
        if not found:
            raise OpError(
                f"`{name}` not found ({exe!r}). Install {install_hint}, or set the "
                f"matching env var to its path.",
                backend="native-cli",
            )
        return found

    def _temp_path(self, ext: str) -> str:
        if not ext.startswith("."):
            ext = "." + ext
        # The scratch dir may be a bespoke NIVA_TMPDIR that doesn't exist yet (unlike the
        # QGIS path, which makes its own temp). Create it so mkstemp doesn't FileNotFound.
        os.makedirs(self._scratch, exist_ok=True)
        fd, path = tempfile.mkstemp(
            prefix="niva-native-", suffix=ext, dir=self._scratch
        )
        os.close(fd)
        os.unlink(path)  # the tool writes it; we only needed a unique name
        return path

    @staticmethod
    def _require_output(path: str, algorithm: str, backend: str) -> None:
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            raise OpError(
                f"`{algorithm}` produced no output at {path}",
                algorithm=algorithm,
                backend=backend,
            )

    def _spawn(
        self, argv: list[str], algorithm: str, cancel, backend: str, hint: str = ""
    ) -> None:
        try:
            proc = subprocess.run(argv, shell=False, capture_output=True, text=True)
        except OSError as exc:
            raise OpError(
                f"could not launch {argv[0]}: {exc}",
                algorithm=algorithm,
                backend=backend,
            ) from exc
        if cancel and cancel():
            raise OpError(
                f"`{algorithm}` canceled", algorithm=algorithm, backend=backend
            )
        if proc.returncode != 0:
            # The tool prints the real reason; surface the tail, not a traceback, and never
            # echo the full argv (may hold paths) into the message. ``hint`` adds
            # version/setup context for the version-churny engines (SAGA).
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = tail[-1] if tail else f"exit code {proc.returncode}"
            msg = f"`{algorithm}` failed: {detail}"
            if hint:
                msg += f" [{hint}]"
            raise OpError(msg, algorithm=algorithm, backend=backend)


# Back-compat alias — the SAGA-only name the first prototype shipped under.
SagaCliBackend = NativeToolBackend


def wrap_native(backend):
    """Wrap ``backend`` in the native-CLI harness so ``saga:*`` and ``pdalcli:*`` ids
    resolve. Transparent for every other id. Call at backend-construction time."""
    return NativeToolBackend(backend)
