"""
qt_overview.py — the Overview workspace: first sanity check of the loaded
dataset (audits + a top-N inventory chart), ported from the old app's
OverviewTab onto the new DataFrameTableView/PlotWidget infrastructure.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

import overview_science as ov
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget


def _plot_top_elements(panel: PlotWidget, df: pd.DataFrame, unit_label: str) -> None:
    panel.ax.clear()
    if df.empty:
        panel.show_message("No data for this unit yet.")
        return
    ranked = df.sort_values("TotalInventory", ascending=True)
    values = ranked["TotalInventory"].to_numpy(dtype=float)
    labels = ranked["Element"].astype(str) + " [" + ranked["Units"].astype(str) + "]"
    positive = values > 0
    if not positive.any():
        panel.show_message("No positive inventory values to plot.")
        return
    panel.ax.barh(np.array(labels)[positive], values[positive], color="#c1502e")
    panel.ax.set_xscale("log")
    panel.ax.set_xlabel(f"Total inventory ({unit_label})" if unit_label != "All" else "Total inventory")
    panel.ax.set_title("Top elements by inventory")
    panel.ax.grid(alpha=0.25, axis="x")
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


class OverviewPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Unit"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("All")
        controls.addWidget(self.unit_combo)
        controls.addWidget(QLabel("Top N"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(5, 300)
        self.top_n_spin.setValue(40)
        controls.addWidget(self.top_n_spin)
        refresh_btn = QPushButton("Refresh overview")
        refresh_btn.setObjectName("Primary")
        refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        export_btn = QPushButton("Export global debug bundle")
        export_btn.clicked.connect(self._export_debug_bundle)
        controls.addWidget(export_btn)
        root.addLayout(controls)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.tables = QTabWidget()
        self._table_views: dict[str, DataFrameTableView] = {}
        for title, max_rows in [
            ("Overview", None), ("Units", None), ("Top elements", None),
            ("Top analytes", None), ("Waste phases", None), ("Waste types", None),
            ("Tank farms", None), ("Missing", None), ("Raw preview", 250),
        ]:
            view = DataFrameTableView(title=title, max_rows_display=max_rows)
            self._table_views[title] = view
            self.tables.addTab(view, title)
        splitter.addWidget(self.tables)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset
        current_unit = self.unit_combo.currentText()
        self.unit_combo.blockSignals(True)
        self.unit_combo.clear()
        self.unit_combo.addItem("All")
        units = dataset.available_units() if dataset.is_loaded() else []
        self.unit_combo.addItems(units)
        restore_index = self.unit_combo.findText(current_unit)
        self.unit_combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self.unit_combo.blockSignals(False)
        if dataset.is_loaded():
            self.refresh(announce=False)

    def refresh(self, announce: bool = True) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Overview", "Load a dataset first.")
            return
        unit = self.unit_combo.currentText() or "All"
        top_n = self.top_n_spin.value()

        self._table_views["Overview"].set_dataframe(ov.overview(self.dataset))
        self._table_views["Units"].set_dataframe(ov.units_audit(self.dataset))
        top_elements = ov.top_elements(self.dataset, unit=unit, top_n=top_n)
        self._table_views["Top elements"].set_dataframe(top_elements)
        self._table_views["Top analytes"].set_dataframe(ov.top_analytes(self.dataset, unit=unit, top_n=top_n))
        self._table_views["Waste phases"].set_dataframe(ov.phase_audit(self.dataset))
        self._table_views["Waste types"].set_dataframe(ov.type_audit(self.dataset))
        self._table_views["Tank farms"].set_dataframe(ov.farm_audit(self.dataset))
        self._table_views["Missing"].set_dataframe(ov.missing_audit(self.dataset))
        self._table_views["Raw preview"].set_dataframe(self.dataset.raw_preview(250))

        _plot_top_elements(self.plot, top_elements, unit)
        if announce:
            self.app_window.statusBar().showMessage(f"Overview refreshed ({unit}, top {top_n}).")

    def _export_debug_bundle(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Export", "Load a dataset first.")
            return
        out_dir = ov.export_global_debug_bundle(self.dataset, extra_info=self._app_extra_info())
        QMessageBox.information(self, "Export complete", f"Debug bundle written to:\n{out_dir}")

    def _app_extra_info(self) -> dict:
        try:
            from qt_help import APP_NAME, APP_VERSION
            return {"app_name": APP_NAME, "app_version": APP_VERSION}
        except Exception:
            return {}
