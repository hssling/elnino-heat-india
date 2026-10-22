import math

import pandas as pd
import pytest

from pipeline.outcomes import farmer_zeros as fz
from pipeline.outcomes import records


def R(unit, label, year, var, value, src=None):
    return {"unit_id": unit, "raw_label": label, "year": year, "variable": var, "value": value,
            "source_id": src or f"ncrb_{year}", "provisional": False}


def series(unit, label, var, values: dict):
    return [R(unit, label, y, var, v) for y, v in values.items()]


def rows_by_key(df):
    return {(r.unit_id, int(r.year), r.variable): r for r in df.itertuples()}


def test_lambda_same_side_then_other_side():
    s = {2009: 1054.0, 2010: 993.0, 2011: 807.0, 2012: math.nan, 2013: 0.0, 2014: 0.0, 2015: 40.0, 2016: 0.0}
    assert fz.reference(s, 2013) == ([2009, 2010, 2011], 951.3333333333334, False)
    years, lam, crossed = fz.reference(s, 2014)                          # nothing earlier post-2014: other side
    assert years == [2009, 2010, 2011] and crossed
    assert fz.reference(s, 2016) == ([2015], 40.0, False)                # same side wins even with one value
    assert fz.reference({2001: 0.0}, 2001) == ([], None, False)


TOTALS = [R("TOTAL", "TOTAL (ALL INDIA)", 2013, "farmers", 11772), R("TOTAL", "TOTAL (ALL INDIA)", 2013, "farming_sector", 11772),
          R("TOTAL", "TOTAL (ALL INDIA)", 2014, "farmers", 5650), R("TOTAL", "TOTAL (ALL INDIA)", 2014, "farming_sector", 12360),
          R("TOTAL", "TOTAL (ALL INDIA)", 2014, "ag_labourers", 6710)]


def test_scale_factors_from_national_totals():
    f = fz.scale_factors(records.make(TOTALS))
    assert f["farmers"] == 5650 / 11772 and f["farming_sector"] == 12360 / 11772 and "ag_labourers" not in f


def test_cross_break_lambda_is_scaled_by_the_national_factor():
    # 2014 zero judged from 2011-2013 values (other side): raw 10, scaled 10 x 0.48 = 4.8 < 5 -> true zero
    recs = records.make(TOTALS + series("DL", "DELHI", "farmers", {2011: 10, 2012: 12, 2013: 8, 2014: 0})
                        + series("WB", "WEST BENGAL", "farmers", {2009: 1054, 2010: 993, 2011: 807, 2014: 0})
                        + series("HP", "HIMACHAL PRADESH", "farming_sector", {2011: 4, 2012: 5, 2013: 5, 2014: 0}))
    out = rows_by_key(fz.zero_review(recs))
    assert ("DL", 2014, "farmers") not in out
    r = out[("WB", 2014, "farmers")]
    assert r.disposition == "non_reporting"
    assert "lambda_raw 951.33" in r.reason and "0.4800" in r.reason and "lambda_scaled 456.59" in r.reason
    assert ("HP", 2014, "farming_sector") not in out                     # 4.67 x 1.05 = 4.90 < 5


def test_cross_break_needs_national_totals():
    recs = records.make(series("WB", "WEST BENGAL", "farmers", {2009: 1054, 2010: 993, 2011: 807, 2014: 0}))
    with pytest.raises(ValueError, match="national"):
        fz.zero_review(recs)


def test_ag_labourers_has_no_cross_break_fallback():
    s = {2014: 0.0}
    assert fz.lam(s, 2014, "ag_labourers", {"farmers": 0.5}) is None
    recs = records.make(TOTALS + series("JH", "JHARKHAND", "ag_labourers", {2014: 0}))
    assert fz.zero_review(recs).empty


def test_zero_rule_non_reporting_and_true_zero():
    recs = records.make(series("WB", "WEST BENGAL", "farmers", {2009: 1054, 2010: 993, 2011: 807, 2013: 0})
                        + series("WB", "WEST BENGAL", "farming_sector", {2009: 1054, 2010: 993, 2011: 807, 2013: 0})
                        + series("SK", "SIKKIM", "farmers", {2009: 3, 2010: 2, 2011: 4, 2013: 0}))
    out = rows_by_key(fz.zero_review(recs))
    r = out[("WB", 2013, "farmers")]
    assert r.disposition == "non_reporting" and r.check == "completeness" and r.outcome == "farmer_suicides"
    assert r.reason.startswith(fz.PREFIX) and "951.3" in r.reason and "2009 1054" in r.evidence
    assert ("WB", 2013, "farming_sector") in out
    assert ("SK", 2013, "farmers") not in out                         # lambda 3 < 5: a true zero


def test_farming_sector_nan_when_a_component_is_non_reporting_post_2014():
    recs = records.make(series("JH", "JHARKHAND", "ag_labourers", {2014: 38, 2015: 40, 2016: 0})
                        + series("JH", "JHARKHAND", "farmers", {2014: 17, 2015: 2, 2016: 3})
                        + series("JH", "JHARKHAND", "farming_sector", {2014: 55, 2015: 42, 2016: 3}))
    out = rows_by_key(fz.zero_review(recs))
    assert out[("JH", 2016, "ag_labourers")].disposition == "non_reporting"
    fs = out[("JH", 2016, "farming_sector")]
    assert fs.disposition == "non_reporting" and "ag_labourers" in fs.reason
    assert ("JH", 2016, "farmers") not in out


def test_pooled_member_zero_is_dropped_with_partial_pool_keep_row():
    recs = records.make(series("AP_TG", "ANDHRA PRADESH", "ag_labourers", {2019: 300, 2020: 400, 2021: 500, 2022: 548})
                        + series("AP_TG", "TELANGANA", "ag_labourers", {2019: 8, 2020: 5, 2021: 7, 2022: 0}))
    out = rows_by_key(fz.zero_review(recs))
    r = out[("AP_TG", 2022, "ag_labourers")]
    assert r.disposition == "keep" and "partial_pool" in r.reason and "TELANGANA" in r.reason and "6.67" in r.reason


def test_pooled_unit_all_members_non_reporting_is_unit_non_reporting():
    recs = records.make(series("JK", "JAMMU & KASHMIR", "farmers", {2017: 20, 2018: 30, 2019: 25, 2020: 0})
                        + series("JK", "LADAKH", "farmers", {2020: 0}))
    out = rows_by_key(fz.zero_review(recs))
    assert out[("JK", 2020, "farmers")].disposition == "non_reporting"


def test_note_cited_where_ncrb_names_the_state():
    recs = records.make(TOTALS + series("TR", "TRIPURA", "farmers", {2008: 50, 2009: 45, 2010: 58, 2021: 0}))
    r = rows_by_key(fz.zero_review(recs))[("TR", 2021, "farmers")]
    assert "reported zero suicides" in r.evidence and "p271" in r.evidence


def test_rule_gate_requires_exactly_the_generated_rows():
    recs = records.make(series("WB", "WEST BENGAL", "farmers", {2009: 1054, 2010: 993, 2011: 807, 2013: 0}))
    gen = fz.zero_review(recs)
    assert fz.rule_gate(recs, gen).passed
    assert not fz.rule_gate(recs, gen.iloc[0:0]).passed
    extra = pd.concat([gen, gen.assign(year=2011)])
    res = fz.rule_gate(recs, extra)
    assert not res.passed and "WB 2011 farmers" in res.detail


def test_merge_into_reviewed_replaces_only_generated_rows():
    recs = records.make(series("WB", "WEST BENGAL", "farmers", {2009: 1054, 2010: 993, 2011: 807, 2013: 0}))
    hand = pd.DataFrame([{"outcome": "farmer_suicides", "unit_id": "WB", "year": "2012", "variable": "farmers",
                          "source_id": "ncrb_2012", "check": "completeness", "disposition": "non_reporting",
                          "reason": "NR printed", "evidence": "e"}])
    stale = fz.zero_review(recs).assign(year=2001)
    merged = fz.merge(pd.concat([hand, stale]), fz.zero_review(recs))
    assert sorted(merged.year.astype(str)) == ["2012", "2013"]
