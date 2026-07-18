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
