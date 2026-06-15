"""niva alias registry (docs/planning/07-alias-registry-design.md).

Verb → QGIS algorithm mapping (``definitions.CORE``), lookup (``Registry`` /
``core_registry``), the declarative model (``Alias`` / ``Arg`` / ``Option`` /
``Flag``), and the binder that resolves a parsed ``Stage`` into a ``BoundOp``.
"""

from .binder import BoundOp, bind
from .model import Alias, Arg, Flag, Option
from .registry import Registry, core_registry

__all__ = [
    "Alias",
    "Arg",
    "Option",
    "Flag",
    "Registry",
    "core_registry",
    "BoundOp",
    "bind",
]
