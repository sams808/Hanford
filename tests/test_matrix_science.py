import math

import numpy as np
import pytest

import matrix_science as ms


class TestLog10Safe:
    def test_positive_values(self):
        out = ms.log10_safe([100.0, 10.0, 1.0])
        assert out.tolist() == pytest.approx([2.0, 1.0, 0.0])

    def test_zero_and_negative_become_nan(self):
        out = ms.log10_safe([0.0, -5.0, 10.0])
        assert math.isnan(out[0])
        assert math.isnan(out[1])
        assert out[2] == pytest.approx(1.0)


class TestTopTanksByInventory:
    def test_ranks_by_total_kg(self, sample_dataset):
        assert ms.top_tanks_by_inventory(sample_dataset, "kg", 1) == ["241-AN-104"]

    def test_max_tanks_limits_result(self, sample_dataset):
        assert len(ms.top_tanks_by_inventory(sample_dataset, "kg", 1)) == 1
        assert len(ms.top_tanks_by_inventory(sample_dataset, "kg", 10)) == 2


class TestMatrixLongWide:
    def test_basic_inventory_mode(self, sample_dataset):
        long_pdf, wide = ms.matrix_long_wide(sample_dataset, unit="kg", top_n_elements=10)
        assert set(long_pdf["Element"]) == {"Na", "Fe", "Cd"}
        assert list(wide.columns) == ["WasteSiteId", "Na", "Fe", "Cd"]  # ordered by total desc
        wide = wide.set_index("WasteSiteId")
        assert wide.loc["241-A-101", "Fe"] == pytest.approx(60.0)  # duplicate-key sum
        assert wide.loc["241-A-101", "Na"] == pytest.approx(0.0)  # fill_value for absent
        assert wide.loc["241-AN-104", "Na"] == pytest.approx(500.0)

    def test_log10_inventory_mode(self, sample_dataset):
        long_pdf, _ = ms.matrix_long_wide(sample_dataset, unit="kg", value_mode="log10_inventory")
        row = long_pdf[long_pdf["Element"] == "Fe"].iloc[0]
        assert row["log10_Inventory_kg"] == pytest.approx(math.log10(60.0))

    def test_fraction_mode_denominator_is_displayed_elements_only(self, sample_dataset):
        # 241-A-101 has Fe=60, Cd=0.5 among the *displayed* top elements --
        # fraction denominator is 60.5, not the tank's true full kg total.
        long_pdf, _ = ms.matrix_long_wide(sample_dataset, unit="kg", value_mode="fraction")
        a101 = long_pdf[long_pdf["WasteSiteId"] == "241-A-101"].set_index("Element")
        assert a101.loc["Fe", "Fraction_kg"] == pytest.approx(60.0 / 60.5)
        assert a101.loc["Cd", "Fraction_kg"] == pytest.approx(0.5 / 60.5)

    def test_min_inventory_filters_elements(self, sample_dataset):
        long_pdf, _ = ms.matrix_long_wide(sample_dataset, unit="kg", min_inventory=1.0)
        assert "Cd" not in set(long_pdf["Element"])  # 0.5 kg excluded

    def test_top_n_elements_limits_columns(self, sample_dataset):
        _, wide = ms.matrix_long_wide(sample_dataset, unit="kg", top_n_elements=1)
        assert list(wide.columns) == ["WasteSiteId", "Na"]

    def test_tank_subset_restricts_rows(self, sample_dataset):
        long_pdf, _ = ms.matrix_long_wide(sample_dataset, unit="kg", tank_subset=["241-A-101"])
        assert set(long_pdf["WasteSiteId"]) == {"241-A-101"}

    def test_empty_when_unit_not_present(self, sample_dataset):
        long_pdf, wide = ms.matrix_long_wide(sample_dataset, unit="XYZ")
        assert long_pdf.empty and wide.empty


class TestElementInventoryMatrix:
    def test_no_elements_or_top_n_uses_all(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", include_all_tanks=False)
        assert set(out.columns) - {"WasteSiteId"} == {"Na", "Fe", "Cd"}

    def test_explicit_elements_filter(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Fe"], include_all_tanks=False)
        assert set(out.columns) - {"WasteSiteId"} == {"Fe"}

    def test_requested_element_absent_from_data_returns_empty(self, sample_dataset):
        # "Au" is a valid symbol but never appears -> filtering leaves zero
        # rows, which must produce an empty frame, not raise.
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Au"])
        assert out.empty

    def test_include_all_tanks_reindexes_and_fills_zero(self, sample_dataset):
        # value_mode="inventory" here specifically to see the raw reindex
        # fill -- the default log10_inventory mode would turn that filled
        # 0.0 into NaN by design (covered separately below).
        out = ms.element_inventory_matrix(
            sample_dataset, unit="kg", elements=["Na"], value_mode="inventory", include_all_tanks=True,
        )
        out = out.set_index("WasteSiteId")
        assert out.loc["241-A-101", "Na"] == pytest.approx(0.0)  # reindexed in, no Na there
        assert out.loc["241-AN-104", "Na"] == pytest.approx(500.0)

    def test_log10_inventory_mode_zero_becomes_nan(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Na"], value_mode="log10_inventory")
        out = out.set_index("WasteSiteId")
        assert math.isnan(out.loc["241-A-101", "Na"])  # 0 kg Na there -> NaN, not -inf
        assert out.loc["241-AN-104", "Na"] == pytest.approx(math.log10(500.0))

    def test_log10_plus1_mode_retains_zero(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Na"], value_mode="log10_plus1")
        out = out.set_index("WasteSiteId")
        assert out.loc["241-A-101", "Na"] == pytest.approx(0.0)  # log10(0+1) = 0

    def test_fraction_mode(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Fe", "Cd"], value_mode="fraction")
        out = out.set_index("WasteSiteId")
        assert out.loc["241-A-101", "Fe"] == pytest.approx(60.0 / 60.5)

    def test_presence_mode(self, sample_dataset):
        out = ms.element_inventory_matrix(sample_dataset, unit="kg", elements=["Na"], value_mode="presence")
        out = out.set_index("WasteSiteId")
        assert out.loc["241-A-101", "Na"] == pytest.approx(0.0)
        assert out.loc["241-AN-104", "Na"] == pytest.approx(1.0)

    def test_unknown_value_mode_raises(self, sample_dataset):
        with pytest.raises(ValueError, match="Unknown value_mode"):
            ms.element_inventory_matrix(sample_dataset, unit="kg", value_mode="bogus")

    def test_empty_when_unit_not_present(self, sample_dataset):
        assert ms.element_inventory_matrix(sample_dataset, unit="XYZ").empty
