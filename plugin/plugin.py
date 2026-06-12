"""NivaPlugin — a minimal stub that demonstrates the niva logo in the QGIS UI.

It adds one toolbar button (and a Plugins ▸ niva menu entry) using
`logo_04.png` as the icon, so you can see how the logo reads at toolbar size.
Clicking it opens a dialog that shows the same logo larger. This is intentionally
the smallest useful plugin shape — the niva project can grow from here if it
becomes a full QGIS plugin.

All Qt imports go through `qgis.PyQt` so the stub works on QGIS 3 (Qt5) and
QGIS 4 (Qt6).
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import QMessageBox

# QAction moved from QtWidgets (Qt5) to QtGui (Qt6); accept either.
try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover — Qt6 path
    from qgis.PyQt.QtGui import QAction

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PLUGIN_DIR, "icon.svg")  # = logos/logo.svg


class NivaPlugin:
    """Toolbar button + menu entry that show the niva logo."""

    MENU = "&niva"

    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):  # noqa: N802 — QGIS-required name
        self.action = QAction(
            QIcon(ICON_PATH), "niva — logo demo", self.iface.mainWindow()
        )
        self.action.setToolTip("niva (logo_04 demo) — click to view the logo")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU, self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.MENU, self.action)
            self.action = None

    def run(self):
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("niva")
        box.setText(
            "This is <b>logo_04</b> shown in QGIS.<br><br>"
            "The toolbar button and the <i>Plugins ▸ niva</i> menu entry both "
            "use this icon. niva is a planned PyQGIS wrapper for higher-level "
            "geoprocessing — this is just a stub to preview the branding."
        )
        pixmap = QPixmap(ICON_PATH)
        if not pixmap.isNull():
            box.setIconPixmap(
                pixmap.scaledToWidth(160, Qt.TransformationMode.SmoothTransformation)
            )
        box.exec()
