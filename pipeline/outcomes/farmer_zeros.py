"""Ruling P14: uniform treatment of printed zeros in the NCRB farmer-suicide series.

For farmers, ag_labourers and farming_sector, a printed 0 for a unit-year (or for one member of a pooled
unit, e.g. Telangana inside AP_TG) is NOT REPORTED when

    lambda = mean of the 3 most recent non-zero, non-NaN values of that variable before the zero
             (taken from the same side of the 2014 definition break if any exist there, else from the
             other side)

is >= LAMBDA_MIN (5; Poisson P(0 | lambda >= 5) <= 0.7%). Otherwise it is kept as a true zero. No earlier
non-zero value -> kept. Ruling P16: when the values come from the other side of the break (a post-2014
"farmers" / "farming_sector" zero judged from the broader pre-2014 "self-employed (farming/agriculture)"
counts), lambda is scaled by the national ratio (scale_factors(): farmers(2014) / farming(2013) or
farming_sector(2014) / farming(2013); the inverse for the opposite direction); ag_labourers has no pre-2014
series, so it has no cross-break fallback (kept). Reasons state lambda_raw, the factor and lambda_scaled.
  * a unit (or a pooled unit whose members are all zero/non-reporting) -> non_reporting (panel NaN);
  * a non-reporting member of a pooled unit whose other members report -> dropped from the pool (its 0
    adds nothing) and recorded as a partial_pool keep row (Ruling P13);
  * from 2014, farming_sector = farmers + ag_labourers is non_reporting whenever either component is
    non_reporting at the unit level.
NCRB's note "Certain States/UTs ... reported zero suicides of Farmers/Cultivators as well as Agricultural
Labourers" (ADSI Table 2.7 note 2, 2016-2023; NOTES below, transcribed from the reports) is cited as
supporting evidence where it names the state; the rule applies whether or not the note names it.

zero_review(records) generates the reviewed rows (reason prefix PREFIX, lambda and the values used in
every row); merge() writes them into outcomes_reviewed.csv in place of the previous generated rows
(python -m pipeline.outcomes.farmer_zeros); rule_gate() fails when the reviewed file's generated rows
differ from what the rule gives for the current records.
"""
import sys
from pathlib import Path

import pandas as pd

from pipeline.outcomes import gates, states
from pipeline.validate import GateResult

OUTCOME = "farmer_suicides"
VARS = ("farmers", "ag_labourers", "farming_sector")
BREAK = 2014
LAMBDA_MIN = 5.0
PREFIX = "P14 printed-zero rule:"
POOLED = gates.POOLED_UNITS
# ADSI Table 2.7 note 2 (PDF page of the note in the full report; names as printed)
NOTES = {
    2016: (269, ["West Bengal", "Bihar", "Nagaland", "Chandigarh", "D & N Haveli", "Daman & Diu", "Delhi UT",
                 "Lakshadweep"]),
    2017: (269, ["West Bengal", "Uttarakhand", "Odisha", "Manipur", "Mizoram", "Nagaland", "Chandigarh",
                 "D & N Haveli", "Daman & Diu", "Delhi UT", "Lakshadweep", "Puducherry"]),
    2018: (271, ["West Bengal", "Uttarakhand", "Odisha", "Bihar", "Meghalaya", "Goa", "Chandigarh", "Daman & Diu",
                 "Delhi UT", "Lakshadweep", "Puducherry"]),
    2019: (269, ["West Bengal", "Bihar", "Odisha", "Uttarakhand", "Manipur", "Chandigarh", "Daman & Diu",
                 "Delhi UT", "Lakshadweep", "Puducherry"]),
    2020: (271, ["West Bengal", "Bihar", "Odisha", "Uttarakhand", "Manipur", "Chandigarh", "Daman & Diu",
                 "Delhi UT", "Lakshadweep", "Puducherry"]),
    2021: (271, ["West Bengal", "Bihar", "Jharkhand", "Odisha", "Tripura", "Manipur", "Arunachal Pradesh",
                 "Uttarakhand", "Chandigarh", "Lakshadweep", "Puducherry"]),
    2022: (271, ["Bihar", "Goa", "Manipur", "Mizoram", "Odisha", "Tripura", "Uttarakhand", "West Bengal",
                 "Chandigarh", "Delhi", "Lakshadweep", "Puducherry"]),
    2023: (271, ["Arunachal Pradesh", "Bihar", "Goa", "Himachal Pradesh", "Jharkhand", "Manipur", "Mizoram",
                 "Nagaland", "Odisha", "Tripura", "West Bengal", "Chandigarh", "Delhi", "Lakshadweep"]),
}


def reference(series: dict, year: int):
    """(years used, raw lambda, crossed) for a zero at `year`: up to 3 most recent non-zero non-NaN values
    before it, same side of BREAK if any, else the other side (crossed=True); ([], None, False) if none."""
    side = year >= BREAK
    prior = [(y, v) for y, v in sorted(series.items()) if y < year and pd.notna(v) and v != 0]
    same = [(y, v) for y, v in prior if (y >= BREAK) == side]
    other = [(y, v) for y, v in prior if (y >= BREAK) != side]
    use, crossed = (same, False) if same else (other, bool(other))
    use = use[-3:]
    if not use:
        return [], None, False
    return [y for y, _ in use], sum(v for _, v in use) / len(use), crossed


def scale_factors(records: pd.DataFrame) -> dict:
    """Ruling P16: national ratios used when lambda comes from the other side of the 2014 break -
    farmers: farmers(2014) / farming(2013); farming_sector: farming_sector(2014) / farming(2013), where
    farming(2013) is the pre-2014 'self-employed (farming/agriculture)' all-India total (TOTAL rows)."""
    t = records[records.unit_id == "TOTAL"].groupby(["variable", "year"]).value.sum(min_count=1)
    base = t.get(("farmers", BREAK - 1))
    out = {}
    for var in ("farmers", "farming_sector"):
        top = t.get((var, BREAK))
        if base is not None and top is not None and pd.notna(base) and pd.notna(top) and base > 0:
            out[var] = float(top) / float(base)
    return out


class Lam:
    """lambda for one zero: raw mean, scale factor (1 unless the values come from the other side of the
    break) and scaled value; years = the years used."""

    def __init__(self, years, raw, factor, crossed):
        self.years, self.raw, self.factor, self.crossed = years, raw, factor, crossed
        self.scaled = raw * factor

    def text(self, var: str) -> str:
        if not self.crossed:
            return f"lambda = mean of the most recent non-zero values before it = {self.scaled:.2f}"
        side = "pre-2014" if max(self.years) < BREAK else "post-2014"
        what = (f"national {var} {BREAK} / farming {BREAK - 1}" if max(self.years) < BREAK
                else f"inverse of national {var} {BREAK} / farming {BREAK - 1}")
        return (f"lambda from {side} values (other side of the {BREAK} definition break): lambda_raw {self.raw:.2f} "
                f"x scale factor {self.factor:.4f} ({what}) = lambda_scaled {self.scaled:.2f}")


def lam(series: dict, year: int, var: str, factors: dict):
    """Lam for a zero of `var` at `year`, or None (no earlier non-zero value, or a cross-break fallback for
    ag_labourers, which has no pre-2014 series)."""
    years, raw, crossed = reference(series, year)
    if raw is None:
        return None
    factor = 1.0
    if crossed:
        if var == "ag_labourers":
            return None
        if var not in factors:
            raise ValueError(f"cross-break lambda for {var} needs the national scale factor (TOTAL rows "
                             f"{BREAK - 1}/{BREAK}); none available")
        factor = factors[var] if max(years) < BREAK else 1.0 / factors[var]
    return Lam(years, raw, factor, crossed)


def _note(unit: str, year: int):
    if year not in NOTES:
        return ""
    page, names = NOTES[year]
    hits = [n for n in names if states.resolve(n) == unit]
    if not hits:
        return ""
    return (f"; ADSI {year} Table 2.7 note 2 (p{page}) names {' / '.join(hits)} among States/UTs that 'reported "
            f"zero suicides of Farmers/Cultivators as well as Agricultural Labourers'")


def _series(df) -> dict:
    s = df.groupby("year").value.sum(min_count=1)
    return {int(y): float(v) for y, v in s.items()}


def _verdict(series: dict, year: int, var: str, factors: dict):
    lm = lam(series, year, var, factors)
    return (lm is not None and lm.scaled >= LAMBDA_MIN), lm


def _vals(series, lm) -> str:
    return ", ".join(f"{y} {series[y]:g}" for y in lm.years)


def zero_review(records: pd.DataFrame, factors: dict | None = None) -> pd.DataFrame:
    """Reviewed rows (outcomes_reviewed.csv columns) that the P14/P16 rule gives for these farmer records.
    factors: cross-break scale factors (default scale_factors(records), from the TOTAL rows)."""
    factors = scale_factors(records) if factors is None else factors
    r = records[(records.unit_id != "TOTAL") & records.variable.isin(VARS)]
    dup = r.groupby(["unit_id", "raw_label", "year", "variable"]).source_id.nunique()
    if (dup > 1).any():
        raise ValueError(f"farmer records: several sources for {dup[dup > 1].index[:3].tolist()}")
    out, nonrep = [], {}
    for (unit, var), g in r.groupby(["unit_id", "variable"]):
        unit_s = _series(g)
        members = {lab: _series(m) for lab, m in g.groupby("raw_label")} if unit in POOLED else {}
        for year, v in sorted(unit_s.items()):
            src = g[g.year == year].source_id.iloc[0]
            mem_nr = []
            for lab, ms in members.items():
                if ms.get(year) == 0:
                    bad, lm = _verdict(ms, year, var, factors)
                    if bad:
                        mem_nr.append((lab, lm, ms))
            present = [lab for lab, ms in members.items() if pd.notna(ms.get(year, float("nan")))]
            unit_bad, ulm = _verdict(unit_s, year, var, factors) if v == 0 else (False, None)
            all_members_bad = bool(members) and len(mem_nr) == len(present) and len(present) > 0
            if unit_bad or (v == 0 and all_members_bad):
                if not unit_bad:            # unit lambda < 5 but every member's own history says not reported
                    lab, lm, ms = mem_nr[0]
                    basis = f"members {', '.join(m[0] for m in mem_nr)} (e.g. {lab}: {_vals(ms, lm)})"
                else:
                    lm, basis = ulm, _vals(unit_s, ulm)
                nonrep[(unit, year, var)] = True
                out.append(dict(outcome=OUTCOME, unit_id=unit, year=year, variable=var, source_id=src,
                                check="completeness", disposition="non_reporting",
                                reason=f"{PREFIX} {unit} {year} {var} printed 0; {lm.text(var)} >= {LAMBDA_MIN:g} "
                                       f"-> not reported (panel NaN; the printed 0 stays in outcome_records_all)",
                                evidence=f"{src} {unit} {year} {var} = 0; values used: {basis}{_note(unit, year)}"))
            elif mem_nr:
                lab, lm, ms = mem_nr[0]
                out.append(dict(outcome=OUTCOME, unit_id=unit, year=year, variable=var, source_id=src,
                                check="completeness", disposition="keep",
                                reason=f"{PREFIX} partial_pool: member {lab} {year} {var} printed 0; {lm.text(var)} "
                                       f">= {LAMBDA_MIN:g} -> not reported and dropped from the pool; the {unit} "
                                       f"value ({v:g}) is the other members' sum (Ruling P13)",
                                evidence=f"{src} {lab} {year} {var} = 0; {lab} values used: {_vals(ms, lm)}"
                                         f"{_note(unit, year)}"))
    # from 2014: farming_sector non_reporting when a component is non_reporting at the unit level
    for (unit, year, var) in list(nonrep):
        if var == "farming_sector" or year < BREAK or (unit, year, "farming_sector") in nonrep:
            continue
        g = r[(r.unit_id == unit) & (r.year == year) & (r.variable == "farming_sector")]
        if g.empty:
            continue
        comps = [c for c in ("farmers", "ag_labourers") if (unit, year, c) in nonrep]
        nonrep[(unit, year, "farming_sector")] = True
        out.append(dict(outcome=OUTCOME, unit_id=unit, year=year, variable="farming_sector",
                        source_id=g.source_id.iloc[0], check="completeness", disposition="non_reporting",
                        reason=f"{PREFIX} {unit} {year} farming_sector = farmers + ag_labourers and its component "
                               f"{' and '.join(comps)} is not reported -> farming_sector NaN",
                        evidence=f"{g.source_id.iloc[0]} {unit} {year} farming_sector = {g.value.sum(min_count=1):g}; "
                                 f"see the {' / '.join(comps)} row(s) of {unit} {year}"))
    cols = gates.REVIEWED_COLUMNS
    df = pd.DataFrame(out, columns=cols)
    return df.sort_values(["unit_id", "year", "variable"]).reset_index(drop=True)


def _generated(reviewed) -> pd.DataFrame:
    r = gates._norm_reviewed(reviewed)
    return r[r.reason.str.startswith(PREFIX)]


def merge(reviewed: pd.DataFrame, generated: pd.DataFrame) -> pd.DataFrame:
    """reviewed rows with the previous generated rows replaced by `generated`."""
    r = gates._norm_reviewed(reviewed)
    keep = r[~r.reason.str.startswith(PREFIX)]
    return pd.concat([keep, gates._norm_reviewed(generated)], ignore_index=True)


def rule_gate(records: pd.DataFrame, reviewed) -> GateResult:
    """The reviewed file's generated (P14) rows must be exactly what the rule gives for the records."""
    key = ["unit_id", "year", "variable", "disposition"]
    want = {tuple(x) for x in gates._norm_reviewed(zero_review(records))[key].values}
    have = {tuple(x) for x in _generated(reviewed)[key].values}
    missing, extra = sorted(want - have), sorted(have - want)
    detail = (f"printed-zero rule (lambda >= {LAMBDA_MIN:g}): non_reporting="
              f"{sum(1 for k in want if k[3] == 'non_reporting')} partial_pool keep="
              f"{sum(1 for k in want if k[3] == 'keep')}")
    if missing:
        detail += "; missing from reviewed: " + ", ".join(f"{u} {y} {v} ({d})" for u, y, v, d in missing)
    if extra:
        detail += "; not given by the rule: " + ", ".join(f"{u} {y} {v} ({d})" for u, y, v, d in extra)
    return GateResult("outcome_farmer_zero_rule", not missing and not extra, detail)


def write(records: pd.DataFrame, path=gates.REVIEWED) -> int:
    """Replace the generated rows of outcomes_reviewed.csv with the rule's rows for `records`."""
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    gen = zero_review(records)
    merge(old, gen).to_csv(path, index=False)
    return len(gen)


if __name__ == "__main__":
    recs = pd.read_csv(gates.DERIVED / "outcomes" / "outcome_records_all.csv.gz")
    recs = recs[recs.outcome == OUTCOME].drop(columns="outcome")
    print(write(recs), "generated rows written to", gates.REVIEWED)
    sys.exit(0)
