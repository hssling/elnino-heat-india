"""Unit x year population denominators, 2001-2027.

Sources (see pipeline/reference/outcomes_sources.csv):
 * census_a02: Census of India 2011, Table A-02 "Decadal variation in population
   1901-2011" (India file, 00 A 2-India.xls). One row-block per state/UT: col 0 state
   code, col 1 district code ("000" on the state's first row), col 2 name (first row
   of the block only), col 3 census year (may carry footnote marks), col 4 persons.
   Census reference date is 1 March. Fetched from the Internet Archive capture of the
   official censusindia.gov.in URL, because that host serves an incomplete TLS chain
   that Python cannot verify (certificate verification is never disabled).
 * rgi_proj2020: RGI / National Commission on Population, "Population Projections for
   India and States 2011-2036, Report of the Technical Group on Population Projections"
   (cover dated Nov 2019, released July 2020). Table 8 (PDF pages 47-59):
   "Projected Total Population by Sex as on 1st March, 2011-2036" in '000, Indian digit
   grouping, three state blocks per page, each block Persons/Male/Female; parsed with
   `pdftotext -raw`. Values are the 1 March series (same reference date as the census),
   converted to persons (x1000). J&K is the post-2019 UT (excl. Ladakh) and Telangana
   is separate from Andhra Pradesh; they are summed into the pooled units JK and AP_TG.

Interpolation 2002-2010: linear between the 2001 and 2011 census values.
"""
import re
import subprocess
from pathlib import Path

import pandas as pd

from pipeline.outcomes import fetch, states
from pipeline.paths import DERIVED, check_source

CENSUS_ORIG = "https://censusindia.gov.in/nada/index.php/catalog/43333/download/47001/00%20A%202-India.xls"
CENSUS_URL = fetch.wayback(CENSUS_ORIG, 2024)
PROJ_URL = "https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf"
CENSUS_FILE, PROJ_FILE = "00_A2_India.xls", "Report_Population_Projection_2019.pdf"   # cached names
LAST_YEAR = 2027               # projections used up to here (Table 8 runs to 2036)
PROJ_PAGES = (47, 59)          # Table 8, 1st March series
PAGE_BLOCKS = {                # ordered state blocks per page of Table 8
    47: ["INDIA", "Jammu & Kashmir", "Himachal Pradesh"],
    48: ["Punjab", "Haryana", "Delhi"],
    49: ["Rajasthan", "Uttar Pradesh", "Bihar"],
    50: ["Assam", "West Bengal", "Jharkhand"],
    51: ["Odisha", "Chhattisgarh", "Madhya Pradesh"],
    52: ["Gujarat", "Maharashtra", "Andhra Pradesh"],
    53: ["Karnataka", "Kerala", "Tamil Nadu"],
    54: ["Chandigarh", "Uttarakhand", "Sikkim"],
    55: ["Arunachal Pradesh", "Nagaland", "Manipur"],
    56: ["Mizoram", "Tripura", "Meghalaya"],
    57: ["Daman & Diu", "Dadra & Nagar Haveli", "Goa"],
    58: ["Lakshadweep", "Puducherry", "Andaman & Nicobar Islands"],
    59: ["Telangana", "Ladakh"],
}
FIRST_WORD = {47: "INDIA", 48: "PUNJAB", 49: "RAJASTHAN", 50: "ASSAM", 51: "ODISHA", 52: "GUJARAT",
              53: "KARNATAKA", 54: "CHANDIGARH", 55: "ARUNACHAL", 56: "MIZORAM", 57: "DAMAN",
              58: "LAKSHADWEEP", 59: "TELANGANA"}


def _year(tok) -> int | None:
    m = re.match(r"\s*(\d{4})\b", str(tok))
    return int(m.group(1)) if m else None


def _pool(rows: list[tuple[str, int, float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["unit_id", "year", "population"])
    return df.groupby(["unit_id", "year"], as_index=False).population.sum()


def census_state_totals() -> pd.DataFrame:
    path = fetch.get("census_a02", CENSUS_URL, filename=CENSUS_FILE)
    d = pd.read_excel(path, header=None, dtype=str)
    rows, label = [], None
    for _, r in d.iterrows():
        if str(r[1]).strip() == "000":
            label = str(r[2])
        y = _year(r[3])
        if label is None or y not in (2001, 2011):
            continue
        uid = states.resolve(label)
        if uid is None:
            raise ValueError(f"unresolved census label {label!r}")
        if uid == "TOTAL":
            continue
        rows.append((uid, y, float(str(r[4]).replace(",", ""))))
    out = _pool(rows)
    missing = set(states.UNITS) - set(out.unit_id)
    if missing:
        raise ValueError(f"census table missing units {sorted(missing)}")
    return out


_ROW = re.compile(r"^(20\d\d)((?:\s+\d[\d,]*)+)\s*$")


def _page_values(pdf, page: int) -> dict[str, dict[int, float]]:
    """{block label: {year: persons ('000)}} for one Table 8 page (pdftotext -raw)."""
    check_source(pdf)
    txt = subprocess.run(["pdftotext", "-raw", "-f", str(page), "-l", str(page), str(pdf), "-"],
                         capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
    blocks = PAGE_BLOCKS[page]
    if FIRST_WORD[page] not in txt.upper():
        raise ValueError(f"page {page}: expected block {FIRST_WORD[page]!r} not found")
    if "1st March" not in txt:
        raise ValueError(f"page {page} is not the 1st March table")
    out = {b: {} for b in blocks}
    for line in txt.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        nums = [float(t.replace(",", "")) for t in m.group(2).split()]
        if len(nums) != 3 * len(blocks):
            continue  # e.g. a stray line
        y = int(m.group(1))
        for i, b in enumerate(blocks):
            p, ma, fe = nums[3 * i:3 * i + 3]
            if abs(p - ma - fe) > 2:
                raise ValueError(f"page {page} {b} {y}: persons {p} != male {ma} + female {fe}")
            out[b][y] = p
    return out


def projections() -> pd.DataFrame:
    pdf = fetch.get("rgi_proj2020", PROJ_URL)
    rows, india = [], {}
    for page in range(PROJ_PAGES[0], PROJ_PAGES[1] + 1):
        for label, series in _page_values(pdf, page).items():
            if label == "INDIA":
                india = series
                continue
            uid = states.resolve(label)
            if uid is None or uid == "TOTAL":
                raise ValueError(f"unresolved projection label {label!r}")
            for y in range(2012, LAST_YEAR + 1):
                if y not in series:
                    raise ValueError(f"projection {label} missing {y}")
                rows.append((uid, y, series[y] * 1000.0))
    out = _pool(rows)
    for y in range(2012, LAST_YEAR + 1):
        tot = out[out.year == y].population.sum() / 1000.0
        if abs(tot - india[y]) / india[y] > 0.002:
            raise ValueError(f"projection {y}: unit sum {tot} vs India {india[y]}")
    missing = set(states.UNITS) - set(out.unit_id)
    if missing:
        raise ValueError(f"projections missing units {sorted(missing)}")
    return out


def cached() -> bool:
    """True when both raw files are in the cache, i.e. table() rebuilds offline (no download)."""
    return ((fetch.RAW_ROOT / "census_a02" / CENSUS_FILE).is_file()
            and (fetch.RAW_ROOT / "rgi_proj2020" / PROJ_FILE).is_file())


def table() -> pd.DataFrame:
    """unit x year population 2001-2027 (unit_id, year, population, source), as written by build()."""
    census = census_state_totals()
    proj = projections()
    rows = []
    for u in states.UNITS:
        c = census[census.unit_id == u].set_index("year").population
        p = proj[proj.unit_id == u].set_index("year").population
        for y in range(2001, LAST_YEAR + 1):
            if y in (2001, 2011):
                v, src = c[y], "census_a02"
            elif y < 2011:
                v, src = c[2001] + (c[2011] - c[2001]) * (y - 2001) / 10.0, "interpolated_census"
            else:
                v, src = p[y], "rgi_proj2020"
            rows.append({"unit_id": u, "year": y, "population": v, "source": src})
    return pd.DataFrame(rows, columns=["unit_id", "year", "population", "source"])


def build(out=DERIVED / "outcomes" / "population_unit_year.csv"):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table().to_csv(out, index=False)
    return out


if __name__ == "__main__":
    print(build())
