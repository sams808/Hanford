# Ember — detailed user notice

This notice describes the desktop application: what each workspace does, what each main control means, how to interpret the plots, how to export data, and what the vitrification screening tools can and cannot tell you.

Ember is a **visual exploration and screening tool** for Hanford tank composition data. It is not a regulatory classifier, not a glass formulation model, not a thermodynamic database, and not a waste loading/property predictor. Its goal is to help you quickly answer questions like:

- Which tanks contain a given element or analyte?
- How much of that element is present, and in which unit?
- What other elements tend to appear in the same tanks?
- Which elements correlate across tanks, and how much of that is just tank-size effects?
- Which tanks look chemically/radiologically similar, or cluster together?
- What would a tank's composition look like converted to oxide (glass) chemistry?
- Which tanks may be interesting candidates for blending or vitrification screening?
- Which data tables and plot inputs should be exported for deeper analysis?

The bundled composition data (`Hanford.csv`, `Tank_attributes.csv`) comes from PNNL's [PHOENIX](https://phoenix.pnnl.gov) (Hanford Online Information Exchange), the access mechanism for Tri-Party Agreement tank waste databases:

> Brulotte, P.J., and Christensen, K.C.. "Tri-Party Agreement databases, access mechanism and procedures". United States. doi:10.2172/10112540. https://www.osti.gov/servlets/purl/10112540
>
> "PNNL Hanford Online Information Exchange (PHOENIX)", Pacific Northwest National Laboratory, Richland WA, U.S. Department of Energy. https://phoenix.pnnl.gov

**Ember (this application) is an independent project and is not produced by, affiliated with, or endorsed by PNNL or the U.S. Department of Energy.**

> **Credit placeholder:** lab/PI attribution below is a starting draft (mirrors the sibling Dataapp/PRISM project's credits) — confirm the exact wording before treating it as final.

---

## 1. Installation and launch

Run `Ember.bat` from the app folder, or `py -3.11 qt_main.py` directly. The packaged `.exe` build needs no Python install at all — see the README for build instructions.

### 1.1 Input files

Ember expects two files next to it (or loadable via `Load CSV/Parquet…`):

- `Hanford.csv` — composition data with columns `WasteSiteId, Analyte, WastePhase, WasteType, Inventory, Units` (required) plus optional `Inventory_RSD, Volume, VolumeUnits, VolumeRSD, ComponentDensity, DensityUnits, AdjustedConcentration, AdjustedConcentrationUnits, DecayDate, PublishedDate, CCBLog`.
- `Tank_attributes.csv` — tank metadata (`Name`/`WasteSiteId`, `TankType`, `Capacity`, `TankStatus`, `TankIntegrity`, ...), joined onto the composition data. Optional; Ember runs without it, just with less tank metadata available.

Ember can open `.csv`, `.tsv`, `.txt`, and `.parquet`/`.pq` files.

---

## 2. General architecture

The nav sidebar has 8 workspaces:

1. **Overview**
2. **Element Explorer**
3. **Tank Attributes**
4. **Tank Explorer**
5. **Heatmaps**
6. **Correlations** — Quick Scan / Association Workbench (kg) / Structure sub-tabs
7. **Vitrification** — Screening / Oxide Chemistry / Candidate Search / Blend Partners sub-tabs
8. **Debug / Export**

Most plots can be saved via the plot panel's own toolbar (PNG/PDF/SVG, pan/zoom). Every workspace also exports the actual data tables behind its plots. This matters: when a plot looks wrong, you don't need to send the giant source CSV — export the debug bundle or the workspace-specific tables and send those.

---

## 3. Top toolbar

- **Load local CSVs** — auto-detects `Hanford.csv`/`Tank_attributes.csv` next to the app (or in the current folder).
- **Load CSV/Parquet…** — opens a file picker for any supported file.
- **Reload** — reloads the currently loaded file (F5). Use after replacing the input file.
- **Use parquet cache** — reuses a cleaned Parquet cache if one already exists next to the source CSV, for much faster reloads.
- **Refresh cache** — ignores any existing cache and rebuilds it from the original CSV. Use after the source CSV changes.
- **Open output folder** — opens the folder where every workspace writes its exports.

---

## 4. Data conventions that matter everywhere

### 4.1 Units are never blindly mixed

The dataset carries two fundamentally different inventory units: `kg` (chemical mass) and `Ci` (radioactivity). These cannot be summed or averaged together as if equivalent. Most Ember workspaces are unit-specific by design; the kg-only Correlations sub-tabs (Association Workbench, Structure) and the Vitrification tab are deliberately kg-only for exactly this reason — Ci and kg aren't comparable, so mixing them into one tank×element matrix would be scientifically meaningless.

### 4.2 Element parsing from analytes

The source `Analyte` column is not a clean element list (`137Cs`, `113mCd`, `239/240Pu`, `Total Alpha`, ...). Ember's parser converts these to element symbols conservatively, to avoid false positives (e.g. `TotalAlpha` does **not** parse to `Al`). When a multi-element analyte is parsed, the first parsed element receives the analyte's full inventory — this attribution rule matches the app's predecessor and is disclosed here since it changes every downstream number for those rows. Always check the raw analyte rows in Tank Explorer when an element total looks surprising.

### 4.3 `(WasteSiteId, Analyte)` is not a unique key

The same tank/analyte pair can appear multiple times across different `WastePhase` rows. Every aggregation in Ember sums across duplicates rather than assuming one row per tank×analyte.

---

## 5. Overview

A first sanity check of the loaded dataset: row/column counts, units audit, missing-value audit, waste-phase/type/farm audits, and top-elements/top-analytes bar charts. Check the units audit before trusting anything downstream — if a unit appears unexpectedly, stop and investigate.

---

## 6. Element Explorer

The main search workspace: element-symbol, exact-analyte, substring, or regex search modes. Shows which tanks contain the target, co-elements/co-analytes found alongside it, and composition statistics (both absolute mean/stdev inventory and tank-normalized fraction mean/stdev — these answer different questions, don't conflate them).

## 7. Tank Attributes

Browses `Tank_attributes.csv` directly: tank type, capacity, integrity, DST/SST status, and audits by category.

## 8. Tank Explorer

The inverse of Element Explorer: select one or more tanks (filterable by farm) and inspect their full composition, raw rows, and a grouped composition plot.

## 9. Heatmaps

Tank × element inventory matrices (raw / log10 / log10+1 value modes), restricted to the top-N elements by inventory to stay readable.

---

## 10. Correlations

Three sub-tabs, all built on the same tank×element pivot (`element_inventory_matrix`).

### 10.1 Quick Scan

Ported target-element scan, dual/triple pairwise correlation, and full correlation-matrix heatmap (lower-triangle only — a correlation matrix is symmetric, so the upper triangle just repeats the same information). Metric options (`inventory` / `log10_inventory` / `log10_plus1` / `fraction` / `presence`) and method options (`pearson` / `spearman`) control how the matrix is built before correlating; `include zeros` / `min overlap` / `min inv` control which tanks and pairs count. **Always check the overlap count before trusting a strong correlation** — `r = 1.0` from 3 overlapping tanks is a clue, not a conclusion.

**Control for tank size** checkbox: strips out the "everything correlates because both elements just scale with tank size" effect via partial correlation, controlling for each tank's total same-unit inventory. When checked, the table's `Correlation_r` column becomes the partial correlation and `Raw_Correlation_r` shows the uncontrolled value alongside it for comparison.

### 10.2 Association Workbench (kg)

Kg-only element-association screening (Ci is deliberately excluded — see §4.1): element stats, pairwise Jaccard co-presence, and a `PreferredAssociationScore_proxy` that rewards elements that are both positively correlated and frequently co-present, never rewarding negative correlation. 17 plot types (heatmaps, top-association bars, pair matrices, tank-similarity/tank×element maps, presence patterns, a stats dashboard), with a Basic/Coherent-colors theme toggle.

### 10.3 Structure

New capability, no equivalent in earlier versions of this tool:

- **PCA + hierarchical clustering** of tanks over a standardized kg element matrix — a scatter of the first two principal components (color-by TankFarm/TankType/TankSystem/TankStatus/Dominant waste phase) and a cross-checkable dendrogram.
- **Partial correlation matrix**, side-by-side with the raw correlation matrix, showing directly how much of each pairwise correlation is a tank-size artifact.
- **Element-association network graph** — nodes sized by total kg, edges thresholded by minimum |r| and minimum Jaccard co-presence, edge color by correlation sign.
- **Export interactive HTML** — writes the correlation heatmap, PCA scatter, and network graph as self-contained interactive Plotly HTML files (the JS is embedded, so they work fully offline) and opens the folder.

---

## 11. Vitrification

Four sub-tabs. **Every score here is a transparent screening heuristic, not an official glass model or waste classification** (see §12 below for the full list of what this tool does *not* calculate).

### 11.1 Screening

Ported from the original tool: one row per tank with chemical/radiological screening features (`frac_glass_former_or_intermediate`, `frac_alkali_alkaline_modifier`, `frac_transition_redox_sensitive`, `frac_volatile_halide_sulfate`, `frac_problem_elements_proxy`, `Ci_per_kg_proxy`, ...) and a combined screening score. Every weight in the score formula is now an editable control (with "Reset to defaults" showing the original constants) instead of buried in code, and a **basis** toggle switches the glass-former term between the legacy elemental-kg fraction and the new oxide-wt% fraction (see 11.2).

### 11.2 Oxide Chemistry

New capability — the real depth upgrade over the old raw-elemental-kg score. Converts a tank's (or a blend of several tanks') elemental kg composition to oxide wt%/mol% via standard stoichiometry, then computes:

- **Optical basicity Λ** (Rodriguez & McCloy, PNNL-20184 Table B.1, oxygen-weighted Duffy mixing).
- **NBO/T** (non-bridging oxygens per network-former cation) — a simplified approximation using the classical former/modifier oxide framework; does not model Al/B charge-balance by alkali. Verify against your preferred reference for publication use.
- **GlassNet property predictions** (Tg, viscosity, density, refractive index, ...; Cassar 2023, SciGlass-trained) when `glasspy` is installed — Python-run only, disabled in the packaged `.exe` (glasspy needs PyTorch, excluded from the build to keep it a reasonable size).
- **Envelope comparison** against a user-supplied `[oxide, min wt%, max wt%]` table (save/load as JSON) — shipped **empty**; Ember does not ship any hardcoded DOE/PNNL composition bounds.

The element→oxide assignment table is editable: multivalent elements (Fe, Cr, Mn, U, Np, Pu, Ce, Co) offer a dropdown of alternative oxidation states; halides and noble metals (F, Cl, Br, I, Ru, Rh, Pd, Ag, Pt, Au, Tc) are shown as elemental wt% by default rather than forced into an oxide framing that doesn't apply to them. Every default is a starting point, not an assertion — check it against your own chemistry knowledge for the specific waste stream.

### 11.3 Candidate Search

Ranks tanks by target-element content, glass-former fraction, and problem-element/penalty-element content, with `required elements` and `min total kg` filters. Same editable-weight treatment as Screening.

### 11.4 Blend Partners

Given a base tank, ranks other tanks by cosine-similarity dissimilarity to the base's composition profile, glass-former gain, and problem-element reduction — i.e. "which other tank might dilute or balance this one?" Not a blend optimization model: it does not compute a final blended composition or melt property constraints.

---

## 12. What the Vitrification tools do NOT calculate

- Real glass formulation, waste loading limits, or liquidus temperature.
- Viscosity, electrical conductivity, or thermal properties (except where GlassNet provides an ML estimate, clearly labeled as such).
- Sulfate solubility or halide volatility limits.
- Redox equilibrium or spinel/nepheline crystallization risk (beyond the coarse "potential spinel/crystallizer" element-group flag).
- PCT durability or TCLP performance.
- Official HLW/LAW/LLW waste classification (see §13).

## 13. Why Ember does not assign HLW/LAW/LLW automatically

Waste class is not determined by the columns in this CSV alone. For Hanford, low-activity waste (LAW) and high-level waste (HLW) are tied to treatment flowsheets, pretreatment, separations, legal definitions, DOE decisions, and disposal pathways. A composition table cannot determine official class. Ember shows relative screening indicators (total Ci, total kg, Ci/kg proxy, radionuclide-associated element inventory, problem-element fraction) — nothing more.

---

## 14. Debug / Export

- **Export global debug bundle** — writes a folder of small audit CSVs (overview, units/missing/phase/type/farm audits, top elements/analytes, a raw-row preview, an environment report, and a manifest). Send this instead of the full source CSV when something needs debugging.
- **Open output folder** — opens where every workspace's exports land.
- **Clear log** — clears the live app log shown below (file loads, cache writes, plot builds, exports, errors).

---

## 15. Common problems

- **A correlation looks impressively strong but is based on very few tanks** — check the overlap/N-tanks column before trusting it, and try the "control for tank size" partial-correlation checkbox to see if it survives.
- **A heatmap or pair-matrix plot is unreadable** — reduce the element/tank count, or switch to log scaling.
- **GlassNet predict is disabled** — `glasspy` (and the PyTorch it depends on) isn't installed in this environment, or you're running the packaged `.exe` (which deliberately excludes it). Run from Python with `pip install glasspy` to enable it.
- **Seaborn-based plots show "not installed"** — `pip install seaborn`; every seaborn-based plot type falls back to a clear message rather than crashing.

---

## 16. Source notes for waste terminology

Background for interpreting LAW/HLW terminology and Hanford vitrification context:

- Hanford DFLAW overview: https://www.hanford.gov/page.cfm/DFLAW
- Washington State Department of Ecology, Hanford tank waste treatment: https://ecology.wa.gov/waste-toxics/nuclear-waste/hanford-cleanup/tank-waste-management/tank-waste-treatment
- NRC high-level waste overview: https://www.nrc.gov/waste/high-level-waste
- IAEA radioactive waste classification publication: https://www.iaea.org/publications/8154/classification-of-radioactive-waste

Use these for terminology context. Do not use this app alone to make regulatory determinations.

---

## 17. Credits

Developed in the NOME group, Washington State University.
Supported by the U.S. Department of Energy.
Thanks to Prof. John S. McCloy.

Concept inspired by PNNL's Phoenix platform gallery (see the disclaimer at the top of this notice). Built on polars, pandas, numpy, matplotlib, seaborn, scipy, scikit-learn, networkx, plotly, xraydb, and PySide6. Optical basicity values: Rodriguez & McCloy, PNNL-20184/EMSP-RPT-003 (2011). GlassNet: Cassar, *Ceramics International* 49 (2023) 36013, trained on SciGlass.
