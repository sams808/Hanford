"""
qt_tank_explorer.py — Tank Explorer workspace: tank-centric view (the
inverse of Element Explorer) -- select one or more tanks and inspect their
composition. Ported from the old app's TankTab.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

import export_utils
import plot_helpers as ph
import tank_science as tsci
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget

PLOT_VALUES = ["Inventory_sum", "Fraction_of_tank_unit_inventory"]


class TankExplorerPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self._profile_df: Optional[pd.DataFrame] = None
        self._raw_df: Optional[pd.DataFrame] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left.setMaximumWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Farm"))
        self.farm_combo = QComboBox()
        self.farm_combo.addItem("All")
        self.farm_combo.currentTextChanged.connect(lambda _: self._refresh_tank_list())
        left_layout.addWidget(self.farm_combo)
        left_layout.addWidget(QLabel("Tanks"))
        self.tank_list = QListWidget()
        self.tank_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.tank_list, 1)

        left_layout.addWidget(QLabel("Unit"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["kg", "Ci"])
        left_layout.addWidget(self.unit_combo)
        left_layout.addWidget(QLabel("Top N"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(5, 300)
        self.top_n_spin.setValue(35)
        left_layout.addWidget(self.top_n_spin)
        left_layout.addWidget(QLabel("Plot value"))
        self.value_combo = QComboBox()
        self.value_combo.addItems(PLOT_VALUES)
        left_layout.addWidget(self.value_combo)
        run_btn = QPushButton("Run tank view")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self.run)
        left_layout.addWidget(run_btn)
        export_btn = QPushButton("Export tables")
        export_btn.clicked.connect(self._export_tables)
        left_layout.addWidget(export_btn)
        splitter.addWidget(left)

        self.tables = QTabWidget()
        self.profile_view = DataFrameTableView(title="Tank composition")
        self.raw_view = DataFrameTableView(title="Raw rows (first selected tank)", max_rows_display=5000)
        self.tables.addTab(self.profile_view, "Composition")
        self.tables.addTab(self.raw_view, "Raw rows")
        splitter.addWidget(self.tables)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset
        if not dataset.is_loaded():
            self.plot.show_message("Load a dataset first.")
            return
        units = dataset.available_units()
        self.unit_combo.blockSignals(True)
        self.unit_combo.clear()
        self.unit_combo.addItems(units or ["kg", "Ci"])
        if "kg" in units:
            self.unit_combo.setCurrentText("kg")
        self.unit_combo.blockSignals(False)

        current_farm = self.farm_combo.currentText()
        self.farm_combo.blockSignals(True)
        self.farm_combo.clear()
        self.farm_combo.addItems(tsci.available_farms_with_all(dataset))
        restore = self.farm_combo.findText(current_farm)
        self.farm_combo.setCurrentIndex(restore if restore >= 0 else 0)
        self.farm_combo.blockSignals(False)
        self._refresh_tank_list()

    def _refresh_tank_list(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            return
        farm = self.farm_combo.currentText()
        tanks = tsci.tanks_in_farm(self.dataset, farm)
        self.tank_list.clear()
        self.tank_list.addItems(tanks)

    def selected_tanks(self) -> List[str]:
        return [item.text() for item in self.tank_list.selectedItems()]

    def run(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Tank Explorer", "Load a dataset first.")
            return
        tanks = self.selected_tanks()
        if not tanks:
            QMessageBox.warning(self, "No tanks", "Select one or more tanks first.")
            return
        unit = self.unit_combo.currentText() or None
        top_n = self.top_n_spin.value()
        self._profile_df = tsci.tank_profile(self.dataset, tanks, unit_filter=unit, top_n=top_n)
        self._raw_df = tsci.raw_rows_for_tank(self.dataset, tanks[0], unit_filter=unit, limit=5000)
        self.profile_view.set_dataframe(self._profile_df)
        self.raw_view.set_dataframe(self._raw_df)
        label = ", ".join(tanks[:4]) + ("..." if len(tanks) > 4 else "")
        ph.plot_grouped_tank_profile(
            self.plot, self._profile_df, self.value_combo.currentText(),
            f"Tank composition: {label}", top_n=top_n,
        )
        self.app_window.statusBar().showMessage(f"Tank view updated for {len(tanks)} tank(s).")

    def _export_tables(self) -> None:
        if self._profile_df is None and self._raw_df is None:
            QMessageBox.information(self, "Export", "Run tank view first.")
            return
        tables = {"tank_composition": self._profile_df, "raw_rows_first_selected_tank": self._raw_df}
        out_dir = export_utils.export_named_tables(self.dataset, "tank_view", tables)
        try:
            self.plot.figure.savefig(out_dir / "tank_plot.png", bbox_inches="tight", dpi=200)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Tank view exported:\n{out_dir}")
