import numpy as np
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

    def barh(self, labels, values, color=None, **kwargs):
        self.barh_calls.append((list(labels), list(values), color))

    def axvline(self, *a, **k): pass
    def set_xlim(self, *a, **k): pass

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

    def test_draws_bars_for_positive_values(self, qtbot):
        # set_size_inches() needs a real Figure, not the FakePanel stand-in
        # used for the early-return checks above (same reasoning as
        # TestPlotHeatmap.test_renders_with_real_plot_widget).
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({"Element": ["Na", "Cs", "Fe"], "TotalInventory": [500.0, 300.0, 60.0]})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", highlighted_label="Cs")
        qtbot.wait(20)
        labels = [t.get_text() for t in panel.ax.get_yticklabels()]
        assert set(labels) == {"Na", "Cs", "Fe"}

    def test_top_n_limits_bars(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({"Element": [f"E{i}" for i in range(10)], "TotalInventory": list(range(10, 0, -1))})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", top_n=3)
        qtbot.wait(20)
        assert len(panel.ax.get_yticklabels()) == 3

    def test_more_bars_grows_figure_height(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        small = pd.DataFrame({"Element": ["Na", "Cs"], "TotalInventory": [500.0, 300.0]})
        ph.plot_barh(panel, small, "Element", "TotalInventory", "t", "x")
        qtbot.wait(20)
        small_height = panel.figure.get_size_inches()[1]

        many = pd.DataFrame({"Element": [f"E{i}" for i in range(40)], "TotalInventory": list(range(40, 0, -1))})
        ph.plot_barh(panel, many, "Element", "TotalInventory", "t", "x", top_n=40)
        qtbot.wait(20)
        large_height = panel.figure.get_size_inches()[1]
        assert large_height > small_height

    def test_log_x_does_not_raise(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({"Element": ["Na"], "TotalInventory": [500.0]})
        ph.plot_barh(panel, df, "Element", "TotalInventory", "t", "x", log_x=True)
        qtbot.wait(20)
        assert panel.ax.get_xscale() == "log"


class TestPlotCorrelationScan:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_correlation_scan(panel, pd.DataFrame({"x": [1]}), "Cs")
        assert panel.messages == ["No correlation scan data"]

    def test_all_nan_correlation_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({"PartnerElement": ["Sr"], "Correlation_r": [float("nan")], "AbsCorrelation": [float("nan")]})
        ph.plot_correlation_scan(panel, df, "Cs")
        assert panel.messages == ["No valid correlations"]

    def test_draws_diverging_bars(self):
        panel = FakePanel()
        df = pd.DataFrame({
            "PartnerElement": ["Sr", "Mo"], "Correlation_r": [0.9, -0.8], "AbsCorrelation": [0.9, 0.8],
            "N_overlap_nonzero_tanks": [5, 5], "Units": ["kg", "kg"], "Metric": ["inventory", "inventory"],
        })
        ph.plot_correlation_scan(panel, df, "Cs")
        assert panel.ax.cleared
        assert panel.canvas.draw_idle_called
        _, _, colors = panel.ax.barh_calls[0]
        assert "tab:blue" in colors and "tab:red" in colors


class TestCorrelationSquareFromDataframe:
    def test_empty_when_no_element_column(self):
        data, elements = ph._correlation_square_from_dataframe(pd.DataFrame({"x": [1]}))
        assert data.empty and elements == []

    def test_extracts_square_matrix(self):
        corr = pd.DataFrame({"Element": ["Cs", "Sr"], "Cs": [1.0, 0.9], "Sr": [0.9, 1.0]})
        data, elements = ph._correlation_square_from_dataframe(corr)
        assert elements == ["Cs", "Sr"]
        assert data.loc["Cs", "Sr"] == pytest.approx(0.9)


class TestAlignedProjectionValues:
    def test_no_totals_returns_zeros(self):
        out = ph._aligned_projection_values(["Cs", "Sr"], None)
        assert out.tolist() == [0.0, 0.0]

    def test_maps_totals_by_element(self):
        out = ph._aligned_projection_values(["Cs", "Sr"], {"Cs": 100.0, "Sr": 50.0})
        assert out.tolist() == [100.0, 50.0]


class TestPlotCorrelationHeatmap:
    def _square_corr(self, n=4):
        elements = [f"E{i}" for i in range(n)]
        data = pd.DataFrame(np.eye(n), index=elements, columns=elements)
        data = data.reset_index().rename(columns={"index": "Element"})
        return data

    def test_empty_correlation_shows_message(self):
        panel = FakePanel()
        ph.plot_correlation_heatmap(panel, pd.DataFrame({"x": [1]}))
        assert panel.messages == ["No correlation matrix"]

    def test_matplotlib_style_renders(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        ph.plot_correlation_heatmap(panel, self._square_corr(), style="Matplotlib lower triangle")
        qtbot.wait(20)
        assert panel.ax.get_title() == "Element correlation heatmap"

    def test_matplotlib_style_with_annotation(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        ph.plot_correlation_heatmap(panel, self._square_corr(n=3), style="Matplotlib lower triangle", annotate=True)
        qtbot.wait(20)

    def test_seaborn_style_renders(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        ph.plot_correlation_heatmap(panel, self._square_corr(), style="Seaborn lower triangle")
        qtbot.wait(20)

    def test_seaborn_with_projections_renders(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        totals = {"E0": 100.0, "E1": 50.0, "E2": 10.0, "E3": 5.0}
        ph.plot_correlation_heatmap(
            panel, self._square_corr(), style="Seaborn + total projections", totals=totals, unit="kg",
        )
        qtbot.wait(20)

    def test_seaborn_unavailable_falls_back_to_matplotlib(self, qtbot, monkeypatch):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        monkeypatch.setattr(ph, "sns", None)
        ph.plot_correlation_heatmap(panel, self._square_corr(), style="Seaborn lower triangle")
        qtbot.wait(20)
        assert "seaborn not installed" in panel.ax.get_title()


class TestSeabornAvailable:
    def test_reflects_import_state(self):
        assert ph.seaborn_available() in (True, False)


class TestPlotPairScatter:
    def test_missing_or_too_few_elements_shows_message(self):
        panel = FakePanel()
        ph.plot_pair_scatter(panel, pd.DataFrame({"WasteSiteId": ["T1"], "Cs": [1.0]}), ["Cs"], "kg", "inventory")
        assert panel.messages == ["Need at least two selected elements with data"]

    def test_two_element_scatter(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        matrix = pd.DataFrame({"WasteSiteId": ["T1", "T2", "T3"], "Cs": [1.0, 2.0, 3.0], "Sr": [2.0, 4.0, 6.0]})
        ph.plot_pair_scatter(panel, matrix, ["Cs", "Sr"], "kg", "inventory")
        qtbot.wait(20)
        assert "r = 1.000" in panel.ax.get_title()

    def test_three_element_scatter_uses_colorbar(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        matrix = pd.DataFrame({
            "WasteSiteId": ["T1", "T2", "T3"], "Cs": [1.0, 2.0, 3.0],
            "Sr": [2.0, 4.0, 6.0], "Mo": [5.0, 3.0, 1.0],
        })
        ph.plot_pair_scatter(panel, matrix, ["Cs", "Sr", "Mo"], "kg", "inventory")
        qtbot.wait(20)
        assert "colored by Mo" in panel.ax.get_title()


class TestPlotHeatmap:
    def test_missing_wastesiteid_column_shows_message(self):
        panel = FakePanel()
        ph.plot_heatmap(panel, pd.DataFrame({"x": [1]}), "kg", "inventory", "t")
        assert panel.messages == ["No heatmap data"]

    def test_empty_dataframe_shows_message(self):
        panel = FakePanel()
        ph.plot_heatmap(panel, pd.DataFrame({"WasteSiteId": []}), "kg", "inventory", "t")
        assert panel.messages == ["No heatmap data"]

    def test_renders_with_real_plot_widget(self, qtbot):
        # figure.clear()/add_subplot()/colorbar() need a real Figure, not
        # the FakePanel stand-in used for the early-return checks above.
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        wide = pd.DataFrame({"WasteSiteId": ["241-A-101", "241-AN-104"], "Na": [0.0, 500.0], "Fe": [60.0, 0.0]})
        ph.plot_heatmap(panel, wide, "kg", "log10_inventory", "t")
        qtbot.wait(20)
        assert panel.ax.get_title() == "t"
        assert [t.get_text() for t in panel.ax.get_xticklabels()] == ["Na", "Fe"]

    def test_fraction_mode_renders(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        wide = pd.DataFrame({"WasteSiteId": ["241-A-101"], "Na": [500.0], "Fe": [60.0]})
        ph.plot_heatmap(panel, wide, "kg", "fraction", "t")
        qtbot.wait(20)

    def test_many_tanks_thins_y_labels(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        wide = pd.DataFrame({"WasteSiteId": [f"T{i}" for i in range(90)], "Na": list(range(90))})
        ph.plot_heatmap(panel, wide, "kg", "inventory", "t")
        qtbot.wait(20)
        assert len(panel.ax.get_yticklabels()) < 90


class TestPlotGroupedTankProfile:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_grouped_tank_profile(panel, pd.DataFrame({"x": [1]}), "Inventory_sum", "t")
        assert panel.messages == ["No tank profile data"]

    def test_all_nonpositive_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({"Element": ["Na"], "Inventory_sum": [0.0], "WasteSiteId": ["241-A-101"]})
        ph.plot_grouped_tank_profile(panel, df, "Inventory_sum", "t")
        assert panel.messages == ["No positive data to plot"]

    def test_draws_one_series_per_tank(self, qtbot):
        # pandas' DataFrame.plot(kind="barh", ax=...) needs a real Axes
        # (spines/transforms/containers) that FakeAx can't stand in for --
        # use the real PlotWidget here instead.
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({
            "Element": ["Na", "Fe", "Na", "Fe"],
            "Inventory_sum": [500.0, 60.0, 300.0, 40.0],
            "WasteSiteId": ["241-A-101", "241-A-101", "241-AN-104", "241-AN-104"],
            "Units": ["kg", "kg", "kg", "kg"],
        })
        ph.plot_grouped_tank_profile(panel, df, "Inventory_sum", "t")
        qtbot.wait(20)
        assert len(panel.ax.get_legend().get_texts()) == 2  # one series per tank


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


class TestPlotVitrificationBurden:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_vitrification_burden(panel, pd.DataFrame({"x": [1]}))
        assert panel.messages == ["No vitrification screening data"]

    def test_no_positive_inventory_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({
            "WasteSiteId": ["T1"], "Total_kg_inventory": [0.0], "Total_Ci_inventory": [0.0],
            "frac_problem_elements_proxy": [0.0], "frac_glass_former_or_intermediate": [0.0],
        })
        ph.plot_vitrification_burden(panel, df)
        assert panel.messages == ["No positive tank inventory"]

    def test_renders_with_real_plot_widget(self, qtbot):
        # figure.clear()/add_subplot()/colorbar() need a real Figure, not
        # the FakePanel stand-in used for the early-return checks above.
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({
            "WasteSiteId": ["T1", "T2"], "Total_kg_inventory": [100.0, 50.0],
            "Total_Ci_inventory": [10.0, 5.0], "frac_problem_elements_proxy": [0.1, 0.9],
            "frac_glass_former_or_intermediate": [0.8, 0.1],
        })
        ph.plot_vitrification_burden(panel, df)
        qtbot.wait(20)
        assert panel.ax.get_title() == "Vitrification screening map"


class TestPlotCandidateScores:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_candidate_scores(panel, pd.DataFrame({"x": [1]}))
        assert panel.messages == ["No candidate ranking data"]

    def test_all_nan_scores_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({"WasteSiteId": ["T1"], "User_search_score_proxy": [float("nan")]})
        ph.plot_candidate_scores(panel, df)
        assert panel.messages == ["No candidate scores to plot"]

    def test_negative_scores_are_plotted_not_filtered(self):
        # Unlike plot_barh, negative scores must still render -- a low or
        # negative vitrification score is meaningful screening information.
        panel = FakePanel()
        df = pd.DataFrame({"WasteSiteId": ["T1", "T2"], "User_search_score_proxy": [-50.0, 30.0]})
        ph.plot_candidate_scores(panel, df)
        labels, values, color = panel.ax.barh_calls[0]
        assert set(labels) == {"T1", "T2"}
        assert -50.0 in values

    def test_top_n_limits_bars(self):
        panel = FakePanel()
        df = pd.DataFrame({"WasteSiteId": [f"T{i}" for i in range(10)], "User_search_score_proxy": list(range(10))})
        ph.plot_candidate_scores(panel, df, top_n=3)
        labels, values, color = panel.ax.barh_calls[0]
        assert len(labels) == 3


class TestPlotBlendScores:
    def test_missing_columns_shows_message(self):
        panel = FakePanel()
        ph.plot_blend_scores(panel, pd.DataFrame({"x": [1]}))
        assert panel.messages == ["No blend partner data"]

    def test_all_nan_scores_shows_message(self):
        panel = FakePanel()
        df = pd.DataFrame({"PartnerTank": ["T1"], "BaseTank": ["T0"], "Blend_complement_score_proxy": [float("nan")]})
        ph.plot_blend_scores(panel, df)
        assert panel.messages == ["No blend scores to plot"]

    def test_title_includes_base_tank(self, qtbot):
        from qt_widgets import PlotWidget
        panel = PlotWidget()
        qtbot.addWidget(panel)
        df = pd.DataFrame({
            "PartnerTank": ["T1", "T2"], "BaseTank": ["T0", "T0"],
            "Blend_complement_score_proxy": [10.0, 20.0],
        })
        ph.plot_blend_scores(panel, df)
        qtbot.wait(20)
        assert "T0" in panel.ax.get_title()
