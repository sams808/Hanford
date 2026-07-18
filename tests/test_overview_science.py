import pandas as pd
import pytest

import overview_science as ov
from data_model import HanfordDataset


class TestOverview:
    def test_counts(self, sample_dataset):
        out = ov.overview(sample_dataset).iloc[0]
        assert out["rows"] == 9
        assert out["n_tanks"] == 2
        assert out["n_analytes"] == 7  # "137Cs" and "Fe" each repeat once
        assert out["n_primary_elements"] == 6  # Cs, Fe, Pu, Cd, Na, Cm
        assert out["n_waste_phases"] == 3
        assert out["n_waste_types"] == 2
        assert out["n_units"] == 2

    def test_no_report_does_not_crash(self, sample_dataset):
        assert sample_dataset.report is None
        out = ov.overview(sample_dataset)
        assert "source_file" not in out.columns

    def test_report_fields_included_when_present(self, tmp_path):
        path = tmp_path / "Hanford.csv"
        path.write_text(
            "WasteSiteId,Analyte,WastePhase,WasteType,Inventory,Units\n"
            "241-A-101,137Cs,Liquid,T1,100.0,Ci\n"
        )
        dataset = HanfordDataset()
        dataset.load(path, use_cache=False)
        out = ov.overview(dataset).iloc[0]
        assert out["source_file"] == str(path)
        assert not out["cache_used"]  # numpy bool via pandas -- avoid `is False`


class TestUnitsAudit:
    def test_ci_row(self, sample_dataset):
        audit = ov.units_audit(sample_dataset).set_index("Units")
        ci = audit.loc["Ci"]
        assert ci["N_rows"] == 5
        assert ci["N_tanks"] == 2
        assert ci["N_analytes"] == 4
        # polars n_unique() counts null as a distinct value (ported as-is
        # from the old app's units_audit, which never dropped nulls first):
        # Cs, Pu, Cm, and None (from the non-elemental "Total Alpha" row).
        assert ci["N_elements"] == 4
        assert ci["TotalInventory"] == pytest.approx(300.013)

    def test_kg_row(self, sample_dataset):
        audit = ov.units_audit(sample_dataset).set_index("Units")
        kg = audit.loc["kg"]
        assert kg["N_rows"] == 4
        assert kg["N_tanks"] == 2
        assert kg["N_analytes"] == 3
        assert kg["N_elements"] == 3
        assert kg["TotalInventory"] == pytest.approx(560.5)


class TestMissingAudit:
    def test_backfilled_column_is_fully_null(self, sample_dataset):
        audit = ov.missing_audit(sample_dataset).set_index("column")
        assert audit.loc["CCBLog", "n_null"] == 9
        assert audit.loc["CCBLog", "pct_null"] == pytest.approx(100.0)

    def test_required_column_has_no_nulls(self, sample_dataset):
        audit = ov.missing_audit(sample_dataset).set_index("column")
        assert audit.loc["WasteSiteId", "n_null"] == 0


class TestCategoryAudits:
    def test_farm_audit_row_counts(self, sample_dataset):
        audit = ov.farm_audit(sample_dataset).set_index("TankFarm")
        assert audit.loc["A", "N_rows"] == 6
        assert audit.loc["A", "N_tanks"] == 1
        assert audit.loc["AN", "N_rows"] == 3

    def test_phase_audit_has_expected_phases(self, sample_dataset):
        audit = ov.phase_audit(sample_dataset)
        assert set(audit["WastePhase"]) == {"Liquid", "Solid", "Sludge"}

    def test_type_audit_has_expected_types(self, sample_dataset):
        audit = ov.type_audit(sample_dataset)
        assert set(audit["WasteType"]) == {"T1", "T2"}


class TestTopElements:
    def test_kg_ranking_and_duplicate_key_aggregation(self, sample_dataset):
        top = ov.top_elements(sample_dataset, unit="kg", top_n=10).set_index("Element")
        assert top.loc["Na", "TotalInventory"] == pytest.approx(500.0)
        # Fe: 50.0 (Solid) + 10.0 (Liquid) from the duplicate-key rows.
        assert top.loc["Fe", "TotalInventory"] == pytest.approx(60.0)
        assert top.loc["Fe", "N_rows"] == 2
        assert top.loc["Fe", "N_tanks"] == 1

    def test_top_n_limits_rows(self, sample_dataset):
        top = ov.top_elements(sample_dataset, unit="kg", top_n=1)
        assert len(top) == 1
        assert top.iloc[0]["Element"] == "Na"

    def test_excludes_null_element(self, sample_dataset):
        top = ov.top_elements(sample_dataset, unit="Ci", top_n=10)
        assert "Total Alpha" not in top.get("Analyte", []).values.tolist() if "Analyte" in top.columns else True
        assert top["Element"].isna().sum() == 0


class TestTopAnalytes:
    def test_ci_top_analyte_is_cs137_across_both_tanks(self, sample_dataset):
        top = ov.top_analytes(sample_dataset, unit="Ci", top_n=10).set_index("Analyte")
        assert top.loc["137Cs", "TotalInventory"] == pytest.approx(300.0)
        assert top.loc["137Cs", "N_tanks"] == 2
        assert top.loc["137Cs", "N_rows"] == 2

    def test_includes_non_elemental_analyte(self, sample_dataset):
        top = ov.top_analytes(sample_dataset, unit="Ci", top_n=10)
        assert "Total Alpha" in top["Analyte"].values


class TestEnvironmentReport:
    def test_has_expected_fields(self):
        env = ov.environment_report().iloc[0]
        assert env["python_version"]
        assert env["polars_version"]
        assert env["pandas_version"]

    def test_missing_pyarrow_falls_back_gracefully(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "pyarrow", None)  # forces ImportError
        env = ov.environment_report().iloc[0]
        assert env["pyarrow_version"] == "not installed"


class TestExportGlobalDebugBundle:
    def test_writes_expected_files(self, sample_dataset, tmp_path):
        sample_dataset.output_root = tmp_path
        out_dir = ov.export_global_debug_bundle(sample_dataset, extra_info={"app_version": "0.1.0"})
        assert out_dir.exists()
        expected = {
            "overview.csv", "units_audit.csv", "missing_audit.csv", "phase_audit.csv",
            "waste_type_audit.csv", "farm_audit.csv", "top_elements_all.csv",
            "top_analytes_all.csv", "raw_preview.csv", "environment.csv", "manifest.csv",
        }
        assert expected.issubset({p.name for p in out_dir.glob("*.csv")})

    def test_extra_info_merged_into_environment_csv(self, sample_dataset, tmp_path):
        sample_dataset.output_root = tmp_path
        out_dir = ov.export_global_debug_bundle(sample_dataset, extra_info={"app_version": "9.9.9"})
        env = pd.read_csv(out_dir / "environment.csv")
        assert env.iloc[0]["app_version"] == "9.9.9"
