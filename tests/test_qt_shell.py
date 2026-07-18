"""
Qt-level tests for the app shell: nav-by-name resolution and the
load -> broadcast-to-pages flow. qt_worker's synchronous-mode autouse
fixture (conftest.py) makes run_in_thread calls execute inline, so no
real background thread or wait-loop is needed here.
"""
import pytest

import data_model as dm
from qt_shell import NAV_EXPLORER, NAV_ITEMS, EmberMainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    # Redirect the startup auto-load to an empty folder: shell/nav tests
    # shouldn't depend on (or be slowed by) the real dev-seed Hanford.csv
    # that happens to sit in this repo. Both search locations matter --
    # load_local_default() also falls back to Path.cwd(), which (unpatched)
    # would still be this repo's own root under pytest.
    monkeypatch.setattr(dm, "app_base_dir", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    win = EmberMainWindow()
    qtbot.addWidget(win)
    qtbot.wait(50)  # let QTimer.singleShot(0, auto-load) fire and fail harmlessly
    return win


class TestNavSwitching:
    def test_starts_on_overview(self, window):
        assert window.nav.currentRow() == 0
        assert window.stack.currentWidget() is window.overview_page

    def test_switching_updates_stack_by_name(self, window):
        explorer_row = NAV_ITEMS.index(NAV_EXPLORER)
        window.nav.setCurrentRow(explorer_row)
        assert window.stack.currentWidget() is window.explorer_page

    def test_all_nav_rows_resolve_to_distinct_pages(self, window):
        seen = set()
        for row, name in enumerate(NAV_ITEMS):
            window.nav.setCurrentRow(row)
            page = window.stack.currentWidget()
            assert page is window._pages_by_nav[name]
            seen.add(id(page))
        assert len(seen) == len(NAV_ITEMS)

    def test_out_of_range_row_is_ignored(self, window):
        current = window.stack.currentWidget()
        window._on_nav_changed(-1)
        window._on_nav_changed(999)
        assert window.stack.currentWidget() is current


class TestDatasetLoadBroadcast:
    def _write_csv(self, tmp_path):
        path = tmp_path / "custom.csv"
        path.write_text(
            "WasteSiteId,Analyte,WastePhase,WasteType,Inventory,Units\n"
            "241-A-101,137Cs,Liquid,T1,100.0,Ci\n"
        )
        return path

    def test_successful_load_broadcasts_to_overview_page(self, window, tmp_path, qtbot):
        csv_path = self._write_csv(tmp_path)
        window._start_load(lambda: window.dataset.load(csv_path, use_cache=False))
        qtbot.wait(50)
        assert window.dataset.is_loaded()
        assert window.overview_page.dataset is window.dataset
        assert "Loaded" in window.statusBar().currentMessage()

    def test_busy_state_toggles_load_actions(self, window, tmp_path, qtbot):
        csv_path = self._write_csv(tmp_path)
        assert window.load_local_action.isEnabled()
        window._start_load(lambda: window.dataset.load(csv_path, use_cache=False))
        qtbot.wait(50)
        # Synchronous worker mode means the load already completed and
        # re-enabled the actions by the time run_in_thread returns.
        assert window.load_local_action.isEnabled()

    def test_load_failure_shows_status_not_a_blocking_dialog(self, window, tmp_path, qtbot):
        missing = tmp_path / "does_not_exist.csv"
        window._start_load(lambda: window.dataset.load(missing, use_cache=False))
        qtbot.wait(50)
        assert "failed" in window.statusBar().currentMessage().lower()

    def test_reload_without_prior_load_shows_info_message(self, window):
        assert window.dataset.path is None
        window._reload()  # must not raise; QMessageBox.information is neutralized by conftest


class TestDarkModeToggle:
    def test_toggling_does_not_raise(self, window, qtbot):
        window.dark_mode_action.setChecked(True)
        window.dark_mode_action.setChecked(False)
