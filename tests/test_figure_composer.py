import pytest

import figure_composer as fcomp
from composer_store import ComposerItem
from qt_widgets import PlotWidget


def _fake_plot(panel, value, *, label="default"):
    ax = panel.reset_axes()
    ax.plot([0, 1], [0, value])
    ax.set_title(f"Fake plot ({label})")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    panel.ax = ax
    panel.canvas.draw_idle()


def _erroring_plot(panel, *args, **kwargs):
    raise ValueError("boom")


def _item(value=1, label="default", caption="", **overrides) -> ComposerItem:
    return ComposerItem(render_fn=_fake_plot, render_args=(value,), render_kwargs={"label": label}, caption=caption, **overrides)


@pytest.fixture
def panel(qtbot):
    p = PlotWidget()
    qtbot.addWidget(p)
    return p


class TestComposeFigureEmpty:
    def test_no_items_shows_message(self, panel, qtbot):
        fcomp.compose_figure(panel, [])
        qtbot.wait(20)
        # show_message() turns the axes off and writes centered text --
        # confirm no crash and that a message-style axes was drawn.
        assert panel.ax.axison is False


class TestComposeFigureRenders:
    def test_single_panel_creates_one_real_axes(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item()])
        qtbot.wait(20)
        assert len(panel.figure.axes) == 1

    def test_panel_is_a_live_vector_axes_not_a_raster_image(self, panel, qtbot):
        # The whole point of the recipe-based redesign: the panel's axes
        # holds a real Line2D artist from the recipe, not an AxesImage
        # showing a rasterized picture of one.
        fcomp.compose_figure(panel, [_item(value=5)])
        qtbot.wait(20)
        ax = panel.figure.axes[0]
        assert len(ax.lines) == 1
        assert ax.lines[0].get_ydata()[-1] == 5
        assert len(ax.images) == 0

    def test_multiple_panels_create_one_axes_each(self, panel, qtbot):
        items = [_item(value=i) for i in range(4)]
        fcomp.compose_figure(panel, items)
        qtbot.wait(20)
        assert len(panel.figure.axes) == 4

    def test_multiple_panels_use_isolated_subfigures(self, panel, qtbot):
        # Confirms the isolation SubFigure is relied on for: each panel's
        # own reset_axes()/figure.clear() must never touch a sibling's.
        items = [_item(value=1, label="one"), _item(value=2, label="two")]
        fcomp.compose_figure(panel, items)
        qtbot.wait(20)
        titles = sorted(ax.get_title() for ax in panel.figure.axes)
        assert titles == ["Fake plot (one)", "Fake plot (two)"]

    def test_panel_labels_are_drawn_on_the_subfigure(self, panel, qtbot):
        items = [_item(), _item()]
        fcomp.compose_figure(panel, items, label_style="A, B, C")
        qtbot.wait(20)
        all_texts = [t.get_text() for sf in panel.figure.subfigs for t in sf.texts]
        assert "A" in all_texts
        assert "B" in all_texts

    def test_label_style_none_draws_no_text(self, panel, qtbot):
        items = [_item(), _item()]
        fcomp.compose_figure(panel, items, label_style="none")
        qtbot.wait(20)
        all_texts = [t.get_text() for sf in panel.figure.subfigs for t in sf.texts]
        assert all_texts == []

    def test_recipe_supplies_the_title_by_default(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item(label="mine")])
        qtbot.wait(20)
        assert panel.figure.axes[0].get_title() == "Fake plot (mine)"

    def test_title_override_replaces_the_recipes_own_title(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item(title_override="Custom title")])
        qtbot.wait(20)
        assert panel.figure.axes[0].get_title() == "Custom title"

    def test_title_override_empty_string_hides_title(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item(title_override="")])
        qtbot.wait(20)
        assert panel.figure.axes[0].get_title() == ""

    def test_xlabel_and_ylabel_overrides(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item(xlabel_override="Se (kg)", ylabel_override="Tank")])
        qtbot.wait(20)
        ax = panel.figure.axes[0]
        assert ax.get_xlabel() == "Se (kg)"
        assert ax.get_ylabel() == "Tank"

    def test_kwarg_override_changes_what_the_recipe_draws(self, panel, qtbot):
        item = ComposerItem(
            render_fn=_fake_plot, render_args=(1,), render_kwargs={"label": "original"},
            caption="", kwarg_overrides={"label": "overridden"},
        )
        fcomp.compose_figure(panel, [item])
        qtbot.wait(20)
        assert panel.figure.axes[0].get_title() == "Fake plot (overridden)"

    def test_erroring_recipe_shows_a_message_instead_of_crashing(self, panel, qtbot):
        item = ComposerItem(render_fn=_erroring_plot, render_args=(), render_kwargs={}, caption="")
        fcomp.compose_figure(panel, [item])  # must not raise
        qtbot.wait(20)
        assert len(panel.figure.axes) == 1

    def test_explicit_cols_produces_requested_columns(self, panel, qtbot):
        items = [_item() for _ in range(4)]
        fcomp.compose_figure(panel, items, cols=1)
        qtbot.wait(20)
        # 4 panels, 1 column requested -> 4 rows x 1 col grid -> figure
        # taller than it is wide relative to the per-panel aspect.
        w, h = panel.figure.get_size_inches()
        assert h > w

    def test_figure_size_grows_with_more_panels(self, panel, qtbot):
        fcomp.compose_figure(panel, [_item()])
        qtbot.wait(20)
        small = tuple(panel.figure.get_size_inches())

        many = [_item() for _ in range(6)]
        fcomp.compose_figure(panel, many)
        qtbot.wait(20)
        large = tuple(panel.figure.get_size_inches())
        assert large[0] * large[1] > small[0] * small[1]


class TestRenderThumbnailPng:
    def test_returns_valid_png_bytes(self):
        png = fcomp.render_thumbnail_png(_item(value=3))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_erroring_recipe_still_returns_a_png(self):
        item = ComposerItem(render_fn=_erroring_plot, render_args=(), render_kwargs={}, caption="")
        png = fcomp.render_thumbnail_png(item)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
