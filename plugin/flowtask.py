"""Run a niva flow in a background thread so the QGIS UI stays responsive.

Uses QgsTask (QGIS's sanctioned background-work mechanism). The flow's heavy work
(load / processing.run / save) happens in ``run()`` on a worker thread; progress
strings are emitted via a Qt **signal** (queued to the main thread, so the dock can
update widgets safely); the result dict is read by the dock in the completion slot,
which runs on the main thread (where it's safe to touch the project / map).

Flows are serial — one task at a time (the dock disables Run while one is in flight)
— honouring the "one QgsApplication, flows serial within a process" rule (Oscar A9).
The backend avoids QgsProject access so save is safe off the main thread.
"""

from __future__ import annotations

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

try:
    _CAN_CANCEL = QgsTask.Flag.CanCancel  # Qt6 (QGIS 4)
except AttributeError:  # pragma: no cover — Qt5
    _CAN_CANCEL = QgsTask.CanCancel


class NivaFlowTask(QgsTask):
    message = pyqtSignal(str)  # live progress, delivered on the main thread

    def __init__(self, text: str, file, log_base):
        super().__init__("niva flow", _CAN_CANCEL)
        self._text = text
        self._file = file
        self._log_base = log_base
        self.result = None  # runner.run_flow's dict — read by the dock when finished

    def run(self) -> bool:  # worker thread
        from . import runner

        self.result = runner.run_flow(
            self._text,
            file=self._file,
            log_base=self._log_base,
            progress=self.message.emit,  # niva calls this; the signal hops to the GUI thread
            cancel=self.isCanceled,  # QgsTask.cancel() (from the dock) flips this
        )
        return bool(self.result and self.result.get("ok"))
