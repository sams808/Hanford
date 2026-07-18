"""
Hand-verifiable expected scores below (see conftest.py's vitrification_dataset
fixture for the exact tank compositions) are computed independently by
hand from those numbers (see comments at each assertion), not by
re-deriving the implementation's own logic.
"""
import math

import polars as pl
import pytest

import data_model as dm
import oxide_science as oxsci
import vitrification_science as vsci


class TestGroupsAndNotes:
    def test_group_definitions_table(self):
        df = vsci.vitrification_group_definitions()
        assert set(df["Group"]) == set(vsci.VITRIFICATION_GROUPS) | {"problem_elements_proxy"}

    def test_waste_class_notes_table(self):
        df = vsci.waste_class_notes()
        assert len(df) == len(vsci.WASTE_CLASS_NOTES)
        assert {"topic", "note"} <= set(df.columns)

    def test_problem_elements_is_union_of_volatile_and_extras(self):
        assert set(vsci.VITRIFICATION_PROBLEM_ELEMENTS) == set(vsci.VITRIFICATION_GROUPS["volatile_halide_sulfate"]) | {"Cr", "Mo", "P", "Ru", "Rh", "Pd", "Ag"}


class TestTankCategorySummary:
    def test_empty_dataset_returns_empty(self):
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame({
            "WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": [],
        }))
        dataset.report = None
        assert vsci.tank_category_summary(dataset).empty

    def test_default_weights_score_hand_computed(self, vitrification_dataset):
        # tank101: frac_former=10/17, frac_mod=5/17, frac_problem=2/17
        # (Cr is a problem element), frac_volatile=0, frac_redox=2/17 (Cr).
        # score = 60*10/17 + 25*5/17 - 45*2/17 - 25*0 - 10*2/17
        out = vsci.tank_category_summary(vitrification_dataset).set_index("WasteSiteId")
        expected = 60 * (10 / 17) + 25 * (5 / 17) - 45 * (2 / 17) - 25 * 0 - 10 * (2 / 17)
        assert out.loc["241-A-101", "Vitrification_screening_score_proxy"] == pytest.approx(expected)

    def test_volatile_only_tank_scores_negative(self, vitrification_dataset):
        # tank102: frac_problem=1.0, frac_volatile=1.0, everything else 0.
        # score = -45*1 - 25*1 = -70.
        out = vsci.tank_category_summary(vitrification_dataset).set_index("WasteSiteId")
        assert out.loc["241-A-102", "Vitrification_screening_score_proxy"] == pytest.approx(-70.0)

    def test_pure_former_tank_scores_sixty(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset).set_index("WasteSiteId")
        assert out.loc["241-A-103", "Vitrification_screening_score_proxy"] == pytest.approx(60.0)

    def test_tank_with_zero_total_kg_scores_zero_not_nan(self, vitrification_dataset):
        # 241-A-104 has only Ci data, no kg rows at all -- every frac_
        # column is NaN (0/NaN) before the fillna(0.0) fix; score must
        # come out as a real number (0.0), not NaN.
        out = vsci.tank_category_summary(vitrification_dataset).set_index("WasteSiteId")
        score = out.loc["241-A-104", "Vitrification_screening_score_proxy"]
        assert not math.isnan(score)
        assert score == pytest.approx(0.0)

    def test_custom_weights_override_defaults(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset, weights={"glass_former_weight": 100.0}).set_index("WasteSiteId")
        assert out.loc["241-A-103", "Vitrification_screening_score_proxy"] == pytest.approx(100.0)

    def test_score_is_clipped_to_100(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset, weights={"glass_former_weight": 1000.0}).set_index("WasteSiteId")
        assert out.loc["241-A-103", "Vitrification_screening_score_proxy"] == pytest.approx(100.0)

    def test_score_is_clipped_to_negative_100(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset, weights={"problem_weight": -1000.0}).set_index("WasteSiteId")
        assert out.loc["241-A-102", "Vitrification_screening_score_proxy"] == pytest.approx(-100.0)

    def test_oxide_basis_differs_from_elemental_basis(self, vitrification_dataset):
        elemental = vsci.tank_category_summary(vitrification_dataset, basis="elemental").set_index("WasteSiteId")
        oxide = vsci.tank_category_summary(vitrification_dataset, basis="oxide").set_index("WasteSiteId")
        assert "frac_glass_former_or_intermediate_oxide_basis" in oxide.columns
        # B/Na/Cr oxidize at different mass-gain factors, so the
        # former-oxide share of tank101's TOTAL oxide mass differs from
        # its elemental-kg former fraction (10/17).
        assert oxide.loc["241-A-101", "frac_glass_former_or_intermediate_oxide_basis"] != pytest.approx(elemental.loc["241-A-101", "frac_glass_former_or_intermediate"])
        assert elemental.loc["241-A-101", "Vitrification_screening_score_proxy"] != pytest.approx(oxide.loc["241-A-101", "Vitrification_screening_score_proxy"])

    def test_important_warning_present(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset)
        assert (out["Important_warning"] == "Screening metric only; not an official waste classification or glass formulation model").all()

    def test_relative_activity_bin_assigned(self, vitrification_dataset):
        out = vsci.tank_category_summary(vitrification_dataset)
        assert out["RelativeActivityBin"].notna().all()

    def test_relative_activity_bin_fallback_with_too_few_tanks(self):
        # qcut with q=4 needs enough distinct values -- a single-tank
        # dataset must fall back to "not enough tanks", not crash.
        rows = {
            "WasteSiteId": ["241-A-101"], "Analyte": ["B"], "WastePhase": ["Liquid"],
            "WasteType": ["T1"], "Inventory": [10.0], "Units": ["kg"],
        }
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
        dataset.report = None
        out = vsci.tank_category_summary(dataset)
        assert (out["RelativeActivityBin"] == "not enough tanks").all()


class TestOxideGlassFormerFractions:
    def test_matches_independent_oxide_science_computation(self, vitrification_dataset):
        fractions = vsci.oxide_glass_former_fractions(vitrification_dataset)
        table = oxsci.convert_composition_to_oxides({"B": 10.0, "Na": 5.0, "Cr": 2.0})
        former_wt_pct = table.loc[table["Component"].isin(oxsci.FORMER_OXIDES), "Wt_pct"].sum()
        assert fractions["241-A-101"] == pytest.approx(former_wt_pct / 100.0)

    def test_tank_with_no_formers_is_zero(self, vitrification_dataset):
        fractions = vsci.oxide_glass_former_fractions(vitrification_dataset)
        assert fractions["241-A-102"] == pytest.approx(0.0)

    def test_tank_with_only_zero_inventory_kg_row_gives_zero_not_crash(self):
        # A tank whose only kg row has Inventory=0.0 (present in the data
        # but not filtered out by this function's own Units=="kg" query,
        # unlike tank_category_summary's Inventory>0 pre-filter) -> every
        # element gets skipped by convert_composition_to_oxides, leaving
        # an empty oxide table for that tank -- must report 0.0, not crash.
        rows = {
            "WasteSiteId": ["241-A-999"], "Analyte": ["Na"], "WastePhase": ["Liquid"],
            "WasteType": ["T1"], "Inventory": [0.0], "Units": ["kg"],
        }
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
        dataset.report = None
        fractions = vsci.oxide_glass_former_fractions(dataset)
        assert fractions["241-A-999"] == pytest.approx(0.0)

    def test_empty_dataset_returns_empty_series(self):
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame({
            "WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": [],
        }))
        dataset.report = None
        assert vsci.oxide_glass_former_fractions(dataset).empty


class TestVitrificationCandidateSearch:
    def test_empty_dataset_returns_empty(self):
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame({
            "WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": [],
        }))
        dataset.report = None
        assert vsci.vitrification_candidate_search(dataset, ["B"], [], []).empty

    def test_target_and_penalty_hand_computed(self, vitrification_dataset):
        # target=[B], penalty=[Cl]: tank101 has B (target hit, no Cl), tank102
        # has Cl (penalty hit, no B). tank101 must outrank tank102.
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=["B"], penalty_elements=["Cl"], required_elements=[],
        ).set_index("WasteSiteId")
        expected_101 = 100.0 * (0.50 * (10 / 17) + 0.25 * (10 / 17) - 0.20 * (2 / 17) - 0.30 * 0.0)
        expected_102 = 100.0 * (0.50 * 0.0 + 0.25 * 0.0 - 0.20 * 1.0 - 0.30 * 1.0)
        assert out.loc["241-A-101", "User_search_score_proxy"] == pytest.approx(expected_101)
        assert out.loc["241-A-102", "User_search_score_proxy"] == pytest.approx(expected_102)
        assert expected_101 > expected_102

    def test_required_elements_filters_out_tanks_missing_them(self, vitrification_dataset):
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=[], penalty_elements=[], required_elements=["Si"],
        )
        assert set(out["WasteSiteId"]) == {"241-A-103"}

    def test_min_total_kg_filters_small_tanks(self, vitrification_dataset):
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=[], penalty_elements=[], required_elements=[], min_total_kg=10.0,
        )
        assert set(out["WasteSiteId"]) == {"241-A-101"}  # only tank with total_kg >= 10 (17)

    def test_top_n_limits_results(self, vitrification_dataset):
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=[], penalty_elements=[], required_elements=[], top_n=1,
        )
        assert len(out) == 1

    def test_custom_weights_change_ranking(self, vitrification_dataset):
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=[], penalty_elements=[], required_elements=[],
            weights={"glass_former_weight": 0.0, "problem_weight": 0.0},
        ).set_index("WasteSiteId")
        # With glass-former and problem terms zeroed out, tank102 (all
        # zeros for target/penalty/former/problem here) scores exactly 0.
        assert out.loc["241-A-102", "User_search_score_proxy"] == pytest.approx(0.0)

    def test_kg_only_dataset_with_no_ci_data_runs_without_crash(self):
        # frac_ci ends up empty (no Ci rows at all) -> rename_frac_cols'
        # empty-frame branch.
        rows = {
            "WasteSiteId": ["241-A-101", "241-A-102"], "Analyte": ["B", "Na"], "WastePhase": ["Liquid"] * 2,
            "WasteType": ["T1"] * 2, "Inventory": [10.0, 5.0], "Units": ["kg", "kg"],
        }
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
        dataset.report = None
        out = vsci.vitrification_candidate_search(dataset, ["B"], [], [])
        assert not out.empty

    def test_oxide_basis_reports_oxide_column(self, vitrification_dataset):
        out = vsci.vitrification_candidate_search(
            vitrification_dataset, target_elements=[], penalty_elements=[], required_elements=[], basis="oxide",
        )
        assert "frac_glass_former_or_intermediate_oxide_basis" in out.columns


class TestBlendPartnerSearch:
    def test_base_tank_not_found_returns_empty(self, vitrification_dataset):
        assert vsci.blend_partner_search(vitrification_dataset, "not-a-tank").empty

    def test_empty_dataset_returns_empty(self):
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame({
            "WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": [],
        }))
        dataset.report = None
        assert vsci.blend_partner_search(dataset, "241-A-101").empty

    def test_orthogonal_partner_similarity_is_zero(self, vitrification_dataset):
        # tank101 (B/Na/Cr) and tank103 (Si only) share no common nonzero
        # element in the kg fraction vector -> cosine similarity exactly 0.
        out = vsci.blend_partner_search(vitrification_dataset, "241-A-101").set_index("PartnerTank")
        assert out.loc["241-A-103", "CosineSimilarity_to_base_fraction_profile"] == pytest.approx(0.0, abs=1e-9)

    def test_complement_scores_hand_computed(self, vitrification_dataset):
        # base=101: gf_base=10/17, prob_base=2/17.
        # partner 103: gf=1.0, prob=0.0, sim=0.
        #   glass_gain=1.0-10/17, problem_reduction=2/17-0=2/17
        #   score = 100*(0.35*glass_gain + 0.35*problem_reduction + 0.20*(1-0) + 0.10*1.0)
        # partner 102: gf=0.0, prob=1.0, sim=0.
        #   glass_gain=0-10/17 (negative -> clipped to 0 by max()),
        #   problem_reduction=2/17-1.0 (negative -> clipped to 0)
        #   score = 100*(0 + 0 + 0.20*(1-0) + 0.10*0) = 20.0
        out = vsci.blend_partner_search(vitrification_dataset, "241-A-101").set_index("PartnerTank")
        gf_base, prob_base = 10 / 17, 2 / 17
        expected_103 = 100.0 * (0.35 * (1.0 - gf_base) + 0.35 * (prob_base - 0.0) + 0.20 * 1.0 + 0.10 * 1.0)
        expected_102 = 100.0 * (0.20 * 1.0)
        assert out.loc["241-A-103", "Blend_complement_score_proxy"] == pytest.approx(expected_103)
        assert out.loc["241-A-102", "Blend_complement_score_proxy"] == pytest.approx(expected_102)
        assert expected_103 > expected_102

    def test_results_sorted_descending_by_complement_score(self, vitrification_dataset):
        out = vsci.blend_partner_search(vitrification_dataset, "241-A-101")
        scores = out["Blend_complement_score_proxy"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_results(self, vitrification_dataset):
        out = vsci.blend_partner_search(vitrification_dataset, "241-A-101", top_n=1)
        assert len(out) == 1

    def test_custom_weights_change_score(self, vitrification_dataset):
        out_default = vsci.blend_partner_search(vitrification_dataset, "241-A-101").set_index("PartnerTank")
        out_custom = vsci.blend_partner_search(
            vitrification_dataset, "241-A-101", weights={"dissimilarity_weight": 0.0},
        ).set_index("PartnerTank")
        assert out_custom.loc["241-A-103", "Blend_complement_score_proxy"] != pytest.approx(out_default.loc["241-A-103", "Blend_complement_score_proxy"])

    def test_oxide_basis_runs_without_crash(self, vitrification_dataset):
        out = vsci.blend_partner_search(vitrification_dataset, "241-A-101", basis="oxide")
        assert not out.empty

    def test_single_tank_dataset_has_no_partners_returns_empty(self):
        rows = {
            "WasteSiteId": ["241-A-101"], "Analyte": ["B"], "WastePhase": ["Liquid"],
            "WasteType": ["T1"], "Inventory": [10.0], "Units": ["kg"],
        }
        dataset = dm.HanfordDataset()
        dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
        dataset.report = None
        out = vsci.blend_partner_search(dataset, "241-A-101")
        assert out.empty
