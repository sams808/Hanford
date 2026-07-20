"""
qt_widgets.py — shared Qt widgets used by every workspace: a matplotlib
plot panel (PlotWidget, ported from the sibling Dataapp project), a
timestamped status log (StatusLogger), and a real DataFrame-backed table
(DataFrameTableModel/DataFrameTableView) -- Ember is far more table-centric
than Dataapp, which gets away with hand-filling a QTableWidget per
workspace; that doesn't scale to the ~30 result tables across Ember's
workspaces, so this is a genuine, justified addition.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Callable, List, Optional

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QLabel, QMenu, QMessageBox,
    QTableView, QVBoxLayout, QWidget,
)


class PlotWidget(QWidget):
    """Figure + canvas + navigation toolbar, with a debounced redraw helper.

    Update existing artists in place where possible rather than
    ax.clear() + replot; request_redraw() below handles the debounce half
    of keeping that responsive, callers are responsible for the "update in
    place" half when they draw.
    """

    def __init__(self, parent: Optional[QWidget] = None, figsize=(6.0, 4.5), dpi: int = 100,
                 debounce_ms: int = 120):
        super().__init__(parent)
        self.figure = Figure(figsize=figsize, dpi=dpi)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.addSeparator()
        self.toolbar.addAction("→ Figure Composer", self._send_to_composer)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.coords_label = QLabel("")
        self.coords_label.setObjectName("SectionNote")
        self.coords_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.coords_label)
        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._flush_redraw)
        self._pending: Optional[tuple] = None

    def _on_mouse_move(self, event) -> None:
        if event.inaxes is None or event.xdata is None:
            self.coords_label.setText("")
            return
        self.coords_label.setText(f"x = {event.xdata:.4g}   y = {event.ydata:.4g}")

    def request_redraw(self, fn: Callable, *args, **kwargs) -> None:
        """Coalesce rapid-fire redraw requests into ONE redraw shortly after
        the last call. `fn` should do the actual plotting/artist updates;
        canvas.draw_idle() is called after."""
        self._pending = (fn, args, kwargs)
        self._debounce.start()

    def _flush_redraw(self) -> None:
        if self._pending is None:
            return
        fn, args, kwargs = self._pending
        self._pending = None
        fn(*args, **kwargs)
        self.canvas.draw_idle()

    def set_figure_size_inches(self, width: float, height: float, *, cap_to_visible: bool = True) -> None:
        """Resize the figure AND the canvas widget to match. Figure.set_size_
        inches(..., forward=True) is a no-op for a canvas embedded directly
        (as this one is, not via pyplot): forward=True only resizes anything
        through `canvas.manager`, which is a pyplot-only concept and is
        always None here -- so callers that want an on-screen size change
        (e.g. a plot with more rows needing a taller figure to keep labels
        legible) must go through this method instead of calling
        figure.set_size_inches() directly.

        A plain canvas.resize() is only advisory -- inside a QSplitter, any
        later relayout (e.g. a sibling table's sizeHint changing after
        set_dataframe() with a different row count) reasserts the splitter's
        own geometry and silently undoes it. Setting the canvas's minimum
        size makes the request an actual constraint the layout must respect
        on every subsequent pass, not just a one-off nudge -- but an
        unbounded minimum size is its own hazard (there's no scroll area
        anywhere in this app, so a wide/tall enough request would force the
        splitter to either overflow the window or crush its sibling panel
        illegibly thin). By default this clamps to available_content_
        width/height_inches() first so growth always stays inside what's
        actually visible; pass cap_to_visible=False to request an exact
        size regardless (e.g. export-at-fixed-size code paths)."""
        if cap_to_visible:
            max_w = self.available_content_width_inches()
            max_h = self.available_content_height_inches()
            if max_w is not None:
                width = min(width, max_w)
            if max_h is not None:
                height = min(height, max_h)
        self.figure.set_size_inches(width, height)
        w_px, h_px = self.canvas.get_width_height()
        self.canvas.setMinimumSize(w_px, h_px)
        self.canvas.resize(w_px, h_px)

    def available_content_height_inches(self) -> Optional[float]:
        """Approximate vertical room left for the canvas within this
        widget's CURRENT on-screen size, after the toolbar -- or None if
        the widget isn't actually shown yet (its height() is then just a
        Qt default/placeholder, not real available space). Callers that
        grow a figure's height based on data size (more rows -> taller
        figure, to keep labels legible) should cap it at this, since there
        is no scroll area around the canvas: a figure taller than what's
        visible doesn't scroll into view, it just gets silently clipped."""
        if not self.isVisible():
            return None
        chrome_px = self.toolbar.height() + 24  # ~one line for coords_label
        return max(self.height() - chrome_px, 0) / self.figure.dpi

    def available_content_width_inches(self, reserve_px: int = 280) -> Optional[float]:
        """Approximate horizontal room available for this canvas without
        forcing the enclosing window wider than it already is. Unlike
        height (this widget is already stretched to fill available
        vertical space by its container), width inside a horizontal
        QSplitter is actively managed by the splitter itself and can't be
        read off self.width() -- that's just whatever the splitter
        currently allocates, not a ceiling. The right ceiling is the
        top-level window's current width, minus a reserve for the sibling
        panel (typically a data table) and the splitter handle -- None if
        the widget isn't shown yet, same reasoning as the height version."""
        if not self.isVisible():
            return None
        top = self.window()
        if top is None or not top.isVisible():
            return None
        return max(top.width() - reserve_px, 0) / self.figure.dpi

    def cap_square_size_inches(self, ideal: float) -> float:
        """For a caller about to request equal (or near-equal, e.g. plus a
        small fixed margin for a colorbar/marginal bars) width and height --
        a `seaborn square=True` heatmap grid, a PCA/network scatter, etc.:
        capping each axis independently after the fact wastes whichever
        axis has more slack, since matplotlib centers a square plot within
        the smaller of the two. Returns the largest size, at most `ideal`,
        that fits within both available_content_width/height_inches()."""
        caps = [ideal]
        avail_w = self.available_content_width_inches()
        if avail_w is not None:
            caps.append(avail_w)
        avail_h = self.available_content_height_inches()
        if avail_h is not None:
            caps.append(avail_h)
        return min(caps)

    def clear(self, title: str = "") -> None:
        self.ax.clear()
        self.ax.grid(alpha=0.25)
        if title:
            self.ax.set_title(title)
        self.canvas.draw_idle()

    def show_message(self, message: str) -> None:
        """Blank the plot and show a centered message (e.g. "no data",
        "seaborn not installed") instead of a stale or empty axes."""
        self.ax.clear()
        self.ax.axis("off")
        self.ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True,
                      transform=self.ax.transAxes, fontsize=11, color="0.4")
        self.canvas.draw_idle()

    def export_at_size_cm(self, path: str, width_cm: float, height_cm: float, dpi: int = 300) -> None:
        """Export the current figure at an exact physical size."""
        w_in, h_in = width_cm / 2.54, height_cm / 2.54
        old_size = self.figure.get_size_inches()
        try:
            self.figure.set_size_inches(w_in, h_in)
            self.figure.savefig(path, dpi=dpi)
        finally:
            self.figure.set_size_inches(*old_size)
            self.canvas.draw_idle()

    def capture_png(self, dpi: int = 300) -> bytes:
        """Renders the current figure to PNG bytes at a fixed DPI,
        independent of the on-screen zoom/size -- used by "-> Figure
        Composer" so a panel's resolution in the combined figure doesn't
        depend on how big the source plot happened to be on screen when
        captured."""
        buf = BytesIO()
        self.figure.savefig(buf, format="png", dpi=dpi, facecolor="white", bbox_inches="tight")
        return buf.getvalue()

    def suggested_caption(self) -> str:
        """The figure's suptitle if it has one (used by the two-marginal-
        bar correlation heatmaps, where an axes-level title would collide
        with the top bar chart), otherwise the main axes' own title."""
        suptitle = self.figure.get_suptitle()
        if suptitle:
            return suptitle
        if self.ax is not None:
            return self.ax.get_title() or ""
        return ""

    def _send_to_composer(self) -> None:
        from composer_store import store
        caption = self.suggested_caption()
        store.add(self.capture_png(), caption, source=caption)


class StatusLogger(QObject):
    """Timestamped, in-memory app log. HanfordDataset takes `.log` as its
    logger callback; the Debug/Export workspace shows `full_text()` and can
    connect to `logged` for a live-updating view."""

    logged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lines: List[str] = []

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self._lines.append(line)
        print(line)
        self.logged.emit(line)

    def full_text(self) -> str:
        return "\n".join(self._lines)

    def clear(self) -> None:
        self._lines.clear()


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, np.ndarray)):
        # Polars list-columns (e.g. the "which analytes contributed" summary
        # columns) come through pandas as numpy object arrays, not Python
        # lists -- pd.isna() on one of those returns an array, not a bool,
        # so this check must come before the scalar pd.isna() branch below.
        return "; ".join(str(v) for v in value)
    if isinstance(value, float):
        return "" if pd.isna(value) else f"{value:.5g}"
    if pd.isna(value):
        return ""
    return str(value)


class DataFrameTableModel(QAbstractTableModel):
    """Read-only Qt table model backed by a pandas DataFrame."""

    def __init__(self, df: Optional[pd.DataFrame] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        value = self._df.iat[index.row(), index.column()]
        return _format_cell(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(self._df.index[section])

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if self._df.empty or column < 0 or column >= len(self._df.columns):
            return
        col_name = self._df.columns[column]
        self.layoutAboutToBeChanged.emit()
        self._df = self._df.sort_values(
            by=col_name, ascending=(order == Qt.AscendingOrder), kind="mergesort"
        ).reset_index(drop=True)
        self.layoutChanged.emit()


class DataFrameTableView(QTableView):
    """DataFrameTableModel-backed table view with sensible defaults and a
    right-click Copy / Export CSV menu (parity with the old app's
    DataFrameTable widget)."""

    def __init__(self, parent: Optional[QWidget] = None, *, title: str = "", max_rows_display: Optional[int] = None):
        super().__init__(parent)
        self.title = title
        self.max_rows_display = max_rows_display
        self._model = DataFrameTableModel()
        self.setModel(self._model)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_dataframe(self, df: pd.DataFrame) -> None:
        if self.max_rows_display is not None and len(df) > self.max_rows_display:
            df = df.head(self.max_rows_display)
        self._model.set_dataframe(df)
        self.resizeColumnsToContents()

    def dataframe(self) -> pd.DataFrame:
        return self._model.dataframe()

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Copy selection", self._copy_selection)
        menu.addAction("Export CSV…", self._export_csv)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_selection(self) -> None:
        df = self.dataframe()
        if df.empty:
            return
        indexes = self.selectedIndexes()
        if not indexes:
            text = df.to_csv(sep="\t", index=False)
        else:
            rows = sorted({i.row() for i in indexes})
            cols = sorted({i.column() for i in indexes})
            text = df.iloc[rows, cols].to_csv(sep="\t", index=False)
        QApplication.clipboard().setText(text)

    def _export_csv(self) -> None:
        df = self.dataframe()
        if df.empty:
            QMessageBox.information(self, "Export CSV", "Nothing to export yet.")
            return
        name = f"{self.title or 'table'}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", name, "CSV (*.csv)")
        if path:
            df.to_csv(path, index=False)
