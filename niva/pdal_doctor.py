"""``niva pdal`` — diagnose, guide, and test the point-cloud (PDAL) backend.

niva's LiDAR verbs (``run pdal:*`` and ``run pdalcli:*``) need a PDAL backend the
rest of niva does not: the ``pdal_wrench`` executable (which the QGIS PDAL algorithms
and niva's own harness shell out to). This helper finds it, tells the user exactly how
to install it on their OS if it's missing, and runs a real end-to-end test so they know
it works before wiring it into a flow.

Design notes:
  * **No QGIS import at module load.** ``check`` must work even when QGIS's Python
    isn't on ``sys.path`` — that's the most common broken state. QGIS probing is lazy
    and optional; its absence is reported, never fatal.
  * **Security:** executables are resolved from env vars / ``PATH`` / known install
    dirs — never from user input. Every subprocess is ``shell=False`` with an explicit
    argv list. The helper *guides* installation (prints commands); it does not download
    or install software itself.
  * ``pdal_wrench`` from conda has an RPATH (``$ORIGIN/../lib``), so it needs **no**
    ``LD_LIBRARY_PATH`` — the helper deliberately does not set one (a global
    ``LD_LIBRARY_PATH`` shadows system libs for QGIS's own gdal tools).
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

WRENCH_ENV_VARS = ("QGIS_WRENCH_EXECUTABLE", "NIVA_PDAL_WRENCH")
DOCS = "docs/guide/pdal-setup.md"


def run(argv: list[str]) -> int:
    """Entry point for ``niva pdal [check|test|setup] [file.las]``."""
    action = argv[0] if argv and not argv[0].startswith("-") else "check"
    rest = argv[1:] if action in ("check", "test", "setup") else argv
    if action == "check":
        return _cmd_check()
    if action == "test":
        sample = next((a for a in rest if not a.startswith("-")), None)
        return _cmd_test(sample)
    if action == "setup":
        _print_setup(_os_key())
        return 0
    print(
        f"niva pdal: unknown action {action!r} — use check | test | setup",
        file=sys.stderr,
    )
    return 2


# --- platform + discovery ----------------------------------------------------


def _os_key() -> str:
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(s, "linux")


def _wrench_name() -> str:
    return "pdal_wrench.exe" if _os_key() == "windows" else "pdal_wrench"


def _candidate_dirs() -> list[str]:
    """Common locations where pdal_wrench lands, per platform — used only after env
    vars and PATH miss, so the report can say 'found it here, just set the env var'."""
    home = os.path.expanduser("~")
    dirs: list[str] = []
    # conda / mamba envs (all OSes)
    for base in ("micromamba", "miniforge3", "miniconda3", "mambaforge", "anaconda3"):
        dirs += glob.glob(os.path.join(home, base, "envs", "*", "bin"))
        # Windows conda puts unix-y tools under Library\bin
        dirs += glob.glob(os.path.join(home, base, "envs", "*", "Library", "bin"))
    # QGIS bundles (Windows / macOS ship pdal_wrench inside the app)
    if _os_key() == "windows":
        dirs += glob.glob(r"C:\Program Files\QGIS*\bin")
        dirs += glob.glob(r"C:\OSGeo4W\bin")
    elif _os_key() == "macos":
        dirs += glob.glob("/Applications/QGIS*.app/Contents/MacOS/bin")
    return dirs


def _find(name: str) -> tuple[str | None, str]:
    """Locate an executable. Returns (path, how) where how ∈ env var name / 'PATH' /
    directory it was found in / ''. Env vars win (that's what QGIS/niva actually read)."""
    for var in WRENCH_ENV_VARS if name == _wrench_name() else ():
        val = os.environ.get(var)
        if val and os.path.isfile(val) and os.access(val, os.X_OK):
            return val, var
    onpath = shutil.which(name)
    if onpath:
        return onpath, "PATH"
    for d in _candidate_dirs():
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand, d
    return None, ""


def _version(exe: str, args: list[str]) -> str | None:
    try:
        p = subprocess.run(
            [exe, *args], shell=False, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (p.stdout or "") + (p.stderr or "")
    return out.strip().splitlines()[0].strip() if out.strip() else None


def _qgis_pointcloud_status() -> tuple[bool | None, dict]:
    """Lazy, optional QGIS probe. Returns (qgis_importable, facts). qgis_importable is
    None when QGIS's Python isn't reachable from this interpreter (not an error here)."""
    try:
        from qgis.core import QgsApplication, QgsProviderRegistry  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — QGIS not on this Python's path
        return None, {}
    facts: dict = {}
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QgsApplication([], False)
        app.initQgis()
        provs = QgsProviderRegistry.instance().providerList()
        facts["pc_data_providers"] = [
            p for p in provs if p in ("copc", "ept", "vpc", "pdal")
        ]
        facts["reads_raw_las"] = (
            "pdal" in provs
        )  # a 'pdal' *data* provider reads raw LAS
        try:
            # Processing algorithms only register after the framework is initialized —
            # needs the bundled `processing` plugin on PYTHONPATH (…/qgis/python/plugins).
            from processing.core.Processing import Processing  # noqa: PLC0415

            Processing.initialize()
            reg = QgsApplication.processingRegistry()
            facts["pdal_algorithms"] = sum(
                1 for a in reg.algorithms() if a.id().startswith("pdal:")
            )
        except Exception:  # noqa: BLE001 — processing plugin not importable
            facts["pdal_algorithms"] = None
    except Exception as exc:  # noqa: BLE001
        facts["error"] = str(exc)[:120]
    return True, facts


# --- check -------------------------------------------------------------------


def _cmd_check() -> int:
    osk = _os_key()
    print(f"niva pdal — point-cloud backend check   (OS: {osk})\n")

    wrench, how = _find(_wrench_name())
    pdal_cli, _pdal_how = _find("pdal.exe" if osk == "windows" else "pdal")

    if wrench:
        ver = _version(wrench, ["--version"]) or "?"
        print(f"  ✓ pdal_wrench   {wrench}")
        print(f"                  {ver}")
        if how in WRENCH_ENV_VARS:
            print(f"                  found via ${how} (what QGIS/niva read) ✓")
        elif how == "PATH":
            print(
                "                  found on PATH — but QGIS reads $QGIS_WRENCH_EXECUTABLE; set it (below)"
            )
        else:
            print(f"                  found in {how}")
            print(
                "                  ⚠ not pointed to by an env var — QGIS/niva won't find it yet"
            )
    else:
        print("  ✗ pdal_wrench   NOT FOUND (env vars, PATH, or common install dirs)")

    if pdal_cli:
        print(f"  ✓ pdal (CLI)    {pdal_cli}  — for COPC indexing + the self-test")
    else:
        print(
            "  ○ pdal (CLI)    not found — optional (COPC indexing; the functional self-test)"
        )

    qgis_ok, facts = _qgis_pointcloud_status()
    if qgis_ok is None:
        print(
            "  ○ QGIS Python   not reachable from this interpreter — run under QGIS's Python"
        )
        print(
            "                  to check the pdal: provider (pdalcli: does not need it)"
        )
    else:
        n = facts.get("pdal_algorithms")
        provs = ", ".join(facts.get("pc_data_providers", [])) or "none"
        print(
            f"  ✓ QGIS PDAL     {n if n is not None else '?'} pdal: algorithms; point-cloud data providers: {provs}"
        )
        if not facts.get("reads_raw_las"):
            print(
                "                  ⚠ no raw-LAS reader — pdal: needs COPC (.copc.laz); pdalcli: reads raw .las"
            )

    print()
    # verdict + tailored next steps
    if wrench and how in WRENCH_ENV_VARS:
        print("  Verdict: ready. Try:  niva pdal test")
        return 0
    if wrench:
        print(
            "  Verdict: pdal_wrench is present but not wired. Add this to your shell rc:"
        )
        print(f"      {_export_line(wrench, osk)}")
        print("  then:  niva pdal test")
        return 0
    print("  Verdict: pdal_wrench missing — install it (no compiling needed):\n")
    _print_setup(osk)
    return 1


# --- test --------------------------------------------------------------------


def _cmd_test(sample: str | None) -> int:
    wrench, how = _find(_wrench_name())
    if not wrench:
        print(
            "niva pdal test: pdal_wrench not found — run `niva pdal check` for setup steps.",
            file=sys.stderr,
        )
        return 1
    print(f"Testing pdal_wrench: {wrench}\n")

    # 1) executes + links its libraries
    ver = _version(wrench, ["--version"])
    if not ver:
        print("  ✗ pdal_wrench does not execute (library/link problem).")
        if _os_key() == "linux":
            print(
                "    On Linux the conda binary self-locates its libs via RPATH — if this fails,"
            )
            print(
                "    the env is incomplete; recreate it: conda create -n pdal -c conda-forge pdal pdal_wrench"
            )
        return 1
    print(f"  ✓ executes: {ver}")

    # 2) end-to-end: grid a point cloud → raster
    with tempfile.TemporaryDirectory(prefix="niva-pdal-test-") as td:
        las = sample
        if las:
            if not os.path.isfile(las):
                print(f"  ✗ sample not found: {las}", file=sys.stderr)
                return 1
            print(f"  · gridding your sample: {las}")
        else:
            las = _synthesize_las(td)
            if not las:
                print("  ○ no `pdal` CLI to synthesize test data and no sample given.")
                print("    Pass a point cloud:  niva pdal test /path/to/tile.las")
                print(
                    "  → wrench executes; gridding not exercised. (Install `pdal` for a full self-test.)"
                )
                return 0
            print("  · gridding a synthetic 100×100 m cloud (via pdal readers.faux)")

        out = os.path.join(td, "dtm.tif")
        try:
            p = subprocess.run(
                [
                    wrench,
                    "to_raster",
                    f"--input={las}",
                    "--attribute=Z",
                    "--resolution=1",
                    f"--output={out}",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"  ✗ to_raster failed to launch: {exc}", file=sys.stderr)
            return 1
        if p.returncode != 0 or not (os.path.exists(out) and os.path.getsize(out) > 0):
            tail = (p.stderr or p.stdout or "").strip().splitlines()
            print(
                f"  ✗ to_raster produced no raster: {tail[-1] if tail else 'exit ' + str(p.returncode)}"
            )
            return 1
        print(f"  ✓ gridded to a {os.path.getsize(out)}-byte GeoTIFF")

    print("\n  PASS — pdal_wrench works end-to-end.")
    if how not in WRENCH_ENV_VARS:
        print("  Reminder: set $QGIS_WRENCH_EXECUTABLE so QGIS/niva flows find it:")
        print(f"      {_export_line(wrench, _os_key())}")
    return 0


def _synthesize_las(td: str) -> str | None:
    """Make a tiny LAS with the `pdal` CLI's faux reader (no input data needed).
    Returns the path, or None if the pdal CLI isn't available."""
    pdal_cli, _ = _find("pdal.exe" if _os_key() == "windows" else "pdal")
    if not pdal_cli:
        return None
    las = os.path.join(td, "faux.las")
    pipeline = os.path.join(td, "pipe.json")
    # Build the pipeline with json.dumps so the LAS path is escaped correctly on every
    # OS — a raw Windows path (C:\Users\…) written into JSON is an invalid \escape.
    stages = [
        {
            "type": "readers.faux",
            "mode": "random",
            "count": 10000,
            "bounds": "([0,100],[0,100],[70,90])",
        },
        {"type": "writers.las", "filename": las},
    ]
    with open(pipeline, "w", encoding="utf-8") as fh:
        json.dump(stages, fh)
    try:
        p = subprocess.run(
            [pdal_cli, "pipeline", pipeline],
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return las if (p.returncode == 0 and os.path.isfile(las)) else None


# --- setup guidance ----------------------------------------------------------


def _export_line(path: str, osk: str) -> str:
    if osk == "windows":
        return f'setx QGIS_WRENCH_EXECUTABLE "{path}"'
    return f'export QGIS_WRENCH_EXECUTABLE="{path}"    # add to your shell rc'


def _print_setup(osk: str) -> None:
    if osk == "windows":
        print(
            "  Windows:\n"
            "    • The official QGIS installer (qgis.org/download) usually bundles pdal_wrench —\n"
            "      if `run pdal:*` already works, you're done.\n"
            "    • Otherwise install Miniforge, then in the Miniforge Prompt:\n"
            "        conda create -y -n pdal -c conda-forge pdal pdal_wrench\n"
            '        setx QGIS_WRENCH_EXECUTABLE "%USERPROFILE%\\miniforge3\\envs\\pdal\\Library\\bin\\pdal_wrench.exe"\n'
            "      then restart QGIS."
        )
    elif osk == "macos":
        print(
            "  macOS:\n"
            "    • The official QGIS .dmg (qgis.org/download) usually bundles pdal_wrench.\n"
            "    • Otherwise (Homebrew's `pdal` lacks wrench) use conda-forge:\n"
            "        conda create -y -n pdal -c conda-forge pdal pdal_wrench\n"
            '        export QGIS_WRENCH_EXECUTABLE="$HOME/miniforge3/envs/pdal/bin/pdal_wrench"   # ~/.zshrc\n'
            '        launchctl setenv QGIS_WRENCH_EXECUTABLE "$HOME/miniforge3/envs/pdal/bin/pdal_wrench"'
        )
    else:
        print(
            "  Linux (no root, no compiling):\n"
            "    cd ~ && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba\n"
            "    export MAMBA_ROOT_PREFIX=$HOME/micromamba\n"
            "    ~/bin/micromamba create -y -p $HOME/micromamba/envs/pdal -c conda-forge pdal pdal_wrench\n"
            '    export QGIS_WRENCH_EXECUTABLE="$HOME/micromamba/envs/pdal/bin/pdal_wrench"   # add to ~/.bashrc\n'
            "    # No LD_LIBRARY_PATH needed — the binary self-locates its libs via RPATH."
        )
    print(f"\n  Full per-platform guide: {DOCS}")
