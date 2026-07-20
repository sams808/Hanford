# Ember — detailed user notice

This notice describes the desktop application in depth: what each workspace
does, what each control means, the exact formulas behind every score and
property, how to interpret the plots, how to export data, and — most
importantly — what the vitrification screening tools can and cannot tell
you. If you only read one section beyond this page, read §12 (Vitrification)
before you rely on any glass-related number Ember produces.

Ember is a **visual exploration and screening tool** for Hanford tank
composition data. It is not a regulatory classifier, not a glass
formulation model, not a thermodynamic database, and not a waste
loading/property predictor. Its goal is to help you quickly answer
questions like:

- Which tanks contain a given element or analyte, and how much?
- What other elements tend to appear in the same tanks?
- Which elements correlate across tanks, and how much of that is just
  tank-size effects?
- Which tanks look chemically/radiologically similar, or cluster together?
- What would a tank's composition look like converted to oxide (glass)
  chemistry, and roughly how "basic" or "polymerized" would that glass be?
- Which tanks may be interesting starting points for blending or
  vitrification screening — as a first pass, not a final answer?
- How do I turn several of these plots into one figure for a report or
  slide deck?

The bundled composition data (`Hanford.csv`, `Tank_attributes.csv`) comes
from PNNL's [PHOENIX](https://phoenix.pnnl.gov) (Hanford Online Information
Exchange), the access mechanism for Tri-Party Agreement tank waste
databases:

> Brulotte, P.J., and Christensen, K.C.. "Tri-Party Agreement databases,
> access mechanism and procedures". United States. doi:10.2172/10112540.
> https://www.osti.gov/servlets/purl/10112540
>
> "PNNL Hanford Online Information Exchange (PHOENIX)", Pacific Northwest
> National Laboratory, Richland WA, U.S. Department of Energy.
> https://phoenix.pnnl.gov

**Ember (this application) is an independent project and is not produced
by, affiliated with, or endorsed by PNNL or the U.S. Department of
Energy.**

> **Credit placeholder:** lab/PI attribution below is a starting draft
> (mirrors the sibling Dataapp/PRISM project's credits) — confirm the exact
> wording before treating it as final.

---

## 1. Installation and launch

Three ways to run Ember, depending on who you are:

- **Standalone, no install** — unzip the portable build and double-click
  `Ember.exe`. Nothing else needs to be installed; the composition data is
  bundled inside the zip next to the executable. This is the form meant
  for colleagues who don't code.
- **From source, with Python** — `py -3.11 qt_main.py`, or double-click
  `Ember.bat` (tries `pyw` first for a windowless launch, falls back to
  `py`).
- **Build your own `.exe`** — `build_exe.bat` (PyInstaller). See the
  README for the exact command and the dependency-exclusion list.

### 1.1 Input files

Ember expects two files next to it (already the case for both the git
repo and the portable zip — you don't need to supply your own copies
unless you want to analyze a different export):

- `Hanford.csv` — composition data with columns `WasteSiteId, Analyte,
  WastePhase, WasteType, Inventory, Units` (required) plus optional
  `Inventory_RSD, Volume, VolumeUnits, VolumeRSD, ComponentDensity,
  DensityUnits, AdjustedConcentration, AdjustedConcentrationUnits,
  DecayDate, PublishedDate, CCBLog`.
- `Tank_attributes.csv` — tank metadata (`Name`/`WasteSiteId`, `TankType`,
  `Capacity`, `TankStatus`, `TankIntegrity`, ...), joined onto the
  composition data. Optional; Ember runs without it, just with less tank
  metadata available.

Ember can also open `.csv`, `.tsv`, `.txt`, and `.parquet`/`.pq` files via
**Load CSV/Parquet…**, so you can point it at an updated PHOENIX export
without editing anything.

---

## 2. General architecture

The nav sidebar has 9 workspaces:

1. **Overview**
2. **Element Explorer**
3. **Tank Attributes**
4. **Tank Explorer**
5. **Heatmaps**
6. **Correlations** — Quick Scan / Association Workbench (kg) / Structure sub-tabs
7. **Vitrification** — Screening / Oxide Chemistry / Candidate Search / Blend Partners sub-tabs
8. **Figure Composer** — combine any of the plots above into one multi-panel publication figure
9. **Debug / Export**

Most plots can be saved directly via the plot panel's own toolbar
(PNG/PDF/SVG, pan/zoom). Every workspace also exports the actual data
tables behind its plots as CSV. This matters in two ways: first, when a
plot looks wrong, you don't need to send the giant source CSV — export the
debug bundle or the workspace-specific tables and send those; second, the
exported tables are the right starting point if you want to reproduce a
plot in your own analysis software.

Every `PlotWidget` (the panel each plot renders into) also has a **"→
Figure Composer"** button next to its toolbar — click it on any plot you
want to include in a combined figure, then switch to the Figure Composer
workspace to arrange, label, and export the panel grid (§13).

---

## 3. Top toolbar

- **Load local CSVs** — auto-detects `Hanford.csv`/`Tank_attributes.csv`
  next to the app (or in the current folder). Runs automatically on
  startup too.
- **Load CSV/Parquet…** — opens a file picker for any supported file.
- **Reload** — reloads the currently loaded file (F5). Use after replacing
  the input file on disk.
- **Use parquet cache** — reuses a cleaned Parquet cache if one already
  exists next to the source CSV, for much faster reloads (loading the raw
  46,894-row CSV and re-parsing every analyte takes noticeably longer than
  reading the cache).
- **Refresh cache** — ignores any existing cache and rebuilds it from the
  original CSV. Use after the source CSV changes, or if you suspect the
  cache is stale (different schema version, etc.).
- **Open output folder** — opens the folder (`ember_outputs/` next to the
  app) where every workspace writes its exports.

---

## 4. Data conventions that matter everywhere

### 4.1 Units are never blindly mixed

The dataset carries two fundamentally different inventory units: `kg`
(chemical mass) and `Ci` (radioactivity, curies). These cannot be summed
or averaged together as if equivalent — 1 kg of stable sodium and 1 Ci of
cesium-137 are not comparable quantities in any physical sense. Most Ember
workspaces are unit-specific by design; the kg-only Correlations sub-tabs
(Association Workbench, Structure) and the entire Vitrification tab are
deliberately kg-only for exactly this reason — mixing Ci and kg into one
tank×element matrix would be scientifically meaningless, not just
inconvenient.

### 4.2 Element parsing from analytes

The source `Analyte` column is not a clean element list — it's a mix of
isotope notations (`137Cs`, `113mCd`, `239/240Pu`), organic-compound names
(`Total Alpha`, benzene, chloroform, various nitrosamines and phthalates),
and a few dead/placeholder columns. Ember's parser converts these to
element symbols conservatively, specifically to avoid false positives
(e.g. the string `TotalAlpha` does **not** parse to element `Al`, even
though it contains that substring). Combined-isotope slash notation
(`239/240Pu`, `243/244Cm`) is handled explicitly rather than silently
dropped.

When a multi-element analyte label is parsed, the **first** parsed element
receives the analyte's full inventory value — this attribution rule
matches the app's predecessor tool and is disclosed here because it
changes every downstream number for those specific rows. It's a
simplification, not a claim that 100% of that inventory chemically belongs
to only that element. Always check the raw analyte rows in Tank Explorer
(§9) when an element total looks surprising.

### 4.3 `(WasteSiteId, Analyte)` is not a unique key

The same tank/analyte pair can appear multiple times across different
`WastePhase` rows (e.g. separate entries for the liquid and solid phase of
the same tank/analyte). Every aggregation in Ember sums across duplicates
rather than assuming one row per tank×analyte — a naive `groupby().first()`
or a plain lookup would silently under-count.

---

## 5. Overview

A first sanity check of the loaded dataset: row/column counts, a units
audit (which units appear and how many rows use each), a missing-value
audit, waste-phase/type/farm breakdowns, and a "top elements by inventory"
bar chart (Top N adjustable, capped in height to whatever's visible in the
panel so labels stay legible even at Top N = 40+). **Check the units audit
before trusting anything downstream** — if a unit you don't expect shows
up, stop and investigate before building on it.

---

## 6. Element Explorer

The main search workspace, with five distinct search modes so you can find
what you're looking for whichever way you think of it:

- **Element symbol** — exact match on the parsed element (e.g. `Cs`).
- **Exact analyte** — exact match on the raw, unparsed `Analyte` string
  (e.g. `137Cs`, useful when you specifically care about one isotope, not
  the whole element).
- **Analyte contains** — substring match on the raw analyte string.
- **Analyte regex** — full regular-expression match, for anything the
  first three modes can't express.

Results show: which tanks contain the target, co-elements/co-analytes
found alongside it in the same tanks, and composition statistics reported
**two different ways that answer two different questions** — don't
conflate them:

- Absolute mean/stdev inventory — "how much of this element is typically
  present, in the tanks that have it."
- Tank-normalized fraction mean/stdev — "what share of each tank's total
  inventory does this element typically represent."

Seven plot types are available for the current search result (bar charts,
scatter against total inventory, correlation-scan style views); each one
respects the same Top N / unit controls as the table.

## 7. Tank Attributes

Browses `Tank_attributes.csv` directly: tank type, capacity, integrity,
DST/SST status, and audits by category (counts and totals grouped by any
categorical column). This is metadata about the tanks themselves — not
composition — so it works even if the composition CSV can't answer a
question (e.g. "how many double-shell tanks are there").

## 8. Tank Explorer

The inverse of Element Explorer: select one or more tanks (filterable by
farm) and inspect their full composition, the **raw, unparsed rows**
behind that composition (the single most useful place to check the §4.2
element-attribution rule when a number looks off), and a grouped
composition plot comparing the selected tanks side by side.

## 9. Heatmaps

Tank × element inventory matrices, with three value modes:

- **raw** — inventory value as-is.
- **log10_inventory** — log10 of the inventory (zeros become undefined/blank
  cells, not zero — a log10 of zero doesn't exist).
- **log10_plus1** — log10(inventory + 1), which keeps zero-inventory cells
  visible as a real (near-minimum) value instead of blank, useful when
  "this element is genuinely absent from this tank" is itself information
  you want to see on the map.

Restricted to the top-N elements by total inventory (adjustable) to stay
readable; the figure's own size scales with how many tanks/elements are
shown, capped at whatever's actually visible in the panel so nothing gets
silently clipped off-screen.

---

## 10. Correlations

Three sub-tabs, all built on the same underlying tank×element pivot
(`element_inventory_matrix`) so results between them are directly
comparable.

### 10.1 Quick Scan

A **target-element scan** (how does one element of interest correlate with
every other element across tanks), a **dual/triple pairwise correlation**
(a specific handful of elements plotted against each other), and a
**full correlation-matrix heatmap** (lower-triangle only — a correlation
matrix is symmetric about its diagonal, so the upper triangle is pure
redundancy and only makes the plot harder to read).

Controls that change what the correlation is actually measuring:

- **Metric**: `inventory` (raw) / `log10_inventory` (zeros become
  undefined) / `log10_plus1` (zeros retained) / `fraction` (each element's
  share of that tank's total) / `presence` (1 if present, 0 if absent —
  turns "correlation" into "how often do these two elements co-occur").
- **Method**: `pearson` (linear correlation) / `spearman` (rank
  correlation — more robust to outliers and nonlinear-but-monotonic
  relationships).
- **include zeros** / **min overlap** / **min inv** — control which tanks
  and element pairs count at all, before any correlation is computed.

**Always check the overlap count before trusting a strong correlation** —
`r = 1.0` computed from only 3 overlapping tanks is a clue to investigate
further, not a conclusion you can act on.

**Control for tank size** checkbox: strips out the "everything correlates
because both elements just scale with how big the tank is" effect, via
partial correlation controlling for each tank's total same-unit inventory
(closed-form: `r_AB.Z = (r_AB − r_AZ·r_BZ) / sqrt((1−r_AZ²)(1−r_BZ²))`
with `Z` = each tank's total inventory, or log10 of it). When checked, the
table's `Correlation_r` column becomes this partial correlation and
`Raw_Correlation_r` shows the uncontrolled value alongside it, so you can
directly see how much of the raw correlation was a tank-size artifact.

### 10.2 Association Workbench (kg)

Kg-only element-association screening (Ci is deliberately excluded — see
§4.1): per-element stats, pairwise **Jaccard co-presence**
(`n_both / n_either` — what fraction of tanks that have *either* element
have *both*), and a `PreferredAssociationScore_proxy`
(`max(r, 0) · ln(1 + n_both) · jaccard`) that rewards element pairs that
are both positively correlated *and* frequently found together, and never
rewards a merely-negative correlation (a real absence relationship is
still informative, but it's not what this particular score is designed to
surface). 17 plot types (heatmaps, top-association bar charts, pair
scatter matrices, tank-similarity and tank×element maps, presence-pattern
plots, and a combined stats dashboard), with a Basic/Coherent-colors theme
toggle for consistent color families across all of them.

### 10.3 Structure

New capability, no equivalent in earlier versions of this tool:

- **PCA + hierarchical clustering** of tanks over a standardized kg
  element matrix — a scatter of the first two principal components
  (color-by TankFarm/TankType/TankSystem/TankStatus/Dominant waste phase)
  and a cross-checkable dendrogram (do the two views agree on which tanks
  group together?).
- **Partial correlation matrix**, side-by-side with the raw correlation
  matrix, showing directly how much of each pairwise correlation is a
  tank-size artifact (same math as the Quick Scan checkbox, applied to the
  whole matrix at once).
- **Element-association network graph** — nodes sized by total kg, edges
  thresholded by minimum |r| and minimum Jaccard co-presence (both
  user-adjustable), edge color by correlation sign.
- **Export interactive HTML** — writes the correlation heatmap, PCA
  scatter, and network graph as self-contained interactive Plotly HTML
  files (the JavaScript is embedded, not loaded from a CDN, so they work
  fully offline — useful for sharing on a network without internet access)
  and opens the folder.

---

## 11. Debug / Export

- **Export global debug bundle** — writes a folder of small audit CSVs
  (overview, units/missing/phase/type/farm audits, top elements/analytes,
  a raw-row preview, an environment report, and a manifest). Send this
  instead of the full source CSV when something needs debugging.
- **Open output folder** — opens where every workspace's exports land.
- **Clear log** — clears the live app log shown below (file loads, cache
  writes, plot builds, exports, errors).

---

## 12. Vitrification

Four sub-tabs covering everything from a quick chemical/radiological
screening score to real oxide-basis glass chemistry. Read this whole
section before trusting a number from here — **every score in this
workspace is a transparent screening heuristic, built from ordinary
chemistry and simple weighted sums, not an official glass formulation
model, thermodynamic calculation, or waste classification** (§14 has the
full, explicit list of what these tools do *not* calculate).

The reason this workspace exists in this form: raw elemental kg inventory
(what the source CSV actually contains) is not what glass scientists
think in. Glass composition, structure, and most of the properties that
matter for vitrification (viscosity, durability, crystallization
tendency, melting behavior) are conventionally described in **oxide
weight or mole percent** — SiO₂, Na₂O, B₂O₃, and so on — not in kg of
elemental Fe or Na. The Oxide Chemistry sub-tab (§12.2) is the bridge
between what the data gives you and what the glass-science literature and
your own intuition actually reason about.

### 12.1 Screening

One row per tank, built entirely from **elemental** kg/Ci fractions (no
oxide conversion needed for this sub-tab — see §12.2 for that). Seven
element groups are defined, each with a specific glass-relevant reason for
being tracked separately:

| Group | Elements | Why it matters |
|---|---|---|
| `glass_former_or_intermediate` | B, Si, P, Al, Zr, Ti | The elements that can build the glass network itself (formers) or participate in it under the right conditions (intermediates) — more of this, generally, means an easier path to a stable glass. |
| `alkali_alkaline_modifier` | Li, Na, K, Mg, Ca, Sr, Ba | Network modifiers — they break up (depolymerize) the glass network, lowering viscosity and melting temperature, but too much can hurt durability. |
| `transition_redox_sensitive` | Fe, Cr, Mn, Ni, Cu, Ce, U, Np, Pu, Tc | Elements whose oxidation state (and therefore glass behavior, color, and sometimes volatility) depends on the melt's redox conditions — a flag for "this tank's glass chemistry may be redox-sensitive," not a redox calculation. |
| `volatile_halide_sulfate` | F, Cl, Br, I, S, Se, Tc, Cs | Elements/species prone to volatilizing out of the melt or having limited solubility (sulfate/halide/chalcogenide chemistry) — a real, well-known glass-processing headache at high concentration. |
| `nuclear_key_radionuclide_elements` | Cs, Sr, Tc, I, Se, U, Np, Pu, Am, Cm, Eu, Sm, Y, Ba | The elements most often tracked for radiological/dose reasons in Hanford tank waste discussions — used for the Ci-side of the screening score, not for any dose calculation itself. |
| `platinum_group_or_noble` | Ru, Rh, Pd, Ag, Re, Os, Ir, Pt, Au | Platinum-group/noble metals — chemically inert in most glass melts, but can form metallic/alloy precipitates (a real processing concern) rather than dissolving into the network. |
| `potential_spinels_or_crystallizers` | Cr, Fe, Ni, Mn, Zn, Zr, Mo, P, Al | Elements associated with spinel or other crystalline phases that can form on cooling — a coarse composition-based flag, not a crystallization-kinetics prediction. |

`problem_elements_proxy` is the union of `volatile_halide_sulfate` with
`{Cr, Mo, P, Ru, Rh, Pd, Ag}` — the single "elements that tend to make
vitrification harder" bucket used in the score below.

**The screening score**, with its actual default weights:

```
score = 60·frac_glass_former_or_intermediate
      + 25·frac_alkali_alkaline_modifier
      − 45·frac_problem_elements_proxy
      − 25·frac_volatile_halide_sulfate
      − 10·frac_transition_redox_sensitive
```

clipped to [−100, 100]. Every one of those five numbers (60, 25, −45, −25,
−10) is now an editable `QDoubleSpinBox` in the UI, with a "Reset to
defaults" button showing these original constants — they were buried in
code in the app's predecessor; here they're visible and adjustable next to
the score they produce, so you can see exactly how sensitive the ranking
is to your own judgment about what matters most.

`frac_*` values are each group's share of the tank's **total kg
inventory** (not oxide-converted) — except when the **basis** toggle is
set to `oxide`, which swaps *only* the glass-former term to the oxide-wt%
glass-former fraction computed in §12.2 (SiO₂+B₂O₃+P₂O₅+Al₂O₃'s combined
share of the tank's oxide-converted composition); every other term stays
elemental. This matters because the elemental-kg glass-former fraction and
the oxide-wt% glass-former fraction can meaningfully disagree — a kg of Al
metal and a kg of Si both count equally in the elemental basis, but
convert to very different amounts of oxide (different molar masses,
different stoichiometry), so the oxide basis is arguably the more
chemically honest of the two once you have it available.

Also reported: `Ci_per_kg_proxy` (total Ci ÷ total kg, a coarse
activity-density indicator) and `RelativeActivityBin` (the dataset's tanks
split into 4 quartiles — low/medium-low/medium-high/high — by that same
ratio, purely for quick relative sorting, not an absolute classification).

### 12.2 Oxide Chemistry

The real depth upgrade over the old app's "glass calculation," which never
left raw elemental kg. This sub-tab is the missing first step (elemental
kg → oxide wt%/mol%) that everything else in glass science — optical
basicity, NBO/T, melting/viscosity models, GlassNet — actually expects as
input.

**Workflow:** pick a farm (optional filter) → select one or more tanks
(selecting 2+ also builds a "Blend (selected tanks)" sample) → **Build
oxide composition** → review/edit the element→oxide assignment table →
**Recompute basicity / NBO-T / envelope** whenever you change an
assignment, a role, or the envelope table.

#### 12.2.1 Element → oxide conversion

For each element with a positive kg inventory in the selected tank(s),
Ember:

1. Converts kg to grams, and looks up (or lets you override) which oxide
   formula that element is assumed to form.
2. Computes the molar mass of the element and the oxide via `xraydb`
   (a standard, well-established X-ray/atomic-data library — not a
   hand-rolled periodic table).
3. Converts the element's mass to moles, divides by how many atoms of that
   element the oxide formula contains, and multiplies back up by the
   oxide's molar mass — ordinary stoichiometric mass-balance, nothing
   probabilistic or fitted.
4. Reports the result as both **wt%** and **mol%** of the total converted
   composition (both are commonly used in different corners of the glass
   literature, so both are always shown together).

The default element→oxide table covers essentially every element with a
tabulated optical-basicity value (§12.2.2) plus explicit non-oxide flags:

- **Multivalent elements** (Fe, Cr, Mn, U, Np, Pu, Ce, Co) get one
  pre-selected default oxide *and* a dropdown of chemically reasonable
  alternatives right there in the table — e.g. Fe defaults to Fe₂O₃ but
  can be switched to FeO, U defaults to UO₃ but can be switched to UO₂ or
  U₃O₈. Real tank waste redox state is not something this table can know;
  picking the right oxidation state for your specific waste stream is a
  judgment call the tool deliberately leaves to you, with the mechanism
  ready either way.
- **Halides and noble/platinum-group metals** (F, Cl, Br, I, Ru, Rh, Pd,
  Ag, Pt, Au, Tc) default to **no oxide** — they're reported as elemental
  wt%/mol% instead, because forcing them into an oxide framing that
  doesn't chemically apply would be actively misleading, not just
  imprecise.
- **Every cell in the table is directly editable**, including elements not
  in either special list — nothing here is a hard-coded assumption you
  can't see or change.

**Blend mode** (2+ tanks selected): the elemental kg from every selected
tank is summed together **first**, and the combined total is converted to
oxides **once** — this is what physically mixing those tanks' contents
would actually produce. It is deliberately *not* an average of each tank's
independently-computed oxide percentages, which would give the wrong
answer whenever the tanks have different total masses (a small tank and a
huge tank don't contribute equally to a real blend just because you
selected both).

#### 12.2.2 Optical basicity (Λ)

Optical basicity is a single number, conventionally between roughly 0.3
(strongly acidic network formers like B₂O₃/P₂O₅) and 1.5+ (strongly basic
modifiers like Cs₂O/BaO), that summarizes how much a glass's oxide mixture
behaves like an electron-density donor (basic) versus acceptor (acidic) —
originally developed to predict UV absorption edge shifts, and now used
more broadly as a quick composition-based proxy that tends to correlate
with things like sulfate/chromate retention, redox equilibria position,
and general "how forgiving is this melt chemistry" intuition. It is a
useful *screening* number precisely because it's cheap to compute from
composition alone — it is not a substitute for a real thermodynamic redox
or solubility model.

Ember computes it via the standard oxygen-weighted (Duffy) mixing rule:

```
Λ = Σ(xᵢ · nO,ᵢ · Λᵢ) / Σ(xᵢ · nO,ᵢ)
```

— molar fraction `xᵢ` of each oxide, weighted by how many oxygen atoms
`nO,ᵢ` that oxide contributes per formula unit, times that oxide's own
tabulated basicity `Λᵢ`. The per-oxide Λᵢ values are the **recommended**
values (Λrec) from Table B.1 of Rodriguez & McCloy, *"Optical basicity and
nepheline crystallization in high alumina glasses,"* PNNL-20184 /
EMSP-RPT-003 (2011) — itself a careful reconciliation of five earlier
sources (Duffy & Ingram 1976; Duffy 2002–2006; Dimitrov & Sakka 1996;
Lebouteiller & Courtine 1998; Lenglet 2004; Mills 1995). This is real,
citable literature data, copied verbatim into Ember — not re-derived or
approximated.

Not every oxide Ember can convert to has a tabulated Λrec value (most
notably, no PNNL-20184 value exists for any plutonium oxide). Rather than
silently dropping those components or crashing, the summary panel lists
exactly which formulas were **excluded from the basicity calculation**
alongside the number itself, so you always know whether Λ represents the
whole composition or only part of it.

#### 12.2.3 NBO/T (non-bridging oxygens per network-forming cation)

NBO/T is a structural indicator, not a thermodynamic property: it
estimates, on average, how many of the oxygen atoms attached to each
network-forming cation (Si, B, P, Al in the classical formalism) are
"non-bridging" — bonded to only one network cation, versus "bridging" —
linking two network cations together into the connected 3D network that
gives silicate/borate/phosphate glasses their structural rigidity. Higher
NBO/T means a more broken-up, depolymerized network (generally lower
viscosity, lower melting/working temperature, faster crystallization
kinetics); lower NBO/T means a more fully connected, polymerized network
(generally higher viscosity, more sluggish/harder-to-crystallize melt).
It's a widely used first-order structural intuition in the glass
literature, not a viscosity or Tg prediction on its own.

Ember uses the classical **former/modifier** framework:

- **Formers** (contribute network-forming T-cations): SiO₂ (1 Si per
  formula unit), B₂O₃ (2 B), P₂O₅ (2 P), Al₂O₃ (2 Al).
- **Modifiers** (break the network, contribute non-bridging oxygen but no
  T-cations): the alkalis (Li₂O, Na₂O, K₂O, Rb₂O, Cs₂O) and alkaline
  earths (MgO, CaO, SrO, BaO).
- Every other oxide/element ("other" role — transition metals, halides,
  actinides, rare earths, ...) is excluded from the NBO/T calculation
  entirely, because its network role is genuinely composition- and
  context-dependent and isn't captured by this simple two-bucket
  formalism. Those components still appear in the main composition table
  and in the optical-basicity calculation; they're only left out of this
  one specific number.

Formula:

```
T       = Σ(molᵢ · T-cations per formula unit) over former-role oxides
O_total = Σ(molᵢ · oxygens per formula unit) over former + modifier oxides
NBO/T   = (O_total − 2·T) / T
```

**Every oxide's role (former/modifier/other) is editable** in its own
table — if you disagree with a default classification for your specific
system, change it and recompute.

This is explicitly a **simplified approximation**: it does not model
charge-balance effects where Al³⁺ or B³⁺ can act as either a former or a
network-modifying species depending on how much alkali is available to
charge-compensate it (the well-known "aluminum avoidance" / boron
anomaly problems in real aluminosilicate and borosilicate glasses). Verify
against your preferred reference or a more detailed structural model
before using an NBO/T number from here in a publication.

#### 12.2.4 GlassNet property prediction

When the optional `glasspy` package is installed, **GlassNet predict**
runs a pretrained machine-learning model (Cassar, *Ceramics International*
49 (2023) 36013) against the current sample's oxide mol% composition and
returns its predicted glass properties — including glass transition
temperature, density, refractive index, and viscosity at multiple
temperatures, among others GlassNet reports. The model was trained on
**SciGlass**, a large curated database of real measured glass properties;
its predictions are only as reliable as that training data's coverage of
compositions similar to yours — treat a GlassNet number for a composition
far outside typical oxide-glass chemistry (e.g. dominated by exotic
actinide oxides) with real skepticism, the same way you would any ML
model extrapolating outside its training distribution.

`glasspy` needs PyTorch, which is a large dependency deliberately
**excluded from the packaged `.exe`** to keep the standalone download a
reasonable size — this button is disabled (with an explanatory tooltip) in
that build. Run Ember from Python with `pip install glasspy` to enable it.
The first prediction after launch is slower than subsequent ones (the
model itself has to load into memory once).

#### 12.2.5 Envelope comparison

A per-oxide `[oxide, min wt%, max wt%]` table you build yourself — **Ember
ships this empty, with zero hardcoded DOE/PNNL/WTP composition bounds**.
This is a deliberate choice, not an oversight: baking in a specific
regulatory or process-envelope specification from memory would risk
silently embedding an outdated or simply misremembered number into a
domain where that could matter. Build your own envelope from whatever
specification you're actually screening against (an internal WTP glass
formulation envelope, a DOE contract requirement, your own group's target
window, ...), save it as JSON (**Save JSON…**) so you can reuse it across
sessions and share it with colleagues, and load it back with **Load
JSON…**.

Once loaded, every oxide in either the envelope or the current
composition is checked and reported with an explicit status: **Pass**
(within bounds), **Fail** (outside bounds), or **Not specified** (present
in the composition but the envelope has no bound for it — reported
explicitly rather than silently skipped, since "no bound specified" and
"passes because it's low" are very different situations). An oxide
specified in the envelope but absent from the composition is checked as
0 wt%, so a nonzero minimum correctly fails.

### 12.3 Candidate Search

Ranks tanks by how well they match a target/penalty-element search, using
the same tank-category summary as Screening (§12.1) plus per-target/
per-penalty element fractions in both kg and Ci (so a search for, say,
Cs/Sr/Tc still works even when those nuclides live primarily in the Ci
table rather than the kg table). `required elements` filters out any tank
missing at least one required element entirely (in either unit); `min
total kg` filters out tanks below a minimum total inventory.

```
score = 100 · (0.50·target_fraction_sum + 0.25·glass_former_fraction
             − 0.20·problem_fraction − 0.30·penalty_fraction_sum)
```

— `target_fraction_sum`/`penalty_fraction_sum` are each the sum of the
kg-fraction and Ci-fraction across all your target/penalty elements for
that tank. Same editable-weight treatment as Screening (0.50, 0.25, −0.20,
−0.30 are all `QDoubleSpinBox` controls with "Reset to defaults"), and the
same elemental/oxide **basis** toggle for the glass-former term.

### 12.4 Blend Partners

Given one base tank, ranks every other tank by how good a **blend
partner** it might be — i.e. "which other tank's composition might dilute
or balance out this one?" Not a blend optimization: it does not compute a
final blended composition, a mixing ratio, or any melt property
constraint on the result — for an actual blend composition, build it
yourself in Oxide Chemistry (§12.2) by selecting the tanks you're
considering together (which physically sums their kg before converting,
exactly as a real blend would).

```
complement_score = 100 · (0.35·max(glass_former_gain, 0)
                         + 0.35·max(problem_reduction, 0)
                         + 0.20·(1 − cosine_similarity)
                         + 0.10·glass_former_fraction_partner)
```

- `glass_former_gain` = partner's glass-former fraction − base tank's
  (only rewarded if positive — a partner that *lowers* the glass-former
  fraction doesn't help).
- `problem_reduction` = base tank's problem-element fraction − partner's
  (only rewarded if positive, i.e. the partner is comparatively cleaner).
- `cosine_similarity` is computed between the two tanks' full
  element-fraction profile vectors — `1 − similarity` is highest for the
  *most chemically different* partner, on the reasoning that a very
  similar tank has little to offer that the base tank doesn't already
  have.
- The glass-former fraction term uses the same elemental/oxide **basis**
  toggle as the other three sub-tabs.

---

## 13. Figure Composer

A tool for combining several already-built plots from anywhere in Ember
into one multi-panel figure, laid out and labeled the way a publication
or slide-deck figure usually is (bold panel letters in the corner: A, B,
C, ...). This is a general-purpose panel arranger — it doesn't care what
kind of plot each panel is, so you can freely mix, say, a scatter plot
from Element Explorer with a heatmap from Correlations and a bar chart
from Vitrification into one figure.

**Workflow:**

1. Build any plot you want as a panel, anywhere in Ember.
2. Click **"→ Figure Composer"** on that plot's toolbar. This captures a
   high-resolution snapshot of exactly what's currently drawn (so the
   panel's contents don't change later if you go build something else in
   the source workspace) and adds it to the Figure Composer's gallery,
   along with a suggested caption drawn from the plot's own title.
3. Repeat for every panel you want in the final figure — from any
   workspace, in any order.
4. Switch to the **Figure Composer** workspace. The gallery on the left
   lists every captured panel with an editable caption, reorder
   (move up/down) and remove controls.
5. Set the layout: number of columns (or leave on **auto** to let Ember
   pick a reasonable grid for however many panels you have), panel-label
   style (`A, B, C`, `a, b, c`, `(a), (b), (c)`, `1, 2, 3`, or **none**),
   and label size.
6. The preview updates live as you change the gallery or layout.
7. **Export** at a specific physical size and DPI (PNG/PDF/SVG/TIFF) —
   the same exact-size export path every other plot in Ember uses, so a
   composed figure prints at the size you actually specified, not
   whatever size happened to be on screen.

Each panel is composited as a high-resolution raster image inside the
combined figure (not re-plotted from scratch) — this is what lets Figure
Composer combine *any* plot type, including ones with their own colorbars,
legends, or seaborn-specific styling, without needing to understand or
reconstruct each plot's internal structure. Capture each panel at the
resolution you want in the final figure (the source `PlotWidget`'s own
toolbar controls the on-screen figure size, and the capture is taken at
300 DPI regardless of the on-screen zoom level) — recapture (send it to
the composer again) if you change a source plot's styling, size, or data
afterward, since the composer holds a snapshot, not a live link back to
the original.

---

## 14. What the Vitrification tools do NOT calculate

Worth restating plainly, in one place:

- Real glass formulation, waste loading limits, or liquidus temperature.
- Viscosity, electrical conductivity, or thermal properties in general
  (except where GlassNet provides an ML *estimate*, always clearly
  labeled as such and only when `glasspy` is installed).
- Sulfate solubility or halide volatility *limits* (optical basicity and
  the volatile-element flag are composition-based indicators that
  correlate with these behaviors in the literature, not a solubility or
  volatility calculation).
- Redox equilibrium, or spinel/nepheline crystallization risk, beyond the
  coarse composition-based element-group flags in §12.1.
- PCT durability or TCLP performance.
- Official HLW/LAW/LLW waste classification (see §15).
- A final blend composition or mixing ratio (Blend Partners ranks
  candidates; building the actual blend composition is a manual step in
  Oxide Chemistry, §12.2).

## 15. Why Ember does not assign HLW/LAW/LLW automatically

Waste class is not determined by the columns in this CSV alone. For
Hanford, low-activity waste (LAW) and high-level waste (HLW) are tied to
treatment flowsheets, pretreatment, separations, legal definitions, DOE
decisions, and disposal pathways — none of which live in a composition
table. A composition table cannot determine official class, no matter how
sophisticated the composition-based heuristic. Ember shows relative
screening indicators (total Ci, total kg, Ci/kg proxy, radionuclide-
associated element inventory, problem-element fraction) — nothing more,
and nothing that should be read as a classification.

---

## 16. Common problems

- **A correlation looks impressively strong but is based on very few
  tanks** — check the overlap/N-tanks column before trusting it, and try
  the "control for tank size" partial-correlation checkbox (§10.1) to see
  if it survives.
- **A heatmap or pair-matrix plot is unreadable** — reduce the
  element/tank count, or switch to log scaling.
- **GlassNet predict is disabled** — `glasspy` (and the PyTorch it depends
  on) isn't installed in this environment, or you're running the packaged
  `.exe` (which deliberately excludes it). Run from Python with `pip
  install glasspy` to enable it.
- **Seaborn-based plots show "not installed"** — `pip install seaborn`;
  every seaborn-based plot type falls back to a clear message rather than
  crashing.
- **Optical basicity shows "Excluded from Λ"** for one of your
  components — that oxide has no tabulated PNNL-20184 value (plutonium
  oxides, most notably). The number shown is still computed correctly
  over everything that *does* have a value; the exclusion list tells you
  what's missing so you can judge whether that matters for your case.
- **NBO/T shows "n/a (no former-role oxide present)"** — the selected
  composition (or your edited role table) has no oxide classified as a
  network former, so `T` is zero and the ratio is undefined by
  construction, not a bug.
- **A Figure Composer panel looks stale after I changed the source plot**
  — the composer holds a snapshot from when you clicked "→ Figure
  Composer," not a live link. Remove the old panel and send the plot
  again after changing it.

---

## 17. Source notes for waste terminology

Background for interpreting LAW/HLW terminology and Hanford vitrification
context:

- Hanford DFLAW overview: https://www.hanford.gov/page.cfm/DFLAW
- Washington State Department of Ecology, Hanford tank waste treatment:
  https://ecology.wa.gov/waste-toxics/nuclear-waste/hanford-cleanup/tank-waste-management/tank-waste-treatment
- NRC high-level waste overview: https://www.nrc.gov/waste/high-level-waste
- IAEA radioactive waste classification publication:
  https://www.iaea.org/publications/8154/classification-of-radioactive-waste

Use these for terminology context. Do not use this app alone to make
regulatory determinations.

---

## 18. Credits

Developed in the NOME group, Washington State University.
Supported by the U.S. Department of Energy.
Thanks to Prof. John S. McCloy.

Composition data via PNNL's PHOENIX (see the citation at the top of this
notice). Built on polars, pandas, numpy, matplotlib, seaborn, scipy,
scikit-learn, networkx, plotly, xraydb, and PySide6. Optical basicity
values: Rodriguez & McCloy, PNNL-20184/EMSP-RPT-003 (2011). GlassNet:
Cassar, *Ceramics International* 49 (2023) 36013, trained on SciGlass.
