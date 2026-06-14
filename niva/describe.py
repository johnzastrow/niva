"""`describe` — introspection for niva verbs and QGIS algorithms (planning 11).

`describe <verb>` shows how a niva alias maps to a QGIS algorithm (positional args,
options with defaults/enums, flags) — pure, no QGIS needed. `describe <algorithm-id>`
(anything containing ``:``) introspects the live QGIS algorithm: its parameters
(name, type, optional, default) and outputs. This makes the `run <id> KEY=value`
escape hatch discoverable — describe an algorithm, then `run` it.
"""

from __future__ import annotations

from .errors import FlowError
from .registry import core_registry


def describe(name: str) -> str:
    reg = core_registry()
    alias = reg.get(name)
    if alias is not None:
        return _format_alias(alias)
    if ":" in name:  # an algorithm id, e.g. native:buffer / gdal:warpreproject
        from .engine.pyqgis import algorithm_info, ensure_qgis

        ensure_qgis()
        info = algorithm_info(name)
        if info is None:
            raise FlowError(f"no algorithm `{name}` is installed in this QGIS")
        return _format_algorithm(info)
    raise FlowError(
        f"`{name}` is neither a niva verb nor an algorithm id (those contain `:`).\n"
        f"Known verbs: {', '.join(reg.verbs())}"
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
        desc = f' — {p["description"]}' if p["description"] else ""
        lines.append(f"    {p['name']} ({', '.join(notes)}){desc}")
    if info["outputs"]:
        lines.append("  outputs:")
        for o in info["outputs"]:
            lines.append(f"    {o['name']} ({o['type']})")
    return "\n".join(lines)
