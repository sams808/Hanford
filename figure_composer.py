"""
figure_composer.py — combines several captured plot "recipes" (see
composer_store.ComposerItem) into one multi-panel figure with
publication-style panel labels (A, B, C, ...).

Each panel is redrawn from its own recipe -- the exact plot_helpers
function and arguments used to draw it the first time -- into its own
matplotlib SubFigure (one cell of the combined figure's grid), rather than
composited as a raster image of what it looked like at capture time. This
keeps every panel a real, live, vector Axes in the final figure: sharp at
any export size, and still carrying its own real colorbars/legends/
gridspec-based marginal plots exactly as the source plot built them --
because it's the SAME plotting code, not a picture of its output.

A SubFigure fully isolates one panel's figure.clear()/add_subplot() calls
from its siblings (confirmed empirically: clearing and rebuilding one
subfigure leaves every other subfigure in the parent figure untouched),
which is what makes reusing plot_helpers functions completely unmodified
safe here -- most of them call panel.figure.clear() as their first step to
reset for a fresh render, which would wipe out every other panel if
panel.figure were the shared top-level Figure instead.
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional, Sequence, Tuple

from compose_science import DEFAULT_LABEL_STYLE, compute_grid_shape, panel_label

PANEL_WIDTH_IN = 4.0
PANEL_HEIGHT_IN = 3.2


class _NullCanvas:
    """draw_idle() is meaningless off-screen -- every plot_helpers function
    calls panel.canvas.draw_idle() as its last step, so this just needs to
    accept and ignore the call."""

    def draw_idle(self) -> None:
        pass


class _FigureCompat:
    """SubFigure implements most of Figure's interface (add_subplot,
    add_gridspec, subplots, colorbar, suptitle, clear, set_facecolor -- all
    confirmed to work identically) but not quite all of it: get_size_inches
    and tight_layout raise AttributeError on a SubFigure, and several
    plot_helpers functions call panel.figure.get_size_inches()/
    tight_layout() directly. Rather than touch those functions (which need
    to stay identical to how they draw outside the composer), wrap
    whichever figure-like object a panel is given so those two calls
    degrade gracefully; everything else forwards straight through
    unchanged via __getattr__."""

    def __init__(self, figure) -> None:
        self._figure = figure

    def __getattr__(self, name):
        return getattr(self._figure, name)

    def get_size_inches(self):
        if hasattr(self._figure, "get_size_inches"):
            return self._figure.get_size_inches()
        return (PANEL_WIDTH_IN, PANEL_HEIGHT_IN)

    def tight_layout(self, *args, **kwargs) -> None:
        if hasattr(self._figure, "tight_layout"):
            self._figure.tight_layout(*args, **kwargs)
        # else: a SubFigure has no equivalent -- its child axes still get
        # matplotlib's normal default padding, just not auto-tightened.


class ComposerCellPanel:
    """Minimal PlotWidget-shaped adapter so any existing plot_helpers
    function can draw into one cell of a shared composed Figure -- a
    SubFigure -- instead of owning a whole standalone Figure. This is what
    lets Figure Composer reuse the exact same plotting code that draws
    each panel in its own workspace, rather than maintaining a second
    rendering path. Also used, wrapping a bare standalone Figure instead of
    a SubFigure, to render gallery thumbnails off-screen.

    A SubFigure's size is dictated by the parent figure's gridspec cell,
    not independently settable (no set_size_inches), so size-related calls
    are no-ops there; a standalone Figure (thumbnails) does support it, and
    resizing it IS worth doing so content-driven sizing (e.g. a heatmap
    wanting to be square, or taller for more bars) still shapes the
    thumbnail sensibly. Either way, the *relative* proportions plot_helpers
    functions build internally (gridspec width/height_ratios for e.g. a
    heatmap's marginal bars) work unchanged, since those are ratios, not
    absolute inches."""

    def __init__(self, figure) -> None:
        self.figure = _FigureCompat(figure)
        self.ax = self.figure.add_subplot(111)
        self.canvas = _NullCanvas()
        # Recorded, not acted on, when wrapping a SubFigure (see
        # set_figure_size_inches below) -- compose_figure() reads this back
        # from a throwaway pre-measurement pass so a content-heavy panel
        # (e.g. plot_barh asking for extra height because it has 40 bars)
        # can get a taller row instead of being crushed into the uniform
        # default cell size, which a SubFigure can't be individually
        # resized out of after the fact.
        self.requested_size: Optional[Tuple[float, float]] = None

    def reset_axes(self):
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        return self.ax

    def show_message(self, message: str) -> None:
        self.reset_axes()
        self.ax.axis("off")
        self.ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True,
                      transform=self.ax.transAxes, fontsize=10, color="0.4")

    def set_figure_size_inches(self, width: float, height: float, *, cap_to_visible: bool = True) -> None:
        self.requested_size = (width, height)
        if hasattr(self.figure, "set_size_inches"):
            self.figure.set_size_inches(width, height)

    def available_content_width_inches(self, reserve_px: int = 280):
        return None

    def available_content_height_inches(self):
        return None

    def cap_square_size_inches(self, ideal: float) -> float:
        return ideal


def _render_item(cell: ComposerCellPanel, item) -> None:
    """Replays one item's recipe into `cell`, then layers its title/axis-
    label overrides on top -- applied AFTER the recipe renders, directly on
    whichever axes the recipe itself left as the panel's "main" one (every
    plot_helpers function ends by setting panel.ax to it, even when it
    built several sub-axes internally e.g. marginal bars). This works
    generically for any recipe without each plot_helpers function needing
    to know Figure Composer exists."""
    try:
        item.render_fn(cell, *item.render_args, **item.effective_kwargs())
    except Exception as exc:
        cell.show_message(f"Could not re-render this panel:\n{exc}")
        return
    ax = cell.ax
    if ax is None:
        return
    if item.title_override is not None:
        ax.set_title(item.title_override)
    if item.xlabel_override is not None:
        ax.set_xlabel(item.xlabel_override)
    if item.ylabel_override is not None:
        ax.set_ylabel(item.ylabel_override)


def _measure_preferred_size(item) -> Optional[Tuple[float, float]]:
    """Cheaply discovers whether this item's recipe asks for a content-
    driven figure size (e.g. plot_barh growing taller for more bars) by
    replaying it once into a tiny, low-DPI, throwaway Figure and reading
    back what it requested via ComposerCellPanel.requested_size. A
    SubFigure can't be resized after the fact (see _FigureCompat), so
    compose_figure needs to know this BEFORE building the real grid, to
    size that item's row/column generously enough in the first place.
    Returns None if the recipe never calls set_figure_size_inches (happy
    with the uniform default) or fails to render at all. Starts from the
    uniform default size (not some arbitrary tiny placeholder) because a
    function like plot_barh reads back "whatever the current figure width
    already is" to preserve it while only changing height -- measured from
    a 1x1in figure, that read-back would itself just be the meaningless
    number 1.0, not a sensible width."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(PANEL_WIDTH_IN, PANEL_HEIGHT_IN), dpi=40)
    cell = ComposerCellPanel(fig)
    try:
        item.render_fn(cell, *item.render_args, **item.effective_kwargs())
    except Exception:
        return None
    return cell.requested_size


def compose_figure(
    panel, items: Sequence, *, cols: int = 0, label_style: str = DEFAULT_LABEL_STYLE,
    label_fontsize: int = 14, spacing: float = 0.05,
) -> None:
    """Draws `items` (composer_store.ComposerItem) into `panel` (a
    qt_widgets.PlotWidget) as a labeled grid of live subfigures. cols=0
    auto-picks a near-square layout; label_style is one of
    compose_science.LABEL_STYLES."""
    n = len(items)
    if n == 0:
        # show_message() reuses panel.ax, so this must run BEFORE
        # figure.clear() below -- clearing first would orphan panel.ax
        # (removed from the figure's axes list, but the Python reference
        # still exists), leaving show_message() drawing into an axes that's
        # no longer actually part of the figure.
        panel.show_message('No panels yet -- click "-> Figure Composer" on any plot to add one.')
        return
    panel.figure.clear()

    rows, ncols = compute_grid_shape(n, cols)

    # Each row/column starts at the uniform default and grows to fit
    # whichever item in it asked for more -- a wide heatmap or a bar chart
    # with many rows gets the room it needs instead of being crushed into
    # a fixed-size cell (which would otherwise leave e.g. its tick labels
    # illegibly overlapping).
    col_widths = [PANEL_WIDTH_IN] * ncols
    row_heights = [PANEL_HEIGHT_IN] * rows
    for i, item in enumerate(items):
        preferred = _measure_preferred_size(item)
        if preferred is None:
            continue
        r, c = divmod(i, ncols)
        w, h = preferred
        col_widths[c] = max(col_widths[c], w)
        row_heights[r] = max(row_heights[r], h)

    panel.set_figure_size_inches(sum(col_widths), sum(row_heights))
    panel.figure.set_facecolor("white")

    subfigs = panel.figure.subfigures(
        rows, ncols, wspace=spacing, hspace=spacing + 0.08, squeeze=False,
        width_ratios=col_widths, height_ratios=row_heights,
    )
    first_ax = None
    for i, item in enumerate(items):
        r, c = divmod(i, ncols)
        subfig = subfigs[r, c]
        subfig.set_facecolor("white")
        cell = ComposerCellPanel(subfig)
        _render_item(cell, item)
        if first_ax is None:
            first_ax = cell.ax
        label = panel_label(i, label_style)
        if label:
            subfig.text(
                0.0, 0.99, label, transform=subfig.transSubfigure, fontsize=label_fontsize,
                fontweight="bold", va="top", ha="left", color="black",
            )
    panel.ax = first_ax
    panel.canvas.draw_idle()


def render_thumbnail_png(item, *, width_in: float = 1.9, height_in: float = 1.4, dpi: int = 90) -> bytes:
    """Small PNG for the Figure Composer gallery's list icon -- re-renders
    the item's recipe into a standalone throwaway Figure (not a Qt canvas)
    at thumbnail size, reusing the same ComposerCellPanel adapter (and
    override-application logic) the real composed figure uses."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(width_in, height_in), dpi=dpi)
    fig.set_facecolor("white")
    cell = ComposerCellPanel(fig)
    _render_item(cell, item)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white", bbox_inches="tight")
    return buf.getvalue()
