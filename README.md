# Ember

A desktop app for exploring Hanford nuclear-waste tank composition data and
screening tanks for vitrification (glass immobilization) — search elements
and analytes across 177 tanks, build tank×element heatmaps and correlation
maps, convert compositions to real oxide-basis glass chemistry (optical
basicity, NBO/T, GlassNet ML property prediction), and combine any of the
resulting plots into one labeled multi-panel figure for a report or slide
deck.

The app is PySide6/Qt-based: one main window with a left navigation rail of
workspaces. It is a from-scratch rewrite of an earlier Tkinter prototype
(`hanford_tank_gui_app.py`); that prototype's full history remains archived
alongside this repo for reference, not in this git history.

**Ember is an independent project — not produced by, affiliated with, or
endorsed by PNNL or the U.S. Department of Energy.** See [`NOTICE.md`](NOTICE.md)
for the full user manual (every workspace, every formula, every source
citation) and the exact data provenance.

## Workspaces

| Workspace | What it does |
|---|---|
| **Overview** | Dataset audit: units, top elements/analytes, waste-phase/type/farm breakdowns, missing values, debug-bundle export. |
| **Element Explorer** | Search by element symbol, analyte (exact/contains/regex); co-elements/co-analytes present alongside a target, composition stats, 7 plot types. |
| **Tank Attributes** | Browse joined tank engineering metadata (type, capacity, integrity, status). |
| **Tank Explorer** | Multi-tank composition profiles, fraction-of-tank-total, raw-row drill-down. |
| **Heatmaps** | Tank×element inventory matrices (log/raw/fraction modes). |
| **Correlations** | Quick Scan (target/dual/triple/full-matrix correlation, partial-correlation tank-size control), Association Workbench (kg-only Jaccard co-presence + preferred-association scoring, 17 plot types), Structure (PCA/clustering, partial correlation, network graph, interactive Plotly export). |
| **Vitrification** | Screening (adjustable-weight glass-formulation heuristic), Oxide Chemistry (element→oxide stoichiometric conversion, optical basicity, NBO/T, composition envelope checking, optional GlassNet ML property prediction), Candidate Search, Blend Partners. |
| **Figure Composer** | Combine any plots captured from any workspace into one multi-panel publication figure, with automatic panel labels (A, B, C, ...) and exact-size/DPI export. |
| **Debug / Export** | Global debug bundle export, environment info. |

## Installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt      # core science stack
pip install -r requirements-qt.txt   # PySide6
pip install -r requirements-dev.txt  # pytest + pytest-qt, for running the tests
```

Optional: `pip install glasspy` enables GlassNet ML property prediction in
the Oxide Chemistry workspace (needs PyTorch — not included in the packaged
`.exe`, Python-run only, same tradeoff as `xraylarch` in the sibling Dataapp
project).

## Running

```bash
python qt_main.py
```

Or double-click `Ember.bat`. `Hanford.csv` and `Tank_attributes.csv` are
committed to this repo and auto-detected next to the script (or the built
`.exe`) on launch — no separate data download needed. Point **Load
CSV/Parquet…** at a different export if you want to analyze updated data.

### Standalone `.exe` (no Python needed)

Build with `build_exe.bat` (PyInstaller) — produces `dist\Ember\Ember.exe`
plus a portable `dist\Ember-portable.zip` colleagues who don't code can run
by unzipping and double-clicking, no install step at all. GlassNet
(§ above) is disabled in this build to keep the download a reasonable size;
everything else is fully functional.

## Repository layout

Flat, one file per concern (mirrors the sibling Dataapp project's
convention): `qt_*.py` modules are the UI, `*_science.py` modules are
framework-agnostic analysis logic with no PySide6 imports and full unit-test
coverage. See `tests/` for the test suite (`pytest`).

## Data

`Hanford.csv` / `Tank_attributes.csv` **are committed to this repository**
so the app works immediately after a clone — no separate download step.
They come from PNNL's [PHOENIX](https://phoenix.pnnl.gov) (Hanford Online
Information Exchange), the access mechanism for Tri-Party Agreement tank
waste databases:

> Brulotte, P.J., and Christensen, K.C.. "Tri-Party Agreement databases,
> access mechanism and procedures". United States. doi:10.2172/10112540.
> https://www.osti.gov/servlets/purl/10112540
>
> "PNNL Hanford Online Information Exchange (PHOENIX)", Pacific Northwest
> National Laboratory, Richland WA, U.S. Department of Energy.
> https://phoenix.pnnl.gov

See [`NOTICE.md`](NOTICE.md) for the full citation context and independence
disclaimer.
