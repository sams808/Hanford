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

import numpy as np
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


STRUCTURE_TANKS = [
    "241-A-101", "241-A-102", "241-A-103", "241-A-104",
    "241-AN-101", "241-AN-102", "241-AN-103", "241-AN-104",
]
GROUP_A_TANKS = STRUCTURE_TANKS[:4]
GROUP_AN_TANKS = STRUCTURE_TANKS[4:]


@pytest.fixture
def structure_dataset():
    """8 tanks in two clean, hand-separated groups (by Cs/Sr/Mo
    composition) so PCA and hierarchical clustering have real structure to
    recover, plus a constant Fe column (drop-constant-element handling)
    and per-farm TankType/WastePhase so tank_categorical_labels /
    color-by has something meaningful to group."""
    cs_vals = [100.0, 110.0, 120.0, 130.0, 5.0, 6.0, 7.0, 8.0]
    sr_vals = [v * 0.5 for v in cs_vals]      # exactly proportional to Cs -> r=1.0
    mo_vals = [138.0 - v for v in cs_vals]    # exact affine, negative slope -> r=-1.0
    fe_vals = [10.0] * 8                       # constant -> must be dropped, not crash
    phases = ["Sludge Solid"] * 4 + ["Supernatant"] * 4

    rows = {"WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": []}
    for tank, cs_v, sr_v, mo_v, fe_v, phase in zip(STRUCTURE_TANKS, cs_vals, sr_vals, mo_vals, fe_vals, phases):
        for analyte, val in [("Cs", cs_v), ("Sr", sr_v), ("Mo", mo_v), ("Fe", fe_v)]:
            rows["WasteSiteId"].append(tank)
            rows["Analyte"].append(analyte)
            rows["WastePhase"].append(phase)
            rows["WasteType"].append("T1")
            rows["Inventory"].append(val)
            rows["Units"].append("kg")

    attrs_rows = pl.DataFrame({
        "Name": STRUCTURE_TANKS,
        "TankType": ["DST"] * 4 + ["SST-4"] * 4,
        "TankStatus": ["Active"] * 4 + ["Interim Closure"] * 4,
        "TankIntegrity": ["Sound"] * 8,
        "Capacity": ["1000"] * 8,
        "DIL_Gal": ["0"] * 8,
    })

    dataset = HanfordDataset()
    df = dataset._clean_dataframe(pl.DataFrame(rows))
    attrs = dataset._clean_attributes_dataframe(attrs_rows)
    dataset.attrs_df = attrs
    dataset.df = dataset._merge_tank_attributes(df, attrs)
    dataset.report = None
    return dataset


@pytest.fixture
def size_confound_dataset():
    """12 tanks where Cs and Ba are both driven mostly by a shared "tank
    size" element (Na) plus independent per-tank noise -- exercises
    control_for_total_inventory / partial correlation (correlation_science,
    structure_science): raw corr(Cs, Ba) is strongly positive because both
    scale with tank size, but that mostly disappears once you control for
    each tank's total kg inventory. Built with a fixed numpy Generator seed
    so it's exactly reproducible; expected raw/partial r values are
    computed independently in each test via plain pandas .corr() calls on
    these same arrays, not by calling the functions under test."""
    rng = np.random.default_rng(0)
    n = 12
    driver = np.linspace(200, 260, n)
    cs = 0.5 * driver + rng.normal(0, 6, n)
    ba = 0.2 * driver + rng.normal(0, 6, n)
    other = 50 + rng.normal(0, 3, n)
    tanks = [f"241-A-{100 + i}" for i in range(n)]

    rows = {"WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": []}
    for tank, na_v, cs_v, ba_v, other_v in zip(tanks, driver, cs, ba, other):
        for analyte, val in [("Na", na_v), ("Cs", cs_v), ("Ba", ba_v), ("Zr", other_v)]:
            rows["WasteSiteId"].append(tank)
            rows["Analyte"].append(analyte)
            rows["WastePhase"].append("Sludge Solid")
            rows["WasteType"].append("T1")
            rows["Inventory"].append(float(val))
            rows["Units"].append("kg")

    dataset = HanfordDataset()
    dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
    dataset.report = None
    return dataset, {"driver": driver, "Cs": cs, "Ba": ba, "other": other, "tanks": tanks}


@pytest.fixture
def oxide_dataset():
    """3 tanks, kg-only: T1 has Na+Si (clean binary glass-former mix), T2
    has Na+Si+Cl (Cl is a non-network element -> reported elemental) and
    Pu (no PNNL-20184 basicity value -> must be excluded, not crash), T3
    repeats T1's elements at different amounts (for the blend test)."""
    rows = {"WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": []}
    data = [
        ("241-A-101", [("Na", 100.0), ("Si", 50.0)]),
        ("241-A-102", [("Na", 40.0), ("Si", 20.0), ("Cl", 5.0), ("Pu", 0.001)]),
        ("241-A-103", [("Na", 60.0), ("Si", 30.0)]),
    ]
    for tank, elements in data:
        for analyte, val in elements:
            rows["WasteSiteId"].append(tank)
            rows["Analyte"].append(analyte)
            rows["WastePhase"].append("Liquid")
            rows["WasteType"].append("T1")
            rows["Inventory"].append(val)
            rows["Units"].append("kg")
    dataset = HanfordDataset()
    dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
    dataset.report = None
    return dataset


@pytest.fixture
def vitrification_dataset():
    """4 tanks, hand-verifiable screening/candidate/blend numbers:
      241-A-101: B=10kg (former), Na=5kg (modifier), Cr=2kg (problem+redox),
                 plus Cs=50 Ci (radiological) -- total_kg=17
      241-A-102: Cl=3kg (volatile+problem only) -- total_kg=3
      241-A-103: Si=8kg (former only) -- total_kg=8
      241-A-104: Cs=10 Ci only, NO kg rows at all -- exercises the
                 all-fractions-NaN-for-this-tank edge case (zero total kg).
    Expected screening/candidate/blend scores are computed independently
    by hand from these numbers in each test, not by re-deriving the
    implementation's own logic."""
    rows = {"WasteSiteId": [], "Analyte": [], "WastePhase": [], "WasteType": [], "Inventory": [], "Units": []}

    def add(tank, analyte, inv, unit):
        rows["WasteSiteId"].append(tank)
        rows["Analyte"].append(analyte)
        rows["WastePhase"].append("Liquid")
        rows["WasteType"].append("T1")
        rows["Inventory"].append(inv)
        rows["Units"].append(unit)

    add("241-A-101", "B", 10.0, "kg")
    add("241-A-101", "Na", 5.0, "kg")
    add("241-A-101", "Cr", 2.0, "kg")
    add("241-A-101", "137Cs", 50.0, "Ci")
    add("241-A-102", "Cl", 3.0, "kg")
    add("241-A-103", "Si", 8.0, "kg")
    add("241-A-104", "137Cs", 10.0, "Ci")

    dataset = HanfordDataset()
    dataset.df = dataset._clean_dataframe(pl.DataFrame(rows))
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
