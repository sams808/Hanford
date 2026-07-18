"""
matrix_science.py — tank x element matrix builders (framework-agnostic).
Ported from the old app's matrix_long_wide (Heatmaps workspace); also the
home for element_inventory_matrix, the shared pivot builder the
Correlations workspaces build on (added in a later milestone).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import polars as pl

from data_model import HanfordDataset
from elements import normalize_element_symbol


def log10_safe(values) -> np.ndarray:
    """log10 with non-positive values mapped to NaN instead of raising/-inf."""
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    mask = arr > 0
    out[mask] = np.log10(arr[mask])
    return out


def top_tanks_by_inventory(dataset: HanfordDataset, unit: str, max_tanks: int) -> List[str]:
    """The `max_tanks` largest tanks by total same-unit inventory -- used to
    subset a heatmap/matrix down to a readable size."""
    df = dataset.require_df().filter(pl.col("Units") == unit)
    return (
        df.group_by("WasteSiteId")
        .agg(pl.col("Inventory").sum().alias("Total"))
        .sort("Total", descending=True)
        .head(max_tanks)
        .get_column("WasteSiteId")
        .to_list()
    )


def matrix_long_wide(
    dataset: HanfordDataset, unit: str = "kg", top_n_elements: int = 35,
    min_inventory: float = 0.0, value_mode: str = "inventory",
    tank_subset: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Long-form (WasteSiteId, Element, Inventory_<unit> [+ transformed
    column per value_mode]) and wide-form (WasteSiteId x Element, ordered
    by total inventory) tank x element matrices, restricted to the top-N
    elements by total inventory in the given unit."""
    df = dataset.require_df().filter((pl.col("Units") == unit) & pl.col("Element").is_not_null())
    df = df.filter(pl.col("Inventory") > float(min_inventory))
    if tank_subset is not None and len(tank_subset) > 0:
        df = df.filter(pl.col("WasteSiteId").is_in(list(tank_subset)))
    if df.is_empty():
        return pd.DataFrame(), pd.DataFrame()

    top_elements = (
        df.group_by("Element")
        .agg(pl.col("Inventory").sum().alias("Total"))
        .sort("Total", descending=True)
        .head(top_n_elements)
        .get_column("Element")
        .to_list()
    )
    agg = (
        df.filter(pl.col("Element").is_in(top_elements))
        .group_by(["WasteSiteId", "Element"])
        .agg(pl.col("Inventory").sum().alias(f"Inventory_{unit}"))
        .sort(["WasteSiteId", "Element"])
    )
    long_pdf = agg.to_pandas()
    if value_mode == "log10_inventory":
        long_pdf[f"log10_Inventory_{unit}"] = log10_safe(long_pdf[f"Inventory_{unit}"].values)
    elif value_mode == "fraction":
        totals = long_pdf.groupby("WasteSiteId")[f"Inventory_{unit}"].transform("sum")
        long_pdf[f"Fraction_{unit}"] = long_pdf[f"Inventory_{unit}"] / totals.replace({0: np.nan})

    wide = long_pdf.pivot_table(index="WasteSiteId", columns="Element", values=f"Inventory_{unit}", aggfunc="sum", fill_value=0.0)
    ordered = [e for e in top_elements if e in wide.columns]
    wide = wide[ordered]
    wide = wide.reset_index()
    return long_pdf, wide


def element_inventory_matrix(
    dataset: HanfordDataset, unit: str = "kg", elements: Optional[Sequence[str]] = None,
    top_n: Optional[int] = None, min_inventory: float = 0.0, value_mode: str = "log10_inventory",
    include_all_tanks: bool = True,
) -> pd.DataFrame:
    """THE shared tank x element pivot builder -- every correlation feature
    (Quick Scan, the kg Association Workbench, Structure/PCA) is built on
    top of this. Five value_mode transforms:
        inventory          raw summed inventory in the selected unit
        log10_inventory    log10(inventory), zeros -> NaN (present-only)
        log10_plus1        log10(inventory + 1), zeros retained as 0
        fraction           fraction of each tank's total across the
                            *selected/displayed* elements only (not the
                            tank's true whole-inventory total -- contrast
                            with element_science.target_by_tank_unit)
        presence           1.0 if inventory > 0 else 0.0
    """
    df = dataset.require_df().filter((pl.col("Units") == unit) & pl.col("Element").is_not_null())
    df = df.filter(pl.col("Inventory") > float(min_inventory))
    if df.is_empty():
        return pd.DataFrame()

    if elements:
        clean_elements = []
        for e in elements:
            sym = normalize_element_symbol(str(e))
            if sym and sym not in clean_elements:
                clean_elements.append(sym)
        if clean_elements:
            df = df.filter(pl.col("Element").is_in(clean_elements))
    elif top_n and int(top_n) > 0:
        clean_elements = (
            df.group_by("Element")
            .agg(pl.col("Inventory").sum().alias("Total"))
            .sort("Total", descending=True)
            .head(int(top_n))
            .get_column("Element")
            .to_list()
        )
        df = df.filter(pl.col("Element").is_in(clean_elements))
    else:
        clean_elements = df.get_column("Element").drop_nulls().unique().sort().to_list()

    grouped = (
        df.group_by(["WasteSiteId", "Element"])
        .agg(pl.col("Inventory").sum().alias("Inventory"))
        .to_pandas()
    )
    if grouped.empty:
        return pd.DataFrame()
    wide = grouped.pivot_table(index="WasteSiteId", columns="Element", values="Inventory", aggfunc="sum", fill_value=0.0)

    ordered = [e for e in clean_elements if e in wide.columns] if clean_elements else list(wide.columns)
    rest = [c for c in wide.columns if c not in ordered]
    wide = wide[ordered + rest]

    if include_all_tanks:
        all_tanks = dataset.available_tanks()
        wide = wide.reindex(all_tanks, fill_value=0.0)

    raw = wide.copy()
    mode = (value_mode or "inventory").lower()
    if mode == "inventory":
        val = raw
    elif mode == "log10_inventory":
        val = raw.replace(0.0, np.nan).apply(lambda col: np.log10(col))
    elif mode == "log10_plus1":
        val = np.log10(raw + 1.0)
    elif mode == "fraction":
        denom = raw.sum(axis=1).replace(0.0, np.nan)
        val = raw.div(denom, axis=0)
    elif mode == "presence":
        val = (raw > 0).astype(float)
    else:
        raise ValueError(f"Unknown value_mode: {value_mode}")

    val = val.reset_index().rename(columns={"index": "WasteSiteId"})
    return val
