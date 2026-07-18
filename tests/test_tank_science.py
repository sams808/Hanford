import math

import pytest

import tank_science as ts


class TestTankAttributesTable:
    def test_one_row_per_tank_sorted(self, sample_dataset):
        out = ts.tank_attributes_table(sample_dataset)
        assert out["WasteSiteId"].tolist() == ["241-A-101", "241-AN-104"]

    def test_derived_flags(self, sample_dataset):
        out = ts.tank_attributes_table(sample_dataset).set_index("WasteSiteId")
        a101 = out.loc["241-A-101"]
        assert a101["TankSystem"] == "SST"
        assert bool(a101["IsSST"]) is True
        assert bool(a101["IsLeakerOrAssumedLeaker"]) is False
        assert a101["Capacity"] == pytest.approx(1000.0)

        an104 = out.loc["241-AN-104"]
        assert an104["TankSystem"] == "DST"
        assert bool(an104["IsDST"]) is True
        assert bool(an104["IsLeakerOrAssumedLeaker"]) is True
        assert an104["DIL_Gal"] == pytest.approx(0.0)

    def test_empty_when_no_matching_columns(self):
        import data_model as dm
        import polars as pl
        dataset = dm.HanfordDataset()
        dataset.df = pl.DataFrame({"SomeOtherColumn": [1, 2]})
        assert ts.tank_attributes_table(dataset).empty


class TestTankAttributeAudit:
    def test_empty_when_category_missing(self, sample_dataset):
        assert ts.tank_attribute_audit(sample_dataset, "NoSuchColumn").empty

    def test_groups_by_tank_system(self, sample_dataset):
        out = ts.tank_attribute_audit(sample_dataset, "TankSystem").set_index("TankSystem")
        assert out.loc["SST", "N_tanks"] == 1
        assert out.loc["SST", "Total_capacity_kgal"] == pytest.approx(1000.0)
        assert out.loc["SST", "N_leaker_or_assumed"] == 0
        assert out.loc["DST", "N_leaker_or_assumed"] == 1
        assert out.loc["DST", "Total_DIL_gal"] == pytest.approx(0.0)


class TestTankAttributeNumericSummary:
    def test_populated_column_stats(self, sample_dataset):
        out = ts.tank_attribute_numeric_summary(sample_dataset).set_index("column")
        capacity = out.loc["Capacity"]
        assert capacity["n_nonnull"] == 2
        assert capacity["min"] == pytest.approx(1000.0)
        assert capacity["max"] == pytest.approx(1160.0)
        assert capacity["sum"] == pytest.approx(2160.0)

    def test_fully_null_column_reports_nan_sum_not_zero(self, sample_dataset):
        # Distinct from tank_attribute_audit's plain groupby-sum (which
        # would report 0.0 for an all-null column) -- this is ported
        # as-is from the old app's explicit notna().any() guard.
        out = ts.tank_attribute_numeric_summary(sample_dataset).set_index("column")
        diameter = out.loc["Diameter"]
        assert diameter["n_nonnull"] == 0
        assert math.isnan(diameter["sum"])

    def test_empty_when_no_attributes(self):
        import data_model as dm
        import polars as pl
        dataset = dm.HanfordDataset()
        dataset.df = pl.DataFrame({"SomeOtherColumn": [1, 2]})
        assert ts.tank_attribute_numeric_summary(dataset).empty

    def test_skips_columns_absent_from_attributes_table(self):
        # A frame with only WasteSiteId + Capacity (no Diameter/
        # MaxOperatingDepth/OperationCapacityKGal/DIL_Gal at all) must
        # summarize only the column that's actually there.
        import data_model as dm
        import polars as pl
        dataset = dm.HanfordDataset()
        dataset.df = pl.DataFrame({"WasteSiteId": ["241-A-101"], "Capacity": [1000.0]})
        out = ts.tank_attribute_numeric_summary(dataset)
        assert out["column"].tolist() == ["Capacity"]


class TestTankProfile:
    def test_single_tank_kg(self, sample_dataset):
        out = ts.tank_profile(sample_dataset, ["241-A-101"], unit_filter="kg").set_index("Element")
        fe = out.loc["Fe"]
        assert fe["Inventory_sum"] == pytest.approx(60.0)  # duplicate-key sum
        assert fe["Fraction_of_tank_unit_inventory"] == pytest.approx(60.0 / 60.5)
        cd = out.loc["Cd"]
        assert cd["Inventory_sum"] == pytest.approx(0.5)

    def test_sorted_by_inventory_desc_within_tank(self, sample_dataset):
        out = ts.tank_profile(sample_dataset, ["241-A-101"], unit_filter="kg")
        assert out.iloc[0]["Element"] == "Fe"
        assert out.iloc[1]["Element"] == "Cd"

    def test_multi_tank_all_units(self, sample_dataset):
        out = ts.tank_profile(sample_dataset, ["241-A-101", "241-AN-104"])
        # 7 (Units, WasteSiteId, Element) groups across both tanks, matching
        # the same context used in composition_stats (Total Alpha excluded).
        assert len(out) == 7

    def test_empty_when_no_matching_tanks(self, sample_dataset):
        assert ts.tank_profile(sample_dataset, ["241-Z-999"]).empty

    def test_top_n_scales_with_tank_count(self, sample_dataset):
        out = ts.tank_profile(sample_dataset, ["241-A-101", "241-AN-104"], top_n=1)
        # head(top_n * n_tanks) = head(2), not head(1)
        assert len(out) == 2


class TestRawRowsForTank:
    def test_returns_all_rows_for_tank_sorted(self, sample_dataset):
        out = ts.raw_rows_for_tank(sample_dataset, "241-A-101")
        assert len(out) == 6
        assert out.iloc[0]["Units"] == "Ci"
        assert out.iloc[0]["Inventory"] == pytest.approx(100.0)  # 137Cs, largest Ci row

    def test_unit_filter(self, sample_dataset):
        out = ts.raw_rows_for_tank(sample_dataset, "241-A-101", unit_filter="kg")
        assert set(out["Units"]) == {"kg"}
        assert len(out) == 3

    def test_limit(self, sample_dataset):
        out = ts.raw_rows_for_tank(sample_dataset, "241-A-101", limit=2)
        assert len(out) == 2

    def test_no_rows_for_unknown_tank(self, sample_dataset):
        assert ts.raw_rows_for_tank(sample_dataset, "241-Z-999").empty


class TestFarmHelpers:
    def test_available_farms_with_all(self, sample_dataset):
        assert ts.available_farms_with_all(sample_dataset) == ["All", "A", "AN"]

    def test_tanks_in_farm(self, sample_dataset):
        assert ts.tanks_in_farm(sample_dataset, "A") == ["241-A-101"]
        assert ts.tanks_in_farm(sample_dataset, "AN") == ["241-AN-104"]

    def test_tanks_in_all_farms(self, sample_dataset):
        assert ts.tanks_in_farm(sample_dataset, "All") == ["241-A-101", "241-AN-104"]

    def test_tanks_in_none_farm_returns_all(self, sample_dataset):
        assert ts.tanks_in_farm(sample_dataset, None) == ["241-A-101", "241-AN-104"]
