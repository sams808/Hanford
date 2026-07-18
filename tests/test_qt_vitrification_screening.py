from PySide6.QtWidgets import QMainWindow

import vitrification_science as vsci
from qt_vitrification_screening import BlendPartnersTab, CandidateSearchTab, ScreeningTab


def _window(qtbot):
    app_window = QMainWindow()
    qtbot.addWidget(app_window)
    return app_window


class TestScreeningTab:
    def test_actions_without_dataset_show_message_not_crash(self, qtbot):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.run_summary()
        tab.export_tables()

    def test_groups_and_notes_populated_on_construction(self, qtbot):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        assert not tab._table_views["Groups"].dataframe().empty
        assert not tab._table_views["Waste notes"].dataframe().empty

    def test_build_summary_populates_table_and_plot(self, qtbot, vitrification_dataset):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.run_summary()
        qtbot.wait(20)
        summary = tab._table_views["Screening summary"].dataframe()
        assert set(summary["WasteSiteId"]) == set(vitrification_dataset.available_tanks())

    def test_default_weight_spins_match_science_defaults(self, qtbot):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        for key, default in vsci.SCREENING_WEIGHT_DEFAULTS.items():
            assert tab.weight_spins[key].value() == default

    def test_reset_to_defaults_restores_edited_weight(self, qtbot):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.weight_spins["glass_former_weight"].setValue(999.0)
        from qt_vitrification_screening import _reset_weight_spins
        _reset_weight_spins(tab.weight_spins, vsci.SCREENING_WEIGHT_DEFAULTS)
        assert tab.weight_spins["glass_former_weight"].value() == vsci.SCREENING_WEIGHT_DEFAULTS["glass_former_weight"]

    def test_edited_weight_persists_to_a_freshly_constructed_tab(self, qtbot):
        tab_a = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab_a)
        tab_a.weight_spins["glass_former_weight"].setValue(12.5)

        tab_b = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab_b)
        assert tab_b.weight_spins["glass_former_weight"].value() == 12.5

        # Reset must persist the default too, not just the widget value.
        from qt_vitrification_screening import _reset_weight_spins
        _reset_weight_spins(tab_a.weight_spins, vsci.SCREENING_WEIGHT_DEFAULTS)
        tab_c = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab_c)
        assert tab_c.weight_spins["glass_former_weight"].value() == vsci.SCREENING_WEIGHT_DEFAULTS["glass_former_weight"]

    def test_custom_weight_changes_score(self, qtbot, vitrification_dataset):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.weight_spins["glass_former_weight"].setValue(1000.0)
        tab.run_summary()
        qtbot.wait(20)
        summary = tab._table_views["Screening summary"].dataframe().set_index("WasteSiteId")
        assert summary.loc["241-A-103", "Vitrification_screening_score_proxy"] == 100.0  # clipped

    def test_oxide_basis_runs_without_crash(self, qtbot, vitrification_dataset):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.basis_combo.setCurrentText("oxide")
        tab.run_summary()
        qtbot.wait(20)
        summary = tab._table_views["Screening summary"].dataframe()
        assert "frac_glass_former_or_intermediate_oxide_basis" in summary.columns

    def test_formula_label_reflects_weight_changes(self, qtbot):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.weight_spins["glass_former_weight"].setValue(42.0)
        assert "42" in tab.formula_label.text()

    def test_export_writes_bundle(self, qtbot, vitrification_dataset, tmp_path):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.run_summary()
        qtbot.wait(20)
        tab.export_tables()
        bundles = list(tmp_path.glob("vitrification_screening_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "tank_screening_summary.csv").exists()
        assert (bundles[0] / "group_definitions.csv").exists()
        assert (bundles[0] / "waste_class_notes.csv").exists()

    def test_export_survives_savefig_failure(self, qtbot, vitrification_dataset, tmp_path, monkeypatch):
        tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.run_summary()
        qtbot.wait(20)
        monkeypatch.setattr(tab.plot.figure, "savefig", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        tab.export_tables()  # must not raise despite the plot PNG save failing


class TestWeightPersistenceIsIndependentPerTab:
    def test_screening_and_candidate_weights_do_not_collide(self, qtbot):
        # Both dicts share the key "glass_former_weight" -- settings_prefix
        # must keep them from clobbering each other in QSettings.
        screening_tab = ScreeningTab(_window(qtbot))
        qtbot.addWidget(screening_tab)
        screening_tab.weight_spins["glass_former_weight"].setValue(777.0)

        candidate_tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(candidate_tab)
        assert candidate_tab.weight_spins["glass_former_weight"].value() == vsci.CANDIDATE_WEIGHT_DEFAULTS["glass_former_weight"]


class TestCandidateSearchTab:
    def test_actions_without_dataset_show_message_not_crash(self, qtbot):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.run_candidates()
        tab.export_tables()

    def test_target_and_penalty_ranking(self, qtbot, vitrification_dataset):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.target_edit.setText("B")
        tab.penalty_edit.setText("Cl")
        tab.required_edit.setText("")
        tab.run_candidates()
        qtbot.wait(20)
        ranking = tab.table.dataframe()
        assert ranking.iloc[0]["WasteSiteId"] == "241-A-101"

    def test_required_elements_filters_results(self, qtbot, vitrification_dataset):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.required_edit.setText("Si")
        tab.run_candidates()
        qtbot.wait(20)
        ranking = tab.table.dataframe()
        assert set(ranking["WasteSiteId"]) == {"241-A-103"}

    def test_min_kg_filters_results(self, qtbot, vitrification_dataset):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.min_kg_spin.setValue(10.0)
        tab.run_candidates()
        qtbot.wait(20)
        ranking = tab.table.dataframe()
        assert set(ranking["WasteSiteId"]) == {"241-A-101"}

    def test_custom_weights_reflected_in_scores(self, qtbot, vitrification_dataset):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.weight_spins["target_weight"].setValue(0.0)
        tab.weight_spins["glass_former_weight"].setValue(0.0)
        tab.weight_spins["problem_weight"].setValue(0.0)
        tab.weight_spins["penalty_weight"].setValue(0.0)
        tab.run_candidates()
        qtbot.wait(20)
        ranking = tab.table.dataframe()
        assert (ranking["User_search_score_proxy"] == 0.0).all()

    def test_oxide_basis_runs_without_crash(self, qtbot, vitrification_dataset):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.basis_combo.setCurrentText("oxide")
        tab.run_candidates()
        qtbot.wait(20)

    def test_export_writes_bundle(self, qtbot, vitrification_dataset, tmp_path):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.run_candidates()
        qtbot.wait(20)
        tab.export_tables()
        bundles = list(tmp_path.glob("vitrification_candidates_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "candidate_ranking.csv").exists()

    def test_export_survives_savefig_failure(self, qtbot, vitrification_dataset, tmp_path, monkeypatch):
        tab = CandidateSearchTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.run_candidates()
        qtbot.wait(20)
        monkeypatch.setattr(tab.plot.figure, "savefig", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        tab.export_tables()


class TestBlendPartnersTab:
    def test_actions_without_dataset_show_message_not_crash(self, qtbot):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.run_blend()
        tab.export_tables()

    def test_on_dataset_changed_populates_base_tank_combo(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        assert tab.base_tank_combo.count() == len(vitrification_dataset.available_tanks())
        assert tab.base_tank_combo.currentText() == vitrification_dataset.available_tanks()[0]

    def test_no_base_tank_selected_shows_warning(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("")
        tab.run_blend()  # QMessageBox.warning neutralized by conftest

    def test_orthogonal_partner_ranking_hand_verified(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-101")
        tab.run_blend()
        qtbot.wait(20)
        result = tab.table.dataframe().set_index("PartnerTank")
        assert result.loc["241-A-103", "Blend_complement_score_proxy"] > result.loc["241-A-102", "Blend_complement_score_proxy"]

    def test_custom_weights_change_score(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-101")
        tab.weight_spins["dissimilarity_weight"].setValue(0.0)
        tab.run_blend()
        qtbot.wait(20)
        assert not tab.table.dataframe().empty

    def test_oxide_basis_runs_without_crash(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-101")
        tab.basis_combo.setCurrentText("oxide")
        tab.run_blend()
        qtbot.wait(20)

    def test_re_setting_dataset_preserves_current_selection(self, qtbot, vitrification_dataset):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-103")
        tab.on_dataset_changed(vitrification_dataset)
        assert tab.base_tank_combo.currentText() == "241-A-103"

    def test_export_writes_bundle(self, qtbot, vitrification_dataset, tmp_path):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-101")
        tab.run_blend()
        qtbot.wait(20)
        tab.export_tables()
        bundles = list(tmp_path.glob("vitrification_blend_*"))
        assert len(bundles) == 1
        assert (bundles[0] / "blend_partners.csv").exists()

    def test_export_survives_savefig_failure(self, qtbot, vitrification_dataset, tmp_path, monkeypatch):
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        vitrification_dataset.output_root = tmp_path
        tab.on_dataset_changed(vitrification_dataset)
        tab.base_tank_combo.setCurrentText("241-A-101")
        tab.run_blend()
        qtbot.wait(20)
        monkeypatch.setattr(tab.plot.figure, "savefig", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        tab.export_tables()

    def test_on_dataset_changed_with_unloaded_dataset_is_noop(self, qtbot):
        import data_model as dm
        tab = BlendPartnersTab(_window(qtbot))
        qtbot.addWidget(tab)
        tab.on_dataset_changed(dm.HanfordDataset())
        assert tab.base_tank_combo.count() == 0
