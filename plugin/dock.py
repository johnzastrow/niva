"""The niva dock — a flow editor with Run / Dry-run, output, and map integration.

All Qt access goes through ``qgis.PyQt`` so it works on QGIS 3 (Qt5) and QGIS 4
(Qt6). Flows run in-process on the GUI thread (v0.1): fine for interactive work;
long jobs block the UI — threading is a later increment (cf. Oscar A9: flows are
serial within a process anyway).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from qgis.PyQt.QtGui import QFont, QPalette
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import environment, runner

# Persisted settings keys (QgsSettings) and the default run-log folder.
_LOG_ENABLED_KEY = "niva/log_enabled"
_LOG_DIR_KEY = "niva/log_dir"


def default_log_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "niva_logs")

_SAMPLE = """\
# Edit this flow, then click Run — it executes in this QGIS session.
# A GeoPackage holds many layers, so name one with |layername=.
# Example:
#   load "/path/to/data.gpkg|layername=roads" | buffer 100m dissolve | save /tmp/out.gpkg
"""


class NivaDock(QDockWidget):
    def __init__(self, iface):
        super().__init__("niva", iface.mainWindow())
        self.iface = iface
        self.path = None  # the .niva file currently open, if any (for relative paths)
        # One log file per QGIS session: a stamp fixed for the dock's lifetime, so all
        # runs append to the same journal until the user hits Reset (new stamp). The
        # microseconds keep a Reset within the same second from reusing the file.
        self._session_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.setObjectName("NivaDock")

        tabs = QTabWidget(self)
        tabs.addTab(self._build_flow_tab(), "Flow")
        tabs.addTab(self._build_setup_tab(), "Setup")
        self.setWidget(tabs)

    def _build_flow_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        # The editor is the only thing you type into — leave it the theme's editable
        # field color (a white-ish "Base") so it reads as an input.
        self.editor = QPlainTextEdit(tab)
        self.editor.setPlainText(_SAMPLE)
        self.editor.setFont(_mono())
        layout.addWidget(self.editor, 3)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Open…", tab)
        open_btn.clicked.connect(self._open)
        self.run_btn = QPushButton("Run", tab)
        self.run_btn.clicked.connect(self._run)
        self.dry_btn = QPushButton("Dry-run", tab)
        self.dry_btn.clicked.connect(self._dry_run)
        self.cancel_btn = QPushButton("Cancel", tab)
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        clear_btn = QPushButton("Clear output", tab)
        clear_btn.clicked.connect(self._clear)
        for b in (open_btn, self.run_btn, self.dry_btn, self.cancel_btn, clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.path_label = QLabel("(unsaved flow)", tab)
        buttons.addWidget(self.path_label)
        layout.addLayout(buttons)

        # Read-only output recedes into the dialog (window colour) so it doesn't look
        # like another input — only the editor above stands out as typeable.
        self.output = QPlainTextEdit(tab)
        self.output.setReadOnly(True)
        self.output.setFont(_mono())
        _recede(self.output)
        layout.addWidget(self.output, 2)
        return tab

    def _build_setup_tab(self) -> QWidget:
        from qgis.core import QgsSettings

        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        # --- Settings: the per-session run log -------------------------------
        settings = QgsSettings()
        self.log_enabled = QCheckBox("Log each run to one file per QGIS session", tab)
        self.log_enabled.setChecked(settings.value(_LOG_ENABLED_KEY, True, type=bool))
        self.log_enabled.toggled.connect(self._on_log_enabled)
        layout.addWidget(self.log_enabled)

        row = QHBoxLayout()
        row.addWidget(QLabel("Log folder:", tab))
        self.log_dir = QLineEdit(
            settings.value(_LOG_DIR_KEY, default_log_dir(), type=str), tab
        )
        self.log_dir.editingFinished.connect(self._on_log_dir_edited)
        browse = QPushButton("Browse…", tab)
        browse.clicked.connect(self._browse_log_dir)
        row.addWidget(self.log_dir)
        row.addWidget(browse)
        layout.addLayout(row)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("Session log:", tab))
        self.session_label = QLabel(tab)
        self.session_label.setTextInteractionFlags(self.session_label.textInteractionFlags())
        reset = QPushButton("Reset (new file)", tab)
        reset.clicked.connect(self._reset_session_log)
        srow.addWidget(self.session_label, 1)
        srow.addWidget(reset)
        layout.addLayout(srow)
        self._update_session_label()

        # --- the environment report ------------------------------------------
        self.setup_view = QTextBrowser(tab)
        _recede(self.setup_view)  # a read-only report — blend with the dialog
        layout.addWidget(self.setup_view, 1)

        row = QHBoxLayout()
        refresh = QPushButton("Refresh", tab)
        refresh.clicked.connect(self._refresh_setup)
        copy = QPushButton("Copy", tab)
        copy.clicked.connect(self._copy_setup)
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addStretch(1)
        layout.addLayout(row)

        self._refresh_setup()
        return tab

    def _browse_log_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Run-log folder", self.log_dir.text())
        if chosen:
            self.log_dir.setText(chosen)
            self._on_log_dir_edited()

    def _on_log_enabled(self, value):
        from qgis.core import QgsSettings

        QgsSettings().setValue(_LOG_ENABLED_KEY, value)
        self._update_session_label()

    def _on_log_dir_edited(self):
        from qgis.core import QgsSettings

        QgsSettings().setValue(_LOG_DIR_KEY, self.log_dir.text())
        self._update_session_label()

    def _reset_session_log(self):
        """Start a fresh session log (the next run writes to a new file)."""
        self._session_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self._update_session_label()

    def _session_log_base(self):
        """The session journal base path, or None when logging is disabled."""
        from qgis.core import QgsSettings

        s = QgsSettings()
        if not s.value(_LOG_ENABLED_KEY, True, type=bool):
            return None
        folder = s.value(_LOG_DIR_KEY, default_log_dir(), type=str) or default_log_dir()
        return os.path.join(folder, f"niva-session-{self._session_id}")

    def _update_session_label(self):
        base = self._session_log_base()
        self.session_label.setText((base + ".log") if base else "(logging off)")

    def _refresh_setup(self):
        try:
            report = environment.report_markdown()
        except Exception as exc:  # safety net — never crash the dock
            self.setup_view.setPlainText(f"could not build environment report: {exc}")
            return
        try:
            self.setup_view.setMarkdown(report)  # Qt 5.14+ / Qt6 renders headings & bold
        except (AttributeError, TypeError):  # pragma: no cover — old Qt5
            self.setup_view.setPlainText(report)

    def _copy_setup(self):
        self.setup_view.selectAll()
        self.setup_view.copy()

    # --- actions -------------------------------------------------------------

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a .niva flow", "", "niva flows (*.niva);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self.editor.setPlainText(fh.read())
        except OSError as exc:
            self._log(f"could not open {path}: {exc}")
            return
        self.path = path
        self.path_label.setText(os.path.basename(path))

    def _run(self):
        self._execute(dry_run=False)

    def _dry_run(self):
        self._execute(dry_run=True)

    def _clear(self):
        self.output.clear()

    def _cancel(self):
        task = getattr(self, "_task", None)
        if task is not None:
            task.cancel()
            self._log("  canceling…")

    def _execute(self, *, dry_run: bool):
        if getattr(self, "_running", False):  # one flow at a time (Oscar A9)
            return
        text = self.editor.toPlainText()

        if dry_run:  # fast + mock — run synchronously, no background task
            self._log("$ niva --dry-run")
            try:
                result = runner.run_flow(text, file=self.path, dry_run=True)
            except Exception as exc:  # safety net — never let the dock crash QGIS
                self._log(f"niva: unexpected error: {exc}")
                return
            self._show_result(result)
            return

        # A real run goes to a background QgsTask so the QGIS UI stays responsive.
        from qgis.core import QgsApplication

        from .flowtask import NivaFlowTask

        self._running = True
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._log("$ niva run")
        self._task = NivaFlowTask(text, self.path, self._session_log_base())
        self._task.message.connect(self._on_progress)
        self._task.taskCompleted.connect(self._on_task_finished)
        self._task.taskTerminated.connect(self._on_task_finished)
        QgsApplication.taskManager().addTask(self._task)

    def _on_task_finished(self):
        """Runs on the main thread when the background flow ends — safe to touch the map."""
        task = getattr(self, "_task", None)
        self._running = False
        self._task = None
        self.run_btn.setEnabled(True)
        self.dry_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if task is None or task.result is None:
            self._log("niva: run produced no result")
            return
        self._show_result(task.result)

    def _show_result(self, result: dict):
        if result["ok"]:
            self._log(result["summary"])
            if result.get("layer") is not None:
                self._add_to_map(result["layer"])
        else:
            self._log(f"niva: {result['error']}")
        if result.get("elapsed") is not None:
            self._log(f"  ({_fmt_secs(result['elapsed'])})")
        if result.get("log"):
            self._log(f"  log: {result['log']}")

    def _on_progress(self, message: str):
        # Delivered on the main thread via the task's queued signal — safe to update.
        self.output.appendPlainText(message)

    # --- map integration -----------------------------------------------------

    def _add_to_map(self, layer):
        """Add the flow's final layer to the project so results land on the map."""
        from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

        ref = getattr(layer, "ref", None)
        added = None
        if isinstance(ref, str):  # a saved file path
            name = os.path.splitext(os.path.basename(ref))[0]
            vec = QgsVectorLayer(ref, name, "ogr")
            added = vec if vec.isValid() else QgsRasterLayer(ref, name)
        elif ref is not None and getattr(ref, "isValid", lambda: False)():
            added = ref
        if added is not None and added.isValid():
            QgsProject.instance().addMapLayer(added)
            self._log(f"  added to map: {added.name()}")

    def _log(self, message: str):
        self.output.appendPlainText(message)


def _fmt_secs(seconds: float) -> str:
    if seconds < 1:
        return f"{round(seconds * 1000)} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _mono() -> QFont:
    font = QFont("monospace")
    try:
        font.setStyleHint(QFont.StyleHint.Monospace)  # Qt6 (QGIS 4)
    except AttributeError:  # pragma: no cover — Qt5 (QGIS 3)
        font.setStyleHint(QFont.Monospace)
    return font


def _recede(widget) -> None:
    """Make a read-only text widget blend with the dialog: paint its background with
    the window colour instead of the editable-field (Base) colour. Theme-adaptive —
    works on light and dark themes — so only the editor reads as an input."""
    try:
        base, window = QPalette.ColorRole.Base, QPalette.ColorRole.Window  # Qt6
    except AttributeError:  # pragma: no cover — Qt5
        base, window = QPalette.Base, QPalette.Window
    palette = widget.palette()
    palette.setColor(base, palette.color(window))
    widget.setPalette(palette)
