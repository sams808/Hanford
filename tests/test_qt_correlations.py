from PySide6.QtWidgets import QMainWindow

from qt_correlations import HEATMAP_STYLES, CorrelationsPage, QuickScanTab


def _make_quick_scan(qtbot):
    app_window = QMainWindow()
    qtbot.addWidget(app_window)
    tab = QuickScanTab(app_window)
    qtbot.addWidget(tab)
    return tab


class TestQuickScanTab:
    def test_actions_without_dataset_show_message_not_crash(self, qtbot):
        tab = _make_quick_scan(qtbot)
        tab.run_target_scan()
        tab.run_selected()
        tab.run_heatmap()

    def test_on_dataset_changed_defaults_to_kg(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        assert tab.unit_combo.currentText() == "kg"

    def test_target_scan_populates_table(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        tab.unit_combo.setCurrentText("Ci")  # Cs (137Cs) is a Ci-unit element in the fixture
        tab.target_edit.setText("Cs")
        tab.min_overlap_spin.setValue(0)
        tab.run_target_scan()
        qtbot.wait(20)
        matrix = tab._table_views["Matrix"].dataframe()
        assert "Cs" in matrix.columns

    def test_invalid_target_symbol_shows_warning_not_crash(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        tab.target_edit.setText("Zz")
        tab.run_target_scan()  # QMessageBox.warning neutralized by conftest

    def test_dual_triple_populates_tables(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        tab.elements_edit.setText("Fe, Cd")
        tab.include_zeros_check.setChecked(True)
        tab.run_selected()
        qtbot.wait(20)
        pairs = tab._table_views["Pairs"].dataframe()
        assert set(pairs.iloc[0][["Element_A", "Element_B"]]) == {"Fe", "Cd"}
        joint = tab._table_views["Joint"].dataframe()
        assert joint.iloc[0]["N_elements"] == 2

    def test_dual_triple_too_few_elements_shows_warning_not_crash(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        tab.elements_edit.setText("Fe")
        tab.run_selected()

    def test_all_heatmap_styles_render_without_crash(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        for style in HEATMAP_STYLES:
            tab.heatmap_style_combo.setCurrentText(style)
            tab.run_heatmap()
            qtbot.wait(20)

    def test_heatmap_populates_projection_table(self, qtbot, sample_dataset):
        tab = _make_quick_scan(qtbot)
        tab.on_dataset_changed(sample_dataset)
        tab.run_heatmap()
        qtbot.wait(20)
        assert not tab._heatmap_projection_df.empty
        assert f"Total_inventory_kg" in tab._heatmap_projection_df.columns

    def test_export_without_results_shows_message_not_crash(self, qtbot):
        tab = _make_quick_scan(qtbot)
        tab._export_tables()

    def test_export_writes_bundle(self, qtbot, sample_dataset, tmp_path):
        tab = _make_quick_scan(qtbot)
        sample_dataset.output_root = tmp_path
        tab.on_dataset_changed(sample_dataset)
        tab.run_heatmap()
        qtbot.wait(20)
        tab._export_tables()
        bundles = list(tmp_path.glob("correlations_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "correlation_plot.png").exists()


class TestCorrelationsPage:
    def test_hosts_three_tabs(self, qtbot):
        app_window = QMainWindow()
        qtbot.addWidget(app_window)
        page = CorrelationsPage(app_window)
        qtbot.addWidget(page)
        titles = [page.tabs.tabText(i) for i in range(page.tabs.count())]
        assert titles == ["Quick Scan", "Association Workbench (kg)", "Structure"]

    def test_on_dataset_changed_forwards_to_quick_scan(self, qtbot, sample_dataset):
        app_window = QMainWindow()
        qtbot.addWidget(app_window)
        page = CorrelationsPage(app_window)
        qtbot.addWidget(page)
        page.on_dataset_changed(sample_dataset)
        assert page.quick_scan_tab.dataset is sample_dataset
