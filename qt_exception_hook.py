"""
qt_exception_hook.py — a global exception hook that shows a dialog and logs
the traceback, instead of an uncaught exception failing silently. Without
this, an exception raised inside a Qt callback is invisible to a user who
double-clicked the packaged .exe with no console attached.
"""
from __future__ import annotations

import logging
import sys
import traceback

logger = logging.getLogger("ember")


def install(app) -> None:
    from PySide6.QtWidgets import QMessageBox

    def _hook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("Unhandled exception:\n%s", tb_text)

        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Unexpected error")
        box.setText(f"{exc_type.__name__}: {exc_value}")
        box.setDetailedText(tb_text)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    sys.excepthook = _hook
