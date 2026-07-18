"""
element_science.py — element/analyte search queries (framework-agnostic).

Ported from the old app's HanfordDataModel search methods (target_rows,
target_by_tank_unit, target_by_phase, target_by_type, co_elements,
co_analytes, composition_stats), restructured as plain functions over a
HanfordDataset instead of methods on a god-class.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

import pandas as pd
import polars as pl

from data_model import HanfordDataset, list_join_expr


def target_rows(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None, min_inventory: float = 0.0,
) -> Tuple[pl.DataFrame, str, Optional[str]]:
    df = dataset.require_df()
    expr, resolved_mode, symbol = dataset.target_expr(query, mode)
    out = df.filter(expr)
    out = dataset.filter_by_units(out, unit_filter)
    if min_inventory is not None:
        out = out.filter(pl.col("Inventory") > float(min_inventory))
    return out, resolved_mode, symbol


def target_tanks(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None, min_inventory: float = 0.0,
) -> List[str]:
    target, _, _ = target_rows(dataset, query, mode, unit_filter, min_inventory)
    return target.get_column("WasteSiteId").drop_nulls().unique().sort().to_list()


def target_by_tank_unit(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None, min_inventory: float = 0.0,
) -> pd.DataFrame:
    """Per (tank, unit): summed target inventory, plus its fraction of that
    tank's TRUE full-unit total (Context_TotalInventory_same_unit, computed
    from the whole unrestricted dataset -- not just the displayed rows)."""
    target, resolved, symbol = target_rows(dataset, query, mode, unit_filter, min_inventory)
    if target.is_empty():
        return pd.DataFrame()
    context_totals = (
        dataset.require_df()
        .group_by(["WasteSiteId", "Units"])
        .agg([
            pl.col("Inventory").sum().alias("Context_TotalInventory_same_unit"),
            pl.len().alias("Context_N_rows_same_unit"),
            pl.col("Analyte").n_unique().alias("Context_N_analytes_same_unit"),
        ])
    )
    grouped = (
        target.group_by(["WasteSiteId", "TankFarm", "Units"])
        .agg([
            pl.col("Inventory").sum().alias("Target_Inventory_sum"),
            pl.col("Inventory").mean().alias("Target_Inventory_mean_row"),
            pl.col("Inventory").max().alias("Target_Inventory_max_row"),
            pl.len().alias("N_target_rows"),
            pl.col("Analyte").n_unique().alias("N_target_analytes"),
            list_join_expr("Analyte", "TargetAnalytes"),
            list_join_expr("WastePhase", "WastePhase_list"),
            list_join_expr("WasteType", "WasteType_list"),
            list_join_expr("PublishedDate", "PublishedDate_list"),
            pl.col("AdjustedConcentration").mean().alias("Target_AdjustedConcentration_mean_row"),
            pl.col("Volume").mean().alias("Volume_mean"),
            pl.col("Volume").max().alias("Volume_max"),
        ])
        .join(context_totals, on=["WasteSiteId", "Units"], how="left")
        .with_columns([
            (pl.col("Target_Inventory_sum") / pl.col("Context_TotalInventory_same_unit")).alias("TargetFractionOfTankUnitInventory"),
        ])
        .sort(["Units", "Target_Inventory_sum"], descending=[False, True])
    )
    pdf = grouped.to_pandas()
    pdf.insert(0, "Query", query)
    pdf.insert(1, "ResolvedMode", resolved)
    if symbol:
        pdf.insert(2, "HighlightedElement", symbol)
    return pdf


def target_by_phase(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None, min_inventory: float = 0.0,
) -> pd.DataFrame:
    target, _, _ = target_rows(dataset, query, mode, unit_filter, min_inventory)
    if target.is_empty():
        return pd.DataFrame()
    return (
        target.group_by(["Units", "WastePhase"])
        .agg([
            pl.col("Inventory").sum().alias("Target_Inventory_sum"),
            pl.len().alias("N_rows"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
        ])
        .sort(["Units", "Target_Inventory_sum"], descending=[False, True])
        .to_pandas()
    )


def target_by_type(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None, min_inventory: float = 0.0,
) -> pd.DataFrame:
    target, _, _ = target_rows(dataset, query, mode, unit_filter, min_inventory)
    if target.is_empty():
        return pd.DataFrame()
    return (
        target.group_by(["Units", "WasteType"])
        .agg([
            pl.col("Inventory").sum().alias("Target_Inventory_sum"),
            pl.len().alias("N_rows"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
        ])
        .sort(["Units", "Target_Inventory_sum"], descending=[False, True])
        .to_pandas()
    )


def co_elements(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None,
    min_target_inventory: float = 0.0, min_context_inventory: float = 0.0,
) -> pd.DataFrame:
    """For every OTHER element present in the tanks containing the target,
    how often and how much (present-tanks-only stats)."""
    target, resolved, symbol = target_rows(dataset, query, mode, unit_filter, min_target_inventory)
    if target.is_empty():
        return pd.DataFrame()
    tanks = target.get_column("WasteSiteId").drop_nulls().unique().to_list()
    n_target_tanks = len(tanks)
    context = dataset.require_df().filter(pl.col("WasteSiteId").is_in(tanks))
    context = dataset.filter_by_units(context, unit_filter)
    context = context.filter((pl.col("Inventory") > float(min_context_inventory)) & pl.col("Element").is_not_null())
    if context.is_empty():
        return pd.DataFrame()

    tank_element = (
        context.group_by(["Units", "WasteSiteId", "Element"])
        .agg(pl.col("Inventory").sum().alias("Inventory_in_tank"))
    )
    stats = (
        tank_element.group_by(["Units", "Element"])
        .agg([
            pl.col("WasteSiteId").n_unique().alias("N_tanks_present"),
            pl.col("Inventory_in_tank").sum().alias("Total_inventory_in_target_tanks"),
            pl.col("Inventory_in_tank").mean().alias("Mean_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").median().alias("Median_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").std().alias("Std_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").max().alias("Max_inventory_in_one_tank"),
        ])
        .with_columns([
            pl.lit(n_target_tanks).alias("N_target_tanks_total"),
            (100.0 * pl.col("N_tanks_present") / pl.lit(max(n_target_tanks, 1))).alias("PresenceFraction_pct"),
        ])
    )
    if symbol:
        stats = stats.with_columns((pl.col("Element") == symbol).alias("IsHighlighted"))
    else:
        stats = stats.with_columns(pl.lit(False).alias("IsHighlighted"))
    return stats.sort(["Units", "Total_inventory_in_target_tanks"], descending=[False, True]).to_pandas()


def co_analytes(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None,
    min_target_inventory: float = 0.0, min_context_inventory: float = 0.0,
) -> pd.DataFrame:
    """Analyte-level companion to co_elements."""
    target, resolved, symbol = target_rows(dataset, query, mode, unit_filter, min_target_inventory)
    if target.is_empty():
        return pd.DataFrame()
    tanks = target.get_column("WasteSiteId").drop_nulls().unique().to_list()
    n_target_tanks = len(tanks)
    context = dataset.require_df().filter(pl.col("WasteSiteId").is_in(tanks))
    context = dataset.filter_by_units(context, unit_filter)
    context = context.filter((pl.col("Inventory") > float(min_context_inventory)) & pl.col("Analyte").is_not_null())
    if context.is_empty():
        return pd.DataFrame()

    tank_analyte = (
        context.group_by(["Units", "WasteSiteId", "Analyte", "Element", "ElementList"])
        .agg(pl.col("Inventory").sum().alias("Inventory_in_tank"))
    )
    stats = (
        tank_analyte.group_by(["Units", "Analyte", "Element", "ElementList"])
        .agg([
            pl.col("WasteSiteId").n_unique().alias("N_tanks_present"),
            pl.col("Inventory_in_tank").sum().alias("Total_inventory_in_target_tanks"),
            pl.col("Inventory_in_tank").mean().alias("Mean_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").median().alias("Median_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").std().alias("Std_inventory_present_tanks_only"),
            pl.col("Inventory_in_tank").max().alias("Max_inventory_in_one_tank"),
        ])
        .with_columns([
            pl.lit(n_target_tanks).alias("N_target_tanks_total"),
            (100.0 * pl.col("N_tanks_present") / pl.lit(max(n_target_tanks, 1))).alias("PresenceFraction_pct"),
        ])
    )
    if symbol:
        stats = stats.with_columns(pl.col("ElementList").str.contains(symbol, literal=True).alias("IsHighlighted"))
    else:
        stats = stats.with_columns(pl.lit(False).alias("IsHighlighted"))
    return stats.sort(["Units", "Total_inventory_in_target_tanks"], descending=[False, True]).to_pandas()


def composition_stats(
    dataset: HanfordDataset, query: str, mode: str = "auto",
    unit_filter: Optional[Union[str, Sequence[str]]] = None,
    min_target_inventory: float = 0.0, min_context_inventory: float = 0.0,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Absolute stats, compositional-fraction stats, and the underlying
    per-tank-element long table, for the tanks containing the target.

    Absolute vs fraction answer different questions: absolute stats are
    mean/std of each element's raw inventory across the tanks it's present
    in; fraction stats first normalize each tank by its own same-unit
    total, THEN average -- so one huge tank can't dominate the "typical
    composition" picture. Both also report a "_zero_filled" mean, averaged
    over ALL target tanks (including tanks where the element is absent,
    i.e. contributing zero) rather than only the tanks it's present in.
    """
    target, resolved, symbol = target_rows(dataset, query, mode, unit_filter, min_target_inventory)
    if target.is_empty():
        empty = pd.DataFrame()
        return empty, empty, empty
    tanks = target.get_column("WasteSiteId").drop_nulls().unique().sort().to_list()
    n_target_tanks = len(tanks)
    context = dataset.require_df().filter(pl.col("WasteSiteId").is_in(tanks))
    context = dataset.filter_by_units(context, unit_filter)
    context = context.filter((pl.col("Inventory") > float(min_context_inventory)) & pl.col("Element").is_not_null())
    if context.is_empty():
        empty = pd.DataFrame()
        return empty, empty, empty

    tank_element = (
        context.group_by(["Units", "WasteSiteId", "TankFarm", "Element"])
        .agg([
            pl.col("Inventory").sum().alias("Inventory_sum"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
            list_join_expr("Analyte", "Analytes"),
        ])
    )
    totals = tank_element.group_by(["Units", "WasteSiteId"]).agg(pl.col("Inventory_sum").sum().alias("Tank_total_same_unit"))
    tank_element = tank_element.join(totals, on=["Units", "WasteSiteId"], how="left").with_columns(
        (pl.col("Inventory_sum") / pl.col("Tank_total_same_unit")).alias("Fraction_of_tank_unit_inventory")
    )

    abs_stats = (
        tank_element.group_by(["Units", "Element"])
        .agg([
            pl.lit(n_target_tanks).alias("N_target_tanks_total"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks_present"),
            pl.col("Inventory_sum").mean().alias("Mean_inventory_present_tanks_only"),
            pl.col("Inventory_sum").std().alias("Std_inventory_present_tanks_only"),
            pl.col("Inventory_sum").median().alias("Median_inventory_present_tanks_only"),
            pl.col("Inventory_sum").max().alias("Max_inventory_in_one_tank"),
            pl.col("Inventory_sum").sum().alias("Total_inventory_in_target_tanks"),
        ])
        .with_columns([
            (pl.col("Total_inventory_in_target_tanks") / pl.lit(max(n_target_tanks, 1))).alias("Mean_inventory_all_target_tanks_zero_filled"),
            (100.0 * pl.col("N_tanks_present") / pl.lit(max(n_target_tanks, 1))).alias("PresenceFraction_pct"),
        ])
    )

    frac_stats = (
        tank_element.group_by(["Units", "Element"])
        .agg([
            pl.lit(n_target_tanks).alias("N_target_tanks_total"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks_present"),
            pl.col("Fraction_of_tank_unit_inventory").mean().alias("Mean_fraction_present_tanks_only"),
            pl.col("Fraction_of_tank_unit_inventory").std().alias("Std_fraction_present_tanks_only"),
            pl.col("Fraction_of_tank_unit_inventory").median().alias("Median_fraction_present_tanks_only"),
            pl.col("Fraction_of_tank_unit_inventory").max().alias("Max_fraction_in_one_tank"),
            pl.col("Fraction_of_tank_unit_inventory").sum().alias("Sum_fraction_present"),
        ])
        .with_columns([
            (pl.col("Sum_fraction_present") / pl.lit(max(n_target_tanks, 1))).alias("Mean_fraction_all_target_tanks_zero_filled"),
            (100.0 * pl.col("N_tanks_present") / pl.lit(max(n_target_tanks, 1))).alias("PresenceFraction_pct"),
        ])
    )

    if symbol:
        abs_stats = abs_stats.with_columns((pl.col("Element") == symbol).alias("IsHighlighted"))
        frac_stats = frac_stats.with_columns((pl.col("Element") == symbol).alias("IsHighlighted"))
        tank_element = tank_element.with_columns((pl.col("Element") == symbol).alias("IsHighlighted"))
    else:
        abs_stats = abs_stats.with_columns(pl.lit(False).alias("IsHighlighted"))
        frac_stats = frac_stats.with_columns(pl.lit(False).alias("IsHighlighted"))
        tank_element = tank_element.with_columns(pl.lit(False).alias("IsHighlighted"))

    abs_pdf = abs_stats.sort(["Units", "Mean_inventory_all_target_tanks_zero_filled"], descending=[False, True]).to_pandas()
    frac_pdf = frac_stats.sort(["Units", "Mean_fraction_all_target_tanks_zero_filled"], descending=[False, True]).to_pandas()
    tank_pdf = tank_element.sort(["Units", "WasteSiteId", "Inventory_sum"], descending=[False, False, True]).to_pandas()
    return abs_pdf, frac_pdf, tank_pdf
