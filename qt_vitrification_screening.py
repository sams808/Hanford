"""
qt_vitrification_screening.py — the Vitrification "Screening", "Candidate
Search", and "Blend Partners" sub-tabs. Ported from the old app's single
VitrificationTab, split into three tabs to match the nav shell's other
multi-tab domains (Correlations). The old app's hardcoded score weights
are now QDoubleSpinBox controls (with "Reset to defaults") instead of
buried constants -- old constants are vitrification_science's *_WEIGHT_DEFAULTS,
used to seed every spin box.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

import export_utils
import plot_helpers as ph
import vitrification_science as vsci
from correlation_science import parse_element_list
from data_model import HanfordDataset
from qt_widgets import DataFrameTableView, PlotWidget

BASIS_OPTIONS = ["elemental", "oxide"]


def _build_weight_spins(layout: QHBoxLayout, defaults: Dict[str, float]) -> Dict[str, QDoubleSpinBox]:
    spins: Dict[str, QDoubleSpinBox] = {}
    for key, default in defaults.items():
        label = key.replace("_weight", "").replace("_", " ")
        layout.addWidget(QLabel(f"{label}"))
        spin = QDoubleSpinBox()
        spin.setRange(-1000.0, 1000.0)
        spin.setDecimals(3)
        spin.setValue(default)
        spins[key] = spin
        layout.addWidget(spin)
    return spins


def _reset_weight_spins(spins: Dict[str, QDoubleSpinBox], defaults: Dict[str, float]) -> None:
    for key, spin in spins.items():
        spin.setValue(defaults[key])


def _current_weights(spins: Dict[str, QDoubleSpinBox]) -> Dict[str, float]:
    return {key: spin.value() for key, spin in spins.items()}


class ScreeningTab(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self.summary_df = pd.DataFrame()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        title = QLabel("Vitrification Screening")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        note = QLabel("Screening metric only; not an official waste classification or glass formulation model.")
        note.setObjectName("SectionNote")
        top.addWidget(note)
        top.addStretch(1)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.export_tables)
        top.addWidget(export_btn)
        root.addLayout(top)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Basis"))
        self.basis_combo = QComboBox()
        self.basis_combo.addItems(BASIS_OPTIONS)
        row1.addWidget(self.basis_combo)
        self.weight_spins = _build_weight_spins(row1, vsci.SCREENING_WEIGHT_DEFAULTS)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(lambda: _reset_weight_spins(self.weight_spins, vsci.SCREENING_WEIGHT_DEFAULTS))
        row1.addWidget(reset_btn)
        row1.addStretch(1)
        root.addLayout(row1)

        self.formula_label = QLabel("")
        self.formula_label.setObjectName("SectionNote")
        self.formula_label.setWordWrap(True)
        root.addWidget(self.formula_label)
        for spin in self.weight_spins.values():
            spin.valueChanged.connect(self._update_formula_label)
        self._update_formula_label()

        build_btn = QPushButton("Build screening summary")
        build_btn.setObjectName("Primary")
        build_btn.clicked.connect(self.run_summary)
        root.addWidget(build_btn)

        splitter = QSplitter()
        root.addWidget(splitter, 1)
        self.tables = QTabWidget()
        self._table_views: Dict[str, DataFrameTableView] = {}
        for title_ in ["Screening summary", "Groups", "Waste notes"]:
            view = DataFrameTableView(title=title_, max_rows_display=500)
            self._table_views[title_] = view
            self.tables.addTab(view, title_)
        splitter.addWidget(self.tables)
        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        self._table_views["Groups"].set_dataframe(vsci.vitrification_group_definitions())
        self._table_views["Waste notes"].set_dataframe(vsci.waste_class_notes())

    def _update_formula_label(self) -> None:
        w = _current_weights(self.weight_spins)
        self.formula_label.setText(
            f"score = {w['glass_former_weight']:.3g}*glass_former + {w['modifier_weight']:.3g}*modifier "
            f"- {abs(w['problem_weight']):.3g}*problem - {abs(w['volatile_weight']):.3g}*volatile "
            f"- {abs(w['redox_weight']):.3g}*redox (clipped to [-100, 100])"
        )

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset

    def run_summary(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Screening", "Load a dataset first.")
            return
        self.summary_df = vsci.tank_category_summary(
            self.dataset, weights=_current_weights(self.weight_spins), basis=self.basis_combo.currentText(),
        )
        self._table_views["Screening summary"].set_dataframe(self.summary_df)
        ph.plot_vitrification_burden(self.plot, self.summary_df)
        self.app_window.statusBar().showMessage(f"Vitrification summary built for {len(self.summary_df):,} tank(s).")

    def export_tables(self) -> None:
        if self.summary_df.empty or self.dataset is None:
            QMessageBox.information(self, "Export", "Build the screening summary first.")
            return
        tables = {
            "tank_screening_summary": self.summary_df,
            "group_definitions": vsci.vitrification_group_definitions(),
            "waste_class_notes": vsci.waste_class_notes(),
        }
        out_dir = export_utils.export_named_tables(self.dataset, "vitrification_screening", tables)
        try:
            self.plot.figure.savefig(out_dir / "screening_plot.png", bbox_inches="tight", dpi=200)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Screening outputs exported:\n{out_dir}")


class CandidateSearchTab(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self.candidates_df = pd.DataFrame()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        title = QLabel("Candidate Search")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.export_tables)
        top.addWidget(export_btn)
        root.addLayout(top)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Target elements"))
        self.target_edit = QLineEdit("Cs, Sr, Tc, I")
        row1.addWidget(self.target_edit)
        row1.addWidget(QLabel("Penalty elements"))
        self.penalty_edit = QLineEdit("S, Cl, F, I, Cr, Mo, Tc")
        row1.addWidget(self.penalty_edit)
        row1.addWidget(QLabel("Required"))
        self.required_edit = QLineEdit("")
        self.required_edit.setMaximumWidth(120)
        row1.addWidget(self.required_edit)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Basis"))
        self.basis_combo = QComboBox()
        self.basis_combo.addItems(BASIS_OPTIONS)
        row2.addWidget(self.basis_combo)
        row2.addWidget(QLabel("min kg"))
        self.min_kg_spin = QDoubleSpinBox()
        self.min_kg_spin.setRange(0.0, 1e12)
        self.min_kg_spin.setDecimals(3)
        row2.addWidget(self.min_kg_spin)
        row2.addWidget(QLabel("top N"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(40)
        row2.addWidget(self.top_n_spin)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        self.weight_spins = _build_weight_spins(row3, vsci.CANDIDATE_WEIGHT_DEFAULTS)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(lambda: _reset_weight_spins(self.weight_spins, vsci.CANDIDATE_WEIGHT_DEFAULTS))
        row3.addWidget(reset_btn)
        row3.addStretch(1)
        root.addLayout(row3)

        run_btn = QPushButton("Rank vitrification candidates")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self.run_candidates)
        root.addWidget(run_btn)

        splitter = QSplitter()
        root.addWidget(splitter, 1)
        self.table = DataFrameTableView(title="Candidate ranking", max_rows_display=500)
        splitter.addWidget(self.table)
        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset

    def run_candidates(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Candidate Search", "Load a dataset first.")
            return
        self.candidates_df = vsci.vitrification_candidate_search(
            self.dataset, parse_element_list(self.target_edit.text()),
            parse_element_list(self.penalty_edit.text()), parse_element_list(self.required_edit.text()),
            min_total_kg=self.min_kg_spin.value(), top_n=self.top_n_spin.value(),
            weights=_current_weights(self.weight_spins), basis=self.basis_combo.currentText(),
        )
        self.table.set_dataframe(self.candidates_df)
        ph.plot_candidate_scores(self.plot, self.candidates_df, top_n=self.top_n_spin.value())
        self.app_window.statusBar().showMessage(f"Candidate ranking built: {len(self.candidates_df):,} tank(s).")

    def export_tables(self) -> None:
        if self.candidates_df.empty or self.dataset is None:
            QMessageBox.information(self, "Export", "Run a candidate search first.")
            return
        out_dir = export_utils.export_named_tables(self.dataset, "vitrification_candidates", {"candidate_ranking": self.candidates_df})
        try:
            self.plot.figure.savefig(out_dir / "candidate_plot.png", bbox_inches="tight", dpi=200)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Candidate ranking exported:\n{out_dir}")


class BlendPartnersTab(QWidget):
    def __init__(self, app_window, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_window = app_window
        self.dataset: Optional[HanfordDataset] = None
        self.blend_df = pd.DataFrame()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        title = QLabel("Blend Partners")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.export_tables)
        top.addWidget(export_btn)
        root.addLayout(top)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Base tank"))
        self.base_tank_combo = QComboBox()
        self.base_tank_combo.setEditable(True)
        row1.addWidget(self.base_tank_combo)
        row1.addWidget(QLabel("Basis"))
        self.basis_combo = QComboBox()
        self.basis_combo.addItems(BASIS_OPTIONS)
        row1.addWidget(self.basis_combo)
        row1.addWidget(QLabel("top N"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(40)
        row1.addWidget(self.top_n_spin)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        self.weight_spins = _build_weight_spins(row2, vsci.BLEND_WEIGHT_DEFAULTS)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(lambda: _reset_weight_spins(self.weight_spins, vsci.BLEND_WEIGHT_DEFAULTS))
        row2.addWidget(reset_btn)
        row2.addStretch(1)
        root.addLayout(row2)

        run_btn = QPushButton("Find blend partners")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self.run_blend)
        root.addWidget(run_btn)

        splitter = QSplitter()
        root.addWidget(splitter, 1)
        self.table = DataFrameTableView(title="Blend partners", max_rows_display=500)
        splitter.addWidget(self.table)
        self.plot = PlotWidget()
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

    # ------------------------------------------------------------------
    def on_dataset_changed(self, dataset: HanfordDataset) -> None:
        self.dataset = dataset
        if not dataset.is_loaded():
            return
        tanks = dataset.available_tanks()
        current = self.base_tank_combo.currentText()
        self.base_tank_combo.blockSignals(True)
        self.base_tank_combo.clear()
        self.base_tank_combo.addItems(tanks)
        if current and self.base_tank_combo.findText(current) >= 0:
            self.base_tank_combo.setCurrentText(current)
        elif tanks:
            self.base_tank_combo.setCurrentIndex(0)
        self.base_tank_combo.blockSignals(False)

    def run_blend(self) -> None:
        if self.dataset is None or not self.dataset.is_loaded():
            QMessageBox.information(self, "Blend Partners", "Load a dataset first.")
            return
        base = self.base_tank_combo.currentText().strip()
        if not base:
            QMessageBox.warning(self, "Blend Partners", "Select a base tank first.")
            return
        self.blend_df = vsci.blend_partner_search(
            self.dataset, base, top_n=self.top_n_spin.value(),
            weights=_current_weights(self.weight_spins), basis=self.basis_combo.currentText(),
        )
        self.table.set_dataframe(self.blend_df)
        ph.plot_blend_scores(self.plot, self.blend_df, top_n=self.top_n_spin.value())
        self.app_window.statusBar().showMessage(f"Blend partner search completed for {base}: {len(self.blend_df):,} partner(s).")

    def export_tables(self) -> None:
        if self.blend_df.empty or self.dataset is None:
            QMessageBox.information(self, "Export", "Run a blend partner search first.")
            return
        out_dir = export_utils.export_named_tables(self.dataset, "vitrification_blend", {"blend_partners": self.blend_df})
        try:
            self.plot.figure.savefig(out_dir / "blend_plot.png", bbox_inches="tight", dpi=200)
        except Exception:
            pass
        QMessageBox.information(self, "Export complete", f"Blend partner search exported:\n{out_dir}")
