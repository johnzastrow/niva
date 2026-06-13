"""niva — a concise, readable text-pipeline grammar for QGIS geoprocessing.

v0.1 (MVP, under construction). This is the pip package; the design lives in
``planning/``. The first increment implements the **grammar** layer (lexer +
parser), which is pure-Python and needs no QGIS. The registry binding, engine, and
PyQGIS backend land in subsequent increments.
"""

__version__ = "0.1.0.dev0"

from .errors import FlowError, NivaError, OpError

__all__ = ["__version__", "NivaError", "FlowError", "OpError"]
