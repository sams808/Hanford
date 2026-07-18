"""
tank_science.py — tank-attribute audits and tank-centric composition
queries (framework-agnostic). Ported from the old app's HanfordDataModel
methods (tank_attributes_table, tank_attribute_audit,
tank_attribute_numeric_summary, tank_profile, raw_rows_for_tank),
restructured as plain functions over a HanfordDataset.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
import pandas as pd
import polars as pl

from data_model import HanfordDataset, list_join_expr

_ATTRIBUTE_TABLE_COLUMNS = [
    "WasteSiteId", "TankFarm", "TankSystem", "TankType", "Capacity", "CapacityUnits",
    "Diameter", "DiameterUnits", "MaxOperatingDepth", "MaxOperatingDepthUnits",
    "Ventilation", "InServiceDate", "InterimStabilization", "IntrusionPrevention",
    "OperationCapacityKGal", "TankStatus", "TankIntegrity", "DIL_Gal",
    "IsDST", "IsSST", "IsLeakerOrAssumedLeaker", "HasWIStatus", "HasTankAttributes",
]
_NUMERIC_SUMMARY_COLUMNS = ["Capacity", "Diameter", "MaxOperatingDepth", "OperationCapacityKGal", "DIL_Gal"]


def tank_attributes_table(dataset: HanfordDataset) -> pd.DataFrame:
    """One row per tank (collapsed from the composition rows that carry
    the same broadcast attribute values), covering every tank present in
    the composition data -- including tanks absent from Tank_attributes.csv
    (their attribute columns are simply null, HasTankAttributes=False)."""
    df = dataset.require_df()
    cols = [c for c in _ATTRIBUTE_TABLE_COLUMNS if c in df.columns]
    if not cols:
        return pd.DataFrame()
    return df.select(cols).unique(subset=["WasteSiteId"], keep="first").sort("WasteSiteId").to_pandas()


def tank_attribute_audit(dataset: HanfordDataset, category_col: str = "TankType") -> pd.DataFrame:
    attrs = tank_attributes_table(dataset)
    if attrs.empty or category_col not in attrs.columns:
        return pd.DataFrame()
    pdf = attrs.copy()
    pdf[category_col] = pdf[category_col].fillna("Unknown").astype(str)
    for col in ["Capacity", "OperationCapacityKGal", "DIL_Gal"]:
        if col in pdf.columns:
            pdf[col] = pd.to_numeric(pdf[col], errors="coerce")
    agg = pdf.groupby(category_col, dropna=False).agg(
        N_tanks=("WasteSiteId", "nunique"),
        Total_capacity_kgal=("Capacity", "sum") if "Capacity" in pdf else ("WasteSiteId", "size"),
        Mean_capacity_kgal=("Capacity", "mean") if "Capacity" in pdf else ("WasteSiteId", "size"),
        Total_operation_capacity_kgal=("OperationCapacityKGal", "sum") if "OperationCapacityKGal" in pdf else ("WasteSiteId", "size"),
        Total_DIL_gal=("DIL_Gal", "sum") if "DIL_Gal" in pdf else ("WasteSiteId", "size"),
        N_leaker_or_assumed=("IsLeakerOrAssumedLeaker", "sum") if "IsLeakerOrAssumedLeaker" in pdf else ("WasteSiteId", "size"),
    ).reset_index()
    return agg.sort_values(["N_tanks", category_col], ascending=[False, True])


def tank_attribute_numeric_summary(dataset: HanfordDataset) -> pd.DataFrame:
    attrs = tank_attributes_table(dataset)
    if attrs.empty:
        return pd.DataFrame()
    rows = []
    for col in _NUMERIC_SUMMARY_COLUMNS:
        if col not in attrs.columns:
            continue
        s = pd.to_numeric(attrs[col], errors="coerce")
        rows.append({
            "column": col,
            "n_nonnull": int(s.notna().sum()),
            "min": float(s.min()) if s.notna().any() else np.nan,
            "mean": float(s.mean()) if s.notna().any() else np.nan,
            "median": float(s.median()) if s.notna().any() else np.nan,
            "max": float(s.max()) if s.notna().any() else np.nan,
            "sum": float(s.sum()) if s.notna().any() else np.nan,
        })
    return pd.DataFrame(rows)


def tank_profile(
    dataset: HanfordDataset, tank_ids: Sequence[str],
    unit_filter: Optional[str] = None, top_n: int = 40,
) -> pd.DataFrame:
    """Per (tank, element): summed inventory and its fraction of that
    tank's own same-unit total, for the selected tanks."""
    df = dataset.require_df().filter(pl.col("WasteSiteId").is_in(list(tank_ids)))
    df = dataset.filter_by_units(df, unit_filter)
    df = df.filter((pl.col("Inventory") > 0) & pl.col("Element").is_not_null())
    if df.is_empty():
        return pd.DataFrame()
    out = (
        df.group_by(["Units", "WasteSiteId", "TankFarm", "Element"])
        .agg([
            pl.col("Inventory").sum().alias("Inventory_sum"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
            pl.len().alias("N_rows"),
            list_join_expr("Analyte", "Analytes"),
            list_join_expr("WastePhase", "WastePhase_list"),
            list_join_expr("WasteType", "WasteType_list"),
        ])
    )
    totals = out.group_by(["Units", "WasteSiteId"]).agg(pl.col("Inventory_sum").sum().alias("Tank_total_same_unit"))
    out = out.join(totals, on=["Units", "WasteSiteId"], how="left").with_columns(
        (pl.col("Inventory_sum") / pl.col("Tank_total_same_unit")).alias("Fraction_of_tank_unit_inventory")
    )
    return (
        out.sort(["Units", "WasteSiteId", "Inventory_sum"], descending=[False, False, True])
        .head(top_n * max(len(tank_ids), 1))
        .to_pandas()
    )


def raw_rows_for_tank(
    dataset: HanfordDataset, tank_id: str, unit_filter: Optional[str] = None, limit: int = 5000,
) -> pd.DataFrame:
    df = dataset.require_df().filter(pl.col("WasteSiteId") == tank_id)
    df = dataset.filter_by_units(df, unit_filter)
    return df.sort(["Units", "Inventory"], descending=[False, True]).head(limit).to_pandas()


def available_farms_with_all(dataset: HanfordDataset) -> List[str]:
    """Farm choices for a selection dropdown, "All" first."""
    return ["All"] + dataset.available_farms()


def tanks_in_farm(dataset: HanfordDataset, farm: Optional[str]) -> List[str]:
    if not farm or farm == "All":
        return dataset.available_tanks()
    df = dataset.require_df().filter(pl.col("TankFarm") == farm)
    return sorted({str(t) for t in df.get_column("WasteSiteId").drop_nulls().unique().to_list()})
