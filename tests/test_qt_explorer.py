from PySide6.QtWidgets import QMainWindow

from qt_explorer import PLOT_TYPES, ExplorerPage


def _make_page(qtbot):
    app_window = QMainWindow()
    qtbot.addWidget(app_window)
    page = ExplorerPage(app_window)
    qtbot.addWidget(page)
    return page


class TestExplorerPage:
    def test_run_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page.run_search()

    def test_run_with_empty_query_shows_message_not_crash(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)  # let show_message()'s canvas.draw_idle() flush before teardown
        page.query_edit.setText("   ")
        page.run_search()

    def test_on_dataset_changed_populates_unit_combo(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        items = [page.unit_combo.itemText(i) for i in range(page.unit_combo.count())]
        assert items == ["All", "Ci", "kg"]

    def test_run_search_populates_tables(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.query_edit.setText("Cs")
        page.run_search()
        qtbot.wait(20)
        target_by_tank = page._table_views["Target by tank"].dataframe()
        assert len(target_by_tank) == 2
        assert set(target_by_tank["WasteSiteId"]) == {"241-A-101", "241-AN-104"}
        co_el = page._table_views["Co-elements"].dataframe()
        assert "Fe" in co_el["Element"].values

    def test_raw_target_rows_table_populated(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.query_edit.setText("Cs")
        page.run_search()
        qtbot.wait(20)
        raw = page._table_views["Raw target rows"].dataframe()
        assert len(raw) == 2
        assert set(raw["Analyte"]) == {"137Cs"}

    def test_invalid_element_symbol_in_element_mode_shows_warning_not_crash(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        page.query_edit.setText("Zz")
        page.mode_combo.setCurrentText("element")
        page.run_search()  # QMessageBox.warning neutralized by conftest; must not raise

    def test_all_plot_types_render_without_crash(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.query_edit.setText("Cs")
        page.run_search()
        qtbot.wait(20)
        for plot_type in PLOT_TYPES:
            page.plot_type_combo.setCurrentText(plot_type)
            qtbot.wait(20)

    def test_export_without_results_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page._export_bundle()

    def test_export_writes_bundle(self, qtbot, sample_dataset, tmp_path):
        page = _make_page(qtbot)
        sample_dataset.output_root = tmp_path
        page.on_dataset_changed(sample_dataset)
        page.query_edit.setText("Cs")
        page.run_search()
        qtbot.wait(20)
        page._export_bundle()
        bundles = list(tmp_path.glob("search_Cs_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "Target_by_tank.csv").exists()
        assert (bundles[0] / "plot.png").exists()

    def test_dataset_changed_clears_stale_results(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.query_edit.setText("Cs")
        page.run_search()
        qtbot.wait(20)
        assert len(page._table_views["Target by tank"].dataframe()) == 2
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        assert page._table_views["Target by tank"].dataframe().empty
