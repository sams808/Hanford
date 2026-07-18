from PySide6.QtWidgets import QMainWindow

from qt_overview import OverviewPage


def _make_page(qtbot):
    app_window = QMainWindow()  # only used for .statusBar()
    qtbot.addWidget(app_window)
    page = OverviewPage(app_window)
    qtbot.addWidget(page)
    return page


class TestOverviewPage:
    def test_refresh_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page.refresh()  # QMessageBox.information neutralized by conftest; must not raise

    def test_on_dataset_changed_populates_unit_combo(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)  # let the plot's canvas.draw_idle() flush before teardown
        items = [page.unit_combo.itemText(i) for i in range(page.unit_combo.count())]
        assert items == ["All", "Ci", "kg"]

    def test_on_dataset_changed_triggers_refresh(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        overview_table = page._table_views["Overview"].dataframe()
        assert overview_table.iloc[0]["rows"] == 9

    def test_unit_filter_changes_top_elements_table(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        page.unit_combo.setCurrentText("kg")
        page.refresh()
        qtbot.wait(20)
        top = page._table_views["Top elements"].dataframe()
        assert set(top["Units"]) == {"kg"}

    def test_export_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page._export_debug_bundle()  # must not raise

    def test_export_writes_debug_bundle(self, qtbot, sample_dataset, tmp_path):
        page = _make_page(qtbot)
        sample_dataset.output_root = tmp_path
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        page._export_debug_bundle()
        bundles = list(tmp_path.glob("debug_bundle_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "overview.csv").exists()
