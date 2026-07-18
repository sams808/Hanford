from PySide6.QtWidgets import QMainWindow

import qt_debug as qd
from qt_debug import DebugPage
from qt_widgets import StatusLogger


def _make_page(qtbot):
    app_window = QMainWindow()
    app_window.status_logger = StatusLogger()
    qtbot.addWidget(app_window)
    page = DebugPage(app_window)
    qtbot.addWidget(page)
    return page, app_window


class TestDebugPage:
    def test_actions_without_dataset_show_message_not_crash(self, qtbot):
        page, _ = _make_page(qtbot)
        page.export_bundle()
        page.open_output()
        page.clear_log()  # must not require a dataset

    def test_log_view_shows_preexisting_log_on_construction(self, qtbot):
        app_window = QMainWindow()
        app_window.status_logger = StatusLogger()
        app_window.status_logger.log("hello before construction")
        qtbot.addWidget(app_window)
        page = DebugPage(app_window)
        qtbot.addWidget(page)
        assert "hello before construction" in page.log_view.toPlainText()

    def test_log_view_appends_new_lines_live(self, qtbot):
        page, app_window = _make_page(qtbot)
        app_window.status_logger.log("live line")
        assert "live line" in page.log_view.toPlainText()

    def test_clear_log_clears_logger_and_view(self, qtbot):
        page, app_window = _make_page(qtbot)
        app_window.status_logger.log("to be cleared")
        page.clear_log()
        assert page.log_view.toPlainText() == ""
        assert app_window.status_logger.full_text() == ""

    def test_export_bundle_success(self, qtbot, sample_dataset, tmp_path):
        page, _ = _make_page(qtbot)
        sample_dataset.output_root = tmp_path
        page.on_dataset_changed(sample_dataset)
        page.export_bundle()
        bundles = list(tmp_path.glob("debug_bundle_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "overview.csv").exists()
        assert "Global debug bundle exported" in page.log_view.toPlainText()

    def test_export_bundle_failure_shows_critical_not_crash(self, qtbot, sample_dataset, monkeypatch):
        page, _ = _make_page(qtbot)
        page.on_dataset_changed(sample_dataset)

        def boom(dataset):
            raise RuntimeError("boom")

        monkeypatch.setattr(qd.osci, "export_global_debug_bundle", boom)
        page.export_bundle()  # QMessageBox.critical neutralized by conftest

    def test_open_output_calls_startfile(self, qtbot, sample_dataset, tmp_path, monkeypatch):
        opened = []
        monkeypatch.setattr(qd.os, "startfile", lambda p: opened.append(p))
        page, _ = _make_page(qtbot)
        sample_dataset.output_root = tmp_path / "out"
        page.on_dataset_changed(sample_dataset)
        page.open_output()
        assert len(opened) == 1
        assert (tmp_path / "out").exists()
