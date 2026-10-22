import math

import pandas as pd
import pytest

from pipeline.outcomes import assemble, gates, records


def R(unit, label, year, var, value, src, prov=False):
    return {"unit_id": unit, "raw_label": label, "year": year, "variable": var, "value": value,
            "source_id": src, "provisional": prov}


def REV(**kw):
    row = {"outcome": "malaria", "unit_id": "", "year": "", "variable": "", "source_id": "", "check": "",
           "disposition": "keep", "reason": "r", "evidence": "e"}
    row.update(kw)
    return row


# ---------------------------------------------------------------- brief tests (plan Step 1)

def test_choose_pools_within_source_then_prefers_final_high_rank():
    recs = records.make([
        R("AP_TG", "Andhra Pradesh", 2015, "cases", 25042, "s1"),
        R("AP_TG", "Telangana", 2015, "cases", 10951, "s1"),
        R("AP_TG", "Andhra Pradesh", 2015, "cases", 25042, "s2", prov=True),
        R("AP_TG", "Telangana", 2015, "cases", 10951, "s2", prov=True),
        R("OD", "Odisha", 2016, "cases", 100, "s1", prov=True),
        R("OD", "Odisha", 2016, "cases", 120, "s2", prov=True),
    ])
    out = assemble.choose(recs, ranks={"s1": 1, "s2": 2}).set_index(["unit_id", "year"])
    assert out.loc[("AP_TG", 2015), "value"] == 35993 and out.loc[("AP_TG", 2015), "source_id"] == "s1"
    assert out.loc[("OD", 2016), "value"] == 120 and bool(out.loc[("OD", 2016), "provisional"])


def test_missing_is_nan_not_zero_and_completeness_flags_it():
    panel = pd.DataFrame({"unit_id": ["OD", "OD"], "year": [2015, 2016], "cases": [100.0, math.nan]})
    res = gates.completeness(panel, years=[2015, 2016], units=["OD"], var="cases", reviewed=pd.DataFrame())
    assert not res.passed and "OD 2016" in res.detail
    rev = pd.DataFrame([{"outcome": "malaria", "unit_id": "OD", "year": 2016, "variable": "cases",
                         "source_id": "", "check": "completeness", "disposition": "non_reporting",
                         "reason": "r", "evidence": "e"}])
    assert gates.completeness(panel, years=[2015, 2016], units=["OD"], var="cases", reviewed=rev).passed


def test_cross_source_tolerances_and_review():
    recs = records.make([
        R("OD", "Odisha", 2010, "cases", 1000, "a"), R("OD", "Odisha", 2010, "cases", 1015, "b"),   # 1.5% ok
        R("GJ", "Gujarat", 2012, "cases", 1461, "a"), R("GJ", "Gujarat", 2012, "cases", 3067, "b"),  # disagree
        R("SK", "Sikkim", 2012, "cases", 3, "a"), R("SK", "Sikkim", 2012, "cases", 7, "b"),          # abs 4 ok
    ])
    res = gates.cross_source(recs, reviewed=pd.DataFrame())
    assert not res.passed and "GJ 2012 cases" in res.detail and "OD" not in res.detail and "SK" not in res.detail


def test_national_totals():
    recs = records.make([R("OD", "Odisha", 2010, "heat_deaths", 130, "n10"),
                         R("GJ", "Gujarat", 2010, "heat_deaths", 58, "n10"),
                         R("TOTAL", "Total (All India)", 2010, "heat_deaths", 188, "n10")])
    assert gates.national_totals(recs, reviewed=pd.DataFrame()).passed
    bad = recs.assign(value=[130, 58, 300])
    assert not gates.national_totals(bad, reviewed=pd.DataFrame()).passed


# ---------------------------------------------------------------- choose / pooling

def test_choose_nan_in_higher_rank_never_overrides_lower_rank_value():
    recs = records.make([R("GJ", "Gujarat", 2010, "tested", math.nan, "hi"),
                         R("GJ", "Gujarat", 2010, "tested", 9_000_000, "lo")])
    out = assemble.choose(recs, ranks={"lo": 1, "hi": 5}).iloc[0]
    assert out.value == 9_000_000 and out.source_id == "lo" and not out.provisional


def test_choose_final_beats_higher_rank_provisional():
    recs = records.make([R("OD", "Odisha", 2010, "cases", 357320, "late", prov=True),
                         R("OD", "Odisha", 2010, "cases", 395651, "early")])
    out = assemble.choose(recs, ranks={"early": 1, "late": 9}).iloc[0]
    assert out.value == 395651 and out.source_id == "early" and not out.provisional


def test_choose_all_nan_is_nan_not_zero():
    recs = records.make([R("LD", "Lakshadweep", 2012, "cases", math.nan, "a"),
                         R("LD", "Lakshadweep", 2012, "cases", math.nan, "b")])
    out = assemble.choose(recs, ranks={"a": 1, "b": 2}).iloc[0]
    assert math.isnan(out.value) and out.source_id == ""


def test_pool_sums_members_with_min_count_and_marks_partial():
    recs = records.make([R("AP_TG", "Andhra Pradesh", 2013, "cases", 910, "s"),
                         R("AP_TG", "Telangana", 2013, "cases", math.nan, "s"),
                         R("DNH_DD", "D & N Haveli", 2013, "cases", math.nan, "s"),
                         R("DNH_DD", "Daman & Diu", 2013, "cases", math.nan, "s"),
                         R("JK", "Jammu & Kashmir", 2013, "cases", 5, "s"),
                         R("JK", "Ladakh", 2013, "cases", 0, "s")])
    p = assemble.pool(recs).set_index("unit_id")
    assert p.loc["AP_TG", "value"] == 910 and bool(p.loc["AP_TG", "partial_pool"])
    assert math.isnan(p.loc["DNH_DD", "value"]) and not bool(p.loc["DNH_DD", "partial_pool"])
    assert p.loc["JK", "value"] == 5 and not bool(p.loc["JK", "partial_pool"])
    assert p.loc["AP_TG", "raw_label"] == "Andhra Pradesh + Telangana"


def test_choose_never_returns_total_rows():
    recs = records.make([R("TOTAL", "All India", 2010, "cases", 10, "a"), R("OD", "Odisha", 2010, "cases", 10, "a")])
    assert list(assemble.choose(recs, ranks={"a": 1}).unit_id) == ["OD"]


def test_ranks_from_csv_foodgrain_same_convention_dld_cross_check_only():
    r = assemble.ranks()
    assert r["foodgrain_rbi2023"] > r["foodgrain_rbi2019"] > r["foodgrain_dld"] == 0     # Ruling P12
    assert r["mal_sit_2022"] > r["mal_ar_2020"] > r["mal_sit_0206"]
    assert r["ncrb_2019"] > r["heat_pib1721"] and r["den_ncvbdc"] > r["den_opendengue"]
    assert not hasattr(assemble, "RANK_OVERRIDE")


def test_choose_rank0_source_is_cross_check_only():
    recs = records.make([R("PB", "Punjab", 2016, "foodgrain_t", 28_000_000, "foodgrain_rbi2019"),
                         R("PB", "Punjab", 2016, "foodgrain_t", 27_000_000, "foodgrain_dld"),
                         R("PB", "Punjab", 2017, "foodgrain_t", 29_000_000, "foodgrain_dld")])
    out = assemble.choose(recs, ranks=assemble.ranks()).set_index("year")
    assert out.loc[2016, "source_id"] == "foodgrain_rbi2019" and out.loc[2016, "n_sources"] == 1
    assert math.isnan(out.loc[2017, "value"]) and out.loc[2017, "source_id"] == ""


def test_foodgrain_scope_units_are_rbi_units():
    assert set(assemble.FOODGRAIN_EXCLUDED) == {"AN", "CH", "DNH_DD", "LD"}
    assert assemble.OUTCOMES["foodgrain"]["vars"] == ["foodgrain_t"]
    assert list(assemble.OUTCOMES["foodgrain"]["years"]) == list(range(1997, 2017))
    units = assemble.OUTCOMES["foodgrain"]["units"]
    assert len(units) == 30 and not set(units) & set(assemble.FOODGRAIN_EXCLUDED)
    recs = records.make([R(u, u, 2000, "foodgrain_t", 1.0, "foodgrain_rbi2019") for u in units])
    assemble.check_scope(recs, "foodgrain_rbi2019", units)
    with pytest.raises(ValueError, match="AN"):
        assemble.check_scope(pd.concat([recs, records.make([R("AN", "A&N", 2000, "foodgrain_t", 1.0,
                                                               "foodgrain_rbi2019")])]), "foodgrain_rbi2019", units)
    with pytest.raises(ValueError, match="PB"):
        assemble.check_scope(recs[recs.unit_id != "PB"], "foodgrain_rbi2019", units)


# ---------------------------------------------------------------- reviewed dispositions

def test_apply_reviewed_use_source_mask_and_non_reporting():
    recs = records.make([R("WB", "West Bengal", 2018, "deaths", 0, "den_nhp2021"),
                         R("WB", "West Bengal", 2018, "deaths", 86, "den_nhp2023"),
                         R("WB", "West Bengal", 2018, "cases", 5, "den_nhp2021"),
                         R("BR", "Bihar", 2018, "cases", 0, "den_nhp2021")])
    ranks = {"den_nhp2021": 9, "den_nhp2023": 1}           # rank alone would pick NHP 2021's 0
    rev = pd.DataFrame([
        REV(outcome="dengue", unit_id="WB", year=2018, variable="deaths", check="cross_source",
            disposition="use_source:den_nhp2023"),
        REV(outcome="dengue", unit_id="WB", year=2018, variable="cases", check="plausibility", disposition="mask"),
        REV(outcome="dengue", unit_id="BR", year=2018, variable="cases", check="completeness",
            disposition="non_reporting"),
        REV(outcome="malaria", unit_id="BR", year=2018, variable="cases", check="completeness",
            disposition="use_source:x"),      # other outcome: ignored
        REV(outcome="dengue", unit_id="LD", year=2008, variable="cases", check="completeness",
            disposition="non_reporting"),     # listed by no source
    ])
    ch = assemble.apply_reviewed(assemble.choose(recs, ranks), recs, rev, "dengue").set_index(["unit_id", "variable"])
    assert ch.loc[("WB", "deaths"), "value"] == 86 and ch.loc[("WB", "deaths"), "source_id"] == "den_nhp2023"
    assert math.isnan(ch.loc[("WB", "cases"), "value"]) and ch.loc[("WB", "cases"), "source_id"] == "masked"
    assert math.isnan(ch.loc[("BR", "cases"), "value"]) and ch.loc[("BR", "cases"), "source_id"] == "non_reporting"
    assert math.isnan(ch.loc[("LD", "cases"), "value"]) and ch.loc[("LD", "cases"), "source_id"] == "non_reporting"


def test_apply_reviewed_use_source_without_a_value_raises():
    recs = records.make([R("WB", "West Bengal", 2018, "deaths", 0, "a")])
    rev = pd.DataFrame([REV(outcome="dengue", unit_id="WB", year=2018, variable="deaths", check="cross_source",
                            disposition="use_source:b")])
    with pytest.raises(ValueError, match="use_source:b"):
        assemble.apply_reviewed(assemble.choose(recs, {"a": 1}), recs, rev, "dengue")


def test_read_reviewed_rejects_bad_rows(tmp_path):
    cols = "outcome,unit_id,year,variable,source_id,check,disposition,reason,evidence\n"
    p = tmp_path / "r.csv"
    p.write_text(cols + "malaria,OD,2010,cases,a|b,cross_source,use_source:a,specific reason,doc p.3\n",
                 encoding="utf-8")
    assert len(gates.read_reviewed(p)) == 1
    for bad in ("malaria,OD,2010,cases,,bogus,keep,r,e\n", "malaria,OD,2010,cases,,completeness,drop,r,e\n",
                "malaria,OD,2010,cases,,completeness,keep,,e\n", "malaria,OD,2010,cases,,completeness,keep,r,\n",
                "malaria,*,2010,cases,,completeness,keep,r,e\n"):
        p.write_text(cols + bad, encoding="utf-8")
        with pytest.raises(ValueError):
            gates.read_reviewed(p)


# ---------------------------------------------------------------- cross-source details

def test_cross_source_provisional_and_lower_bound_pairs_do_not_gate(tmp_path):
    recs = records.make([
        R("OD", "Odisha", 2010, "cases", 357320, "a", prov=True), R("OD", "Odisha", 2010, "cases", 395651, "b"),
        R("WB", "West Bengal", 2014, "foodgrain_t", 16_000_000, "foodgrain_rbi2019"),
        R("WB", "West Bengal", 2014, "foodgrain_t", 17_100_000, "foodgrain_dld"),
    ])
    out = tmp_path / "cross_source_report.csv"
    res = gates.cross_source(recs, reviewed=pd.DataFrame(), report_path=out)
    assert res.passed
    rep = pd.read_csv(out).set_index("unit_id")
    assert bool(rep.loc["OD", "provisional_pair"]) and not bool(rep.loc["OD", "lower_bound_pair"])
    assert bool(rep.loc["WB", "lower_bound_pair"]) and not bool(rep.loc["WB", "gating"])


def test_cross_source_reviewed_pair_passes_and_partial_pool_reported(tmp_path):
    recs = records.make([
        R("GJ", "Gujarat", 2012, "cases", 1461, "a"), R("GJ", "Gujarat", 2012, "cases", 3067, "b"),
        R("AP_TG", "Andhra Pradesh", 2015, "cases", 25042, "a"), R("AP_TG", "Telangana", 2015, "cases", math.nan, "a"),
        R("AP_TG", "Andhra Pradesh", 2015, "cases", 25042, "b"), R("AP_TG", "Telangana", 2015, "cases", 10951, "b"),
    ])
    rev = pd.DataFrame([REV(unit_id="GJ", year=2012, variable="cases", source_id="a|b", check="cross_source",
                            disposition="use_source:b")])
    out = tmp_path / "x.csv"
    res = gates.cross_source(recs, reviewed=rev, report_path=out)
    assert not res.passed and "AP_TG 2015 cases" in res.detail and "GJ 2012" not in res.detail.split("unreviewed")[-1]
    rep = pd.read_csv(out).set_index("unit_id")
    assert bool(rep.loc["AP_TG", "partial_pool"]) and rep.loc["GJ", "reviewed"] == "use_source:b"
    rev2 = pd.concat([rev, pd.DataFrame([REV(unit_id="AP_TG", year=2015, variable="cases", source_id="b|a",
                                             check="cross_source", disposition="use_source:b")])])
    assert gates.cross_source(recs, reviewed=rev2).passed


def test_cross_source_reviewed_filtered_by_outcome():
    recs = records.make([R("GJ", "Gujarat", 2012, "cases", 1461, "a"), R("GJ", "Gujarat", 2012, "cases", 3067, "b")])
    rev = pd.DataFrame([REV(outcome="dengue", unit_id="GJ", year=2012, variable="cases", source_id="a|b",
                            check="cross_source")])
    assert not gates.cross_source(recs, reviewed=rev, outcome="malaria").passed
    assert gates.cross_source(recs, reviewed=rev, outcome="dengue").passed


def test_cross_source_reviewed_row_must_name_the_pair():
    recs = records.make([R("GJ", "Gujarat", 2012, "cases", 1461, "a"), R("GJ", "Gujarat", 2012, "cases", 3067, "b"),
                         R("GJ", "Gujarat", 2012, "cases", 3067, "c")])
    rev = pd.DataFrame([REV(unit_id="GJ", year=2012, variable="cases", source_id="a|b", check="cross_source")])
    res = gates.cross_source(recs, reviewed=rev)
    assert not res.passed and "GJ 2012 cases" in res.detail                # pair a|c not reviewed
    rev2 = pd.DataFrame([REV(unit_id="GJ", year=2012, variable="cases", source_id="", check="cross_source")])
    assert not gates.cross_source(recs, reviewed=rev2).passed               # no pair named: silences nothing


def test_read_reviewed_cross_source_rows_need_two_sources(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("outcome,unit_id,year,variable,source_id,check,disposition,reason,evidence\n"
                 "malaria,OD,2010,cases,a,cross_source,keep,r,e\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pair"):
        gates.read_reviewed(p)


def test_cross_source_table_lists_only_disagreements():
    recs = records.make([R("OD", "Odisha", 2010, "cases", 1000, "a"), R("OD", "Odisha", 2010, "cases", 1015, "b"),
                         R("OD", "Odisha", 2010, "deaths", 1000, "a"), R("OD", "Odisha", 2010, "deaths", 1100, "b")])
    t = gates.cross_source_table(recs)
    assert list(t.variable) == ["deaths"] and t.iloc[0].value_a == 1000 and t.iloc[0].value_b == 1100


def test_agree_rule():
    assert gates.agree(1000, 1015) and not gates.agree(1000, 1030)
    assert gates.agree(3, 7) and gates.agree(95, 100) and not gates.agree(90, 100)
    assert gates.agree(0, 5) and not gates.agree(0, 6)


# ---------------------------------------------------------------- national totals details

def test_national_totals_reviewed_exception_and_dld_skipped():
    recs = records.make([R("PB", "Punjab", 2011, "foodgrain_t", 101.15, "foodgrain_rbi2019"),
                         R("TOTAL", "ALL INDIA", 2011, "foodgrain_t", 100.0, "foodgrain_rbi2019"),
                         R("PB", "Punjab", 2012, "foodgrain_t", 50.0, "foodgrain_dld")])
    res = gates.national_totals(recs, reviewed=pd.DataFrame())
    assert not res.passed and "foodgrain_rbi2019 2011 foodgrain_t" in res.detail
    rev = pd.DataFrame([REV(outcome="foodgrain", unit_id="TOTAL", year=2011, variable="foodgrain_t",
                            source_id="foodgrain_rbi2019", check="national_total")])
    assert gates.national_totals(recs, reviewed=rev).passed


def test_national_totals_pool_partial_states_and_nan_total_skipped():
    recs = records.make([R("AP_TG", "Andhra Pradesh", 2015, "cases", 60, "s"),
                         R("AP_TG", "Telangana", 2015, "cases", 40, "s"),
                         R("TOTAL", "Total", 2015, "cases", 100, "s"),
                         R("OD", "Odisha", 2016, "cases", 5, "s"),
                         R("TOTAL", "Total", 2016, "cases", math.nan, "s")])
    assert gates.national_totals(recs, reviewed=pd.DataFrame()).passed


# ---------------------------------------------------------------- completeness details

def test_completeness_absent_row_flagged_and_missing_source_excuses_only_empty_years():
    panel = pd.DataFrame({"unit_id": ["OD", "GJ", "OD", "GJ", "OD"], "year": [2015, 2015, 2016, 2016, 2017],
                          "foodgrain_t": [1.0, 2.0, math.nan, math.nan, math.nan]})
    res = gates.completeness(panel, years=[2015, 2016, 2017], units=["OD", "GJ"], var="foodgrain_t",
                             reviewed=pd.DataFrame())
    assert not res.passed and "GJ 2017" in res.detail and "OD 2016" in res.detail
    ms = pd.DataFrame([REV(outcome="foodgrain", unit_id="ALL", year=y, variable="foodgrain_t",
                           source_id="foodgrain_rbi2023", check="missing_source", disposition="non_reporting")
                       for y in (2016, 2017)])
    res = gates.completeness(panel, years=[2015, 2016, 2017], units=["OD", "GJ"], var="foodgrain_t", reviewed=ms)
    assert not res.passed and "GJ 2017" in res.detail and "OD 2016" not in res.detail   # absent row still fails
    panel.loc[len(panel)] = ["GJ", 2017, math.nan]
    assert gates.completeness(panel, years=[2015, 2016, 2017], units=["OD", "GJ"], var="foodgrain_t",
                              reviewed=ms).passed
    panel.loc[panel.index[2], "foodgrain_t"] = 3.0          # 2016 no longer an empty year: GJ 2016 needs its own row
    res = gates.completeness(panel, years=[2015, 2016, 2017], units=["OD", "GJ"], var="foodgrain_t", reviewed=ms)
    assert not res.passed and "GJ 2016" in res.detail


def test_completeness_accepts_nan_made_by_a_reviewed_mask_or_non_reporting_row():
    panel = pd.DataFrame({"unit_id": ["OD", "GJ"], "year": [2016, 2016], "cases": [math.nan, math.nan]})
    rev = pd.DataFrame([REV(unit_id="OD", year=2016, variable="cases", check="plausibility",
                            disposition="non_reporting"),
                        REV(unit_id="GJ", year=2016, variable="cases", check="plausibility", disposition="keep")])
    res = gates.completeness(panel, years=[2016], units=["OD", "GJ"], var="cases", reviewed=rev)
    assert not res.passed and "GJ 2016" in res.detail and "OD 2016" not in res.detail


def test_completeness_keep_row_does_not_excuse_nan():
    panel = pd.DataFrame({"unit_id": ["OD"], "year": [2016], "cases": [math.nan]})
    rev = pd.DataFrame([REV(unit_id="OD", year=2016, variable="cases", check="completeness", disposition="keep")])
    assert not gates.completeness(panel, years=[2016], units=["OD"], var="cases", reviewed=rev).passed


def test_pool_rejects_multi_member_groups_outside_pooled_units():
    recs = records.make([R("OD", "Orissa", 2010, "cases", 5, "s"), R("OD", "Odisha", 2010, "cases", 5, "s")])
    with pytest.raises(ValueError, match="OD"):
        gates.pool(recs)


def test_completeness_blank_year_rows_excuse_nothing():
    panel = pd.DataFrame({"unit_id": ["OD"], "year": [2016], "cases": [math.nan]})
    rev = pd.DataFrame([REV(unit_id="OD", year="", variable="cases", check="completeness")])
    assert not gates.completeness(panel, years=[2016], units=["OD"], var="cases", reviewed=rev).passed


# ---------------------------------------------------------------- plausibility

def test_plausibility_flags_outliers_vs_unit_median():
    years = list(range(2001, 2011))
    vals = [100.0] * 9 + [1000.0]
    panel = pd.DataFrame({"unit_id": ["OD"] * 10 + ["SK"] * 10, "year": years * 2,
                          "cases": vals + [1.0] * 9 + [50.0]})
    res = gates.plausibility(panel, "cases", reviewed=pd.DataFrame())
    assert not res.passed and "OD 2010" in res.detail and "SK" not in res.detail   # SK median 1 < min_count
    rev = pd.DataFrame([REV(unit_id="OD", year=2010, variable="cases", check="plausibility")])
    assert gates.plausibility(panel, "cases", reviewed=rev).passed


def test_plausibility_rolling_median_ignores_trends_but_flags_spikes():
    years = list(range(2001, 2021))
    trend = [10000.0 * 0.8 ** k for k in range(20)]                  # -20%/yr: x0.014 over the series
    spike = [500.0] * 20
    spike[10] = 5000.0                                                 # x10 one year
    panel = pd.DataFrame({"unit_id": ["OD"] * 20 + ["GJ"] * 20, "year": years * 2, "cases": trend + spike})
    t = gates.plausibility_table(panel, "cases")
    assert list(zip(t.unit_id, t.year)) == [("GJ", 2011)] and t.iloc[0]["median"] == 500


def test_plausibility_split_at_definition_break_and_window_in_calendar_years():
    years = list(range(2004, 2017))
    vals = [1000.0] * 10 + [100.0] * 3                                # level change at 2014 (definition)
    panel = pd.DataFrame({"unit_id": ["OD"] * 13, "year": years, "farmers": vals})
    assert len(gates.plausibility_table(panel, "farmers", split=2014)) == 0
    assert len(gates.plausibility_table(panel, "farmers")) > 0         # unsplit: 2014 window mixes 1000s
    gap = pd.DataFrame({"unit_id": ["OD"] * 4, "year": [2001, 2002, 2010, 2011], "cases": [100.0, 100.0, 5.0, 5.0]})
    assert len(gates.plausibility_table(gap, "cases")) == 0             # 2010 window 2007-2013: only 2 obs


def test_plausibility_low_side_and_nan_ignored():
    panel = pd.DataFrame({"unit_id": ["OD"] * 5, "year": range(2001, 2006), "cases": [100, 100, 100, 10, math.nan]})
    res = gates.plausibility(panel, "cases", reviewed=pd.DataFrame())
    assert not res.passed and "OD 2004" in res.detail and "OD 2005" not in res.detail


# ---------------------------------------------------------------- panels

def test_wide_panel_aber_and_flags():
    ch = pd.DataFrame([
        {"unit_id": "OD", "year": 2010, "variable": "tested", "value": 1000.0, "source_id": "a", "provisional": False},
        {"unit_id": "OD", "year": 2010, "variable": "cases", "value": 10.0, "source_id": "b", "provisional": True},
        {"unit_id": "OD", "year": 2011, "variable": "tested", "value": math.nan, "source_id": "", "provisional": False},
    ])
    pop = pd.DataFrame({"unit_id": ["OD", "OD"], "year": [2010, 2011], "population": [10000.0, 10000.0]})
    p = assemble.wide(ch, ["tested", "cases"], units=["OD"], years=[2010, 2011], population=pop)
    p["aber"] = assemble.aber(p)
    p = p.set_index("year")
    assert p.loc[2010, "aber"] == 10.0 and math.isnan(p.loc[2011, "aber"]) and math.isnan(p.loc[2011, "cases"])
    assert bool(p.loc[2010, "provisional_any"]) and not bool(p.loc[2011, "provisional_any"])
    assert p.loc[2010, "sources"] == "tested:a;cases:b" and p.loc[2010, "unit_name"] == "Odisha"


def test_farmer_panel_definition_break():
    ch = pd.DataFrame([{"unit_id": "OD", "year": y, "variable": "farmers", "value": 1.0, "source_id": "a",
                        "provisional": False} for y in (2013, 2014)])
    p = assemble.farmer_panel(ch, units=["OD"], years=[2013, 2014], population=None).set_index("year")
    assert not p.loc[2013, "definition_break_2014"] and p.loc[2014, "definition_break_2014"]
    assert math.isnan(p.loc[2013, "ag_labourers"])


# ---------------------------------------------------------------- outcome gates on files

def test_run_outcome_gates_on_files(tmp_path):
    out = tmp_path / "outcomes"
    out.mkdir()
    recs = records.make([R("OD", "Odisha", 2010, "heat_deaths", 130, "ncrb_2010"),
                         R("TOTAL", "Total", 2010, "heat_deaths", 130, "ncrb_2010")]).assign(outcome="heat_deaths")
    recs.to_csv(out / "outcome_records_all.csv.gz", index=False)
    pop = pd.DataFrame({"unit_id": ["OD"], "year": [2010], "population": [1.0]})
    pop.to_csv(out / "population_unit_year.csv", index=False)
    cfg = {"heat_deaths": {"file": "heat_deaths_state_year.csv", "years": [2010], "units": ["OD"],
                           "vars": ["heat_deaths"]}}
    panel = assemble.panels({"heat_deaths": recs.drop(columns="outcome")}, pop, pd.DataFrame(), outcomes=cfg)
    panel["heat_deaths"].to_csv(out / "heat_deaths_state_year.csv", index=False)
    pd.DataFrame({"outcome": ["heat_deaths"], "source_id": ["ncrb_1999"], "reason": ["scan"]}).to_csv(
        out / "missing_sources.csv", index=False)
    rev = tmp_path / "rev.csv"
    head = "outcome,unit_id,year,variable,source_id,check,disposition,reason,evidence\n"
    rev.write_text(head, encoding="utf-8")
    spec = {"heat_deaths": {"file": "heat_deaths_state_year.csv", "years": [2010], "units": ["OD"], "split": None,
                            "complete": ["heat_deaths", ("population", [2009, 2010])], "plausible": ["heat_deaths"]}}
    res = gates.run_outcome_gates(out, reviewed_path=rev, spec=spec)
    names = {r.name: r.passed for r in res}
    assert names == {"outcome_cross_source_heat_deaths": True, "outcome_national_total_heat_deaths": True,
                     "outcome_completeness_heat_deaths_heat_deaths": True,
                     "outcome_completeness_heat_deaths_population": False,      # OD 2009 row absent
                     "outcome_plausibility_heat_deaths_heat_deaths": True, "outcome_missing_sources": False,
                     "outcome_reproduce": True, "outcome_partial_year_heat_deaths": True,
                     "outcome_population": False}                                # OD 2010 only, not 34 x 2001-2027
    assert (out / "cross_source_report.csv").exists()
    rev.write_text(head + "heat_deaths,ALL,1999,heat_deaths,ncrb_1999,missing_source,non_reporting,scan only,"
                          "ADSI 1999\n", encoding="utf-8")
    res = gates.run_outcome_gates(out, reviewed_path=rev, spec=spec)
    assert {r.name: r.passed for r in res}["outcome_missing_sources"]
    (out / "heat_deaths_state_year.csv").unlink()                      # a missing panel is a FAIL result
    res = {r.name: r for r in gates.run_outcome_gates(out, reviewed_path=rev, spec=spec)}
    assert not res["outcome_panel_heat_deaths"].passed and "heat_deaths_state_year.csv" in res[
        "outcome_panel_heat_deaths"].detail
    assert not res["outcome_reproduce"].passed


# ---------------------------------------------------------------- reproduction gate

def test_reproduce_gate_rebuilds_panels_from_records_and_reviewed(tmp_path):
    cfg = {"heat_deaths": {"file": "heat_deaths_state_year.csv", "years": range(2010, 2012), "vars": ["heat_deaths"],
                           "units": ["OD", "GJ"]}}
    recs = records.make([R("OD", "Odisha", 2010, "heat_deaths", 130, "ncrb_2010"),
                         R("GJ", "Gujarat", 2010, "heat_deaths", 0, "ncrb_2010"),
                         R("OD", "Odisha", 2011, "heat_deaths", 120, "ncrb_2011")])
    pop = pd.DataFrame({"unit_id": ["OD", "GJ"] * 2, "year": [2010, 2010, 2011, 2011], "population": [1.0, 2, 3, 4]})
    rev = tmp_path / "rev.csv"
    rev.write_text("outcome,unit_id,year,variable,source_id,check,disposition,reason,evidence\n"
                   "heat_deaths,GJ,2010,heat_deaths,,plausibility,mask,r,e\n", encoding="utf-8")
    out = tmp_path / "outcomes"
    out.mkdir()
    pop.to_csv(out / "population_unit_year.csv", index=False)
    recs.assign(outcome="heat_deaths").to_csv(out / "outcome_records_all.csv.gz", index=False)
    panels = assemble.panels({"heat_deaths": recs}, pop, gates.read_reviewed(rev), outcomes=cfg)
    assert math.isnan(panels["heat_deaths"].set_index(["unit_id", "year"]).loc[("GJ", 2010), "heat_deaths"])
    panels["heat_deaths"].to_csv(out / "heat_deaths_state_year.csv", index=False)
    assert assemble.reproduce_gate(out, rev, outcomes=cfg).passed
    p = pd.read_csv(out / "heat_deaths_state_year.csv")
    p.loc[0, "heat_deaths"] = 130.0001                  # inside pandas' default rtol 1e-5: exact comparison
    p.to_csv(out / "heat_deaths_state_year.csv", index=False)
    assert not assemble.reproduce_gate(out, rev, outcomes=cfg).passed
    p.loc[0, "heat_deaths"] = 131
    p.to_csv(out / "heat_deaths_state_year.csv", index=False)
    res = assemble.reproduce_gate(out, rev, outcomes=cfg)
    assert not res.passed and "heat_deaths_state_year.csv" in res.detail
    (out / "heat_deaths_state_year.csv").unlink()
    assert not assemble.reproduce_gate(out, rev, outcomes=cfg).passed


# ---------------------------------------------------------------- Ruling P17: partial-year gate

def test_partial_year_gate_requires_a_mask_where_a_partial_value_is_chosen():
    P = records.PARTIAL_YEAR
    recs = records.make([R("OD", "Orissa" + P, 2006, "cases", 100, "a", True),
                         R("GJ", "Gujarat" + P, 2006, "cases", 50, "a", True),
                         R("GJ", "Gujarat", 2006, "cases", 90, "b"),             # final value wins: not chosen
                         R("KL", "Kerala" + P, 2006, "cases", 7, "a", True),
                         R("KL", "Kerala", 2006, "cases", 9, "c", True)])
    ranks = {"a": 2, "b": 1, "c": 1}
    res = gates.partial_year(recs, ranks, reviewed=None, outcome="malaria")
    assert res.name == "outcome_partial_year_malaria" and not res.passed
    assert "OD 2006 cases" in res.detail and "KL 2006 cases" in res.detail and "GJ" not in res.detail
    rev = pd.DataFrame([REV(unit_id="OD", year=2006, variable="cases", check="completeness", disposition="mask"),
                        REV(unit_id="KL", year=2006, variable="cases", check="cross_source", source_id="a|c",
                            disposition="use_source:c")])
    assert gates.partial_year(recs, ranks, reviewed=rev, outcome="malaria").passed
    for disp in ("non_reporting", "keep"):                    # only a mask (or a non-partial source) clears it
        bad = rev.assign(disposition=["mask", "use_source:c"]).copy()
        bad.loc[0, "disposition"] = disp
        assert not gates.partial_year(recs, ranks, reviewed=bad, outcome="malaria").passed
    other = rev.assign(outcome="dengue")                      # rows of another outcome do not count
    assert not gates.partial_year(recs, ranks, reviewed=other, outcome="malaria").passed
    t = gates.partial_year_cells(recs, ranks, reviewed=rev, outcome="malaria")
    assert set(zip(t.unit_id, t.ok)) == {("OD", True), ("KL", True)}


def test_partial_year_gate_restricted_to_panel_units_and_years():
    recs = records.make([R("OD", "Orissa" + records.PARTIAL_YEAR, 2026, "cases", 100, "a", True)])
    assert not gates.partial_year(recs, {"a": 1}).passed
    assert gates.partial_year(recs, {"a": 1}, years=range(2002, 2026)).passed
    assert gates.partial_year(recs, {"a": 1}, units=["GJ"]).passed


def test_module_source_ranks_equal_outcomes_sources_csv():
    from pipeline.outcomes import dengue, foodgrain, malaria, ncrb
    csv = assemble.ranks()
    mods = {"malaria": malaria, "dengue": dengue, "ncrb": ncrb, "foodgrain": foodgrain}
    seen = set()
    for name, mod in mods.items():
        for sid, cfg in mod.SOURCES.items():
            assert sid in csv, f"{name}: {sid} not in outcomes_sources.csv"
            assert cfg["rank"] == csv[sid], f"{name}: {sid} rank {cfg['rank']} != csv {csv[sid]}"
            seen.add(sid)
    # every non-population source of the CSV belongs to one module
    pop = set(pd.read_csv(assemble.SOURCES_CSV).query("outcome == 'population'").source_id)
    assert set(csv) - pop == seen
    assert csv["heat_pib1721"] == 0 and csv["foodgrain_dld"] == 0          # cross-check-only sources


def test_completeness_counts_reviewed_masks_before_missing_source_years():
    # malaria 2006: every cell masked by its own reviewed row AND the year is a missing-source year
    panel = pd.DataFrame({"unit_id": ["OD", "GJ"], "year": [2006, 2006], "cases": [math.nan, math.nan]})
    rev = pd.DataFrame([REV(unit_id=u, year=2006, variable="cases", check="completeness", disposition="mask")
                        for u in ("OD", "GJ")]
                       + [REV(unit_id="ALL", year=2006, source_id="mal_sit_0509", check="missing_source")])
    res = gates.completeness(panel, years=[2006], units=["OD", "GJ"], var="cases", reviewed=rev, outcome="malaria")
    assert res.passed and "reviewed 2," in res.detail and "[2006]: 0)" in res.detail
