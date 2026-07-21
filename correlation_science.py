"""
correlation_science.py — element-element correlation queries
(framework-agnostic). Ported from the old app's HanfordDataModel
(element_correlation_scan, element_totals_by_unit,
selected_element_correlations, full_correlation_matrix), restructured as
plain functions over a HanfordDataset. All build on
matrix_science.element_inventory_matrix, the shared tank x element pivot.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import polars as pl

from data_model import HanfordDataset
from elements import normalize_element_symbol
from matrix_science import element_inventory_matrix


def element_totals_by_unit(dataset: HanfordDataset, unit: str = "kg") -> Dict[str, float]:
    df = dataset.require_df().filter((pl.col("Units") == unit) & pl.col("Element").is_not_null())
    if df.is_empty():
        return {}
    pdf = df.group_by("Element").agg(pl.col("Inventory").sum().alias("Total")).to_pandas()
    return {str(r.Element): float(r.Total) for r in pdf.itertuples(index=False)}


def tank_total_inventory(dataset: HanfordDataset, unit: str = "kg", log_transform: bool = True) -> pd.Series:
    """Per-tank total inventory in `unit`, summed across ALL elements (not
    just a selected subset) -- the "how big is this tank overall" variable
    used to control for the "everything correlates because both elements
    just scale with tank size" effect. log_transform applies log10(total+1),
    matching the log10_plus1 convention used elsewhere so a few huge tanks
    don't dominate the control variable's own scale."""
    df = dataset.require_df().filter((pl.col("Units") == unit) & pl.col("Element").is_not_null())
    all_tanks = dataset.available_tanks()
    if df.is_empty():
        totals = pd.Series(0.0, index=all_tanks)
    else:
        totals = (
            df.group_by("WasteSiteId").agg(pl.col("Inventory").sum().alias("Total"))
            .to_pandas().set_index("WasteSiteId")["Total"]
        )
        totals = totals.reindex(all_tanks, fill_value=0.0)
    if log_transform:
        totals = np.log10(totals.astype(float) + 1.0)
    totals.name = "TotalInventory"
    return totals


def partial_correlation_value(r_xy: float, r_xz: float, r_yz: float) -> float:
    """First-order partial correlation of X,Y controlling for Z, from the
    three pairwise correlations (closed form; exact for Pearson, a
    standard and widely used approximation for Spearman/Kendall computed
    the same way on their own pairwise coefficients):
        r_XY.Z = (r_XY - r_XZ*r_YZ) / sqrt((1 - r_XZ^2)(1 - r_YZ^2))
    """
    if pd.isna(r_xy) or pd.isna(r_xz) or pd.isna(r_yz):
        return float("nan")
    denom = math.sqrt(max((1.0 - r_xz ** 2) * (1.0 - r_yz ** 2), 0.0))
    if denom == 0.0:
        return float("nan")
    return float((r_xy - r_xz * r_yz) / denom)


def _controlled_correlation(
    pair: pd.DataFrame, col_a: str, col_b: str, z_full: Optional[pd.Series], method: str,
) -> Tuple[float, float]:
    """(raw_r, active_r) for a two-column `pair` (already overlap-masked
    and NaN-dropped). active_r is the partial correlation controlling for
    z_full when given and enough aligned, finite rows remain (>=4, the
    minimum for one degree of freedom after controlling a third variable);
    otherwise active_r falls back to raw_r unchanged."""
    raw_r = pair[col_a].corr(pair[col_b], method=method) if len(pair) >= 3 else float("nan")
    if z_full is None or pd.isna(raw_r):
        return raw_r, raw_r
    combined = pair.assign(_z=z_full.reindex(pair.index)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(combined) < 4:
        return raw_r, raw_r
    r_az = combined[col_a].corr(combined["_z"], method=method)
    r_bz = combined[col_b].corr(combined["_z"], method=method)
    partial = partial_correlation_value(raw_r, r_az, r_bz)
    if pd.isna(partial):
        return raw_r, raw_r
    return raw_r, partial


def element_correlation_scan(
    dataset: HanfordDataset, target_element: str, unit: str = "kg",
    value_mode: str = "log10_plus1", method: str = "pearson", top_n_elements: int = 80,
    min_overlap: int = 5, min_inventory: float = 0.0, include_zeros: bool = True,
    control_for_total_inventory: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Rank every other element by |correlation| with the target, across
    the top-N elements by inventory (the target is always kept even if it
    isn't itself one of the top-N)."""
    target = normalize_element_symbol(target_element)
    if not target:
        raise ValueError(f"{target_element!r} is not a valid element symbol.")
    df_for_elements = dataset.require_df().filter(
        (pl.col("Units") == unit) & pl.col("Element").is_not_null() & (pl.col("Inventory") > float(min_inventory))
    )
    top_elements: List[str] = []
    if not df_for_elements.is_empty():
        top_elements = (
            df_for_elements.group_by("Element")
            .agg(pl.col("Inventory").sum().alias("Total"))
            .sort("Total", descending=True)
            .head(max(int(top_n_elements), 2))
            .get_column("Element")
            .to_list()
        )
    selected_elements = [target] + [e for e in top_elements if e != target]
    matrix = element_inventory_matrix(
        dataset, unit=unit, elements=selected_elements, min_inventory=min_inventory,
        value_mode=value_mode, include_all_tanks=True,
    )
    if matrix.empty or target not in matrix.columns:
        return pd.DataFrame(), matrix

    values = matrix.set_index("WasteSiteId")
    if not include_zeros and value_mode in ("inventory", "log10_plus1", "presence"):
        # Present-only correlations: use the raw inventory matrix to mask
        # zero pairs, regardless of which transform is displayed.
        raw = element_inventory_matrix(
            dataset, unit=unit, top_n=max(int(top_n_elements), 2), min_inventory=min_inventory, value_mode="inventory",
        )
        raw_values = raw.set_index("WasteSiteId") if not raw.empty else values.copy()
    else:
        raw_values = values.copy()

    rows = []
    totals = element_totals_by_unit(dataset, unit)
    target_total = totals.get(target, 0.0)
    z_full = tank_total_inventory(dataset, unit=unit, log_transform=True) if control_for_total_inventory else None
    for partner in values.columns:
        if partner == target:
            continue
        pair = pd.DataFrame({"target": values[target], "partner": values[partner]})
        raw_pair = pd.DataFrame({
            "target": raw_values.get(target, values[target]),
            "partner": raw_values.get(partner, values[partner]),
        })
        overlap_mask = (raw_pair["target"].fillna(0) > 0) & (raw_pair["partner"].fillna(0) > 0)
        n_overlap = int(overlap_mask.sum())
        n_target_present = int((raw_pair["target"].fillna(0) > 0).sum())
        n_partner_present = int((raw_pair["partner"].fillna(0) > 0).sum())
        if n_overlap < int(min_overlap):
            continue
        if not include_zeros:
            pair = pair.loc[overlap_mask]
        pair = pair.replace([np.inf, -np.inf], np.nan).dropna()
        if len(pair) < max(int(min_overlap), 3):
            continue
        raw_r, r = _controlled_correlation(pair, "target", "partner", z_full, method)
        if pd.isna(r):
            continue
        partner_total = totals.get(partner, 0.0)
        rows.append({
            "TargetElement": target, "PartnerElement": partner, "Units": unit,
            "Metric": value_mode, "Method": method, "Correlation_r": float(r),
            "AbsCorrelation": abs(float(r)), "Raw_Correlation_r": float(raw_r) if pd.notna(raw_r) else np.nan,
            "ControlledForTotalInventory": bool(control_for_total_inventory),
            "N_tanks_used_for_corr": int(len(pair)),
            "N_overlap_nonzero_tanks": n_overlap, "N_target_present_tanks": n_target_present,
            "N_partner_present_tanks": n_partner_present, "Target_total_inventory": float(target_total),
            "Partner_total_inventory": float(partner_total),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out, matrix
    out = out.sort_values("AbsCorrelation", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank_abs", np.arange(1, len(out) + 1))
    out["Rank_positive"] = out["Correlation_r"].rank(ascending=False, method="dense").astype(int)
    out["Rank_negative"] = out["Correlation_r"].rank(ascending=True, method="dense").astype(int)
    return out, matrix


def parse_element_list(text: str) -> List[str]:
    """Comma/semicolon/whitespace-separated element list -> normalized,
    deduplicated symbols. Unrecognized tokens are silently dropped."""
    import re
    parts = re.split(r"[,;\s]+", text.strip())
    out: List[str] = []
    for p in parts:
        sym = normalize_element_symbol(p)
        if sym and sym not in out:
            out.append(sym)
    return out


def selected_element_correlations(
    dataset: HanfordDataset, elements: Sequence[str], unit: str = "kg",
    value_mode: str = "log10_plus1", method: str = "pearson",
    min_inventory: float = 0.0, include_zeros: bool = True,
    control_for_total_inventory: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """All pairwise correlations among 2-3 selected elements, plus a joint
    co-occurrence summary row."""
    clean: List[str] = []
    for item in elements:
        sym = normalize_element_symbol(str(item).strip())
        if sym and sym not in clean:
            clean.append(sym)
    if len(clean) < 2:
        raise ValueError("Enter at least two valid element symbols, e.g. Cs, Sr or Se, Tc, I.")
    matrix = element_inventory_matrix(
        dataset, unit=unit, elements=clean, min_inventory=min_inventory,
        value_mode=value_mode, include_all_tanks=True,
    )
    if matrix.empty:
        return pd.DataFrame(), pd.DataFrame(), matrix
    vals = matrix.set_index("WasteSiteId")
    if not include_zeros:
        raw = element_inventory_matrix(dataset, unit=unit, elements=clean, min_inventory=min_inventory, value_mode="inventory")
        raw_vals = raw.set_index("WasteSiteId") if not raw.empty else vals.copy()
    else:
        raw_vals = vals.copy()

    z_full = tank_total_inventory(dataset, unit=unit, log_transform=True) if control_for_total_inventory else None
    rows = []
    for a, b in combinations(clean, 2):
        if a not in vals.columns or b not in vals.columns:
            continue
        pair = pd.DataFrame({a: vals[a], b: vals[b]})
        overlap = (raw_vals[a].fillna(0) > 0) & (raw_vals[b].fillna(0) > 0)
        if not include_zeros:
            pair = pair.loc[overlap]
        pair = pair.replace([np.inf, -np.inf], np.nan).dropna()
        raw_r, r = _controlled_correlation(pair, a, b, z_full, method)
        rows.append({
            "Element_A": a, "Element_B": b, "Units": unit, "Metric": value_mode, "Method": method,
            "Correlation_r": r, "AbsCorrelation": abs(r) if pd.notna(r) else np.nan,
            "Raw_Correlation_r": raw_r, "ControlledForTotalInventory": bool(control_for_total_inventory),
            "N_tanks_used_for_corr": int(len(pair)), "N_overlap_nonzero_tanks": int(overlap.sum()),
        })
    pair_table = pd.DataFrame(rows).sort_values("AbsCorrelation", ascending=False) if rows else pd.DataFrame()

    presence = pd.DataFrame({e: (raw_vals[e].fillna(0) > 0) for e in clean if e in raw_vals.columns})
    joint = pd.DataFrame()
    if not presence.empty:
        all_mask = presence.all(axis=1)
        any_mask = presence.any(axis=1)
        joint = pd.DataFrame([{
            "Elements": ";".join(clean), "Units": unit, "Metric": value_mode, "N_elements": len(clean),
            "N_tanks_all_present": int(all_mask.sum()), "N_tanks_any_present": int(any_mask.sum()),
            "Fraction_all_present_pct": 100.0 * float(all_mask.sum()) / max(len(presence), 1),
            "Mean_pairwise_correlation": pair_table["Correlation_r"].mean() if not pair_table.empty else np.nan,
            "Min_pairwise_correlation": pair_table["Correlation_r"].min() if not pair_table.empty else np.nan,
            "Max_pairwise_correlation": pair_table["Correlation_r"].max() if not pair_table.empty else np.nan,
        }])
    return pair_table, joint, matrix


def kg_correlation_workbench(
    dataset: HanfordDataset, elements_text: str = "", selection_mode: str = "User list",
    top_n_elements: int = 20, value_mode: str = "log10_plus1", method: str = "pearson",
    min_inventory: float = 0.0, include_zeros: bool = True, skip_elements_text: str = "",
) -> Dict[str, pd.DataFrame]:
    """Build every table used by the kg-only Association Workbench.

    Deliberately kg-only: this is chemical mass association screening for
    vitrification/blending, not a mix of chemical mass and radiological
    activity. One row = one tank; one column = one parsed element. The raw
    matrix is inventory_kg; the metric matrix is the transformed version
    used for correlations and plots. skip_elements_text is applied BEFORE
    "Top kg elements" selection, so "top 25" means top 25 after removing
    the skipped elements.
    """
    unit = "kg"
    selection_mode_norm = (selection_mode or "User list").lower()
    skip_elements = parse_element_list(skip_elements_text)
    skip_set = set(skip_elements)
    df = dataset.require_df().filter(
        (pl.col("Units") == unit) & pl.col("Element").is_not_null() & (pl.col("Inventory") > float(min_inventory))
    )
    if skip_set:
        df = df.filter(~pl.col("Element").is_in(list(skip_set)))
    if df.is_empty():
        empty = pd.DataFrame()
        return {
            "element_stats": empty, "pair_stats": empty, "raw_matrix": empty, "metric_matrix": empty,
            "corr_matrix": empty, "jaccard_matrix": empty, "tank_similarity": empty,
            "tank_element_long": empty, "presence_matrix": empty,
            "excluded_elements": pd.DataFrame({"ExcludedElement": skip_elements, "Reason": "User skip list"}),
        }

    if "top" in selection_mode_norm:
        elements = (
            df.group_by("Element").agg(pl.col("Inventory").sum().alias("Total_inventory_kg"))
            .sort("Total_inventory_kg", descending=True).head(max(int(top_n_elements), 2))
            .get_column("Element").to_list()
        )
    else:
        elements = parse_element_list(elements_text)
        if not elements:
            # Forgiving default: an empty list falls back to top kg elements
            # rather than failing outright.
            elements = (
                df.group_by("Element").agg(pl.col("Inventory").sum().alias("Total_inventory_kg"))
                .sort("Total_inventory_kg", descending=True).head(max(int(top_n_elements), 2))
                .get_column("Element").to_list()
            )
    elements = [e for e in elements if e and e not in skip_set]
    if len(elements) < 2:
        skipped_msg = f" Skipped elements: {', '.join(skip_elements)}." if skip_elements else ""
        raise ValueError("Need at least two valid elements after applying the skip list, e.g. Cs, Sr, Tc, I, Se." + skipped_msg)

    raw_matrix = element_inventory_matrix(
        dataset, unit=unit, elements=elements, min_inventory=float(min_inventory),
        value_mode="inventory", include_all_tanks=True,
    )
    if raw_matrix.empty:
        raise ValueError("No kg inventory rows matched the selected elements.")
    for e in elements:
        if e not in raw_matrix.columns:
            raw_matrix[e] = 0.0
    raw_matrix = raw_matrix[["WasteSiteId"] + elements]
    raw_vals = raw_matrix.set_index("WasteSiteId").apply(pd.to_numeric, errors="coerce").fillna(0.0)

    mode = (value_mode or "log10_plus1").lower()
    if mode == "inventory":
        metric_vals = raw_vals.copy()
        metric_label = "Inventory_kg"
    elif mode == "log10_inventory":
        metric_vals = raw_vals.replace(0.0, np.nan).apply(lambda col: np.log10(col))
        metric_label = "log10_inventory_kg_present_only"
    elif mode == "log10_plus1":
        metric_vals = np.log10(raw_vals + 1.0)
        metric_label = "log10_inventory_kg_plus1"
    elif mode == "fraction":
        denom = raw_vals.sum(axis=1).replace(0.0, np.nan)
        metric_vals = raw_vals.div(denom, axis=0)
        metric_label = "Fraction_of_selected_kg_inventory"
    elif mode == "presence":
        metric_vals = (raw_vals > 0).astype(float)
        metric_label = "Presence_0_or_1"
    else:
        raise ValueError(f"Unknown kg seaborn metric: {value_mode}")
    metric_matrix = metric_vals.reset_index()

    presence_bool = raw_vals > 0
    n_tanks_total = len(raw_vals)
    totals = raw_vals.sum(axis=0)
    element_rows = []
    for e in elements:
        present = presence_bool[e]
        values_present = raw_vals.loc[present, e]
        element_rows.append({
            "Element": e, "Units": "kg", "Total_inventory_kg": float(totals.get(e, 0.0)),
            "N_tanks_present": int(present.sum()), "N_tanks_total": int(n_tanks_total),
            "PresenceFraction_pct": 100.0 * float(present.sum()) / max(n_tanks_total, 1),
            "Mean_kg_present_tanks_only": float(values_present.mean()) if len(values_present) else np.nan,
            "Median_kg_present_tanks_only": float(values_present.median()) if len(values_present) else np.nan,
            "Std_kg_present_tanks_only": float(values_present.std(ddof=1)) if len(values_present) > 1 else np.nan,
            "Max_kg_in_one_tank": float(values_present.max()) if len(values_present) else np.nan,
        })
    element_stats = pd.DataFrame(element_rows).sort_values("Total_inventory_kg", ascending=False).reset_index(drop=True)

    # Pairwise correlations and co-occurrence statistics. When zeros are
    # included every pair shares the same row set, so all N*(N-1)/2
    # correlations come from ONE vectorized whole-matrix .corr() call
    # (pandas already computes it pairwise-complete per column pair,
    # matching the old per-pair dropna() exactly, min_periods=3 to match
    # its explicit len(pair) >= 3 floor) instead of a per-pair DataFrame
    # construction + replace + dropna + .corr(). Profiling on the real
    # dataset showed that per-pair pandas object-construction overhead --
    # not the correlation math itself -- dominated wall time: 90 elements
    # (4005 pairs) went from ~5.6s to well under a second. include_zeros=
    # False still needs a genuinely different row mask per pair, so that
    # path keeps the original per-pair computation.
    n_elements = len(elements)
    metric_clean = metric_vals[elements].replace([np.inf, -np.inf], np.nan)
    if include_zeros:
        bulk_corr = metric_clean.corr(method=method, min_periods=3)
        finite = metric_clean.notna()
    else:
        bulk_corr = None
        finite = None

    pair_rows = []
    corr_np = np.eye(n_elements, dtype=float)
    jaccard_np = np.eye(n_elements, dtype=float)
    for idx_a, idx_b in combinations(range(n_elements), 2):
        a, b = elements[idx_a], elements[idx_b]
        raw_a, raw_b = raw_vals[a], raw_vals[b]
        pres_a, pres_b = presence_bool[a], presence_bool[b]
        both = pres_a & pres_b
        either = pres_a | pres_b
        if include_zeros:
            r = bulk_corr.loc[a, b]
            n_used = int((finite[a] & finite[b]).sum())
        else:
            pair = metric_clean.loc[both, [a, b]].dropna()
            r = pair[a].corr(pair[b], method=method) if len(pair) >= 3 else np.nan
            n_used = len(pair)
        n_a, n_b = int(pres_a.sum()), int(pres_b.sum())
        n_both, n_either = int(both.sum()), int(either.sum())
        jaccard = float(n_both / n_either) if n_either else np.nan
        overlap_a_pct = 100.0 * n_both / max(n_a, 1)
        overlap_b_pct = 100.0 * n_both / max(n_b, 1)
        min_sum = np.minimum(raw_a, raw_b).sum()
        # Ranking proxy only: rewards positive correlation, repeated
        # co-occurrence, and overlap. Negative r is kept in the table but
        # never scores as a preferred association.
        score = (max(float(r), 0.0) if pd.notna(r) else 0.0) * math.log1p(n_both) * (jaccard if pd.notna(jaccard) else 0.0)
        corr_np[idx_a, idx_b] = corr_np[idx_b, idx_a] = r
        jaccard_np[idx_a, idx_b] = jaccard_np[idx_b, idx_a] = jaccard
        pair_rows.append({
            "Element_A": a, "Element_B": b, "Units": "kg", "Metric": mode, "Metric_label": metric_label,
            "Method": method, "Include_zeros": bool(include_zeros),
            "Correlation_r": float(r) if pd.notna(r) else np.nan,
            "AbsCorrelation": abs(float(r)) if pd.notna(r) else np.nan,
            "N_tanks_used_for_corr": int(n_used), "N_tanks_total": int(n_tanks_total),
            "N_A_present": n_a, "N_B_present": n_b, "N_both_present": n_both, "N_either_present": n_either,
            "Jaccard_presence": jaccard, "OverlapFraction_of_A_pct": overlap_a_pct,
            "OverlapFraction_of_B_pct": overlap_b_pct, "Total_A_kg": float(totals.get(a, 0.0)),
            "Total_B_kg": float(totals.get(b, 0.0)), "Shared_min_inventory_proxy_kg": float(min_sum),
            "PreferredAssociationScore_proxy": float(score),
        })
    corr_square = pd.DataFrame(corr_np, index=elements, columns=elements)
    jaccard_square = pd.DataFrame(jaccard_np, index=elements, columns=elements)
    pair_stats = pd.DataFrame(pair_rows)
    if not pair_stats.empty:
        pair_stats = pair_stats.sort_values(
            ["PreferredAssociationScore_proxy", "AbsCorrelation", "N_both_present"], ascending=[False, False, False],
        ).reset_index(drop=True)
        pair_stats.insert(0, "Rank_preferred_association", np.arange(1, len(pair_stats) + 1))

    corr_df = corr_square.reset_index().rename(columns={"index": "Element"})
    jaccard_df = jaccard_square.reset_index().rename(columns={"index": "Element"})
    presence_matrix = presence_bool.astype(int).reset_index()

    tank_similarity = pd.DataFrame()
    valid_metric = metric_vals.replace([np.inf, -np.inf], np.nan)
    # Drop constant elements first -- correlation between tanks is undefined otherwise.
    usable_cols = [c for c in valid_metric.columns if valid_metric[c].nunique(dropna=True) > 1]
    if len(usable_cols) >= 2 and len(valid_metric) >= 2:
        tank_corr = valid_metric[usable_cols].T.corr(method=method)
        tank_similarity = tank_corr.reset_index().rename(columns={"index": "WasteSiteId"})

    long_rows = []
    for tank, row in raw_vals.iterrows():
        selected_total = float(row.sum())
        for e in elements:
            inv = float(row[e])
            if inv > 0:
                long_rows.append({
                    "WasteSiteId": tank, "Element": e, "Inventory_kg": inv,
                    "Fraction_of_selected_kg_inventory": inv / selected_total if selected_total > 0 else np.nan,
                })
    tank_element_long = (
        pd.DataFrame(long_rows).sort_values(["WasteSiteId", "Inventory_kg"], ascending=[True, False])
        if long_rows else pd.DataFrame()
    )

    return {
        "element_stats": element_stats, "pair_stats": pair_stats, "raw_matrix": raw_matrix,
        "metric_matrix": metric_matrix, "corr_matrix": corr_df, "jaccard_matrix": jaccard_df,
        "tank_similarity": tank_similarity, "tank_element_long": tank_element_long,
        "presence_matrix": presence_matrix,
        "excluded_elements": pd.DataFrame({"ExcludedElement": skip_elements, "Reason": "User skip list"}),
    }


def full_correlation_matrix(
    dataset: HanfordDataset, unit: str = "kg", top_n_elements: int = 35,
    value_mode: str = "log10_plus1", method: str = "pearson", min_inventory: float = 0.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    matrix = element_inventory_matrix(dataset, unit=unit, top_n=top_n_elements, min_inventory=min_inventory, value_mode=value_mode)
    if matrix.empty:
        return pd.DataFrame(), matrix
    corr = matrix.drop(columns=["WasteSiteId"]).corr(method=method)
    corr = corr.reset_index().rename(columns={"index": "Element"})
    return corr, matrix
