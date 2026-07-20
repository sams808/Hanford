import pytest

import compose_science as csci


class TestComputeGridShape:
    def test_zero_panels(self):
        assert csci.compute_grid_shape(0) == (0, 0)

    def test_one_panel_auto(self):
        assert csci.compute_grid_shape(1) == (1, 1)

    def test_two_panels_auto_is_landscape(self):
        # ceil(sqrt(2)) = 2 columns -> 1 row x 2 cols, not 2x1
        assert csci.compute_grid_shape(2) == (1, 2)

    def test_four_panels_auto_is_square(self):
        assert csci.compute_grid_shape(4) == (2, 2)

    def test_five_panels_auto(self):
        # ceil(sqrt(5))=3 cols -> ceil(5/3)=2 rows
        assert csci.compute_grid_shape(5) == (2, 3)

    def test_explicit_cols_honored(self):
        assert csci.compute_grid_shape(6, cols=3) == (2, 3)

    def test_explicit_cols_capped_at_n(self):
        # asking for more columns than panels shouldn't leave empty columns
        assert csci.compute_grid_shape(2, cols=8) == (1, 2)

    def test_negative_n_treated_as_zero(self):
        assert csci.compute_grid_shape(-3) == (0, 0)


class TestPanelLabel:
    def test_none_style_is_empty(self):
        assert csci.panel_label(0, "none") == ""
        assert csci.panel_label(5, "none") == ""

    def test_numeric_style_is_one_based(self):
        assert csci.panel_label(0, "1, 2, 3") == "1"
        assert csci.panel_label(4, "1, 2, 3") == "5"

    def test_uppercase_letters(self):
        assert csci.panel_label(0, "A, B, C") == "A"
        assert csci.panel_label(1, "A, B, C") == "B"
        assert csci.panel_label(25, "A, B, C") == "Z"

    def test_lowercase_letters(self):
        assert csci.panel_label(0, "a, b, c") == "a"
        assert csci.panel_label(2, "a, b, c") == "c"

    def test_parenthesized_lowercase(self):
        assert csci.panel_label(0, "(a), (b), (c)") == "(a)"
        assert csci.panel_label(1, "(a), (b), (c)") == "(b)"

    def test_unknown_style_falls_back_to_uppercase(self):
        assert csci.panel_label(0, "some unknown style") == "A"

    @pytest.mark.parametrize("index,expected", [
        (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA"),
    ])
    def test_beyond_26_panels_uses_spreadsheet_style(self, index, expected):
        assert csci.panel_label(index, "A, B, C") == expected


class TestLabelStyles:
    def test_default_is_a_valid_style(self):
        assert csci.DEFAULT_LABEL_STYLE in csci.LABEL_STYLES

    def test_every_style_produces_distinct_labels_for_first_three_panels(self):
        for style in csci.LABEL_STYLES:
            labels = [csci.panel_label(i, style) for i in range(3)]
            if style == "none":
                assert labels == ["", "", ""]
            else:
                assert len(set(labels)) == 3
