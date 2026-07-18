"""
export_utils.py — generic "write a folder of named CSV tables" helper,
shared across workspaces (search results, tank views, correlation tables,
vitrification results, ...) instead of each one reimplementing the same
timestamped-folder-plus-manifest logic.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from data_model import HanfordDataset


def safe_name(text: object, max_len: int = 90) -> str:
    s = str(text) if text is not None else "NA"
    s = re.sub(r"[^\w\-.]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if s else "NA"


def export_named_tables(
    dataset: HanfordDataset, folder_prefix: str, tables: Dict[str, Optional[pd.DataFrame]],
) -> Path:
    """Write each non-None DataFrame in `tables` as `<name>.csv` inside a
    fresh timestamped folder under dataset.output_root, plus a
    manifest.csv. Returns the folder path."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dataset.output_root / f"{safe_name(folder_prefix)}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    for name, df in tables.items():
        if df is None:
            continue
        path = out_dir / f"{safe_name(name)}.csv"
        df.to_csv(path, index=False)
        manifest_rows.append({"file": path.name, "rows": len(df)})
    pd.DataFrame(manifest_rows).to_csv(out_dir / "manifest.csv", index=False)
    return out_dir
