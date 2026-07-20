"""
compose_science.py — pure grid-layout and panel-label logic for the Figure
Composer workspace. Framework-agnostic (no Qt, no matplotlib) so it's
directly unit-testable; the actual raster compositing lives in
figure_composer.py, which uses these functions.
"""
from __future__ import annotations

import math
from typing import Tuple

LABEL_STYLES = ["A, B, C", "a, b, c", "(a), (b), (c)", "1, 2, 3", "none"]
DEFAULT_LABEL_STYLE = "A, B, C"


def compute_grid_shape(n: int, cols: int = 0) -> Tuple[int, int]:
    """(rows, cols) for n panels. cols=0 ("auto") picks a near-square grid
    -- ceil(sqrt(n)) columns -- which tends toward a landscape aspect for
    typical panel counts (2-6), matching how most publication figures are
    laid out. A positive cols is honored directly (capped at n, so asking
    for more columns than panels doesn't leave empty columns)."""
    n = max(int(n), 0)
    if n == 0:
        return (0, 0)
    if cols and cols > 0:
        cols = min(int(cols), n)
        rows = math.ceil(n / cols)
        return (rows, cols)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return (rows, cols)


def panel_label(index: int, style: str) -> str:
    """0-based panel index -> label text, per one of LABEL_STYLES."""
    if style == "none":
        return ""
    if style == "1, 2, 3":
        return str(index + 1)
    letters = _index_to_letters(index)
    if style == "a, b, c":
        return letters.lower()
    if style == "(a), (b), (c)":
        return f"({letters.lower()})"
    return letters  # "A, B, C" (default, and the fallback for any unknown style)


def _index_to_letters(index: int) -> str:
    """0->A, 1->B, ..., 25->Z, 26->AA, 27->AB, ... -- spreadsheet-column
    style, in case someone composes more than 26 panels into one figure."""
    letters = ""
    n = index
    while True:
        n, rem = divmod(n, 26)
        letters = chr(65 + rem) + letters
        if n == 0:
            return letters
        n -= 1
