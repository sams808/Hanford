"""
make_logo.py — generates Ember's placeholder brand assets into assets/:
  ember_logo.png (512x512, window/taskbar icon source)
  ember.ico      (multi-size Windows icon, for the exe + title bar)

Design: a simple layered flame/ember glow (deep red core -> the app's own
warm accent orange -> a bright yellow-white tip), on the same dark ink
background qt_theme.py's dark palette uses -- ties the icon to both the
app's name and its vitrification/kiln subject matter. This is explicitly
a placeholder (per the project plan) until real branding is supplied;
regenerate any time: python make_logo.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

INK = "#201a16"        # qt_theme.DARK_PALETTE["bg"]
CORE = "#7a2a17"        # deep ember red
ACCENT = "#c1502e"      # qt_theme.PALETTE["accent"]
ACCENT_HOVER = "#e0703f"  # qt_theme.DARK_PALETTE["accent"]
TIP = "#ffd27a"         # bright glowing tip


def _draw_mark(ax) -> None:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")

    # Three layered flame blobs (outer -> inner -> tip), each a slightly
    # squashed/offset circle stack rather than a literal flame outline --
    # simple shapes read cleanly at small icon sizes.
    ax.add_patch(Circle((5.0, 4.6), 3.15, facecolor=CORE, edgecolor="none", zorder=1))
    ax.add_patch(Circle((5.0, 4.3), 2.55, facecolor=ACCENT, edgecolor="none", zorder=2))
    ax.add_patch(Circle((5.05, 3.85), 1.85, facecolor=ACCENT_HOVER, edgecolor="none", zorder=3, alpha=0.95))
    ax.add_patch(Circle((5.1, 3.55), 1.05, facecolor=TIP, edgecolor="none", zorder=4, alpha=0.95))
    # A few small drifting ember sparks.
    for x, y, r in [(7.6, 6.6, 0.22), (7.95, 7.55, 0.14), (2.55, 7.0, 0.16)]:
        ax.add_patch(Circle((x, y), r, facecolor=TIP, edgecolor="none", zorder=5, alpha=0.85))


def make_logo(path: str, px: int = 512) -> None:
    fig = plt.figure(figsize=(px / 100, px / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    bg = FancyBboxPatch(
        (0.25, 0.25), 9.5, 9.5, boxstyle="round,pad=0.02,rounding_size=1.6",
        facecolor=INK, edgecolor="none",
    )
    ax.add_patch(bg)
    _draw_mark(ax)
    fig.savefig(path, transparent=True)
    plt.close(fig)


def make_ico(png_path: str, ico_path: str) -> None:
    from PIL import Image
    img = Image.open(png_path)
    img.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    logo = os.path.join(ASSETS, "ember_logo.png")
    make_logo(logo)
    make_ico(logo, os.path.join(ASSETS, "ember.ico"))
    print("assets written to", ASSETS)
