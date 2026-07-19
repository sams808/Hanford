"""
structure_science.py — the Correlations "Structure" sub-tab's analytics:
PCA + hierarchical clustering of tanks, a partial-correlation matrix
controlling for tank size, and element-association network graph edges.

Entirely NEW capability (the old app has no equivalent -- no scipy/sklearn/
networkx dependency existed there). Kg-only, same rationale as
correlation_science.kg_correlation_workbench: Ci (activity) and kg (mass)
are not comparable, so mixing them into one tank x element matrix would be
scientifically meaningless. Reuses kg_correlation_workbench for element
selection/parsing and the correlation/Jaccard/element-stats math, so
Structure and the Association Workbench always agree on "what counts as
this element's correlation" for the same inputs.

scipy/sklearn/networkx are imported lazily, inside the functions that use
them, not at module scope: this module is imported eagerly at app startup
(via qt_shell -> qt_correlations -> qt_correlations_structure), and these
three libraries alone cost several seconds of cold-import time that most
sessions never need paid up front just to reach the Overview page.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import polars as pl

from correlation_science import kg_correlation_workbench, partial_correlation_value, tank_total_inventory
from data_model import HanfordDataset
from matrix_science import square_matrix_lookup
from tank_science import tank_attributes_table

CATEGORY_FIELDS = ["TankFarm", "TankType", "TankSystem", "TankStatus", "Dominant waste phase"]
CLUSTER_METHODS = ["ward", "average", "complete", "single"]


def tank_categorical_labels(dataset: HanfordDataset, category: str) -> pd.Series:
    """Per-tank categorical label for the Structure color-by dropdown,
    indexed by WasteSiteId. TankFarm/TankType/TankSystem/TankStatus come
    straight from tank_attributes_table (already one row per tank). Raw
    WasteType is deliberately NOT offered here: it is row-level and
    extremely fine-grained (154/177 tanks in the real dataset carry more
    than one distinct value across their composition rows), so a per-tank
    reduction of it would be noisy and produce an unreadable legend.
    "Dominant waste phase" is offered instead: each tank's WastePhase with
    the largest total kg inventory. WastePhase only has 7 distinct values
    dataset-wide and is still a meaningful grouping ("this tank is
    majority sludge solid")."""
    if category == "Dominant waste phase":
        df = dataset.require_df().filter((pl.col("Units") == "kg") & pl.col("WastePhase").is_not_null())
        if df.is_empty():
            return pd.Series(dtype=object, name=category)
        totals = (
            df.group_by(["WasteSiteId", "WastePhase"]).agg(pl.col("Inventory").sum().alias("Total")).to_pandas()
        )
        idx = totals.groupby("WasteSiteId")["Total"].idxmax()
        out = totals.loc[idx].set_index("WasteSiteId")["WastePhase"]
        out.name = category
        return out

    attrs = tank_attributes_table(dataset)
    if attrs.empty or category not in attrs.columns:
        return pd.Series(dtype=object, name=category)
    out = attrs.set_index("WasteSiteId")[category]
    out.name = category
    return out


def tank_pca(metric_matrix: pd.DataFrame, elements: Sequence[str], n_components: int = 2) -> Dict[str, object]:
    """PCA on a StandardScaler-normalized tank x element metric matrix
    (log10_plus1 by default, via kg_correlation_workbench's metric_matrix).
    Constant-value elements (zero variance -- StandardScaler can't usefully
    scale them) are dropped before fitting and reported separately."""
    empty = {"scores": pd.DataFrame(), "loadings": pd.DataFrame(), "variance": pd.DataFrame(), "dropped_constant_elements": []}
    if metric_matrix is None or metric_matrix.empty:
        return empty
    vals = metric_matrix.set_index("WasteSiteId")
    vals = vals[[e for e in elements if e in vals.columns]]
    usable = [c for c in vals.columns if vals[c].nunique(dropna=True) > 1]
    dropped = [c for c in vals.columns if c not in usable]
    vals = vals[usable].fillna(0.0)
    n_comp = int(min(n_components, len(usable), max(len(vals) - 1, 1)))
    if len(usable) < 2 or len(vals) < 3 or n_comp < 2:
        return {**empty, "dropped_constant_elements": dropped}

    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(vals.to_numpy(dtype=float))
    pca = PCA(n_components=n_comp, random_state=0)
    scores = pca.fit_transform(scaled)
    pc_cols = [f"PC{i + 1}" for i in range(n_comp)]
    scores_df = pd.DataFrame(scores, columns=pc_cols, index=vals.index).reset_index().rename(columns={"index": "WasteSiteId"})
    loadings_df = pd.DataFrame(pca.components_.T, index=usable, columns=pc_cols).reset_index().rename(columns={"index": "Element"})
    variance_df = pd.DataFrame({
        "PC": pc_cols,
        "ExplainedVarianceRatio": pca.explained_variance_ratio_,
        "CumulativeVarianceRatio": np.cumsum(pca.explained_variance_ratio_),
    })
    return {"scores": scores_df, "loadings": loadings_df, "variance": variance_df, "dropped_constant_elements": dropped}


def hierarchical_clusters(
    metric_matrix: pd.DataFrame, elements: Sequence[str], method: str = "ward", n_clusters: int = 4,
) -> Dict[str, object]:
    """Agglomerative hierarchical clustering of tanks over the same
    standardized metric matrix PCA uses -- an alternate, cross-checkable
    view of tank structure (does a dendrogram cut at n_clusters agree with
    the PCA scatter's visual grouping?). Always uses Euclidean distance
    (required by "ward", and the standard choice for the other linkage
    methods here on already-standardized data)."""
    empty = {"linkage": np.empty((0, 4)), "labels": [], "assignments": pd.DataFrame()}
    if metric_matrix is None or metric_matrix.empty:
        return empty
    vals = metric_matrix.set_index("WasteSiteId")
    vals = vals[[e for e in elements if e in vals.columns]]
    usable = [c for c in vals.columns if vals[c].nunique(dropna=True) > 1]
    vals = vals[usable].fillna(0.0)
    if len(usable) < 2 or len(vals) < 3:
        return empty

    from scipy.cluster.hierarchy import fcluster, linkage
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(vals.to_numpy(dtype=float))
    z = linkage(scaled, method=method, metric="euclidean")
    labels = [str(x) for x in vals.index.tolist()]
    n_clusters_eff = int(max(1, min(n_clusters, len(labels))))
    cluster_ids = fcluster(z, t=n_clusters_eff, criterion="maxclust")
    assignments = pd.DataFrame({"WasteSiteId": labels, "Cluster": cluster_ids})
    return {"linkage": z, "labels": labels, "assignments": assignments}


def partial_correlation_matrix(
    dataset: HanfordDataset, metric_matrix: pd.DataFrame, elements: Sequence[str],
    unit: str = "kg", method: str = "pearson",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Element x element partial-correlation matrix, controlling for each
    tank's total same-unit inventory (log10(total+1)) -- directly shows how
    much of a raw pairwise correlation is just "both elements are more
    abundant in bigger tanks." Returns (partial_matrix, raw_matrix), both
    in the same Element-column square-matrix shape as
    correlation_science.full_correlation_matrix, so the two can be plotted
    side by side or diffed."""
    if metric_matrix is None or metric_matrix.empty:
        return pd.DataFrame(), pd.DataFrame()
    vals = metric_matrix.set_index("WasteSiteId")
    usable = [e for e in elements if e in vals.columns]
    if len(usable) < 2:
        return pd.DataFrame(), pd.DataFrame()
    z = tank_total_inventory(dataset, unit=unit, log_transform=True).reindex(vals.index)

    raw_square = pd.DataFrame(np.eye(len(usable)), index=usable, columns=usable, dtype=float)
    partial_square = pd.DataFrame(np.eye(len(usable)), index=usable, columns=usable, dtype=float)
    for a, b in combinations(usable, 2):
        pair = pd.DataFrame({"a": vals[a], "b": vals[b], "z": z}).replace([np.inf, -np.inf], np.nan).dropna()
        # Raw r only needs 3 points (matches correlation_science's own
        # floor elsewhere); partial r needs a 4th for one degree of freedom
        # after controlling for z, so it can go NaN while raw_r is still a
        # real number.
        r_ab = pair["a"].corr(pair["b"], method=method) if len(pair) >= 3 else np.nan
        if len(pair) < 4 or pd.isna(r_ab):
            r_partial = np.nan
        else:
            r_az = pair["a"].corr(pair["z"], method=method)
            r_bz = pair["b"].corr(pair["z"], method=method)
            r_partial = partial_correlation_value(r_ab, r_az, r_bz)
        raw_square.loc[a, b] = raw_square.loc[b, a] = r_ab
        partial_square.loc[a, b] = partial_square.loc[b, a] = r_partial

    raw_df = raw_square.reset_index().rename(columns={"index": "Element"})
    partial_df = partial_square.reset_index().rename(columns={"index": "Element"})
    return partial_df, raw_df


def element_network(
    workbench_results: Dict[str, pd.DataFrame], min_abs_r: float = 0.0, min_jaccard: float = 0.0,
    partial_corr_matrix: Optional[pd.DataFrame] = None, layout_seed: int = 0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Nodes (one per element, sized by total kg, positioned by a shared
    spring layout so the matplotlib plot and the Plotly HTML export always
    agree) and edges (element pairs passing BOTH the min |r| and min
    Jaccard thresholds). Every element gets a node even if it ends up with
    no edges at the current thresholds -- an isolated node is itself
    informative feedback about how strict the thresholds are. Pass
    partial_corr_matrix to use partial correlation (controlling for tank
    size) as the edge weight/color basis instead of the raw pairwise
    correlation."""
    element_stats = workbench_results.get("element_stats", pd.DataFrame())
    jaccard_matrix = workbench_results.get("jaccard_matrix", pd.DataFrame())
    corr_source = partial_corr_matrix if partial_corr_matrix is not None else workbench_results.get("corr_matrix", pd.DataFrame())
    if element_stats is None or element_stats.empty or corr_source is None or corr_source.empty:
        return pd.DataFrame(), pd.DataFrame()

    all_elements = element_stats["Element"].astype(str).tolist()
    corr_sq, corr_elems = square_matrix_lookup(corr_source)
    jacc_sq, _jacc_elems = square_matrix_lookup(jaccard_matrix) if jaccard_matrix is not None and not jaccard_matrix.empty else (pd.DataFrame(), [])

    edge_rows = []
    for a, b in combinations(corr_elems, 2):
        r = corr_sq.loc[a, b]
        if pd.isna(r) or abs(r) < float(min_abs_r):
            continue
        jacc = jacc_sq.loc[a, b] if (not jacc_sq.empty and a in jacc_sq.index and b in jacc_sq.columns) else np.nan
        if pd.notna(jacc) and jacc < float(min_jaccard):
            continue
        edge_rows.append({
            "Element_A": a, "Element_B": b, "Correlation_r": float(r), "AbsCorrelation": abs(float(r)),
            "Jaccard_presence": float(jacc) if pd.notna(jacc) else np.nan,
            "Sign": "positive" if r > 0 else ("negative" if r < 0 else "zero"),
        })
    edges = pd.DataFrame(edge_rows)
    if not edges.empty:
        edges = edges.sort_values("AbsCorrelation", ascending=False).reset_index(drop=True)

    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(all_elements)
    for row in edges.itertuples(index=False):
        graph.add_edge(row.Element_A, row.Element_B)
    positions = nx.spring_layout(graph, seed=layout_seed) if graph.number_of_nodes() else {}

    totals_map = {str(r.Element): float(r.Total_inventory_kg or 0.0) for r in element_stats.itertuples(index=False)}
    nodes = pd.DataFrame({
        "Element": all_elements,
        "Total_inventory_kg": [totals_map.get(e, 0.0) for e in all_elements],
    })
    nodes["LogTotalInventory"] = np.log10(nodes["Total_inventory_kg"].clip(lower=0) + 1.0)
    nodes["x"] = [positions.get(e, (0.0, 0.0))[0] for e in all_elements]
    nodes["y"] = [positions.get(e, (0.0, 0.0))[1] for e in all_elements]
    nodes["N_edges"] = [graph.degree[e] for e in all_elements]
    return nodes, edges


def structure_workbench(
    dataset: HanfordDataset, elements_text: str = "", selection_mode: str = "User list",
    top_n_elements: int = 20, value_mode: str = "log10_plus1", method: str = "pearson",
    min_inventory: float = 0.0, include_zeros: bool = True, skip_elements_text: str = "",
    n_clusters: int = 4, cluster_method: str = "ward",
    min_abs_r: float = 0.0, min_jaccard: float = 0.0, use_partial_for_network: bool = False,
) -> Dict[str, object]:
    """Build every table used by the Structure sub-tab. Reuses
    kg_correlation_workbench for element selection/parsing and the
    correlation/Jaccard/element-stats math (raises the same ValueErrors it
    does, e.g. "need at least two valid elements"), then layers on PCA,
    hierarchical clustering, a partial-correlation matrix, and the element-
    association network on top of that shared basis."""
    base = kg_correlation_workbench(
        dataset, elements_text=elements_text, selection_mode=selection_mode,
        top_n_elements=top_n_elements, value_mode=value_mode, method=method,
        min_inventory=min_inventory, include_zeros=include_zeros, skip_elements_text=skip_elements_text,
    )
    empty = pd.DataFrame()
    result: Dict[str, object] = dict(base)
    result.update({
        "pca_scores": empty, "pca_loadings": empty, "pca_variance": empty, "pca_dropped_elements": [],
        "cluster_assignments": empty, "cluster_linkage": np.empty((0, 4)), "cluster_labels": [],
        "partial_corr_matrix": empty, "raw_corr_matrix": base.get("corr_matrix", empty),
        "network_nodes": empty, "network_edges": empty, "tank_summary": empty,
    })
    raw_matrix = base.get("raw_matrix", empty)
    if raw_matrix is None or raw_matrix.empty:
        return result

    elements = [c for c in raw_matrix.columns if c != "WasteSiteId"]
    metric_matrix = base.get("metric_matrix", empty)

    pca_out = tank_pca(metric_matrix, elements, n_components=2)
    cluster_out = hierarchical_clusters(metric_matrix, elements, method=cluster_method, n_clusters=n_clusters)
    partial_df, raw_corr_df = partial_correlation_matrix(dataset, metric_matrix, elements, unit="kg", method=method)
    nodes_df, edges_df = element_network(
        base, min_abs_r=min_abs_r, min_jaccard=min_jaccard,
        partial_corr_matrix=partial_df if use_partial_for_network else None,
    )

    tank_summary = pca_out["scores"].copy()
    if not tank_summary.empty:
        if not cluster_out["assignments"].empty:
            tank_summary = tank_summary.merge(cluster_out["assignments"], on="WasteSiteId", how="left")
        for cat in CATEGORY_FIELDS:
            labels = tank_categorical_labels(dataset, cat)
            tank_summary[cat] = tank_summary["WasteSiteId"].map(labels)

    result.update({
        "pca_scores": pca_out["scores"], "pca_loadings": pca_out["loadings"], "pca_variance": pca_out["variance"],
        "pca_dropped_elements": pca_out["dropped_constant_elements"],
        "cluster_assignments": cluster_out["assignments"], "cluster_linkage": cluster_out["linkage"],
        "cluster_labels": cluster_out["labels"],
        "partial_corr_matrix": partial_df, "raw_corr_matrix": raw_corr_df,
        "network_nodes": nodes_df, "network_edges": edges_df, "tank_summary": tank_summary,
    })
    return result
