from PySide6.QtWidgets import QMainWindow

from qt_vitrification import VitrificationPage


class TestVitrificationPage:
    def test_hosts_four_tabs(self, qtbot):
        app_window = QMainWindow()
        qtbot.addWidget(app_window)
        page = VitrificationPage(app_window)
        qtbot.addWidget(page)
        titles = [page.tabs.tabText(i) for i in range(page.tabs.count())]
        assert titles == ["Screening", "Oxide Chemistry", "Candidate Search", "Blend Partners"]

    def test_on_dataset_changed_forwards_to_all_tabs(self, qtbot, oxide_dataset):
        app_window = QMainWindow()
        qtbot.addWidget(app_window)
        page = VitrificationPage(app_window)
        qtbot.addWidget(page)
        page.on_dataset_changed(oxide_dataset)
        assert page.screening_tab.dataset is oxide_dataset
        assert page.oxide_tab.dataset is oxide_dataset
        assert page.candidate_tab.dataset is oxide_dataset
        assert page.blend_tab.dataset is oxide_dataset
