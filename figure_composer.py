"""
figure_composer.py — combines several already-rendered plot snapshots
(PNG bytes captured from any PlotWidget elsewhere in Ember, see
composer_store.ComposerItem) into one multi-panel figure with
publication-style panel labels (A, B, C, ...).

Each panel is composited as a raster image rather than re-plotted from
scratch. This is what lets Figure Composer combine ANY plot type --
including ones with their own colorbars, legends, or seaborn-specific
styling -- without needing to understand or reconstruct each plot's
internal structure. The tradeoff (panels are raster, not vector, in the
final export) is worth it for the generality; a plot that needs to stay
fully vector should be exported directly from its own workspace instead.
"""
from __future__ import annotations

from io import BytesIO
from typing import Sequence

import matplotlib.image as mpimg

from compose_science import DEFAULT_LABEL_STYLE, compute_grid_shape, panel_label

PANEL_WIDTH_IN = 4.0
PANEL_HEIGHT_IN = 3.2


def compose_figure(
    panel, items: Sequence, *, cols: int = 0, label_style: str = DEFAULT_LABEL_STYLE,
    label_fontsize: int = 14, spacing: float = 0.03,
) -> None:
    """Draws `items` (composer_store.ComposerItem, or any object with
    .png_bytes and .caption attributes) into `panel` (a qt_widgets.
    PlotWidget) as a labeled grid. cols=0 auto-picks a near-square layout;
    label_style is one of compose_science.LABEL_STYLES."""
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
    panel.set_figure_size_inches(ncols * PANEL_WIDTH_IN, rows * PANEL_HEIGHT_IN)
    panel.figure.set_facecolor("white")

    gs = panel.figure.add_gridspec(rows, ncols, wspace=spacing, hspace=spacing + 0.1)
    first_ax = None
    for i, item in enumerate(items):
        r, c = divmod(i, ncols)
        ax = panel.figure.add_subplot(gs[r, c])
        if first_ax is None:
            first_ax = ax
        img = mpimg.imread(BytesIO(item.png_bytes))
        ax.imshow(img)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        label = panel_label(i, label_style)
        if label:
            ax.text(
                0.02, 0.98, label, transform=ax.transAxes, fontsize=label_fontsize,
                fontweight="bold", va="top", ha="left", color="black",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75),
            )
        if item.caption:
            ax.set_title(item.caption, fontsize=max(label_fontsize - 4, 8))
    panel.ax = first_ax
    panel.canvas.draw_idle()
