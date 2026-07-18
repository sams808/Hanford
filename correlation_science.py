"""
correlation_science.py — element-element correlation queries
(framework-agnostic). Ported from the old app's HanfordDataModel
(element_correlation_scan, element_totals_by_unit,
selected_element_correlations, full_correlation_matrix), restructured as
plain functions over a HanfordDataset. All build on
matrix_science.element_inventory_matrix, the shared tank x element pivot.
"""
from __future__ import annotations

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


def element_correlation_scan(
    dataset: HanfordDataset, target_element: str, unit: str = "kg",
    value_mode: str = "log10_plus1", method: str = "pearson", top_n_elements: int = 80,
    min_overlap: int = 5, min_inventory: float = 0.0, include_zeros: bool = True,
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
        r = pair["target"].corr(pair["partner"], method=method)
        if pd.isna(r):
            continue
        partner_total = totals.get(partner, 0.0)
        rows.append({
            "TargetElement": target, "PartnerElement": partner, "Units": unit,
            "Metric": value_mode, "Method": method, "Correlation_r": float(r),
            "AbsCorrelation": abs(float(r)), "N_tanks_used_for_corr": int(len(pair)),
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

    rows = []
    for a, b in combinations(clean, 2):
        if a not in vals.columns or b not in vals.columns:
            continue
        pair = pd.DataFrame({a: vals[a], b: vals[b]})
        overlap = (raw_vals[a].fillna(0) > 0) & (raw_vals[b].fillna(0) > 0)
        if not include_zeros:
            pair = pair.loc[overlap]
        pair = pair.replace([np.inf, -np.inf], np.nan).dropna()
        r = pair[a].corr(pair[b], method=method) if len(pair) >= 3 else np.nan
        rows.append({
            "Element_A": a, "Element_B": b, "Units": unit, "Metric": value_mode, "Method": method,
            "Correlation_r": r, "AbsCorrelation": abs(r) if pd.notna(r) else np.nan,
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
