from pathlib import Path

import pandas as pd
import pytest

from pipeline.outcomes import fetch, ncrb, records

FIX = Path(__file__).parent / "fixtures"


def L(name):
    return (FIX / name).read_text(encoding="utf-8").splitlines()


def val(df, unit, var="heat_deaths"):
    return df[(df.unit_id == unit) & (df.variable == var)].value.sum()


# ---------------------------------------------------------------- brief tests

@pytest.mark.parametrize("year,fixture,expect", [
    (2003, "ncrb_heat_2003.txt", {"AP_TG": 100, "GJ": 30}),
    (2010, "ncrb_heat_2010.txt", {"AP_TG": 197, "GJ": 58, "MH": 137, "OD": 130, "TOTAL": 1274}),
    (2015, "ncrb_heat_2015.txt", {"AP_TG": 836, "TOTAL": 1908}),
    (2017, "ncrb_heat_2017.txt", {"AP_TG": 411, "TOTAL": 1127}),
    (2018, "ncrb_heat_2018.txt", {"AP_TG": 204, "TOTAL": 890}),
    (2019, "ncrb_heat_2019.txt", {"AP_TG": 284, "TOTAL": 1274}),
    (2021, "ncrb_heat_2021.txt", {"AP_TG": 65, "TOTAL": 374}),
])
def test_heat_golden(year, fixture, expect):
    df = ncrb.heat_deaths(year, lines=L(fixture))
    records.validate(df)
    for unit, v in expect.items():
        assert val(df, unit) == v


def test_farmer_totals_and_definition_break():
    d13 = ncrb.farmer_suicides(2013, lines=L("ncrb_farm_2013.txt"))
    d14 = ncrb.farmer_suicides(2014, lines=L("ncrb_farm_2014.txt"))
    assert val(d13, "TOTAL", "farmers") == 11_772 and val(d14, "TOTAL", "farmers") == 5_650
    assert "ag_labourers" in set(d14.variable) and "ag_labourers" not in set(d13.variable)


# ---------------------------------------------------------------- heat details

def test_heat_rows_carry_labels_years_and_only_the_all_india_total():
    df = ncrb.heat_deaths(2003, lines=L("ncrb_heat_2003.txt"))
    assert set(df.year) == {2003} and set(df.variable) == {"heat_deaths"}
    assert set(df.source_id) == {"ncrb_2003"} and not df.provisional.any()
    assert sorted(df.raw_label) == ["ANDHRA PRADESH", "GUJARAT", "ORISSA", "TOTAL (ALL INDIA)"]
    assert val(df, "OD") == 98 and val(df, "TOTAL") == 807          # TOTAL (STATES) 789 not emitted


def test_heat_2015_andhra_pradesh_and_telangana_rows():
    df = ncrb.heat_deaths(2015, lines=L("ncrb_heat_2015.txt"))
    ap = df[df.unit_id == "AP_TG"].set_index("raw_label").value
    assert ap.to_dict() == {"ANDHRA PRADESH": 654, "TELANGANA": 182}


def test_heat_2019_pools_ap_and_telangana_and_keeps_both_rows():
    df = ncrb.heat_deaths(2019, lines=L("ncrb_heat_2019.txt"))
    ap = df[df.unit_id == "AP_TG"].set_index("raw_label").value
    assert ap.to_dict() == {"ANDHRA PRADESH": 128, "TELANGANA": 156}
    assert val(df, "DNH_DD") == 0 and len(df[df.unit_id == "DNH_DD"]) == 2


def test_heat_2020_split_merged_ut_label_and_short_row_warning():
    with pytest.warns(UserWarning, match=r"A & N ISLANDS.*8 of 12"):
        df = ncrb.heat_deaths(2020, lines=L("ncrb_heat_2020.txt"))
    assert val(df, "AP_TG") == 50 + 98 and val(df, "TOTAL") == 530
    dnh = df[df.unit_id == "DNH_DD"]
    assert dnh.raw_label.tolist() == ["D & N HAVELI AND DAMAN & DIU"] and dnh.value.tolist() == [0]
    assert val(df, "AN") == 0                     # the heat group is the last one: right-anchored


def test_short_row_outside_the_allow_list_raises():
    lines = [ln.replace("10 JAMMU & KASHMIR 0 0 0 0 0 0 0 0 0 0 0 0", "10 JAMMU & KASHMIR 0 0 0 0 0 0 0 0")
             for ln in L("ncrb_heat_2019.txt")]
    with pytest.raises(ValueError, match=r"JAMMU & KASHMIR.*8 values"):
        ncrb.heat_deaths(2019, lines=lines)
    with pytest.raises(ValueError, match=r"A & N ISLANDS.*8 values"):    # allow-listed for 2020 only
        ncrb.heat_deaths(2021, lines=L("ncrb_heat_2020.txt"))


def test_report_year_must_be_named_in_a_title():
    assert ncrb._names_year("TABLE - 2.11 Profile of Suicide Victims Categorised by Profession -- 2004 (St", 2004)
    assert ncrb._names_year("ACCIDENTAL DEATHS AND SUICIDES IN INDIA 2010 National Crime", 2010)
    assert ncrb._names_year("Accidental Deaths & Suicides in India 2019", 2019)
    assert ncrb._names_year("Natural Causes and Sex During 2001 (State", 2001)
    assert ncrb._names_year("by Causes Attributable to Nature and Sex \u2013 2007 (State", 2007)
    assert ncrb._names_year("by Causes Attributable to Nature and Sex \ufffd 2008 (State", 2008)
    assert not ncrb._names_year("Incidence and Rate of Accidental Deaths during 1998 to 2008", 2009)
    assert not ncrb._names_year("Rs. 2009 crore; page 2009", 2009)


def test_missing_pdftotext_is_a_runtime_error(monkeypatch):
    ncrb._pdftotext.cache_clear()
    monkeypatch.setattr(ncrb.shutil, "which", lambda name: None)
    try:
        with pytest.raises(RuntimeError, match="pdftotext"):
            ncrb._pdftotext()
    finally:
        ncrb._pdftotext.cache_clear()


def test_missing_local_source_raises_dedicated_error(monkeypatch, tmp_path):
    monkeypatch.setitem(ncrb.SOURCES, "ncrb_2018", {"url": f"file:{tmp_path / 'ADSI_2018.pdf'}", "rank": 2})
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path / "raw")     # no cached copy to fall back on
    with pytest.raises(fetch.LocalSourceMissing):
        ncrb._source_file(2018, "heat")


def test_unresolved_labelled_row_raises():
    lines = L("ncrb_heat_2010.txt")
    lines.insert(lines.index("UNION TERRITORIES:"), "21 NARNIA 1 0 1 0.1 2 0 2 0.2")
    with pytest.raises(ValueError, match="NARNIA"):
        ncrb.heat_deaths(2010, lines=lines)


def test_component_mismatch_raises():
    lines = [ln.replace("158 39 197", "158 39 198") for ln in L("ncrb_heat_2010.txt")]
    with pytest.raises(ValueError, match="ANDHRA PRADESH"):
        ncrb.heat_deaths(2010, lines=lines)


def test_missing_table_raises():
    with pytest.raises(ValueError, match="heat_deaths 2010"):
        ncrb.heat_deaths(2010, lines=L("ncrb_heat_2015.txt"))


def test_dash_is_nil():
    lines = [ln.replace("20 ODISHA 2 2 4 0.3 91 39 130 8.3", "20 ODISHA 2 2 4 0.3 - - - -")
             for ln in L("ncrb_heat_2010.txt")]
    df = ncrb.heat_deaths(2010, lines=lines)
    assert val(df, "OD") == 0


# ---------------------------------------------------------------- farmers details

def test_farmers_2013_is_farming_sector_and_names_the_category():
    df = ncrb.farmer_suicides(2013, lines=L("ncrb_farm_2013.txt"))
    assert set(df.variable) == {"farmers", "farming_sector"}
    assert val(df, "AP_TG", "farmers") == 2014 and val(df, "AP_TG", "farming_sector") == 2014
    assert val(df, "DNH_DD", "farmers") == 15
    assert ncrb.FARMER_CATEGORY[2013] == "Self–employed (farming / agriculture)"


# ---------------------------------------------------------------- data.gov.in OGD 2001-2012

def test_ogd_farmers_2001_2003():
    df = ncrb.ogd_farmers(path=FIX / "ncrb_ogd0112.csv")
    records.validate(df)
    assert set(df.year) == {2001, 2002, 2003} and set(df.source_id) == {"farm_ogd0112"}
    assert set(df.variable) == {"farmers", "farming_sector"}
    f = df[df.variable == "farmers"]
    assert val(f[f.year == 2001], "AP_TG", "farmers") == 1509
    assert val(f[f.year == 2002], "OD", "farmers") == 345
    assert f[f.unit_id == "TOTAL"].set_index("year").value.to_dict() == {2001: 16415, 2002: 17971, 2003: 17164}
    assert "TOTAL (STATES)" not in set(df.raw_label)
    s = df[df.variable == "farming_sector"].set_index(["raw_label", "year"]).value
    assert s.equals(f.set_index(["raw_label", "year"]).value)


def test_ogd_west_bengal_2012_not_reported_is_nan():
    df = ncrb.ogd_farmers(years=(2012,), path=FIX / "ncrb_ogd0112.csv")
    wb = df[(df.unit_id == "WB") & (df.variable == "farmers")]
    assert wb.value.isna().all() and len(wb) == 1
    assert val(df, "AP_TG", "farmers") == 2572 and val(df, "TOTAL", "farmers") == 13754


def test_ogd_male_female_must_add_up(tmp_path):
    text = (FIX / "ncrb_ogd0112.csv").read_text(encoding="utf-8").replace(",1331,", ",1332,", 1)
    (tmp_path / "x.csv").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="ANDHRA PRADESH"):
        ncrb.ogd_farmers(path=tmp_path / "x.csv")


OGD_FIX = FIX / "ncrb_ogd0112.csv"


def _reference_from_fixture(monkeypatch, calls=None):
    """Stand-in for the NCRB 2004-2012 parses: the (valid) fixture's 2006 and 2012 rows."""
    monkeypatch.setattr(ncrb, "VALIDATION_YEARS", (2006, 2012))
    monkeypatch.setattr(ncrb, "_VALIDATED", {})
    ref = ncrb.ogd_farmers(years=(2006, 2012), path=OGD_FIX).assign(source_id="ncrb_ref")

    def reference(years):
        if calls is not None:
            calls.append(tuple(years))
        return ref
    monkeypatch.setattr(ncrb, "_ncrb_reference", reference)


def _tampered(tmp_path, old, new):
    text = OGD_FIX.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "ogd.csv"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_ogd_emit_validated_fixture_passes_and_validation_is_cached(monkeypatch):
    calls = []
    _reference_from_fixture(monkeypatch, calls)
    df = ncrb.ogd_emit(path=OGD_FIX)
    assert set(df.year) == {2001, 2002, 2003}
    assert df[(df.unit_id == "TOTAL") & (df.variable == "farmers")].value.tolist() == [16415, 17971, 17164]
    ncrb.ogd_emit(years=(2002,), path=OGD_FIX)
    assert calls == [(2006, 2012)]                          # validated once per process


def test_ogd_emit_raises_when_a_validation_year_differs_from_ncrb(monkeypatch, tmp_path):
    _reference_from_fixture(monkeypatch)
    bad = _tampered(tmp_path, "MAHARASHTRA,2006,Farming/Agriculture Activity,7,942,1589,1032,541,4111,",
                    "MAHARASHTRA,2006,Farming/Agriculture Activity,7,942,1589,1032,541,4112,")
    bad.write_text(bad.read_text(encoding="utf-8").replace(",342,4453", ",342,4454", 1), encoding="utf-8")
    with pytest.raises(ValueError, match=r"does not reproduce NCRB.*MH.*2006"):
        ncrb.ogd_emit(path=bad)


def test_ogd_emit_raises_when_units_do_not_add_up_to_all_india(monkeypatch, tmp_path):
    _reference_from_fixture(monkeypatch)
    bad = _tampered(tmp_path, "ANDHRA PRADESH,2001,Farming/Agriculture Activity,16,382,480,",
                    "ANDHRA PRADESH,2001,Farming/Agriculture Activity,17,382,480,")
    text = bad.read_text(encoding="utf-8").replace(",79,1331,", ",79,1332,", 1).replace(",178,1509", ",178,1510", 1)
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=r"2001.*sum of units"):
        ncrb.ogd_emit(path=bad)


def test_all_farmers_skips_ogd_when_validation_sources_are_unavailable(monkeypatch):
    base = ncrb.farmer_suicides(2013, lines=L("ncrb_farm_2013.txt"))
    monkeypatch.setattr(ncrb, "farmer_suicides", lambda year, lines=None: base.assign(year=year))
    monkeypatch.setattr(ncrb, "_VALIDATED", {})

    def unavailable(years):
        raise fetch.LocalSourceMissing("ncrb_2009: local source not found")
    monkeypatch.setattr(ncrb, "_ncrb_reference", unavailable)
    with pytest.warns(UserWarning, match="1997-2000"), pytest.warns(UserWarning, match="farm_ogd0112"):
        df = ncrb.all_farmers()
    assert "farm_ogd0112" in df.attrs["missing_sources"]
    assert df.attrs["missing_reasons"]["farm_ogd0112"].startswith("validation sources unavailable")
    assert set(df.year) == set(range(2004, 2024))
    with pytest.raises(fetch.LocalSourceMissing):
        ncrb.ogd_emit(path=OGD_FIX)


def test_farmer_suicides_2001_2003_dispatch_to_ogd(monkeypatch):
    seen = []
    monkeypatch.setattr(ncrb, "ogd_emit", lambda years=None, path=None: seen.append(tuple(years)) or "df")
    assert ncrb.farmer_suicides(2002) == "df" and seen == [(2002,)]
    with pytest.raises(ValueError, match="lines"):
        ncrb.farmer_suicides(2002, lines=["x"])
    with pytest.raises(ValueError, match="1999"):
        ncrb.farmer_suicides(1999)


def test_farmers_2014_sector_is_sum_of_farmers_and_labourers():
    df = ncrb.farmer_suicides(2014, lines=L("ncrb_farm_2014.txt"))
    assert val(df, "AP_TG", "farmers") == 160 + 898
    assert val(df, "AP_TG", "ag_labourers") == 472 + 449
    assert val(df, "TOTAL", "ag_labourers") == 6_710 and val(df, "TOTAL", "farming_sector") == 12_360
    assert val(df, "MH", "farming_sector") == 4_004


def test_farmers_2015_farming_sector_table():
    df = ncrb.farmer_suicides(2015, lines=L("ncrb_farm_2015.txt"))
    assert (val(df, "TOTAL", "farmers"), val(df, "TOTAL", "ag_labourers")) == (8_007, 4_595)
    assert val(df, "TOTAL", "farming_sector") == 12_602
    assert val(df, "AP_TG", "farmers") == 516 + 1358            # 2015 columns, not 2014's
    assert set(df.year) == {2015}


def test_farmers_2022_two_pages_and_zero_reporting_kept():
    df = ncrb.farmer_suicides(2022, lines=L("ncrb_farm_2022.txt"))
    assert val(df, "TOTAL", "farmers") == 5_207 and val(df, "TOTAL", "ag_labourers") == 6_083
    assert val(df, "TOTAL", "farming_sector") == 11_290
    tg = df[(df.raw_label == "TELANGANA") & (df.variable == "ag_labourers")]
    assert tg.value.tolist() == [0]                              # printed 0 kept as 0 (Task 9 reviews)
    assert val(df, "DNH_DD", "farmers") == 9 and val(df, "DNH_DD", "ag_labourers") == 11


def test_farmer_sector_mismatch_with_printed_total_raises():
    lines = [ln.replace("798 119 0 917", "798 119 0 918").replace("0 917 361", "0 918 361")
             for ln in L("ncrb_farm_2022.txt")]
    with pytest.raises(ValueError, match="ANDHRA PRADESH"):
        ncrb.farmer_suicides(2022, lines=lines)


def test_out_of_range_years_raise():
    with pytest.raises(ValueError):
        ncrb.heat_deaths(2000, lines=[])
    with pytest.raises(ValueError):
        ncrb.farmer_suicides(2024, lines=[])


# ---------------------------------------------------------------- PIB cross-check source

def test_pib_2017_2021_golden():
    df = ncrb.pib_heat_2017_2021(lines=L("ncrb_pib1721.txt"))
    records.validate(df)
    assert set(df.source_id) == {"heat_pib1721"}
    ap = df[df.unit_id == "AP_TG"].groupby("year").value.sum().to_dict()
    assert ap == {2017: 411, 2018: 204, 2019: 284, 2020: 148, 2021: 65}
    tot = df[df.unit_id == "TOTAL"].set_index("year").value.to_dict()
    assert tot == {2017: 1127, 2018: 890, 2019: 1274, 2020: 530, 2021: 374}
    assert df[(df.raw_label == "Ladakh") & (df.year == 2017)].value.tolist() == [0]   # "-" = nil
    assert set(df[df.unit_id == "DNH_DD"].raw_label) == {"D&N Haveli and Daman&Diu"}


# ---------------------------------------------------------------- sources / all_*

def test_sources_cover_years():
    assert {f"ncrb_{y}" for y in range(2001, 2025)} | {"heat_pib1721", "farm_ogd0112"} == set(ncrb.SOURCES)
    assert ncrb.SOURCES["heat_pib1721"]["rank"] < ncrb.SOURCES["ncrb_2019"]["rank"]
    assert ncrb.SOURCES["farm_ogd0112"]["rank"] < ncrb.SOURCES["ncrb_2010"]["rank"]
    assert set(ncrb.FARMER_MISSING) == set(range(1997, 2001))
    assert set(ncrb.FARMER_CATEGORY) == set(range(2001, 2024))
    assert all("not available on the NCRB website with a text layer" in r for r in ncrb.FARMER_MISSING.values())


def test_sources_csv_lists_every_source():
    csv = pd.read_csv(Path(ncrb.__file__).resolve().parents[1] / "reference" / "outcomes_sources.csv")
    assert set(ncrb.SOURCES) <= set(csv.source_id)


def test_all_heat_skips_unavailable_sources(monkeypatch):
    base = ncrb.heat_deaths(2003, lines=L("ncrb_heat_2003.txt"))
    pib = ncrb.pib_heat_2017_2021(lines=L("ncrb_pib1721.txt"))

    def fake(year, lines=None):
        if year == 2002:
            raise fetch.FetchError("HTTP 404")
        return base.assign(year=year, source_id=f"ncrb_{year}")

    monkeypatch.setattr(ncrb, "heat_deaths", fake)
    monkeypatch.setattr(ncrb, "pib_heat_2017_2021", lambda lines=None: pib)
    with pytest.warns(UserWarning, match="ncrb_2002"):
        df = ncrb.all_heat()
    assert df.attrs["missing_sources"] == ["ncrb_2002"]
    assert set(df.year) == set(range(2001, 2025)) - {2002}
    assert "heat_pib1721" in set(df.source_id)


def test_all_heat_skips_missing_local_copy_but_not_other_file_errors(monkeypatch):
    base = ncrb.heat_deaths(2003, lines=L("ncrb_heat_2003.txt"))

    def fake(year, lines=None):
        if year == 2024:
            raise fetch.LocalSourceMissing("ncrb_2024: local source ADSI_2024.pdf not found")
        return base.assign(year=year, source_id=f"ncrb_{year}")

    monkeypatch.setattr(ncrb, "heat_deaths", fake)
    monkeypatch.setattr(ncrb, "pib_heat_2017_2021", lambda lines=None: base.iloc[:0])
    with pytest.warns(UserWarning, match="ncrb_2024"):
        assert ncrb.all_heat().attrs["missing_sources"] == ["ncrb_2024"]

    def broken(year, lines=None):
        raise FileNotFoundError("some other file")

    monkeypatch.setattr(ncrb, "heat_deaths", broken)
    with pytest.raises(FileNotFoundError):
        ncrb.all_heat()


def test_all_farmers_reports_years_without_a_state_table(monkeypatch):
    base = ncrb.farmer_suicides(2013, lines=L("ncrb_farm_2013.txt"))
    monkeypatch.setattr(ncrb, "farmer_suicides", lambda year, lines=None: base.assign(year=year))
    ogd = ncrb.ogd_farmers(path=OGD_FIX)
    monkeypatch.setattr(ncrb, "_require_validated", lambda path=None: None)
    monkeypatch.setattr(ncrb, "ogd_emit", lambda years=None, path=None: ogd)
    with pytest.warns(UserWarning, match=r"1997-2000"):
        df = ncrb.all_farmers()
    assert df.attrs["missing_sources"] == [f"ncrb_{y}" for y in range(1997, 2001)]
    assert set(df.attrs["missing_reasons"]) == set(df.attrs["missing_sources"])
    assert set(df.year) == set(range(2001, 2024))


# ---------------------------------------------------------------- network

@pytest.mark.network
def test_year_index_lists_the_source_files():
    for y, url in ncrb.FULL_REPORTS.items():
        assert url in ncrb.year_index(y), y
    idx = ncrb.year_index(2005)
    assert ncrb.SOURCES["ncrb_2005"]["url"] in idx and ncrb.FARMER_URLS[2005] in idx


@pytest.mark.network
def test_per_table_urls_are_found_by_title():
    for y, url in ncrb.HEAT_URLS.items():
        assert ncrb.find_by_title(y, r"Natural Causes (&|and) Sex") == url, y
    for y, url in ncrb.FARMER_URLS.items():
        assert ncrb.find_by_title(y, r"Profession During \d{4} \(State") == url, y


def test_index_entries_parse_listing_tables():
    page = ('<html><table class="table table-bordered c-table"><tr><td class="w-70"> '
            '<a target="_blank" class="link" href="https://www.ncrb.gov.in/x/table-1.10_2003.pdf">'
            'Distribution of Accidental Deaths by Natural Causes &amp; Sex</a></td></tr></table>'
            '<a href="https://www.ncrb.gov.in/uploads/files/AIBEResult2026.pdf">site link</a></html>')
    assert ncrb.index_entries(page) == [("https://www.ncrb.gov.in/x/table-1.10_2003.pdf",
                                         "Distribution of Accidental Deaths by Natural Causes & Sex")]


@pytest.mark.network
def test_missing_farmer_years_evidence_is_cached():
    for y in range(1997, 2001):                  # chapter-2 PDF is a scan: no text layer
        ev = ncrb.missing_evidence(y)
        assert ev["chapter2_pdf"] and ev["text_chars"] == 0, (y, ev)
    assert ncrb.missing_evidence(2002)["chapter2_pdf"] is None
    for y in (2001, 2003):                       # text, but no profession-by-state table
        ev = ncrb.missing_evidence(y)
        assert ev["text_chars"] > 10_000 and not ev["has_state_profession_table"], (y, ev)


@pytest.mark.network
def test_ogd_reproduces_ncrb_2004_2012():
    mism = ncrb.ogd_validation()
    assert mism.empty, mism
