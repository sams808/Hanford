"""
qt_settings_store.py — generic "settings that persist per item" store.

Any workspace that needs per-tank or per-element UI memory (e.g. remembered
oxidation-state overrides per element, remembered filter settings per
saved search) should use ONE of these, keyed by a stable id (WasteSiteId,
element symbol) -- never by row title or position, which silently breaks
when two items share a display label or the list gets reordered.
"""
from __future__ import annotations

from typing import Callable, Dict, Generic, Iterator, Tuple, TypeVar

T = TypeVar("T")


class PerItemSettingsStore(Generic[T]):
    def __init__(self, default_factory: Callable[[], T]):
        self._default_factory = default_factory
        self._store: Dict[str, T] = {}

    def get(self, item_id: str) -> T:
        if item_id not in self._store:
            self._store[item_id] = self._default_factory()
        return self._store[item_id]

    def set(self, item_id: str, value: T) -> None:
        self._store[item_id] = value

    def has(self, item_id: str) -> bool:
        return item_id in self._store

    def discard(self, item_id: str) -> None:
        self._store.pop(item_id, None)

    def clear(self) -> None:
        self._store.clear()

    def items(self) -> Iterator[Tuple[str, T]]:
        return iter(self._store.items())
