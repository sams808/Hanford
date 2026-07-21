import pytest

from composer_store import ComposerStore


def _fake_render(panel, x, y=1, label="a"):
    pass


@pytest.fixture
def fresh_store():
    # A dedicated instance per test, not the app-wide singleton -- avoids
    # tests leaking state into each other (and into the real qt_widgets/
    # qt_figure_composer code paths, which import the module-level `store`).
    return ComposerStore()


class TestComposerStoreAddRecipe:
    def test_starts_empty(self, fresh_store):
        assert fresh_store.items() == []

    def test_add_recipe_appends_item(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {"y": 2}, "caption one", source="Overview")
        items = fresh_store.items()
        assert len(items) == 1
        assert items[0].render_fn is _fake_render
        assert items[0].render_args == (1,)
        assert items[0].render_kwargs == {"y": 2}
        assert items[0].caption == "caption one"
        assert items[0].source == "Overview"

    def test_add_recipe_deep_copies_mutable_args(self, fresh_store):
        original_kwargs = {"label": ["mutable", "list"]}
        fresh_store.add_recipe(_fake_render, (1,), original_kwargs, "c")
        original_kwargs["label"].append("changed after capture")
        assert fresh_store.items()[0].render_kwargs["label"] == ["mutable", "list"]

    def test_add_recipe_emits_changed_signal(self, fresh_store, qtbot):
        with qtbot.waitSignal(fresh_store.changed, timeout=1000):
            fresh_store.add_recipe(_fake_render, (), {}, "c")

    def test_items_returns_a_copy_not_the_live_list(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        items = fresh_store.items()
        items.append("tampered")
        assert len(fresh_store.items()) == 1

    def test_each_item_gets_a_unique_stable_uid(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {}, "a")
        fresh_store.add_recipe(_fake_render, (2,), {}, "b")
        uid_a, uid_b = (i.uid for i in fresh_store.items())
        assert uid_a != uid_b
        fresh_store.set_caption(0, "renamed")
        assert fresh_store.items()[0].uid == uid_a  # survives a replace()-based edit


class TestComposerStoreRemove:
    def test_remove_valid_index(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "1")
        fresh_store.add_recipe(_fake_render, (), {}, "2")
        fresh_store.remove(0)
        items = fresh_store.items()
        assert len(items) == 1
        assert items[0].caption == "2"

    def test_remove_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "1")
        fresh_store.remove(5)
        fresh_store.remove(-1)
        assert len(fresh_store.items()) == 1

    def test_remove_emits_changed_signal(self, fresh_store, qtbot):
        fresh_store.add_recipe(_fake_render, (), {}, "1")
        with qtbot.waitSignal(fresh_store.changed, timeout=1000):
            fresh_store.remove(0)


class TestComposerStoreMove:
    def test_move_swaps_adjacent_items(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "first")
        fresh_store.add_recipe(_fake_render, (), {}, "second")
        fresh_store.move(0, 1)
        captions = [i.caption for i in fresh_store.items()]
        assert captions == ["second", "first"]

    def test_move_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "only")
        fresh_store.move(0, 1)  # would move to index 1, which doesn't exist
        assert fresh_store.items()[0].caption == "only"


class TestComposerStoreSetCaption:
    def test_set_caption_updates_text_only(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {"y": 2}, "old caption", source="Heatmaps")
        fresh_store.set_caption(0, "new caption")
        item = fresh_store.items()[0]
        assert item.caption == "new caption"
        assert item.render_args == (1,)
        assert item.source == "Heatmaps"

    def test_set_caption_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.set_caption(0, "whatever")  # nothing to update, must not raise
        assert fresh_store.items() == []


class TestComposerStoreOverrides:
    def test_title_override_defaults_to_none(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        assert fresh_store.items()[0].title_override is None

    def test_set_title_override_to_custom_text(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        fresh_store.set_title_override(0, "Custom title")
        assert fresh_store.items()[0].title_override == "Custom title"

    def test_set_title_override_to_empty_string_hides_it(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        fresh_store.set_title_override(0, "")
        assert fresh_store.items()[0].title_override == ""

    def test_set_xlabel_and_ylabel_overrides(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        fresh_store.set_xlabel_override(0, "Se (kg)")
        fresh_store.set_ylabel_override(0, "Tank")
        item = fresh_store.items()[0]
        assert item.xlabel_override == "Se (kg)"
        assert item.ylabel_override == "Tank"

    def test_overrides_out_of_range_are_a_noop(self, fresh_store):
        fresh_store.set_title_override(0, "x")  # nothing to update, must not raise
        fresh_store.set_xlabel_override(0, "x")
        fresh_store.set_ylabel_override(0, "x")
        assert fresh_store.items() == []


class TestComposerStoreKwargOverrides:
    def test_effective_kwargs_without_overrides_matches_captured(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {"y": 2, "label": "a"}, "c")
        assert fresh_store.items()[0].effective_kwargs() == {"y": 2, "label": "a"}

    def test_set_kwarg_override_replaces_one_key(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {"y": 2, "label": "a"}, "c")
        fresh_store.set_kwarg_override(0, "label", "b")
        item = fresh_store.items()[0]
        assert item.render_kwargs == {"y": 2, "label": "a"}  # original untouched
        assert item.effective_kwargs() == {"y": 2, "label": "b"}

    def test_set_kwarg_override_new_dict_object_each_time(self, fresh_store):
        # A fresh dict object per change (rather than mutating in place) is
        # what lets the Figure Composer UI's thumbnail cache key off
        # id(kwarg_overrides) to detect "this item's rendering changed".
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        fresh_store.set_kwarg_override(0, "a", 1)
        first = fresh_store.items()[0].kwarg_overrides
        fresh_store.set_kwarg_override(0, "b", 2)
        second = fresh_store.items()[0].kwarg_overrides
        assert first is not second
        assert second == {"a": 1, "b": 2}

    def test_clear_kwarg_overrides_resets_to_original(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (1,), {"y": 2}, "c")
        fresh_store.set_kwarg_override(0, "y", 99)
        fresh_store.clear_kwarg_overrides(0)
        item = fresh_store.items()[0]
        assert item.kwarg_overrides == {}
        assert item.effective_kwargs() == {"y": 2}

    def test_clear_kwarg_overrides_on_already_clear_item_does_not_emit(self, fresh_store, qtbot):
        fresh_store.add_recipe(_fake_render, (), {}, "c")
        received = []
        fresh_store.changed.connect(lambda: received.append(1))
        fresh_store.clear_kwarg_overrides(0)
        qtbot.wait(20)
        assert received == []

    def test_kwarg_override_out_of_range_is_a_noop(self, fresh_store):
        fresh_store.set_kwarg_override(0, "x", 1)  # nothing to update, must not raise
        assert fresh_store.items() == []


class TestComposerStoreClear:
    def test_clear_empties_the_list(self, fresh_store):
        fresh_store.add_recipe(_fake_render, (), {}, "1")
        fresh_store.add_recipe(_fake_render, (), {}, "2")
        fresh_store.clear()
        assert fresh_store.items() == []

    def test_clear_on_already_empty_store_does_not_emit(self, fresh_store, qtbot):
        received = []
        fresh_store.changed.connect(lambda: received.append(1))
        fresh_store.clear()
        qtbot.wait(20)
        assert received == []
