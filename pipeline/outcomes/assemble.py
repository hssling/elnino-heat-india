"""Assemble the state x year outcome panels (Phase 2a, Task 9) from every parsed source record.

Per (unit_id, year, variable) - see choose():
  1. pool within a source: rows of the same unit in one document (Andhra Pradesh + Telangana, J&K +
     Ladakh, Dadra & Nagar Haveli + Daman & Diu) are SUMMED (skipna, min_count=1: all members NaN ->
     NaN, never 0); a pool with some members NaN is marked partial_pool (shown in `sources`);
  2. the highest-rank source with a non-NaN FINAL value wins; if no source has a final value, the
     highest-rank provisional value is used (provisional=True); NaN in a higher-rank source never
     overrides a lower-rank value; no value anywhere -> NaN (source "");
  3. reviewed exceptions (pipeline/reference/outcomes_reviewed.csv, apply_reviewed): use_source:<id>
     forces that source's pooled value, mask / non_reporting set NaN (missing is not zero), keep
     changes nothing. A partial-year record (raw_label suffix records.PARTIAL_YEAR, Ruling P17) is a
     provisional value like any other here; where it would be chosen, a reviewed mask row is required
     (gate outcome_partial_year in gates.py), so no partial-year count reaches a panel.
Ranks come from outcomes_sources.csv: a higher rank is a later / annual-report document; rank 0 marks a
cross-check-only source (foodgrain_dld, Ruling P12) that stays in outcome_records_all and the
cross-source report but is never chosen for a panel.
Foodgrain (Ruling P12): foodgrain_t from the RBI tables only, 1997-2016 (to 2022 once Table 64 /
foodgrain_rbi2023 is supplied: extend OUTCOMES["foodgrain"]["years"]), for the units RBI reports
(FOODGRAIN_EXCLUDED: Andaman & Nicobar, Chandigarh, DNH & DD and Lakshadweep have no RBI row; checked by
check_scope). foodgrain_ha (DLD only) is not in the panel.

Outputs (build_all, data/derived/outcomes/): one CSV per outcome (unit_id, unit_name, year, the
variables, population, provisional_any, sources = "var:source_id;..." of the chosen values, with
"[partial_pool]" where the chosen value is a partial pool), outcome_records_all.csv.gz (every parsed
record, unmodified, with its outcome) and missing_sources.csv (sources that could not be obtained).
"""
import io
import math
import sys
import warnings
from pathlib import Path

import pandas as pd

from pipeline.outcomes import gates, records as rec_mod, states
from pipeline.paths import DERIVED
from pipeline.validate import GateResult

REF = Path(__file__).resolve().parents[1] / "reference"
SOURCES_CSV = REF / "outcomes_sources.csv"
OUT_DIR = DERIVED / "outcomes"
DEFINITION_BREAK = 2014
FOODGRAIN_EXCLUDED = ["AN", "CH", "DNH_DD", "LD"]       # no row in RBI Table 54 (Ruling P12 scope)
FOODGRAIN_UNITS = [u for u in states.UNITS if u not in FOODGRAIN_EXCLUDED]

OUTCOMES = {
    "malaria": {"file": "malaria_state_year.csv", "years": range(2002, 2026),
                "vars": ["tested", "cases", "pf", "deaths"]},
    "dengue": {"file": "dengue_state_year.csv", "years": range(2007, 2026), "vars": ["cases", "deaths"]},
    "heat_deaths": {"file": "heat_deaths_state_year.csv", "years": range(2001, 2025), "vars": ["heat_deaths"]},
    # Ruling P7: farmer-suicide panel 2001-2023 (1997-2000: scans only, missing_source)
    "farmer_suicides": {"file": "farmer_suicides_state_year.csv", "years": range(2001, 2024),
                        "vars": ["farmers", "ag_labourers", "farming_sector"]},
    "foodgrain": {"file": "foodgrain_state_year.csv", "years": range(1997, 2017), "vars": ["foodgrain_t"],
                  "units": FOODGRAIN_UNITS},
}
for _c in OUTCOMES.values():
    _c.setdefault("units", states.UNITS)
# Variables gated for completeness (a name, or (name, years) when the variable exists only in part of the
# panel years) and plausibility (split = definition-break year the rolling windows do not cross).
GATE_SPEC = {
    "malaria": {"complete": ["tested", "cases", "pf", "deaths"], "plausible": ["tested", "cases", "pf", "deaths"]},
    "dengue": {"complete": ["cases", "deaths"], "plausible": ["cases", "deaths"]},
    "heat_deaths": {"complete": ["heat_deaths"], "plausible": ["heat_deaths"]},
    "farmer_suicides": {"complete": ["farmers", "farming_sector",
                                     ("ag_labourers", list(range(DEFINITION_BREAK, 2024)))],
                        "plausible": ["farmers", "ag_labourers", "farming_sector"], "split": DEFINITION_BREAK},
    "foodgrain": {"complete": ["foodgrain_t"], "plausible": ["foodgrain_t"]},
}
for _o, _g in GATE_SPEC.items():
    _g.update(file=OUTCOMES[_o]["file"], years=list(OUTCOMES[_o]["years"]), units=list(OUTCOMES[_o]["units"]))
    _g.setdefault("split", None)


def ranks(path=SOURCES_CSV) -> dict:
    s = pd.read_csv(path)
    return {str(k): int(v) for k, v in zip(s.source_id, s["rank"])}


pool = gates.pool


def choose(records: pd.DataFrame, ranks: dict) -> pd.DataFrame:
    """One row per (unit_id, year, variable) of the non-TOTAL records: value, source_id, provisional,
    partial_pool, n_sources (sources with a value). See the module docstring for the rule."""
    p = pool(records[records.unit_id != "TOTAL"])
    unknown = sorted(set(p.source_id) - set(ranks))
    if unknown:
        raise ValueError(f"no rank for sources {unknown}")
    p = p.assign(rank=p.source_id.map(ranks), final=~p.provisional.astype(bool))
    p["has"] = p.value.notna() & (p["rank"] > 0)          # rank 0: cross-check only, never chosen
    p = p.sort_values(["unit_id", "year", "variable", "has", "final", "rank", "source_id"])
    key = ["unit_id", "year", "variable"]
    n = p.groupby(key).has.sum().rename("n_sources")
    out = p.groupby(key, sort=True).tail(1).set_index(key).join(n).reset_index()
    none = ~out.has
    out.loc[none, "source_id"] = ""
    out.loc[none, "value"] = math.nan
    out.loc[none, "provisional"] = False
    out.loc[none, "partial_pool"] = False
    out["provisional"] = out.provisional.astype(bool)
    out["partial_pool"] = out.partial_pool.astype(bool)
    out["year"] = out.year.astype(int)
    cols = ["unit_id", "year", "variable", "value", "source_id", "provisional", "partial_pool", "n_sources"]
    return out[cols].sort_values(key).reset_index(drop=True)


def apply_reviewed(chosen: pd.DataFrame, records: pd.DataFrame, reviewed, outcome: str) -> pd.DataFrame:
    """Apply the reviewed dispositions of `outcome` (rows with a unit, year and variable) to the chosen
    values: use_source:<id> -> that source's pooled value (must exist and be non-NaN); mask ->
    NaN (source "masked"); non_reporting -> NaN (source "non_reporting"; also for a unit-year that no
    source lists); keep -> unchanged."""
    rev = gates._norm_reviewed(reviewed)
    rev = rev[(rev.outcome == outcome) & (rev.year != "") & (rev.variable != "")
              & ~rev.unit_id.isin(["", "ALL", "TOTAL"]) & (rev.check != "missing_source") & (rev.disposition != "keep")]
    out = chosen.copy().set_index(["unit_id", "year", "variable"])
    pooled = pool(records[records.unit_id != "TOTAL"]).set_index(["unit_id", "year", "variable", "source_id"])
    for r in rev.itertuples():
        k = (r.unit_id, int(r.year), r.variable)
        if r.disposition.startswith("use_source:"):
            sid = r.disposition.split(":", 1)[1]
            if k + (sid,) not in pooled.index or pd.isna(pooled.loc[k + (sid,), "value"]):
                raise ValueError(f"reviewed row {k} {r.disposition}: source has no value")
            src = pooled.loc[k + (sid,)]
            out.loc[k, ["value", "source_id", "provisional", "partial_pool"]] = [
                float(src.value), sid, bool(src.provisional), bool(src.partial_pool)]
        else:
            out.loc[k, ["value", "source_id", "provisional", "partial_pool", "n_sources"]] = [
                math.nan, "masked" if r.disposition == "mask" else "non_reporting", False, False,
                out.n_sources.get(k, 0)]
    out = out.reset_index()
    out["year"] = out.year.astype(int)
    out["n_sources"] = out.n_sources.astype(int)
    out["provisional"] = out.provisional.astype(bool)
    out["partial_pool"] = out.partial_pool.astype(bool)
    return out


def check_scope(records: pd.DataFrame, source_id: str, units) -> None:
    """The units with a value in `source_id` must be exactly `units` (the declared panel scope)."""
    r = records[(records.source_id == source_id) & (records.unit_id != "TOTAL") & records.value.notna()]
    have, want = set(r.unit_id), set(units)
    if have != want:
        raise ValueError(f"{source_id}: units outside the declared scope {sorted(have - want)}, "
                         f"declared units without a value {sorted(want - have)}")


def _unit_names() -> dict:
    f = states.frame()
    return dict(zip(f.unit_id, f.unit_name))


def wide(chosen: pd.DataFrame, variables, units, years, population=None) -> pd.DataFrame:
    """unit x year panel (every unit-year row present) of `variables`, + population, provisional_any and
    sources."""
    names = _unit_names()
    base = pd.DataFrame([(u, names[u], int(y)) for u in units for y in years], columns=["unit_id", "unit_name", "year"])
    c = chosen[chosen.variable.isin(variables)]
    if "partial_pool" not in c:
        c = c.assign(partial_pool=False)
    vals = c.pivot_table(index=["unit_id", "year"], columns="variable", values="value", aggfunc="first", dropna=False)
    p = base.join(vals, on=["unit_id", "year"])
    for v in variables:
        if v not in p:
            p[v] = math.nan
    p = p[["unit_id", "unit_name", "year"] + list(variables)]
    if population is not None:
        p = p.merge(population[["unit_id", "year", "population"]], on=["unit_id", "year"], how="left")
    c = c.assign(order=c.variable.map({v: i for i, v in enumerate(variables)}))
    prov = c.groupby(["unit_id", "year"]).provisional.any()
    srcs = (c[c.source_id != ""].sort_values("order")
            .assign(s=lambda d: d.variable + ":" + d.source_id + d.partial_pool.map({True: "[partial_pool]",
                                                                                      False: ""}))
            .groupby(["unit_id", "year"]).s.agg(";".join))
    p = p.join(prov.rename("provisional_any"), on=["unit_id", "year"]).join(srcs.rename("sources"),
                                                                            on=["unit_id", "year"])
    p["provisional_any"] = p.provisional_any.fillna(False).astype(bool)
    p["sources"] = p.sources.fillna("")
    return p


def aber(p: pd.DataFrame) -> pd.Series:
    """Annual blood examination rate, % = tested / population x 100 (NaN where either is NaN)."""
    return p.tested / p.population * 100.0


def farmer_panel(chosen, units, years, population=None) -> pd.DataFrame:
    p = wide(chosen, OUTCOMES["farmer_suicides"]["vars"], units, years, population)
    p.insert(p.columns.get_loc("farming_sector") + 1, "definition_break_2014", p.year >= DEFINITION_BREAK)
    return p


# ---------------------------------------------------------------- build

def _load_records() -> tuple[dict, list]:
    """{outcome: records} and the missing sources [(outcome, source_id, reason)]."""
    from pipeline.outcomes import dengue, foodgrain, malaria, ncrb
    calls = {"malaria": malaria.all_records, "dengue": dengue.all_records, "heat_deaths": ncrb.all_heat,
             "farmer_suicides": ncrb.all_farmers, "foodgrain": foodgrain.all_records}
    out, missing = {}, []
    for outcome, fn in calls.items():
        df = fn()
        reasons = df.attrs.get("missing_reasons", {}) or {}
        for sid in df.attrs.get("missing_sources", []) or []:
            missing.append((outcome, sid, reasons.get(sid, "raw file unavailable (parser skipped the source)")))
        rec_mod.validate(df)
        out[outcome] = df
    return out, missing


def panels(recs: dict, pop: pd.DataFrame, reviewed, outcomes=None) -> dict:
    """{outcome: panel DataFrame} from records-by-outcome, population and the reviewed exceptions."""
    outcomes = OUTCOMES if outcomes is None else outcomes
    rk = ranks()
    out = {}
    for outcome, cfg in outcomes.items():
        r = recs[outcome]
        ch = apply_reviewed(choose(r, rk), r, reviewed, outcome)
        years, units = list(cfg["years"]), list(cfg["units"])
        if outcome == "farmer_suicides":
            p = farmer_panel(ch, units, years, pop)
        elif outcome == "foodgrain":
            check_scope(r, "foodgrain_rbi2019", units)
            later = r[(r.source_id == "foodgrain_rbi2023") & r.value.notna() & (r.year > max(years))]
            if len(later):
                warnings.warn(f"foodgrain_rbi2023 has values to {later.year.max()}: extend OUTCOMES['foodgrain']"
                              f"['years'] (Ruling P12)", UserWarning, stacklevel=2)
            p = wide(ch, cfg["vars"], units, years)
        else:
            p = wide(ch, cfg["vars"], units, years, pop)
            if outcome == "malaria":
                p.insert(p.columns.get_loc("population") + 1, "aber", aber(p))
        out[outcome] = p
    return out


def read_records(path) -> pd.DataFrame:
    """outcome_records_all.csv.gz -> records (with the outcome column), schema types restored."""
    r = pd.read_csv(path, dtype={"outcome": str, "unit_id": str, "raw_label": str, "variable": str,
                                 "source_id": str})
    r["year"] = r.year.astype(int)
    r["value"] = r.value.astype(float)
    r["provisional"] = r.provisional.astype(str).str.lower().isin(["true", "1"])
    return r


def reproduce_gate(out_dir=OUT_DIR, reviewed_path=gates.REVIEWED, outcomes=None) -> GateResult:
    """Rebuild every panel in memory from outcome_records_all.csv.gz + outcomes_reviewed.csv (+ the
    population file) and compare it with the panel file on disk; any difference fails."""
    out_dir = Path(out_dir)
    outcomes = OUTCOMES if outcomes is None else outcomes
    try:
        allr = read_records(out_dir / "outcome_records_all.csv.gz")
        recs = {o: allr[allr.outcome == o].drop(columns="outcome").reset_index(drop=True) for o in outcomes}
        pop = pd.read_csv(out_dir / "population_unit_year.csv")
        built = panels(recs, pop, gates.read_reviewed(reviewed_path), outcomes)
    except Exception as e:                          # a gate reports, it does not crash validation
        return GateResult("outcome_reproduce", False, f"rebuild failed: {type(e).__name__}: {e}")
    bad = []
    for o, p in built.items():
        f = out_dir / outcomes[o]["file"]
        if not f.exists():
            bad.append(f"{f.name} missing")
            continue
        want = pd.read_csv(io.StringIO(p.to_csv(index=False)))
        have = pd.read_csv(f)
        try:
            pd.testing.assert_frame_equal(have, want, check_dtype=False, check_exact=True)
        except AssertionError as e:
            first = " ".join(str(e).split())[:160]
            bad.append(f"{f.name} differs from the rebuild ({first})")
    detail = f"panels rebuilt from records + reviewed: {len(built)}"
    return GateResult("outcome_reproduce", not bad, detail + ("; " + "; ".join(bad) if bad else "; all identical"))


def build_all(out_dir=OUT_DIR, reviewed_path=gates.REVIEWED, loaded=None) -> dict:
    """Parse every source (cached raw files; missing ones downloaded where possible), choose, apply the
    reviewed exceptions and write the panels. loaded: optional (records-by-outcome, missing) to reuse."""
    from pipeline.outcomes import population
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recs, missing = loaded if loaded is not None else _load_records()
    pop = pd.read_csv(population.build(out=out_dir / "population_unit_year.csv"))
    reviewed = gates.read_reviewed(reviewed_path)
    written = {"population": out_dir / "population_unit_year.csv"}
    for outcome, p in panels(recs, pop, reviewed).items():
        path = out_dir / OUTCOMES[outcome]["file"]
        p.to_csv(path, index=False)
        written[outcome] = path
    allr = pd.concat([r.assign(outcome=o) for o, r in recs.items()], ignore_index=True)
    allr = allr[["outcome"] + rec_mod.COLUMNS]
    written["records"] = out_dir / "outcome_records_all.csv.gz"
    allr.to_csv(written["records"], index=False)
    written["missing_sources"] = out_dir / "missing_sources.csv"
    pd.DataFrame(missing, columns=["outcome", "source_id", "reason"]).to_csv(written["missing_sources"], index=False)
    return written


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        for k, v in build_all().items():
            print(k, v)
    sys.exit(0)
