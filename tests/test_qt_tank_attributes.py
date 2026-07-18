from PySide6.QtWidgets import QMainWindow

from qt_tank_attributes import PLOT_TYPES, TankAttributesPage


def _make_page(qtbot):
    app_window = QMainWindow()
    qtbot.addWidget(app_window)
    page = TankAttributesPage(app_window)
    qtbot.addWidget(page)
    return page


class TestTankAttributesPage:
    def test_refresh_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page.refresh()

    def test_on_dataset_changed_populates_tables(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        attrs = page._table_views["Attributes"].dataframe()
        assert set(attrs["WasteSiteId"]) == {"241-A-101", "241-AN-104"}

    def test_category_change_updates_audit_table(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        page.category_combo.setCurrentText("TankSystem")
        qtbot.wait(20)
        audit = page._table_views["Category audit"].dataframe()
        assert set(audit["TankSystem"]) == {"SST", "DST"}

    def test_all_plot_types_render_without_crash(self, qtbot, sample_dataset):
        page = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        for plot_type in PLOT_TYPES:
            page.plot_type_combo.setCurrentText(plot_type)
            qtbot.wait(20)

    def test_export_without_dataset_shows_message_not_crash(self, qtbot):
        page = _make_page(qtbot)
        page._export_tables()

    def test_export_writes_tables(self, qtbot, sample_dataset, tmp_path):
        page = _make_page(qtbot)
        sample_dataset.output_root = tmp_path
        page.on_dataset_changed(sample_dataset)
        qtbot.wait(20)
        page._export_tables()
        bundles = list(tmp_path.glob("tank_attributes_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "Attributes.csv").exists()

    def test_dataset_not_loaded_shows_plot_message(self, qtbot):
        import data_model as dm
        page = _make_page(qtbot)
        empty_dataset = dm.HanfordDataset()
        page.on_dataset_changed(empty_dataset)
        qtbot.wait(20)
        assert page._table_views["Attributes"].dataframe().empty
