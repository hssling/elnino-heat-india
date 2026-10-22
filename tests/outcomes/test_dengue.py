import math
from pathlib import Path

import pandas as pd
import pytest

from pipeline.outcomes import dengue, fetch, records

FIX = Path(__file__).parent / "fixtures"


def val(df, unit, year, var):
    return df[(df.unit_id == unit) & (df.year == year) & (df.variable == var)].value.sum()


def one(df, unit, year, var):
    s = df[(df.unit_id == unit) & (df.year == year) & (df.variable == var)]
    assert len(s) == 1, s
    return s.iloc[0]


def page_html():
    return (FIX / "dengue_nvbdcp.html").read_text(encoding="utf-8")


def lines(name):
    return (FIX / name).read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------- brief tests

def test_nvbdcp_page_golden():
    df = dengue.nvbdcp_page(html=page_html())
    records.validate(df)
    assert (val(df, "DL", 2010, "cases"), val(df, "DL", 2010, "deaths")) == (6_259, 8)
    assert (val(df, "TN", 2012, "cases"), val(df, "TN", 2012, "deaths")) == (12_826, 66)


def test_ncvbdc_2126_golden():
    df = dengue.ncvbdc_2126(lines=lines("dengue_ncvbdc.txt"))
    assert (val(df, "AP_TG", 2021, "cases") >= 4_760) and val(df, "AR", 2021, "cases") == 7


def test_opendengue_resolves_split_labels_and_keeps_moh_rows(tmp_path):
    src = pd.DataFrame({"adm_1_name": ["ARUNACHAL\nPRADESH", "DELHI", "DELHI"], "Year": [2016, 2016, 2012],
                        "dengue_total": [10, 100, 50], "UUID": ["MOH-IND-x", "MOH-IND-x", "LITERATURE-IND-y"]})
    p = tmp_path / "od.csv"
    src.to_csv(p, index=False)
    df = dengue.opendengue(path=p)
    assert set(df.unit_id) == {"AR", "DL"} and set(df.year) == {2016}


# ---------------------------------------------------------------- NVBDCP page

def test_nvbdcp_page_years_provisional_and_total():
    df = dengue.nvbdcp_page(html=page_html())
    assert set(df.year) == set(range(2007, 2014))
    assert set(df.variable) == {"cases", "deaths"}
    assert set(df.source_id) == {"den_nvbdcp"}
    # header "2012*" (provisional till 31 Dec) and "2013**" (provisional till 28 Oct 2013)
    assert df[df.year.isin([2012, 2013])].provisional.all()
    assert not df[df.year <= 2011].provisional.any()
    assert (val(df, "TOTAL", 2010, "cases"), val(df, "TOTAL", 2013, "deaths")) == (28_292, 138)
    assert one(df, "DL", 2007, "cases").raw_label == "Delhi"
    assert "LD" not in set(df.unit_id)          # not listed on the page: absent (NaN downstream), never 0


def test_nvbdcp_page_unresolved_label_raises():
    with pytest.raises(ValueError, match="Atlantis"):
        dengue.nvbdcp_page(html=page_html().replace(">Delhi<", ">Atlantis<"))


def test_nvbdcp_page_label_aliases_and_pooling():
    html = page_html().replace(">Delhi<", ">Himachal Pd.<").replace(">Tamil Nadu<", ">A& N Island<")
    df = dengue.nvbdcp_page(html=html)
    assert val(df, "HP", 2010, "cases") == 6_259 and val(df, "AN", 2012, "deaths") == 66
    two = page_html().replace(">Delhi<", ">D&amp;N Haveli<").replace(">Tamil Nadu<", ">Daman &amp; Diu<")
    df = dengue.nvbdcp_page(html=two)
    assert val(df, "DNH_DD", 2012, "cases") == 2_093 + 12_826      # summed, not overwritten


def test_nvbdcp_page_blank_cell_is_nan_and_header_checked():
    html = page_html().replace('<td class="table_text">6259</td>', '<td class="table_text"></td>')
    df = dengue.nvbdcp_page(html=html)
    assert math.isnan(one(df, "DL", 2010, "cases").value)
    with pytest.raises(ValueError, match="C/D"):
        dengue.nvbdcp_page(html=page_html().replace('<td class="menu_style">D</td>',
                                                    '<td class="menu_style">X</td>', 1))


# ---------------------------------------------------------------- 2014 (NHP 2018 fallback)

def test_nhp2018_2013_2017():
    df = dengue.nhp_2018(lines=lines("dengue_nhp2018.txt"))
    records.validate(df)
    # ruling P5: all columns 2013-2017 emitted (2015-2016 deaths needed); "2017(P)" provisional
    assert set(df.year) == set(range(2013, 2018)) and set(df.source_id) == {"den_nhp2018"}
    assert df[df.year == 2017].provisional.all() and not df[df.year < 2017].provisional.any()
    assert (val(df, "DL", 2015, "deaths"), val(df, "DL", 2016, "deaths")) == (60, 10)   # golden
    assert (val(df, "TN", 2015, "deaths"), val(df, "TN", 2016, "cases")) == (12, 2_531)
    tg17 = df[df.raw_label.str.startswith("Telangana") & (df.year == 2017) & (df.variable == "deaths")]
    assert math.isnan(tg17.value.item())                               # "-"
    assert (val(df, "DL", 2014, "cases"), val(df, "DL", 2014, "deaths")) == (995, 3)
    assert val(df, "AP_TG", 2014, "cases") == 1_262 + 704
    tg = df[df.raw_label.str.startswith("Telangana") & (df.year == 2013) & (df.variable == "cases")]
    assert len(tg) == 1 and math.isnan(tg.value.item())               # "-": not reported -> NaN
    assert val(df, "DNH_DD", 2014, "cases") == 641 + 46
    assert (val(df, "TOTAL", 2014, "cases"), val(df, "TOTAL", 2014, "deaths")) == (40_571, 137)
    assert (val(df, "TN", 2013, "cases"), val(df, "TN", 2013, "deaths")) == (6_122, 0)


def test_nvbdcp_2014_without_fallback_raises(monkeypatch):
    def fail(*a, **k):
        raise fetch.FetchError("HTTP 429")

    monkeypatch.setattr(dengue.fetch, "get", fail)
    with pytest.raises(fetch.FetchError):
        dengue.nvbdcp_2014(fallback=False)


def test_nvbdcp_2014_falls_back_to_nhp(monkeypatch):
    def fail(*a, **k):
        raise fetch.FetchError("HTTP 429")

    monkeypatch.setattr(dengue.fetch, "get", fail)
    monkeypatch.setattr(dengue, "nhp_2018", lambda lines=None: records.make(
        [{"unit_id": "DL", "raw_label": "Delhi", "year": 2014, "variable": "cases", "value": 995.0,
          "source_id": "den_nhp2018", "provisional": False}]))
    with pytest.warns(UserWarning, match="den_nvbdcp14.*den_nhp2018"):
        df = dengue.nvbdcp_2014()
    assert set(df.source_id) == {"den_nhp2018"}


def test_nvbdcp_2014_from_page_keeps_2013_2014():
    html = page_html()      # relabel the header as a later snapshot: 2008 ... 2013, 2014*
    for a, b in (("2013**", "2014*"), ("2012*", "2013"), (">2011<", ">2012<"), (">2010<", ">2011<"),
                 (">2009<", ">2010<"), (">2008<", ">2009<"), (">2007<", ">2008<")):
        html = html.replace(a, b, 1)
    df = dengue.nvbdcp_2014(html=html)
    assert set(df.year) == {2013, 2014} and set(df.source_id) == {"den_nvbdcp14"}
    assert df[df.year == 2014].provisional.all() and not df[df.year == 2013].provisional.any()


# ---------------------------------------------------------------- NCVBDC 2021-2026

def test_ncvbdc_2126_years_marks_and_rows():
    df = dengue.ncvbdc_2126(lines=lines("dengue_ncvbdc.txt"))
    records.validate(df)
    assert set(df.year) == set(range(2021, 2026))                     # 2026 (till April) dropped
    assert (val(df, "AP_TG", 2021, "cases"), val(df, "AP_TG", 2021, "deaths")) == (4_760 + 7_135, 0)
    assert val(df, "DNH_DD", 2022, "cases") == 685 + 228
    assert val(df, "JK", 2023, "cases") == 6_403                       # Ladakh "Non endemic": no row
    assert val(df, "JK", 2021, "cases") == 1_709 and len(df[(df.unit_id == "JK") & (df.year == 2021)]) == 2
    assert not df.raw_label.str.contains("Ladakh").any()
    assert val(df, "TOTAL", 2024, "cases") == 233_519
    wb = df[df.unit_id == "WB"].set_index(["year", "variable"])
    assert wb.loc[(2023, "cases")].value == 30_683 and wb.loc[(2023, "cases")].provisional  # *Till 13.9.2023
    assert wb.loc[(2023, "deaths")].provisional and wb.loc[(2024, "cases")].provisional     # **Till 21.2.2024
    assert not wb.loc[(2022, "cases")].provisional
    assert math.isnan(wb.loc[(2025, "cases")].value) and math.isnan(wb.loc[(2025, "deaths")].value)  # NR
    assert not df[df.unit_id != "WB"].provisional.any()


def test_ncvbdc_2126_year_header_checked():
    bad = [ln.replace("2021 2022", "2020 2022") for ln in lines("dengue_ncvbdc.txt")]
    with pytest.raises(ValueError, match="year header"):
        dengue.ncvbdc_2126(lines=bad)


# ---------------------------------------------------------------- OpenDengue

def test_opendengue_rule_years_and_labels(tmp_path):
    src = pd.DataFrame({
        "adm_1_name": ["A&N ISLAND", "A & N ISLAND", "TELANGANA", "ANDHRA PRADESH", "DELHI", "DELHI", "GOA"],
        "Year": [2023, 2024, 2016, 2016, 2014, 2025, 2015],
        "dengue_total": [5, 6, 10, 20, 1, 2, 3],
        "UUID": ["MOH-IND-20152024-Y01-02", "MOH-IND-20152024-Y01-02", "MOH-IND-2022-Y01-01",
                 "MOH-IND-20152024-Y01-00", "MOH-IND-20152024-Y01-00", "MOH-IND-20152024-Y01-00",
                 "LITERATURE-IND-19972012-Y01-01"]})
    p = tmp_path / "od.csv"
    src.to_csv(p, index=False)
    df = dengue.opendengue(path=p)
    records.validate(df)
    assert set(df.variable) == {"cases"} and set(df.source_id) == {"den_opendengue"}
    assert set(zip(df.unit_id, df.year)) == {("AN", 2023), ("AN", 2024), ("AP_TG", 2016)}
    assert val(df, "AP_TG", 2016, "cases") == 30


def test_opendengue_west_bengal_partial_years_provisional(tmp_path):
    src = pd.DataFrame({"adm_1_name": ["WEST BENGAL"] * 3 + ["DELHI"], "Year": [2022, 2023, 2024, 2023],
                        "dengue_total": [67271, 30683, 441, 16866], "UUID": ["MOH-IND-x"] * 4})
    p = tmp_path / "od.csv"
    src.to_csv(p, index=False)
    df = dengue.opendengue(path=p).set_index(["unit_id", "year"])
    # NCVBDC footnotes "*Till 13.9.2023", "**Till 21.2.2024": partial-year counts
    assert df.loc[("WB", 2023)].provisional and df.loc[("WB", 2024)].provisional
    assert not df.loc[("WB", 2022)].provisional and not df.loc[("DL", 2023)].provisional
    src.loc[1, "dengue_total"] = 31_000                                  # a later (final) figure: not flagged
    src.to_csv(p, index=False)
    assert not dengue.opendengue(path=p).set_index(["unit_id", "year"]).loc[("WB", 2023)].provisional


def test_opendengue_unresolved_label_raises(tmp_path):
    p = tmp_path / "od.csv"
    pd.DataFrame({"adm_1_name": ["ATLANTIS"], "Year": [2016], "dengue_total": [1],
                  "UUID": ["MOH-IND-x"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="ATLANTIS"):
        dengue.opendengue(path=p)


# ---------------------------------------------------------------- all_records / sources

def test_all_records_skips_unavailable_sources(monkeypatch):
    empty = records.make([])
    ok = records.make([{"unit_id": "DL", "raw_label": "Delhi", "year": 2010, "variable": "cases",
                        "value": 1.0, "source_id": "den_nvbdcp", "provisional": False}])

    def unavailable(*a, **k):
        raise fetch.FetchError("HTTP 429")

    monkeypatch.setattr(dengue, "nvbdcp_page", lambda html=None, source_id="den_nvbdcp":
                        unavailable() if source_id == "den_nvbdcp12" else ok)
    monkeypatch.setattr(dengue, "nvbdcp_2014", lambda fallback=True: unavailable())
    monkeypatch.setattr(dengue, "state_table", lambda sid, lines=None:
                        unavailable() if sid == "den_nhp2021" else empty)
    monkeypatch.setattr(dengue, "opendengue", lambda path=None: empty)
    monkeypatch.setattr(dengue, "ncvbdc_2126", lambda lines=None: empty)
    with pytest.warns(UserWarning, match="raw file unavailable"):
        df = dengue.all_records()
    assert df.attrs["missing_sources"] == ["den_nvbdcp12", "den_nvbdcp14", "den_nhp2021"]
    assert set(df.source_id) == {"den_nvbdcp"}


def test_sources_table_covers_all_sources():
    table = pd.read_csv(Path(dengue.__file__).resolve().parents[1] / "reference" / "outcomes_sources.csv")
    den = table[table.outcome == "dengue"]
    assert set(den.source_id) == set(dengue.SOURCES)
    r = {k: v["rank"] for k, v in dengue.SOURCES.items()}
    assert r["den_ncvbdc"] > r["den_opendengue"] > r["den_nhp2023"] > r["den_nhp2021"] > r["den_nhp2019"] \
        > r["den_nhp2018"] > r["den_nvbdcp14"] > r["den_ar1415"] > r["den_nvbdcp"] > r["den_nvbdcp12"]
    assert dict(zip(den.source_id, den["rank"])) == r and len(set(r.values())) == len(r)     # no ties


def test_nhp2018_skips_contents_entry_and_checks_header():
    body = lines("dengue_nhp2018.txt")
    toc = ["3.1.5 State/UT wise Cases and Deaths due to Dengue in India, 2013 – 2017 (P) 87",
           "3.1.6 State/UT wise Cases and Deaths due to Chikungunya 88", "All India Total 1 2 3 4 5 6 7 8 9 10"]
    assert dengue.nhp_2018(lines=toc + body).equals(dengue.nhp_2018(lines=body))
    with pytest.raises(ValueError, match="year header"):
        dengue.nhp_2018(lines=[ln.replace("2016 2017(P)", "2016") for ln in body])


def test_nvbdcp_page_any_year_suffix_is_provisional():
    df = dengue.nvbdcp_page(html=page_html().replace(">2010<", ">2010 (P)<", 1))
    assert one(df, "DL", 2010, "cases").provisional and not one(df, "DL", 2009, "cases").provisional


# ---------------------------------------------------------------- NHP 2019/2021/2023, annual report 2014-15

def test_nhp2019_golden():
    df = dengue.state_table("den_nhp2019", lines=lines("dengue_nhp2019.txt"))
    records.validate(df)
    assert set(df.year) == set(range(2014, 2019)) and set(df.source_id) == {"den_nhp2019"}
    assert df[df.year == 2018].provisional.all() and not df[df.year < 2018].provisional.any()
    assert (val(df, "MH", 2017, "deaths"), val(df, "KL", 2018, "deaths")) == (65, 32)        # golden
    assert val(df, "AP_TG", 2017, "cases") == 4_925 + 5_369
    assert val(df, "DNH_DD", 2017, "cases") == 2_064 + 59
    assert (val(df, "TOTAL", 2017, "cases"), val(df, "TOTAL", 2017, "deaths")) == (188_401, 325)


def test_nhp2021_golden_and_merged_dnh_dd():
    df = dengue.state_table("den_nhp2021", lines=lines("dengue_nhp2021.txt"))
    records.validate(df)
    assert set(df.year) == set(range(2016, 2021))
    assert df[df.year == 2020].provisional.all() and not df[df.year < 2020].provisional.any()
    assert (val(df, "PB", 2020, "deaths"), val(df, "UP", 2019, "deaths")) == (22, 26)        # golden
    assert val(df, "DNH_DD", 2019, "cases") == 1_491 + 625
    dnh20 = df[(df.unit_id == "DNH_DD") & (df.year == 2020)]
    assert len(dnh20) == 2 and val(df, "DNH_DD", 2020, "cases") == 319 and val(df, "DNH_DD", 2020, "deaths") == 0
    assert (val(df, "TOTAL", 2019, "cases"), val(df, "TOTAL", 2019, "deaths")) == (205_243, 166)


def test_nhp2023_golden_emits_2018_2020_only():
    df = dengue.state_table("den_nhp2023", lines=lines("dengue_nhp2023.txt"))
    records.validate(df)
    assert set(df.year) == {2018, 2019, 2020} and not df.provisional.any()
    assert (val(df, "WB", 2018, "deaths"), val(df, "KL", 2019, "deaths")) == (86, 16)        # golden
    assert val(df, "RJ", 2020, "deaths") == 7
    assert val(df, "AN", 2018, "cases") == 49                       # "Andaman & Nicobar" / "Islands"
    assert val(df, "JK", 2018, "cases") == 214                      # J&K 214 + Ladakh 0
    assert val(df, "DNH_DD", 2020, "cases") == 319 and val(df, "DNH_DD", 2019, "cases") == 1_491 + 625
    assert (val(df, "TOTAL", 2020, "cases"), val(df, "TOTAL", 2020, "deaths")) == (44_585, 66)   # India row first


def test_ar1415_golden():
    df = dengue.state_table("den_ar1415", lines=lines("dengue_ar1415.txt"))
    records.validate(df)
    assert set(df.year) == set(range(2010, 2015))
    assert df[df.year == 2014].provisional.all() and not df[df.year < 2014].provisional.any()
    assert (val(df, "DL", 2012, "cases"), val(df, "DL", 2012, "deaths")) == (2_093, 4)      # golden
    assert (val(df, "TN", 2012, "cases"), val(df, "TN", 2012, "deaths")) == (12_826, 66)
    assert val(df, "AP_TG", 2014, "cases") == 805 + 606 and val(df, "AN", 2010, "cases") == 25
    assert (val(df, "TOTAL", 2012, "cases"), val(df, "TOTAL", 2013, "deaths")) == (50_222, 193)


def test_state_table_partial_row_without_combined_line_raises():
    body = [ln for ln in lines("dengue_nhp2021.txt") if ln.strip() != "319 0"]
    with pytest.raises(ValueError, match="D & N Haveli"):
        dengue.state_table("den_nhp2021", lines=body)


def test_state_table_header_checked():
    body = [ln.replace("2019 2020 (Prov.)", "2019") for ln in lines("dengue_nhp2021.txt")]
    with pytest.raises(ValueError, match="year header"):
        dengue.state_table("den_nhp2021", lines=body)


def test_state_table_unresolved_full_row_raises():
    body = [ln.replace("Punjab", "Pudduland") for ln in lines("dengue_nhp2021.txt")]
    with pytest.raises(ValueError, match="Pudduland"):
        dengue.state_table("den_nhp2021", lines=body)


# ---------------------------------------------------------------- Ruling P17: partial-year marker

def partial(df):
    return set(zip(df[df.raw_label.map(records.is_partial)].unit_id, df[df.raw_label.map(records.is_partial)].year))


def test_ncvbdc_starred_cells_are_partial_year():
    df = dengue.ncvbdc_2126(lines=lines("dengue_ncvbdc.txt"))
    assert partial(df) == {("WB", 2023), ("WB", 2024)}                      # *Till 13.9.2023, **Till 21.2.2024
    assert one(df, "WB", 2023, "deaths").raw_label == "West Bengal [partial_year]"
    body = [ln for ln in lines("dengue_ncvbdc.txt") if not ln.startswith("*Till")]
    with pytest.raises(ValueError, match="partial-year footnote"):
        dengue.ncvbdc_2126(lines=body)


def test_opendengue_copies_of_partial_counts_are_partial_year(tmp_path):
    src = pd.DataFrame({"adm_1_name": ["WEST BENGAL"] * 3, "Year": [2022, 2023, 2024],
                        "dengue_total": [67271, 30683, 441], "UUID": ["MOH-IND-x"] * 3})
    p = tmp_path / "od.csv"
    src.to_csv(p, index=False)
    assert partial(dengue.opendengue(path=p)) == {("WB", 2023), ("WB", 2024)}
    src.loc[1, "dengue_total"] = 31_000                                     # a later (final) figure
    src.to_csv(p, index=False)
    assert partial(dengue.opendengue(path=p)) == {("WB", 2024)}


def test_nvbdcp_page_partial_year_column():
    df = dengue.nvbdcp_page(html=page_html())
    # "* Provisional till 31st December" (2012: whole year) | "** Provisional till 28th October 2013"
    assert {y for _, y in partial(df)} == {2013} and partial(df) >= {("DL", 2013)}
    html = page_html().replace("Provisional till 28th October 2013", "Provisional till 31st December 2013")
    assert not partial(dengue.nvbdcp_page(html=html))


def test_ar1415_2014_upto_november_is_partial_year():
    df = dengue.state_table("den_ar1415", lines=lines("dengue_ar1415.txt"))
    assert {y for _, y in partial(df)} == {2014}
    assert not partial(dengue.state_table("den_nhp2021", lines=lines("dengue_nhp2021.txt")))
