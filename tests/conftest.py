"""
Shared pytest fixtures: data fixtures (below) plus three autouse Qt
fixtures that keep the Qt-level tests deterministic and non-blocking:

- _synchronous_workers: qt_worker.run_in_thread executes inline during
  tests instead of on a QThreadPool, so tests don't need wait-loops.
- _hermetic_qsettings: QSettings is replaced with an in-memory fake so
  real per-user registry values never leak into or out of a test.
- _prevent_blocking_qt_dialogs: QMessageBox convenience popups resolve
  immediately instead of blocking on user input under pytest.

qt_shell.py and friends must import QSettings *locally* inside the methods
that use it (not once at module level) for _hermetic_qsettings to actually
take effect there -- patching PySide6.QtCore.QSettings only affects lookups
that happen after the patch is applied.
"""
from pathlib import Path

import polars as pl
import pytest

from data_model import HanfordDataset

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_CSV_PATH = REPO_ROOT / "Hanford.csv"
REAL_ATTRS_PATH = REPO_ROOT / "Tank_attributes.csv"

requires_real_data = pytest.mark.skipif(
    not REAL_CSV_PATH.exists(), reason="Hanford.csv not present locally (gitignored dev seed data)"
)


def _raw_composition_rows() -> pl.DataFrame:
    """Small, deliberately-chosen composition rows:
    - a plain isotope (137Cs), a metastable isotope (113mCd)
    - both combined-isotope bug-fix cases (239/240Pu, 243/244Cm)
    - a legitimately non-elemental analyte (Total Alpha)
    - a genuine duplicate (WasteSiteId, Analyte) key across WastePhase
      (241-A-101 / Fe appears twice, in Solid and Liquid phase) to prove
      aggregation must group-by-sum rather than assume a unique key
    - both Ci and kg units, two tanks in two different farms (A, AN)
    """
    return pl.DataFrame({
        "WasteSiteId": [
            "241-A-101", "241-A-101", "241-A-101", "241-A-101", "241-A-101", "241-A-101",
            "241-AN-104", "241-AN-104", "241-AN-104",
        ],
        "Analyte": [
            "137Cs", "Fe", "239/240Pu", "113mCd", "Total Alpha", "Fe",
            "137Cs", "Na", "243/244Cm",
        ],
        "WastePhase": [
            "Liquid", "Solid", "Solid", "Liquid", "Liquid", "Liquid",
            "Sludge", "Sludge", "Sludge",
        ],
        "WasteType": ["T1"] * 6 + ["T2"] * 3,
        "Inventory": [100.0, 50.0, 0.002, 0.5, 0.01, 10.0, 200.0, 500.0, 0.001],
        "Units": ["Ci", "kg", "Ci", "kg", "Ci", "kg", "Ci", "kg", "Ci"],
    })


def _raw_attributes_rows() -> pl.DataFrame:
    return pl.DataFrame({
        "Name": ["241-A-101", "241-AN-104"],
        "TankType": ["SST-4", "DST"],
        "TankStatus": ["", ""],
        "TankIntegrity": ["Sound", "Assumed leaker"],
        "Capacity": ["1000", "1160"],
        "DIL_Gal": ["37000", "0"],
    })


@pytest.fixture
def sample_dataset() -> HanfordDataset:
    """A HanfordDataset with small, hand-built, already-cleaned data — no
    disk I/O. Exercises the real cleaning pipeline (_clean_dataframe /
    _clean_attributes_dataframe / _merge_tank_attributes) against fixture
    rows rather than mocking it away."""
    dataset = HanfordDataset()
    df = dataset._clean_dataframe(_raw_composition_rows())
    attrs = dataset._clean_attributes_dataframe(_raw_attributes_rows())
    dataset.attrs_df = attrs
    dataset.df = dataset._merge_tank_attributes(df, attrs)
    dataset.report = None
    return dataset


@pytest.fixture
def real_csv_paths():
    """(composition_path, attributes_path) for the real local dataset.
    Use with @requires_real_data."""
    return REAL_CSV_PATH, REAL_ATTRS_PATH


@pytest.fixture(scope="session", autouse=True)
def _synchronous_workers():
    import qt_worker
    qt_worker.set_synchronous(True)
    yield
    qt_worker.set_synchronous(False)


@pytest.fixture(autouse=True)
def _hermetic_qsettings(monkeypatch):
    store: dict = {}

    class FakeQSettings:
        def __init__(self, *args, **kwargs):
            pass

        def value(self, key, default=None, type=None):
            val = store.get(key, default)
            if type is not None and val is not None:
                try:
                    return type(val)
                except (TypeError, ValueError):
                    return val
            return val

        def setValue(self, key, value) -> None:
            store[key] = value

        def sync(self) -> None:
            pass

    monkeypatch.setattr("PySide6.QtCore.QSettings", FakeQSettings)
    yield


@pytest.fixture(autouse=True)
def _prevent_blocking_qt_dialogs(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    yield
