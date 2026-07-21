"""
qt_correlations_structure.py — the "Structure" Correlations sub-tab: PCA +
hierarchical clustering of tanks, a partial-correlation matrix controlling
for tank size, and an element-association network graph, with interactive
Plotly HTML export. Entirely NEW capability -- no old-app equivalent to
port; reuses kg_correlation_workbench's element-selection controls (same
shape as the Association Workbench tab) since structure_science.
structure_workbench builds directly on top of it.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

import export_utils
import html_export as he
import plot_helpers as ph
import structure_science as ssci
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget

METRICS = ["log10_plus1", "log10_inventory", "fraction", "inventory", "presence"]
METHODS = ["pearson", "spearman", "kendall"]
COLOR_MODES = ["Basic", "Coherent colors"]
STRUCTURE_PLOT_TYPES = ["PCA scatter", "Dendrogram", "Partial vs raw correlation", "Element network"]
_TABLE_KEY_BY_TITLE = {
    "Tank summary": "tank_summary", "PCA loadings": "pca_loadings", "PCA variance": "pca_variance",
    "Raw corr matrix": "raw_corr_matrix", "Partial corr matrix": "partial_corr_matrix",
    "Network nodes": "network_nodes", "Network edges": "network_edges",
    "Element stats": "element_stats", "Skipped": "excluded_elements",
}


class StructureTab(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self.results: dict = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        title = QLabel("Tank Structure")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        note = QLabel("PCA + clustering of tanks, partial correlation controlling for tank size, and an element-association network. Kg only, same reasoning as the Association Workbench.")
        note.setObjectName("SectionNote")
        top.addWidget(note)
        top.addStretch(1)
        export_tables_btn = QPushButton("Export all tables")
        export_tables_btn.clicked.connect(self.export_tables)
        top.addWidget(export_tables_btn)
        export_html_btn = QPushButton("Export interactive HTML")
        export_html_btn.clicked.connect(self.export_html_views)
        top.addWidget(export_html_btn)
        root.addLayout(top)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Selection"))
        self.selection_combo = QComboBox()
        self.selection_combo.addItems(["User list", "Top kg elements"])
        row1.addWidget(self.selection_combo)
        row1.addWidget(QLabel("Elements"))
        self.elements_edit = QLineEdit("Cs, Sr, Tc, I, Se, U, Cr, Fe, Al, Na, P, B, Si")
        self.elements_edit.setMinimumWidth(260)
        row1.addWidget(self.elements_edit)
        row1.addWidget(QLabel("Skip"))
        self.skip_edit = QLineEdit()
        self.skip_edit.setMaximumWidth(140)
        row1.addWidget(self.skip_edit)
        row1.addWidget(QLabel("top kg"))
        self.top_kg_spin = QSpinBox()
        self.top_kg_spin.setRange(2, 500)
        self.top_kg_spin.setValue(25)
        row1.addWidget(self.top_kg_spin)
        row1.addWidget(QLabel("min kg row"))
        self.min_inv_spin = QDoubleSpinBox()
        self.min_inv_spin.setRange(0.0, 1e12)
        self.min_inv_spin.setDecimals(6)
        row1.addWidget(self.min_inv_spin)
        self.build_btn = QPushButton("Build structure data")
        self.build_btn.setObjectName("Primary")
        self.build_btn.clicked.connect(self.build_data)
        row1.addWidget(self.build_btn)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Metric"))
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(METRICS)
        row2.addWidget(self.metric_combo)
        row2.addWidget(QLabel("Method"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(METHODS)
        row2.addWidget(self.method_combo)
        self.include_zeros_check = QCheckBox("include zero tanks")
        self.include_zeros_check.setChecked(True)
        row2.addWidget(self.include_zeros_check)
        row2.addWidget(QLabel("clusters"))
        self.n_clusters_spin = QSpinBox()
        self.n_clusters_spin.setRange(1, 20)
        self.n_clusters_spin.setValue(4)
        row2.addWidget(self.n_clusters_spin)
        row2.addWidget(QLabel("cluster method"))
        self.cluster_method_combo = QComboBox()
        self.cluster_method_combo.addItems(ssci.CLUSTER_METHODS)
        row2.addWidget(self.cluster_method_combo)
        row2.addWidget(QLabel("Colors"))
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItems(COLOR_MODES)
        self.color_mode_combo.setCurrentText("Coherent colors")
        row2.addWidget(self.color_mode_combo)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("min |r| (network)"))
        self.min_abs_r_spin = QDoubleSpinBox()
        self.min_abs_r_spin.setRange(0.0, 1.0)
        self.min_abs_r_spin.setSingleStep(0.05)
        self.min_abs_r_spin.setDecimals(2)
        row3.addWidget(self.min_abs_r_spin)
        row3.addWidget(QLabel("min Jaccard (network)"))
        self.min_jaccard_spin = QDoubleSpinBox()
        self.min_jaccard_spin.setRange(0.0, 1.0)
        self.min_jaccard_spin.setSingleStep(0.05)
        self.min_jaccard_spin.setDecimals(2)
        row3.addWidget(self.min_jaccard_spin)
        self.use_partial_check = QCheckBox("network uses partial r")
        row3.addWidget(self.use_partial_check)
        self.annotate_check = QCheckBox("annotate heatmaps")
        row3.addWidget(self.annotate_check)
        row3.addWidget(QLabel("color PCA by"))
        self.color_by_combo = QComboBox()
        self.color_by_combo.addItems(["None"] + ssci.CATEGORY_FIELDS)
        row3.addWidget(self.color_by_combo)
        root.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Plot"))
        self.plot_type_combo = QComboBox()
        self.plot_type_combo.addItems(STRUCTURE_PLOT_TYPES)
        row4.addWidget(self.plot_type_combo)
        plot_btn = QPushButton("Plot selected")
        plot_btn.clicked.connect(self.plot_selected)
        row4.addWidget(plot_btn)
        row4.addStretch(1)
        root.addLayout(row4)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.tables = QTabWidget()
        self._table_views: dict[str, DataFrameTableView] = {}
        for title_ in _TABLE_KEY_BY_TITLE:
            view = DataFrameTableView(title=title_, max_rows_display=500)
            self._table_views[title_] = view
            self.tables.addTab(view, title_)
        splitter.addWidget(self.tables)

        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset  # kg-only by design; nothing else to sync from the dataset

    def _current_color_by(self) -> Optional[str]:
        text = self.color_by_combo.currentText()
        return None if text == "None" else text

    def build_data(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Structure", "Load a dataset first.")
            return
        self.build_btn.setEnabled(False)
        self.build_btn.setText("Building…")
        QApplication.processEvents()
        try:
            self.results = ssci.structure_workbench(
                self.dataset, elements_text=self.elements_edit.text(),
                selection_mode=self.selection_combo.currentText(), top_n_elements=self.top_kg_spin.value(),
                value_mode=self.metric_combo.currentText(), method=self.method_combo.currentText(),
                min_inventory=self.min_inv_spin.value(), include_zeros=self.include_zeros_check.isChecked(),
                skip_elements_text=self.skip_edit.text(), n_clusters=self.n_clusters_spin.value(),
                cluster_method=self.cluster_method_combo.currentText(),
                min_abs_r=self.min_abs_r_spin.value(), min_jaccard=self.min_jaccard_spin.value(),
                use_partial_for_network=self.use_partial_check.isChecked(),
            )
        except ValueError as exc:
            self.build_btn.setEnabled(True)
            self.build_btn.setText("Build structure data")
            QMessageBox.warning(self, "Build failed", str(exc))
            return
        self.build_btn.setEnabled(True)
        self.build_btn.setText("Build structure data")
        for title_, key in _TABLE_KEY_BY_TITLE.items():
            value = self.results.get(key, pd.DataFrame())
            self._table_views[title_].set_dataframe(value if isinstance(value, pd.DataFrame) else pd.DataFrame())
        self.plot_selected()
        n_elements = len([c for c in self.results.get("raw_matrix", pd.DataFrame()).columns if c != "WasteSiteId"])
        self.app_window.statusBar().showMessage(f"Structure data built for {n_elements} element(s).")

    def _ensure_results(self) -> bool:
        if not self.results:
            self.build_data()
        return bool(self.results)

    def plot_selected(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Structure", "Load a dataset first.")
            return
        if not self._ensure_results():
            return
        ptype = self.plot_type_combo.currentText()
        color_mode = self.color_mode_combo.currentText()
        if ptype == "PCA scatter":
            ph.plot_pca_scatter(
                self.plot, self.results.get("tank_summary", pd.DataFrame()), self._current_color_by(),
                self.results.get("pca_variance", pd.DataFrame()), color_mode=color_mode,
            )
        elif ptype == "Dendrogram":
            ph.plot_dendrogram(
                self.plot, self.results.get("cluster_linkage"), self.results.get("cluster_labels", []),
                color_mode=color_mode,
            )
        elif ptype == "Partial vs raw correlation":
            ph.plot_partial_correlation_comparison(
                self.plot, self.results.get("partial_corr_matrix", pd.DataFrame()),
                self.results.get("raw_corr_matrix", pd.DataFrame()), annotate=self.annotate_check.isChecked(),
                color_mode=color_mode,
            )
        elif ptype == "Element network":
            ph.plot_element_network(
                self.plot, self.results.get("network_nodes", pd.DataFrame()),
                self.results.get("network_edges", pd.DataFrame()), color_mode=color_mode,
            )
        else:
            self.plot.show_message(f"Unknown plot type: {ptype}")

    def export_tables(self) -> None:
        if not self.results or self.dataset is None:
            QMessageBox.information(self, "Export", "Build the structure data first.")
            return
        tables = {k: v for k, v in self.results.items() if isinstance(v, pd.DataFrame)}
        linkage_arr = self.results.get("cluster_linkage")
        if linkage_arr is not None and len(linkage_arr) > 0:
            tables["cluster_linkage"] = pd.DataFrame(linkage_arr, columns=["Cluster_A", "Cluster_B", "Distance", "N_samples"])
        settings = pd.DataFrame([{
            "unit": "kg", "selection_mode": self.selection_combo.currentText(),
            "elements_text": self.elements_edit.text(), "skip_elements_text": self.skip_edit.text(),
            "metric": self.metric_combo.currentText(), "method": self.method_combo.currentText(),
            "top_elements": self.top_kg_spin.value(), "min_inventory_kg_row": self.min_inv_spin.value(),
            "include_zeros": self.include_zeros_check.isChecked(), "n_clusters": self.n_clusters_spin.value(),
            "cluster_method": self.cluster_method_combo.currentText(), "min_abs_r": self.min_abs_r_spin.value(),
            "min_jaccard": self.min_jaccard_spin.value(), "network_uses_partial_r": self.use_partial_check.isChecked(),
            "color_pca_by": self.color_by_combo.currentText(), "color_mode": self.color_mode_combo.currentText(),
        }])
        tables["settings"] = settings
        out_dir = export_utils.export_named_tables(self.dataset, "structure", tables)
        try:
            self.plot.figure.savefig(out_dir / "current_plot.png", bbox_inches="tight", dpi=220)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Structure tables exported:\n{out_dir}")

    def export_html_views(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Structure", "Load a dataset first.")
            return
        if not self._ensure_results():
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = self.dataset.output_root / f"structure_html_{stamp}"
        try:
            he.export_correlation_heatmap_html(
                out_dir / "correlation_heatmap.html", self.results.get("raw_corr_matrix", pd.DataFrame()),
                title="Element correlation heatmap (kg)",
            )
            he.export_pca_scatter_html(
                out_dir / "pca_scatter.html", self.results.get("tank_summary", pd.DataFrame()),
                color_by=self._current_color_by(), pca_variance=self.results.get("pca_variance", pd.DataFrame()),
            )
            he.export_network_html(
                out_dir / "network_graph.html", self.results.get("network_nodes", pd.DataFrame()),
                self.results.get("network_edges", pd.DataFrame()),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "HTML export failed", str(exc))
            return
        os.startfile(str(out_dir.resolve()))
        self.app_window.statusBar().showMessage(f"Interactive HTML exported: {out_dir}")
