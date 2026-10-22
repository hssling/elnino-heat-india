"""State foodgrain production 1997-2023 (t) for the drought-food pathway.

Variables (records schema, see records.py):
  foodgrain_t   production, tonnes ('000 tonnes x 1000)
  foodgrain_ha  area, hectares ('000 ha x 1000) -- DLD only
Year convention: agricultural year "Y-(Y+1)" -> calendar year Y (its kharif season is the JJAS
monsoon of year Y). Verified for the DLD against the RBI table (DLD 2012 Punjab 28,550 vs RBI
2012-13 28,543 '000 t).

Sources
  foodgrain_rbi2019 (rank 1)  RBI "Handbook of Statistics on Indian States" (March 2019), Table 54
      "State-wise Production of Foodgrains - Total Foodgrains" ('000 tonnes; MoA&FW DES source),
      1990-91..2016-17, three blocks of 9 years; the PDF is read with `pdftotext -layout`. Column
      header line "States/Union Territories  1990-91 ... "; rows from the first state to the
      "ALL INDIA" row (TOTAL). "." = not applicable (Telangana before 2011-12, Chhattisgarh/
      Jharkhand/Uttarakhand before 2000-01, i.e. inside their parent states) -> NaN. Fetched from
      the Internet Archive capture of the RBI PDF.
  foodgrain_rbi2023 (rank 2: later edition)  same handbook, Nov 2023 edition, Table 64,
      2004-05..2022-23 (2022-23 = 3rd advance estimate -> provisional). OPTIONAL local file:
      rbidocs.rbi.org.in puts a human-verification (CAPTCHA) page in front of the file and the
      Internet Archive snapshot is that page, so it is never downloaded; place the PDF at
      RAW_ROOT/foodgrain_rbi2023/<file name> by hand.
      Absent -> source skipped with a warning (missing_sources). Its layout is assumed identical to
      Table 54 (header line + state rows + ALL INDIA); this is unverified.
  foodgrain_dld (rank 0: cross-check only, never in the panel; Ruling P12)  ICRISAT-TCI District
      Level Database (CC BY 4.0), "apportioned" (2011 district boundaries) area-production-yield
      JSON from the DLD's public API; district rows summed to the state. The DLD has no foodgrain
      total: foodgrain = RICE + WHEAT + SORGHUM + PEARL MILLET +
      MAIZE + FINGER MILLET + BARLEY + CHICKPEA + PIGEONPEA + MINOR PULSES (area and production). It
      omits small millets and "other cereals", so it is a LOWER BOUND of the official foodgrain total.
      -1 = missing in the DLD: any -1 component in a state-year makes that state-year NaN.
      20 states (no J&K, NE except Assam).
Pooling: Andhra Pradesh + Telangana etc. rows of one unit are summed (NaN-aware: a "." part is
treated as absent, all-NaN stays NaN), raw_label = " + ".join(labels).
"""
import json
import math
import re
import warnings
from pathlib import Path

import pandas as pd

from pipeline.outcomes import fetch, records, states, textable
from pipeline.paths import ROOT

DLD_URL = "http://data.icrisat.org/dldAPI/apportioned/area-production-yield"
DLD_FILE = "dld_apportioned_area_production_yield.json"
RBI_BASE = "https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/"
WAYBACK2019 = "https://web.archive.org/web/20250822230316id_/" + RBI_BASE
RBI_FILES = {"foodgrain_rbi2019": "54TABLEA93F71A7ED764906B8575187B1A88681.PDF",
             "foodgrain_rbi2023": "64T_15112023FA45A663E56549F98199708AE35A02F0.PDF"}
RBI_URLS = {"foodgrain_rbi2019": WAYBACK2019 + RBI_FILES["foodgrain_rbi2019"],
            "foodgrain_rbi2023": RBI_BASE + RBI_FILES["foodgrain_rbi2023"]}
PROVISIONAL = {"foodgrain_rbi2023": {2022}}          # 3rd advance estimates
YEARS = range(1997, 2024)
DLD_CROPS = ["RICE", "WHEAT", "SORGHUM", "PEARL MILLET", "MAIZE", "FINGER MILLET", "BARLEY",
             "CHICKPEA", "PIGEONPEA", "MINOR PULSES"]
_AGYEAR = re.compile(r"^(\d{4})-(\d{2})$")
_HDR = re.compile(r"^\s*States?\s*/\s*Union Territories\b", re.I)
SOURCES = {"foodgrain_rbi2019": {"url": RBI_URLS["foodgrain_rbi2019"], "rank": 1},
           "foodgrain_rbi2023": {"url": RBI_URLS["foodgrain_rbi2023"], "rank": 2},
           "foodgrain_dld": {"url": DLD_URL, "rank": 0}}       # rank 0 = cross-check only (Ruling P12)


def agri_year(label: str) -> int:
    """'2015-16' -> 2015; the end year must be start+1 (mod 100)."""
    m = _AGYEAR.match(str(label).strip())
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise ValueError(f"not an agricultural year label: {label!r}")
    return int(m.group(1))


def _pool(rows: list[dict], source_id: str) -> pd.DataFrame:
    """rows: dicts with unit_id, raw_label, year, variable, value, provisional -> pooled records."""
    df = pd.DataFrame(rows)
    out = []
    for (uid, year, var), g in df.groupby(["unit_id", "year", "variable"], sort=False):
        labels = list(dict.fromkeys(g.raw_label))
        vals = g.value.dropna()
        out.append({"unit_id": uid, "raw_label": " + ".join(labels), "year": year, "variable": var,
                    "value": float(vals.sum()) if len(vals) else math.nan, "source_id": source_id,
                    "provisional": bool(g.provisional.any())})
    res = records.make(out)
    records.validate(res)
    return res


# ---------------------------------------------------------------- DES / RBI tables

def _blocks(lines):
    """[(years, body lines)] for each 'States/Union Territories  <year labels>' header."""
    heads = []
    for i, ln in enumerate(lines):
        if _HDR.match(ln):
            heads.append(([agri_year(t) for t in _HDR.sub("", ln).split()], i))
    blocks = []
    for k, (years, i) in enumerate(heads):
        end = heads[k + 1][1] if k + 1 < len(heads) else len(lines)
        blocks.append((years, lines[i + 1:end]))
    return blocks


def rbi_table(lines, source_id: str) -> pd.DataFrame:
    """RBI Handbook state foodgrain production table text (pdftotext -layout), '000 t -> t.

    Every printed line that has a label and as many numeric cells as the block has years must
    resolve to a unit (or TOTAL) or the parse raises. Per year 1997-2023 a state-row sum differing
    from the printed ALL INDIA row by more than 1% only warns (the source itself is inconsistent:
    2011-12 +1.15% in Table 54; the 1996-97 row, outside the window, is -3.95%), so Task 9's
    national-total gate decides."""
    blocks = _blocks(lines)
    if not blocks:
        raise ValueError(f"{source_id}: no 'States/Union Territories' header found")
    prov = PROVISIONAL.get(source_id, set())
    rows, totals = [], {}
    for years, body in blocks:
        n = len(years)
        norm = [re.sub(r"(?<!\S)\.(?!\S)", "NR", ln) for ln in body]      # "." = not applicable
        for ln in norm:
            label, toks = textable.split_row(ln)
            if label and len(toks) >= n and states.resolve(label) is None:
                raise ValueError(f"{source_id}: unresolved row {label!r}")
        for r in textable.state_rows(norm, n):
            for y, tok in zip(years, r["tokens"]):
                rec = {"unit_id": r["unit_id"], "raw_label": r["raw_label"], "year": y,
                       "variable": "foodgrain_t", "value": textable.parse_number(tok) * 1000.0,
                       "provisional": y in prov}
                if r["unit_id"] == "TOTAL":
                    totals[y] = rec["value"]
                rows.append(rec)
    sums = pd.DataFrame([r for r in rows if r["unit_id"] != "TOTAL"]).groupby("year").value.sum(min_count=1)
    if set(sums.index) != set(totals):
        raise ValueError(f"{source_id}: years without a state sum / ALL INDIA row: "
                         f"{sorted(set(sums.index) ^ set(totals))}")
    for y, t in sorted(totals.items()):
        if y in YEARS and not abs(sums[y] - t) <= 0.01 * t:
            warnings.warn(f"{source_id}: {y} state rows sum to {sums[y]:.1f} t but the printed ALL INDIA is "
                          f"{t:.1f} t ({100 * (sums[y] - t) / t:+.2f}%); source inconsistency, left to the "
                          "national-total gate", UserWarning, stacklevel=2)
    return _pool(rows, source_id)


def _repo_path(p: Path) -> str:
    """Repository-relative POSIX path (absolute when outside the repository)."""
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def rbi_pdf(source_id: str) -> pd.DataFrame:
    """One RBI Handbook table (cached / downloaded). foodgrain_rbi2023 is never downloaded: an absent
    file raises fetch.LocalSourceMissing (all_records skips it)."""
    name = RBI_FILES[source_id]
    if source_id == "foodgrain_rbi2023" and not (fetch.RAW_ROOT / source_id / name).exists():
        raise fetch.LocalSourceMissing(f"{source_id}: {_repo_path(fetch.RAW_ROOT / source_id / name)} not present "
                                       "(RBI serves the file behind a human-verification page; place it manually)")
    path = fetch.get(source_id, RBI_URLS[source_id], filename=name, kind="pdf")
    return rbi_table(textable.pdf_lines(path), source_id)


# ---------------------------------------------------------------- ICRISAT DLD

def _dld_sums(data: dict, state: str, year: int):
    """(production '000 t, area '000 ha) for a DLD state-year; NaN when any component is -1."""
    H = [h["header"] for h in data["headers"]]
    ip, ia = [H.index(f"{c} PRODUCTION") for c in DLD_CROPS], [H.index(f"{c} AREA") for c in DLD_CROPS]
    iy, ist = H.index("Year"), H.index("State Name")
    prod = area = 0.0
    for r in data["data"]:
        if r[ist] == state and int(r[iy]) == year:
            p, a = [float(r[i]) for i in ip], [float(r[i]) for i in ia]
            if min(p) < 0 or min(a) < 0:
                return math.nan, math.nan
            prod += sum(p)
            area += sum(a)
    return prod, area


def dld_state(path=None, data=None) -> pd.DataFrame:
    """ICRISAT DLD apportioned area-production-yield JSON -> state foodgrain_t / foodgrain_ha
    (10-component sum, see module docstring); years 1997-2023 only."""
    if data is None:
        p = Path(path) if path is not None else fetch.get("foodgrain_dld", DLD_URL, filename=DLD_FILE)
        data = json.loads(p.read_text(encoding="utf-8"))
    H = [h["header"] for h in data["headers"]]
    iy, ist = H.index("Year"), H.index("State Name")
    rows = []
    for st, yr in sorted({(r[ist], int(r[iy])) for r in data["data"]}):
        if yr not in YEARS:
            continue
        uid = states.resolve(st)
        if uid is None or uid == "TOTAL":
            raise ValueError(f"unresolved DLD state name {st!r}")
        prod, area = _dld_sums(data, st, yr)
        for var, v in (("foodgrain_t", prod), ("foodgrain_ha", area)):
            rows.append({"unit_id": uid, "raw_label": st, "year": yr, "variable": var,
                         "value": v * 1000.0, "provisional": False})
    return _pool(rows, "foodgrain_dld")


# ---------------------------------------------------------------- all

def all_records() -> pd.DataFrame:
    """All sources, validated and restricted to 1997-2023. A source that cannot be obtained is
    skipped with a warning; df.attrs["missing_sources"] / ["missing_reasons"] list them."""
    calls = [("foodgrain_dld", lambda: dld_state()),
             ("foodgrain_rbi2019", lambda: rbi_pdf("foodgrain_rbi2019")),
             ("foodgrain_rbi2023", lambda: rbi_pdf("foodgrain_rbi2023"))]
    parts, missing, reasons = [], [], {}
    for sid, call in calls:
        try:
            parts.append(call())
        except (fetch.FetchError, fetch.LocalSourceMissing) as e:
            warnings.warn(f"{sid}: source unavailable; skipped ({e})", UserWarning, stacklevel=2)
            missing.append(sid)
            reasons[sid] = str(e)
    df = pd.concat(parts, ignore_index=True)
    df = df[df.year.isin(YEARS)].reset_index(drop=True)
    records.validate(df)
    df.attrs["missing_sources"] = missing
    df.attrs["missing_reasons"] = reasons
    return df
