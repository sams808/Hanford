import numpy as np
import pandas as pd

from qt_widgets import DataFrameTableModel, PlotWidget, StatusLogger, _format_cell
from PySide6.QtCore import Qt


class TestPlotWidgetSetFigureSizeInches:
    """Figure.set_size_inches(..., forward=True) is a documented no-op for
    a canvas embedded directly (not via pyplot) -- this codebase's canvases
    all have canvas.manager is None, so forward=True never actually resizes
    anything on screen. set_figure_size_inches() is the real fix: it must
    resize the canvas widget itself, not just the Figure's internal bbox."""

    def test_grows_canvas_pixel_size_to_match_figure_inches(self, qtbot):
        panel = PlotWidget(figsize=(6.0, 4.5), dpi=100)
        qtbot.addWidget(panel)
        start_height = panel.canvas.height()

        panel.set_figure_size_inches(6.0, 12.0)

        assert panel.canvas.height() > start_height
        assert panel.canvas.get_width_height() == (
            int(panel.figure.bbox.width), int(panel.figure.bbox.height),
        )

    def test_figure_bbox_inches_updated(self, qtbot):
        panel = PlotWidget(figsize=(6.0, 4.5), dpi=100)
        qtbot.addWidget(panel)
        panel.set_figure_size_inches(7.0, 9.0)
        assert tuple(panel.figure.get_size_inches()) == (7.0, 9.0)


class TestPlotWidgetAvailableContentHeightInches:
    """A figure grown taller than the panel doesn't scroll into view --
    there's no scroll area around the canvas -- it just clips silently.
    Callers that grow figure height based on data size need to know how
    much is actually visible so they can cap at that instead."""

    def test_none_when_not_shown(self, qtbot):
        # qtbot.addWidget() alone doesn't show the widget, so height()
        # would just be a Qt placeholder default, not real available space.
        panel = PlotWidget()
        qtbot.addWidget(panel)
        assert panel.available_content_height_inches() is None

    def test_positive_value_when_shown(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.resize(800, 1000)
        panel.show()
        qtbot.waitExposed(panel)
        qtbot.wait(20)  # let any deferred draw_idle from show()/resize() flush
        try:
            available = panel.available_content_height_inches()
            assert available is not None
            assert 0 < available < 1000 / panel.figure.dpi
        finally:
            panel.hide()
            qtbot.wait(20)  # settle before qtbot's teardown deletes the widget


class TestPlotWidgetCapturePng:
    def test_returns_valid_png_bytes(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.ax.plot([1, 2, 3], [1, 4, 9])
        data = panel.capture_png()
        assert isinstance(data, bytes)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    def test_dpi_affects_output_size(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.ax.plot([1, 2, 3], [1, 4, 9])
        low = panel.capture_png(dpi=50)
        high = panel.capture_png(dpi=300)
        assert len(high) > len(low)


class TestPlotWidgetSuggestedCaption:
    def test_uses_axes_title_when_no_suptitle(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.ax.set_title("My plot title")
        assert panel.suggested_caption() == "My plot title"

    def test_uses_suptitle_when_present(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.ax.set_title("axes title")
        panel.figure.suptitle("figure suptitle")
        assert panel.suggested_caption() == "figure suptitle"

    def test_empty_string_when_no_title_at_all(self, qtbot):
        panel = PlotWidget()
        qtbot.addWidget(panel)
        assert panel.suggested_caption() == ""


class TestPlotWidgetSendToComposer:
    def test_adds_current_figure_to_the_shared_store(self, qtbot):
        from composer_store import store
        store.clear()
        panel = PlotWidget()
        qtbot.addWidget(panel)
        panel.ax.set_title("Sent from a test")
        panel.ax.plot([1, 2], [3, 4])

        panel._send_to_composer()

        items = store.items()
        assert len(items) == 1
        assert items[0].caption == "Sent from a test"
        assert items[0].png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        store.clear()


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

    def test_numpy_array_joined(self):
        # Polars list-columns arrive here as numpy object arrays (not
        # Python lists) once a DataFrame has gone through .to_pandas() --
        # pd.isna() on one of those returns an array, not a bool, so this
        # must be handled before the scalar-isna fallback branch.
        assert _format_cell(np.array(["Cs", "Sr"], dtype=object)) == "Cs; Sr"

    def test_empty_numpy_array(self):
        assert _format_cell(np.array([], dtype=object)) == ""

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
