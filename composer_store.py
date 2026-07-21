"""
composer_store.py — shared state for the Figure Composer workspace: a
single in-memory list of captured plot "recipes" (the plot_helpers render
function plus the exact arguments used to call it), mutated by the "->
Figure Composer" button on every PlotWidget's toolbar and read by the
Figure Composer page itself.

Recipes, not snapshots: each captured item remembers *how* to redraw its
plot rather than a frozen raster image of it. figure_composer.compose_figure
replays that call into its own subfigure at compose time, so every panel in
the combined figure stays a real, live, vector matplotlib Axes -- editable
(title, axis labels, any of the recipe's own keyword parameters) and sharp
at any export size -- instead of a fixed-resolution picture of what the
plot looked like at capture time.

Kept as its own tiny module (rather than living in qt_widgets.py or
qt_figure_composer.py) specifically to avoid a circular import: PlotWidget
(in qt_widgets.py) needs to push into this store, and the Figure Composer
page (in qt_figure_composer.py) needs to both read it AND import
PlotWidget for its own preview pane -- putting the store in either of
those two files would make the other import it back.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

_uid_counter = itertools.count()


@dataclass(frozen=True)
class ComposerItem:
    render_fn: Callable
    render_args: Tuple[Any, ...]
    render_kwargs: Dict[str, Any]
    caption: str
    source: str = ""
    added_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    # Stable across replace()-based edits below (those only ever override
    # OTHER fields), unlike object identity -- lets a thumbnail cache tell
    # "same panel, cosmetic edit" apart from "genuinely different content"
    # without needing render_args/render_kwargs (which may hold DataFrames,
    # not usable as a plain dict key) to be hashable.
    uid: int = field(default_factory=lambda: next(_uid_counter))
    # User overrides layered on top of the recipe at render time. None means
    # "use whatever the recipe itself produces"; "" (title/axis labels
    # only) means "force blank". kwarg_overrides replaces individual keys
    # of render_kwargs without losing the originally-captured values, so
    # "reset to original" is just clearing the dict back to {}.
    title_override: Optional[str] = None
    xlabel_override: Optional[str] = None
    ylabel_override: Optional[str] = None
    kwarg_overrides: Dict[str, Any] = field(default_factory=dict)

    def effective_kwargs(self) -> Dict[str, Any]:
        return {**self.render_kwargs, **self.kwarg_overrides}


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

    def add_recipe(
        self, render_fn: Callable, render_args: Tuple[Any, ...], render_kwargs: Dict[str, Any],
        caption: str, source: str = "",
    ) -> None:
        # Deep-copy so a later reload/rerun elsewhere in the app that
        # reassigns the source DataFrames can't change what an
        # already-captured panel replays.
        item = ComposerItem(
            render_fn=render_fn, render_args=copy.deepcopy(render_args),
            render_kwargs=copy.deepcopy(render_kwargs), caption=caption, source=source,
        )
        self._items.append(item)
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

    def set_title_override(self, index: int, title: Optional[str]) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = replace(self._items[index], title_override=title)
            self.changed.emit()

    def set_xlabel_override(self, index: int, xlabel: Optional[str]) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = replace(self._items[index], xlabel_override=xlabel)
            self.changed.emit()

    def set_ylabel_override(self, index: int, ylabel: Optional[str]) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = replace(self._items[index], ylabel_override=ylabel)
            self.changed.emit()

    def set_kwarg_override(self, index: int, key: str, value: Any) -> None:
        if 0 <= index < len(self._items):
            overrides = dict(self._items[index].kwarg_overrides)
            overrides[key] = value
            self._items[index] = replace(self._items[index], kwarg_overrides=overrides)
            self.changed.emit()

    def clear_kwarg_overrides(self, index: int) -> None:
        if 0 <= index < len(self._items) and self._items[index].kwarg_overrides:
            self._items[index] = replace(self._items[index], kwarg_overrides={})
            self.changed.emit()

    def clear(self) -> None:
        if self._items:
            self._items.clear()
            self.changed.emit()


# Module-level singleton: every PlotWidget's "-> Figure Composer" button and
# the Figure Composer page itself share this one instance.
store = ComposerStore()
