"""
qt_figure_composer.py — the Figure Composer workspace: a gallery of plot
"recipes" captured (via each PlotWidget's "-> Figure Composer" toolbar
button, anywhere in Ember) into composer_store.store, arranged into a
labeled multi-panel grid and exported at a chosen physical size/DPI.

Each panel is a live re-render of its recipe (see composer_store.py /
figure_composer.py), not a frozen snapshot, so title, axis labels, and any
of the recipe's own keyword parameters (color mode, annotate, top-N, ...)
stay editable right up to export.

Layout pattern borrowed from qt_vitrification_oxide.py (left-controls/
right-preview QSplitter). The actual grid compositing is
figure_composer.compose_figure(); the pure layout/label math it calls is
in compose_science.py.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import compose_science as csci
import figure_composer as fcomp
from composer_store import store
from data_model import HanfordDataset
from qt_widgets import PlotWidget


def _parse_param_text(text: str) -> Any:
    """A typed Python literal (True/False/None/42/3.14/"quoted") if it
    parses as one, otherwise the raw text as a plain string -- lets users
    edit a string-valued parameter (e.g. method=pearson) without having to
    remember to type quotes."""
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


class FigureComposerPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self._thumbnail_cache: Dict[tuple, bytes] = {}
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
        left.setMaximumWidth(400)
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

        ll.addWidget(QLabel("Selected panel"))
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title"))
        self.title_edit = QLineEdit()
        self.title_edit.setEnabled(False)
        self.title_edit.setPlaceholderText("(from plot)")
        self.title_edit.editingFinished.connect(self._apply_title_edit)
        title_row.addWidget(self.title_edit, 1)
        self.hide_title_check = QCheckBox("Hide")
        self.hide_title_check.setEnabled(False)
        self.hide_title_check.toggled.connect(self._apply_title_edit)
        title_row.addWidget(self.hide_title_check)
        ll.addLayout(title_row)

        xlabel_row = QHBoxLayout()
        xlabel_row.addWidget(QLabel("X axis"))
        self.xlabel_edit = QLineEdit()
        self.xlabel_edit.setEnabled(False)
        self.xlabel_edit.setPlaceholderText("(from plot)")
        self.xlabel_edit.editingFinished.connect(self._apply_xlabel_edit)
        xlabel_row.addWidget(self.xlabel_edit)
        ll.addLayout(xlabel_row)

        ylabel_row = QHBoxLayout()
        ylabel_row.addWidget(QLabel("Y axis"))
        self.ylabel_edit = QLineEdit()
        self.ylabel_edit.setEnabled(False)
        self.ylabel_edit.setPlaceholderText("(from plot)")
        self.ylabel_edit.editingFinished.connect(self._apply_ylabel_edit)
        ylabel_row.addWidget(self.ylabel_edit)
        ll.addLayout(ylabel_row)

        params_row = QHBoxLayout()
        params_row.addWidget(QLabel("Parameters"))
        params_row.addStretch(1)
        self.reset_params_btn = QPushButton("Reset")
        self.reset_params_btn.setEnabled(False)
        self.reset_params_btn.clicked.connect(self._reset_params)
        params_row.addWidget(self.reset_params_btn)
        ll.addLayout(params_row)
        self.params_table = QTableWidget(0, 2)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params_table.horizontalHeader().setStretchLastSection(True)
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setMaximumHeight(150)
        self.params_table.setEnabled(False)
        self.params_table.itemChanged.connect(self._on_param_item_changed)
        ll.addWidget(self.params_table)

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
        splitter.addWidget(left)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        pass  # Figure Composer works on captured plot recipes, not the dataset directly.

    # ------------------------------------------------------------------
    def _thumbnail_cache_key(self, item) -> tuple:
        return (
            item.uid, id(item.render_args), id(item.render_kwargs), id(item.kwarg_overrides),
            item.title_override, item.xlabel_override, item.ylabel_override,
        )

    def _thumbnail(self, item) -> bytes:
        key = self._thumbnail_cache_key(item)
        cached = self._thumbnail_cache.get(key)
        if cached is not None:
            return cached
        png = fcomp.render_thumbnail_png(item)
        self._thumbnail_cache[key] = png
        return png

    def _refresh_gallery(self) -> None:
        current = self.gallery_list.currentRow()
        items = store.items()
        live_keys = {self._thumbnail_cache_key(item) for item in items}
        for stale_key in [k for k in self._thumbnail_cache if k not in live_keys]:
            del self._thumbnail_cache[stale_key]

        self.gallery_list.blockSignals(True)
        self.gallery_list.clear()
        for item in items:
            list_item = QListWidgetItem(item.caption or "(untitled)")
            pixmap = QPixmap()
            pixmap.loadFromData(self._thumbnail(item))
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
        selected = 0 <= row < len(items)
        for widget in (self.caption_edit, self.title_edit, self.hide_title_check,
                       self.xlabel_edit, self.ylabel_edit, self.params_table, self.reset_params_btn):
            widget.setEnabled(selected)
        if not selected:
            self.caption_edit.clear()
            self.title_edit.clear()
            self.hide_title_check.setChecked(False)
            self.xlabel_edit.clear()
            self.ylabel_edit.clear()
            self.params_table.setRowCount(0)
            return
        item = items[row]
        self.caption_edit.setText(item.caption)
        self.hide_title_check.blockSignals(True)
        self.hide_title_check.setChecked(item.title_override == "")
        self.hide_title_check.blockSignals(False)
        self.title_edit.setText(item.title_override if item.title_override else "")
        self.title_edit.setEnabled(selected and not self.hide_title_check.isChecked())
        self.xlabel_edit.setText(item.xlabel_override or "")
        self.ylabel_edit.setText(item.ylabel_override or "")
        self._populate_params_table(item)

    def _populate_params_table(self, item) -> None:
        self.params_table.blockSignals(True)
        kwargs = item.effective_kwargs()
        keys = sorted(kwargs)
        self.params_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            name_item = QTableWidgetItem(key)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.params_table.setItem(row, 0, name_item)
            value_item = QTableWidgetItem(str(kwargs[key]))
            if key in item.kwarg_overrides:
                value_item.setForeground(QColor("darkgreen"))
            self.params_table.setItem(row, 1, value_item)
        self.params_table.blockSignals(False)

    # ------------------------------------------------------------------
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

    def _apply_title_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self.title_edit.setEnabled(not self.hide_title_check.isChecked())
        if self.hide_title_check.isChecked():
            store.set_title_override(idx, "")
            return
        text = self.title_edit.text()
        store.set_title_override(idx, text if text else None)

    def _apply_xlabel_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        text = self.xlabel_edit.text()
        store.set_xlabel_override(idx, text if text else None)

    def _apply_ylabel_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        text = self.ylabel_edit.text()
        store.set_ylabel_override(idx, text if text else None)

    def _on_param_item_changed(self, table_item: QTableWidgetItem) -> None:
        if table_item.column() != 1:
            return
        idx = self._selected_index()
        if idx is None:
            return
        row = table_item.row()
        key_item = self.params_table.item(row, 0)
        if key_item is None:
            return
        value = _parse_param_text(table_item.text())
        store.set_kwarg_override(idx, key_item.text(), value)

    def _reset_params(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        store.clear_kwarg_overrides(idx)

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
