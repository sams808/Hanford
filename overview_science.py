"""
overview_science.py — dataset-level audit queries (framework-agnostic).

Ported from the old app's HanfordDataModel.overview/units_audit/
missing_audit/phase_audit/type_audit/farm_audit/top_analytes/top_elements,
restructured as plain functions over a HanfordDataset instead of methods on
a god-class.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import polars as pl

from data_model import HanfordDataset


def overview(dataset: HanfordDataset) -> pd.DataFrame:
    df = dataset.require_df()
    out = {
        "rows": df.height,
        "columns": df.width,
        "n_tanks": df.get_column("WasteSiteId").n_unique(),
        "n_analytes": df.get_column("Analyte").n_unique(),
        "n_primary_elements": df.filter(pl.col("Element").is_not_null()).get_column("Element").n_unique(),
        "n_waste_phases": df.get_column("WastePhase").n_unique(),
        "n_waste_types": df.get_column("WasteType").n_unique(),
        "n_units": df.get_column("Units").n_unique(),
    }
    report = dataset.report
    if report is not None:
        out.update({
            "source_file": str(report.source_path),
            "cache_used": report.cache_used,
            "load_seconds": round(report.load_seconds, 3),
            "estimated_size_mb": round(report.estimated_size_mb or 0, 3),
            "tank_attributes_file": str(report.attributes_path) if report.attributes_path else "",
            "tank_attributes_rows": report.attributes_rows,
        })
    return pd.DataFrame([out])


def units_audit(dataset: HanfordDataset) -> pd.DataFrame:
    df = dataset.require_df()
    return (
        df.group_by("Units")
        .agg([
            pl.len().alias("N_rows"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
            pl.col("Element").n_unique().alias("N_elements"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.col("Inventory").sum().alias("TotalInventory"),
            pl.col("Inventory").min().alias("MinInventory"),
            pl.col("Inventory").max().alias("MaxInventory"),
        ])
        .sort("TotalInventory", descending=True)
        .to_pandas()
    )


def missing_audit(dataset: HanfordDataset) -> pd.DataFrame:
    df = dataset.require_df()
    rows = df.height
    records = []
    for col in df.columns:
        n_null = df.select(pl.col(col).is_null().sum()).item()
        records.append({
            "column": col,
            "n_null": int(n_null),
            "pct_null": 100.0 * float(n_null) / max(rows, 1),
            "dtype": str(df.schema[col]),
        })
    return pd.DataFrame(records).sort_values(["pct_null", "column"], ascending=[False, True])


def category_audit(dataset: HanfordDataset, category_col: str) -> pd.DataFrame:
    df = dataset.require_df()
    return (
        df.group_by(category_col)
        .agg([
            pl.len().alias("N_rows"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
            pl.col("Element").n_unique().alias("N_elements"),
            pl.col("Inventory").sum().alias("TotalInventory"),
        ])
        .sort("TotalInventory", descending=True)
        .to_pandas()
    )


def phase_audit(dataset: HanfordDataset) -> pd.DataFrame:
    return category_audit(dataset, "WastePhase")


def type_audit(dataset: HanfordDataset) -> pd.DataFrame:
    return category_audit(dataset, "WasteType")


def farm_audit(dataset: HanfordDataset) -> pd.DataFrame:
    return category_audit(dataset, "TankFarm")


def top_analytes(dataset: HanfordDataset, unit: Optional[str] = None, top_n: int = 50) -> pd.DataFrame:
    df = dataset.require_df()
    if unit and unit != "All":
        df = df.filter(pl.col("Units") == unit)
    return (
        df.group_by(["Units", "Analyte", "Element", "ElementList", "AnalyteClass"])
        .agg([
            pl.col("Inventory").sum().alias("TotalInventory"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.len().alias("N_rows"),
        ])
        .sort("TotalInventory", descending=True)
        .head(top_n)
        .to_pandas()
    )


def top_elements(dataset: HanfordDataset, unit: Optional[str] = None, top_n: int = 50) -> pd.DataFrame:
    df = dataset.require_df().filter(pl.col("Element").is_not_null())
    if unit and unit != "All":
        df = df.filter(pl.col("Units") == unit)
    return (
        df.group_by(["Units", "Element"])
        .agg([
            pl.col("Inventory").sum().alias("TotalInventory"),
            pl.col("WasteSiteId").n_unique().alias("N_tanks"),
            pl.col("Analyte").n_unique().alias("N_analytes"),
            pl.len().alias("N_rows"),
        ])
        .sort("TotalInventory", descending=True)
        .head(top_n)
        .to_pandas()
    )


def environment_report() -> pd.DataFrame:
    """Library versions + platform info for debug bundles. Deliberately has
    no knowledge of app identity (APP_NAME/APP_VERSION) -- that's a Qt-layer
    concern the caller can merge in via `extra_info`."""
    import platform
    import sys

    import matplotlib
    import numpy

    try:
        import pyarrow
        pyarrow_version = pyarrow.__version__
    except Exception:
        pyarrow_version = "not installed"

    return pd.DataFrame([{
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "polars_version": pl.__version__,
        "pandas_version": pd.__version__,
        "numpy_version": numpy.__version__,
        "matplotlib_version": matplotlib.__version__,
        "pyarrow_version": pyarrow_version,
    }])


def export_global_debug_bundle(dataset: HanfordDataset, extra_info: Optional[dict] = None) -> Path:
    """Write a timestamped folder of small audit CSVs -- send this instead
    of the full source CSV when something needs debugging."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dataset.output_root / f"debug_bundle_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    overview(dataset).to_csv(out_dir / "overview.csv", index=False)
    units_audit(dataset).to_csv(out_dir / "units_audit.csv", index=False)
    missing_audit(dataset).to_csv(out_dir / "missing_audit.csv", index=False)
    phase_audit(dataset).to_csv(out_dir / "phase_audit.csv", index=False)
    type_audit(dataset).to_csv(out_dir / "waste_type_audit.csv", index=False)
    farm_audit(dataset).to_csv(out_dir / "farm_audit.csv", index=False)
    top_elements(dataset, unit=None, top_n=200).to_csv(out_dir / "top_elements_all.csv", index=False)
    top_analytes(dataset, unit=None, top_n=300).to_csv(out_dir / "top_analytes_all.csv", index=False)
    dataset.raw_preview(500).to_csv(out_dir / "raw_preview.csv", index=False)

    env = environment_report()
    for key, value in (extra_info or {}).items():
        env[key] = value
    env.to_csv(out_dir / "environment.csv", index=False)

    manifest = pd.DataFrame([
        {"file": p.name, "size_bytes": p.stat().st_size} for p in sorted(out_dir.glob("*.csv"))
    ])
    manifest.to_csv(out_dir / "manifest.csv", index=False)
    return out_dir
