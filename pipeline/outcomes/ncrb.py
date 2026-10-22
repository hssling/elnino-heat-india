"""NCRB 'Accidental Deaths & Suicides in India' (ADSI): heat/sun-stroke deaths 2001-2024 and
farmer suicides 1997-2023, state x year.

Variables (records schema, see records.py):
  heat_deaths     Total (male + female [+ transgender]) of the "Heat Stroke" (to 2013) / "Heat/Sun
                  Stroke" (from 2014) cause in the state-wise "accidental deaths by natural causes
                  and sex" table.
  farmers         2001-2013: the pre-2014 ADSI profession category "Self-employed (Farming/
                  Agriculture)" (exact printed name per year in FARMER_CATEGORY); NCRB does not
                  state whether agricultural labourers are included. 2014+: the farmers/
                  cultivators sub-category. The two are not comparable (definition_break=2014,
                  DEFINITION_BREAK).
  ag_labourers    suicides of agricultural labourers (2014+ only).
  farming_sector  2014+: farmers + ag_labourers (checked row by row against the printed
                  farming-sector total); 2001-2013: = farmers (the pre-2014 category).
Missing-value rule: in NCRB tables "-" means nil -> 0 (textable.parse_number(dash="zero")); a printed
0 is 0 (zero-reporting states, e.g. West Bengal / Telangana in some years, are kept as 0 here; Task 9
decides missing-vs-zero on review). raw_label is the printed label without the serial number.
Only the "TOTAL (ALL INDIA)" row is emitted as unit TOTAL; "TOTAL (STATES)" and "TOTAL (UTs)"
sub-totals are skipped. Andhra Pradesh + Telangana, Dadra & Nagar Haveli + Daman & Diu and J&K +
Ladakh are separate rows (pooled downstream); the merged "D & N HAVELI AND / <serial + values> /
DAMAN & DIU" row (2020+) is re-joined from the label lines above and below its values.

Text: pdfplumber page text (pdftotext -layout splits and merges cells in the 2016+ tables, e.g.
"00" for "0 0"). Pages are pre-selected with plain `pdftotext` (fast): the page must mention the
table number, "STATES" and the cause/profession keyword.

Table locator (all eras; _block): the column-number line "(1) (2) (n) ..." whose numbers include
the configured columns, preceded (within 25 lines) by the "Table <no>" title line; the text from
the title to the column-number line must match the era's header regex and contain "State/UT"
(this excludes the City-wise continuation pages). Exactly one such table must exist. Rows run from
the "STATES" line to the "TOTAL (ALL INDIA)" row. Value columns are addressed by their printed
column numbers: token k of a row is column marker k+2 ((1) = Sl. No., (2) = State/UT). The last
configured column is the value; the others are its components (male, female[, transgender]) and
must add up to it on every row. A row with fewer values than columns (blank cells, e.g. 2020
A & N Islands "Epidemic") is read right-anchored when the target group is the last one on the
page (left-anchored when it is the first) with a warning, else it raises; an unresolved labelled
data row raises. Short rows are accepted only for SHORT_ROWS (year, label) pairs; any other
short row raises.

Sources (rank 2; source_id ncrb_<year>, see outcomes_sources.csv):
  2001-2008  per-table PDFs from the "table content" page (.../accidental-deaths-suicides-in-
             india-table-content.html?year=YYYY), matched by title, not file name:
             heat  "Distribution of Accidental Deaths by Natural Causes & Sex (State, UT &
                   City-wise)" (Table 1.10; 2005 file 1703150138atable110.pdf)
             farm  "Profile of Suicide Victims by Profession During YYYY (State, UT & City-wise)"
                   (Table 2.11; 2004-2008 only)
  2009-2017  the "full report" PDF of the year page (.../accidental-deaths-suicides-in-india-
             year-wise.html?year=YYYY). 2017: the "...FULL-REPORT-2017-new-updated.pdf" file (listed
             under "Publication Team"; its heat table matches the MoES/PIB 2017 figures).
  2018-2024  the full-report PDFs from the NCRB year pages (YEAR_PAGE), obtained from NCRB and not
             redistributed: save them as LOCAL_DIR/ADSI_<year>.pdf; they are copied into
             data/raw/outcomes/ncrb_<year>/ and recorded in the MANIFEST (SHA-256 checked).
  heat_pib1721 (rank 0, cross-check only): MoES/PIB Lok Sabha annexure "State/UT-wise Number of
             Accidental deaths due to Heat/Sun Stroke during 2017-2021" (source: ADSI).
  farm_ogd0112 (rank 1): data.gov.in (OGD Platform India) resource "State/UT-wise professional
             profile of suicide victim during 2001-2012" (NCRB; Government Open Data License -
             India), CSV columns STATE/UT, Year, CAUSE, male/female age groups, Total Male, Total
             Female, Grand Total. CAUSE "Farming/Agriculture Activity" = ADSI "Self-employed
             (Farming/Agriculture)": it reproduces the NCRB Table 2.11 values of every unit and the
             all-India totals 2004-2012 exactly (ogd_validation()), except West Bengal 2012, printed
             "NR" by NCRB and 0 in the CSV -> NaN here. Used for 2001-2003 only (OGD_YEARS), where
             NCRB publishes no profession-by-state table, and only after ogd_emit() has checked, once
             per process, that it reproduces the NCRB parses of 2004-2012 (VALIDATION_YEARS) and that
             each emitted year's units add up to its all-India total.

Heat eras (cause columns: Male, Female, [Transgender,] Total[, %share]):
  2001-2013  Table 1.10 "Flood | Heat Stroke" page: Flood (27)-(30), Heat Stroke (31) M, (32) F,
             (33) Total, (34) %share -> value (33).
  2014-2015  Table 1.8 "Heat/Sun Stroke | Landslide | Lightning": (39) M, (40) F, (41) TG,
             (42) Total -> value (42).
  2016-2019  Table 1.8 "Epidemic | Flood | Heat/Sun Stroke": (35)-(37) M/F/TG, (38) Total.
  2020-2024  Table 1.9, same page layout ("Epidemic@ | Flood | Heat/Sun Stroke").
Farmer eras:
  1997-2000  no source (FARMER_MISSING): not available on the NCRB website with a text layer
             (the chapter-2 PDFs suicides-YYYY.pdf are scans; missing_evidence() caches them).
  2001-2003  farm_ogd0112 (ogd_farmers): no profession-by-state table on the NCRB website (the
             chapter-2 PDFs suicidal-part-2001.pdf / suicidal-2003.pdf have narrative and summary
             tables only; 2002 lists no chapter-2 PDF).
  2004-2013  Table 2.11 "Self-employed (Farming/Agriculture) | Self-employed (Others)": (35) M,
             (36) F, (37) Total, (38) %share -> farmers (37).
  2014       Table 2.7 page "[Agriculture (Total)]# | [Agriculture (Agricultural Labourers)] |
             [Agriculture (Farmers (Sub Total))]": total (63)-(66), labourers (67)-(70), farmers
             (71)-(74) (M, F, TG, Total).
  2015       Table 2A.1 "Incidence and Percentage Change in Suicides in Farming Sector during
             2015": 2014 (3.1) farmers, (3.2) labourers, (3) total; 2015 (4.1), (4.2), (4); (5) %
             change -> 2015 columns.
  2016-2023  Table 2.7: page "Other Self-employed | Farming Sector (Total) | [Farmers/Cultivators
             (Total)]": sector (67)-(70), farmers (71)-(74); next page "Own Land | Lease Land |
             Farming Sector (Agricultural Labourers)": labourers (83)-(86).
"""
import html as htmlmod
import logging
import math
import re
import shutil
import subprocess
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd

from pipeline.outcomes import fetch, records, states, textable
from pipeline.paths import EXTERNAL, check_source

SITE = "https://www.ncrb.gov.in"
ADSI = f"{SITE}/uploads/2022/July/11/custom/adsi"
CUSTOM = f"{SITE}/uploads/nationalcrimerecordsbureau/custom"
POST = f"{SITE}/uploads/nationalcrimerecordsbureau/post"
YEAR_PAGE = SITE + "/accidental-deaths-suicides-in-india-year-wise.html?year={}"
TABLE_PAGE = SITE + "/accidental-deaths-suicides-in-india-table-content.html?year={}"
LOCAL_DIR = EXTERNAL / "ncrb_adsi"     # user-supplied ADSI 2018-2024 full reports (see docstring)
PIB_URL = "https://static.pib.gov.in/WriteReadData/specificdocs/documents/2023/jul/doc2023726228401.pdf"

HEAT_YEARS = range(2001, 2025)
FARMER_YEARS = range(1997, 2024)
DEFINITION_BREAK = 2014

# 2001-2008: per-table PDFs (titles matched on the table-content page; see module docstring)
HEAT_URLS = {y: f"{ADSI}/table-1.10_{y}.pdf" for y in range(2001, 2009) if y != 2005}
HEAT_URLS[2005] = f"{CUSTOM}/1703150138atable110.pdf"
FARMER_URLS = {2004: f"{CUSTOM}/1703069044atable211.pdf", 2005: f"{CUSTOM}/1703151056atable211.pdf",
               2006: f"{CUSTOM}/1703155503Table-211.pdf", 2007: f"{CUSTOM}/1703155592Table-211.pdf",
               2008: f"{CUSTOM}/1703156877Table-211-2008.pdf"}
FULL_REPORTS = {
    2009: f"{ADSI}/adsi-full-report-2009.pdf", 2010: f"{ADSI}/adsi-full-report-2010.pdf",
    2011: f"{ADSI}/adsi-full-report-2011.pdf", 2012: f"{ADSI}/adsi-report-2012.pdf",
    2013: f"{ADSI}/adsi-full-report-2013.pdf",
    2014: f"{POST}/1695471443adsi-2014fullreport-new.pdf",
    2015: f"{POST}/1695471412adsi-2015-full-report-2015new.pdf",
    2016: f"{POST}/1695471250ADSI-2016-FULL-REPORT-2016-new.pdf",
    2017: f"{POST}/1695471120ADSI2017-FULL-REPORT-2017-new-updated.pdf",
}

SOURCES: dict[str, dict] = {}
for _y in HEAT_YEARS:
    if _y in HEAT_URLS:
        _url = HEAT_URLS[_y]
    elif _y in FULL_REPORTS:
        _url = FULL_REPORTS[_y]
    else:
        _url = f"file:{LOCAL_DIR / f'ADSI_{_y}.pdf'}"
    SOURCES[f"ncrb_{_y}"] = {"url": _url, "rank": 2}
SOURCES["heat_pib1721"] = {"url": PIB_URL, "rank": 0}     # cross-check only (never chosen)
OGD_URL = "https://data.gov.in/sites/default/files/datafile/Profession_profile_of_suicide_victims_state.csv"
OGD_PAGE = "https://www.data.gov.in/resource/stateut-wise-professional-profile-suicide-victim-during-2001-2012"
SOURCES["farm_ogd0112"] = {"url": OGD_URL, "rank": 1}
OGD_YEARS = range(2001, 2004)                 # years taken from farm_ogd0112
VALIDATION_YEARS = range(2004, 2013)          # farm_ogd0112 must reproduce NCRB Table 2.11 here
OGD_CAUSE = "Farming/Agriculture Activity"
_OGD_NR = {("WEST BENGAL", 2012)}           # NCRB Table 2.11 prints "NR"; the CSV has 0

# Exact printed name of the farmer category (pdfplumber text of the table header).
FARMER_CATEGORY = {y: "Self–Employed (Farming / Agriculture)" for y in range(2004, 2012)}
FARMER_CATEGORY.update({2012: "Self–employed (farming / agriculture)",
                        2013: "Self–employed (farming / agriculture)",
                        2014: "Self-employed Persons [Agriculture (Farmers (Sub Total))]",
                        2015: "Farmers/ Cultivators"})
FARMER_CATEGORY.update({y: "Persons Engaged in Farming Sector [Farmers/Cultivators (Total)]"
                        for y in range(2016, 2024)})
FARMER_CATEGORY.update({y: OGD_CAUSE for y in OGD_YEARS})   # data.gov.in CAUSE (farm_ogd0112)

# Rows with blank cells that may be read anchored (see _pick); any other short row raises.
SHORT_ROWS = {(2020, "A & N ISLANDS")}

# Years with no state-wise farmer table from NCRB (missing_evidence() caches the documents cited).
FARMER_MISSING = {y: (f"state-wise profession table for {y} not available on the NCRB website with a "
                      f"text layer: the ADSI chapter-2 PDF (suicides-{y}.pdf) is a scan and the "
                      f"table-content page lists chapter-1 tables only")
                  for y in range(1997, 2001)}


@dataclass(frozen=True)
class Column:
    """One variable read from one table: header regex (title..column-number line) and the
    printed column numbers; the last is the value, the others must add up to it."""
    var: str
    header: str
    cols: tuple[str, ...]


@dataclass(frozen=True)
class Era:
    table: str            # printed table number, e.g. "1.10"
    keyword: str          # loose page pre-filter on pdftotext text
    columns: tuple[Column, ...]


_HEAT_KW = r"Heat"
_FARM_KW = r"(?i)farm|agricultur"


def _flex(text: str) -> str:
    return r"\s*".join(re.escape(w) for w in text.split())


def _heat_2001_2013(year: int) -> Era:
    """Table 1.10 page "Flood | Heat Stroke" (per-table PDF to 2008, full report 2009-2013):
    Flood (27)-(30); Heat Stroke (31) Male, (32) Female, (33) Total, (34) %share -> (33)."""
    return Era("1.10", _HEAT_KW, (Column("heat_deaths", r"Flood\s+Heat Stroke", ("(31)", "(32)", "(33)")),))


def _heat_2014_2015(year: int) -> Era:
    """Table 1.8 page "Heat/Sun Stroke | Landslide | Lightning": (39) Male, (40) Female,
    (41) Transgender, (42) Total -> (42)."""
    return Era("1.8", _HEAT_KW, (Column("heat_deaths", r"Heat/Sun Stroke\s+Landslide",
                                        ("(39)", "(40)", "(41)", "(42)")),))


def _heat_2016_2024(year: int) -> Era:
    """Table 1.8 (2016-2019) / 1.9 (2020-2024) page "Epidemic[@] | Flood | Heat/Sun Stroke":
    (35) Male, (36) Female, (37) Transgender, (38) Total -> (38)."""
    return Era("1.8" if year <= 2019 else "1.9", _HEAT_KW,
               (Column("heat_deaths", r"Epidemic@?\s+Flood\s+Heat/Sun Stroke", ("(35)", "(36)", "(37)", "(38)")),))


def _farm_2004_2013(year: int) -> Era:
    """Table 2.11 page "<FARMER_CATEGORY[year]> | Self-employed (Others)" (per-table PDF to 2008,
    full report 2009-2013): (35) Male, (36) Female, (37) Total, (38) %share -> farmers (37)."""
    return Era("2.11", _FARM_KW, (Column("farmers", _flex(FARMER_CATEGORY[year]), ("(35)", "(36)", "(37)")),))


def _farm_2014(year: int) -> Era:
    """Table 2.7 page "[Agriculture (Total)]# | [Agriculture (Agricultural Labourers)] |
    [Agriculture (Farmers (Sub Total))]", each Male, Female, Transgender, Total: printed sector
    (63)-(66), ag_labourers (67)-(70), farmers (71)-(74)."""
    return Era("2.7", _FARM_KW, (
        Column("farmers", r"\[Agriculture \(Farmers \(Sub Total\)\)\]", ("(71)", "(72)", "(73)", "(74)")),
        Column("ag_labourers", r"Agricultural\b.*\bLabourers\)\]", ("(67)", "(68)", "(69)", "(70)")),
        Column("sector_printed", r"\[Agriculture \(Total\)\]", ("(63)", "(64)", "(65)", "(66)"))))


def _farm_2015(year: int) -> Era:
    """Table 2A.1 "Incidence and Percentage Change in Suicides in Farming Sector during 2015":
    2014 (3.1) farmers, (3.2) labourers, (3) total; 2015 (4.1) farmers, (4.2) labourers, (4) total;
    (5) % change. -> farmers (4.1), ag_labourers (4.2), printed sector (4)."""
    hdr = r"Farming Sector during 2015"
    return Era("2A.1", _FARM_KW, (Column("farmers", hdr, ("(4.1)",)), Column("ag_labourers", hdr, ("(4.2)",)),
                                  Column("sector_printed", hdr, ("(4.1)", "(4.2)", "(4)"))))


def _farm_2016_2023(year: int) -> Era:
    """Table 2.7, two pages, each group Male, Female, Transgender, Total: "Other Self-employed
    Persons | Persons Engaged in Farming Sector (Total) | ... [Farmers/Cultivators (Total)]" ->
    printed sector (67)-(70), farmers (71)-(74); "Farmers/Cultivators (Own Land) | (Lease Land) |
    Persons engaged in Farming Sector (Agricultural Labourers / Laborers)" -> ag_labourers (83)-(86)."""
    return Era("2.7", _FARM_KW, (
        Column("farmers", r"\[Farmers/Cultivators \(Total\)\]", ("(71)", "(72)", "(73)", "(74)")),
        Column("ag_labourers", r"\(Agricultural Labou?rers\)", ("(83)", "(84)", "(85)", "(86)")),
        Column("sector_printed", r"Farming Sector .*Sector \(Total\) \[Farmers/Cultivators",
               ("(67)", "(68)", "(69)", "(70)"))))


_HEAT_ERAS = ((2001, 2013, _heat_2001_2013), (2014, 2015, _heat_2014_2015), (2016, 2024, _heat_2016_2024))
_FARM_ERAS = ((2004, 2013, _farm_2004_2013), (2014, 2014, _farm_2014), (2015, 2015, _farm_2015),
              (2016, 2023, _farm_2016_2023))


def _heat_era(year: int) -> Era:
    for lo, hi, era in _HEAT_ERAS:
        if lo <= year <= hi:
            return era(year)
    raise ValueError(f"heat_deaths: year {year} outside {HEAT_YEARS.start}-{HEAT_YEARS.stop - 1}")


def _farmer_era(year: int) -> Era:
    if year in FARMER_MISSING:
        raise ValueError(f"farmer_suicides {year}: {FARMER_MISSING[year]}")
    if year in OGD_YEARS:
        raise ValueError(f"farmer_suicides {year}: no NCRB PDF table; use ogd_farmers()")
    for lo, hi, era in _FARM_ERAS:
        if lo <= year <= hi:
            return era(year)
    raise ValueError(f"farmer_suicides: year {year} outside {FARMER_YEARS.start}-{FARMER_YEARS.stop - 1}")


# ---------------------------------------------------------------- discovery (year pages)

_CTABLE = re.compile(r'<table class="table[^"]*c-table">(.*?)</table>', re.S)
_CELL = re.compile(r'<td class="w-70">\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def index_entries(html: str) -> list[tuple[str, str]]:
    """(absolute URL, title) of the document links in the listing tables of an NCRB ADSI page."""
    out = []
    for block in _CTABLE.findall(html):
        for href, title in _CELL.findall(block):
            text = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", title))).strip()
            out.append((urljoin(SITE, href.strip()), text))
    return out


def _index_html(kind: str, year: int) -> str:
    url = (YEAR_PAGE if kind == "year-wise" else TABLE_PAGE).format(year)
    path = fetch.get("ncrb_index", url, filename=f"{kind}_{year}.html", kind="html")
    return path.read_text(encoding="utf-8", errors="replace")


def year_index(year: int) -> list[str]:
    """URLs of the PDFs listed for `year`: the year page and, for 2001-2008, the table-content
    page (per-table PDFs). Pages are fetched with the browser User-Agent and cached under
    data/raw/outcomes/ncrb_index/."""
    kinds = ["year-wise"] + (["table-content"] if 2001 <= year <= 2008 else [])
    urls = [u for k in kinds for u, _ in index_entries(_index_html(k, year))
            if urlparse(u).path.lower().endswith(".pdf")]
    return list(dict.fromkeys(urls))


def find_by_title(year: int, title_regex: str) -> str:
    """The single table-content PDF of `year` whose listed title matches title_regex."""
    hits = [u for u, t in index_entries(_index_html("table-content", year)) if re.search(title_regex, t, re.I)]
    if len(hits) != 1:
        raise ValueError(f"ncrb {year}: {len(hits)} table-content entries match {title_regex!r}")
    return hits[0]


# ---------------------------------------------------------------- file access

def _source_file(year: int, which: str) -> Path:
    sid = f"ncrb_{year}"
    if which == "farm" and year in FARMER_URLS:
        url = FARMER_URLS[year]
    else:
        url = SOURCES[sid]["url"]
    if url.startswith("file:"):
        return fetch.local_copy(sid, Path(url[len("file:"):]))     # LocalSourceMissing if absent
    return fetch.get(sid, url, kind="pdf")


def _table_re(num: str) -> re.Pattern:
    return re.compile(rf"\bTABLE\W*{re.escape(num)}(?![\d.])", re.I)


@lru_cache(maxsize=1)
def _pdftotext() -> str:
    """Path of the pdftotext binary (Poppler); RuntimeError if it is not installed."""
    exe = shutil.which("pdftotext")
    if exe is None:
        raise RuntimeError("pdftotext (Poppler) not found on PATH; it is required to read NCRB PDFs")
    return exe


def _pdftotext_text(path, *args) -> str:
    out = subprocess.run([_pdftotext(), *args, str(path), "-"], capture_output=True, check=True).stdout
    return out.decode("utf-8", errors="replace")


def _names_year(text: str, year: int) -> bool:
    """True if `text` has a title naming `year` as the report year: "Accidental Deaths & Suicides
    in India [-] YYYY" (report covers) or "during YYYY" / "-- YYYY" / "- YYYY" (table titles)."""
    pat = (rf"(?:Accidental\s+Deaths\s*(?:&|and)\s*Suicides\s+in\s+India|\bduring|(?:^|\s)(?:--|[-–—\ufffd]))"
           rf"\s*[-–—]?\s*{year}\b(?!\s*(?:to|&|and)\s*\d)")
    return re.search(pat, " ".join(text.split()), re.I) is not None


def _pdf_lines(path, page_res=()) -> list[str]:
    """pdfplumber text lines of the pages whose plain pdftotext text matches every regex in
    page_res (whitespace collapsed); all pages when page_res is empty."""
    import pdfplumber
    check_source(path)
    texts = [" ".join(t.split()) for t in _pdftotext_text(path).split("\f")]
    pages = [i for i, t in enumerate(texts) if all(re.search(r, t) for r in page_res)]
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for i in (i for i in pages if i < len(pdf.pages)):     # pdftotext ends with a form feed
            out.extend((pdf.pages[i].extract_text() or "").splitlines())
    return out


def _document_lines(year: int, which: str, era: Era) -> list[str]:
    path = _source_file(year, which)
    if not _names_year(_pdftotext_text(path, "-l", "3"), year):
        raise ValueError(f"ncrb_{year}: no title on the first pages of {path.name} names the year {year}")
    lines = _pdf_lines(path, (_table_re(era.table), r"STATES", era.keyword))
    if not lines:
        raise ValueError(f"ncrb_{year}: no page with Table {era.table} in {path.name}")
    return lines


# ---------------------------------------------------------------- table parsing

_MARK = re.compile(r"^\(\d+(?:\.\d+)?\)$")
_SERIAL = re.compile(r"^\d+\s+")
_TRAIL_MARKS = re.compile(r"[\s@*+#$†‡]+$")
# minus sign of a signed number ("-30.0", Table 2A.1 % change): dropped so the cell tokenises as
# a number; such columns are never read (counts are not negative). A lone "-" (nil) is kept.
_UNSIGN = re.compile(r"(?<!\S)-(?=\d)")


def _split(line: str):
    return textable.split_row(_UNSIGN.sub("", line))


def _clean_label(label: str) -> str:
    return _TRAIL_MARKS.sub("", _SERIAL.sub("", label.strip())).strip()


def _is_all_india(label: str) -> bool:
    return "ALL INDIA" in states.normalise(label)


def _block(lines, table: str, column: Column, where: str):
    """(value-column markers, body lines from after "STATES" to the TOTAL (ALL INDIA) row)."""
    title = _table_re(table)
    hits = []
    for i, ln in enumerate(lines):
        toks = ln.split()
        if len(toks) < 4 or not all(_MARK.match(t) for t in toks) or not set(column.cols) <= set(toks):
            continue
        start = next((j for j in range(i - 1, max(i - 26, -1), -1) if title.search(lines[j])), None)
        if start is None:
            continue
        head = " ".join(" ".join(lines[start:i]).split())
        if re.search(column.header, head) and re.search(r"State\s*/\s*UT", head):
            if toks[:2] != ["(1)", "(2)"]:
                raise ValueError(f"{where}: column numbers {toks[:3]} do not start with (1) (2)")
            hits.append((i, toks[2:]))
    if len(hits) != 1:
        raise ValueError(f"{where}: {len(hits)} tables found for Table {table} with header "
                         f"{column.header!r} and columns {column.cols} (expected 1)")
    i, markers = hits[0]
    k = next((j for j in range(i + 1, min(i + 6, len(lines)))
              if lines[j].strip().rstrip(":").upper() == "STATES"), None)
    if k is None:
        raise ValueError(f"{where}: no 'STATES' line after the column numbers")
    body = []
    for ln in lines[k + 1:]:
        body.append(ln)
        label, toks = _split(ln)
        if toks and _is_all_india(label):
            return markers, body
    raise ValueError(f"{where}: no TOTAL (ALL INDIA) row")


def _rows(body, n: int, where: str):
    """[(unit_id, raw_label, tokens)] of the unit rows and the all-India row.

    A row whose label (serial removed) does not resolve is joined with the numberless line
    above and/or below it ("D & N HAVELI AND" / "31 0 0 ..." / "DAMAN & DIU"); a serial-only row
    has n + 1 tokens and the first is dropped. Unresolved data rows raise; TOTAL (STATES) /
    TOTAL (UTs) are skipped; a numberless line that names a unit and is not used raises.
    """
    parsed = [(ln, *_split(ln)) for ln in body]
    used, out = set(), []

    def numberless(j):
        return 0 <= j < len(parsed) and not parsed[j][2] and parsed[j][1] and j not in used

    for i, (ln, label, toks) in enumerate(parsed):
        if not toks or i in used:
            continue
        lab = _clean_label(label)
        if not lab and len(toks) == n + 1:
            toks = toks[1:]
        uid = states.resolve(lab) if lab else None
        if uid is None:
            for combo in ((i - 1, i + 1), (i - 1,), (i + 1,)):
                if not all(numberless(j) for j in combo):
                    continue
                parts = [_clean_label(parsed[j][1]) for j in combo if j < i] + [lab] + \
                        [_clean_label(parsed[j][1]) for j in combo if j > i]
                joined = " ".join(p for p in parts if p)
                if states.resolve(joined):
                    uid, lab = states.resolve(joined), joined
                    used.update(combo)
                    break
        if uid is None:
            raise ValueError(f"{where}: unresolved state label in data row {ln!r}")
        if uid == "TOTAL" and not _is_all_india(lab):
            continue
        out.append((uid, lab, toks))
    for j, (ln, label, toks) in enumerate(parsed):
        lab = _clean_label(label)
        if not toks and j not in used and lab and states.resolve(lab) not in (None, "TOTAL"):
            raise ValueError(f"{where}: state label without values {ln!r}")
    return out


def _pick(toks, idx, n, label, where, year):
    """Tokens at column indices idx of a row with n columns (see module docstring). A short row
    is accepted only when (year, label) is in SHORT_ROWS."""
    if len(toks) == n:
        return [toks[i] for i in idx]
    if (year, label) not in SHORT_ROWS:
        raise ValueError(f"{where}: row {label!r} has {len(toks)} values, expected {n}")
    if len(toks) < n and max(idx) == n - 1:
        side, picked = "right", [toks[i - n] for i in idx]
    elif len(toks) < n and max(idx) < len(toks) and min(idx) == 0:
        side, picked = "left", [toks[i] for i in idx]
    else:
        raise ValueError(f"{where}: row {label!r} has {len(toks)} values, expected {n}")
    warnings.warn(f"{where}: row {label!r} has {len(toks)} of {n} values (blank cells); target "
                  f"columns read {side}-anchored", UserWarning, stacklevel=4)
    return picked


def _read(lines, era: Era, where: str, year: int) -> dict:
    """{var: {(unit_id, raw_label): value}} for every Column of the era."""
    out = {}
    for col in era.columns:
        w = f"{where} [{col.var}]"
        markers, body = _block(lines, era.table, col, w)
        idx = [markers.index(c) for c in col.cols]
        vals = {}
        for uid, lab, toks in _rows(body, len(markers), w):
            nums = [textable.parse_number(t, dash="zero") for t in _pick(toks, idx, len(markers), lab, w, year)]
            nan = [math.isnan(x) for x in nums]
            if any(nan) and not all(nan):
                raise ValueError(f"{w}: {lab}: partly not reported {nums}")
            if not any(nan) and len(nums) > 1 and sum(nums[:-1]) != nums[-1]:
                raise ValueError(f"{w}: {lab}: components {nums[:-1]} do not add up to {nums[-1]}")
            if (uid, lab) in vals:
                raise ValueError(f"{w}: duplicate row {lab!r}")
            vals[(uid, lab)] = nums[-1]
        out[col.var] = vals
    return out


def _rec(uid, label, year, var, value, source_id):
    return {"unit_id": uid, "raw_label": label, "year": year, "variable": var, "value": value,
            "source_id": source_id, "provisional": False}


def _finish(out) -> pd.DataFrame:
    df = records.make(out)
    records.validate(df)
    return df


# ---------------------------------------------------------------- public parsers

def heat_deaths(year: int, lines=None) -> pd.DataFrame:
    """State heat/sun-stroke deaths (Total column) for one ADSI year, 2001-2024."""
    era = _heat_era(year)
    sid = f"ncrb_{year}"
    if lines is None:
        lines = _document_lines(year, "heat", era)
    vals = _read(lines, era, f"heat_deaths {year} ({sid})", year)["heat_deaths"]
    return _finish([_rec(uid, lab, year, "heat_deaths", v, sid) for (uid, lab), v in vals.items()])


def farmer_suicides(year: int, lines=None) -> pd.DataFrame:
    """Farmer suicides for one year: 2004-2023 from the NCRB PDFs, 2001-2003 from farm_ogd0112
    (ogd_farmers; `lines` does not apply), 1997-2000 raise (FARMER_MISSING).

    Variables: farmers; 2014+ also ag_labourers; farming_sector (= farmers before 2014, farmers +
    ag_labourers from 2014, which must equal the printed farming-sector total row by row)."""
    if year in OGD_YEARS:
        if lines is not None:
            raise ValueError(f"farmer_suicides {year}: from the farm_ogd0112 CSV; lines do not apply")
        return ogd_emit(years=(year,))
    era = _farmer_era(year)
    sid = f"ncrb_{year}"
    if lines is None:
        lines = _document_lines(year, "farm", era)
    where = f"farmer_suicides {year} ({sid})"
    got = _read(lines, era, where, year)
    farmers, labourers = got["farmers"], got.get("ag_labourers")
    out = [_rec(u, lab, year, "farmers", v, sid) for (u, lab), v in farmers.items()]
    if labourers is None:
        out += [_rec(u, lab, year, "farming_sector", v, sid) for (u, lab), v in farmers.items()]
        return _finish(out)
    printed = got["sector_printed"]
    if set(labourers) != set(farmers) or set(printed) != set(farmers):
        raise ValueError(f"{where}: farmer, labourer and sector tables list different rows: "
                         f"{sorted(set(farmers) ^ set(labourers) | set(farmers) ^ set(printed))}")
    for key, f in farmers.items():
        lab_v, sector = labourers[key], f + labourers[key]
        if sector != printed[key]:
            raise ValueError(f"{where}: {key[1]}: farmers {f} + labourers {lab_v} != printed "
                             f"farming-sector total {printed[key]}")
        out.append(_rec(key[0], key[1], year, "ag_labourers", lab_v, sid))
        out.append(_rec(key[0], key[1], year, "farming_sector", sector, sid))
    return _finish(out)


def ogd_farmers(years=OGD_YEARS, path=None) -> pd.DataFrame:
    """farm_ogd0112 rows of CAUSE "Farming/Agriculture Activity" for `years` (default 2001-2003):
    variables farmers and farming_sector (= farmers; pre-2014 category). Total Male + Total
    Female must equal Grand Total on every row. "TOTAL (STATES)"/"TOTAL (UTs)" are skipped;
    "TOTAL (ALL INDIA)" -> TOTAL. _OGD_NR cells (NCRB "NR", 0 in the CSV) -> NaN."""
    sid = "farm_ogd0112"
    path = check_source(Path(path)) if path is not None else fetch.get(sid, OGD_URL)
    d = pd.read_csv(path)
    need = {"STATE/UT", "Year", "CAUSE", "Total Male", "Total Female", "Grand Total"}
    if not need <= set(d.columns):
        raise ValueError(f"{sid}: columns {sorted(need - set(d.columns))} missing")
    d = d[(d.CAUSE == OGD_CAUSE) & d.Year.isin(list(years))]
    out = []
    for _, r in d.iterrows():
        label, year = str(r["STATE/UT"]).strip(), int(r.Year)
        uid = states.resolve(label)
        if uid is None:
            raise ValueError(f"{sid}: unresolved state label {label!r}")
        if uid == "TOTAL" and not _is_all_india(label):
            continue
        if r["Total Male"] + r["Total Female"] != r["Grand Total"]:
            raise ValueError(f"{sid}: {label} {year}: Total Male + Total Female != Grand Total")
        value = math.nan if (label, year) in _OGD_NR else float(r["Grand Total"])
        out += [_rec(uid, label, year, v, value, sid) for v in ("farmers", "farming_sector")]
    if {y for y in years} - {rec["year"] for rec in out}:
        raise ValueError(f"{sid}: no rows for {sorted(set(years) - {rec['year'] for rec in out})}")
    return _finish(out)


def _ncrb_reference(years) -> pd.DataFrame:
    """NCRB Table 2.11 farmer records of `years` (the PDFs; raises FetchError/LocalSourceMissing
    when a raw file cannot be obtained)."""
    return pd.concat([farmer_suicides(y) for y in years], ignore_index=True)


def ogd_validation(years=None, path=None) -> pd.DataFrame:
    """farm_ogd0112 vs the NCRB Table 2.11 farmers of `years` (default VALIDATION_YEARS), per unit
    (pooled) and all-India: the unit-years that differ, including units missing on one side
    (NaN = NaN counts as equal, so the _OGD_NR cells set to NaN match NCRB's "NR"). Empty = the
    CSV reproduces NCRB."""
    years = VALIDATION_YEARS if years is None else years
    ncrb = _ncrb_reference(years)                  # first: no OGD download if NCRB is unavailable
    ogd = ogd_farmers(years=years, path=path)
    key = ["unit_id", "year"]
    a = ncrb[ncrb.variable == "farmers"].groupby(key).value.sum(min_count=1)
    b = ogd[ogd.variable == "farmers"].groupby(key).value.sum(min_count=1)
    m = pd.concat([a, b], axis=1, keys=["ncrb", "ogd"])
    same = (m.ncrb == m.ogd) | (m.ncrb.isna() & m.ogd.isna())
    return m[~same]


_VALIDATED: dict = {}      # OGD file -> True once ogd_validation() found no mismatch (per process)


def _require_validated(path=None) -> None:
    key = str(Path(path).resolve()) if path is not None else "farm_ogd0112"
    if key in _VALIDATED:
        return
    mism = ogd_validation(path=path)
    if not mism.empty:
        rows = "; ".join(f"{u} {y}: NCRB {r.ncrb} vs OGD {r.ogd}" for (u, y), r in mism.head(10).iterrows())
        raise ValueError(f"farm_ogd0112 does not reproduce NCRB Table 2.11 {min(VALIDATION_YEARS)}-"
                         f"{max(VALIDATION_YEARS)}: {len(mism)} unit-year(s) differ ({rows}); "
                         f"2001-2003 are not emitted")
    _VALIDATED[key] = True


def ogd_emit(years=OGD_YEARS, path=None) -> pd.DataFrame:
    """farm_ogd0112 farmers for `years` (2001-2003), emitted only after _require_validated() (the
    file reproduces the NCRB 2004-2012 parses; cached per process) and only if, for every emitted
    year, the sum of the units equals the file's all-India total."""
    _require_validated(path)
    df = ogd_farmers(years=years, path=path)
    f = df[df.variable == "farmers"]
    for year, g in f.groupby("year"):
        total = g[g.unit_id == "TOTAL"].value
        units = g[g.unit_id != "TOTAL"].value.sum()
        if len(total) != 1 or units != total.iloc[0]:
            raise ValueError(f"farm_ogd0112 {year}: sum of units {units:.0f} != all-India total "
                             f"{total.tolist()}")
    return df


def missing_evidence(year: int) -> dict:
    """Cache (fetch.get, MANIFEST-recorded) the year page and its chapter-2 (suicides) PDF of a year
    without an NCRB state-wise profession table, and summarise them: chapter2_pdf (URL or None),
    text_chars (non-blank characters pdftotext extracts; 0 for a scan) and
    has_state_profession_table (a "Profession" title followed by state rows)."""
    urls = [u for u in year_index(year) if re.search(r"/suicid[a-z-]*[-_]?(?:part-)?\d{4}\.pdf$", u, re.I)]
    if len(urls) > 1:
        raise ValueError(f"ncrb {year}: several chapter-2 PDFs {urls}")
    out = {"year": year, "year_page": YEAR_PAGE.format(year), "chapter2_pdf": urls[0] if urls else None,
           "text_chars": None, "has_state_profession_table": False}
    if urls:
        text = _pdftotext_text(fetch.get(f"ncrb_{year}", urls[0], kind="pdf"))
        out["text_chars"] = len("".join(text.split()))
        out["has_state_profession_table"] = bool(re.search(
            r"Profession[^\n]*\n(?:.*\n){0,30}?\s*\d+\s+ANDHRA PRADESH\s+\d", text, re.I))
    return out


_PIB_YEARS = (2017, 2018, 2019, 2020, 2021)


def pib_heat_2017_2021(lines=None) -> pd.DataFrame:
    """MoES/PIB annexure "State/UT-wise Number of Accidental deaths due to Heat/Sun Stroke during
    2017-2021" (source: ADSI), source_id heat_pib1721 - a cross-check of ncrb_2017..ncrb_2021.

    pdfplumber text: header "SN State/UT 2017 2018 2019 2020 2021"; rows serial, label, 5 values;
    "TOTAL STATE(S)" / "TOTAL UT(S)" skipped, "TOTAL (ALL INDIA)" -> TOTAL. Footnote marks after
    labels ("@ +", "@ *") are dropped from raw_label. "-" (Ladakh 2017-2019, before the UT
    existed; J&K includes Ladakh then) = nil -> 0, the NCRB rule."""
    sid = "heat_pib1721"
    if lines is None:
        lines = _pdf_lines(fetch.get(sid, PIB_URL, kind="pdf"))
    where = f"heat deaths 2017-2021 ({sid})"
    text = " ".join(" ".join(lines).split())
    if not re.search(r"Heat/Sun Stroke during 2017-2021", text):
        raise ValueError(f"{where}: title not found")
    head = next((i for i, ln in enumerate(lines)
                 if re.search(r"State/UT\s+" + r"\s+".join(map(str, _PIB_YEARS)) + r"\s*$", ln)), None)
    if head is None:
        raise ValueError(f"{where}: year header {_PIB_YEARS} not found")
    body = []
    for ln in lines[head + 1:]:
        body.append(ln)
        label, toks = _split(ln)
        if toks and _is_all_india(label):
            break
    else:
        raise ValueError(f"{where}: no TOTAL (ALL INDIA) row")
    out = []
    for uid, lab, toks in _rows(body, len(_PIB_YEARS), where):
        if len(toks) != len(_PIB_YEARS):
            raise ValueError(f"{where}: row {lab!r} has {len(toks)} values, expected {len(_PIB_YEARS)}")
        out += [_rec(uid, lab, y, "heat_deaths", textable.parse_number(t, dash="zero"), sid)
                for y, t in zip(_PIB_YEARS, toks)]
    return _finish(out)


# ---------------------------------------------------------------- all

def _collect(calls, missing=None, reasons=None) -> pd.DataFrame:
    parts, missing, reasons = [], list(missing or []), dict(reasons or {})
    for sid, call in calls:
        try:
            parts.append(call())
        except (fetch.FetchError, fetch.LocalSourceMissing) as e:
            warnings.warn(f"{sid}: raw file unavailable; skipped ({e})", UserWarning, stacklevel=3)
            missing.append(sid)
            reasons[sid] = f"raw file unavailable: {e}"
    df = pd.concat(parts, ignore_index=True) if parts else records.make([])
    records.validate(df)
    df.attrs["missing_sources"] = missing
    df.attrs["missing_reasons"] = reasons
    return df


def all_heat() -> pd.DataFrame:
    """heat_deaths 2001-2024 (ncrb_<year>) plus the heat_pib1721 cross-check. A source whose raw
    file cannot be obtained is skipped with a warning and listed in df.attrs["missing_sources"]."""
    calls = [(f"ncrb_{y}", lambda y=y: heat_deaths(y)) for y in HEAT_YEARS]
    calls.append(("heat_pib1721", lambda: pib_heat_2017_2021()))
    return _collect(calls)


def all_farmers() -> pd.DataFrame:
    """farmer_suicides 2001-2023 (2001-2003 from farm_ogd0112 via ogd_emit; if the NCRB 2004-2012
    sources needed to validate it are unavailable, 2001-2003 are not emitted and farm_ogd0112 is
    listed in the missing sources with reason "validation sources unavailable"). 1997-2000 have no source
    (FARMER_MISSING): one warning, and their ncrb_<year> ids are listed in
    df.attrs["missing_sources"] with reasons in df.attrs["missing_reasons"] (for Task 9's
    missing_source rows)."""
    lo, hi = min(FARMER_MISSING), max(FARMER_MISSING)
    warnings.warn(f"farmer suicides {lo}-{hi}: no state-wise table available on the NCRB website with a "
                  f"text layer (scanned chapter-2 PDFs); not parsed", UserWarning, stacklevel=2)
    missing = [f"ncrb_{y}" for y in sorted(FARMER_MISSING)]
    reasons = {f"ncrb_{y}": r for y, r in FARMER_MISSING.items()}
    calls = [(f"ncrb_{y}", lambda y=y: farmer_suicides(y))
             for y in FARMER_YEARS if y not in FARMER_MISSING and y not in OGD_YEARS]
    try:
        _require_validated()
    except (fetch.FetchError, fetch.LocalSourceMissing) as e:
        warnings.warn(f"farm_ogd0112: {min(OGD_YEARS)}-{max(OGD_YEARS)} not emitted, validation sources "
                      f"unavailable ({e})", UserWarning, stacklevel=2)
        missing.append("farm_ogd0112")
        reasons["farm_ogd0112"] = f"validation sources unavailable: {e}"
    else:
        calls.insert(0, ("farm_ogd0112", lambda: ogd_emit()))
    return _collect(calls, missing, reasons)
