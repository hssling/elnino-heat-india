import math
from pathlib import Path

import pytest

from pipeline.outcomes import fetch, malaria, records

FIX = Path(__file__).parent / "fixtures"


def lines(name):
    return (FIX / name).read_text(encoding="utf-8").splitlines()


# mal_sit_0509 / mal_sit_1317 exist only as Internet Archive captures, which refused this
# machine (HTTP 429 "suspected bot traffic"); controller ruling P4: proceed without them.
# Their fixtures are cut from the downloaded PDFs if a fetch ever succeeds; until then skipped.
_PENDING = {n: not (FIX / n).exists() for n in ("malaria_mal_sit_0509.txt", "malaria_mal_sit_1317.txt")}


def pending(name):
    return pytest.mark.skipif(_PENDING[name], reason=f"{name} not yet cut: Internet Archive fetch refused")


def val(df, unit, year, var):
    s = df[(df.unit_id == unit) & (df.year == year) & (df.variable == var)].value
    return s.sum()


def vals(df, unit, year):
    return tuple(val(df, unit, year, v) for v in ("tested", "cases", "pf", "deaths"))


def test_situation_0206_golden():
    df = malaria.situation_2002_2006(lines=lines("malaria_mal_sit_0206.txt"))
    records.validate(df)
    assert val(df, "AP_TG", 2002, "tested") == 8_718_569
    assert val(df, "AP_TG", 2002, "cases") == 38_053
    assert val(df, "AP_TG", 2002, "pf") == 21_416
    assert val(df, "AP_TG", 2002, "deaths") == 0
    assert df[df.year.isin([2005, 2006])].provisional.all()


def test_upto2011_golden():
    df = malaria.situation_upto2011(lines=lines("malaria_mal_upto2011.txt"))
    assert (val(df, "AS", 2009, "tested"), val(df, "AS", 2009, "cases"),
            val(df, "AS", 2009, "pf"), val(df, "AS", 2009, "deaths")) == (3_021_920, 91_413, 66_557, 63)
    assert (val(df, "OD", 2010, "cases"), val(df, "OD", 2010, "deaths")) == (357_320, 241)
    assert (val(df, "AP_TG", 2007, "cases"), val(df, "AP_TG", 2007, "pf")) == (27_803, 16_996)


def test_situation_1519_golden_and_pooling():
    df = malaria.situation_2015_2019(lines=lines("malaria_mal_sit_1519.txt"))
    assert (val(df, "BR", 2015, "tested"), val(df, "BR", 2015, "cases"),
            val(df, "BR", 2015, "pf"), val(df, "BR", 2015, "deaths")) == (217_632, 4_006, 1_286, 1)
    assert val(df, "AP_TG", 2015, "cases") == 25_042 + 10_951
    assert df[df.year == 2019].provisional.all()
    ap = df[(df.raw_label.str.upper().str.contains("ANDHRA")) & (df.year == 2015)]
    assert ap[ap.variable == "cases"].value.item() == 25_042 and ap[ap.variable == "pf"].value.item() == 18_709


@pending("malaria_mal_sit_1317.txt")
def test_situation_1317_matches_1519_for_ap_2015():
    df = malaria.situation_2013_2017(lines=lines("malaria_mal_sit_1317.txt"))
    ap = df[(df.raw_label.str.upper().str.contains("ANDHRA")) & (df.year == 2015)]
    assert ap[ap.variable == "cases"].value.item() == 25_042 and ap[ap.variable == "pf"].value.item() == 18_709


@pytest.mark.filterwarnings("ignore:mal_ar_2014 Gujarat. E-notation BSE:UserWarning")
def test_annual_report_2014_state_total_an():
    df = malaria.annual_report(2014, lines=lines("malaria_mal_ar_2014.txt"))
    assert (val(df, "AN", 2014, "tested"), val(df, "AN", 2014, "cases"), val(df, "AN", 2014, "pf")) == (74_905, 557, 109)


# ---- further checks on fixtures cut from the real documents

def test_situation_0206_pooling_and_totals():
    df = malaria.situation_2002_2006(lines=lines("malaria_mal_sit_0206.txt"))
    assert val(df, "DNH_DD", 2002, "cases") == 493 + 173              # D & N Haveli + Daman & Diu
    assert vals(df, "UK", 2004) == (330_317, 1_255, 39, 0)            # "Uttaranchal"
    assert vals(df, "PY", 2006) == (143_940, 37, 0, 0)                # "Pondicherry"
    assert vals(df, "AN", 2002) == (202_542, 865, 158, 1)             # "A.N.Islands"
    assert val(df, "TOTAL", 2002, "cases") == 1_841_229
    assert not df[df.year < 2005].provisional.any()


@pending("malaria_mal_sit_0509.txt")
def test_situation_0509_label_variants_and_provisional():
    # Structural checks only: the document has never been obtained, so no golden value may be
    # asserted until the fixture is cut from the real PDF (2005-06 may legitimately differ from
    # mal_sit_0206, which printed provisional/partial figures). Add goldens from the PDF text then.
    df = malaria.situation_2005_2009(lines=lines("malaria_mal_sit_0509.txt"))
    assert {"AP_TG", "AN", "TOTAL"} <= set(df.unit_id)
    assert df[df.year.isin([2008, 2009])].provisional.all()
    assert not df[df.year < 2008].provisional.any()


def test_upto2011_drops_partial_2011_and_flags_2010():
    df = malaria.situation_upto2011(lines=lines("malaria_mal_upto2011.txt"))
    assert sorted(df.year.unique()) == [2007, 2008, 2009, 2010]
    assert df[df.year == 2010].provisional.all() and not df[df.year < 2010].provisional.any()
    assert vals(df, "AN", 2008) == (165_631, 4_688, 3_173, 0)        # "A.N.Islands"
    assert val(df, "DNH_DD", 2009, "cases") == 97                     # Daman & Diu row only in fixture
    assert val(df, "TOTAL", 2009, "cases") == 1_563_574


def test_1519_west_bengal_2017_provisional_and_clean_labels():
    df = malaria.situation_2015_2019(lines=lines("malaria_mal_sit_1519.txt"))
    wb = df[(df.unit_id == "WB") & (df.year == 2017)]
    assert wb.provisional.all() and val(df, "WB", 2017, "cases") == 31_265
    assert not df[(df.unit_id != "WB") & (df.year == 2017)].provisional.any()
    assert val(df, "TOTAL", 2015, "cases") == 1_169_261
    assert {"Andhra Pradesh", "Telangana", "A.N.Islands", "All India Total"} <= set(df.raw_label)
    assert not df.raw_label.str.match(r"^\d").any()                   # "1Andhra Pradesh" -> "Andhra Pradesh"


def test_from2022_unwraps_dnh_drops_partial_year():
    df = malaria.situation_from2022(lines=lines("malaria_mal_sit_2022.txt"))
    assert sorted(df.year.unique()) == [2022, 2023, 2024, 2025]
    assert vals(df, "AN", 2022) == (31_737, 50, 20, 0)
    assert vals(df, "DNH_DD", 2023) == (146_190, 128, 36, 1)
    assert set(df[df.unit_id == "DNH_DD"].raw_label) == {"The Dadra And Nagar Haveli And Daman And Diu"}
    assert vals(df, "TOTAL", 2024) == (181_653_330, 255_500, 153_472, 86)
    assert not df.provisional.any()


def test_annual_report_2014_bse_from_districts_short_row_and_pooling():
    with pytest.warns(UserWarning, match="Gujarat: E-notation BSE 1.3E\\+07 replaced by the sum of districts"):
        df = malaria.annual_report(2014, lines=lines("malaria_mal_ar_2014.txt"))
    gj = df[(df.unit_id == "GJ") & (df.variable == "tested")]
    assert gj.value.item() == 13_440_364 and gj.raw_label.item() == "Gujarat [BSE=sum of districts]"
    assert vals(df, "GJ", 2014)[1:] == (41_608, 6_253, 16)
    assert vals(df, "LD", 2014) == (132, 0, 0, 0)                     # PF% cell blank
    assert vals(df, "AP_TG", 2014) == (9_853_526 + 3_600_200, 21_077 + 5_189, 15_511 + 4_602, 0)
    assert val(df, "AN", 2014, "deaths") == 0


def test_annual_report_2014_bse_not_recovered_when_checks_fail():
    src = [ln for ln in lines("malaria_mal_ar_2014.txt") if not ln.startswith("Ahmadabad Mc#")]
    with pytest.warns(UserWarning, match="Gujarat: E-notation BSE 1.3E\\+07 read as NaN"):
        df = malaria.annual_report(2014, lines=src)
    gj = df[(df.unit_id == "GJ") & (df.variable == "tested")]
    assert math.isnan(gj.value.item()) and gj.raw_label.item() == "Gujarat"


def test_annual_report_2017_2018_deaths_only():
    df = malaria.annual_report(2017, lines=lines("malaria_mal_ar_2017.txt"))
    assert set(df.variable) == {"deaths"}
    d = df.set_index("unit_id").value
    assert (d["AP_TG"], d["CG"], d["MP"], d["WB"], d["TOTAL"]) == (0, 2 + 79, 5, 29, 11 + 183)
    assert df[df.unit_id == "WB"].provisional.all() and not df[df.unit_id != "WB"].provisional.any()
    with pytest.warns(UserWarning, match="Chhattisgarh: stray leading '0' cell dropped"):
        df = malaria.annual_report(2018, lines=lines("malaria_mal_ar_2018.txt"))
    d = df.set_index("unit_id").value                                 # heading "Andhra Padesh"
    assert (d["AP_TG"], d["WB"], d["TOTAL"]) == (0, 2 + 6, 8 + 88) and not df.provisional.any()
    assert d["CG"] == 1 + 38                                          # "0 79.38 ... 1 38" (summary: 1 38)
    assert d["DL"] == 0                                               # district row == total row


def test_annual_report_2019_wrapped_and_split_totals():
    df = malaria.annual_report(2019, lines=lines("malaria_mal_ar_2019.txt"))
    assert vals(df, "AP_TG", 2019) == (6_502_654, 3_104, 1_990, 0)
    assert vals(df, "KA", 2019) == (11_297_885, 3_499, 566, 0)        # cells split over two lines
    assert vals(df, "NL", 2019) == (225_519, 20, 4, 0)                # values on the line above
    assert vals(df, "RJ", 2019) == (8_460_010, 3_421, 420, 1)         # heading "Rajsthan"
    assert vals(df, "TN", 2019) == (8_745_502, 2_088, 84, 0)          # "S t a t e T o t a l", values below
    assert vals(df, "JK", 2019) == (0, 0, 0, 0)                       # Ladakh page (all zero)


def test_annual_report_2020_incomplete_row_tested_confirmed_by_adjacent_line():
    with pytest.warns(UserWarning) as rec:
        df = malaria.annual_report(2020, lines=lines("malaria_mal_ar_2020.txt"))
    msgs = " | ".join(str(w.message) for w in rec)
    assert "Jharkhand: incomplete row (12 cells); species block re-anchored" in msgs
    assert "Jharkhand: tested 2708477 = sum of parts, confirmed by the adjacent line" in msgs
    assert "tested not verifiable" not in msgs
    assert vals(df, "AP_TG", 2020) == (5_341_770, 2_027, 1_767, 0)
    assert vals(df, "JH", 2020) == (2_708_477, 16_653, 11_961, 8)    # wrapped line "2708477 2708477 71.82 ..."


def test_reanchored_tested_needs_adjacent_confirmation():
    jh = "40406 1702070 1006407 1702070 1006407 4692 11893 68 16653 16653 0 8".split()
    for adjacent in ((), [["2708478", "71.82"]]):                                  # none / no exact match
        with pytest.warns(UserWarning) as rec:
            got = malaria._parse_total(jh, malaria._FMT[2020], "x", strict=False, adjacent=adjacent)
        msgs = [str(w.message) for w in rec]
        assert any("re-anchored" in m for m in msgs) and any("tested not verifiable" in m for m in msgs)
        assert math.isnan(got["tested"]) and got["cases"] == 16_653


def test_reanchored_row_missing_pop_keeps_verified_tested():
    full = ("50893 4346744 1027339 4333003 1008767 5374083 5341770 260 1757 10 2027 "
            "87.17 10.50 0.04 0.04 0.03 0.03 2027 0 0").split()          # AP 2020 state total
    with pytest.warns(UserWarning, match="re-anchored by its sum at cell 6"):
        got = malaria._parse_total(full[1:], malaria._FMT[2020], "synthetic", strict=False)
    assert (got["tested"], got["cases"], got["pf"], got["deaths"]) == (5_341_770, 2_027, 1_767, 0)
    garbled = full[1:3] + ["999"] + full[4:]                          # BSE no longer adds up
    with pytest.warns(UserWarning) as rec:
        got = malaria._parse_total(garbled, malaria._FMT[2020], "synthetic", strict=False)
    msgs = [str(w.message) for w in rec]
    assert any("re-anchored" in m for m in msgs) and any("tested not verifiable" in m for m in msgs)
    assert math.isnan(got["tested"]) and got["cases"] == 2_027


def test_annual_report_2021_total_block_and_dnh():
    df = malaria.annual_report(2021, lines=lines("malaria_mal_ar_2021.txt"))
    assert vals(df, "AP_TG", 2021) == (7_336_198, 1_315, 1_081, 0)
    assert vals(df, "DNH_DD", 2021) == (124_972, 54, 5, 0)


def test_annual_report_2022_labelled_totals():
    df = malaria.annual_report(2022, lines=lines("malaria_mal_ar_2022.txt"))
    assert vals(df, "AP_TG", 2022) == (8_653_048, 2_022, 1_457, 0)    # "Andhra Pra. Total"
    assert vals(df, "DNH_DD", 2022) == (131_198, 111, 16, 0)          # "DNH &DD Total"
    assert vals(df, "TOTAL", 2022) == (152_049_892, 176_522, 101_068, 83)


def test_annual_report_2023_glued_cells_and_duplicate_summary():
    with pytest.warns(UserWarning) as rec:
        df = malaria.annual_report(2023, lines=lines("malaria_mal_ar_2023.txt"))
    msgs = " | ".join(str(w.message) for w in rec)
    for frag in ("Mizoram: incomplete row", "West Bengal: incomplete row", "All States: incomplete row",
                 "All States: deaths cells ['227564', '182'] unreadable"):
        assert frag in msgs
    assert vals(df, "CG", 2023) == (6_891_223, 31_706, 28_167, 15)    # deaths printed "015"
    assert vals(df, "MZ", 2023) == (367_855, 18_077, 11_628, 13)      # "29.014.2" and "013"
    assert vals(df, "WB", 2023) == (12_870_741, 26_493, 3_565, 2)     # "245511460" glued
    assert vals(df, "AP_TG", 2023) == (10_294_202, 5_268, 4_437, 0)   # printed twice, counted once
    tot = df[(df.unit_id == "TOTAL") & (df.year == 2023)].set_index("variable").value
    assert tot["cases"] == 227_564 and tot["tested"] == 164_738_643 and tot.isna()["deaths"]


def test_annual_report_2024_grand_total_and_garbled_row():
    with pytest.warns(UserWarning) as rec:
        df = malaria.annual_report(2024, lines=lines("malaria_mal_ar_2024.txt"))
    msgs = " | ".join(str(w.message) for w in rec)
    assert "Grand: incomplete row (36 cells)" in msgs
    assert "Grand: deaths cells ['235243', '383'] unreadable" in msgs
    assert vals(df, "AP_TG", 2024) == (12_364_281, 7_866, 6_201, 3)
    assert vals(df, "CG", 2024) == (7_835_708, 31_373, 27_300, 18)    # deaths printed "018"
    assert vals(df, "AN", 2024) == (47_413, 96, 46, 0)
    assert "DNH_DD" not in set(df.unit_id)                            # garbled label: not guessed
    tot = df[(df.unit_id == "TOTAL") & (df.year == 2024)].set_index("variable").value
    assert tot["cases"] == 255_500 and tot["tested"] == 181_653_330 and tot.isna()["deaths"]


def test_annual_report_2025_state_summary_table():
    df = malaria.annual_report(2025, lines=lines("malaria_mal_ar_2025.txt"))
    assert vals(df, "AN", 2025) == (55_701, 48, 25, 0)
    assert vals(df, "AP_TG", 2025) == (12_898_436, 7_878, 6_356, 8)
    assert vals(df, "DNH_DD", 2025) == (130_760, 212, 48, 0)
    assert vals(df, "TOTAL", 2025) == (196_524_931, 233_917, 135_783, 76)
    assert set(df.unit_id) == {"AN", "AP_TG", "AR", "AS", "RJ", "DNH_DD", "TR", "TOTAL"}


def test_all_records_skips_unavailable_sources(monkeypatch):
    fixtures = {p.stem.replace("malaria_", ""): p for p in FIX.glob("malaria_*.txt")}

    def fake_source_path(sid):
        if sid == "mal_sit_1317":
            raise fetch.FetchError("HTTP 429")
        return Path(sid)

    def fake_lines(path):
        return lines(fixtures[path.name].name)    # KeyError for sources without a fixture

    monkeypatch.setattr(malaria, "source_path", fake_source_path)
    monkeypatch.setattr(malaria, "_pdf_lines", fake_lines)
    monkeypatch.setattr(malaria, "_SITUATION", {k: v for k, v in malaria._SITUATION.items()
                                                if k in ("mal_sit_1317", "mal_sit_0206", "mal_sit_1519")})
    monkeypatch.setattr(malaria, "annual_report", lambda y: malaria.records.make([]))
    with pytest.warns(UserWarning, match="mal_sit_1317: raw file unavailable; skipped"):
        df = malaria.all_records()
    assert df.attrs["missing_sources"] == ["mal_sit_1317"]
    assert set(df.source_id) == {"mal_sit_0206", "mal_sit_1519"}


def test_source_path_uses_unquoted_filename(monkeypatch):
    seen = {}

    def fake_get(source_id, url, filename=None, kind=None):
        seen[url] = filename
        return Path(filename)

    monkeypatch.setattr(malaria.fetch, "get", fake_get)
    assert malaria.source_path("mal_sit_0206") == Path("Malaria Situation.pdf")


def test_sources_table_covers_all_sources():
    assert {"mal_sit_0206", "mal_sit_0509", "mal_upto2011", "mal_sit_1317", "mal_sit_1519",
            "mal_sit_2022"} | {f"mal_ar_{y}" for y in range(2010, 2026)} == set(malaria.SOURCES)
    assert malaria.SOURCES["mal_sit_2022"]["rank"] > malaria.SOURCES["mal_ar_2020"]["rank"] \
        > malaria.SOURCES["mal_sit_1519"]["rank"] > malaria.SOURCES["mal_sit_0206"]["rank"]


# ---- Ruling P17: partial-year columns carry the [partial_year] marker

def test_situation_0206_2006_is_partial_year():
    df = malaria.situation_2002_2006(lines=lines("malaria_mal_sit_0206.txt"))
    y06 = df[df.year == 2006]
    assert len(y06) and y06.raw_label.map(records.is_partial).all() and y06.provisional.all()
    assert not df[df.year < 2006].raw_label.map(records.is_partial).any()        # 2005* provisional only
    assert one_label(df, "AP_TG", 2006) == "Andhra Pradesh [partial_year]"
    assert val(df, "TOTAL", 2006, "cases") == 1_047_977                          # value unchanged


def test_situation_partial_year_footnote_must_be_present():
    body = [ln for ln in lines("malaria_mal_sit_0206.txt") if "Report received till" not in ln]
    with pytest.raises(ValueError, match="partial-year footnote"):
        malaria.situation_2002_2006(lines=body)


def test_situation_1519_2019_upto_october_is_partial_year():
    df = malaria.situation_2015_2019(lines=lines("malaria_mal_sit_1519.txt"))
    assert df[df.year == 2019].raw_label.map(records.is_partial).all()
    assert not df[df.year < 2019].raw_label.map(records.is_partial).any()


def test_situation_other_tables_have_no_partial_year():
    for fn, name in ((malaria.situation_upto2011, "malaria_mal_upto2011.txt"),
                     (malaria.situation_from2022, "malaria_mal_sit_2022.txt")):
        assert not fn(lines=lines(name)).raw_label.map(records.is_partial).any()   # partial years dropped


def one_label(df, unit, year):
    s = df[(df.unit_id == unit) & (df.year == year) & (df.variable == "cases")].raw_label
    assert len(s) == 1, s
    return s.item()
