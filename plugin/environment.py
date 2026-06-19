"""Environment report for the plugin's Setup tab.

This is now a thin shim over `niva.environment` so the plugin's "Environment report"
button and the CLI's `info` verb share **one** implementation (see
`niva/environment.py`). niva is bundled into the plugin under `libs/`, so the import
resolves once the plugin's runner has put `libs/` on `sys.path`.
"""

from __future__ import annotations

from niva.environment import report_markdown  # noqa: F401 — re-exported for dock.py
