"""`describe` — introspection for niva verbs and QGIS algorithms (planning 11).

`describe <verb>` shows how a niva alias maps to a QGIS algorithm (positional args,
options with defaults/enums, flags) — pure, no QGIS needed. `describe <algorithm-id>`
(anything containing ``:``) introspects the live QGIS algorithm: its parameters
(name, type, optional, default) and outputs. This makes the `run <id> KEY=value`
escape hatch discoverable — describe an algorithm, then `run` it.

Every description ends with a runnable **example**: a curated one for verbs that carry
``example=`` in the registry, else one synthesised from the signature (so there are no
gaps). Algorithm descriptions get a synthesised ``run <id> …`` example.
"""

from __future__ import annotations

from .errors import FlowError
from .registry import core_registry

# Verbs whose input/output are rasters — so a synthesised example reads/writes .tif.
_RASTER_VERBS = frozenset(
    {"warp", "clipraster", "hillshade", "slope", "aspect", "polygonize"}
)

# A representative value per niva arg/option type, used only to synthesise an example
# flow when an alias carries no curated `example=`.
_PLACEHOLDER = {
    "distance": "100m",
    "crs": "EPSG:3857",
    "layer": "overlay.gpkg",
    "raster": "elevation.tif",
    "field": "category",
    "fields": "id,name",
    "expression": '"population > 1000"',
    "int": "10",
    "number": "1.0",
    "string": "value",
}


def _example_for(alias) -> str:
    """Synthesise a runnable example flow from an alias's signature (load → verb → save),
    used when the alias has no curated ``example=``. Generic but valid-shaped: only the
    REQUIRED args/options are filled, with a representative value per type."""
    raster = alias.verb in _RASTER_VERBS
    src, out = ("dem.tif", "out.tif") if raster else ("roads.gpkg", "out.gpkg")
    parts = [alias.verb]
    parts += [_PLACEHOLDER.get(a.type, "value") for a in alias.args if a.required]
    parts += [
        f"{key}={_PLACEHOLDER.get(opt.type, 'value')}"
        for key, opt in alias.options.items()
        if opt.required
    ]
    return f"load {src} | {' '.join(parts)} | save {out}"


def _example_for_algorithm(info: dict) -> str:
    """Synthesise a `run <id> …` example from an algorithm's required parameters (INPUT
    comes from the piped layer, OUTPUT from a temp file, so both are omitted)."""
    skip = {"INPUT", "OUTPUT"}
    req = [p for p in info["params"] if not p["optional"] and p["name"] not in skip]
    kvs = " ".join(f"{p['name']}=<{p['type']}>" for p in req)
    run = f"run {info['id']}" + (f" {kvs}" if kvs else "")
    return f"load input.gpkg | {run} | save out.gpkg"


# Built-in verbs are handled by the engine, not the alias registry, so they carry their
# own (summary, example) here — making `describe`/`search`/`docs` cover them too.
BUILTINS = {
    "load": (
        "Read a dataset (file, @conn.table, or URI) to start a flow.",
        'load "roads.gpkg|layername=primary"',
    ),
    "save": (
        "Write the current layer to a file or database table (pass-through).",
        "load roads.gpkg | buffer 50m | save buffered.gpkg as roads mode=create",
    ),
    "sql": (
        "Run SQL on a connection — SELECT pipes a layer; DDL/DML is terminal.",
        'sql @gisdb "SELECT * FROM parcels WHERE acres > 5"',
    ),
    "run": (
        "Call any QGIS algorithm directly by id with native KEY=value params.",
        "load dem.tif | run native:slope Z_FACTOR=2 | save slope.tif",
    ),
    "split": (
        "Keep only features of one geometry type (point/line/polygon).",
        "load mixed.gpkg | split line | save lines.gpkg",
    ),
    "metadata": (
        "Stamp descriptive metadata onto the layer; persisted on the next save.",
        'load roads.gpkg | metadata set title="City roads" | save roads.gpkg',
    ),
    "assess": (
        "Profile the current layer to a data-quality Markdown report (pass-through).",
        "load parcels.gpkg | assess deep to quality.md",
    ),
    "catalog": (
        "Inventory a directory of datasets to a Markdown report.",
        'catalog "data/" to=inventory.md',
    ),
    "show": (
        "List the loadable layers/tables at a file, directory, @conn, or service URL.",
        "show @gisdb.public to=tables.md",
    ),
    "info": (
        "Inspect the local QGIS environment: connections, providers, versions.",
        "info to=env.md",
    ),
    "describe": (
        "Show a verb's mapping (args, options, flags, example) or a live algorithm.",
        "describe buffer",
    ),
    "search": (
        "Fuzzy-search verbs and the QGIS algorithm catalog by keyword.",
        'search "reproject" to=matches.md',
    ),
    "docs": (
        "Search by keyword and emit the full describe for every match — your own guide.",
        "docs raster to=raster_guide.md",
    ),
    "project": (
        "Create / convert / repoint QGIS project files, or inventory one.",
        "project base.qgs to=out.qgz repoint=@gisdb",
    ),
    "style": (
        "Apply or export a layer style / metadata sidecar (pass-through).",
        "load roads.gpkg | style apply roads.qml",
    ),
    "notify": (
        "Push a message to an ntfy topic (pass-through; credentials from env).",
        'load roads.gpkg | buffer 1km | save out.gpkg | notify "done" to=alerts',
    ),
    "email": (
        "Send an email via SMTP (pass-through; credentials from env).",
        'save out.gpkg | email to=me@example.com subject="Run finished"',
    ),
    "remove": (
        "Delete a file output and its sidecar family, behind a safety gate.",
        "remove old_output.gpkg",
    ),
    "each": (
        "Run the rest of the flow once per dataset in a directory/glob (flow prefix). "
        "Optional filters (flat options, same vocabulary as `find`): ext, minsize, maxsize, "
        "newerthan, format, geom, crs, minfeatures, maxfeatures, hasfield.",
        'each "tiles/*.tif" geom=polygon minfeatures=1 | warp EPSG:3857 | save "out/{name}.tif"',
    ),
    "call": (
        "Run another .niva file inline (procedural reuse).",
        "call common/setup.niva",
    ),
}


def describe(name: str) -> str:
    reg = core_registry()
    alias = reg.get(name)
    if alias is not None:
        return _format_alias(alias)
    if name in BUILTINS:
        return _format_builtin(name)
    if ":" in name:  # an algorithm id, e.g. native:buffer / gdal:warpreproject
        # Offline-first: the packaged catalog (docs/algorithms + algorithms.json) covers the
        # 878 stock algorithms with no QGIS needed (issue #25). Fall back to live QGIS only
        # for ids the catalog doesn't have (e.g. a third-party plugin's algorithm).
        from .registry import catalog

        info = catalog.algorithm_info(name)
        if info is not None:
            return _format_algorithm(info)
        try:
            from .engine.pyqgis import algorithm_info, ensure_qgis

            ensure_qgis()
            live = algorithm_info(name)
        except Exception:  # noqa: BLE001 — QGIS unavailable; report from the catalog's view
            raise FlowError(
                f"`{name}` isn't in niva's algorithm catalog, and QGIS isn't available to "
                "check for a plugin-provided algorithm."
            ) from None
        if live is None:
            raise FlowError(f"no algorithm `{name}` is installed in this QGIS")
        return _format_algorithm(live)
    raise FlowError(
        f"`{name}` is neither a niva verb nor an algorithm id (those contain `:`).\n"
        f"Known verbs: {', '.join(reg.verbs())}"
    )


def _format_builtin(name: str) -> str:
    summary, example = BUILTINS[name]
    return "\n".join(
        [
            f"verb `{name}` (built-in)",
            f"  {summary}",
            "  example:",
            f"    {example}",
        ]
    )


def _format_alias(alias) -> str:
    lines = [f"verb `{alias.verb}` → {alias.algorithm}"]
    if alias.summary:
        lines.append(f"  {alias.summary}")
    if alias.args:
        lines.append("  positional:")
        for arg in alias.args:
            req = "required" if arg.required else "optional"
            lines.append(f"    {arg.name} ({arg.type}, {req}) → {arg.param}")
    if alias.options:
        lines.append("  options:")
        for key, opt in alias.options.items():
            bits = [opt.type]
            if opt.values:
                bits = ["|".join(opt.values)]
            if opt.required:
                bits.append("required")
            if opt.default is not None:
                bits.append(f"default {opt.default}")
            lines.append(f"    {key}=<{', '.join(bits)}> → {opt.param}")
    if alias.flags:
        lines.append("  flags:")
        for name, flag in alias.flags.items():
            lines.append(f"    {name} → {flag.param}")
    lines.append("  example:")
    lines.append(f"    {alias.example or _example_for(alias)}")
    return "\n".join(lines)


def _format_algorithm(info: dict) -> str:
    lines = [
        f'algorithm {info["id"]} — "{info["display_name"]}"  (provider: {info["provider"]})',
        "  parameters:",
    ]
    for p in info["params"]:
        notes = [p["type"]]
        if p["optional"]:
            notes.append("optional")
        if p["default"] is not None:
            notes.append(f"default {p['default']!r}")
        desc = f" — {p['description']}" if p["description"] else ""
        lines.append(f"    {p['name']} ({', '.join(notes)}){desc}")
    if info["outputs"]:
        lines.append("  outputs:")
        for o in info["outputs"]:
            lines.append(f"    {o['name']} ({o['type']})")
    lines.append("  example:")
    lines.append(f"    {_example_for_algorithm(info)}")
    return "\n".join(lines)
