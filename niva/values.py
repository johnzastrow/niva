"""niva value types (planning/03-§1.1, 07-§5)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Distance:
    """A distance value.

    ``unit`` is ``None`` for the layer's CRS units, otherwise a suffix
    (``m`` / ``km`` / ``cm`` / ``ft`` / ``yd`` / ``mi`` / ``nmi`` / ``deg``). The
    engine converts to CRS units at runtime using the layer's CRS — and a linear
    unit on a degrees CRS is a hard error (03-§1.1). The binder never reprojects.
    """

    value: float
    unit: str | None = None
