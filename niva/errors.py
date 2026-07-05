"""niva error types (docs/planning/02-architecture.md §6, docs/planning/11-cli-...).

Two user-facing categories: a *parse/grammar* problem (``FlowError``, exit 2) and a
*runtime* problem from an algorithm/SQL (``OpError``, exit 1). Both carry enough
context to name the failing stage — and, across ``call``s, the file + line.
"""

from __future__ import annotations


class NivaError(Exception):
    """Base class for every niva error."""


class FlowError(NivaError):
    """A parse/grammar problem. Names the stage and (file +) line. CLI exit code 2."""

    def __init__(
        self, message: str, *, line: int = 0, stage: str = "", file: str | None = None
    ):
        self.message = message
        self.line = line
        self.stage = stage
        self.file = file
        loc = []
        if file:
            loc.append(str(file))
        if line:
            loc.append(f"line {line}")
        where = f" ({', '.join(loc)})" if loc else ""
        detail = f"\n    in: {stage}" if stage else ""
        super().__init__(f"{message}{where}{detail}")


class OpError(NivaError):
    """A runtime problem from an algorithm/SQL step. CLI exit code 1."""

    def __init__(
        self,
        message: str,
        *,
        algorithm: str | None = None,
        params: dict | None = None,
        backend: str | None = None,
    ):
        self.message = message
        self.algorithm = algorithm
        self.params = params
        self.backend = backend
        super().__init__(message)
