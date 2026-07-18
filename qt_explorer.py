"""
qt_explorer.py — the Element / Analyte Explorer workspace: search by
element symbol, analyte name, or regex; see which tanks contain it, what
else tends to appear alongside it, and its typical composition. Ported
from the old app's SearchTab onto the new DataFrameTableView/PlotWidget
infrastructure.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

import element_science as esci
import export_utils
import plot_helpers as ph
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget

MODES = ["auto", "element", "analyte_exact", "analyte_contains", "regex"]
PLOT_TYPES = [
    "Target inventory by tank",
    "Target fraction by tank",
    "Target vs total inventory",
    "Co-elements inventory",
    "Co-elements presence (%)",
    "Mean absolute composition",
    "Mean fraction composition",
]


class ExplorerPage(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self._last_query: Optional[str] = None
        self._results: dict = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Query"))
        self.query_edit = QLineEdit("Se")
        self.query_edit.setMaximumWidth(160)
        row1.addWidget(self.query_edit)
        row1.addWidget(QLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODES)
        row1.addWidget(self.mode_combo)
        row1.addWidget(QLabel("Unit"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("All")
        row1.addWidget(self.unit_combo)
        run_btn = QPushButton("Run")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self.run_search)
        row1.addWidget(run_btn)
        row1.addStretch(1)
        export_btn = QPushButton("Export result bundle")
        export_btn.clicked.connect(self._export_bundle)
        row1.addWidget(export_btn)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("min target inventory"))
        self.min_target_spin = QDoubleSpinBox()
        self.min_target_spin.setRange(0.0, 1e12)
        self.min_target_spin.setDecimals(6)
        row2.addWidget(self.min_target_spin)
        row2.addWidget(QLabel("min context inventory"))
        self.min_context_spin = QDoubleSpinBox()
        self.min_context_spin.setRange(0.0, 1e12)
        self.min_context_spin.setDecimals(6)
        row2.addWidget(self.min_context_spin)
        row2.addWidget(QLabel("Top N"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(5, 300)
        self.top_n_spin.setValue(40)
        row2.addWidget(self.top_n_spin)
        row2.addStretch(1)
        root.addLayout(row2)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.tables = QTabWidget()
        self._table_views: dict[str, DataFrameTableView] = {}
        for title, max_rows in [
            ("Target by tank", None), ("Target by phase", None), ("Target by type", None),
            ("Co-elements", None), ("Co-analytes", None),
            ("Composition (absolute)", None), ("Composition (fraction)", None),
            ("Composition (by tank)", None), ("Raw target rows", 500),
        ]:
            view = DataFrameTableView(title=title, max_rows_display=max_rows)
            self._table_views[title] = view
            self.tables.addTab(view, title)
        splitter.addWidget(self.tables)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        plot_row = QHBoxLayout()
        plot_row.addWidget(QLabel("Plot"))
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(PLOT_TYPES)
        self.plot_type_combo.currentTextChanged.connect(self._update_plot)
        plot_row.addWidget(self.plot_type_combo)
        plot_row.addStretch(1)
        right_layout.addLayout(plot_row)
        self.plot = PlotWidget()
        right_layout.addWidget(self.plot)
        splitter.addWidget(right)
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
        self._results = {}
        for view in self._table_views.values():
            view.set_dataframe(view.dataframe().iloc[0:0])
        self.plot.show_message("Run a search to see results.")

    def run_search(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Element Explorer", "Load a dataset first.")
            return
        query = self.query_edit.text().strip()
        if not query:
            QMessageBox.information(self, "Element Explorer", "Enter a query first.")
            return
        mode = self.mode_combo.currentText()
        unit = self.unit_combo.currentText() or "All"
        min_target = self.min_target_spin.value()
        min_context = self.min_context_spin.value()

        try:
            target_by_tank = esci.target_by_tank_unit(self.dataset, query, mode, unit, min_target)
            target_by_phase = esci.target_by_phase(self.dataset, query, mode, unit, min_target)
            target_by_type = esci.target_by_type(self.dataset, query, mode, unit, min_target)
            co_el = esci.co_elements(self.dataset, query, mode, unit, min_target, min_context)
            co_an = esci.co_analytes(self.dataset, query, mode, unit, min_target, min_context)
            abs_stats, frac_stats, tank_stats = esci.composition_stats(self.dataset, query, mode, unit, min_target, min_context)
            raw_rows, resolved_mode, symbol = esci.target_rows(self.dataset, query, mode, unit, min_target)
        except ValueError as exc:
            QMessageBox.warning(self, "Search failed", str(exc))
            return

        self._results = {
            "Target by tank": target_by_tank, "Target by phase": target_by_phase,
            "Target by type": target_by_type, "Co-elements": co_el, "Co-analytes": co_an,
            "Composition (absolute)": abs_stats, "Composition (fraction)": frac_stats,
            "Composition (by tank)": tank_stats,
        }
        self._table_views["Target by tank"].set_dataframe(target_by_tank)
        self._table_views["Target by phase"].set_dataframe(target_by_phase)
        self._table_views["Target by type"].set_dataframe(target_by_type)
        self._table_views["Co-elements"].set_dataframe(co_el)
        self._table_views["Co-analytes"].set_dataframe(co_an)
        self._table_views["Composition (absolute)"].set_dataframe(abs_stats)
        self._table_views["Composition (fraction)"].set_dataframe(frac_stats)
        self._table_views["Composition (by tank)"].set_dataframe(tank_stats)
        self._table_views["Raw target rows"].set_dataframe(raw_rows.to_pandas())

        self._last_query = query
        self._symbol = symbol
        self._update_plot()

        n_tanks = target_by_tank["WasteSiteId"].nunique() if not target_by_tank.empty else 0
        self.app_window.statusBar().showMessage(
            f"'{query}' ({resolved_mode}{' -> ' + symbol if symbol else ''}): {n_tanks} tank(s), "
            f"{raw_rows.height} matching row(s)."
        )

    def _update_plot(self) -> None:
        if not self._results:
            return
        plot_type = self.plot_type_combo.currentText()
        symbol = getattr(self, "_symbol", None)
        target_by_tank = self._results.get("Target by tank")
        co_el = self._results.get("Co-elements")
        abs_stats = self._results.get("Composition (absolute)")
        frac_stats = self._results.get("Composition (fraction)")

        if plot_type == "Target inventory by tank":
            ph.plot_barh(self.plot, target_by_tank, "WasteSiteId", "Target_Inventory_sum",
                         "Target inventory by tank", "Target inventory", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol, log_x=True)
        elif plot_type == "Target fraction by tank":
            ph.plot_barh(self.plot, target_by_tank, "WasteSiteId", "TargetFractionOfTankUnitInventory",
                         "Target fraction of tank total", "Fraction", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol)
        elif plot_type == "Target vs total inventory":
            ph.plot_target_vs_total(self.plot, target_by_tank, "Target vs total tank inventory")
        elif plot_type == "Co-elements inventory":
            ph.plot_barh(self.plot, co_el, "Element", "Total_inventory_in_target_tanks",
                         "Co-elements inventory", "Total inventory", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol, log_x=True)
        elif plot_type == "Co-elements presence (%)":
            ph.plot_barh(self.plot, co_el, "Element", "PresenceFraction_pct",
                         "Co-elements presence", "% of target tanks", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol)
        elif plot_type == "Mean absolute composition":
            ph.plot_barh(self.plot, abs_stats, "Element", "Mean_inventory_all_target_tanks_zero_filled",
                         "Mean absolute composition", "Mean inventory (zero-filled)", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol, log_x=True)
        elif plot_type == "Mean fraction composition":
            ph.plot_barh(self.plot, frac_stats, "Element", "Mean_fraction_all_target_tanks_zero_filled",
                         "Mean fraction composition", "Mean fraction (zero-filled)", top_n=self.top_n_spin.value(),
                         highlighted_label=symbol)

    def _export_bundle(self) -> None:
        if not self._results or self.dataset is None:
            QMessageBox.information(self, "Export", "Run a search first.")
            return
        tables = dict(self._results)
        tables["Raw target rows"] = self._table_views["Raw target rows"].dataframe()
        out_dir = export_utils.export_named_tables(self.dataset, f"search_{self._last_query}", tables)
        try:
            self.plot.figure.savefig(out_dir / "plot.png", bbox_inches="tight", dpi=200)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Search results exported to:\n{out_dir}")
