"""niva setup-core — the shared logic behind ``niva setup …`` (CLI) and the QGIS plugin's Setup
tab. See ``docs/planning/21-install-and-onboarding-design.md``.

The core does the work and returns **data** (:class:`StepResult` / :class:`EnvReport`); it never
prints, prompts, or exits. Consent lives in each UI layer, not here. Every mutating function is
idempotent, reports ``changed``, and accepts ``dry_run=True`` to preview without acting.
"""

from .core import (
    EnvReport,
    StepResult,
    detect_environment,
    install_command,
    launcher_target,
    uninstall_command,
)
from .marimo import install_marimo_qgis

__all__ = [
    "EnvReport",
    "StepResult",
    "detect_environment",
    "install_command",
    "uninstall_command",
    "launcher_target",
    "install_marimo_qgis",
]
