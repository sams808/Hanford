"""
qt_figure_composer.py — the Figure Composer workspace: a gallery of plot
snapshots captured (via each PlotWidget's "-> Figure Composer" toolbar
button, anywhere in Ember) into composer_store.store, arranged into a
labeled multi-panel grid and exported at a chosen physical size/DPI.

Layout pattern borrowed from qt_vitrification_oxide.py (left-controls/
right-preview QSplitter). The actual grid compositing is
figure_composer.compose_figure(); the pure layout/label math it calls is
in compose_science.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)

import compose_science as csci
import figure_composer as fcomp
from composer_store import store
from data_model import HanfordDataset
from qt_widgets import PlotWidget


class FigureComposerPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self._build_ui()
        store.changed.connect(self._refresh_gallery)
        self._refresh_gallery()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left.setObjectName("Card")
        left.setMaximumWidth(380)
        ll = QVBoxLayout(left)
        title = QLabel("Figure Composer")
        title.setObjectName("SectionTitle")
        ll.addWidget(title)
        note = QLabel('Click "→ Figure Composer" on any plot\'s toolbar, anywhere in Ember, to add it here.')
        note.setWordWrap(True)
        note.setObjectName("SectionNote")
        ll.addWidget(note)

        self.gallery_list = QListWidget()
        self.gallery_list.setIconSize(QSize(110, 82))
        self.gallery_list.currentRowChanged.connect(self._on_selection_changed)
        ll.addWidget(self.gallery_list, 1)

        row_btns = QHBoxLayout()
        up_btn = QPushButton("Move up")
        up_btn.clicked.connect(lambda: self._move(-1))
        row_btns.addWidget(up_btn)
        down_btn = QPushButton("Move down")
        down_btn.clicked.connect(lambda: self._move(1))
        row_btns.addWidget(down_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_selected)
        row_btns.addWidget(remove_btn)
        ll.addLayout(row_btns)

        caption_row = QHBoxLayout()
        caption_row.addWidget(QLabel("Caption"))
        self.caption_edit = QLineEdit()
        self.caption_edit.setEnabled(False)
        self.caption_edit.editingFinished.connect(self._apply_caption_edit)
        caption_row.addWidget(self.caption_edit)
        ll.addLayout(caption_row)

        clear_btn = QPushButton("Clear all panels")
        clear_btn.clicked.connect(self._clear_all)
        ll.addWidget(clear_btn)

        ll.addWidget(QLabel("Layout"))
        cols_row = QHBoxLayout()
        cols_row.addWidget(QLabel("Columns (0 = auto)"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(0, 8)
        self.cols_spin.valueChanged.connect(self._rebuild_preview)
        cols_row.addWidget(self.cols_spin)
        ll.addLayout(cols_row)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Panel labels"))
        self.label_style_combo = QComboBox()
        self.label_style_combo.addItems(csci.LABEL_STYLES)
        self.label_style_combo.currentTextChanged.connect(self._rebuild_preview)
        label_row.addWidget(self.label_style_combo)
        ll.addLayout(label_row)

        fontsize_row = QHBoxLayout()
        fontsize_row.addWidget(QLabel("Label size"))
        self.label_size_spin = QSpinBox()
        self.label_size_spin.setRange(6, 36)
        self.label_size_spin.setValue(14)
        self.label_size_spin.valueChanged.connect(self._rebuild_preview)
        fontsize_row.addWidget(self.label_size_spin)
        ll.addLayout(fontsize_row)

        ll.addWidget(QLabel("Export size (cm)"))
        size_row = QHBoxLayout()
        self.export_w_spin = QDoubleSpinBox()
        self.export_w_spin.setRange(1.0, 100.0)
        self.export_w_spin.setValue(18.0)
        size_row.addWidget(self.export_w_spin)
        size_row.addWidget(QLabel("x"))
        self.export_h_spin = QDoubleSpinBox()
        self.export_h_spin.setRange(1.0, 100.0)
        self.export_h_spin.setValue(12.0)
        size_row.addWidget(self.export_h_spin)
        ll.addLayout(size_row)

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("Export DPI"))
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        dpi_row.addWidget(self.dpi_spin)
        ll.addLayout(dpi_row)

        export_btn = QPushButton("Export figure…")
        export_btn.setObjectName("Primary")
        export_btn.clicked.connect(self.export_figure)
        ll.addWidget(export_btn)
        ll.addStretch(1)
        splitter.addWidget(left)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        pass  # Figure Composer works on captured plot snapshots, not the dataset directly.

    # ------------------------------------------------------------------
    def _refresh_gallery(self) -> None:
        current = self.gallery_list.currentRow()
        self.gallery_list.blockSignals(True)
        self.gallery_list.clear()
        for item in store.items():
            list_item = QListWidgetItem(item.caption or "(untitled)")
            pixmap = QPixmap()
            pixmap.loadFromData(item.png_bytes)
            list_item.setIcon(QIcon(pixmap))
            self.gallery_list.addItem(list_item)
        n = self.gallery_list.count()
        if n:
            self.gallery_list.setCurrentRow(min(max(current, 0), n - 1))
        self.gallery_list.blockSignals(False)
        self._on_selection_changed(self.gallery_list.currentRow())
        self._rebuild_preview()

    def _selected_index(self) -> Optional[int]:
        row = self.gallery_list.currentRow()
        return row if 0 <= row < len(store.items()) else None

    def _on_selection_changed(self, row: int) -> None:
        items = store.items()
        if 0 <= row < len(items):
            self.caption_edit.setEnabled(True)
            self.caption_edit.setText(items[row].caption)
        else:
            self.caption_edit.setEnabled(False)
            self.caption_edit.clear()

    def _move(self, delta: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        store.move(idx, delta)
        self.gallery_list.setCurrentRow(idx + delta)

    def _remove_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        store.remove(idx)

    def _apply_caption_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        store.set_caption(idx, self.caption_edit.text())

    def _clear_all(self) -> None:
        if not store.items():
            return
        reply = QMessageBox.question(
            self, "Clear all panels", "Remove every panel from the Figure Composer?",
        )
        if reply == QMessageBox.Yes:
            store.clear()

    # ------------------------------------------------------------------
    def _rebuild_preview(self) -> None:
        fcomp.compose_figure(
            self.plot, store.items(), cols=self.cols_spin.value(),
            label_style=self.label_style_combo.currentText(),
            label_fontsize=self.label_size_spin.value(),
        )

    def export_figure(self) -> None:
        if not store.items():
            QMessageBox.information(self, "Export", "Add at least one panel first (see the note above the gallery).")
            return
        from PySide6.QtCore import QSettings
        from qt_help import APP_NAME
        settings = QSettings(APP_NAME, APP_NAME)
        last_dir = settings.value("composer_last_export_dir", "", type=str)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export figure", last_dir, "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tiff)",
        )
        if not path:
            return
        settings.setValue("composer_last_export_dir", str(Path(path).resolve().parent))
        self.plot.export_at_size_cm(path, self.export_w_spin.value(), self.export_h_spin.value(), dpi=self.dpi_spin.value())
        QMessageBox.information(self, "Export complete", f"Saved {path}")
