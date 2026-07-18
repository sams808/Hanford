"""
qt_debug.py — Debug / Export workspace: a live app log viewer plus a
one-click "export everything" bundle for bug reports. Ported from the old
app's DebugTab (export global debug bundle / open output folder / clear
log), adapted to Ember's StatusLogger (a live-updating Qt log via the
`logged` signal, rather than the old app's static Tk Text widget bound
once at startup).
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

import overview_science as osci
from data_model import HanfordDataset


class DebugPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        title = QLabel("Debug / Export")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        note = QLabel("Send the exported bundle instead of the full source CSV when something needs debugging.")
        note.setObjectName("SectionNote")
        top.addWidget(note)
        top.addStretch(1)
        export_btn = QPushButton("Export global debug bundle")
        export_btn.setObjectName("Primary")
        export_btn.clicked.connect(self.export_bundle)
        top.addWidget(export_btn)
        open_btn = QPushButton("Open output folder")
        open_btn.clicked.connect(self.open_output)
        top.addWidget(open_btn)
        clear_btn = QPushButton("Clear log")
        clear_btn.clicked.connect(self.clear_log)
        top.addWidget(clear_btn)
        root.addLayout(top)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        root.addWidget(self.log_view, 1)

        logger = self.app_window.status_logger
        self.log_view.setPlainText(logger.full_text())
        logger.logged.connect(self._append_line)

    def _append_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset

    def export_bundle(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Debug / Export", "Load a dataset first.")
            return
        try:
            path = osci.export_global_debug_bundle(self.dataset)
        except Exception as exc:
            QMessageBox.critical(self, "Debug export failed", str(exc))
            return
        self.app_window.status_logger.log(f"Global debug bundle exported: {path}")
        QMessageBox.information(self, "Export complete", f"Debug bundle exported:\n{path}")

    def open_output(self) -> None:
        if self.dataset is None:
            QMessageBox.information(self, "Debug / Export", "Load a dataset first.")
            return
        self.dataset.output_root.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.dataset.output_root.resolve()))

    def clear_log(self) -> None:
        self.app_window.status_logger.clear()
        self.log_view.clear()
