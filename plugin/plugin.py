"""NivaPlugin — toolbar button + menu entry that toggle the niva dock.

Qt imports go through ``qgis.PyQt`` so this works on QGIS 3 (Qt5) and QGIS 4 (Qt6).
The plugin runs niva in-process (see ``runner``); nothing here launches a subprocess
or depends on an OS-specific path, so it behaves the same on Windows/macOS/Linux.
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

# QAction moved from QtWidgets (Qt5) to QtGui (Qt6); accept either.
try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover — Qt6 path
    from qgis.PyQt.QtGui import QAction

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PLUGIN_DIR, "icon.svg")

# Qt6 (QGIS 4) scopes enums (Qt.DockWidgetArea.RightDockWidgetArea); Qt5 (QGIS 3)
# exposes them flat (Qt.RightDockWidgetArea). Resolve once, both ways.
try:
    _RIGHT_DOCK = Qt.DockWidgetArea.RightDockWidgetArea
except AttributeError:  # pragma: no cover — Qt5 path
    _RIGHT_DOCK = Qt.RightDockWidgetArea


class NivaPlugin:
    MENU = "&niva"

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None

    def initGui(self):  # noqa: N802 — QGIS-required name
        self.action = QAction(QIcon(ICON_PATH), "niva", self.iface.mainWindow())
        self.action.setToolTip("niva — open the flow panel")
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU, self.action)

    def unload(self):  # noqa: N802 — QGIS-required name
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.MENU, self.action)
            self.action = None

    def toggle(self):
        if self.dock is None:
            from .dock import NivaDock

            self.dock = NivaDock(self.iface)
            self.iface.addDockWidget(_RIGHT_DOCK, self.dock)
            self.dock.visibilityChanged.connect(self._sync_action)
        else:
            self.dock.setVisible(not self.dock.isVisible())

    def _sync_action(self, visible):
        if self.action is not None:
            self.action.setChecked(visible)
