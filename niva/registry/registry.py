"""Registry lookup (docs/planning/07-§3). Verb → ``Alias``, with duplicate detection."""

from __future__ import annotations

from .definitions import CORE
from .model import Alias


class Registry:
    def __init__(self, aliases):
        self._by_verb: dict = {}
        for a in aliases:
            if a.verb in self._by_verb:
                raise ValueError(f"duplicate verb in registry: {a.verb!r}")
            self._by_verb[a.verb] = a

    def get(self, verb: str) -> Alias | None:
        """Return the alias for ``verb``, or ``None`` if it is not an alias verb
        (it may still be a built-in — that is the engine's call, not ours)."""
        return self._by_verb.get(verb)

    def __contains__(self, verb: str) -> bool:
        return verb in self._by_verb

    def verbs(self) -> list:
        return sorted(self._by_verb)


def core_registry() -> Registry:
    """The built-in core alias set (``definitions.CORE``)."""
    return Registry(CORE)
