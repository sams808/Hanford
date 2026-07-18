"""
plot_helpers.py — shared matplotlib plotting utilities used by multiple
workspaces (Element Explorer, Tank Explorer, ...), ported from the old
app's module-level plot helper functions. Framework-agnostic aside from
taking a qt_widgets.PlotWidget to draw into.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
import numpy as np
import pandas as pd

from elements import normalize_element_symbol
from matrix_science import log10_safe

try:
    import seaborn as sns
except Exception:  # pragma: no cover - exercised via a dedicated sns=None test
    sns = None

ACCENT_COLOR = "#c1502e"
BASE_COLOR = "0.55"


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

    panel.ax.clear()
    ax = panel.ax
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
    panel.figure.set_size_inches(width, height, forward=True)
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
    panel.canvas.draw_idle()


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

    panel.ax.clear()
    ax = panel.ax
    pivot.plot(kind="barh", ax=ax, width=0.85)
    ax.set_xlabel(value_col)
    ax.set_ylabel("Element" if ("Units" not in pdf or pdf["Units"].nunique() <= 1) else "Element [unit]")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(title="Tank", fontsize=8)
    panel.figure.tight_layout()
    panel.canvas.draw_idle()


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
    panel.ax.clear()
    ax = panel.ax
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
    return sns is not None


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
    use_seaborn = ("seaborn" in style_norm) and (sns is not None)
    with_projection = ("projection" in style_norm or "total" in style_norm)

    if "seaborn" in style_norm and sns is None:
        title = title + " | seaborn not installed, using Matplotlib"
        use_seaborn = False
        with_projection = False

    panel.figure.clear()
    base_size = min(max(6.5, n * 0.34), 19.0)

    if use_seaborn and with_projection:
        proj_raw = _aligned_projection_values(elements, totals)
        proj = np.log10(proj_raw + 1.0)
        panel.figure.set_size_inches(base_size + 2.5, base_size + 1.8, forward=True)
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
        ax.set_title(title)
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
        panel.figure.set_size_inches(base_size, base_size, forward=True)
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
        panel.figure.set_size_inches(base_size, base_size, forward=True)
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
    panel.ax.clear()
    ax = panel.ax
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
    panel.ax.clear()
    ax = panel.ax
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
