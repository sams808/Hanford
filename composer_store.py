"""
composer_store.py — shared state for the Figure Composer workspace: a
single in-memory list of captured plot snapshots, mutated by the "-> Figure
Composer" button on every PlotWidget's toolbar and read by the Figure
Composer page itself.

Kept as its own tiny module (rather than living in qt_widgets.py or
qt_figure_composer.py) specifically to avoid a circular import: PlotWidget
(in qt_widgets.py) needs to push into this store, and the Figure Composer
page (in qt_figure_composer.py) needs to both read it AND import
PlotWidget for its own preview pane -- putting the store in either of
those two files would make the other import it back.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import List

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class ComposerItem:
    png_bytes: bytes
    caption: str
    source: str = ""
    added_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


class ComposerStore(QObject):
    """Emits `changed` after every mutation so the Figure Composer page
    (if currently visible) can refresh its gallery/preview immediately,
    even though the item was added from a completely different workspace."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._items: List[ComposerItem] = []

    def items(self) -> List[ComposerItem]:
        return list(self._items)

    def add(self, png_bytes: bytes, caption: str, source: str = "") -> None:
        self._items.append(ComposerItem(png_bytes=png_bytes, caption=caption, source=source))
        self.changed.emit()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self.changed.emit()

    def move(self, index: int, delta: int) -> None:
        new_index = index + delta
        if 0 <= index < len(self._items) and 0 <= new_index < len(self._items):
            self._items[index], self._items[new_index] = self._items[new_index], self._items[index]
            self.changed.emit()

    def set_caption(self, index: int, caption: str) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = replace(self._items[index], caption=caption)
            self.changed.emit()

    def clear(self) -> None:
        if self._items:
            self._items.clear()
            self.changed.emit()


# Module-level singleton: every PlotWidget's "-> Figure Composer" button and
# the Figure Composer page itself share this one instance.
store = ComposerStore()
