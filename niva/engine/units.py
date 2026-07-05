"""Distance → CRS-units resolution (docs/planning/03-§1.1).

The one rule that matters: **niva never silently buffers in degrees and never
silently reprojects.** A linear distance (``100m``) on a geographic CRS is a hard
error telling the user to reproject or to ask for degrees explicitly. A bare number
(no unit) is taken in the layer's own CRS units, whatever they are.
"""

from __future__ import annotations

from ..errors import FlowError
from ..values import Distance

# One linear unit in metres. (Angular `deg` is handled separately — it only makes
# sense on a geographic CRS and is never converted to metres.)
UNIT_TO_M = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
    "nmi": 1852.0,
}


def resolve_distance(dist: Distance, crs, *, stage=None) -> float:
    """Return the distance expressed in ``crs``'s own units, or raise FlowError."""
    line = getattr(stage, "line", 0)
    raw = getattr(stage, "raw", "")

    if dist.unit is None:
        # No unit given: trust the number as already being in the CRS's units.
        return dist.value

    if dist.unit == "deg":
        if not crs.is_geographic:
            raise FlowError(
                f"a distance in degrees (`{dist.value}deg`) needs a geographic CRS, "
                f"but the layer is in {crs.authid} ({crs.map_units})",
                line=line,
                stage=raw,
            )
        return dist.value

    # A linear unit (m/km/ft/…).
    if crs.is_geographic:
        raise FlowError(
            f"`{dist.value}{dist.unit}` is a linear distance, but the layer is in "
            f"{crs.authid} (degrees). Reproject to a projected CRS first, or give the "
            f"distance in `deg` — niva will not silently buffer in degrees.",
            line=line,
            stage=raw,
        )

    metres = dist.value * UNIT_TO_M[dist.unit]
    return metres / crs.units_to_meters
