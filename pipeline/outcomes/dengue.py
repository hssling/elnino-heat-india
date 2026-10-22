"""Dengue state x year counts (NVBDCP / NCVBDC / OpenDengue), 2007-2025.

Variables (records schema, see records.py): cases (reported dengue cases), deaths.
Missing-value rule (NVBDCP/NCVBDC): "-", "NR" and blank cells are NaN; a printed 0 is 0.
Partial years (Ruling P17): a year whose header or footnote ends the count before the year's end
is emitted with raw_label "<label> [partial_year]" (records.PARTIAL_YEAR) and provisional=True;
assembly masks such a value through a reviewed row wherever it would be chosen.
raw_label is the printed label with leading serial numbers removed (footnote marks kept).
All-India rows ("Total", "TOTAL", "All India Total") are emitted as unit TOTAL.

Sources (rank: a higher rank is a later document; see outcomes_sources.csv):
  den_nvbdcp12  web.archive.org/web/2012id_/http://nvbdcp.gov.in/den-cd.html ("Dengue Cases and
                Deaths in the Country since 2007"), which resolves to the capture of 2013-10-06
                (the index has no 2012 capture). Same layout as below; 2007-2012 identical to
                den_nvbdcp, 2013** provisional till September 2013.
  den_nvbdcp    Internet Archive 2013 capture of the same page (20131115224117), 2007-2013.
                HTML table (pandas.read_html, the table containing "Affected"):
                  header row 1: Sl. No. | Affected States/UTs | one colspan-2 cell per year
                  header row 2: C | D per year (Cases, Deaths)
                  rows: serial, label, (cases, deaths) x years; last row " Total".
                Year cells carry provisional marks: "2012*" (provisional till 31 Dec) and
                "2013**" (provisional till 28 Oct 2013, i.e. partial) -> provisional=True; a mark
                whose footnote ends before 31 December is a partial year (raw_label suffix
                " [partial_year]", Ruling P17).
                Not listed: Lakshadweep (and Telangana, which did not exist). AP is undivided.
                An unresolved labelled row raises ValueError.
  den_ar1415    NVBDCP Annual Report 2014-15, Annexure-5 "State-wise Dengue Situation in
                Country": 2010-2013 final, 2014 "Prov. upto 30.11.14" -> provisional, partial year.
  den_nvbdcp14  Internet Archive 2015 capture of the same page; 2013 and 2014 kept (starred
                header years flagged provisional). If unavailable, nvbdcp_2014() falls back to
                den_nhp2018 (2013-2014); all_records() calls it without the fallback.
  den_nhp2018/2019/2021/2023  CBHI National Health Profile Table 3.1.5 "State/UT wise Cases
                and Deaths Due to Dengue in India, <5 years>" (source: Dte. NVBDCP / NCVBDC):
                NHP 2018 2013-2017(P), 2019 2014-2018(P), 2021 2016-2020(Prov.), 2023
                2018-2022 (India row printed first; only 2018-2020 used - its 2021 column is
                printed in another state order and 2022 is provisional, both from den_ncvbdc).
                The "(P)"/"Prov." year is provisional. NHP 2020 is not used: its state labels
                and value rows are misaligned (rows 15-17, 25-28, 32-34 carry other states'
                values, checked against NHP 2019 and 2021). No NHP 2022 is on the CBHI site.
  The state tables above (state_table(); located by title + year header, contents-list
  entries skipped; pdfplumber text of the pages whose pdftotext text matches the title):
                row: serial, label, (cases, deaths) x 5 years; "Total"/"TOTAL"/"India"/"All
                India Total" -> TOTAL; "-" -> NaN (Telangana before 2014). Dadra & Nagar Haveli
                and Daman & Diu merged in 2020: in NHP 2021/2023 their rows stop at 2019 and the
                merged UT's later years are a numeric-only line between them, emitted once as
                DNH_DD with raw_label "<label> [merged UT, later years]". Any other incomplete
                state row raises.
  den_opendengue  OpenDengue admin-1 yearly rows (data/external/opendengue_india_admin1_year.csv,
                copied in Phase 1). Kept: UUID starting "MOH-IND-" (the Ministry of Health /
                NVBDCP-NCVBDC state tables: MOH-IND-20152024-Y01-00 = 2015-2021,
                MOH-IND-2022-Y01-01 = 2022, MOH-IND-20152024-Y01-02 = 2023-2024) and
                2015 <= Year <= 2024. The other prefix, "LITERATURE-IND-19972012-*" (1997-2012
                compiled from literature), is dropped. Variable "cases" only (dengue_total).
                West Bengal 2023 (30683) and 2024 (441) are NCVBDC's starred partial-year
                counts (OpenDengue carries no footnote): while they hold those values they are
                provisional and partial-year (_OD_PARTIAL).
  den_ncvbdc    NCVBDC "Dengue Cases and Deaths in the Country" 2021-2026 (Prov till 30th
                April 2026). pdfplumber text lines (pdftotext -layout scrambles the columns);
                row: serial, label, (cases, deaths) x 2021..2026; "TOTAL" row. The partial
                current year 2026 is not emitted. A starred cell ("30683*" = "*Till 13.9.2023",
                "441**" = "**Till 21.2.2024", West Bengal) is a partial-year count: that
                unit-year (cases and deaths) is provisional and partial-year (raw_label suffix
                " [partial_year]", Ruling P17); the footnote must be printed. "34 Ladakh Non
                endemic" has no values (no row; J&K is printed separately as "J&K"). D&N Haveli
                and Daman & Diu are separate rows (summed downstream into DNH_DD).
"""
import io
import re
import subprocess
import warnings
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from pipeline.outcomes import fetch, records, states, textable
from pipeline.paths import EXTERNAL, check_source

VARS = ("cases", "deaths")
PAGE = "http://nvbdcp.gov.in/den-cd.html"
CBHI = "https://cbhidghs.mohfw.gov.in/sites/default/files/NHP"
NHP_URL = f"{CBHI}/National-health-2018-chapter3_0.pdf"
NCVBDC_URL = "https://ncvbdc.mohfw.gov.in/Doc/Dengue-Cases-deaths-2021-2026-till-April.pdf"
OPENDENGUE = EXTERNAL / "opendengue_india_admin1_year.csv"

SOURCES: dict[str, dict] = {
    "den_nvbdcp12": {"url": fetch.wayback(PAGE, 2012), "filename": "den-cd_2012.html", "rank": 1},
    # the capture of 2013-11-15 (latest 2013 capture known; the copy in data/raw was retrieved by
    # the Phase 2 research probe because the Internet Archive refused this machine with HTTP 429)
    "den_nvbdcp": {"url": f"https://web.archive.org/web/20131115224117id_/{PAGE}",
                   "filename": "den-cd_2013.html", "rank": 2},
    "den_ar1415": {"url": "https://ncvbdc.mohfw.gov.in/Doc/Annual-report-NVBDCP-2014-15.pdf", "rank": 3},
    "den_nvbdcp14": {"url": fetch.wayback(PAGE, 2015), "filename": "den-cd_2015.html", "rank": 4},
    "den_nhp2018": {"url": NHP_URL, "rank": 5},
    "den_nhp2019": {"url": f"{CBHI}/National-health-2019.pdf", "rank": 6},
    "den_nhp2021": {"url": f"{CBHI}/National-health-2021.pdf", "rank": 7},
    "den_nhp2023": {"url": f"{CBHI}/NHP-2023-Last-Final.pdf", "rank": 8},
    "den_opendengue": {"url": f"file:{OPENDENGUE}", "rank": 9},
    "den_ncvbdc": {"url": NCVBDC_URL, "rank": 10},
}

_SERIAL = re.compile(r"^\d+\s*")
_YEAR = re.compile(r"^((?:19|20)\d\d)\s*(.*)$")   # any suffix ("*", "**", "(P)") marks a provisional year
_MARK = re.compile(r"[*]")


def _clean_label(label: str) -> str:
    return _SERIAL.sub("", str(label).strip())


def source_path(source_id: str) -> Path:
    cfg = SOURCES[source_id]
    url = cfg["url"]
    if url.startswith("file:"):
        return check_source(Path(url[len("file:"):]))
    name = cfg.get("filename") or Path(urlparse(url).path).name
    kind = "html" if name.endswith(".html") else "pdf"
    return fetch.get(source_id, url, filename=name, kind=kind)


def _pdf_lines(path, page_filter: str | None = None) -> list[str]:
    """pdfplumber text lines. page_filter (regex): only pages whose `pdftotext` text (fast; the
    NHP volumes have 300-540 pages) matches it, with whitespace collapsed, are read."""
    import logging

    import pdfplumber
    check_source(path)
    pages = None
    if page_filter:
        raw = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, check=True).stdout
        texts = raw.decode("utf-8", errors="replace").split("\f")
        pages = [i for i, t in enumerate(texts) if re.search(page_filter, " ".join(t.split()), re.I)]
    out = []
    logging.getLogger("pdfminer").setLevel(logging.ERROR)   # "Cannot set gray non-stroke color" noise
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            if pages is None or i in pages:
                out.extend((page.extract_text() or "").splitlines())
    return out


def _rec(uid, label, year, var, value, source_id, prov):
    return {"unit_id": uid, "raw_label": label, "year": year, "variable": var, "value": value,
            "source_id": source_id, "provisional": bool(prov)}


def _finish(out) -> pd.DataFrame:
    df = records.make(out)
    records.validate(df)
    return df


# ---------------------------------------------------------------- NVBDCP den-cd.html

def _page_table(html: str) -> pd.DataFrame:
    tables = [t for t in pd.read_html(io.StringIO(html), match="Affected", header=None)
              if t.shape[1] >= 4]
    if not tables:
        raise ValueError("den-cd.html: no state table found")
    return tables[-1]                      # the innermost table (read_html also returns the wrappers)


def _page_columns(t: pd.DataFrame):
    """[(column index, year, variable, mark)] from the two header rows; mark = the year cell's suffix
    ("", "*", "**", "(P)"); a non-empty mark makes the year provisional."""
    yrow, vrow = [str(x).strip() for x in t.iloc[0]], [str(x).strip().upper() for x in t.iloc[1]]
    cols = []
    for j, (y, v) in enumerate(zip(yrow, vrow)):
        m = _YEAR.match(y)
        if not m:
            continue
        if v not in ("C", "D"):
            raise ValueError(f"den-cd.html: column {j} under {y!r} is {v!r}, expected C/D")
        cols.append((j, int(m.group(1)), "cases" if v == "C" else "deaths", m.group(2).strip()))
    pairs = [(y, var) for _, y, var, _ in cols]
    years = sorted({y for y, _ in pairs})
    if not cols or pairs != [(y, var) for y in years for var in VARS]:
        raise ValueError(f"den-cd.html: unexpected C/D header layout {pairs}")
    return cols


_TILL = re.compile(r"(?<!\*)(\*+)\s*Provisional\s+till\s+([^|*<]+)", re.I)
_YEAR_END = re.compile(r"\b31(?:st)?\s*Dec", re.I)


def _partial_marks(html: str) -> set:
    """Year marks whose page footnote ends the count before the year's end ("** Provisional till 28th
    October 2013" -> {"**"}; "* Provisional till 31st December" is a whole provisional year)."""
    text = " ".join(re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").split())
    return {m.group(1) for m in _TILL.finditer(text) if not _YEAR_END.search(m.group(2))}


def nvbdcp_page(html: str | None = None, source_id: str = "den_nvbdcp") -> pd.DataFrame:
    """State rows of an Internet Archive capture of nvbdcp.gov.in/den-cd.html (all years). A year
    column whose mark's footnote is a "Provisional till <date before 31 Dec>" note is a partial year
    (raw_label "<label> [partial_year]", Ruling P17)."""
    if html is None:
        html = source_path(source_id).read_text(encoding="utf-8", errors="replace")
    t = _page_table(html)
    cols = _page_columns(t)
    partial_marks = _partial_marks(html)
    first = min(j for j, *_ in cols)
    out = []
    for i in range(2, len(t)):
        row = t.iloc[i]
        texts = [str(x).strip() for x in row.iloc[:first] if pd.notna(x)]
        label = next((s for s in reversed(texts) if not re.fullmatch(r"[\d.]+", s)), "")
        uid = states.resolve(label) if label else None
        if uid is None:
            if label or any(pd.notna(row.iloc[j]) for j, *_ in cols):
                raise ValueError(f"{source_id}: unresolved state label in row {texts!r}")
            continue                       # an empty spacer row
        for j, year, var, mark in cols:
            cell = row.iloc[j]
            value = float("nan") if pd.isna(cell) else textable.parse_number(str(cell))
            lab = _clean_label(label)
            out.append(_rec(uid, records.partial_label(lab) if mark in partial_marks else lab, year, var,
                            value, source_id, bool(mark)))
    return _finish(out)


# ---------------------------------------------------------------- state tables (annual report, NHP)

_NHP_TITLE = r"State/UT wise Cases and Deaths (?:Due|due) to Dengue in India"
# years: column order (cases, deaths per year); prov: "(P)"/"Prov." columns; emit: years used;
# partial: {year: header regex} - a column whose header ends the count before the year's end (Ruling
# P17; the regex must match the table text, whitespace collapsed).
_TABLES = {
    "den_ar1415": dict(title=r"State-wise Dengue Situation in Country",
                       years=(2010, 2011, 2012, 2013, 2014), prov={2014}, emit=range(2010, 2015),
                       partial={2014: r"Prov\. upto .{0,40}30\.11\.14"}),
    "den_nhp2018": dict(title=_NHP_TITLE, years=(2013, 2014, 2015, 2016, 2017), prov={2017},
                        emit=range(2013, 2018)),
    "den_nhp2019": dict(title=_NHP_TITLE, years=(2014, 2015, 2016, 2017, 2018), prov={2018},
                        emit=range(2014, 2019)),
    "den_nhp2021": dict(title=_NHP_TITLE, years=(2016, 2017, 2018, 2019, 2020), prov={2020},
                        emit=range(2016, 2021)),
    # 2021: column printed in another state order (Maharashtra/Manipur/Meghalaya rotated,
    # Telangana/Tripura swapped vs NCVBDC); 2022 "till Dec - Prov." -> both covered by den_ncvbdc.
    "den_nhp2023": dict(title=_NHP_TITLE, years=(2018, 2019, 2020, 2021, 2022), prov={2022},
                        emit=range(2018, 2021)),
}
_YEARS_RE = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def _table_block(lines, cfg, source_id):
    """Lines of the table: from the title that is followed by the configured year header (the
    title also appears in contents lists) to the "Source"/"Note" line, or to the total row when
    it follows state rows."""
    title = re.compile(cfg["title"], re.I)
    for i, ln in enumerate(lines):
        if not title.search(ln):
            continue
        window = []
        for h in lines[i + 1:i + 5]:        # the year header follows the title within 4 lines
            if title.search(h):
                break
            window.append(h)
        found = {int(y) for h in window for y in _YEARS_RE.findall(h)}
        if found != set(cfg["years"]):
            continue
        block, seen_state = [], False
        for ln2 in lines[i + 1:]:
            if re.match(r"^\s*(Source|Notes?)\b", ln2):
                break
            block.append(ln2)
            label, toks = textable.split_row(ln2)
            uid = states.resolve(label) if label and toks else None
            if uid == "TOTAL" and seen_state:
                break
            seen_state = seen_state or (uid not in (None, "TOTAL"))
        return block
    raise ValueError(f"{source_id}: table with year header {list(cfg['years'])} not found")


def _numeric_line(ln):
    label, toks = textable.split_row(ln)
    return toks if not label and toks else None


def _table_rows(block, n, source_id):
    """[(unit_id, label, {token index: token})]; token 2k / 2k+1 = cases / deaths of year k.

    A complete row has n = 2 x years tokens. Dadra & Nagar Haveli and Daman & Diu merged in
    2020: their rows print only the earlier years and the merged UT's later years are on a
    numeric-only line next to them ("33 D & N Haveli 4161 2 2064 0 493 0 1491 2" / "319 0" /
    "34 Daman & Diu 89 0 ..."): the line is attributed once to DNH_DD. Any other incomplete
    state row raises.
    """
    rows, used = [], set()
    for i, ln in enumerate(block):
        label, toks = textable.split_row(ln)
        uid = states.resolve(label) if label else None
        if uid is None and label and len(toks) == n:
            raise ValueError(f"{source_id}: unresolved state label {label!r} in a full data row")
        if uid is None or not toks:
            continue
        label = _clean_label(label)
        if len(toks) == n:
            rows.append((uid, label, dict(enumerate(toks))))
            continue
        if uid == "DNH_DD" and len(toks) < n and len(toks) % 2 == 0:
            rows.append((uid, label, dict(enumerate(toks))))
            for j in (i + 1, i - 1):
                rest = _numeric_line(block[j]) if 0 <= j < len(block) and j not in used else None
                if rest and len(toks) + len(rest) == n:
                    used.add(j)
                    rows.append((uid, f"{label} [merged UT, later years]",
                                 {len(toks) + k: t for k, t in enumerate(rest)}))
                    break
            else:
                if not any(r[1].endswith("[merged UT, later years]") for r in rows):
                    raise ValueError(f"{source_id}: row {label!r} has {len(toks)} of {n} values and no "
                                     f"adjacent merged-UT line")
            continue
        raise ValueError(f"{source_id}: row {label!r} has {len(toks)} values, expected {n}")
    return rows


def state_table(source_id: str, lines=None) -> pd.DataFrame:
    """State-wise dengue table (cases, deaths per year) of an NVBDCP annual report / CBHI NHP."""
    cfg = _TABLES[source_id]
    if lines is None:
        lines = _pdf_lines(source_path(source_id), page_filter=cfg["title"])
    years = cfg["years"]
    partial = cfg.get("partial", {})
    text = " ".join(" ".join(lines).split())
    for y, pat in partial.items():
        if not re.search(pat, text):
            raise ValueError(f"{source_id}: partial-year header for {y} ({pat!r}) not found")
    out = []
    for uid, label, toks in _table_rows(_table_block(lines, cfg, source_id), 2 * len(years), source_id):
        for k, year in enumerate(years):
            if year not in cfg["emit"] or 2 * k not in toks:
                continue
            lab = records.partial_label(label) if year in partial else label
            for v, var in enumerate(VARS):
                out.append(_rec(uid, lab, year, var, textable.parse_number(toks[2 * k + v]),
                                source_id, year in cfg["prov"] or year in partial))
    return _finish(out)


def nhp_2018(lines=None) -> pd.DataFrame:
    return state_table("den_nhp2018", lines)


def nvbdcp_2014(html: str | None = None, lines=None, fallback: bool = True) -> pd.DataFrame:
    """2013 and 2014: the 2015 capture of den-cd.html (den_nvbdcp14); if that capture cannot be
    obtained and fallback is set, CBHI NHP 2018 Table 3.1.5 2013-2014 (den_nhp2018).
    source_id records which was used. all_records() uses fallback=False (it reads den_nhp2018
    in full itself)."""
    if html is None and lines is None:
        try:
            html = source_path("den_nvbdcp14").read_text(encoding="utf-8", errors="replace")
        except fetch.FetchError as e:
            if not fallback:
                raise
            warnings.warn(f"den_nvbdcp14: Internet Archive capture unavailable ({e}); "
                          f"using den_nhp2018 (CBHI National Health Profile 2018)", UserWarning, stacklevel=2)
    if html is not None:
        df = nvbdcp_page(html=html, source_id="den_nvbdcp14")
    else:
        df = nhp_2018(lines=lines)
    return df[df.year.isin([2013, 2014])].reset_index(drop=True)


# ---------------------------------------------------------------- OpenDengue

_MOH = "MOH-IND-"     # OpenDengue UUID prefix of the MoHFW (NVBDCP/NCVBDC) state tables
# Partial-year counts that OpenDengue copied from the NCVBDC table, where they are starred:
# West Bengal 2023 "30683*" (*Till 13.9.2023) and 2024 "441**" (**Till 21.2.2024). Such a row is
# provisional only while its value equals the starred count (a later, final figure is not).
_OD_PARTIAL = {("WB", 2023): 30683.0, ("WB", 2024): 441.0}


def opendengue(path=None) -> pd.DataFrame:
    """OpenDengue MoHFW rows 2015-2024 (UUID prefix "MOH-IND-"), variable cases."""
    source_id = "den_opendengue"
    path = check_source(Path(path) if path is not None else OPENDENGUE)
    d = pd.read_csv(path)
    d = d[d.UUID.astype(str).str.startswith(_MOH) & d.Year.between(2015, 2024)]
    out = []
    for _, r in d.iterrows():
        label = re.sub(r"\s+", " ", str(r.adm_1_name)).strip()      # "ARUNACHAL\r\nPRADESH"
        uid = states.resolve(label)
        if uid is None or uid == "TOTAL":
            raise ValueError(f"{source_id}: unresolved state label {r.adm_1_name!r}")
        year, value = int(r.Year), float(r.dengue_total)
        prov = _OD_PARTIAL.get((uid, year)) == value       # no footnote in OpenDengue: matched to NCVBDC's
        out.append(_rec(uid, records.partial_label(label) if prov else label, year, "cases", value,
                        source_id, prov))
    return _finish(out)


# ---------------------------------------------------------------- NCVBDC 2021-2026

NCVBDC_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
NCVBDC_EMIT = {2021, 2022, 2023, 2024, 2025}        # 2026 is "Prov till 30th April": not used
# every starred cell is a partial-year count; the footnote defining the marks must be printed
_NCVBDC_FOOTNOTE = r"^\s*\*Till \d{1,2}\.\d{1,2}\.\d{4}; \*\*Till \d{1,2}\.\d{1,2}\.\d{4}"


def _check_ncvbdc_header(lines):
    head = " ".join(lines[:10])
    found = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", head)]
    if sorted(found) != list(NCVBDC_YEARS) or not re.search(r"Prov till", head):
        raise ValueError(f"den_ncvbdc: year header {found} != {list(NCVBDC_YEARS)} (2026 provisional)")


def ncvbdc_2126(lines=None) -> pd.DataFrame:
    source_id = "den_ncvbdc"
    if lines is None:
        lines = _pdf_lines(source_path(source_id))
    _check_ncvbdc_header(lines)
    if not any(re.search(_NCVBDC_FOOTNOTE, ln) for ln in lines):
        raise ValueError(f"den_ncvbdc: partial-year footnote {_NCVBDC_FOOTNOTE!r} not found")
    out = []
    for r in textable.state_rows(lines, expected_numbers=2 * len(NCVBDC_YEARS)):
        toks = r["tokens"]
        for k, year in enumerate(NCVBDC_YEARS):
            if year not in NCVBDC_EMIT:
                continue
            pair = toks[2 * k:2 * k + 2]
            prov = any(_MARK.search(t) for t in pair)   # "*Till 13.9.2023", "**Till 21.2.2024"
            lab = _clean_label(r["raw_label"])
            for v, var in enumerate(VARS):
                out.append(_rec(r["unit_id"], records.partial_label(lab) if prov else lab, year, var,
                                textable.parse_number(pair[v]), source_id, prov))
    return _finish(out)


# ---------------------------------------------------------------- all

def all_records() -> pd.DataFrame:
    """All sources, validated. A source whose raw file cannot be obtained is skipped with a
    warning and listed in df.attrs["missing_sources"] (for Task 9's missing_source rows)."""
    calls = [("den_nvbdcp12", lambda: nvbdcp_page(source_id="den_nvbdcp12")),
             ("den_nvbdcp", lambda: nvbdcp_page(source_id="den_nvbdcp")),
             ("den_nvbdcp14", lambda: nvbdcp_2014(fallback=False))]
    calls += [(sid, lambda sid=sid: state_table(sid)) for sid in _TABLES]
    calls += [("den_opendengue", lambda: opendengue()),
             ("den_ncvbdc", lambda: ncvbdc_2126())]
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
