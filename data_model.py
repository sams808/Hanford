"""
data_model.py — load/clean/cache/join pipeline for Hanford tank composition
data (framework-agnostic: no PySide6 imports).

Ported from the original app's HanfordDataModel, restructured: this class
owns only load/clean/cache/join plus cheap accessors. All analytical
queries are plain functions in the *_science modules that take `dataset.df`
as an argument (see overview_science.py and friends) — the old app's ~40
methods on one god-class are deliberately not reproduced here.

Two behavior differences from the old app, both deliberate:
  - `app_base_dir()` is frozen-exe aware (`sys.frozen`); the old app was
    never packaged so it never needed this, but a naive `__file__`-based
    lookup silently fails to find data files next to a PyInstaller .exe.
  - CACHE_SCHEMA_VERSION is Ember's own string, so dev parquet caches never
    collide with the old app's cache files if they're ever in the same folder.
"""
from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

import polars as pl

from elements import (
    classify_analyte,
    element_list_padded,
    element_list_string,
    primary_element_from_analyte,
    tank_farm_from_id,
)

CACHE_SCHEMA_VERSION = "ember_v1"

DEFAULT_COMPOSITION_FILENAMES = ["Hanford.csv", "hanford.csv", "Hanford.tsv", "hanford.tsv"]
DEFAULT_ATTRIBUTES_FILENAMES = [
    "Tank_attributes.csv", "tank_attributes.csv", "Tank_Attributes.csv",
    "tank_attributes.tsv", "Tank_attributes.tsv",
]

NULL_VALUES = ["", "NA", "N/A", "NaN", "nan", "None", "null", "undefined", "NULL"]
REQUIRED_COLUMNS = ["WasteSiteId", "Analyte", "Inventory", "Units"]

_OPTIONAL_COMPOSITION_DEFAULTS = {
    "WastePhase": None, "WasteType": None, "Volume": None, "VolumeUnits": None,
    "AdjustedConcentration": None, "AdjustedConcentrationUnits": None,
    "DecayDate": None, "PublishedDate": None, "CCBLog": None,
}
_COMPOSITION_TEXT_COLUMNS = [
    "WasteSiteId", "Analyte", "WastePhase", "WasteType", "Units",
    "VolumeUnits", "AdjustedConcentrationUnits", "DecayDate", "PublishedDate", "CCBLog",
]
_COMPOSITION_NUMERIC_COLUMNS = ["Inventory", "Volume", "AdjustedConcentration"]

_ATTRIBUTE_OPTIONAL_COLUMNS = [
    "TankType", "Capacity", "CapacityUnits", "Diameter", "DiameterUnits",
    "MaxOperatingDepth", "MaxOperatingDepthUnits", "Ventilation", "InServiceDate",
    "InterimStabilization", "IntrusionPrevention", "OperationCapacityKGal",
    "TankStatus", "TankIntegrity", "DIL_Gal",
]
_ATTRIBUTE_TEXT_COLUMNS = [
    "WasteSiteId", "TankType", "CapacityUnits", "DiameterUnits", "MaxOperatingDepthUnits",
    "Ventilation", "InServiceDate", "InterimStabilization", "IntrusionPrevention",
    "TankStatus", "TankIntegrity",
]
_ATTRIBUTE_NUMERIC_COLUMNS = ["Capacity", "Diameter", "MaxOperatingDepth", "OperationCapacityKGal", "DIL_Gal"]


def app_base_dir() -> Path:
    """Folder Ember's data files should be auto-detected from: next to the
    frozen .exe when packaged (PyInstaller extracts __file__ into a temp
    _MEIPASS folder, not next to the actual exe), next to this source file
    when run from Python."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_first_existing_file(folders: Sequence[Union[str, Path]], names: Sequence[str]) -> Optional[Path]:
    for folder in folders:
        try:
            base = Path(folder).expanduser().resolve()
        except Exception:
            continue
        for name in names:
            p = base / name
            if p.exists():
                return p
    return None


def detect_separator(path: Union[str, Path], n_bytes: int = 65536) -> str:
    path = Path(path)
    raw = path.read_bytes()[:n_bytes]
    text = raw.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=["\t", ",", ";", "|"])
        return dialect.delimiter
    except Exception:
        first_lines = "\n".join(text.splitlines()[:10])
        counts = {d: first_lines.count(d) for d in ["\t", ",", ";", "|"]}
        return max(counts, key=counts.get)


def _clean_numeric_expr(col: str) -> pl.Expr:
    # Cast through Utf8 first: some CSV exports contain thousands separators
    # or mixed numeric/text values that a direct numeric cast would reject.
    expr = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars().str.replace_all(",", "")
    return pl.when(expr.is_in(NULL_VALUES)).then(None).otherwise(expr).cast(pl.Float64, strict=False)


def list_join_expr(col: str, alias: Optional[str] = None) -> pl.Expr:
    """A group-by aggregation expression collecting a column's distinct
    non-null values as a (still-list-typed) column -- used by the
    *_science modules for "which analytes/phases/types contributed to this
    group" summary columns. Kept as a Polars list rather than joined into a
    string here; pandas/table/export code stringifies it on the way out."""
    return pl.col(col).drop_nulls().unique().sort().alias(alias or f"{col}_list")


@dataclass
class LoadReport:
    source_path: Path
    parquet_path: Optional[Path]
    separator: Optional[str]
    rows: int
    columns: int
    load_seconds: float
    cache_used: bool
    estimated_size_mb: Optional[float]
    attributes_path: Optional[Path] = None
    attributes_rows: int = 0


class HanfordDataset:
    """Owns the loaded DataFrame and the load/clean/cache/join pipeline.
    Everything analytical lives in the *_science modules as plain functions
    over `dataset.df`."""

    def __init__(self, logger: Optional[Callable[[str], None]] = None) -> None:
        self.df: Optional[pl.DataFrame] = None
        self.attrs_df: Optional[pl.DataFrame] = None
        self.path: Optional[Path] = None
        self.output_root: Path = Path("ember_outputs")
        self.report: Optional[LoadReport] = None
        self.logger = logger or (lambda msg: None)

    def log(self, msg: str) -> None:
        self.logger(msg)

    def is_loaded(self) -> bool:
        return self.df is not None

    def require_df(self) -> pl.DataFrame:
        if self.df is None:
            raise RuntimeError("No dataset loaded. Load Hanford.csv first.")
        return self.df

    # ------------------------------------------------------------------
    # Load / clean / cache / join
    # ------------------------------------------------------------------
    def load_local_default(self, use_cache: bool = True, refresh_cache: bool = False) -> LoadReport:
        """Auto-detect Hanford.csv (+ Tank_attributes.csv) next to the app."""
        search_folders = [app_base_dir(), Path.cwd()]
        comp_path = find_first_existing_file(search_folders, DEFAULT_COMPOSITION_FILENAMES)
        if comp_path is None:
            raise FileNotFoundError(
                "Could not find Hanford.csv next to the app or in the current "
                "folder. Place Hanford.csv (and optionally Tank_attributes.csv) "
                "next to Ember, or use 'Load CSV/Parquet'."
            )
        attr_path = find_first_existing_file(
            [comp_path.parent, app_base_dir(), Path.cwd()], DEFAULT_ATTRIBUTES_FILENAMES
        )
        if attr_path is not None:
            self.log(f"Using local dataset: {comp_path} + attributes: {attr_path}")
        else:
            self.log(f"Using local dataset: {comp_path} (no Tank_attributes.csv found)")
        return self.load(comp_path, use_cache=use_cache, refresh_cache=refresh_cache, attributes_path=attr_path)

    def load(
        self,
        path: Union[str, Path],
        use_cache: bool = True,
        refresh_cache: bool = False,
        attributes_path: Optional[Union[str, Path]] = None,
    ) -> LoadReport:
        t0 = time.time()
        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        self.path = path
        self.output_root = path.parent / "ember_outputs"
        self.output_root.mkdir(parents=True, exist_ok=True)

        if attributes_path is None:
            attributes_path = find_first_existing_file([path.parent], DEFAULT_ATTRIBUTES_FILENAMES)
        attributes_path_resolved = Path(attributes_path).expanduser().resolve() if attributes_path else None

        parquet_path = path.with_name(f"{path.stem}.cleaned.{CACHE_SCHEMA_VERSION}.parquet")
        cache_used = False
        separator: Optional[str] = None
        attrs_rows = 0

        if use_cache and parquet_path.exists() and not refresh_cache:
            self.log(f"Loading cached parquet: {parquet_path.name}")
            df = pl.read_parquet(parquet_path)
            cache_used = True
            # Reload the compact attributes table fresh even off a merged
            # cache, so the Tank Attributes workspace has a live source.
            if attributes_path_resolved and attributes_path_resolved.exists():
                try:
                    self.attrs_df = self._clean_attributes_dataframe(self._read_table(attributes_path_resolved))
                    attrs_rows = self.attrs_df.height
                except Exception as exc:
                    self.log(f"WARNING: could not load tank attributes: {exc}")
                    self.attrs_df = None
            else:
                self.attrs_df = None
        else:
            df_raw = self._read_table(path)
            if path.suffix.lower() not in (".parquet", ".pq"):
                separator = detect_separator(path)
                self.log(f"Detected separator: {separator!r}")
            df = self._clean_dataframe(df_raw)

            if attributes_path_resolved and attributes_path_resolved.exists():
                self.log(f"Loading tank attributes: {attributes_path_resolved.name}")
                attrs_raw = self._read_table(attributes_path_resolved)
                self.attrs_df = self._clean_attributes_dataframe(attrs_raw)
                attrs_rows = self.attrs_df.height
                df = self._merge_tank_attributes(df, self.attrs_df)
                self.log(f"Merged tank attributes: {attrs_rows:,} tanks")
            else:
                self.attrs_df = None
                self.log("No Tank_attributes.csv found; running without tank metadata.")

            if use_cache:
                self.log(f"Writing cleaned parquet cache: {parquet_path.name}")
                df.write_parquet(parquet_path)

        self.df = df
        load_seconds = time.time() - t0
        try:
            estimated_size_mb = float(df.estimated_size("mb"))
        except Exception:
            estimated_size_mb = None

        self.report = LoadReport(
            source_path=path,
            parquet_path=parquet_path if use_cache else None,
            separator=separator,
            rows=df.height,
            columns=df.width,
            load_seconds=load_seconds,
            cache_used=cache_used,
            estimated_size_mb=estimated_size_mb,
            attributes_path=attributes_path_resolved,
            attributes_rows=attrs_rows,
        )
        self.log(f"Loaded {df.height:,} rows x {df.width} columns in {load_seconds:.2f}s")
        return self.report

    def _read_table(self, path: Path) -> pl.DataFrame:
        if path.suffix.lower() in (".parquet", ".pq"):
            return pl.read_parquet(path)
        sep = detect_separator(path)
        return pl.read_csv(
            path, separator=sep, null_values=NULL_VALUES,
            infer_schema_length=50000, ignore_errors=True, try_parse_dates=False,
        )

    def _clean_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.rename({c: str(c).strip() for c in df.columns})

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}\nFound columns: {df.columns}")

        for col, default in _OPTIONAL_COMPOSITION_DEFAULTS.items():
            if col not in df.columns:
                df = df.with_columns(pl.lit(default).alias(col))

        exprs = [
            pl.col(c).cast(pl.Utf8, strict=False).str.strip_chars().alias(c)
            for c in _COMPOSITION_TEXT_COLUMNS if c in df.columns
        ]
        df = df.with_columns(exprs)
        for col in _COMPOSITION_NUMERIC_COLUMNS:
            if col in df.columns:
                df = df.with_columns(_clean_numeric_expr(col).alias(col))

        # Parsed columns via Python functions — fine for tens of thousands of
        # rows (this is the same approach the old app used).
        analytes = df.get_column("Analyte").to_list()
        site_ids = df.get_column("WasteSiteId").to_list()
        df = df.with_columns([
            pl.Series("Element", [primary_element_from_analyte(a) for a in analytes], dtype=pl.Utf8),
            pl.Series("ElementList", [element_list_string(a) for a in analytes], dtype=pl.Utf8),
            pl.Series("ElementListPadded", [element_list_padded(a) for a in analytes], dtype=pl.Utf8),
            pl.Series("AnalyteClass", [classify_analyte(a) for a in analytes], dtype=pl.Utf8),
            pl.Series("TankFarm", [tank_farm_from_id(w) for w in site_ids], dtype=pl.Utf8),
        ])

        df = df.with_columns([
            (pl.col("Inventory") > 0).fill_null(False).alias("InventoryPositive"),
            pl.when(pl.col("Inventory") > 0).then(pl.col("Inventory").log10()).otherwise(None).alias("log10_Inventory"),
        ])
        return df

    def _clean_attributes_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.rename({c: str(c).strip() for c in df.columns})
        if "Name" in df.columns and "WasteSiteId" not in df.columns:
            df = df.rename({"Name": "WasteSiteId"})
        if "WasteSiteId" not in df.columns:
            raise ValueError(f"Tank attributes file must contain Name or WasteSiteId. Found columns: {df.columns}")

        for col in _ATTRIBUTE_OPTIONAL_COLUMNS:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))

        exprs = [
            pl.col(c).cast(pl.Utf8, strict=False).str.strip_chars().alias(c)
            for c in _ATTRIBUTE_TEXT_COLUMNS if c in df.columns
        ]
        df = df.with_columns(exprs)
        for col in _ATTRIBUTE_NUMERIC_COLUMNS:
            if col in df.columns:
                df = df.with_columns(_clean_numeric_expr(col).alias(col))

        tank_type_upper = pl.col("TankType").cast(pl.Utf8, strict=False).str.to_uppercase()
        status_upper = pl.col("TankStatus").cast(pl.Utf8, strict=False).str.to_uppercase()
        integrity_lower = pl.col("TankIntegrity").cast(pl.Utf8, strict=False).str.to_lowercase()
        df = df.with_columns([
            tank_type_upper.str.contains("DST", literal=True).fill_null(False).alias("IsDST"),
            tank_type_upper.str.contains("SST", literal=True).fill_null(False).alias("IsSST"),
            pl.when(tank_type_upper.str.contains("DST", literal=True)).then(pl.lit("DST"))
              .when(tank_type_upper.str.contains("SST", literal=True)).then(pl.lit("SST"))
              .otherwise(pl.lit("Unknown")).alias("TankSystem"),
            integrity_lower.str.contains("leaker", literal=True).fill_null(False).alias("IsLeakerOrAssumedLeaker"),
            status_upper.str.contains("WI", literal=True).fill_null(False).alias("HasWIStatus"),
            pl.col("WasteSiteId").map_elements(tank_farm_from_id, return_dtype=pl.Utf8).alias("TankFarm"),
        ])
        return df.unique(subset=["WasteSiteId"], keep="first")

    def _merge_tank_attributes(self, df: pl.DataFrame, attrs: Optional[pl.DataFrame]) -> pl.DataFrame:
        if attrs is None or attrs.is_empty():
            return df
        attr_cols = [c for c in attrs.columns if c != "WasteSiteId"]
        # Drop any stale attribute columns from a previous merge, but keep
        # the composition-derived TankFarm unless the join provides its own.
        drop_cols = [c for c in attr_cols if c in df.columns and c != "TankFarm"]
        if drop_cols:
            df = df.drop(drop_cols)
        attrs_join = attrs
        if "TankFarm" in attrs_join.columns and "TankFarm" in df.columns:
            attrs_join = attrs_join.drop("TankFarm")
        out = df.join(attrs_join, on="WasteSiteId", how="left")
        return out.with_columns(pl.col("TankType").is_not_null().fill_null(False).alias("HasTankAttributes"))

    # ------------------------------------------------------------------
    # Cheap accessors
    # ------------------------------------------------------------------
    def available_units(self) -> List[str]:
        return [str(v) for v in self.require_df().get_column("Units").drop_nulls().unique().sort().to_list()]

    def available_tanks(self) -> List[str]:
        return [str(v) for v in self.require_df().get_column("WasteSiteId").drop_nulls().unique().sort().to_list()]

    def available_farms(self) -> List[str]:
        return [str(v) for v in self.require_df().get_column("TankFarm").drop_nulls().unique().sort().to_list()]

    def available_elements(self) -> List[str]:
        return [str(v) for v in self.require_df().get_column("Element").drop_nulls().unique().sort().to_list()]

    def raw_preview(self, n: int = 250):
        return self.require_df().head(n).to_pandas()

    def target_expr(self, query: str, mode: str = "auto") -> Tuple[pl.Expr, str, Optional[str]]:
        """Build a filter expression for an element/analyte search query.
        Shared by element_science's target-search functions."""
        from elements import normalize_element_symbol

        query = str(query).strip()
        if not query:
            raise ValueError("Enter an element/analyte query first.")
        mode = (mode or "auto").strip().lower()
        norm_symbol = normalize_element_symbol(query)
        resolved = mode
        if mode == "auto":
            resolved = "element" if norm_symbol else "analyte_contains"

        if resolved == "element":
            symbol = norm_symbol or normalize_element_symbol(query)
            if not symbol:
                raise ValueError(f"{query!r} is not a valid element symbol. Use analyte_contains or regex mode.")
            return pl.col("ElementListPadded").str.contains(f";{symbol};", literal=True), "element", symbol
        if resolved == "analyte_exact":
            return (pl.col("Analyte").str.to_lowercase() == query.lower()), "analyte_exact", None
        if resolved == "analyte_contains":
            return pl.col("Analyte").str.to_lowercase().str.contains(query.lower(), literal=True), "analyte_contains", None
        if resolved == "regex":
            return pl.col("Analyte").str.contains(query), "regex", None
        raise ValueError(f"Unknown match mode: {mode}")

    def filter_by_units(self, df: pl.DataFrame, unit_filter: Optional[Union[str, Sequence[str]]]) -> pl.DataFrame:
        """Filter by unit, tolerant of a single string, a list, or None/"All"."""
        if unit_filter is None:
            return df
        if isinstance(unit_filter, str):
            if unit_filter in ("", "All"):
                return df
            units = [unit_filter]
        else:
            units = [str(u) for u in list(unit_filter) if str(u) not in ("", "All")]
            if not units:
                return df
        return df.filter(pl.col("Units").is_in(units))
