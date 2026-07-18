"""
qt_tank_attributes.py — Tank Attributes workspace: browse joined tank
engineering/status metadata, independent of composition. Ported from the
old app's TankAttributesTab.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

import export_utils
import plot_helpers as ph
import tank_science as tsci
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget

CATEGORY_CHOICES = ["TankType", "TankSystem", "TankIntegrity", "TankStatus", "Ventilation", "TankFarm"]
PLOT_TYPES = ["Count by category", "Capacity by category", "DIL by category", "Integrity count"]
_PREVIEW_COLUMNS = [
    "WasteSiteId", "Analyte", "Inventory", "Units", "TankType",
    "TankSystem", "TankIntegrity", "Ventilation", "DIL_Gal",
]


class TankAttributesPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self._audit_df: Optional[pd.DataFrame] = None
        self._category = "TankType"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Group by"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(CATEGORY_CHOICES)
        controls.addWidget(self.category_combo)
        controls.addWidget(QLabel("Plot"))
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(PLOT_TYPES)
        controls.addWidget(self.plot_type_combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("Primary")
        refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        export_btn = QPushButton("Export tables")
        export_btn.clicked.connect(self._export_tables)
        controls.addWidget(export_btn)
        root.addLayout(controls)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.tables = QTabWidget()
        self._table_views: dict[str, DataFrameTableView] = {}
        for title, max_rows in [
            ("Attributes", None), ("Category audit", None),
            ("Numeric summary", None), ("Merged preview", 500),
        ]:
            view = DataFrameTableView(title=title, max_rows_display=max_rows)
            self._table_views[title] = view
            self.tables.addTab(view, title)
        splitter.addWidget(self.tables)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # currentTextChanged emits the new str -- discard it via lambda
        # rather than let it silently misalign with refresh()'s bool param.
        self.category_combo.currentTextChanged.connect(lambda _: self.refresh())
        self.plot_type_combo.currentTextChanged.connect(lambda _: self._update_plot())

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset
        if dataset.is_loaded():
            self.refresh(announce=False)
        else:
            for view in self._table_views.values():
                view.set_dataframe(view.dataframe().iloc[0:0])
            self.plot.show_message("Load a dataset first.")

    def refresh(self, announce: bool = True) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Tank Attributes", "Load a dataset first.")
            return
        category = self.category_combo.currentText() or "TankType"
        attrs = tsci.tank_attributes_table(self.dataset)
        audit = tsci.tank_attribute_audit(self.dataset, category)
        numeric = tsci.tank_attribute_numeric_summary(self.dataset)
        df = self.dataset.require_df()
        preview_cols = [c for c in _PREVIEW_COLUMNS if c in df.columns]
        merged_preview = df.select(preview_cols).head(500).to_pandas() if preview_cols else pd.DataFrame()

        self._table_views["Attributes"].set_dataframe(attrs)
        self._table_views["Category audit"].set_dataframe(audit)
        self._table_views["Numeric summary"].set_dataframe(numeric)
        self._table_views["Merged preview"].set_dataframe(merged_preview)
        self._audit_df = audit
        self._category = category
        self._update_plot()
        if announce:
            self.app_window.statusBar().showMessage(f"Tank attributes refreshed ({category}).")

    def _update_plot(self) -> None:
        if self._audit_df is None or self._audit_df.empty:
            self.plot.show_message("No tank attributes available")
            return
        category = self._category
        ptype = self.plot_type_combo.currentText()
        if ptype == "Capacity by category" and "Total_capacity_kgal" in self._audit_df.columns:
            ph.plot_barh(self.plot, self._audit_df, category, "Total_capacity_kgal",
                         f"Total capacity by {category}", "Total capacity (kgal)", top_n=50)
        elif ptype == "DIL by category" and "Total_DIL_gal" in self._audit_df.columns:
            ph.plot_barh(self.plot, self._audit_df, category, "Total_DIL_gal",
                         f"Total drainable interstitial liquid by {category}", "DIL (gal)", top_n=50)
        elif ptype == "Integrity count" and "N_leaker_or_assumed" in self._audit_df.columns:
            ph.plot_barh(self.plot, self._audit_df, category, "N_leaker_or_assumed",
                         f"Leaker/assumed-leaker count by {category}", "N tanks", top_n=50)
        else:
            ph.plot_barh(self.plot, self._audit_df, category, "N_tanks",
                         f"Tank count by {category}", "N tanks", top_n=50)

    def _export_tables(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Export", "Load a dataset first.")
            return
        tables = {name: view.dataframe() for name, view in self._table_views.items()}
        out_dir = export_utils.export_named_tables(self.dataset, "tank_attributes", tables)
        QMessageBox.information(self, "Export complete", f"Tank attributes tables exported:\n{out_dir}")
