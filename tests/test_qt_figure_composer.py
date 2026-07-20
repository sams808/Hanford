from io import BytesIO

import matplotlib.pyplot as plt
import pytest
from PySide6.QtWidgets import QMainWindow

from composer_store import store
from qt_figure_composer import FigureComposerPage


def _fake_png(color="blue") -> bytes:
    fig = plt.figure(figsize=(1, 1), dpi=20)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(color)
    ax.axis("off")
    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clean_store():
    # The page reads composer_store.store, a module-level singleton shared
    # with the real app -- reset it around every test so panels captured
    # (or left) by one test can't leak into the next.
    store.clear()
    yield
    store.clear()


@pytest.fixture
def page(qtbot):
    app_window = QMainWindow()  # only used for .statusBar()-style calls, none needed here
    qtbot.addWidget(app_window)
    p = FigureComposerPage(app_window)
    qtbot.addWidget(p)
    qtbot.wait(20)  # let the initial (empty-state) compose_figure()'s draw_idle flush
    yield p
    qtbot.wait(20)  # flush anything the test itself queued, before teardown deletes the widgets


class TestGallerySync:
    def test_starts_empty(self, page):
        assert page.gallery_list.count() == 0

    def test_gallery_reflects_items_already_in_the_store(self, qtbot):
        store.add(_fake_png(), "Pre-existing panel")
        app_window = QMainWindow()
        qtbot.addWidget(app_window)
        p = FigureComposerPage(app_window)
        qtbot.addWidget(p)
        qtbot.wait(20)
        assert p.gallery_list.count() == 1
        assert p.gallery_list.item(0).text() == "Pre-existing panel"
        qtbot.wait(20)  # flush before this test's own widgets get torn down

    def test_gallery_updates_when_store_changes_after_construction(self, page, qtbot):
        store.add(_fake_png(), "Added later")
        qtbot.wait(20)
        assert page.gallery_list.count() == 1
        assert page.gallery_list.item(0).text() == "Added later"

    def test_untitled_caption_shown_for_empty_caption(self, page, qtbot):
        store.add(_fake_png(), "")
        qtbot.wait(20)
        assert page.gallery_list.item(0).text() == "(untitled)"


class TestSelectionAndCaptionEditing:
    def test_selecting_item_populates_caption_field(self, page, qtbot):
        store.add(_fake_png(), "First")
        store.add(_fake_png(), "Second")
        qtbot.wait(20)
        page.gallery_list.setCurrentRow(1)
        assert page.caption_edit.text() == "Second"

    def test_caption_field_disabled_with_nothing_selected(self, page):
        assert page.caption_edit.isEnabled() is False

    def test_editing_caption_updates_the_store(self, page, qtbot):
        store.add(_fake_png(), "Original")
        qtbot.wait(20)
        page.gallery_list.setCurrentRow(0)
        page.caption_edit.setText("Edited caption")
        page.caption_edit.editingFinished.emit()
        qtbot.wait(20)
        assert store.items()[0].caption == "Edited caption"


class TestReorderAndRemove:
    def test_move_down_swaps_store_order(self, page, qtbot):
        store.add(_fake_png(), "A")
        store.add(_fake_png(), "B")
        qtbot.wait(20)
        page.gallery_list.setCurrentRow(0)
        page._move(1)
        qtbot.wait(20)
        assert [i.caption for i in store.items()] == ["B", "A"]

    def test_remove_deletes_from_store(self, page, qtbot):
        store.add(_fake_png(), "keep")
        store.add(_fake_png(), "remove me")
        qtbot.wait(20)
        page.gallery_list.setCurrentRow(1)
        page._remove_selected()
        qtbot.wait(20)
        captions = [i.caption for i in store.items()]
        assert captions == ["keep"]

    def test_remove_with_nothing_selected_is_a_noop(self, page, qtbot):
        store.add(_fake_png(), "solo")
        qtbot.wait(20)
        page.gallery_list.setCurrentRow(-1)
        page._remove_selected()
        qtbot.wait(20)
        assert len(store.items()) == 1

    def test_clear_all_empties_the_store(self, page, qtbot):
        # _prevent_blocking_qt_dialogs (conftest, autouse) makes the
        # QMessageBox.question confirmation resolve to Yes automatically.
        store.add(_fake_png(), "one")
        store.add(_fake_png(), "two")
        qtbot.wait(20)
        page._clear_all()
        qtbot.wait(20)
        assert store.items() == []


class TestPreviewRebuildsOnLayoutChange:
    def test_preview_has_no_axes_when_empty(self, page):
        # compose_figure([]) calls panel.show_message(), which clears and
        # turns off the PlotWidget's original axes rather than removing it.
        assert len(page.plot.figure.axes) == 1
        assert page.plot.figure.axes[0].axison is False

    def test_preview_grows_axes_count_with_panels(self, page, qtbot):
        store.add(_fake_png(), "one")
        store.add(_fake_png(), "two")
        store.add(_fake_png(), "three")
        qtbot.wait(20)
        assert len(page.plot.figure.axes) == 3

    def test_changing_label_style_rebuilds_preview_without_raising(self, page, qtbot):
        store.add(_fake_png(), "one")
        qtbot.wait(20)
        page.label_style_combo.setCurrentText("none")
        qtbot.wait(20)
        all_texts = [t.get_text() for ax in page.plot.figure.axes for t in ax.texts]
        assert all_texts == []


class TestExport:
    def test_export_with_no_panels_shows_message_not_crash(self, page):
        page.export_figure()  # QMessageBox.information neutralized by conftest; must not raise

    def test_export_writes_a_file(self, page, qtbot, tmp_path, monkeypatch):
        store.add(_fake_png(), "panel")
        qtbot.wait(20)
        out_path = tmp_path / "combined_figure.png"
        monkeypatch.setattr(
            "qt_figure_composer.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(out_path), "")),
        )
        page.export_figure()
        qtbot.wait(20)
        assert out_path.exists()

    def test_cancelled_dialog_writes_nothing(self, page, qtbot, tmp_path, monkeypatch):
        store.add(_fake_png(), "panel")
        qtbot.wait(20)
        monkeypatch.setattr(
            "qt_figure_composer.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: ("", "")),
        )
        page.export_figure()
        qtbot.wait(20)
        assert list(tmp_path.iterdir()) == []


class TestOnDatasetChanged:
    def test_does_not_raise(self, page):
        page.on_dataset_changed(None)  # Figure Composer ignores the dataset; must not raise
