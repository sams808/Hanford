"""
vitrification_science.py — Vitrification "Screening" / "Candidate Search" /
"Blend Partners" scoring (framework-agnostic). Ported from the old app's
HanfordDataModel (tank_category_summary, vitrification_candidate_search,
blend_partner_search), restructured as plain functions over a
HanfordDataset. Same explicit framing as the old app: transparent
screening heuristics, NOT an official glass model or waste-classification
tool (see WASTE_CLASS_NOTES).

Rethought per the plan: every hardcoded weight is now a function parameter
(the old constant is its default) rather than buried in the formula — the
Qt layer exposes these as QDoubleSpinBox controls with "reset to
defaults". Screening/candidate/blend results can also report each tank's
OXIDE-basis glass-former wt% (via oxide_science, new capability) alongside
the legacy elemental-kg fraction the old app used exclusively, selected
via a basis="elemental"|"oxide" toggle.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import polars as pl

from data_model import HanfordDataset
from elements import normalize_element_symbol
from matrix_science import element_inventory_matrix

VITRIFICATION_GROUPS: Dict[str, List[str]] = {
    "glass_former_or_intermediate": ["B", "Si", "P", "Al", "Zr", "Ti"],
    "alkali_alkaline_modifier": ["Li", "Na", "K", "Mg", "Ca", "Sr", "Ba"],
    "transition_redox_sensitive": ["Fe", "Cr", "Mn", "Ni", "Cu", "Ce", "U", "Np", "Pu", "Tc"],
    "volatile_halide_sulfate": ["F", "Cl", "Br", "I", "S", "Se", "Tc", "Cs"],
    "nuclear_key_radionuclide_elements": ["Cs", "Sr", "Tc", "I", "Se", "U", "Np", "Pu", "Am", "Cm", "Eu", "Sm", "Y", "Ba"],
    "platinum_group_or_noble": ["Ru", "Rh", "Pd", "Ag", "Re", "Os", "Ir", "Pt", "Au"],
    "potential_spinels_or_crystallizers": ["Cr", "Fe", "Ni", "Mn", "Zn", "Zr", "Mo", "P", "Al"],
}

VITRIFICATION_PROBLEM_ELEMENTS = sorted(set(
    VITRIFICATION_GROUPS["volatile_halide_sulfate"] + ["Cr", "Mo", "P", "Ru", "Rh", "Pd", "Ag"]
))

WASTE_CLASS_NOTES = [
    {
        "topic": "Hanford tank waste classification",
        "note": "Hanford tank waste is historically treated as high-level radioactive waste, but current treatment separates low-activity waste (LAW) fractions from high-level waste (HLW) fractions through pretreatment and regulatory decisions. Do not infer official HLW/LAW/LLW class from this composition table alone.",
    },
    {
        "topic": "HLW definition, US context",
        "note": "In US usage, HLW generally includes spent fuel accepted for disposal and waste remaining after spent-fuel reprocessing. Hanford defense tank waste is tied to reprocessing history, but disposal pathway and reclassification are legal/regulatory questions, not just chemistry.",
    },
    {
        "topic": "LAW / low-activity waste",
        "note": "LAW is a Hanford process stream: tank waste pretreated to remove much of the high-activity radionuclide burden before vitrification or other treatment. It is not equivalent to saying the original tank is harmless or chemically easy to vitrify.",
    },
    {
        "topic": "App classification output",
        "note": "The app provides relative screening metrics such as total Ci, Ci/kg, volatile/problem-element fraction, and glass-former fraction. These are engineering screening flags, not official waste class assignments.",
    },
]

# Old app's hardcoded weights, now defaults for the Qt layer's editable spin boxes.
SCREENING_WEIGHT_DEFAULTS: Dict[str, float] = {
    "glass_former_weight": 60.0, "modifier_weight": 25.0,
    "problem_weight": -45.0, "volatile_weight": -25.0, "redox_weight": -10.0,
}
CANDIDATE_WEIGHT_DEFAULTS: Dict[str, float] = {
    "target_weight": 0.50, "glass_former_weight": 0.25,
    "problem_weight": -0.20, "penalty_weight": -0.30,
}
BLEND_WEIGHT_DEFAULTS: Dict[str, float] = {
    "glass_former_gain_weight": 0.35, "problem_reduction_weight": 0.35,
    "dissimilarity_weight": 0.20, "glass_former_weight": 0.10,
}


def waste_class_notes() -> pd.DataFrame:
    return pd.DataFrame(WASTE_CLASS_NOTES)


def vitrification_group_definitions() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Group": k, "Elements": "; ".join(v)} for k, v in VITRIFICATION_GROUPS.items()]
        + [{"Group": "problem_elements_proxy", "Elements": "; ".join(VITRIFICATION_PROBLEM_ELEMENTS)}]
    )


def tank_element_fraction_table(dataset: HanfordDataset, unit: str = "kg") -> pd.DataFrame:
    mat = element_inventory_matrix(dataset, unit=unit, value_mode="inventory", include_all_tanks=True)
    if mat.empty:
        return mat
    vals = mat.set_index("WasteSiteId")
    denom = vals.sum(axis=1).replace(0.0, np.nan)
    return vals.div(denom, axis=0).reset_index()


def oxide_glass_former_fractions(dataset: HanfordDataset) -> pd.Series:
    """Per-tank oxide-basis glass-former wt% fraction (0-1), indexed by
    WasteSiteId -- the FORMER_OXIDES' (SiO2/B2O3/P2O5/Al2O3) combined
    share of the tank's full oxide-converted kg composition. The
    oxide-basis alternative to the elemental-kg
    frac_glass_former_or_intermediate column below (basis="oxide")."""
    import oxide_science as oxsci

    df = dataset.require_df().filter((pl.col("Units") == "kg") & pl.col("Element").is_not_null())
    if df.is_empty():
        return pd.Series(dtype=float)
    grouped = df.group_by(["WasteSiteId", "Element"]).agg(pl.col("Inventory").sum().alias("Inventory")).to_pandas()
    out: Dict[str, float] = {}
    for tank, sub in grouped.groupby("WasteSiteId"):
        element_kg = dict(zip(sub["Element"], sub["Inventory"]))
        table = oxsci.convert_composition_to_oxides(element_kg)
        if table.empty:
            out[tank] = 0.0
            continue
        former_mask = (table["Kind"] == "oxide") & table["Component"].isin(oxsci.FORMER_OXIDES)
        out[tank] = float(table.loc[former_mask, "Wt_pct"].sum()) / 100.0
    return pd.Series(out)


def tank_category_summary(
    dataset: HanfordDataset, weights: Optional[Dict[str, float]] = None, basis: str = "elemental",
) -> pd.DataFrame:
    """One row per tank with chemical/radiological screening features and
    the vitrification screening score (a transparent heuristic, NOT a
    glass property model). basis="oxide" swaps the glass-former term from
    elemental-kg fraction to oxide-basis wt% fraction (see
    oxide_glass_former_fractions); every other term is unaffected."""
    w = dict(SCREENING_WEIGHT_DEFAULTS)
    if weights:
        w.update(weights)

    df = dataset.require_df().filter((pl.col("Inventory") > 0) & pl.col("Element").is_not_null())
    if df.is_empty():
        return pd.DataFrame()
    kg = df.filter(pl.col("Units") == "kg")
    ci = df.filter(pl.col("Units") == "Ci")

    def group_sum(frame: pl.DataFrame, elements: Sequence[str], col_name: str) -> pl.DataFrame:
        # Both call sites below are already guarded by "if not kg/ci.is_empty()",
        # and polars group_by/agg on a zero-row (post-filter) frame still
        # yields the right (WasteSiteId, col_name) schema, so no separate
        # empty-input branch is needed here.
        return (
            frame.filter(pl.col("Element").is_in(list(elements)))
            .group_by("WasteSiteId")
            .agg(pl.col("Inventory").sum().alias(col_name))
        )

    all_tanks = pd.DataFrame({"WasteSiteId": dataset.available_tanks()})
    farm = dataset.require_df().select(["WasteSiteId", "TankFarm"]).unique().to_pandas()
    out = all_tanks.merge(farm, on="WasteSiteId", how="left")

    if not kg.is_empty():
        kg_total = kg.group_by("WasteSiteId").agg(pl.col("Inventory").sum().alias("Total_kg_inventory")).to_pandas()
        out = out.merge(kg_total, on="WasteSiteId", how="left")
        for name, elems in VITRIFICATION_GROUPS.items():
            pdf = group_sum(kg, elems, f"kg_{name}").to_pandas()
            out = out.merge(pdf, on="WasteSiteId", how="left")
        prob = group_sum(kg, VITRIFICATION_PROBLEM_ELEMENTS, "kg_problem_elements_proxy").to_pandas()
        out = out.merge(prob, on="WasteSiteId", how="left")
    if not ci.is_empty():
        ci_total = ci.group_by("WasteSiteId").agg(pl.col("Inventory").sum().alias("Total_Ci_inventory")).to_pandas()
        out = out.merge(ci_total, on="WasteSiteId", how="left")
        ci_key = group_sum(ci, VITRIFICATION_GROUPS["nuclear_key_radionuclide_elements"], "Ci_key_radionuclide_elements").to_pandas()
        out = out.merge(ci_key, on="WasteSiteId", how="left")

    numeric_cols = [c for c in out.columns if c not in ("WasteSiteId", "TankFarm")]
    for c in numeric_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    total_kg = out.get("Total_kg_inventory", pd.Series(0.0, index=out.index)).replace(0.0, np.nan)
    for c in [c for c in out.columns if c.startswith("kg_")]:
        out[c.replace("kg_", "frac_")] = out[c] / total_kg
    out["Ci_per_kg_proxy"] = out.get("Total_Ci_inventory", 0.0) / total_kg
    try:
        out["RelativeActivityBin"] = pd.qcut(
            out["Ci_per_kg_proxy"].replace([np.inf, -np.inf], np.nan).fillna(0.0).rank(method="first"),
            q=4, labels=["low relative", "medium-low relative", "medium-high relative", "high relative"],
        ).astype(str)
    except Exception:
        out["RelativeActivityBin"] = "not enough tanks"

    if basis == "oxide":
        oxide_gf = oxide_glass_former_fractions(dataset)
        out["frac_glass_former_or_intermediate_oxide_basis"] = out["WasteSiteId"].map(oxide_gf).fillna(0.0)
        gf = out["frac_glass_former_or_intermediate_oxide_basis"]
    else:
        gf = out["frac_glass_former_or_intermediate"].fillna(0.0) if "frac_glass_former_or_intermediate" in out.columns else pd.Series(0.0, index=out.index)
    mod = out["frac_alkali_alkaline_modifier"].fillna(0.0) if "frac_alkali_alkaline_modifier" in out.columns else pd.Series(0.0, index=out.index)
    prob = out["frac_problem_elements_proxy"].fillna(0.0) if "frac_problem_elements_proxy" in out.columns else pd.Series(0.0, index=out.index)
    vol = out["frac_volatile_halide_sulfate"].fillna(0.0) if "frac_volatile_halide_sulfate" in out.columns else pd.Series(0.0, index=out.index)
    redox = out["frac_transition_redox_sensitive"].fillna(0.0) if "frac_transition_redox_sensitive" in out.columns else pd.Series(0.0, index=out.index)
    raw_score = (
        w["glass_former_weight"] * gf + w["modifier_weight"] * mod
        + w["problem_weight"] * prob + w["volatile_weight"] * vol + w["redox_weight"] * redox
    )
    out["Vitrification_screening_score_proxy"] = raw_score.clip(lower=-100, upper=100)
    out["Important_warning"] = "Screening metric only; not an official waste classification or glass formulation model"
    return out.sort_values("Vitrification_screening_score_proxy", ascending=False).reset_index(drop=True)


def vitrification_candidate_search(
    dataset: HanfordDataset, target_elements: Sequence[str], penalty_elements: Sequence[str],
    required_elements: Sequence[str], min_total_kg: float = 0.0, top_n: int = 50,
    weights: Optional[Dict[str, float]] = None, basis: str = "elemental",
) -> pd.DataFrame:
    """Rank tanks for glass-development screening. Scores combine chemical
    fractions in kg and radiological fractions in Ci so a search for
    Cs/Sr/Tc still works even when those nuclides are primarily in the Ci
    inventory table."""
    w = dict(CANDIDATE_WEIGHT_DEFAULTS)
    if weights:
        w.update(weights)

    summary = tank_category_summary(dataset, basis=basis)
    frac_kg = tank_element_fraction_table(dataset, "kg")
    frac_ci = tank_element_fraction_table(dataset, "Ci")
    if summary.empty:
        return pd.DataFrame()
    target = [normalize_element_symbol(e) for e in target_elements if normalize_element_symbol(e)]
    penalty = [normalize_element_symbol(e) for e in penalty_elements if normalize_element_symbol(e)]
    required = [normalize_element_symbol(e) for e in required_elements if normalize_element_symbol(e)]

    out = summary.copy()

    def rename_frac_cols(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame({"WasteSiteId": out["WasteSiteId"]})
        renamed = frame.copy()
        return renamed.rename(columns={c: f"{c}_{suffix}" for c in renamed.columns if c != "WasteSiteId"})

    out = out.merge(rename_frac_cols(frac_kg, "kg_frac"), on="WasteSiteId", how="left")
    out = out.merge(rename_frac_cols(frac_ci, "Ci_frac"), on="WasteSiteId", how="left")

    for e in target + penalty + required:
        for suffix in ("kg_frac", "Ci_frac"):
            col = f"{e}_{suffix}"
            if col not in out.columns:
                out[col] = 0.0
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out["UserTargetChemicalFraction_sum"] = out[[f"{e}_kg_frac" for e in target]].sum(axis=1) if target else 0.0
    out["UserTargetRadiologicalFraction_sum"] = out[[f"{e}_Ci_frac" for e in target]].sum(axis=1) if target else 0.0
    out["UserPenaltyChemicalFraction_sum"] = out[[f"{e}_kg_frac" for e in penalty]].sum(axis=1) if penalty else 0.0
    out["UserPenaltyRadiologicalFraction_sum"] = out[[f"{e}_Ci_frac" for e in penalty]].sum(axis=1) if penalty else 0.0
    out["UserTargetFraction_sum"] = out["UserTargetChemicalFraction_sum"] + out["UserTargetRadiologicalFraction_sum"]
    out["UserPenaltyFraction_sum"] = out["UserPenaltyChemicalFraction_sum"] + out["UserPenaltyRadiologicalFraction_sum"]
    out["RequiredElementsPresent"] = True
    for e in required:
        out["RequiredElementsPresent"] &= (out[f"{e}_kg_frac"].fillna(0.0) > 0) | (out[f"{e}_Ci_frac"].fillna(0.0) > 0)
    out = out[out["Total_kg_inventory"].fillna(0.0) >= float(min_total_kg)]
    out = out[out["RequiredElementsPresent"]]

    gf_col = "frac_glass_former_or_intermediate_oxide_basis" if basis == "oxide" else "frac_glass_former_or_intermediate"
    gf = out[gf_col].fillna(0.0) if gf_col in out.columns else pd.Series(0.0, index=out.index)
    prob = out["frac_problem_elements_proxy"].fillna(0.0) if "frac_problem_elements_proxy" in out.columns else pd.Series(0.0, index=out.index)
    target_score = out["UserTargetFraction_sum"].fillna(0.0)
    penalty_score = out["UserPenaltyFraction_sum"].fillna(0.0)
    out["User_search_score_proxy"] = 100.0 * (
        w["target_weight"] * target_score + w["glass_former_weight"] * gf
        + w["problem_weight"] * prob + w["penalty_weight"] * penalty_score
    )

    useful_cols = [
        "WasteSiteId", "TankFarm", "Total_kg_inventory", "Total_Ci_inventory", "Ci_per_kg_proxy",
        "RelativeActivityBin", "User_search_score_proxy", "Vitrification_screening_score_proxy",
        "UserTargetFraction_sum", "UserTargetChemicalFraction_sum", "UserTargetRadiologicalFraction_sum",
        "UserPenaltyFraction_sum", "UserPenaltyChemicalFraction_sum", "UserPenaltyRadiologicalFraction_sum",
        "frac_glass_former_or_intermediate", "frac_alkali_alkaline_modifier", "frac_problem_elements_proxy",
        "frac_volatile_halide_sulfate", "frac_transition_redox_sensitive", "Important_warning",
    ]
    if "frac_glass_former_or_intermediate_oxide_basis" in out.columns:
        useful_cols.append("frac_glass_former_or_intermediate_oxide_basis")
    for e in target + penalty + required:
        for suffix in ("kg_frac", "Ci_frac"):
            col = f"{e}_{suffix}"
            if col in out.columns and col not in useful_cols:
                useful_cols.append(col)
    useful_cols = [c for c in useful_cols if c in out.columns]
    return out[useful_cols].sort_values("User_search_score_proxy", ascending=False).head(int(top_n)).reset_index(drop=True)


def blend_partner_search(
    dataset: HanfordDataset, base_tank: str, top_n: int = 50, unit: str = "kg",
    weights: Optional[Dict[str, float]] = None, basis: str = "elemental",
) -> pd.DataFrame:
    w = dict(BLEND_WEIGHT_DEFAULTS)
    if weights:
        w.update(weights)

    frac = tank_element_fraction_table(dataset, unit)
    summary = tank_category_summary(dataset, basis=basis)
    if frac.empty or base_tank not in set(frac["WasteSiteId"]):
        return pd.DataFrame()
    vals = frac.set_index("WasteSiteId")

    gf_col = "frac_glass_former_or_intermediate_oxide_basis" if basis == "oxide" else "frac_glass_former_or_intermediate"
    base = vals.loc[base_tank].fillna(0.0).astype(float)
    base_row = summary[summary["WasteSiteId"] == base_tank]
    base_prob = float(base_row["frac_problem_elements_proxy"].fillna(0.0).iloc[0]) if not base_row.empty and "frac_problem_elements_proxy" in base_row else 0.0
    base_gf = float(base_row[gf_col].fillna(0.0).iloc[0]) if not base_row.empty and gf_col in base_row else 0.0

    rows = []
    for tank, vec in vals.iterrows():
        if tank == base_tank:
            continue
        v = vec.fillna(0.0).astype(float)
        denom = np.linalg.norm(base.values) * np.linalg.norm(v.values)
        sim = float(np.dot(base.values, v.values) / denom) if denom > 0 else np.nan
        # `tank` comes from `vals` (frac reindexed to every dataset tank);
        # `summary` is independently built from the same dataset.available_tanks()
        # list, so `pair` always has exactly one row here -- no empty guard needed.
        pair = summary[summary["WasteSiteId"] == tank]
        gf = float(pair[gf_col].fillna(0.0).iloc[0]) if gf_col in pair else 0.0
        prob = float(pair["frac_problem_elements_proxy"].fillna(0.0).iloc[0]) if "frac_problem_elements_proxy" in pair else 0.0
        glass_gain = gf - base_gf
        problem_reduction = base_prob - prob
        complement_score = 100.0 * (
            w["glass_former_gain_weight"] * max(glass_gain, 0.0)
            + w["problem_reduction_weight"] * max(problem_reduction, 0.0)
            + w["dissimilarity_weight"] * (1.0 - sim if pd.notna(sim) else 0.0)
            + w["glass_former_weight"] * gf
        )
        rows.append({
            "BaseTank": base_tank, "PartnerTank": tank, "Units": unit,
            "CosineSimilarity_to_base_fraction_profile": sim,
            "GlassFormerFraction_partner": gf, "ProblemFraction_partner": prob,
            "GlassFormerFraction_base": base_gf, "ProblemFraction_base": base_prob,
            "GlassFormerGain_vs_base": glass_gain, "ProblemReduction_vs_base": problem_reduction,
            "Blend_complement_score_proxy": complement_score,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.merge(
        summary[["WasteSiteId", "TankFarm", "Total_kg_inventory", "Total_Ci_inventory", "Ci_per_kg_proxy", "RelativeActivityBin"]],
        left_on="PartnerTank", right_on="WasteSiteId", how="left",
    ).drop(columns=["WasteSiteId"])
    return out.sort_values("Blend_complement_score_proxy", ascending=False).head(int(top_n)).reset_index(drop=True)
