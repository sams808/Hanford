from io import BytesIO

import matplotlib.pyplot as plt
import pytest

import figure_composer as fcomp
from composer_store import ComposerItem
from qt_widgets import PlotWidget


def _fake_png(color="red") -> bytes:
    """A small, genuinely valid PNG (not just placeholder bytes) so
    matplotlib.image.imread inside compose_figure has something real to
    decode -- exercises the actual raster-compositing path, not just the
    "did it crash" surface."""
    fig = plt.figure(figsize=(1, 1), dpi=20)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(color)
    ax.axis("off")
    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


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
    def test_single_panel(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption="Panel one")]
        fcomp.compose_figure(panel, items)
        qtbot.wait(20)
        assert len(panel.figure.axes) == 1

    def test_multiple_panels_create_one_axes_each(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption=f"Panel {i}") for i in range(4)]
        fcomp.compose_figure(panel, items)
        qtbot.wait(20)
        assert len(panel.figure.axes) == 4

    def test_panel_labels_are_drawn_as_text(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption="") for _ in range(2)]
        fcomp.compose_figure(panel, items, label_style="A, B, C")
        qtbot.wait(20)
        all_texts = [t.get_text() for ax in panel.figure.axes for t in ax.texts]
        assert "A" in all_texts
        assert "B" in all_texts

    def test_label_style_none_draws_no_text(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption="") for _ in range(2)]
        fcomp.compose_figure(panel, items, label_style="none")
        qtbot.wait(20)
        all_texts = [t.get_text() for ax in panel.figure.axes for t in ax.texts]
        assert all_texts == []

    def test_caption_becomes_axes_title(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption="My caption")]
        fcomp.compose_figure(panel, items)
        qtbot.wait(20)
        assert panel.figure.axes[0].get_title() == "My caption"

    def test_explicit_cols_produces_requested_columns(self, panel, qtbot):
        items = [ComposerItem(png_bytes=_fake_png(), caption="") for _ in range(4)]
        fcomp.compose_figure(panel, items, cols=1)
        qtbot.wait(20)
        # 4 panels, 1 column requested -> 4 rows x 1 col grid -> figure
        # taller than it is wide relative to the per-panel aspect.
        w, h = panel.figure.get_size_inches()
        assert h > w

    def test_figure_size_grows_with_more_panels(self, panel, qtbot):
        fcomp.compose_figure(panel, [ComposerItem(png_bytes=_fake_png(), caption="")])
        qtbot.wait(20)
        small = tuple(panel.figure.get_size_inches())

        many = [ComposerItem(png_bytes=_fake_png(), caption="") for _ in range(6)]
        fcomp.compose_figure(panel, many)
        qtbot.wait(20)
        large = tuple(panel.figure.get_size_inches())
        assert large[0] * large[1] > small[0] * small[1]
