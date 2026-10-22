"""Malaria state x year counts (NVBDCP / NCVBDC), 2002-2025.

Variables (records schema, see records.py):
  tested  Persons examined for malaria. Up to 2019 the documents print "Blood Slide
          Examination" / B.S.E.; from the 2020 reports slides and RDTs are printed
          separately with "Total (BSE+RDT)", which is used for 2020-2021, and "Tested"
          (slides + RDT + others) for 2022+ (mal_sit_2022 and the 2022-2025 reports print the
          same figure). The pre-2020 "B.S.E." is taken to be the combined slides + RDT
          examined count - inferred from the continuity of the series across 2019/2020, not
          stated in the documents - so there is NO definitional break at 2020.
  cases   total malaria positives (all species; indigenous + imported where split).
  pf      P. falciparum cases including mixed infections. Situation tables to 2019: the
          printed "Pf cases". Annual reports: Pf + Mixed (reproduces their printed Pf%).
          mal_sit_2022: the printed "Pf" equals Pf + Mixed + Pm + Po of the annual reports
          (i.e. all non-Pv positives; e.g. India 2022: 101,070 vs Pf+Mixed 101,068), so
          mal_sit_2022 pf can exceed the annual-report pf by the few Pm/Po cases.
  deaths  malaria deaths (annual reports 2017+: Pv deaths + Pf deaths).

raw_label is the printed state label with leading serial numbers removed. A tested cell
reconstructed from district rows (see below) has raw_label "<label> [BSE=sum of districts]".

Text extraction: pdfplumber page.extract_text() lines (_pdf_lines). `pdftotext -layout`
(textable.pdf_lines) was inspected first but detaches the label column from the values
in the 2005-2009 table and in the annual reports, so it is not used here.
Dash / "NR" / blank cells are NaN (NVBDCP rule, textable.parse_number dash="nan");
"#DIV/0!" ratio cells are ignored.

Situation tables (state_rows; per year block, in year order: B.S.E. (or Tested),
Malaria cases (Positive), Pf cases, Deaths; expected_numbers = 4 x years in the table;
the year header line is verified against the configured years):
  mal_sit_0206  ncvbdc "Malaria Situation.pdf"            2002-2006 (2005* provisional; 2006** "Report
                received till 25th November,2006": partial year)
  mal_sit_0509  wayback 2012 "Malaria Situation_Sep.pdf"  2005-2009 (2008* provisional; 2009** to Sept:
                partial year)
  mal_upto2011  Malaria-situation-upto2011(P).pdf         2007-2010 (2010(P) provisional; 2011* upto January
                dropped)
  mal_sit_1317  wayback 2018 "malaria-situation.pdf"      2013-2017
  mal_sit_1519  Malaria-Situation-Oct19.pdf               2015-2019 (2019* "Upto October": partial year;
                West Bengal 2017 provisional per the footnote "West Bengal Provisional Data 2017")
  mal_sit_2022  Malaria_Situation_India_from_2022.pdf     2022-2025 (2026 "Upto August" dropped)
Partial-year columns (Ruling P17) are emitted provisional with raw_label "<label> [partial_year]"
(records.PARTIAL_YEAR); a partial-year value that would be chosen for a panel cell must be masked by
a reviewed row (gate outcome_partial_year). All-India rows are emitted as unit TOTAL. (0509 and 1317
exist only as Internet Archive captures, which refused this machine; all_records() skips unavailable
sources.)

Annual reports (mal_ar_YYYY, district tables): ONLY state-total rows are emitted. Locator:
  2010-2016  "State: <name>" heading, then district rows, then a row labelled "State Total";
             the total belongs to the latest heading. Row: Pop('000), BSE, Pv, Pf, Total
             cases, PF%, ABER, API, SPR, SFR, AFI, Deaths (PF% blank when no cases).
             Large BSE totals are printed in Excel E-notation ("1.3E+07"). Such a cell is
             replaced by the sum of the state's district BSE cells only if every district row
             since the heading parsed cleanly (11-12 cells, integer BSE, Pv+Pf=Total), the sum
             rounds to the printed mantissa, and |sum - ABER x Pop('000) x 10| / sum < 0.1%;
             otherwise it is NaN. Either way a warning is issued.
  2017-2018  the reports carry only ratios (PF%, ABER, API, SPR, AFI, SFR) and deaths
             (Pv, Pf); only "deaths" (Pv + Pf) is emitted, from the "State Total" rows under
             the "Epidemiological Situation Report of <name> YYYY" headings, plus
             "All India Total" -> TOTAL. A heading marked "(P)" (West Bengal 2017) makes that
             state's values provisional; note the 2017 All India Total includes those
             provisional West Bengal deaths (its TOTAL row itself is not flagged).
  2019-2021  heading "Epidemiological Situation Report of <name> YYYY", row "State Total"
             (also letter-spaced "S t a t e T o t a l"); "All India Total" -> TOTAL.
             2019: Pop, BSC, BSE, Pv, Pf, Mixed, Total, 6 ratios, RT, deaths Pv, deaths Pf.
             2020: Pop, BSC, RDT, BSE, RDT, Total(BSC+RDT), Total(BSE+RDT), Pv, Pf, Mixed,
                   Total, 6 ratios, RT, deaths Pv, Pf.
             2021: as 2020 but cases in three blocks (indigenous, imported, total) of
                   Pv, Pf, Mixed, Total; the total block is used.
  2022-2024  row labelled "<State> Total" (label may be abbreviated, e.g. "Andhra Pra.");
             "All India/All States/Grand Total" -> TOTAL. Same lead columns as 2020, then
             indigenous / imported / total case blocks; the total block is
             Pv, Pf, Mixed, Pm, Po, Others, Total; then 6 ratios, RT, deaths Pv, Pf.
             (2022-2023: the indigenous block is Pv, Pf, Mixed, Total.)
  2025       the state-wise summary table on page 1 (rows up to "India" -> TOTAL):
             Population, collected (slides, RDT, others), tested (slides, RDT, others),
             total collected, total tested, indigenous / imported / total blocks of
             Pv, Pf, Mix, Pm, Po, Total, 6 ratios, treatment done, deaths Pv, Pf.
  When a total row's values are wrapped onto the line above/below (2017-2019), the adjacent
  numeric-only line is used; when cells are missing or glued, the species block is
  re-anchored by its own arithmetic (Pv+Pf+... == Total) within +-2 positions, with a
  warning; "tested" of such a row is kept only if it still equals the sum of its printed
  parts (BSE + RDT ...) at the original or the shifted position, or - when the tested cell
  itself was lost - if the parts (unshifted, before the lost cells) sum to an integer printed
  on an adjacent numeric-only line; else NaN. Deaths cells
  glued as "015" are read as 0 + 15; other glued deaths -> NaN.
"""
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import pandas as pd

from pipeline.outcomes import fetch, records, states, textable
from pipeline.paths import check_source

VARS = ("tested", "cases", "pf", "deaths")
NCVBDC = "https://ncvbdc.mohfw.gov.in"

SOURCES: dict[str, dict] = {
    # The Internet Archive capture named in the plan was refused (HTTP 429 "suspected bot
    # traffic") at implementation time; the same file is served by the successor host.
    "mal_sit_0206": {"url": f"{NCVBDC}/Doc/Malaria%20Situation.pdf",
                     "alt_urls": [fetch.wayback("http://nvbdcp.gov.in/Doc/Malaria%20Situation.pdf", 2012)],
                     "years": (2002, 2006), "rank": 1},
    "mal_sit_0509": {"url": fetch.wayback("http://nvbdcp.gov.in/Doc/Malaria%20Situation_Sep.pdf", 2012),
                     "years": (2005, 2009), "rank": 2},
    "mal_upto2011": {"url": f"{NCVBDC}/Doc/Malaria-situation-upto2011(P).pdf", "years": (2007, 2010), "rank": 3},
    "mal_sit_1317": {"url": fetch.wayback("http://nvbdcp.gov.in/Doc/malaria-situation.pdf", 2018),
                     "years": (2013, 2017), "rank": 4},
    "mal_sit_1519": {"url": f"{NCVBDC}/WriteReadData/l892s/Malaria-Situation-Oct19.pdf",
                     "years": (2015, 2019), "rank": 5},
}
# Annual reports: the URL that worked (alternates tried in order when the main pattern 404s:
# Annual-Report-YYYY.pdf, Malaria-AnnualReport-YYYY.pdf, Malaria-Annual-Report-YYYY-1.pdf).
for _y in range(2010, 2017):
    SOURCES[f"mal_ar_{_y}"] = {"url": f"{NCVBDC}/Doc/Malaria-Annual-Report-{_y}.pdf", "years": (_y, _y), "rank": 6}
SOURCES["mal_ar_2017"] = {"url": f"{NCVBDC}/Doc/Annual-Report-2017.pdf", "years": (2017, 2017), "rank": 6}
# 2018-2025 annual reports and the 2022+ situation table: official NCVBDC URLs (accessed 2026-10-16;
# pipeline/reference/ncvbdc_source_urls.csv). The analysed files are byte-identical (SHA-256) to these
# downloads; they are cached under the file names below, so data/raw_files_manifest.csv applies to them.
# The 2025 and situation-table URLs are opaque and may change when NCVBDC updates the files.
_AR_URLS = {
    2018: f"{NCVBDC}/Doc/Annual-Report-2018.pdf",
    2019: f"{NCVBDC}/Doc/Malaria-AnnualReport-2019.pdf",
    2020: f"{NCVBDC}/Doc/Malaria-AnnualReport-2020.pdf",
    2021: f"{NCVBDC}/Doc/Malaria-AnnualReport-2021.pdf",
    2022: f"{NCVBDC}/Doc/Malaria-AnnualReport-2022.pdf",
    2023: f"{NCVBDC}/Doc/Malaria-AnnualReport-2023.pdf",
    2024: f"{NCVBDC}/Doc/Malaria-Annual-Report-2024.pdf",
    2025: f"{NCVBDC}/WriteReadData/l892s/87226817751785920429.pdf",
}
for _y, _u in _AR_URLS.items():
    SOURCES[f"mal_ar_{_y}"] = {"url": _u, "filename": f"Malaria_Annual_Report_{_y}.pdf",
                               "years": (_y, _y), "rank": 6}
SOURCES["mal_sit_2022"] = {"url": f"{NCVBDC}/WriteReadData/l892s/25134454981790683579.pdf",
                           "filename": "Malaria_Situation_India_from_2022.pdf", "years": (2022, 2025), "rank": 7}
DEATHS_ONLY = {2017, 2018}   # annual reports that publish ratios and deaths only

_TOTAL_LABEL = re.compile(r"^(all\s*(states|india)(\s+total)?|india|grand)$", re.I)
_SERIAL = re.compile(r"^\d+\s*")


def _clean_label(label: str) -> str:
    return _SERIAL.sub("", label.strip())


# ---------------------------------------------------------------- file access

def _pdf_lines(path) -> list[str]:
    import pdfplumber
    check_source(path)
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            out.extend((page.extract_text() or "").splitlines())
    return out


def source_path(source_id: str) -> Path:
    url = SOURCES[source_id]["url"]
    if url.startswith("file:"):
        return fetch.local_copy(source_id, Path(url[len("file:"):]))
    errors = []
    for u in [url] + SOURCES[source_id].get("alt_urls", []):
        name = SOURCES[source_id].get("filename") or unquote(Path(urlparse(u).path).name)  # not %20
        try:
            return fetch.get(source_id, u, filename=name, kind="pdf")
        except fetch.FetchError as e:
            errors.append(str(e))
    raise fetch.FetchError(f"{source_id}: all URLs failed: {errors}")


def _lines_for(source_id, lines):
    return lines if lines is not None else _pdf_lines(source_path(source_id))


# ---------------------------------------------------------------- shared helpers

_NUMLIKE = re.compile(r"^(?:#DIV/0!|NA|NR|N\.A\.|[-–—]|\d[\d,]*(?:\.\d+)*(?:E\+?\d+)?\*?)$", re.I)
_ENOTE = re.compile(r"^(?P<m>\d+(?:\.(?P<d>\d+))?)E\+?(?P<e>\d+)$", re.I)
_INT = re.compile(r"^\d[\d,]*$")


def _value(tok: str) -> float:
    if tok.upper() == "#DIV/0!" or tok.count(".") > 1 or _ENOTE.match(tok):
        return float("nan")
    try:
        return textable.parse_number(tok)
    except ValueError:
        return float("nan")


def _numeric_only(line: str):
    toks = line.split()
    return toks if toks and all(_NUMLIKE.match(t) for t in toks) else None


def _has_digit(line: str) -> bool:
    return any(c.isdigit() for c in line)


def _unwrap(lines: list[str]) -> list[str]:
    """Join 'label start / numeric-only row / label end' triples into one row.

    Used where a long state name wraps around its value line (2025 report, mal_sit_2022):
    "The Dadra And Nagar Haveli And" / "32 131198 ..." / "Daman And Diu".
    """
    out, i = [], 0
    while i < len(lines):
        if (0 < i < len(lines) - 1 and _numeric_only(lines[i]) and out and out[-1] == lines[i - 1]
                and not _has_digit(lines[i - 1]) and not _has_digit(lines[i + 1])):
            label = f"{lines[i - 1].strip()} {lines[i + 1].strip()}"
            if states.resolve(label):
                out[-1] = f"{label} {lines[i].strip()}"
                i += 2
                continue
        out.append(lines[i])
        i += 1
    return out


def _check_years(lines, years, source_id):
    for line in lines:
        found = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", line)]
        if len(found) >= 2:
            if found[:len(years)] != list(years):
                raise ValueError(f"{source_id}: year header {line!r} != configured {list(years)}")
            return
    raise ValueError(f"{source_id}: no year header line found")


# ---------------------------------------------------------------- situation tables

# partial: {year: footnote regex} - a year column the document marks as covering only part of the
# year (Ruling P17). Its records are emitted provisional with raw_label "<label> [partial_year]"; the
# footnote must be found in the text (None: the document has not been seen - mal_sit_0509 - and the
# declaration rests on the Task 5 source notes). Partial columns at the right edge of a table that a
# later source already covers are not emitted at all (emit).
_SITUATION = {
    "mal_sit_0206": dict(years=(2002, 2003, 2004, 2005, 2006), emit=None, provisional={2005, 2006},
                         partial={2006: r"\*\*\s*Report received till 25th November"}),
    "mal_sit_0509": dict(years=(2005, 2006, 2007, 2008, 2009), emit=None, provisional={2008, 2009},
                         partial={2009: None}),
    "mal_upto2011": dict(years=(2007, 2008, 2009, 2010, 2011), emit={2007, 2008, 2009, 2010},
                         provisional={2010}),
    "mal_sit_1317": dict(years=(2013, 2014, 2015, 2016, 2017), emit=None, provisional=set()),
    "mal_sit_1519": dict(years=(2015, 2016, 2017, 2018, 2019), emit=None, provisional={2019},
                         partial={2019: r"^\s*\*\s*Upto October"},
                         cells={("WB", 2017): r"West Bengal Provisional Data 2017"}),
    "mal_sit_2022": dict(years=(2022, 2023, 2024, 2025, 2026), emit={2022, 2023, 2024, 2025},
                         provisional=set()),
}


def _row_label(r: dict) -> str:
    """state_rows raw_label without serial numbers (leading, or trailing ones it trimmed)."""
    label = r["raw_label"]
    if r["trimmed"]:
        label = label.rsplit(None, r["trimmed"])[0]
    return _clean_label(label)


def situation(source_id: str, lines=None) -> pd.DataFrame:
    cfg = _SITUATION[source_id]
    lines = _lines_for(source_id, lines)
    years = cfg["years"]
    _check_years(lines, years, source_id)
    prov_cells = {k for k, pat in cfg.get("cells", {}).items()
                  if any(re.search(pat, ln) for ln in lines)}
    partial = cfg.get("partial", {})
    for y, pat in partial.items():
        if pat is not None and not any(re.search(pat, ln, re.I) for ln in lines):
            raise ValueError(f"{source_id}: partial-year footnote for {y} ({pat!r}) not found")
    rows = textable.state_rows(_unwrap(lines), expected_numbers=4 * len(years))
    out = []
    for r in rows:
        vals = [textable.parse_number(t) for t in r["tokens"]]
        label = _row_label(r)
        for k, y in enumerate(years):
            if cfg["emit"] is not None and y not in cfg["emit"]:
                continue
            prov = y in cfg["provisional"] or y in partial or (r["unit_id"], y) in prov_cells
            lab = records.partial_label(label) if y in partial else label
            for j, var in enumerate(VARS):
                out.append({"unit_id": r["unit_id"], "raw_label": lab, "year": y,
                            "variable": var, "value": vals[4 * k + j], "source_id": source_id,
                            "provisional": prov})
    df = records.make(out)
    records.validate(df)
    return df


def situation_2002_2006(lines=None):
    return situation("mal_sit_0206", lines)


def situation_2005_2009(lines=None):
    return situation("mal_sit_0509", lines)


def situation_upto2011(lines=None):
    return situation("mal_upto2011", lines)


def situation_2013_2017(lines=None):
    return situation("mal_sit_1317", lines)


def situation_2015_2019(lines=None):
    return situation("mal_sit_1519", lines)


def situation_from2022(lines=None):
    return situation("mal_sit_2022", lines)


# ---------------------------------------------------------------- annual reports

@dataclass(frozen=True)
class _Fmt:
    lens: tuple            # accepted token counts of a complete row
    tested: int            # index of "tested"
    block: tuple           # (start, length) of the species block; its last cell is the total
    pf: tuple              # indices (absolute, for the unshifted row) summed into pf
    deaths: int            # number of trailing death columns (summed)
    tested_parts: tuple = ()   # indices whose sum must equal tested (BSE + RDT ...)


_FMT_A = _Fmt(lens=(12, 11), tested=1, block=(2, 3), pf=(3,), deaths=1)
_FMT = {
    2019: _Fmt(lens=(16,), tested=2, block=(3, 4), pf=(4, 5), deaths=2),
    2020: _Fmt(lens=(20,), tested=6, block=(7, 4), pf=(8, 9), deaths=2, tested_parts=(3, 4)),
    2021: _Fmt(lens=(28,), tested=6, block=(15, 4), pf=(16, 17), deaths=2, tested_parts=(3, 4)),
    2022: _Fmt(lens=(34,), tested=6, block=(18, 7), pf=(19, 20), deaths=2, tested_parts=(3, 4)),
    2023: _Fmt(lens=(34,), tested=6, block=(18, 7), pf=(19, 20), deaths=2, tested_parts=(3, 4)),
    2024: _Fmt(lens=(37,), tested=6, block=(21, 7), pf=(22, 23), deaths=2, tested_parts=(3, 4)),
    2025: _Fmt(lens=(36,), tested=8, block=(21, 6), pf=(22, 23), deaths=2, tested_parts=(4, 5, 6)),
}
for _y in range(2010, 2017):
    _FMT[_y] = _FMT_A
_DEATHS_FMT = "deaths-only"     # 2017-2018: 6 ratios, deaths Pv, deaths Pf
for _y in DEATHS_ONLY:
    _FMT[_y] = _DEATHS_FMT


def _warn(msg):
    warnings.warn(msg, UserWarning, stacklevel=4)


def _parse_deaths_only(toks, where):
    """2017-2018 row: 6 ratio cells then deaths Pv, deaths Pf (all must look right).

    A stray leading "0" cell (printed before Chhattisgarh's total in both years) is dropped.
    """
    if len(toks) == 9 and toks[0] == "0":
        _warn(f"{where}: stray leading '0' cell dropped")
        toks = toks[1:]
    if (len(toks) == 8 and all(("." in t or t.upper() == "#DIV/0!") for t in toks[:6])
            and all(_INT.match(t) for t in toks[6:])):
        return {"tested": float("nan"), "cases": float("nan"), "pf": float("nan"),
                "deaths": _value(toks[6]) + _value(toks[7]), "_toks": toks}
    return None


def _parse_total(toks: list[str], fmt, where: str, strict: bool, adjacent=()):
    """{tested, cases, pf, deaths, _toks} from a state-total row's tokens, or None.

    strict: only a complete row (len in fmt.lens) whose species block adds up is accepted.
    Otherwise the block is re-anchored within +-2 positions by its arithmetic.
    adjacent: token lists of the numeric-only lines next to the row (re-anchored rows only:
    they may confirm a tested total that was wrapped off the row).
    """
    toks = list(toks)
    if fmt == _DEATHS_FMT:
        return _parse_deaths_only(toks, where)
    if fmt.deaths == 2 and toks and re.fullmatch(r"0\d+", toks[-1]):
        toks[-1:] = ["0", toks[-1][1:]]   # glued "015" can only be deaths Pv 0, Pf 15
    vals = [_value(t) for t in toks]
    start, L = fmt.block

    def block_ok(s):
        b = toks[s:s + L]
        return (s >= 0 and len(b) == L and all(_INT.match(t) for t in b)
                and sum(vals[s:s + L - 1]) == vals[s + L - 1])

    complete = len(toks) in fmt.lens
    if complete and block_ok(start):
        s = start
    elif strict:
        return None
    else:
        cands = [start + d for d in (0, -1, 1, -2, 2) if block_ok(start + d)]
        if not cands:
            return None
        s = cands[0]
        _warn(f"{where}: incomplete row ({len(toks)} cells); species block re-anchored "
              f"by its sum at cell {s} (layout position {start})")
    shift = s - start

    def at(i):
        return vals[i] if 0 <= i < len(vals) else float("nan")

    if complete and shift == 0:
        tested = at(fmt.tested)
        if fmt.tested_parts and tested != sum(at(i) for i in fmt.tested_parts):
            _warn(f"{where}: tested {tested} != sum of its printed parts; printed total kept")
    else:
        # re-anchored row: keep tested only where it still equals the sum of its parts
        tested = float("nan")
        for o in dict.fromkeys((0, shift)):
            if fmt.tested_parts and at(fmt.tested + o) == sum(at(i + o) for i in fmt.tested_parts):
                tested = at(fmt.tested + o)
                break
        if tested != tested and fmt.tested_parts:
            # the parts (read unshifted, all before the lost cells) sum to a candidate that is
            # accepted only when an adjacent numeric-only line prints exactly that integer
            # (Jharkhand 2020: "2708477 2708477 71.82 ..." wrapped onto the line above)
            parts = [toks[i] if i < len(toks) else "" for i in fmt.tested_parts]
            if max(fmt.tested_parts) < min(len(toks), s) and all(_INT.match(t) for t in parts):
                cand = sum(_value(t) for t in parts)
                if any(_INT.match(t) and _value(t) == cand for line in adjacent for t in line):
                    tested = cand
                    _warn(f"{where}: tested {cand:.0f} = sum of parts, confirmed by the adjacent line")
        if tested != tested:
            _warn(f"{where}: tested not verifiable in an incomplete row; NaN")
    # deaths = the trailing cells, trusted only when they are integers and (2019+) the cell
    # before them is the integer R.T. count - a ratio there means the row is cut short or
    # glued ("... 0.08 235243 383").
    tail = toks[-fmt.deaths:]
    rt_ok = fmt.deaths == 1 or (len(toks) > fmt.deaths and _INT.match(toks[-fmt.deaths - 1]))
    if len(toks) - fmt.deaths >= s + L and rt_ok and all(_INT.match(t) for t in tail):
        deaths = sum(vals[-fmt.deaths:])
    else:
        _warn(f"{where}: deaths cells {tail} unreadable; NaN")
        deaths = float("nan")
    out = {"tested": tested, "cases": vals[s + L - 1],
           "pf": sum(vals[i + shift] for i in fmt.pf), "deaths": deaths, "_toks": toks}
    if out["pf"] > out["cases"] or (out["tested"] == out["tested"] and out["cases"] > out["tested"]):
        _warn(f"{where}: implausible values {out}")
    return out


def _vkey(vals: dict) -> tuple:
    """Comparable (NaN-safe) tuple of a parsed row's variables."""
    return tuple(None if vals[v] != vals[v] else vals[v] for v in VARS)


def _row_values(lines, i, rest: str, fmt, where: str):
    """Values of the total row at line i: same line, else wrapped onto an adjacent numeric-only line."""
    toks = rest.split()
    got = _parse_total(toks, fmt, where, strict=True)
    if got:
        return got
    adj, near = [], []
    for j in (i - 1, i + 1):
        if 0 <= j < len(lines):
            nums = _numeric_only(lines[j])
            if nums:
                near.append(nums)
                r = _parse_total(toks + nums, fmt, where, strict=True)
                if r:
                    adj.append(r)
    # identical candidates (a single-district UT's district row repeats its total) are one
    if adj and all(_vkey(a) == _vkey(adj[0]) for a in adj):
        return adj[0]
    if len(adj) > 1:
        _warn(f"{where}: ambiguous wrapped values; row skipped")
        return None
    got = _parse_total(toks, fmt, where, strict=False, adjacent=near) if toks else None
    if got is None:
        _warn(f"{where}: total row unreadable ({len(toks)} cells); skipped")
    return got


def _district_bse(line: str):
    """2010-2016 district row -> BSE (int), 'bad' for an unparseable data row, None for non-rows."""
    _, toks = textable.split_row(line)
    if len(toks) < 3:
        return None                      # headings, column header, "Page 1 of 16"
    if len(toks) in (11, 12) and all(_INT.match(t) for t in toks[1:5]):
        v = [_value(t) for t in toks[1:5]]
        if v[1] + v[2] == v[3]:
            return int(v[0])
    return "bad"


def _recover_bse(toks, districts, where):
    """E-notation state BSE -> sum of district BSE if all checks pass, else NaN (see docstring)."""
    m = _ENOTE.match(toks[1])
    checks = []
    total = None
    if districts and "bad" not in districts and len(toks) == 12:
        total = sum(districts)
        digits = len(m.group("d") or "")
        mantissa_ok = float(f"{total:.{digits}E}") == float(toks[1])
        aber, pop = _value(toks[6]), _value(toks[0])
        aber_dev = abs(total - aber * pop * 10) / total if total else float("inf")
        checks = [f"sum={total}", f"rounds to {toks[1]}: {mantissa_ok}",
                  f"ABER x Pop x 10 = {aber * pop * 10:.0f} (dev {aber_dev:.4%})"]
        if mantissa_ok and aber_dev < 0.001:
            _warn(f"{where}: E-notation BSE {toks[1]} replaced by the sum of districts ({'; '.join(checks)})")
            return float(total)
    reason = "; ".join(checks) if checks else (
        f"district rows unusable ({len(districts)} rows, bad={districts.count('bad')}, cells={len(toks)})")
    _warn(f"{where}: E-notation BSE {toks[1]} read as NaN ({reason})")
    return float("nan")


_STATE_HDR = re.compile(r"^State:\s*(?P<s>.+?)\s*$")
_REPORT_HDR = re.compile(r"Situation Report of\s+(?P<s>.+?),?\s+(?:19|20)\d\d\b(?P<p>\s*\(P\))?")
_STATE_TOTAL = re.compile(r"^(?:\d+\s+)?S\s*t\s*a\s*t\s*e\s*T\s*o\s*t\s*a\s*l(?=\s|$)\s*(?P<rest>.*)$")
_ALL_INDIA = re.compile(r"^All\s+India\s+Total(?=\s|$)\s*(?P<rest>.*)$")
_X_TOTAL = re.compile(r"^\s*\d*\s*(?P<label>[^\d\s].*?)\s+Total(?=\s|$)\s*(?P<rest>.*)$")


def _headed_totals(lines, fmt, year, header_re):
    """2010-2021: total rows attributed to the latest state heading -> [(label, vals, prov)]."""
    found, current, prov, districts = [], None, False, []
    for i, line in enumerate(lines):
        line = line.strip()
        m = header_re.search(line)
        if m:
            if current is not None:
                _warn(f"mal_ar_{year}: {current!r} has no State Total row")
            current, districts = m.group("s"), []
            prov = bool(m.groupdict().get("p"))
            continue
        m = _STATE_TOTAL.match(line) or _ALL_INDIA.match(line)
        if not m:
            if fmt is _FMT_A and current is not None:
                d = _district_bse(line)
                if d is not None:
                    districts.append(d)
            continue
        label = "All India Total" if m.re is _ALL_INDIA else current
        if label is None:
            _warn(f"mal_ar_{year}: State Total row without a heading at line {i}; skipped")
            continue
        where = f"mal_ar_{year} {label}"
        vals = _row_values(lines, i, m.group("rest"), fmt, where)
        if vals and fmt is _FMT_A and _ENOTE.match(vals["_toks"][1]):
            vals["tested"] = _recover_bse(vals["_toks"], districts, where)
            vals["_derived"] = vals["tested"] == vals["tested"]
        row_prov = prov and m.re is not _ALL_INDIA
        if m.re is not _ALL_INDIA:
            current, districts = None, []
        if vals:
            found.append((label, vals, row_prov))
    return found


def _labelled_totals(lines, fmt, year):
    """2022-2024: rows labelled '<State> Total'; duplicates (summary table) must agree."""
    found, seen = [], {}
    for i, line in enumerate(lines):
        m = _X_TOTAL.match(line.strip())
        if not m:
            continue
        label = m.group("label").strip()
        if not states.resolve(label) and not _TOTAL_LABEL.match(label):
            if sum(bool(_NUMLIKE.match(t)) for t in m.group("rest").split()) >= 10:
                _warn(f"mal_ar_{year}: unresolved total label {label!r}; skipped")
            continue
        vals = _row_values(lines, i, m.group("rest"), fmt, f"mal_ar_{year} {label}")
        if not vals:
            continue
        # A state-wise summary repeats the district-section totals (2023), sometimes with a
        # different spelling ("Arunachal Pra." / "Arunachal Pradesh"): a row is a repeat when
        # its unit and values equal an earlier row's (members of a pooled unit, e.g. Andhra
        # Pradesh and Telangana, differ in value). Same label with other values -> warning.
        uid = "TOTAL" if _TOTAL_LABEL.match(label) else states.resolve(label)
        key = (uid, _vkey(vals))
        name = states.normalise(label)
        if key in seen:
            continue
        if name in seen:
            _warn(f"mal_ar_{year}: {label!r} printed twice with different values; first kept")
            continue
        seen[key] = seen[name] = True
        found.append((label, vals, False))
    return found


_ROW = re.compile(r"^\s*\d*\s*(?P<label>[A-Za-z][^\d]*?)\s+(?P<rest>\d.*)$")


def _summary_table(lines, fmt, year):
    """2025: page-1 state-wise table, up to and including the 'India' row."""
    found = []
    for line in _unwrap(lines):
        m = _ROW.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        if not states.resolve(label) and not _TOTAL_LABEL.match(label):
            continue
        toks = m.group("rest").split()
        if len(toks) - 1 in fmt.lens:   # serial number left after an unwrapped label
            toks = toks[1:]
        vals = _parse_total(toks, fmt, f"mal_ar_{year} {label}", strict=False)
        if vals is None:
            _warn(f"mal_ar_{year}: row {label!r} unreadable; skipped")
            continue
        found.append((label, vals, False))
        if _TOTAL_LABEL.match(label):
            break
    return found


def annual_report(year: int, lines=None) -> pd.DataFrame:
    """State-total rows of the NCVBDC annual report for `year` (see module docstring)."""
    source_id = f"mal_ar_{year}"
    if source_id not in SOURCES:
        raise ValueError(f"no annual report configured for {year}")
    lines_given = lines
    lines = _lines_for(source_id, lines)
    fmt = _FMT[year]
    if year <= 2016:
        found = _headed_totals(lines, fmt, year, _STATE_HDR)
    elif year <= 2021:
        found = _headed_totals(lines, fmt, year, _REPORT_HDR)
    elif year <= 2024:
        found = _labelled_totals(lines, fmt, year)
    else:
        found = _summary_table(lines, fmt, year)
    variables = ("deaths",) if year in DEATHS_ONLY else VARS
    out, units = [], set()
    for label, vals, prov in found:
        label = _clean_label(label)
        uid = "TOTAL" if (_TOTAL_LABEL.match(label) or label == "All India Total") else states.resolve(label)
        if uid is None:
            raise ValueError(f"{source_id}: unresolved state label {label!r}")
        units.add(uid)
        for var in variables:
            raw = f"{label} [BSE=sum of districts]" if var == "tested" and vals.get("_derived") else label
            out.append({"unit_id": uid, "raw_label": raw, "year": year, "variable": var,
                        "value": vals[var], "source_id": source_id, "provisional": prov})
    missing = sorted(set(states.UNITS) - units)
    if lines_given is None and missing:
        warnings.warn(f"{source_id}: no state-total row for {missing}", UserWarning, stacklevel=2)
    df = records.make(out)
    records.validate(df)
    return df


def all_records() -> pd.DataFrame:
    """All sources, validated. A source whose raw file cannot be obtained is skipped with a
    warning and listed in df.attrs["missing_sources"] (for Task 9's missing_source rows)."""
    calls = [(s, lambda s=s: situation(s)) for s in _SITUATION]
    calls += [(f"mal_ar_{y}", lambda y=y: annual_report(y)) for y in range(2010, 2026)]
    parts, missing = [], []
    for sid, call in calls:
        try:
            parts.append(call())
        except (fetch.FetchError, FileNotFoundError) as e:
            warnings.warn(f"{sid}: raw file unavailable; skipped ({e})", UserWarning, stacklevel=2)
            missing.append(sid)
    df = pd.concat(parts, ignore_index=True)
    records.validate(df)
    df.attrs["missing_sources"] = missing
    return df
