"""
plot_helpers.py — shared matplotlib plotting utilities used by multiple
workspaces (Element Explorer, Tank Explorer, ...), ported from the old
app's module-level plot helper functions. Framework-agnostic aside from
taking a qt_widgets.PlotWidget (or figure_composer.ComposerCellPanel, which
mimics the same small interface) to draw into.
"""
from __future__ import annotations

import functools
import math
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
import numpy as np
import pandas as pd

from elements import normalize_element_symbol
from matrix_science import log10_safe, square_matrix_lookup

ACCENT_COLOR = "#c1502e"
BASE_COLOR = "0.55"


def composable(fn):
    """Marks a plot function as reusable by Figure Composer. After a
    successful render, remembers (fn, args, kwargs) on the panel -- if it
    has a _set_last_recipe method, which qt_widgets.PlotWidget does and the
    lightweight FakePanel test doubles in this file's own tests don't --
    so a later "-> Figure Composer" click can replay this exact call into
    a combined figure's own subfigure, instead of capturing a raster
    snapshot of it. This is what lets Figure Composer stay generic across
    every plot kind without a second, parallel rendering path: it's
    literally re-invoking this same function later, against a different
    (subfigure-backed) panel."""
    @functools.wraps(fn)
    def wrapper(panel, *args, **kwargs):
        fn(panel, *args, **kwargs)
        set_recipe = getattr(panel, "_set_last_recipe", None)
        if set_recipe is not None:
            set_recipe(fn, args, kwargs)
    return wrapper

# seaborn is imported lazily (on first actual use, via _ensure_seaborn()
# below) rather than at module scope: this module is imported eagerly at
# app startup by nearly every workspace, and seaborn alone costs ~2s of
# cold-import time -- most of it ipywidgets/IPython, pulled in for Jupyter
# widget support this desktop app never touches. Most sessions never select
# a seaborn plot style, so most sessions shouldn't pay that cost at launch.
_SEABORN_UNSET = object()
sns = _SEABORN_UNSET


def _ensure_seaborn() -> None:
    global sns
    if sns is _SEABORN_UNSET:
        try:
            import seaborn as _seaborn_module
            sns = _seaborn_module
        except Exception:  # pragma: no cover - exercised via a dedicated sns=None test
            sns = None


def numeric_plot_series(series: pd.Series) -> pd.Series:
    """Numeric conversion for plotting without mangling non-numeric columns."""
    out = pd.to_numeric(series, errors="coerce")
    return out.where(np.isfinite(out), np.nan)


def color_by_highlight(
    labels: Sequence[str], highlighted: Optional[str],
    base_labels: Optional[Sequence[str]] = None,
) -> List[str]:
    """Bar colors, highlighting the requested element/analyte when possible."""
    if not highlighted:
        return [BASE_COLOR for _ in labels]
    highlighted = str(highlighted)
    if base_labels is None:
        base_labels = labels
    colors: List[str] = []
    for label, base in zip(labels, base_labels):
        label_s, base_s = str(label), str(base)
        is_match = base_s == highlighted or label_s == highlighted or label_s.startswith(f"{highlighted} [")
        colors.append(ACCENT_COLOR if is_match else BASE_COLOR)
    return colors


def make_unique_plot_labels(pdf: pd.DataFrame, label_col: str, unit_col: str = "Units") -> pd.Series:
    """Build unique y-axis labels. Matplotlib categorical axes collapse
    duplicated labels (e.g. "Sr" appearing once for Ci rows and once for kg
    rows) -- append the unit whenever that would happen, and fall back to a
    disambiguating suffix if labels are still duplicated after that."""
    base = pdf[label_col].astype(str).fillna("NA")
    labels = base.copy()
    has_units = unit_col in pdf.columns
    duplicated_base = bool(base.duplicated(keep=False).any())
    multiple_units = bool(has_units and pdf[unit_col].dropna().astype(str).nunique() > 1)
    if has_units and (duplicated_base or multiple_units):
        labels = base + " [" + pdf[unit_col].astype(str).fillna("?") + "]"

    if labels.duplicated(keep=False).any():
        counts: Dict[str, int] = {}
        fixed: List[str] = []
        for idx, label in labels.items():
            label_s = str(label)
            counts[label_s] = counts.get(label_s, 0) + 1
            if counts[label_s] == 1:
                fixed.append(label_s)
                continue
            suffix = str(counts[label_s])
            for col in ("Analyte", "WasteSiteId", "WastePhase", "WasteType"):
                if col in pdf.columns and col != label_col:
                    val = pdf.at[idx, col]
                    if pd.notna(val):
                        suffix = str(val)
                        break
            fixed.append(f"{label_s} ({suffix})")
        labels = pd.Series(fixed, index=pdf.index)
    return labels


@composable
def plot_barh(
    panel, data: pd.DataFrame, label_col: str, value_col: str, title: str, xlabel: str,
    top_n: int = 40, highlighted_label: Optional[str] = None, log_x: bool = False,
) -> None:
    if data is None or data.empty or label_col not in data or value_col not in data:
        panel.show_message("No data to plot")
        return

    pdf = data.copy()
    pdf["_plot_value"] = numeric_plot_series(pdf[value_col])
    pdf = pdf.dropna(subset=[label_col, "_plot_value"])
    pdf = pdf[pdf["_plot_value"] > 0]
    if pdf.empty:
        panel.show_message("No positive values to plot")
        return

    pdf = pdf.sort_values("_plot_value", ascending=False).head(int(top_n)).copy()
    pdf["_plot_label"] = make_unique_plot_labels(pdf, label_col)
    pdf = pdf.iloc[::-1]  # reverse after sort/head so the largest value is at the top of barh

    # Scale figure height with the bar count, the same way plot_heatmap
    # scales with tank/element count below -- a fixed-height figure crams
    # every label into the same vertical space regardless of top_n, which
    # is what makes a 40-bar chart's y-tick labels overlap into
    # illegibility even though the panel has plenty of unused space below.
    # set_figure_size_inches() caps this at what's actually visible on its
    # own (there's no scroll area around the canvas), so no manual cap
    # needed here.
    ax = panel.reset_axes()
    height = min(max(4.5, len(pdf) * 0.26), 16.0)
    width = panel.figure.get_size_inches()[0]
    panel.set_figure_size_inches(width, height)

    colors = color_by_highlight(
        pdf["_plot_label"].astype(str).tolist(), highlighted_label,
        base_labels=pdf[label_col].astype(str).tolist(),
    )
    ax.barh(pdf["_plot_label"].astype(str), pdf["_plot_value"].to_numpy(dtype=float), color=colors)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    if log_x:
        ax.set_xscale("log")
    ax.grid(True, axis="x", alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_heatmap(panel, wide: pd.DataFrame, unit: str, mode: str, title: str) -> None:
    """Tank x element inventory heatmap. Rebuilds the panel's axes (rather
    than clearing in place) because figure size must scale with the number
    of tanks/elements to stay readable -- up to 177 tanks in this dataset."""
    if wide is None or wide.empty or "WasteSiteId" not in wide:
        panel.show_message("No heatmap data")
        return
    data = wide.copy()
    labels_y = data["WasteSiteId"].astype(str).tolist()
    elements = [c for c in data.columns if c != "WasteSiteId"]
    arr = data[elements].to_numpy(dtype=float)
    if mode == "log10_inventory":
        arr = log10_safe(arr)
        cbar_label = f"log10 inventory ({unit})"
    elif mode == "fraction":
        denom = np.nansum(arr, axis=1, keepdims=True)
        arr = np.divide(arr, denom, where=denom > 0)
        cbar_label = f"fraction of displayed {unit} inventory"
    else:
        cbar_label = f"inventory ({unit})"

    panel.figure.clear()
    height = min(max(5, len(labels_y) * 0.10), 18)
    width = min(max(8, len(elements) * 0.25), 18)
    panel.set_figure_size_inches(width, height)
    ax = panel.figure.add_subplot(111)
    im = ax.imshow(arr, aspect="auto", interpolation="nearest")
    ax.set_xticks(np.arange(len(elements)))
    ax.set_xticklabels(elements, rotation=90)
    if len(labels_y) <= 80:
        ax.set_yticks(np.arange(len(labels_y)))
        ax.set_yticklabels(labels_y, fontsize=7)
    else:
        step = max(1, len(labels_y) // 40)
        yticks = np.arange(0, len(labels_y), step)
        ax.set_yticks(yticks)
        ax.set_yticklabels([labels_y[i] for i in yticks], fontsize=7)
    ax.set_xlabel("Element")
    ax.set_ylabel("Tank")
    ax.set_title(title)
    cbar = panel.figure.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label(cbar_label)
    panel.ax = ax
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_grouped_tank_profile(panel, data: pd.DataFrame, value_col: str, title: str, top_n: int = 25) -> None:
    """Grouped horizontal bars: one cluster per element, one series per
    tank -- for comparing composition across several selected tanks at once."""
    if data is None or data.empty or value_col not in data or "Element" not in data:
        panel.show_message("No tank profile data")
        return
    pdf = data.copy()
    pdf["_plot_value"] = numeric_plot_series(pdf[value_col])
    pdf = pdf.dropna(subset=["Element", "_plot_value"])
    pdf = pdf[pdf["_plot_value"] > 0]
    if pdf.empty:
        panel.show_message("No positive data to plot")
        return

    pdf["_plot_element"] = make_unique_plot_labels(pdf, "Element")

    top_labels = (
        pdf.groupby("_plot_element", as_index=True)["_plot_value"]
        .sum()
        .sort_values(ascending=False)
        .head(int(top_n))
        .index
        .tolist()
    )
    pdf = pdf[pdf["_plot_element"].isin(top_labels)]
    pivot = pdf.pivot_table(index="_plot_element", columns="WasteSiteId", values="_plot_value", aggfunc="sum", fill_value=0.0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]

    ax = panel.reset_axes()
    pivot.plot(kind="barh", ax=ax, width=0.85)
    ax.set_xlabel(value_col)
    ax.set_ylabel("Element" if ("Units" not in pdf or pdf["Units"].nunique() <= 1) else "Element [unit]")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(title="Tank", fontsize=8)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_correlation_scan(panel, data: pd.DataFrame, target: str, top_n: int = 30) -> None:
    if data is None or data.empty or "PartnerElement" not in data or "Correlation_r" not in data:
        panel.show_message("No correlation scan data")
        return
    pdf = data.copy().dropna(subset=["Correlation_r"])
    pdf = pdf.sort_values("AbsCorrelation", ascending=False).head(int(top_n)).copy()
    if pdf.empty:
        panel.show_message("No valid correlations")
        return
    pdf = pdf.iloc[::-1]
    ax = panel.reset_axes()
    colors = ["tab:blue" if v >= 0 else "tab:red" for v in pdf["Correlation_r"]]
    labels = pdf["PartnerElement"].astype(str) + " (n=" + pdf["N_overlap_nonzero_tanks"].astype(str) + ")"
    ax.barh(labels, pdf["Correlation_r"].astype(float), color=colors, alpha=0.75)
    ax.axvline(0, color="0.2", linewidth=0.8)
    ax.set_xlim(-1.05, 1.05)
    unit = str(pdf["Units"].iloc[0]) if "Units" in pdf else ""
    metric = str(pdf["Metric"].iloc[0]) if "Metric" in pdf else ""
    ax.set_xlabel(f"Correlation coefficient r ({metric}, {unit})")
    ax.set_ylabel("Partner element")
    ax.set_title(f"Top correlations with {target}")
    ax.grid(True, axis="x", alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


def _correlation_square_from_dataframe(corr: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Numeric square correlation matrix indexed/columned by Element,
    dropping any accidental metadata columns that don't match the index."""
    if corr is None or corr.empty or "Element" not in corr:
        return pd.DataFrame(), []
    data = corr.copy().set_index("Element")
    elements = [str(e) for e in data.index.tolist()]
    keep = [e for e in elements if e in data.columns]
    data = data.loc[keep, keep]
    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    return data, keep


def _aligned_projection_values(elements: Sequence[str], totals: Optional[Dict[str, float]]) -> np.ndarray:
    if not totals:
        return np.zeros(len(elements), dtype=float)
    vals = np.array([float(totals.get(str(e), 0.0) or 0.0) for e in elements], dtype=float)
    vals[~np.isfinite(vals)] = 0.0
    return vals


def seaborn_available() -> bool:
    _ensure_seaborn()
    return sns is not None


@composable
def plot_correlation_heatmap(
    panel, corr: pd.DataFrame, title: str = "Element correlation heatmap",
    style: str = "Matplotlib lower triangle", totals: Optional[Dict[str, float]] = None,
    unit: str = "", annotate: bool = False,
) -> None:
    """Lower-triangle-only correlation heatmap (the matrix is symmetric, so
    the upper triangle is pure redundancy). Three styles:
        Matplotlib lower triangle    no seaborn dependency
        Seaborn lower triangle       nicer labels/grid/colorbar
        Seaborn + total projections  + marginal bars of log10(total+1)
    """
    data, elements = _correlation_square_from_dataframe(corr)
    if data.empty:
        panel.show_message("No correlation matrix")
        return

    n = len(elements)
    arr = data.to_numpy(dtype=float)
    upper_mask = np.triu(np.ones_like(arr, dtype=bool), k=1)
    style_norm = (style or "").lower()
    _ensure_seaborn()
    use_seaborn = ("seaborn" in style_norm) and (sns is not None)
    with_projection = ("projection" in style_norm or "total" in style_norm)

    if "seaborn" in style_norm and sns is None:
        title = title + " | seaborn not installed, using Matplotlib"
        use_seaborn = False
        with_projection = False

    panel.figure.clear()
    base_size = panel.cap_square_size_inches(min(max(6.5, n * 0.34), 19.0))

    if use_seaborn and with_projection:
        proj_raw = _aligned_projection_values(elements, totals)
        proj = np.log10(proj_raw + 1.0)
        panel.set_figure_size_inches(base_size + 2.5, base_size + 1.8)
        gs = panel.figure.add_gridspec(
            2, 2, width_ratios=[base_size, 2.2], height_ratios=[1.4, base_size], wspace=0.05, hspace=0.05,
        )
        ax_top = panel.figure.add_subplot(gs[0, 0])
        ax = panel.figure.add_subplot(gs[1, 0])
        ax_right = panel.figure.add_subplot(gs[1, 1], sharey=ax)

        x = np.arange(n)
        ax_top.bar(x, proj, color="0.45", alpha=0.85)
        ax_top.set_xlim(-0.5, n - 0.5)
        ax_top.set_ylabel(f"log10(total {unit}+1)" if unit else "log10(total+1)", fontsize=8)
        ax_top.tick_params(axis="x", bottom=False, labelbottom=False)
        ax_top.grid(True, axis="y", alpha=0.2)
        for spine in ("top", "right"):
            ax_top.spines[spine].set_visible(False)

        sns.heatmap(
            data, mask=upper_mask, vmin=-1, vmax=1, cmap="vlag", center=0, square=True,
            linewidths=0.4 if n <= 45 else 0.0, linecolor="white",
            annot=bool(annotate and n <= 25), fmt=".2f",
            cbar_kws={"label": "Correlation r", "shrink": 0.75}, ax=ax,
        )
        # suptitle, not ax.set_title(): ax sits directly below ax_top with
        # hspace=0.05 (no room reserved between rows for a title), so an
        # axes-level title renders on top of ax_top's bars instead of above
        # them. suptitle sits above the whole figure, clear of ax_top.
        panel.figure.suptitle(title)
        ax.set_xlabel("Element")
        ax.set_ylabel("Element")
        ax.tick_params(axis="x", rotation=90, labelsize=8 if n <= 55 else 6)
        ax.tick_params(axis="y", rotation=0, labelsize=8 if n <= 55 else 6)

        y_centers = np.arange(n) + 0.5
        ax_right.barh(y_centers, proj, height=0.8, color="0.45", alpha=0.85)
        ax_right.set_xlabel(f"log10(total {unit}+1)" if unit else "log10(total+1)", fontsize=8)
        ax_right.tick_params(axis="y", left=False, labelleft=False)
        ax_right.grid(True, axis="x", alpha=0.2)
        for spine in ("top", "right"):
            ax_right.spines[spine].set_visible(False)
        panel.ax = ax
    elif use_seaborn:
        panel.set_figure_size_inches(base_size, base_size)
        ax = panel.figure.add_subplot(111)
        sns.heatmap(
            data, mask=upper_mask, vmin=-1, vmax=1, cmap="vlag", center=0, square=True,
            linewidths=0.4 if n <= 45 else 0.0, linecolor="white",
            annot=bool(annotate and n <= 25), fmt=".2f",
            cbar_kws={"label": "Correlation r", "shrink": 0.8}, ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel("Element")
        ax.set_ylabel("Element")
        ax.tick_params(axis="x", rotation=90, labelsize=8 if n <= 55 else 6)
        ax.tick_params(axis="y", rotation=0, labelsize=8 if n <= 55 else 6)
        panel.ax = ax
    else:
        panel.set_figure_size_inches(base_size, base_size)
        ax = panel.figure.add_subplot(111)
        masked = np.ma.array(arr, mask=upper_mask)
        cmap = matplotlib.colormaps.get_cmap("coolwarm").copy()
        cmap.set_bad(color="white")
        im = ax.imshow(masked, vmin=-1, vmax=1, cmap=cmap, interpolation="nearest")
        ax.set_xticks(np.arange(n))
        ax.set_yticks(np.arange(n))
        ax.set_xticklabels(elements, rotation=90, fontsize=8 if n <= 55 else 6)
        ax.set_yticklabels(elements, fontsize=8 if n <= 55 else 6)
        ax.set_title(title)
        ax.set_xlabel("Element")
        ax.set_ylabel("Element")
        ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
        if n <= 50:
            ax.grid(which="minor", color="white", linestyle="-", linewidth=0.5)
        ax.tick_params(which="minor", bottom=False, left=False)
        cbar = panel.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Correlation r")
        if annotate and n <= 25:
            for i in range(n):
                for j in range(i + 1):
                    val = arr[i, j]
                    if np.isfinite(val):
                        ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7)
        panel.ax = ax

    panel.canvas.draw_idle()


@composable
def plot_pair_scatter(panel, matrix: pd.DataFrame, elements: Sequence[str], unit: str, metric: str) -> None:
    clean = [normalize_element_symbol(e) for e in elements if normalize_element_symbol(e)]
    clean = [e for e in clean if e in matrix.columns]
    if matrix is None or matrix.empty or len(clean) < 2:
        panel.show_message("Need at least two selected elements with data")
        return
    a, b = clean[0], clean[1]
    pdf = matrix[["WasteSiteId"] + clean].copy()
    pdf[a] = numeric_plot_series(pdf[a])
    pdf[b] = numeric_plot_series(pdf[b])
    pdf = pdf.dropna(subset=[a, b])
    ax = panel.reset_axes()
    if len(clean) >= 3:
        c = clean[2]
        pdf[c] = numeric_plot_series(pdf[c]).fillna(0.0)
        sc = ax.scatter(pdf[a], pdf[b], c=pdf[c], s=45, alpha=0.8)
        cbar = panel.figure.colorbar(sc, ax=ax)
        cbar.set_label(f"{c} ({metric}, {unit})")
        title = f"{a} vs {b}, colored by {c}"
    else:
        ax.scatter(pdf[a], pdf[b], s=45, alpha=0.8)
        title = f"{a} vs {b}"
    r = pdf[a].corr(pdf[b]) if len(pdf) >= 3 else np.nan
    ax.set_xlabel(f"{a} ({metric}, {unit})")
    ax.set_ylabel(f"{b} ({metric}, {unit})")
    ax.set_title(f"{title} | r = {r:.3f}" if pd.notna(r) else title)
    ax.grid(True, alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_target_vs_total(panel, data: pd.DataFrame, title: str) -> None:
    required = ["Context_TotalInventory_same_unit", "Target_Inventory_sum", "Units"]
    if data is None or data.empty or any(c not in data for c in required):
        panel.show_message("No target-vs-total data to plot")
        return
    pdf = data.copy()
    pdf["_x_total"] = numeric_plot_series(pdf["Context_TotalInventory_same_unit"])
    pdf["_y_target"] = numeric_plot_series(pdf["Target_Inventory_sum"])
    pdf = pdf.dropna(subset=["_x_total", "_y_target"])
    pdf = pdf[(pdf["_x_total"] > 0) & (pdf["_y_target"] > 0)]
    if pdf.empty:
        panel.show_message("No positive values to plot")
        return
    ax = panel.reset_axes()
    for unit in pd.unique(pdf["Units"]):
        sub = pdf[pdf["Units"] == unit]
        ax.scatter(sub["_x_total"], sub["_y_target"], label=str(unit), alpha=0.75, s=35)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Total tank inventory in same unit")
    ax.set_ylabel("Target inventory in tank")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(title="Units")
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


# ---------------------------------------------------------------------------
# kg Association Workbench (M7): coherent-colors palette + 17 plot types
# (8 functions, several parameterized by a `kind`/`mode` argument).
# ---------------------------------------------------------------------------

def _seaborn_available_or_message(panel) -> bool:
    _ensure_seaborn()
    if sns is None:
        panel.show_message("Seaborn is not installed. Run: python -m pip install seaborn")
        return False
    return True


def _use_coherent_colors(color_mode: str = "Basic") -> bool:
    """Two visual styles: Basic (conservative grayscale) and Coherent
    colors (consistent color families across correlation, co-presence,
    abundance, and positive/negative-association plots)."""
    return str(color_mode or "").strip().lower().startswith("coherent")


def _set_seaborn_theme(color_mode: str = "Basic") -> None:
    _ensure_seaborn()
    if sns is None:
        return
    if _use_coherent_colors(color_mode):
        sns.set_theme(style="whitegrid", context="notebook", font_scale=0.95)
    else:
        sns.set_theme(style="ticks", context="notebook", font_scale=0.95)


def _corr_cmap(color_mode: str = "Basic") -> str:
    return "vlag" if _use_coherent_colors(color_mode) else "coolwarm"


def _sequential_cmap(color_mode: str = "Basic") -> str:
    return "mako" if _use_coherent_colors(color_mode) else "Greys"


def _jaccard_cmap(color_mode: str = "Basic") -> str:
    return "crest" if _use_coherent_colors(color_mode) else "Greys"


def _projection_bar_color(color_mode: str = "Basic") -> str:
    return "#4C78A8" if _use_coherent_colors(color_mode) else "0.45"


def _main_point_color(color_mode: str = "Basic") -> str:
    return "#4C78A8" if _use_coherent_colors(color_mode) else "0.35"


def _line_color(color_mode: str = "Basic") -> str:
    return "#D55E00" if _use_coherent_colors(color_mode) else "0.15"


def _pair_palette_name(mode: str, color_mode: str = "Basic") -> Optional[str]:
    if not _use_coherent_colors(color_mode):
        return None
    mode = str(mode or "").lower()
    if "negative" in mode:
        return "rocket_r"
    if "positive" in mode or "jaccard" in mode:
        return "crest"
    return "flare"


def _square_matrix_from_element_table(square_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    return square_matrix_lookup(square_df)


@composable
def plot_seaborn_lower_triangle_matrix(
    panel, square_df: pd.DataFrame, title: str, cbar_label: str, cmap: str = "vlag",
    center: Optional[float] = 0.0, annotate: bool = False, totals: Optional[pd.DataFrame] = None,
    projections: bool = False, color_mode: str = "Basic",
) -> None:
    """Lower-triangle heatmap shared by the corr heatmap, corr+projections,
    and Jaccard co-presence plot types (cbar_label picks the colormap)."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    data, elements = _square_matrix_from_element_table(square_df)
    if data.empty:
        panel.show_message("No square matrix to plot")
        return
    n = len(elements)
    mask = np.triu(np.ones_like(data.to_numpy(dtype=float), dtype=bool), k=1)
    cmap = (
        _corr_cmap(color_mode) if "correlation" in cbar_label.lower()
        else (_jaccard_cmap(color_mode) if "jaccard" in cbar_label.lower() else _sequential_cmap(color_mode))
    )
    projection_color = _projection_bar_color(color_mode)
    panel.figure.clear()
    base_size = panel.cap_square_size_inches(min(max(6.5, n * 0.34), 19.0))
    if projections:
        total_map: Dict[str, float] = {}
        if totals is not None and not totals.empty and "Element" in totals.columns and "Total_inventory_kg" in totals.columns:
            total_map = {str(r.Element): float(r.Total_inventory_kg or 0.0) for r in totals.itertuples(index=False)}
        proj = np.array([math.log10(max(total_map.get(e, 0.0), 0.0) + 1.0) for e in elements], dtype=float)
        panel.set_figure_size_inches(base_size + 2.5, base_size + 1.8)
        gs = panel.figure.add_gridspec(2, 2, width_ratios=[base_size, 2.2], height_ratios=[1.4, base_size], wspace=0.05, hspace=0.05)
        ax_top = panel.figure.add_subplot(gs[0, 0])
        ax = panel.figure.add_subplot(gs[1, 0])
        ax_right = panel.figure.add_subplot(gs[1, 1], sharey=ax)
        x = np.arange(n)
        ax_top.bar(x, proj, color=projection_color, alpha=0.88)
        ax_top.set_xlim(-0.5, n - 0.5)
        ax_top.set_ylabel("log10(total kg+1)", fontsize=8)
        ax_top.tick_params(axis="x", bottom=False, labelbottom=False)
        ax_top.grid(True, axis="y", alpha=0.2)
        for spine in ("top", "right"):
            ax_top.spines[spine].set_visible(False)
    else:
        panel.set_figure_size_inches(base_size, base_size)
        ax = panel.figure.add_subplot(111)

    sns.heatmap(
        data, mask=mask, vmin=-1 if "correlation" in cbar_label.lower() else 0, vmax=1, center=center, cmap=cmap,
        square=True, linewidths=0.4 if n <= 45 else 0.0, linecolor="white",
        annot=bool(annotate and n <= 25), fmt=".2f", cbar_kws={"label": cbar_label, "shrink": 0.75}, ax=ax,
    )
    if projections:
        # suptitle, not ax.set_title(): ax sits directly below ax_top with
        # hspace=0.05 (no room reserved between rows for a title), so an
        # axes-level title renders on top of ax_top's bars instead of above
        # them. suptitle sits above the whole figure, clear of ax_top.
        panel.figure.suptitle(title)
    else:
        ax.set_title(title)
    ax.set_xlabel("Element")
    ax.set_ylabel("Element")
    ax.tick_params(axis="x", rotation=90, labelsize=8 if n <= 55 else 6)
    ax.tick_params(axis="y", rotation=0, labelsize=8 if n <= 55 else 6)

    if projections:
        y_centers = np.arange(n) + 0.5
        ax_right.barh(y_centers, proj, height=0.8, color=projection_color, alpha=0.88)
        ax_right.set_xlabel("log10(total kg+1)", fontsize=8)
        ax_right.tick_params(axis="y", left=False, labelleft=False)
        ax_right.grid(True, axis="x", alpha=0.2)
        for spine in ("top", "right"):
            ax_right.spines[spine].set_visible(False)
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_seaborn_top_associations(panel, pair_stats: pd.DataFrame, top_n: int = 30, mode: str = "preferred", color_mode: str = "Basic") -> None:
    """mode: preferred / positive / negative / jaccard -- 4 of the 17 plot types."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if pair_stats is None or pair_stats.empty:
        panel.show_message("No pair statistics. Build the workbench data first.")
        return
    pdf = pair_stats.copy()
    if mode == "positive":
        pdf = pdf[pdf["Correlation_r"] > 0].sort_values("Correlation_r", ascending=False)
        value_col, xlabel = "Correlation_r", "Positive correlation r (kg matrix)"
    elif mode == "negative":
        pdf = pdf[pdf["Correlation_r"] < 0].sort_values("Correlation_r", ascending=True)
        value_col, xlabel = "Correlation_r", "Negative correlation r (kg matrix)"
    elif mode == "jaccard":
        pdf = pdf.sort_values("Jaccard_presence", ascending=False)
        value_col, xlabel = "Jaccard_presence", "Jaccard co-presence across tanks"
    else:
        pdf = pdf.sort_values("PreferredAssociationScore_proxy", ascending=False)
        value_col, xlabel = "PreferredAssociationScore_proxy", "Preferred association score proxy"
    pdf = pdf.head(int(top_n)).copy()
    if pdf.empty:
        panel.show_message("No associations to plot")
        return
    pdf["Pair"] = pdf["Element_A"].astype(str) + "-" + pdf["Element_B"].astype(str) + "  (n=" + pdf["N_both_present"].astype(str) + ")"
    pdf = pdf.iloc[::-1]
    ax = panel.reset_axes()
    panel.set_figure_size_inches(9, max(5, min(16, 0.32 * len(pdf) + 2)))
    palette_name = _pair_palette_name(mode, color_mode)
    if palette_name:
        try:
            palette = sns.color_palette(palette_name, n_colors=len(pdf))
            sns.barplot(data=pdf, y="Pair", x=value_col, hue="Pair", palette=palette, legend=False, ax=ax, orient="h")
        except Exception:
            sns.barplot(data=pdf, y="Pair", x=value_col, color=_main_point_color(color_mode), ax=ax, orient="h")
    else:
        sns.barplot(data=pdf, y="Pair", x=value_col, color="0.55", ax=ax, orient="h")
    ax.axvline(0, color=_line_color(color_mode), linewidth=0.9)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Element pair")
    ax.set_title(f"Top kg element associations ({mode})")
    ax.grid(True, axis="x", alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_seaborn_pair_matrix(
    panel, metric_matrix: pd.DataFrame, raw_matrix: pd.DataFrame, elements: Sequence[str], metric: str,
    kind: str = "regression", max_elements: int = 8, color_mode: str = "Basic",
) -> None:
    """kind: regression / scatter / kde -- 3 of the 17 plot types. Lower
    triangle only, diagonal = histogram+KDE, points colored by whether both
    elements are present in that tank."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    clean = [e for e in elements if e in metric_matrix.columns]
    clean = clean[:max(2, int(max_elements))]
    if len(clean) < 2:
        panel.show_message("Need at least two elements in the kg matrix")
        return
    data = metric_matrix[["WasteSiteId"] + clean].copy()
    for e in clean:
        data[e] = numeric_plot_series(data[e])
    data = data.replace([np.inf, -np.inf], np.nan)
    data = data[data[clean].notna().sum(axis=1) >= 2]
    if data.empty:
        panel.show_message("No finite values for pair matrix")
        return
    n = len(clean)
    size = panel.cap_square_size_inches(min(max(2.0 * n, 7), 18))
    panel.figure.clear()
    panel.set_figure_size_inches(size, size)
    axes = panel.figure.subplots(n, n, squeeze=False)
    raw = raw_matrix.set_index("WasteSiteId") if raw_matrix is not None and not raw_matrix.empty else pd.DataFrame()
    for i, y in enumerate(clean):
        for j, x in enumerate(clean):
            ax = axes[i, j]
            if j > i:
                ax.set_axis_off()
                continue
            if i == j:
                vals = data[y].dropna()
                if vals.nunique() <= 1:
                    ax.text(0.5, 0.5, "constant", ha="center", va="center", transform=ax.transAxes)
                else:
                    sns.histplot(vals, kde=True, ax=ax, bins="auto", color=_main_point_color(color_mode))
                ax.set_ylabel("")
            else:
                sub = data[["WasteSiteId", x, y]].dropna()
                if raw is not None and not raw.empty and x in raw.columns and y in raw.columns:
                    both = (raw.loc[sub["WasteSiteId"], x].to_numpy(dtype=float) > 0) & (raw.loc[sub["WasteSiteId"], y].to_numpy(dtype=float) > 0)
                    sub = sub.assign(_both_present=both)
                else:
                    sub = sub.assign(_both_present=True)
                if sub.empty:
                    ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
                elif kind == "kde":
                    if sub[x].nunique() > 1 and sub[y].nunique() > 1 and len(sub) >= 6:
                        try:
                            sns.kdeplot(data=sub, x=x, y=y, fill=True, levels=6, thresh=0.05, cmap=_sequential_cmap(color_mode), ax=ax)
                            sns.scatterplot(data=sub, x=x, y=y, hue="_both_present", palette={False: "0.70", True: _main_point_color(color_mode)}, legend=False, s=12, alpha=0.45, ax=ax)
                        except Exception:
                            sns.scatterplot(data=sub, x=x, y=y, hue="_both_present", palette={False: "0.70", True: _main_point_color(color_mode)}, legend=False, s=18, alpha=0.65, ax=ax)
                    else:
                        sns.scatterplot(data=sub, x=x, y=y, hue="_both_present", palette={False: "0.70", True: _main_point_color(color_mode)}, legend=False, s=18, alpha=0.65, ax=ax)
                elif kind == "scatter":
                    sns.scatterplot(data=sub, x=x, y=y, hue="_both_present", palette={False: "0.70", True: _main_point_color(color_mode)}, legend=False, s=18, alpha=0.70, ax=ax)
                else:
                    if sub[x].nunique() > 1 and sub[y].nunique() > 1 and len(sub) >= 3:
                        sns.regplot(data=sub, x=x, y=y, scatter_kws={"s": 16, "alpha": 0.55, "color": _main_point_color(color_mode)}, line_kws={"linewidth": 1.0, "color": _line_color(color_mode)}, ax=ax)
                    else:
                        sns.scatterplot(data=sub, x=x, y=y, color=_main_point_color(color_mode), s=18, alpha=0.70, ax=ax)
            if i < n - 1:
                ax.set_xlabel("")
                ax.set_xticklabels([])
            else:
                ax.set_xlabel(x, fontsize=8)
            if j > 0:
                ax.set_ylabel("")
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(y, fontsize=8)
            ax.tick_params(labelsize=7)
    panel.figure.suptitle(f"Lower pair matrix - kg only - {metric}", y=0.995)
    panel.ax = axes[-1, 0]
    panel.canvas.draw_idle()


@composable
def plot_seaborn_joint_first_two(panel, metric_matrix: pd.DataFrame, elements: Sequence[str], metric: str, kind: str = "scatter", color_mode: str = "Basic") -> None:
    """kind: regression / scatter / kde -- 3 of the 17 plot types, first two selected elements only."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    clean = [e for e in elements if e in metric_matrix.columns]
    if len(clean) < 2:
        panel.show_message("Need at least two elements")
        return
    x, y = clean[0], clean[1]
    data = metric_matrix[["WasteSiteId", x, y]].copy()
    data[x] = numeric_plot_series(data[x])
    data[y] = numeric_plot_series(data[y])
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=[x, y])
    if data.empty:
        panel.show_message("No finite values for joint plot")
        return
    panel.figure.clear()
    panel.set_figure_size_inches(8, 8)
    gs = panel.figure.add_gridspec(2, 2, width_ratios=[5, 1.2], height_ratios=[1.2, 5], wspace=0.05, hspace=0.05)
    ax_top = panel.figure.add_subplot(gs[0, 0])
    ax = panel.figure.add_subplot(gs[1, 0])
    ax_right = panel.figure.add_subplot(gs[1, 1], sharey=ax)
    if kind == "kde" and data[x].nunique() > 1 and data[y].nunique() > 1 and len(data) >= 6:
        try:
            sns.kdeplot(data=data, x=x, y=y, fill=True, levels=8, thresh=0.05, cmap=_sequential_cmap(color_mode), ax=ax)
            sns.scatterplot(data=data, x=x, y=y, color=_main_point_color(color_mode), s=18, alpha=0.45, ax=ax)
        except Exception:
            sns.scatterplot(data=data, x=x, y=y, color=_main_point_color(color_mode), s=30, alpha=0.7, ax=ax)
    elif kind == "regression" and data[x].nunique() > 1 and data[y].nunique() > 1 and len(data) >= 3:
        sns.regplot(data=data, x=x, y=y, scatter_kws={"s": 30, "alpha": 0.65, "color": _main_point_color(color_mode)}, line_kws={"linewidth": 1.2, "color": _line_color(color_mode)}, ax=ax)
    else:
        sns.scatterplot(data=data, x=x, y=y, color=_main_point_color(color_mode), s=30, alpha=0.7, ax=ax)
    sns.histplot(data[x].dropna(), kde=True, color=_main_point_color(color_mode), ax=ax_top)
    sns.histplot(y=data[y].dropna(), kde=True, color=_main_point_color(color_mode), ax=ax_right)
    ax_top.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_right.tick_params(axis="y", left=False, labelleft=False)
    r = data[x].corr(data[y]) if len(data) >= 3 else np.nan
    ax.set_xlabel(f"{x} ({metric}, kg)")
    ax.set_ylabel(f"{y} ({metric}, kg)")
    ax.set_title(f"{x} vs {y} - kg only" + (f" | r={r:.3f}" if pd.notna(r) else ""))
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_seaborn_tank_similarity(panel, tank_similarity: pd.DataFrame, raw_matrix: pd.DataFrame, top_tanks: int = 40, annotate: bool = False, color_mode: str = "Basic") -> None:
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if tank_similarity is None or tank_similarity.empty or "WasteSiteId" not in tank_similarity.columns:
        panel.show_message("No tank similarity matrix")
        return
    data = tank_similarity.copy().set_index("WasteSiteId")
    tanks = [str(t) for t in data.index.tolist()]
    keep = [t for t in tanks if t in data.columns]
    data = data.loc[keep, keep]
    if raw_matrix is not None and not raw_matrix.empty and "WasteSiteId" in raw_matrix.columns:
        raw = raw_matrix.set_index("WasteSiteId")
        totals = raw.sum(axis=1).sort_values(ascending=False).head(int(top_tanks)).index.astype(str).tolist()
        keep = [t for t in totals if t in data.index]
        if len(keep) >= 2:
            data = data.loc[keep, keep]
    else:
        data = data.iloc[:int(top_tanks), :int(top_tanks)]
    n = len(data)
    if n < 2:
        panel.show_message("Need at least two tanks for tank similarity")
        return
    panel.figure.clear()
    base_size = panel.cap_square_size_inches(min(max(7, n * 0.23), 18))
    panel.set_figure_size_inches(base_size, base_size)
    ax = panel.figure.add_subplot(111)
    mask = np.triu(np.ones_like(data.to_numpy(dtype=float), dtype=bool), k=1)
    sns.heatmap(
        data, mask=mask, vmin=-1, vmax=1, center=0, cmap=_corr_cmap(color_mode), square=True,
        linewidths=0.2 if n <= 50 else 0, annot=bool(annotate and n <= 20), fmt=".2f",
        cbar_kws={"label": "Tank-to-tank correlation across selected kg elements"}, ax=ax,
    )
    ax.set_title(f"Tank similarity lower triangle - kg element vectors - top {n} tanks")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.tick_params(axis="y", rotation=0, labelsize=7)
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_seaborn_tank_element_map(panel, raw_matrix: pd.DataFrame, elements: Sequence[str], top_tanks: int = 60, metric: str = "log10_plus1", color_mode: str = "Basic") -> None:
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if raw_matrix is None or raw_matrix.empty or "WasteSiteId" not in raw_matrix.columns:
        panel.show_message("No raw kg matrix")
        return
    clean = [e for e in elements if e in raw_matrix.columns]
    if not clean:
        panel.show_message("No selected elements in raw matrix")
        return
    raw = raw_matrix[["WasteSiteId"] + clean].copy().set_index("WasteSiteId")
    raw = raw.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    top_ids = raw.sum(axis=1).sort_values(ascending=False).head(int(top_tanks)).index.tolist()
    raw = raw.loc[top_ids]
    if metric == "fraction":
        denom = raw.sum(axis=1).replace(0.0, np.nan)
        data = raw.div(denom, axis=0)
        label = "Fraction of selected kg inventory"
    else:
        data = np.log10(raw + 1.0)
        label = "log10(inventory kg + 1)"
    panel.figure.clear()
    width = min(max(7, len(clean) * 0.5), 18)
    height = min(max(6, len(raw) * 0.16), 18)
    panel.set_figure_size_inches(width, height)
    ax = panel.figure.add_subplot(111)
    sns.heatmap(data, cmap=_sequential_cmap(color_mode), cbar_kws={"label": label}, linewidths=0.0, ax=ax)
    ax.set_title(f"Tank x selected element map - kg only - top {len(raw)} tanks")
    ax.set_xlabel("Element")
    ax.set_ylabel("Tank")
    ax.tick_params(axis="x", rotation=90)
    ax.tick_params(axis="y", rotation=0, labelsize=7)
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_seaborn_presence_patterns(panel, presence_matrix: pd.DataFrame, elements: Sequence[str], top_n: int = 30, color_mode: str = "Basic") -> None:
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if presence_matrix is None or presence_matrix.empty or "WasteSiteId" not in presence_matrix.columns:
        panel.show_message("No presence matrix")
        return
    clean = [e for e in elements if e in presence_matrix.columns]
    if len(clean) < 2:
        panel.show_message("Need at least two elements")
        return
    df = presence_matrix[["WasteSiteId"] + clean].copy()
    for e in clean:
        df[e] = pd.to_numeric(df[e], errors="coerce").fillna(0).astype(int)
    df["N_selected_elements_present"] = df[clean].sum(axis=1)
    df["Combination"] = df[clean].apply(lambda row: "+".join([e for e, v in row.items() if int(v) > 0]) or "none", axis=1)
    counts = df.groupby(["Combination", "N_selected_elements_present"], as_index=False).size().rename(columns={"size": "N_tanks"})
    counts = counts[counts["Combination"] != "none"].sort_values("N_tanks", ascending=False).head(int(top_n))
    if counts.empty:
        panel.show_message("No non-empty presence patterns")
        return
    counts = counts.iloc[::-1]
    ax = panel.reset_axes()
    panel.set_figure_size_inches(10, max(5, min(16, 0.32 * len(counts) + 2)))
    sns.barplot(
        data=counts, y="Combination", x="N_tanks", hue="N_selected_elements_present",
        palette=(_sequential_cmap(color_mode) if _use_coherent_colors(color_mode) else None), dodge=False, ax=ax,
    )
    ax.set_xlabel("Number of tanks")
    ax.set_ylabel("Element combination present in tank")
    ax.set_title("Most common selected-element co-presence patterns - kg only")
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(title="N elements", fontsize=8)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_seaborn_stats_dashboard(panel, element_stats: pd.DataFrame, pair_stats: pd.DataFrame, top_n: int = 20, color_mode: str = "Basic") -> None:
    """4-panel dashboard: total-kg bars, abundance-vs-spread scatter,
    r-vs-Jaccard scatter, top-12 preferred-association bars."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if element_stats is None or element_stats.empty:
        panel.show_message("No element statistics")
        return
    elems = element_stats.sort_values("Total_inventory_kg", ascending=False).head(int(top_n)).copy()
    pairs = pair_stats.sort_values("PreferredAssociationScore_proxy", ascending=False).head(int(top_n)).copy() if pair_stats is not None and not pair_stats.empty else pd.DataFrame()
    panel.figure.clear()
    panel.set_figure_size_inches(14, 10)
    gs = panel.figure.add_gridspec(2, 2, wspace=0.32, hspace=0.35)
    ax1 = panel.figure.add_subplot(gs[0, 0])
    ax2 = panel.figure.add_subplot(gs[0, 1])
    ax3 = panel.figure.add_subplot(gs[1, 0])
    ax4 = panel.figure.add_subplot(gs[1, 1])
    if _use_coherent_colors(color_mode):
        sns.barplot(data=elems, y="Element", x="Total_inventory_kg", hue="Element", palette=sns.color_palette("mako", n_colors=len(elems)), legend=False, ax=ax1, orient="h")
    else:
        sns.barplot(data=elems, y="Element", x="Total_inventory_kg", color="0.55", ax=ax1, orient="h")
    ax1.set_xscale("log")
    ax1.set_xlabel("Total inventory (kg, log scale)")
    ax1.set_ylabel("Element")
    ax1.set_title("Selected elements: total kg")
    sns.scatterplot(data=elems, x="PresenceFraction_pct", y="Total_inventory_kg", size="Max_kg_in_one_tank", color=_main_point_color(color_mode), sizes=(30, 300), legend=False, ax=ax2)
    ax2.set_yscale("log")
    ax2.set_xlabel("Presence fraction across tanks (%)")
    ax2.set_ylabel("Total inventory (kg)")
    ax2.set_title("Abundance vs spread")
    if not pairs.empty:
        p = pairs.copy()
        p["Pair"] = p["Element_A"].astype(str) + "-" + p["Element_B"].astype(str)
        sns.scatterplot(data=p, x="Correlation_r", y="Jaccard_presence", size="N_both_present", hue="PreferredAssociationScore_proxy", palette=(_sequential_cmap(color_mode) if _use_coherent_colors(color_mode) else None), sizes=(30, 250), ax=ax3)
        ax3.set_xlim(-1.05, 1.05)
        ax3.set_xlabel("Correlation r")
        ax3.set_ylabel("Jaccard co-presence")
        ax3.set_title("Pair associations")
        p2 = p.sort_values("PreferredAssociationScore_proxy", ascending=False).head(12).iloc[::-1]
        if _use_coherent_colors(color_mode):
            sns.barplot(data=p2, y="Pair", x="PreferredAssociationScore_proxy", hue="Pair", palette=sns.color_palette("flare", n_colors=len(p2)), legend=False, ax=ax4, orient="h")
        else:
            sns.barplot(data=p2, y="Pair", x="PreferredAssociationScore_proxy", color="0.55", ax=ax4, orient="h")
        ax4.set_xlabel("Preferred association score proxy")
        ax4.set_ylabel("Pair")
        ax4.set_title("Top preferred associations")
    else:
        ax3.text(0.5, 0.5, "No pair stats", ha="center", va="center", transform=ax3.transAxes)
        ax4.text(0.5, 0.5, "No pair stats", ha="center", va="center", transform=ax4.transAxes)
    panel.ax = ax1
    panel.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Correlations "Structure" sub-tab (M8): PCA scatter, dendrogram, partial-
# vs-raw correlation comparison, element-association network graph.
# ---------------------------------------------------------------------------

@composable
def plot_pca_scatter(panel, tank_summary: pd.DataFrame, color_by: Optional[str], pca_variance: pd.DataFrame, color_mode: str = "Basic") -> None:
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if tank_summary is None or tank_summary.empty or "PC1" not in tank_summary.columns or "PC2" not in tank_summary.columns:
        panel.show_message("No PCA scores. Build the structure data first.")
        return
    pdf = tank_summary.copy()
    var_map: Dict[str, float] = {}
    if pca_variance is not None and not pca_variance.empty:
        var_map = {str(r.PC): float(r.ExplainedVarianceRatio) for r in pca_variance.itertuples(index=False)}
    xlabel = f"PC1 ({var_map.get('PC1', 0.0) * 100:.1f}%)" if var_map else "PC1"
    ylabel = f"PC2 ({var_map.get('PC2', 0.0) * 100:.1f}%)" if var_map else "PC2"

    panel.figure.clear()
    ax = panel.figure.add_subplot(111)
    hue_col = color_by if color_by and color_by in pdf.columns and pdf[color_by].notna().any() else None
    if hue_col:
        pdf[hue_col] = pdf[hue_col].astype(str).fillna("Unknown")
        palette = "tab20" if pdf[hue_col].nunique() > 10 else ("crest" if _use_coherent_colors(color_mode) else "tab10")
        sns.scatterplot(data=pdf, x="PC1", y="PC2", hue=hue_col, palette=palette, s=60, alpha=0.85, ax=ax)
        ax.legend(title=hue_col, bbox_to_anchor=(1.02, 1.0), loc="upper left", fontsize=8)
    else:
        ax.scatter(pdf["PC1"], pdf["PC2"], s=60, alpha=0.85, color=_main_point_color(color_mode))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title("Tank PCA (kg, standardized)" + (f" - colored by {color_by}" if hue_col else ""))
    ax.grid(True, alpha=0.25)
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_dendrogram(panel, cluster_linkage, cluster_labels: Sequence[str], color_mode: str = "Basic") -> None:
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if cluster_linkage is None or len(cluster_linkage) == 0 or not cluster_labels:
        panel.show_message("No clustering result. Build the structure data first.")
        return
    from scipy.cluster.hierarchy import dendrogram

    n = len(cluster_labels)
    panel.figure.clear()
    base_size = min(max(6.5, n * 0.28), 19.0)
    panel.set_figure_size_inches(base_size, 6.0)
    ax = panel.figure.add_subplot(111)
    dendrogram(
        cluster_linkage, labels=list(cluster_labels), ax=ax, leaf_rotation=90,
        leaf_font_size=8 if n <= 55 else 6, color_threshold=0, above_threshold_color=_line_color(color_mode),
    )
    ax.set_title("Tank hierarchical clustering (kg, standardized)")
    ax.set_ylabel("Distance")
    ax.grid(True, axis="y", alpha=0.2)
    panel.ax = ax
    panel.canvas.draw_idle()


@composable
def plot_partial_correlation_comparison(panel, partial_df: pd.DataFrame, raw_df: pd.DataFrame, annotate: bool = False, color_mode: str = "Basic") -> None:
    """Raw and partial (controlling for tank size) correlation heatmaps
    side by side, so the size of the "everything correlates because both
    scale with tank size" effect is directly visible."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    raw_data, raw_elements = _square_matrix_from_element_table(raw_df)
    partial_data, _partial_elements = _square_matrix_from_element_table(partial_df)
    if raw_data.empty or partial_data.empty:
        panel.show_message("No partial-correlation matrix. Build the structure data first.")
        return
    n = len(raw_elements)
    cmap = _corr_cmap(color_mode)
    panel.figure.clear()
    base_size = min(max(5.5, n * 0.32), 14.0)
    # Two side-by-side square heatmaps sharing base_size: cap it against
    # the width formula's own 2x+1.2 factor, not the raw available width,
    # or the pair would overflow even though the figure fits the ceiling.
    avail_w = panel.available_content_width_inches()
    avail_h = panel.available_content_height_inches()
    if avail_w is not None:
        base_size = min(base_size, (avail_w - 1.2) / 2)
    if avail_h is not None:
        base_size = min(base_size, avail_h - 1.0)
    panel.set_figure_size_inches(base_size * 2 + 1.2, base_size + 1.0)
    ax1 = panel.figure.add_subplot(1, 2, 1)
    ax2 = panel.figure.add_subplot(1, 2, 2)
    mask1 = np.triu(np.ones_like(raw_data.to_numpy(dtype=float), dtype=bool), k=1)
    mask2 = np.triu(np.ones_like(partial_data.to_numpy(dtype=float), dtype=bool), k=1)
    annot = bool(annotate and n <= 25)
    sns.heatmap(raw_data, mask=mask1, vmin=-1, vmax=1, center=0, cmap=cmap, square=True,
                linewidths=0.4 if n <= 45 else 0.0, linecolor="white", annot=annot, fmt=".2f",
                cbar_kws={"label": "Correlation r", "shrink": 0.75}, ax=ax1)
    sns.heatmap(partial_data, mask=mask2, vmin=-1, vmax=1, center=0, cmap=cmap, square=True,
                linewidths=0.4 if n <= 45 else 0.0, linecolor="white", annot=annot, fmt=".2f",
                cbar_kws={"label": "Partial correlation r", "shrink": 0.75}, ax=ax2)
    ax1.set_title("Raw correlation")
    ax2.set_title("Partial correlation\n(controlling for tank size)")
    for ax in (ax1, ax2):
        ax.set_xlabel("Element")
        ax.set_ylabel("Element")
        ax.tick_params(axis="x", rotation=90, labelsize=8 if n <= 55 else 6)
        ax.tick_params(axis="y", rotation=0, labelsize=8 if n <= 55 else 6)
    panel.ax = ax1
    panel.canvas.draw_idle()


@composable
def plot_element_network(panel, network_nodes: pd.DataFrame, network_edges: pd.DataFrame, color_mode: str = "Basic") -> None:
    """Element-association network: node position/size come straight from
    structure_science.element_network (a shared spring layout also used by
    html_export's Plotly version, so the two views always agree). Every
    selected element is drawn even with zero edges -- an isolated node at a
    strict threshold is itself informative."""
    if not _seaborn_available_or_message(panel):
        return
    _set_seaborn_theme(color_mode)
    if network_nodes is None or network_nodes.empty:
        panel.show_message("No network data. Build the structure data first.")
        return
    from matplotlib.lines import Line2D

    panel.figure.clear()
    ax = panel.figure.add_subplot(111)
    pos = {str(r.Element): (float(r.x), float(r.y)) for r in network_nodes.itertuples(index=False)}
    sizes = {str(r.Element): float(r.LogTotalInventory) for r in network_nodes.itertuples(index=False)}
    max_size = max(sizes.values()) if sizes else 0.0
    node_sizes = [200.0 + 1400.0 * (sizes[e] / max_size if max_size > 0 else 0.0) for e in pos]

    positive_color = "#4C78A8" if _use_coherent_colors(color_mode) else "0.25"
    negative_color = "#D55E00" if _use_coherent_colors(color_mode) else "0.55"
    if network_edges is not None and not network_edges.empty:
        for row in network_edges.itertuples(index=False):
            x1, y1 = pos[row.Element_A]
            x2, y2 = pos[row.Element_B]
            width = 0.6 + 3.0 * float(row.AbsCorrelation)
            color = positive_color if row.Sign == "positive" else negative_color
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, alpha=0.55, zorder=1)
    xs = [pos[e][0] for e in pos]
    ys = [pos[e][1] for e in pos]
    ax.scatter(xs, ys, s=node_sizes, color=_main_point_color(color_mode), edgecolor="white", linewidth=0.8, zorder=2)
    for e, (x, y) in pos.items():
        ax.annotate(e, (x, y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9, zorder=3)

    legend_handles = []
    if network_edges is not None and not network_edges.empty:
        if (network_edges["Sign"] == "positive").any():
            legend_handles.append(Line2D([0], [0], color=positive_color, lw=2, label="positive r"))
        if (network_edges["Sign"] == "negative").any():
            legend_handles.append(Line2D([0], [0], color=negative_color, lw=2, label="negative r"))
    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower left", fontsize=8)
    ax.set_title("Element association network (kg)")
    ax.axis("off")
    panel.ax = ax
    panel.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Vitrification Screening / Candidate Search / Blend Partners (M10), ported
# from the old app's plot_vitrification_burden / plot_candidate_scores /
# plot_blend_scores.
# ---------------------------------------------------------------------------

@composable
def plot_vitrification_burden(panel, data: pd.DataFrame, title: str = "Vitrification screening map") -> None:
    required = ["Total_kg_inventory", "Total_Ci_inventory", "frac_problem_elements_proxy", "frac_glass_former_or_intermediate", "WasteSiteId"]
    if data is None or data.empty or any(c not in data for c in required):
        panel.show_message("No vitrification screening data")
        return
    pdf = data.copy()
    for c in required[:-1]:
        pdf[c] = numeric_plot_series(pdf[c]).fillna(0.0)
    pdf = pdf[(pdf["Total_kg_inventory"] > 0) | (pdf["Total_Ci_inventory"] > 0)]
    if pdf.empty:
        panel.show_message("No positive tank inventory")
        return
    ax = panel.reset_axes()
    size = 40 + 500 * pdf["frac_glass_former_or_intermediate"].clip(lower=0, upper=1)
    sc = ax.scatter(
        pdf["Total_kg_inventory"].clip(lower=1e-30), pdf["Total_Ci_inventory"].clip(lower=1e-30),
        c=pdf["frac_problem_elements_proxy"].clip(lower=0), s=size, alpha=0.75,
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Total chemical inventory (kg)")
    ax.set_ylabel("Total radiological inventory (Ci)")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    cbar = panel.figure.colorbar(sc, ax=ax)
    cbar.set_label("Problem-element proxy fraction (kg/kg)")
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_candidate_scores(panel, data: pd.DataFrame, score_col: str = "User_search_score_proxy", top_n: int = 30) -> None:
    if data is None or data.empty or score_col not in data or "WasteSiteId" not in data:
        panel.show_message("No candidate ranking data")
        return
    pdf = data.copy()
    pdf["_score"] = numeric_plot_series(pdf[score_col])
    pdf = pdf.dropna(subset=["_score"]).sort_values("_score", ascending=False).head(int(top_n)).iloc[::-1]
    if pdf.empty:
        panel.show_message("No candidate scores to plot")
        return
    ax = panel.reset_axes()
    ax.barh(pdf["WasteSiteId"].astype(str), pdf["_score"].astype(float), color=BASE_COLOR)
    ax.set_xlabel(f"{score_col} (dimensionless proxy score)")
    ax.set_ylabel("Tank")
    ax.set_title("Candidate tank ranking")
    ax.grid(True, axis="x", alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


@composable
def plot_blend_scores(panel, data: pd.DataFrame, top_n: int = 30) -> None:
    if data is None or data.empty or "Blend_complement_score_proxy" not in data or "PartnerTank" not in data:
        panel.show_message("No blend partner data")
        return
    pdf = data.copy()
    pdf["_score"] = numeric_plot_series(pdf["Blend_complement_score_proxy"])
    pdf = pdf.dropna(subset=["_score"]).sort_values("_score", ascending=False).head(int(top_n)).iloc[::-1]
    if pdf.empty:
        panel.show_message("No blend scores to plot")
        return
    ax = panel.reset_axes()
    ax.barh(pdf["PartnerTank"].astype(str), pdf["_score"].astype(float), color=BASE_COLOR)
    ax.set_xlabel("Blend complement score (dimensionless proxy)")
    ax.set_ylabel("Partner tank")
    base = str(pdf["BaseTank"].iloc[0]) if "BaseTank" in pdf and len(pdf) else "base"
    ax.set_title(f"Potential blend partners for {base}")
    ax.grid(True, axis="x", alpha=0.25)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()
