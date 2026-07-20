import pytest

from composer_store import ComposerStore


@pytest.fixture
def fresh_store():
    # A dedicated instance per test, not the app-wide singleton -- avoids
    # tests leaking state into each other (and into the real qt_widgets/
    # qt_figure_composer code paths, which import the module-level `store`).
    return ComposerStore()


class TestComposerStoreAdd:
    def test_starts_empty(self, fresh_store):
        assert fresh_store.items() == []

    def test_add_appends_item(self, fresh_store):
        fresh_store.add(b"fakepng", "caption one", source="Overview")
        items = fresh_store.items()
        assert len(items) == 1
        assert items[0].png_bytes == b"fakepng"
        assert items[0].caption == "caption one"
        assert items[0].source == "Overview"

    def test_add_emits_changed_signal(self, fresh_store, qtbot):
        with qtbot.waitSignal(fresh_store.changed, timeout=1000):
            fresh_store.add(b"x", "c")

    def test_items_returns_a_copy_not_the_live_list(self, fresh_store):
        fresh_store.add(b"x", "c")
        items = fresh_store.items()
        items.append("tampered")
        assert len(fresh_store.items()) == 1


class TestComposerStoreRemove:
    def test_remove_valid_index(self, fresh_store):
        fresh_store.add(b"a", "1")
        fresh_store.add(b"b", "2")
        fresh_store.remove(0)
        items = fresh_store.items()
        assert len(items) == 1
        assert items[0].caption == "2"

    def test_remove_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.add(b"a", "1")
        fresh_store.remove(5)
        fresh_store.remove(-1)
        assert len(fresh_store.items()) == 1

    def test_remove_emits_changed_signal(self, fresh_store, qtbot):
        fresh_store.add(b"a", "1")
        with qtbot.waitSignal(fresh_store.changed, timeout=1000):
            fresh_store.remove(0)


class TestComposerStoreMove:
    def test_move_swaps_adjacent_items(self, fresh_store):
        fresh_store.add(b"a", "first")
        fresh_store.add(b"b", "second")
        fresh_store.move(0, 1)
        captions = [i.caption for i in fresh_store.items()]
        assert captions == ["second", "first"]

    def test_move_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.add(b"a", "only")
        fresh_store.move(0, 1)  # would move to index 1, which doesn't exist
        assert fresh_store.items()[0].caption == "only"


class TestComposerStoreSetCaption:
    def test_set_caption_updates_text_only(self, fresh_store):
        fresh_store.add(b"payload", "old caption", source="Heatmaps")
        fresh_store.set_caption(0, "new caption")
        item = fresh_store.items()[0]
        assert item.caption == "new caption"
        assert item.png_bytes == b"payload"
        assert item.source == "Heatmaps"

    def test_set_caption_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.set_caption(0, "whatever")  # nothing to update, must not raise
        assert fresh_store.items() == []


class TestComposerStoreClear:
    def test_clear_empties_the_list(self, fresh_store):
        fresh_store.add(b"a", "1")
        fresh_store.add(b"b", "2")
        fresh_store.clear()
        assert fresh_store.items() == []

    def test_clear_on_already_empty_store_does_not_emit(self, fresh_store, qtbot):
        received = []
        fresh_store.changed.connect(lambda: received.append(1))
        fresh_store.clear()
        qtbot.wait(20)
        assert received == []
