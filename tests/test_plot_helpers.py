import pandas as pd
import pytest

import plot_helpers as ph


class FakePanel:
    """Minimal stand-in for qt_widgets.PlotWidget -- exercises plot_helpers'
    contract without needing a real Qt figure/canvas."""

    def __init__(self):
        self.messages = []
        self.ax = _FakeAx()
        self.figure = _FakeFigure()
        self.canvas = _FakeCanvas()

    def show_message(self, message):
        self.messages.append(message)


class _FakeAx:
    def __init__(self):
        self.cleared = False
        self.barh_calls = []
        self.scatter_calls = []
        self.legend_called = False

    def clear(self):
        self.cleared = True

    def barh(self, labels, values, color=None):
        self.barh_calls.append((list(labels), list(values), color))

    def scatter(self, x, y, **kwargs):
        self.scatter_calls.append((list(x), list(y), kwargs))

    def set_xlabel(self, *a, **k): pass
    def set_ylabel(self, *a, **k): pass
    def set_title(self, *a, **k): pass
    def set_xscale(self, *a, **k): pass
    def set_yscale(self, *a, **k): pass
    def grid(self, *a, **k): pass
    def legend(self, *a, **k): self.legend_called = True


class _FakeFigure:
    def tight_layout(self): pass


class _FakeCanvas:
    def __init__(self):
        self.draw_idle_called = False

    def draw_idle(self):
        self.draw_idle_called = True


class TestColorByHighlight:
    def test_no_highlight_returns_base_color(self):
        assert ph.color_by_highlight(["Na", "Cs"], None) == [ph.BASE_COLOR, ph.BASE_COLOR]

    def test_exact_match_highlighted(self):
        colors = ph.color_by_highlight(["Na", "Cs"], "Cs")
        assert colors == [ph.BASE_COLOR, ph.ACCENT_COLOR]

    def test_bracketed_unit_suffix_still_matches(self):
        colors = ph.color_by_highlight(["Cs [Ci]", "Na [kg]"], "Cs", base_labels=["Cs", "Na"])
        assert colors == [ph.ACCENT_COLOR, ph.BASE_COLOR]


class TestMakeUniquePlotLabels:
    def test_single_unit_no_duplication_labels_unchanged(self):
        # Both the base labels AND the unit are non-ambiguous here (only
        # one distinct unit value present) -- no suffix needed at all.
        pdf = pd.DataFrame({"Element": ["Na", "Cs"], "Units": ["kg", "kg"]})
        labels = ph.make_unique_plot_labels(pdf, "Element")
        assert labels.tolist() == ["Na", "Cs"]

    def test_multiple_distinct_units_present_suffixes_everything(self):
        # Even with no colliding label, >1 distinct unit anywhere in the
        # frame triggers unit suffixes on every label (safety margin against
        # accidentally mixing kg/Ci bars that just happen not to collide).
        pdf = pd.DataFrame({"Element": ["Na", "Cs"], "Units": ["kg", "Ci"]})
        labels = ph.make_unique_plot_labels(pdf, "Element")
        assert labels.tolist() == ["Na [kg]", "Cs [Ci]"]

    def test_duplicate_element_across_units_gets_unit_suffix(self):
        pdf = pd.DataFrame({"Element": ["Sr", "Sr"], "Units": ["Ci", "kg"]})
        labels = ph.make_unique_plot_labels(pdf, "Element")
        assert labels.tolist() == ["Sr [Ci]", "Sr [kg]"]

    def test_still_duplicated_after_unit_suffix_gets_disambiguated(self):
        # Same element AND same unit for both rows: the unit suffix alone
        # can't disambiguate, so the fallback appends a WasteSiteId suffix.
        # Only the second-and-later occurrence of a repeated string gets
        # the extra suffix -- the first keeps its (still unique in context)
        # unit-suffixed form. What matters is the final labels are distinct.
        pdf = pd.DataFrame({
            "Element": ["Sr", "Sr"], "Units": ["Ci", "Ci"],
            "WasteSiteId": ["241-A-101", "241-AN-104"],
        })
        labels = ph.make_unique_plot_labels(pdf, "Element")
        assert labels.tolist() == ["Sr [Ci]", "Sr [Ci] (241-AN-104)"]
        assert labels.is_unique


class TestPlotBarh:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_barh(panel, pd.DataFrame({"x": [1]}), "Element", "TotalInventory", "t", "x")
        assert panel.messages == ["No data to plot"]

    def test_empty_dataframe_shows_message(self):
        panel = FakePanel()
        ph.plot_barh(panel, pd.DataFrame({"Element": [], "TotalInventory": []}), "Element", "TotalInventory", "t", "x")
        assert panel.messages == ["No data to plot"]

    def test_all_nonpositive_values_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({"Element": ["Na"], "TotalInventory": [0.0]})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x")
        assert panel.messages == ["No positive values to plot"]

    def test_draws_bars_for_positive_values(self):
        panel = FakePanel()
        df = pd.DataFrame({"Element": ["Na", "Cs", "Fe"], "TotalInventory": [500.0, 300.0, 60.0]})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", highlighted_label="Cs")
        assert panel.ax.cleared
        assert panel.canvas.draw_idle_called
        labels, values, colors = panel.ax.barh_calls[0]
        assert set(labels) == {"Na", "Cs", "Fe"}
        assert colors[labels.index("Cs")] == ph.ACCENT_COLOR

    def test_top_n_limits_bars(self):
        panel = FakePanel()
        df = pd.DataFrame({"Element": [f"E{i}" for i in range(10)], "TotalInventory": list(range(10, 0, -1))})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", top_n=3)
        labels, _, _ = panel.ax.barh_calls[0]
        assert len(labels) == 3

    def test_log_x_does_not_raise(self):
        panel = FakePanel()
        df = pd.DataFrame({"Element": ["Na"], "TotalInventory": [500.0]})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", log_x=True)
        assert panel.canvas.draw_idle_called


class TestPlotTargetVsTotal:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_target_vs_total(panel, pd.DataFrame({"x": [1]}), "t")
        assert panel.messages == ["No target-vs-total data to plot"]

    def test_no_positive_pairs_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({
            "Context_TotalInventory_same_unit": [0.0], "Target_Inventory_sum": [0.0], "Units": ["Ci"],
        })
        ph.plot_target_vs_total(panel, df, "t")
        assert panel.messages == ["No positive values to plot"]

    def test_scatters_by_unit(self):
        panel = FakePanel()
        df = pd.DataFrame({
            "Context_TotalInventory_same_unit": [100.0, 50.0],
            "Target_Inventory_sum": [10.0, 5.0],
            "Units": ["Ci", "kg"],
        })
        ph.plot_target_vs_total(panel, df, "t")
        assert len(panel.ax.scatter_calls) == 2
        assert panel.ax.legend_called
        assert panel.canvas.draw_idle_called
