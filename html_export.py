"""
html_export.py — interactive Plotly HTML exports for the Correlations
"Structure" sub-tab: full correlation heatmap, PCA scatter, and the
element-association network graph. Each embeds plotly.js directly
(include_plotlyjs=True) so the exported file works fully offline -- no CDN
dependency once written to disk. The Qt layer opens the result via
os.startfile().

plotly.graph_objects is imported lazily inside each export function rather
than at module scope: this module is imported eagerly at app startup, and
cold-importing plotly costs real time that only the sessions which actually
use "Export interactive HTML" should pay.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from matrix_science import square_matrix_lookup


def export_correlation_heatmap_html(
    path: Union[str, Path], corr_df: pd.DataFrame, title: str = "Element correlation heatmap",
) -> Path:
    """Full (not lower-triangle -- Plotly's own hover/zoom makes the
    redundancy harmless and simplifies the trace) correlation heatmap with
    per-cell hover text."""
    import plotly.graph_objects as go

    data, elements = square_matrix_lookup(corr_df)
    if data.empty:
        raise ValueError("No correlation matrix to export.")
    z = data.to_numpy(dtype=float)
    fig = go.Figure(data=go.Heatmap(
        z=z, x=elements, y=elements, zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
        zmid=0, colorbar=dict(title="r"),
        hovertemplate="%{y} x %{x}<br>r = %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(title=title, xaxis=dict(tickangle=90), yaxis=dict(autorange="reversed"), width=900, height=900)
    return _write(fig, path)


def export_pca_scatter_html(
    path: Union[str, Path], tank_summary: pd.DataFrame, color_by: Optional[str] = None,
    pca_variance: Optional[pd.DataFrame] = None, title: str = "Tank PCA (kg, standardized)",
) -> Path:
    import plotly.graph_objects as go

    if tank_summary is None or tank_summary.empty or "PC1" not in tank_summary.columns:
        raise ValueError("No PCA scores to export.")
    var_map = {}
    if pca_variance is not None and not pca_variance.empty:
        var_map = {str(r.PC): float(r.ExplainedVarianceRatio) for r in pca_variance.itertuples(index=False)}
    xlabel = f"PC1 ({var_map.get('PC1', 0.0) * 100:.1f}%)" if var_map else "PC1"
    ylabel = f"PC2 ({var_map.get('PC2', 0.0) * 100:.1f}%)" if var_map else "PC2"

    hover_cols = [c for c in ["WasteSiteId", "Cluster", "TankFarm", "TankType", "TankStatus", "Dominant waste phase"] if c in tank_summary.columns]
    custom_data = tank_summary[hover_cols] if hover_cols else None
    hover_lines = "<br>".join(f"{c}: %{{customdata[{i}]}}" for i, c in enumerate(hover_cols))

    fig = go.Figure()
    if color_by and color_by in tank_summary.columns and tank_summary[color_by].notna().any():
        groups = tank_summary.copy()
        groups[color_by] = groups[color_by].astype(str).fillna("Unknown")
        for value, sub in groups.groupby(color_by):
            fig.add_trace(go.Scatter(
                x=sub["PC1"], y=sub["PC2"], mode="markers", name=str(value),
                customdata=sub[hover_cols].to_numpy() if hover_cols else None,
                hovertemplate=(hover_lines + "<extra></extra>") if hover_cols else None,
                marker=dict(size=10, opacity=0.85),
            ))
        fig.update_layout(legend_title=color_by)
    else:
        fig.add_trace(go.Scatter(
            x=tank_summary["PC1"], y=tank_summary["PC2"], mode="markers",
            customdata=custom_data.to_numpy() if custom_data is not None else None,
            hovertemplate=(hover_lines + "<extra></extra>") if hover_cols else None,
            marker=dict(size=10, opacity=0.85),
        ))
    fig.update_layout(title=title, xaxis_title=xlabel, yaxis_title=ylabel, width=900, height=700)
    return _write(fig, path)


def export_network_html(
    path: Union[str, Path], network_nodes: pd.DataFrame, network_edges: pd.DataFrame,
    title: str = "Element association network (kg)",
) -> Path:
    """Draws the SAME node positions structure_science.element_network
    already computed (nodes carry x/y from a shared spring layout), so this
    view and the matplotlib plot_element_network view always agree."""
    import plotly.graph_objects as go

    if network_nodes is None or network_nodes.empty:
        raise ValueError("No network data to export.")
    positions = {str(r.Element): (float(r.x), float(r.y)) for r in network_nodes.itertuples(index=False)}

    fig = go.Figure()
    if network_edges is not None and not network_edges.empty:
        for sign, color in [("positive", "#4C78A8"), ("negative", "#D55E00")]:
            sub = network_edges[network_edges["Sign"] == sign]
            if sub.empty:
                continue
            edge_x, edge_y = [], []
            for row in sub.itertuples(index=False):
                x1, y1 = positions[row.Element_A]
                x2, y2 = positions[row.Element_B]
                edge_x += [x1, x2, None]
                edge_y += [y1, y2, None]
            fig.add_trace(go.Scatter(
                x=edge_x, y=edge_y, mode="lines", line=dict(color=color, width=1.5),
                name=f"{sign} r", hoverinfo="skip",
            ))

    max_log = float(network_nodes["LogTotalInventory"].max()) if "LogTotalInventory" in network_nodes.columns and not network_nodes.empty else 0.0
    sizes = [
        12.0 + 28.0 * (float(v) / max_log if max_log > 0 else 0.0)
        for v in network_nodes.get("LogTotalInventory", pd.Series([0.0] * len(network_nodes)))
    ]
    fig.add_trace(go.Scatter(
        x=[positions[e][0] for e in network_nodes["Element"]], y=[positions[e][1] for e in network_nodes["Element"]],
        mode="markers+text", text=list(network_nodes["Element"]), textposition="top center",
        marker=dict(size=sizes, color="#4C78A8", line=dict(color="white", width=1)),
        customdata=network_nodes[["Total_inventory_kg", "N_edges"]].to_numpy() if {"Total_inventory_kg", "N_edges"}.issubset(network_nodes.columns) else None,
        hovertemplate="%{text}<br>Total kg: %{customdata[0]:.4g}<br>Edges: %{customdata[1]}<extra></extra>",
        name="Element",
    ))
    fig.update_layout(
        title=title, showlegend=True, width=900, height=800,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return _write(fig, path)


def _write(fig: go.Figure, path: Union[str, Path]) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_path), include_plotlyjs=True)
    return out_path
