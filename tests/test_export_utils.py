import pandas as pd

import export_utils as eu


class TestSafeName:
    def test_replaces_unsafe_characters(self):
        assert eu.safe_name("Se / Total Alpha?") == "Se_Total_Alpha"

    def test_none_becomes_na(self):
        assert eu.safe_name(None) == "NA"

    def test_truncates_to_max_len(self):
        assert len(eu.safe_name("x" * 200, max_len=10)) == 10


class TestExportNamedTables:
    def test_writes_csv_per_table_and_manifest(self, sample_dataset, tmp_path):
        sample_dataset.output_root = tmp_path
        tables = {
            "overview": pd.DataFrame({"a": [1, 2]}),
            "empty_skipped": None,
            "co_elements": pd.DataFrame({"b": [1, 2, 3]}),
        }
        out_dir = eu.export_named_tables(sample_dataset, "search_Cs", tables)
        assert (out_dir / "overview.csv").exists()
        assert (out_dir / "co_elements.csv").exists()
        assert not (out_dir / "empty_skipped.csv").exists()
        manifest = pd.read_csv(out_dir / "manifest.csv")
        assert set(manifest["file"]) == {"overview.csv", "co_elements.csv"}
        assert int(manifest.loc[manifest["file"] == "co_elements.csv", "rows"].iloc[0]) == 3

    def test_folder_name_uses_safe_prefix(self, sample_dataset, tmp_path):
        sample_dataset.output_root = tmp_path
        out_dir = eu.export_named_tables(sample_dataset, "search Se/Total", {"t": pd.DataFrame({"a": [1]})})
        assert out_dir.name.startswith("search_Se_Total_")
