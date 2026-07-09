"""The binder (docs/planning/07-§4–5).

Turn a parsed ``Stage`` plus its ``Alias`` into a ``BoundOp``: the algorithm id and
a fully-resolved parameter dict for ``processing.run`` — *except* the primary input
and output, whose param names are returned separately for the engine to fill at run
time (it alone knows the upstream layer and the temp/save destination).

This layer is pure Python and QGIS-free: it does the static work (split flags from
positionals, coerce by type, apply defaults, force fixed values, validate
arity/options) so the engine and backend stay thin. Errors are ``FlowError`` —
they are the user's flow-authoring mistakes (unknown option, missing value, bad
enum word), reported with the stage's line and text (02-§6).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..errors import FlowError
from ..values import Distance
from .model import Alias

_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_DISTANCE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*([a-zA-Z]*)$")
# Linear/angular units niva understands; the engine resolves these against the
# layer CRS at run time (03-§1.1). `None` unit = "in the layer's own CRS units".
_UNITS = {"m", "km", "cm", "mm", "ft", "yd", "mi", "nmi", "deg"}


@dataclass
class BoundOp:
    algorithm: str
    params: dict
    input_param: str
    output_param: str
    # Param names bound from a `layer`-typed arg/option — a secondary layer (e.g. clip's
    # OVERLAY, spatialjoin's JOIN). The engine resolves a `@conn.table` value here into a
    # loaded layer (the binder is QGIS-free and can't); a plain path passes straight through.
    layer_params: frozenset = field(default_factory=frozenset)
    # Param names bound from a `crs`-typed arg/option (reproject's TARGET_CRS, warp's
    # SOURCE/TARGET_CRS, …). The engine asks the backend to validate each value before running,
    # so an unknown CRS (e.g. `EPSG:99999`) fails closed instead of silently producing a layer
    # with an invalid/empty CRS.
    crs_params: frozenset = field(default_factory=frozenset)


def bind(stage, alias: Alias) -> BoundOp:
    params: dict = {}

    # 1. Split the parser's undifferentiated args into flags and positionals.
    positionals = []
    for arg in stage.args:
        flag = alias.flags.get(arg)
        if flag is not None:
            params[flag.param] = True
        else:
            positionals.append(arg)

    # 2. Bind positionals in order; enforce required / arity.
    for i, spec in enumerate(alias.args):
        if i < len(positionals):
            params[spec.param] = _coerce(
                positionals[i], spec.type, None, stage, spec.name
            )
        elif spec.required:
            raise FlowError(
                f"`{stage.verb}` needs a `{spec.name}` value",
                line=stage.line,
                stage=stage.raw,
            )
    extra = positionals[len(alias.args) :]
    if extra:
        joined = ", ".join(repr(x) for x in extra)
        raise FlowError(
            f"`{stage.verb}` got unexpected value(s): {joined}",
            line=stage.line,
            stage=stage.raw,
        )

    # 3. Bind options.
    for key, value in stage.options.items():
        spec = alias.options.get(key)
        if spec is None:
            valid = sorted(alias.options) + sorted(alias.flags)
            hint = ", ".join(valid) if valid else "(none)"
            raise FlowError(
                f"`{stage.verb}` has no option `{key}` — valid: {hint}",
                line=stage.line,
                stage=stage.raw,
            )
        params[spec.param] = _coerce(value, spec.type, spec.values, stage, key)

    # 4. Required options must be present.
    for key, spec in alias.options.items():
        if spec.required and spec.param not in params:
            raise FlowError(
                f"`{stage.verb}` needs option `{key}=…`",
                line=stage.line,
                stage=stage.raw,
            )

    # 5. Defaults for omitted options.
    for spec in alias.options.values():
        if spec.param not in params and spec.default is not None:
            params[spec.param] = _coerce(
                spec.default, spec.type, spec.values, stage, ""
            )

    # 6. Flags default to False.
    for spec in alias.flags.values():
        params.setdefault(spec.param, False)

    # 7. Forced values are literal (never coerced) and always win.
    params.update(alias.forced)

    # Secondary path-bearing inputs — a filesystem path or a `@conn.table` ref. The engine
    # `~`/`$VAR`-expands the path form and loads the `@conn` form (see `_resolve_layer_refs`).
    # Covers overlay/mask *layers* (clip, intersect, spatialjoin `with=`) AND *raster*/*vector*
    # option inputs (zonalstats `raster=`, joins) so all of them expand env vars alike.
    _PATH_TYPES = ("layer", "raster", "vector")
    layer_params = {
        s.param for s in alias.args if s.type in _PATH_TYPES and s.param in params
    }
    layer_params |= {
        s.param
        for s in alias.options.values()
        if s.type in _PATH_TYPES and s.param in params
    }
    crs_params = {s.param for s in alias.args if s.type == "crs" and s.param in params}
    crs_params |= {
        s.param for s in alias.options.values() if s.type == "crs" and s.param in params
    }
    return BoundOp(
        alias.algorithm,
        params,
        alias.primary_input,
        alias.primary_output,
        frozenset(layer_params),
        frozenset(crs_params),
    )


# --- coercion --------------------------------------------------------------


def _coerce(value: str, type_: str, values, stage, what: str):
    if type_ == "distance":
        return _distance(value, stage, what)
    if type_ in ("number", "int"):
        return _number(value, type_, stage, what)
    if type_ == "enum":
        return _enum(value, values, stage, what)
    if type_ == "enumlist":
        return [_enum(v, values, stage, what) for v in _split(value)]
    if type_ in ("fields", "list"):
        return _split(value)
    if type_ in ("layer", "raster"):
        # A dataset path: expand a leading ~ so `clip "~/aoi.gpkg"` works like
        # `load "~/aoi.gpkg"` (QGIS/GDAL don't expand ~). An already-absolute path or a
        # `@connection.table` reference has no leading ~, so it passes through unchanged.
        return os.path.expanduser(value)
    # crs, field, string, expression — passed through verbatim.
    return value


def _distance(value: str, stage, what: str) -> Distance:
    m = _DISTANCE.match(value)
    if not m:
        raise FlowError(
            f"`{stage.verb}`: expected a distance for `{what}`, got `{value}`",
            line=stage.line,
            stage=stage.raw,
        )
    unit = m.group(2) or None
    if unit is not None and unit not in _UNITS:
        raise FlowError(
            f"`{stage.verb}`: unknown unit `{unit}` in `{value}` — use one of: "
            + ", ".join(sorted(_UNITS)),
            line=stage.line,
            stage=stage.raw,
        )
    return Distance(float(m.group(1)), unit)


def _number(value: str, type_: str, stage, what: str):
    if not _NUMBER.match(value):
        raise FlowError(
            f"`{stage.verb}`: expected a number for `{what}`, got `{value}`",
            line=stage.line,
            stage=stage.raw,
        )
    return int(value) if type_ == "int" else float(value)


def _enum(word: str, values, stage, what: str) -> int:
    if values is None or word not in values:
        valid = ", ".join(values) if values else "(none)"
        raise FlowError(
            f"`{stage.verb}`: `{word}` is not a valid value for `{what}` — use one of: {valid}",
            line=stage.line,
            stage=stage.raw,
        )
    return values[word]


def _split(value: str) -> list:
    return [part.strip() for part in value.split(",") if part.strip()]
