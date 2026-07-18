import numpy as np
import pandas as pd

from qt_widgets import DataFrameTableModel, StatusLogger, _format_cell
from PySide6.QtCore import Qt


class TestFormatCell:
    def test_none(self):
        assert _format_cell(None) == ""

    def test_nan_float(self):
        assert _format_cell(float("nan")) == ""

    def test_float_uses_5_sig_figs(self):
        assert _format_cell(1234567.891) == "1.2346e+06"

    def test_small_float(self):
        assert _format_cell(0.00012345) == "0.00012345"

    def test_list_joined(self):
        assert _format_cell(["A", "B", "C"]) == "A; B; C"

    def test_plain_string(self):
        assert _format_cell("Cs") == "Cs"

    def test_int(self):
        assert _format_cell(42) == "42"


class TestDataFrameTableModel:
    def _sample_df(self) -> pd.DataFrame:
        return pd.DataFrame({"Element": ["Na", "Fe", "Cs"], "TotalInventory": [500.0, 60.0, 300.0]})

    def test_row_and_column_count(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        assert model.rowCount() == 3
        assert model.columnCount() == 2

    def test_empty_model(self, qtbot):
        model = DataFrameTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 0

    def test_data_display_role(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        index = model.index(1, 0)
        assert model.data(index, Qt.DisplayRole) == "Fe"

    def test_data_invalid_role_returns_none(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        index = model.index(0, 0)
        assert model.data(index, Qt.BackgroundRole) is None

    def test_header_data(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        assert model.headerData(0, Qt.Horizontal) == "Element"
        assert model.headerData(1, Qt.Vertical) == "1"

    def test_set_dataframe_resets_model(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        model.set_dataframe(pd.DataFrame({"X": [1, 2]}))
        assert model.rowCount() == 2
        assert model.columnCount() == 1

    def test_sort_ascending(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        model.sort(1, Qt.AscendingOrder)  # sort by TotalInventory
        assert model.dataframe()["Element"].tolist() == ["Fe", "Cs", "Na"]

    def test_sort_descending(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        model.sort(1, Qt.DescendingOrder)
        assert model.dataframe()["Element"].tolist() == ["Na", "Cs", "Fe"]

    def test_sort_on_empty_dataframe_is_a_noop(self, qtbot):
        model = DataFrameTableModel()
        model.sort(0)  # must not raise
        assert model.rowCount() == 0

    def test_sort_out_of_range_column_is_a_noop(self, qtbot):
        model = DataFrameTableModel(self._sample_df())
        model.sort(5)
        assert model.dataframe()["Element"].tolist() == ["Na", "Fe", "Cs"]


class TestStatusLogger:
    def test_log_appends_timestamped_line(self, qtbot):
        logger = StatusLogger()
        logger.log("hello")
        assert logger.full_text().endswith("hello")
        assert logger.full_text().startswith("[")

    def test_logged_signal_emits(self, qtbot):
        logger = StatusLogger()
        with qtbot.waitSignal(logger.logged, timeout=1000) as blocker:
            logger.log("world")
        assert "world" in blocker.args[0]

    def test_clear(self, qtbot):
        logger = StatusLogger()
        logger.log("a")
        logger.clear()
        assert logger.full_text() == ""
