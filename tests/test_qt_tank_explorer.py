from PySide6.QtWidgets import QMainWindow

from qt_tank_explorer import TankExplorerPage


def _make_page(qtbot):
    app_window = QMainWindow()
    qtbot.addWidget(app_window)
    page = TankExplorerPage(app_window)
    qtbot.addWidget(page)
    return page


class TestTankExplorerPage:
    def test_run_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page.run()

    def test_on_dataset_changed_populates_farm_and_tanks(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        farms = [page.farm_combo.itemText(i) for i in range(page.farm_combo.count())]
        assert farms == ["All", "A", "AN"]
        tanks = [page.tank_list.item(i).text() for i in range(page.tank_list.count())]
        assert tanks == ["241-A-101", "241-AN-104"]

    def test_farm_filter_narrows_tank_list(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.farm_combo.setCurrentText("A")
        tanks = [page.tank_list.item(i).text() for i in range(page.tank_list.count())]
        assert tanks == ["241-A-101"]

    def test_run_without_selection_shows_warning_not_crash(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.run()  # nothing selected; QMessageBox.warning neutralized by conftest

    def test_run_populates_tables_and_plot(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        page.tank_list.item(0).setSelected(True)  # 241-A-101
        page.unit_combo.setCurrentText("kg")
        page.run()
        qtbot.wait(20)
        profile = page.profile_view.dataframe()
        assert set(profile["Element"]) == {"Fe", "Cd"}
        raw = page.raw_view.dataframe()
        assert set(raw["Units"]) == {"kg"}

    def test_export_without_run_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page._export_tables()

    def test_export_writes_tables_and_plot(self, qtbot, sample_dataset, tmp_path):
        page = _make_page(qtbot)
        sample_dataset.output_root = tmp_path
        page.on_dataset_changed(sample_dataset)
        page.tank_list.item(0).setSelected(True)
        page.run()
        qtbot.wait(20)
        page._export_tables()
        bundles = list(tmp_path.glob("tank_view_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "tank_composition.csv").exists()
        assert (bundles[0] / "tank_plot.png").exists()

    def test_dataset_not_loaded_shows_plot_message(self, qtbot):
        import data_model as dm
        page = _make_page(qtbot)
        empty_dataset = dm.HanfordDataset()
        page.on_dataset_changed(empty_dataset)
        qtbot.wait(20)
