import sys

import polars as pl
import pytest

import data_model as dm
from conftest import REAL_ATTRS_PATH, REAL_CSV_PATH, requires_real_data


class TestAppBaseDir:
    def test_dev_mode_uses_module_folder(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        base = dm.app_base_dir()
        assert base.exists()
        assert (base / "data_model.py").exists()

    def test_frozen_exe_uses_executable_folder(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "Ember.exe"
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe))
        assert dm.app_base_dir() == tmp_path


class TestFindFirstExistingFile:
    def test_finds_in_second_folder(self, tmp_path):
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_a.mkdir()
        folder_b.mkdir()
        (folder_b / "Hanford.csv").write_text("x")
        found = dm.find_first_existing_file([folder_a, folder_b], dm.DEFAULT_COMPOSITION_FILENAMES)
        assert found == folder_b / "Hanford.csv"

    def test_returns_none_when_missing(self, tmp_path):
        assert dm.find_first_existing_file([tmp_path], dm.DEFAULT_COMPOSITION_FILENAMES) is None

    def test_skips_unresolvable_folder_entry(self, tmp_path):
        (tmp_path / "Hanford.csv").write_text("x")
        # None can't be turned into a Path -- must be skipped, not raise.
        found = dm.find_first_existing_file([None, tmp_path], dm.DEFAULT_COMPOSITION_FILENAMES)
        assert found == tmp_path / "Hanford.csv"


class TestDetectSeparator:
    def test_detects_comma(self, tmp_path):
        path = tmp_path / "a.csv"
        path.write_text("a,b,c\n1,2,3\n1,2,3\n1,2,3\n")
        assert dm.detect_separator(path) == ","

    def test_falls_back_when_sniffer_cannot_decide(self, tmp_path):
        path = tmp_path / "a.csv"
        path.write_text("nodelimiterhere\nanotherline\n")
        # No tab/comma/semicolon/pipe anywhere -- Sniffer raises, and the
        # manual fallback returns the first (all-zero-count) candidate.
        assert dm.detect_separator(path) == "\t"


class TestCheapAccessors:
    def test_is_loaded_false_before_load(self):
        assert dm.HanfordDataset().is_loaded() is False

    def test_is_loaded_true_after(self, sample_dataset):
        assert sample_dataset.is_loaded() is True

    def test_require_df_raises_when_unloaded(self):
        with pytest.raises(RuntimeError, match="No dataset loaded"):
            dm.HanfordDataset().require_df()

    def test_available_units(self, sample_dataset):
        assert sample_dataset.available_units() == ["Ci", "kg"]

    def test_available_tanks(self, sample_dataset):
        assert sample_dataset.available_tanks() == ["241-A-101", "241-AN-104"]

    def test_available_farms(self, sample_dataset):
        assert sample_dataset.available_farms() == ["A", "AN"]

    def test_available_elements(self, sample_dataset):
        assert sample_dataset.available_elements() == ["Cd", "Cm", "Cs", "Fe", "Na", "Pu"]

    def test_raw_preview(self, sample_dataset):
        assert len(sample_dataset.raw_preview(n=3)) == 3


class TestTargetExpr:
    def test_auto_mode_resolves_element_when_valid_symbol(self, sample_dataset):
        expr, mode, symbol = sample_dataset.target_expr("Cs", mode="auto")
        assert mode == "element"
        assert symbol == "Cs"
        assert set(sample_dataset.df.filter(expr)["Analyte"].to_list()) == {"137Cs"}

    def test_auto_mode_falls_back_to_analyte_contains(self, sample_dataset):
        expr, mode, symbol = sample_dataset.target_expr("Alpha", mode="auto")
        assert mode == "analyte_contains"
        assert symbol is None
        assert set(sample_dataset.df.filter(expr)["Analyte"].to_list()) == {"Total Alpha"}

    def test_analyte_exact_mode(self, sample_dataset):
        expr, _, _ = sample_dataset.target_expr("total alpha", mode="analyte_exact")
        assert set(sample_dataset.df.filter(expr)["Analyte"].to_list()) == {"Total Alpha"}

    def test_regex_mode(self, sample_dataset):
        expr, _, _ = sample_dataset.target_expr(r"^2\d\d/2\d\dPu$", mode="regex")
        assert set(sample_dataset.df.filter(expr)["Analyte"].to_list()) == {"239/240Pu"}

    def test_empty_query_raises(self, sample_dataset):
        with pytest.raises(ValueError, match="Enter an element"):
            sample_dataset.target_expr("   ")

    def test_element_mode_with_invalid_symbol_raises(self, sample_dataset):
        with pytest.raises(ValueError, match="not a valid element symbol"):
            sample_dataset.target_expr("Zz", mode="element")

    def test_unknown_mode_raises(self, sample_dataset):
        with pytest.raises(ValueError, match="Unknown match mode"):
            sample_dataset.target_expr("Cs", mode="bogus")


class TestFilterByUnits:
    def test_none_passthrough(self, sample_dataset):
        assert sample_dataset.filter_by_units(sample_dataset.df, None).height == sample_dataset.df.height

    def test_all_string_passthrough(self, sample_dataset):
        assert sample_dataset.filter_by_units(sample_dataset.df, "All").height == sample_dataset.df.height

    def test_single_unit_string(self, sample_dataset):
        result = sample_dataset.filter_by_units(sample_dataset.df, "kg")
        assert set(result["Units"].unique().to_list()) == {"kg"}

    def test_list_of_units(self, sample_dataset):
        result = sample_dataset.filter_by_units(sample_dataset.df, ["kg", "Ci"])
        assert set(result["Units"].unique().to_list()) == {"kg", "Ci"}

    def test_list_with_only_blanks_passthrough(self, sample_dataset):
        result = sample_dataset.filter_by_units(sample_dataset.df, ["", "All"])
        assert result.height == sample_dataset.df.height


class TestMergeTankAttributesEdgeCases:
    def test_none_attrs_passthrough(self):
        dataset = dm.HanfordDataset()
        df = pl.DataFrame({"WasteSiteId": ["241-A-101"], "Analyte": ["Fe"]})
        assert dataset._merge_tank_attributes(df, None) is df

    def test_empty_attrs_passthrough(self):
        dataset = dm.HanfordDataset()
        df = pl.DataFrame({"WasteSiteId": ["241-A-101"], "Analyte": ["Fe"]})
        empty_attrs = pl.DataFrame(schema={"WasteSiteId": pl.Utf8, "TankType": pl.Utf8})
        assert dataset._merge_tank_attributes(df, empty_attrs) is df

    def test_remerge_drops_stale_columns(self, sample_dataset):
        # sample_dataset already has attributes merged once; re-merging must
        # drop the stale attribute columns before rejoining instead of
        # erroring on duplicate column names.
        remerged = sample_dataset._merge_tank_attributes(sample_dataset.df, sample_dataset.attrs_df)
        assert remerged.height == sample_dataset.df.height
        assert remerged["HasTankAttributes"].all()


class TestListJoinExpr:
    def test_collects_sorted_unique_non_null_values(self):
        df = pl.DataFrame({"g": [1, 1, 1, 2], "v": ["b", "a", "b", None]})
        out = df.group_by("g", maintain_order=True).agg(dm.list_join_expr("v")).sort("g")
        assert out.filter(pl.col("g") == 1)["v_list"].item().to_list() == ["a", "b"]
        assert out.filter(pl.col("g") == 2)["v_list"].item().to_list() == []

    def test_custom_alias(self):
        df = pl.DataFrame({"g": [1], "v": ["x"]})
        out = df.group_by("g").agg(dm.list_join_expr("v", "MyAlias"))
        assert "MyAlias" in out.columns


class TestCleanAttributesDataframeErrors:
    def test_missing_id_column_raises(self):
        dataset = dm.HanfordDataset()
        bad = pl.DataFrame({"SomeColumn": ["x"]})
        with pytest.raises(ValueError, match="must contain Name or WasteSiteId"):
            dataset._clean_attributes_dataframe(bad)


class TestCleanDataframe:
    def test_row_count_preserved_no_dedup(self, sample_dataset):
        # 9 fixture rows in, 9 out — cleaning must not silently collapse the
        # deliberate duplicate (WasteSiteId, Analyte) key.
        assert sample_dataset.df.height == 9

    def test_isotope_parsing_through_full_pipeline(self, sample_dataset):
        df = sample_dataset.df
        row = df.filter((pl.col("WasteSiteId") == "241-A-101") & (pl.col("Analyte") == "137Cs"))
        assert row["Element"].item() == "Cs"

    def test_combined_isotope_bugfix_through_full_pipeline(self, sample_dataset):
        df = sample_dataset.df
        pu = df.filter(pl.col("Analyte") == "239/240Pu")
        cm = df.filter(pl.col("Analyte") == "243/244Cm")
        assert pu["Element"].item() == "Pu"
        assert cm["Element"].item() == "Cm"

    def test_non_elemental_analyte_has_no_element(self, sample_dataset):
        row = sample_dataset.df.filter(pl.col("Analyte") == "Total Alpha")
        assert row["Element"].item() is None

    def test_tank_farm_parsed(self, sample_dataset):
        df = sample_dataset.df
        assert df.filter(pl.col("WasteSiteId") == "241-A-101")["TankFarm"].unique().to_list() == ["A"]
        assert df.filter(pl.col("WasteSiteId") == "241-AN-104")["TankFarm"].unique().to_list() == ["AN"]

    def test_inventory_positive_flag(self, sample_dataset):
        df = sample_dataset.df
        assert df["InventoryPositive"].all()

    def test_log10_inventory_matches_positive_inventory(self, sample_dataset):
        df = sample_dataset.df
        assert df["log10_Inventory"].null_count() == 0  # all fixture rows have positive inventory

    def test_duplicate_key_aggregates_correctly(self, sample_dataset):
        # Two rows share (WasteSiteId="241-A-101", Analyte="Fe") across
        # different WastePhase (50.0 Solid kg + 10.0 Liquid kg). Any query
        # must group_by(...).sum() rather than assume a unique key.
        fe_kg_total = (
            sample_dataset.df
            .filter((pl.col("WasteSiteId") == "241-A-101") & (pl.col("Element") == "Fe"))
            .group_by("WasteSiteId")
            .agg(pl.col("Inventory").sum().alias("total"))
        )
        assert fe_kg_total["total"].item() == pytest.approx(60.0)

    def test_missing_required_column_raises(self):
        bad = pl.DataFrame({"WasteSiteId": ["241-A-101"], "Analyte": ["Fe"]})
        with pytest.raises(ValueError, match="Missing required columns"):
            dm.HanfordDataset()._clean_dataframe(bad)


class TestCleanAttributesAndMerge:
    def test_tank_system_derived(self, sample_dataset):
        attrs = sample_dataset.attrs_df
        a101 = attrs.filter(pl.col("WasteSiteId") == "241-A-101")
        an104 = attrs.filter(pl.col("WasteSiteId") == "241-AN-104")
        assert a101["TankSystem"].item() == "SST"
        assert a101["IsSST"].item() is True
        assert an104["TankSystem"].item() == "DST"
        assert an104["IsDST"].item() is True

    def test_leaker_flag(self, sample_dataset):
        attrs = sample_dataset.attrs_df
        assert attrs.filter(pl.col("WasteSiteId") == "241-AN-104")["IsLeakerOrAssumedLeaker"].item() is True
        assert attrs.filter(pl.col("WasteSiteId") == "241-A-101")["IsLeakerOrAssumedLeaker"].item() is False

    def test_merge_sets_has_tank_attributes(self, sample_dataset):
        assert sample_dataset.df["HasTankAttributes"].all()

    def test_unmatched_tank_has_false_flag(self):
        dataset = dm.HanfordDataset()
        comp = pl.DataFrame({
            "WasteSiteId": ["241-Z-999"], "Analyte": ["Fe"], "WastePhase": ["Solid"],
            "WasteType": ["T9"], "Inventory": [1.0], "Units": ["kg"],
        })
        attrs_raw = pl.DataFrame({"Name": ["241-A-101"], "TankType": ["SST-4"]})
        df = dataset._clean_dataframe(comp)
        attrs = dataset._clean_attributes_dataframe(attrs_raw)
        merged = dataset._merge_tank_attributes(df, attrs)
        assert merged["HasTankAttributes"].item() is False


class TestLoadIntegration:
    def _write_csv(self, tmp_path):
        path = tmp_path / "Hanford.csv"
        path.write_text(
            "WasteSiteId,Analyte,WastePhase,WasteType,Inventory,Units\n"
            "241-A-101,137Cs,Liquid,T1,100.0,Ci\n"
            "241-A-101,Fe,Solid,T1,50.0,kg\n"
            "241-AN-104,239/240Pu,Sludge,T2,0.002,Ci\n"
        )
        return path

    def test_load_from_csv_and_cache_roundtrip(self, tmp_path):
        path = self._write_csv(tmp_path)
        dataset = dm.HanfordDataset()
        report1 = dataset.load(path, use_cache=True, refresh_cache=False)
        assert report1.rows == 3
        assert report1.cache_used is False
        assert report1.parquet_path is not None
        assert report1.parquet_path.exists()

        dataset2 = dm.HanfordDataset()
        report2 = dataset2.load(path, use_cache=True, refresh_cache=False)
        assert report2.cache_used is True
        assert dataset2.df.height == 3

    def test_load_missing_file_raises(self, tmp_path):
        dataset = dm.HanfordDataset()
        with pytest.raises(FileNotFoundError):
            dataset.load(tmp_path / "does_not_exist.csv")

    def test_load_from_parquet_path(self, tmp_path):
        csv_path = self._write_csv(tmp_path)
        first = dm.HanfordDataset()
        first.load(csv_path, use_cache=False)
        parquet_path = tmp_path / "exported.parquet"
        first.df.write_parquet(parquet_path)

        dataset = dm.HanfordDataset()
        report = dataset.load(parquet_path, use_cache=False)
        assert report.separator is None
        assert report.rows == 3
        assert dataset.df.filter(pl.col("Analyte") == "239/240Pu")["Element"].item() == "Pu"

    def test_estimated_size_failure_falls_back_to_none(self, tmp_path, monkeypatch):
        path = self._write_csv(tmp_path)

        def boom(self, unit):
            raise RuntimeError("no size for you")

        monkeypatch.setattr(pl.DataFrame, "estimated_size", boom)
        dataset = dm.HanfordDataset()
        report = dataset.load(path, use_cache=False)
        assert report.estimated_size_mb is None

    def test_cache_hit_with_valid_attributes(self, tmp_path):
        path = self._write_csv(tmp_path)
        dm.HanfordDataset().load(path, use_cache=True)  # writes the cache
        attrs_path = tmp_path / "Tank_attributes.csv"
        attrs_path.write_text("Name,TankType\n241-A-101,SST-4\n241-AN-104,DST\n")

        dataset = dm.HanfordDataset()
        report = dataset.load(path, use_cache=True, attributes_path=attrs_path)
        assert report.cache_used is True
        assert report.attributes_rows == 2
        assert dataset.attrs_df is not None

    def test_cache_hit_with_broken_attributes_logs_warning_and_continues(self, tmp_path):
        path = self._write_csv(tmp_path)
        dm.HanfordDataset().load(path, use_cache=True)  # writes the cache
        bad_attrs = tmp_path / "bad_attrs.csv"
        bad_attrs.write_text("SomeOtherColumn\nvalue\n")

        logs = []
        dataset = dm.HanfordDataset(logger=logs.append)
        report = dataset.load(path, use_cache=True, attributes_path=bad_attrs)
        assert report.cache_used is True
        assert dataset.attrs_df is None
        assert any("could not load tank attributes" in m.lower() for m in logs)

    def test_load_local_default_success_with_attributes(self, tmp_path, monkeypatch):
        self._write_csv(tmp_path)
        (tmp_path / "Tank_attributes.csv").write_text("Name,TankType\n241-A-101,SST-4\n")
        monkeypatch.setattr(dm, "app_base_dir", lambda: tmp_path)
        dataset = dm.HanfordDataset()
        report = dataset.load_local_default()
        assert report.rows == 3
        assert report.attributes_rows == 1

    def test_load_local_default_success_without_attributes(self, tmp_path, monkeypatch):
        # Must also chdir: load_local_default's attribute search falls back
        # to Path.cwd(), which (unpatched) would find this repo's own real
        # Tank_attributes.csv dev-seed file and defeat the "no attrs" case.
        self._write_csv(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(dm, "app_base_dir", lambda: tmp_path)
        dataset = dm.HanfordDataset()
        report = dataset.load_local_default()
        assert report.rows == 3
        assert report.attributes_rows == 0

    def test_load_local_default_missing_raises_friendly_error(self, tmp_path, monkeypatch):
        # app_base_dir() must also be redirected: in dev mode it resolves to
        # this repo's own folder, which has a real Hanford.csv (gitignored
        # dev seed data) — searching only cwd wouldn't exercise this path.
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.setattr(dm, "app_base_dir", lambda: empty_dir)
        dataset = dm.HanfordDataset()
        with pytest.raises(FileNotFoundError, match="Could not find Hanford.csv"):
            dataset.load_local_default()


@requires_real_data
class TestRealData:
    def test_row_and_tank_counts(self):
        dataset = dm.HanfordDataset()
        report = dataset.load(REAL_CSV_PATH, use_cache=False, attributes_path=REAL_ATTRS_PATH)
        assert report.rows == 46894
        assert dataset.df.get_column("WasteSiteId").n_unique() == 177
        assert dataset.df.get_column("Analyte").n_unique() == 193

    def test_combined_isotope_mass_not_dropped(self):
        dataset = dm.HanfordDataset()
        dataset.load(REAL_CSV_PATH, use_cache=False, attributes_path=REAL_ATTRS_PATH)
        pu = dataset.df.filter(pl.col("Analyte") == "239/240Pu")
        assert pu.height > 0
        assert pu["Element"].unique().to_list() == ["Pu"]
