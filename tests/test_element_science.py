import pytest

import element_science as es


class TestTargetRowsAndTanks:
    def test_target_rows_element_mode(self, sample_dataset):
        target, mode, symbol = es.target_rows(sample_dataset, "Cs")
        assert mode == "element"
        assert symbol == "Cs"
        assert target.height == 2

    def test_target_tanks_sorted(self, sample_dataset):
        assert es.target_tanks(sample_dataset, "Cs") == ["241-A-101", "241-AN-104"]

    def test_target_rows_min_inventory_filters(self, sample_dataset):
        # Pu's only row is 0.002 Ci -- a min_inventory above that excludes it.
        target, _, _ = es.target_rows(sample_dataset, "Pu", min_inventory=0.01)
        assert target.height == 0

    def test_target_rows_analyte_contains_no_symbol(self, sample_dataset):
        target, mode, symbol = es.target_rows(sample_dataset, "Alpha")
        assert mode == "analyte_contains"
        assert symbol is None
        assert target.height == 1


class TestTargetByTankUnit:
    def test_empty_query_result_returns_empty_frame(self, sample_dataset):
        # A valid element with zero matching rows once min_inventory excludes it all.
        out = es.target_by_tank_unit(sample_dataset, "Pu", min_inventory=1.0)
        assert out.empty

    def test_ranks_tanks_by_target_inventory_desc(self, sample_dataset):
        out = es.target_by_tank_unit(sample_dataset, "Cs")
        assert len(out) == 2
        assert out.iloc[0]["WasteSiteId"] == "241-AN-104"
        assert out.iloc[0]["Target_Inventory_sum"] == pytest.approx(200.0)
        assert out.iloc[1]["WasteSiteId"] == "241-A-101"
        assert out.iloc[1]["Target_Inventory_sum"] == pytest.approx(100.0)

    def test_fraction_denominator_is_true_tank_total_not_displayed_rows(self, sample_dataset):
        out = es.target_by_tank_unit(sample_dataset, "Cs").set_index("WasteSiteId")
        # 241-A-101's true Ci total across ALL analytes is 100 + 0.002 + 0.01
        # = 100.012 (Cs + Pu + Total Alpha), not just the 100 Cs itself.
        row = out.loc["241-A-101"]
        assert row["Context_TotalInventory_same_unit"] == pytest.approx(100.012)
        assert row["TargetFractionOfTankUnitInventory"] == pytest.approx(100.0 / 100.012)

    def test_query_and_mode_columns_present(self, sample_dataset):
        out = es.target_by_tank_unit(sample_dataset, "Cs")
        assert (out["Query"] == "Cs").all()
        assert (out["ResolvedMode"] == "element").all()
        assert (out["HighlightedElement"] == "Cs").all()

    def test_no_highlighted_column_when_no_symbol(self, sample_dataset):
        out = es.target_by_tank_unit(sample_dataset, "Alpha")
        assert "HighlightedElement" not in out.columns


class TestTargetByPhaseAndType:
    def test_target_by_phase_empty(self, sample_dataset):
        assert es.target_by_phase(sample_dataset, "Pu", min_inventory=1.0).empty

    def test_target_by_phase_groups_correctly(self, sample_dataset):
        out = es.target_by_phase(sample_dataset, "Cs").set_index("WastePhase")
        assert out.loc["Liquid", "Target_Inventory_sum"] == pytest.approx(100.0)
        assert out.loc["Sludge", "Target_Inventory_sum"] == pytest.approx(200.0)

    def test_target_by_type_empty(self, sample_dataset):
        assert es.target_by_type(sample_dataset, "Pu", min_inventory=1.0).empty

    def test_target_by_type_groups_correctly(self, sample_dataset):
        out = es.target_by_type(sample_dataset, "Cs").set_index("WasteType")
        assert out.loc["T1", "Target_Inventory_sum"] == pytest.approx(100.0)
        assert out.loc["T2", "Target_Inventory_sum"] == pytest.approx(200.0)


class TestCoElements:
    def test_empty_when_target_min_inventory_excludes_all(self, sample_dataset):
        assert es.co_elements(sample_dataset, "Pu", min_target_inventory=1.0).empty

    def test_empty_when_context_min_inventory_excludes_everything(self, sample_dataset):
        # Target itself is found (Cs, 100/200 Ci), but a context threshold
        # above every row's inventory (max in the fixture is 500) empties
        # the context even though the target match was non-empty.
        assert es.co_elements(sample_dataset, "Cs", min_context_inventory=10_000.0).empty

    def test_co_elements_presence_and_totals(self, sample_dataset):
        out = es.co_elements(sample_dataset, "Cs").set_index(["Units", "Element"])
        cs_row = out.loc[("Ci", "Cs")]
        assert cs_row["N_tanks_present"] == 2
        assert cs_row["N_target_tanks_total"] == 2
        assert cs_row["PresenceFraction_pct"] == pytest.approx(100.0)
        assert cs_row["Total_inventory_in_target_tanks"] == pytest.approx(300.0)
        assert bool(cs_row["IsHighlighted"]) is True

        fe_row = out.loc[("kg", "Fe")]
        assert fe_row["N_tanks_present"] == 1  # only present in 241-A-101
        assert fe_row["Total_inventory_in_target_tanks"] == pytest.approx(60.0)  # duplicate-key sum
        assert fe_row["PresenceFraction_pct"] == pytest.approx(50.0)
        assert bool(fe_row["IsHighlighted"]) is False

    def test_total_alpha_excluded_no_element(self, sample_dataset):
        out = es.co_elements(sample_dataset, "Cs")
        assert out["Element"].isna().sum() == 0

    def test_no_symbol_all_unhighlighted(self, sample_dataset):
        out = es.co_elements(sample_dataset, "Alpha")
        assert not out["IsHighlighted"].any()


class TestCoAnalytes:
    def test_empty_when_target_excluded(self, sample_dataset):
        assert es.co_analytes(sample_dataset, "Pu", min_target_inventory=1.0).empty

    def test_empty_when_context_min_inventory_excludes_everything(self, sample_dataset):
        assert es.co_analytes(sample_dataset, "Cs", min_context_inventory=10_000.0).empty

    def test_highlight_matches_element_list_substring(self, sample_dataset):
        out = es.co_analytes(sample_dataset, "Cs").set_index("Analyte")
        assert bool(out.loc["137Cs", "IsHighlighted"]) is True
        assert bool(out.loc["Fe", "IsHighlighted"]) is False

    def test_presence_counts(self, sample_dataset):
        out = es.co_analytes(sample_dataset, "Cs").set_index("Analyte")
        assert out.loc["137Cs", "N_tanks_present"] == 2
        assert out.loc["Na", "N_tanks_present"] == 1

    def test_no_symbol_all_unhighlighted(self, sample_dataset):
        out = es.co_analytes(sample_dataset, "Alpha")
        assert not out["IsHighlighted"].any()


class TestCompositionStats:
    def test_empty_when_target_excluded(self, sample_dataset):
        abs_pdf, frac_pdf, tank_pdf = es.composition_stats(sample_dataset, "Pu", min_target_inventory=1.0)
        assert abs_pdf.empty and frac_pdf.empty and tank_pdf.empty

    def test_empty_when_context_min_inventory_excludes_everything(self, sample_dataset):
        abs_pdf, frac_pdf, tank_pdf = es.composition_stats(sample_dataset, "Cs", min_context_inventory=10_000.0)
        assert abs_pdf.empty and frac_pdf.empty and tank_pdf.empty

    def test_zero_filled_mean_dilutes_absent_tanks(self, sample_dataset):
        # Cs is present in BOTH target tanks (100, 200) -> zero-filled mean
        # equals the present-only mean. Pu is present in only ONE of the two
        # target tanks (0.002) -> the zero-filled mean must be half its
        # present-only mean, since it's averaged over both target tanks
        # including the one where it's absent.
        abs_pdf, _, _ = es.composition_stats(sample_dataset, "Cs")
        abs_pdf = abs_pdf.set_index(["Units", "Element"])
        cs = abs_pdf.loc[("Ci", "Cs")]
        assert cs["Mean_inventory_present_tanks_only"] == pytest.approx(150.0)
        assert cs["Mean_inventory_all_target_tanks_zero_filled"] == pytest.approx(150.0)

        pu = abs_pdf.loc[("Ci", "Pu")]
        assert pu["Mean_inventory_present_tanks_only"] == pytest.approx(0.002)
        assert pu["Mean_inventory_all_target_tanks_zero_filled"] == pytest.approx(0.001)
        assert pu["Mean_inventory_all_target_tanks_zero_filled"] == pytest.approx(
            pu["Mean_inventory_present_tanks_only"] / 2
        )

    def test_fraction_stats_use_compositional_fraction(self, sample_dataset):
        _, frac_pdf, _ = es.composition_stats(sample_dataset, "Cs")
        frac_pdf = frac_pdf.set_index(["Units", "Element"])
        na = frac_pdf.loc[("kg", "Na")]
        # Na is 100% of tank 241-AN-104's kg total (its only kg analyte),
        # 0% of 241-A-101's (absent there) -- present-tanks-only mean is 1.0.
        assert na["Mean_fraction_present_tanks_only"] == pytest.approx(1.0)
        assert na["Mean_fraction_all_target_tanks_zero_filled"] == pytest.approx(0.5)

    def test_tank_level_table_row_count_and_highlight(self, sample_dataset):
        _, _, tank_pdf = es.composition_stats(sample_dataset, "Cs")
        # 7 (Units, WasteSiteId, Element) groups in the 8-row context
        # (Fe's duplicate-key rows collapse into one group).
        assert len(tank_pdf) == 7
        highlighted = tank_pdf[tank_pdf["IsHighlighted"]]
        assert set(highlighted["Element"]) == {"Cs"}

    def test_no_symbol_all_unhighlighted(self, sample_dataset):
        abs_pdf, frac_pdf, tank_pdf = es.composition_stats(sample_dataset, "Alpha")
        assert not abs_pdf["IsHighlighted"].any()
        assert not frac_pdf["IsHighlighted"].any()
        assert not tank_pdf["IsHighlighted"].any()
