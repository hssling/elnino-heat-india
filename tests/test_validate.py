import numpy as np
import pandas as pd
import pytest

from pipeline import validate as v


def test_allindia_gate_pass_and_fail():
    years = list(range(1981, 2025))
    rng = np.random.default_rng(0)
    jjas = 850 * (1 + rng.normal(0, 0.1, len(years)))
    cy = pd.DataFrame({"region_id": "IND", "year": years, "rain_jjas_mm": jjas})
    normal = cy[cy.year.between(1981, 2020)].rain_jjas_mm.mean()
    true_dep = 100 * (cy.rain_jjas_mm - normal) / normal
    ref = pd.DataFrame({"year": years[-12:], "dep_pct": true_dep.iloc[-12:].round(0)})
    assert v.gate_allindia_jjas(cy, ref).passed
    ref_bad = ref.assign(dep_pct=-ref.dep_pct)
    assert not v.gate_allindia_jjas(cy, ref_bad).passed


def _allindia_fixture(seed=0):
    years = list(range(1981, 2025))
    rng = np.random.default_rng(seed)
    cy = pd.DataFrame({"region_id": "IND", "year": years, "rain_jjas_mm": 850 * (1 + rng.normal(0, 0.1, len(years)))})
    normal = cy[cy.year.between(1981, 2020)].rain_jjas_mm.mean()
    dep = 100 * (cy.rain_jjas_mm - normal) / normal
    return cy, years[-12:], dep.iloc[-12:].to_numpy()


def test_allindia_gate_tolerates_constant_bias():
    cy, yrs, dep = _allindia_fixture()
    res = v.gate_allindia_jjas(cy, pd.DataFrame({"year": yrs, "dep_pct": dep - 3.0}))   # ours = ref + 3 pp
    assert res.passed
    for token in ("n=12", "r=", "bias=+3.0", "raw max|diff|=3.0", "bias-adjusted max|diff|=0.0",
                  "(normal 1981-2020; IMD refs use era-specific LPAs)"):
        assert token in res.detail, res.detail


def test_allindia_gate_fails_on_single_year_deviation_after_bias_removal():
    cy, yrs, dep = _allindia_fixture()
    ref = dep - 3.0
    ref[0] += 12.0
    assert not v.gate_allindia_jjas(cy, pd.DataFrame({"year": yrs, "dep_pct": ref})).passed


def test_allindia_gate_fails_on_negated_reference():
    cy, yrs, dep = _allindia_fixture()
    assert not v.gate_allindia_jjas(cy, pd.DataFrame({"year": yrs, "dep_pct": -dep})).passed


def test_allindia_gate_fails_on_low_r_even_with_small_diffs():
    years = list(range(1981, 2025))
    ours_dev = [2, -2] * 6
    ref_dev = [2, 2, -2, -2] * 3                      # uncorrelated with ours_dev; |diff| <= 4 pp
    cy = pd.DataFrame({"region_id": "IND", "year": years, "rain_jjas_mm": 850.0})
    cy.loc[cy.year >= 2013, "rain_jjas_mm"] = [850 * (1 + d / 100) for d in ours_dev]
    ref = pd.DataFrame({"year": list(range(2013, 2025)), "dep_pct": ref_dev})
    res = v.gate_allindia_jjas(cy, ref)
    assert float(res.detail.split("bias-adjusted max|diff|=")[1].split(" ")[0]) <= 5.0, res.detail
    assert not res.passed


def test_enso_gate_tolerates_one_season():
    ep = pd.DataFrame({"phase": ["el_nino", "el_nino"], "start_season": ["JJA", "AMJ"], "start_year": [2009, 1997],
                       "provisional": [False, False]})
    ref = pd.DataFrame({"phase": ["el_nino", "el_nino"], "start_season": ["JAS", "AMJ"], "start_year": [2009, 1997]})
    assert v.gate_enso_episodes(ep, ref).passed
    ref2 = pd.DataFrame({"phase": ["el_nino"], "start_season": ["NDJ"], "start_year": [2009]})
    assert not v.gate_enso_episodes(ep, ref2).passed


def test_blocklist_gate():
    assert v.gate_blocklist([{"path": "data/external/a.csv", "url": "file:/x/a.csv"}]).passed
    assert not v.gate_blocklist([{"path": "x", "url": "file:/r/dengue_climate_india.csv"}]).passed


def test_completeness_gate():
    m = pd.DataFrame({"region_id": ["A"] * 12, "year": 2020, "month": range(1, 13), "rain_mm": 1.0, "tmax_mean": 30.0})
    assert v.gate_completeness(m, expected_regions=1, years=[2020]).passed
    assert not v.gate_completeness(m.iloc[:11], expected_regions=1, years=[2020]).passed


def _month(regions, years):
    return pd.DataFrame([{"region_id": r, "year": y, "month": mo, "rain_mm": 1.0, "tmax_mean": 30.0}
                         for r in regions for y in years for mo in range(1, 13)])


def test_completeness_uses_fixed_expected_counts_and_level_name():
    assert v.EXPECTED_REGIONS == {"country": 1, "state": 36, "district": 666}
    m = _month(["A", "B"], [2020])
    res = v.gate_completeness(m, expected_regions=3, years=[2020], level="state")
    assert res.name == "completeness_state" and not res.passed       # a missing region fails
    assert "regions=2 expected_regions=3" in res.detail
    # same row count but a duplicated region in place of a missing one also fails
    m2 = pd.concat([_month(["A"], [2020]), _month(["A"], [2020]).assign(year=2020)])
    assert not v.gate_completeness(m2, expected_regions=2, years=[2020]).passed


def test_completeness_allows_nan_only_where_qc_masked():
    m = _month(["A", "B"], [2020, 2021])
    m.loc[(m.region_id == "B") & (m.year == 2021) & (m.month == 7), "rain_mm"] = np.nan
    assert not v.gate_completeness(m, expected_regions=2, years=[2020, 2021]).passed
    ok = v.gate_completeness(m, expected_regions=2, years=[2020, 2021], allowed_nan={("B", 2021)})
    assert ok.passed and "qc-explained NaN=1" in ok.detail


def _year_table(values_by_region, base_value=1000.0):
    rows = []
    for rid, over in values_by_region.items():
        for y in range(1981, 2016):
            rows.append({"region_id": rid, "region_name": rid + "name", "year": y,
                         "rain_jjas_mm": over.get(y, base_value), "rain_annual_mm": 2 * over.get(y, base_value),
                         "qc_masked": ""})
    return pd.DataFrame(rows)


def test_qc_flags_ratio_to_base_median():
    t = _year_table({"S1": {2011: 2600.0, 2012: 2400.0}, "S2": {1990: 200.0}})
    f = v.qc_flags(t, "state")
    got = sorted(zip(f.region_id, f.year, f.variable))
    assert got == [("S1", 2011, "rain_annual_mm"), ("S1", 2011, "rain_jjas_mm"),
                   ("S2", 1990, "rain_annual_mm"), ("S2", 1990, "rain_jjas_mm")]
    assert f.columns.tolist() == ["level", "region_id", "region_name", "year", "variable", "ratio"]
    assert f[(f.region_id == "S1") & (f.variable == "rain_jjas_mm")].ratio.item() == pytest.approx(2.6)


def _reviewed(rows):
    return pd.DataFrame([dict(level=l, region_id=r, region_name="", year=y, variable=var, ratio=0.0,
                              disposition=d, reason="why", evidence="ev") for l, r, y, var, d in rows],
                        columns=["level", "region_id", "region_name", "year", "variable", "ratio", "disposition",
                                 "reason", "evidence"])


def test_qc_gate_fails_on_unreviewed_flag_and_passes_when_reviewed():
    t = _year_table({"S1": {2011: 2600.0}})
    res = v.gate_qc_plausibility({"state": t}, _reviewed([]))
    assert res.name == "qc_plausibility" and not res.passed and "unreviewed=2" in res.detail
    rev = _reviewed([("state", "S1", 2011, "rain_jjas_mm", "keep"), ("state", "S1", 2011, "rain_annual_mm", "keep")])
    res = v.gate_qc_plausibility({"state": t}, rev)
    assert res.passed, res.detail
    assert "flagged=2" in res.detail and "keep=2" in res.detail


def test_qc_gate_requires_mask_dispositions_to_be_applied():
    t = _year_table({"S1": {2011: 2600.0}})
    rev = _reviewed([("state", "S1", 2011, "rain_jjas_mm", "mask"), ("state", "S1", 2011, "rain_annual_mm", "keep")])
    res = v.gate_qc_plausibility({"state": t}, rev)
    assert not res.passed and "mask not applied" in res.detail
    applied = t.copy()
    sel = (applied.region_id == "S1") & (applied.year == 2011)
    applied.loc[sel, "rain_jjas_mm"] = np.nan
    applied.loc[sel, "qc_masked"] = "rain_jjas_mm"
    assert v.gate_qc_plausibility({"state": applied}, rev).passed


def test_power_gate():
    years = range(1995, 2010)
    rng = np.random.default_rng(2)
    base = rng.normal(800, 100, len(years))
    imd = pd.DataFrame({"region_id": "S", "year": list(years), "rain_jjas_mm": base})
    pw = pd.DataFrame([{"region_id": "S", "year": y, "month": m, "rain_mm": b / 4 + rng.normal(0, 5)}
                       for y, b in zip(years, base) for m in (6, 7, 8, 9)])
    assert v.gate_power_vs_imd(imd, pw).passed


def _power_fixture(r_noise):
    years = list(range(1995, 2010))
    rng = np.random.default_rng(5)
    base = rng.normal(800, 100, len(years))
    imd = pd.DataFrame({"region_id": "S", "region_name": "Sname", "year": years, "rain_jjas_mm": base})
    pw = pd.DataFrame([{"region_id": "S", "year": y, "month": m, "rain_mm": b / 4 + rng.normal(0, r_noise)}
                       for y, b in zip(years, base) for m in (6, 7, 8, 9)])
    return imd, pw


def test_power_diagnostic_passes_even_when_poor_but_fails_without_overlap():
    imd, pw = _power_fixture(r_noise=500)          # essentially uncorrelated
    res = v.gate_power_vs_imd(imd, pw)
    assert res.passed and "states=1" in res.detail and "median r=" in res.detail and "min r=" in res.detail
    assert not v.gate_power_vs_imd(imd.assign(region_id="X"), pw).passed


def test_power_table_rows():
    imd, pw = _power_fixture(r_noise=5)
    t = v.power_table(imd, pw)
    assert t.columns.tolist() == ["region_id", "region_name", "r", "n_years"]
    assert t.iloc[0].n_years == 15 and t.iloc[0].r > 0.9


def test_run_all_report_has_diagnostic_section_and_renamed_row(tmp_path, monkeypatch):
    years = list(range(1981, 2026))
    rng = np.random.default_rng(1)
    jjas = 850 * (1 + rng.normal(0, 0.1, len(years)))
    pd.DataFrame({"region_id": "IND", "year": years, "rain_jjas_mm": jjas}).to_csv(tmp_path / "climate_country_year.csv", index=False)
    for level, rid in (("state", "S"), ("district", "D")):
        pd.DataFrame({"region_id": rid, "region_name": rid + "name", "year": years, "rain_jjas_mm": jjas,
                      "rain_annual_mm": 1.2 * jjas, "qc_masked": ""}).to_csv(
            tmp_path / f"climate_{level}_year.csv", index=False)
    for level, rid, name in (("country", "IND", "climate_country_month.csv"), ("state", "S", "climate_state_month.csv"),
                             ("district", "D", "climate_district_month.csv.gz")):
        pd.DataFrame([{"region_id": rid, "year": y, "month": m, "rain_mm": 1.0, "tmax_mean": 30.0}
                      for y in years for m in range(1, 13)]).to_csv(tmp_path / name, index=False)
    qc = tmp_path / "qc_reviewed.csv"
    pd.DataFrame(columns=["level", "region_id", "region_name", "year", "variable", "ratio", "disposition",
                          "reason", "evidence"]).to_csv(qc, index=False)
    pd.DataFrame([{"region_id": "S", "year": y, "month": m, "rain_mm": j / 4}
                  for y, j in zip(years, jjas) for m in (6, 7, 8, 9)]).to_csv(tmp_path / "power_state_month.csv", index=False)
    pd.read_csv(v.REF / "noaa_enso_episodes.csv").assign(
        end_season="DJF", end_year=2000, n_seasons=5, peak_anom=1.0, intensity="weak", provisional=False,
        ongoing=False, episode_id=range(1, len(pd.read_csv(v.REF / "noaa_enso_episodes.csv")) + 1),
    ).to_csv(tmp_path / "enso_episodes.csv", index=False)
    monkeypatch.setattr(v.mf, "read", lambda: [])
    pd.DataFrame(columns=["year", "ilat", "ilon", "lat", "lon", "annual_mm", "base_median_mm", "ratio"]).to_csv(
        tmp_path / "qc_rain_nearzero_cells.csv", index=False)
    pd.DataFrame(columns=["level", "region_id", "region_name", "year", "flagged_share", "n_flagged_cells",
                          "est_bias_pct"]).to_csv(tmp_path / "qc_rain_nearzero_regions.csv", index=False)
    (tmp_path / "_parts").mkdir()
    pd.DataFrame({"region_id": ["D"], "ilat": [0], "ilon": [0], "area_km2": [10.0], "weight": [1.0]}).to_csv(
        tmp_path / "_parts" / "weights_r025_district.csv", index=False)
    smap = tmp_path / "map.csv"
    pd.DataFrame({"region_id": ["D"], "district_name": ["Dname"], "state_name": ["S"],
                  "imd_subdivision": ["Tamil Nadu"]}).to_csv(smap, index=False)
    simd = tmp_path / "sub.csv"
    pd.DataFrame({"SUBDIVISION": "Tamil Nadu", "YEAR": years, "JJAS": jjas * 0.9}).to_csv(simd, index=False)
    res = v.run_all(tmp_path, qc_reviewed=qc, expected={"country": 1, "state": 1, "district": 1, "subdivisions": 1},
                    imd_subdivisions=simd, subdivision_map=smap, subdivision_reviewed=tmp_path / "none.csv")
    names = {r.name: r for r in res}
    assert names["nearzero_reviewed"].passed and names["subdivision_jjas"].passed
    assert "median r=1.000" in names["subdivision_jjas"].detail
    assert [r.name for r in res if r.name.startswith("completeness")] == [
        "completeness_country", "completeness_state", "completeness_district"]
    assert all(r.passed for r in res if r.name.startswith(("completeness", "qc_"))), [v.format_result(r) for r in res]
    text = (tmp_path / "validation_report.md").read_text(encoding="utf-8")
    assert "| power_vs_imd (diagnostic) | DIAG |" in text
    assert "| qc_plausibility | PASS |" in text
    assert "outlier state-years" in text
    assert "## NASA POWER cross-check (diagnostic, not a gate)" in text
    assert "| region_id | region_name | r | n_years |" in text
    assert "| S | Sname |" in text
    assert "## IMD sub-divisional rainfall check (gate subdivision_jjas)" in text
    assert not any(r.name.startswith("outcome_") for r in res)          # no outcome panels -> no outcome gates
    (tmp_path / "outcomes").mkdir()                                     # directory without records: FAIL
    res = v.run_all(tmp_path, qc_reviewed=qc, expected={"country": 1, "state": 1, "district": 1, "subdivisions": 1},
                    imd_subdivisions=simd, subdivision_map=smap, subdivision_reviewed=tmp_path / "none.csv")
    bad = [r for r in res if r.name == "outcome_records"]
    assert len(bad) == 1 and not bad[0].passed and "outcome_records_all.csv.gz" in bad[0].detail
    (tmp_path / "outcomes" / "outcome_records_all.csv.gz").write_bytes(b"")
    from pipeline.outcomes import gates as og
    seen = {}
    monkeypatch.setattr(og, "run_outcome_gates",
                        lambda d, reviewed_path: seen.update(d=d, rev=reviewed_path) or [v.GateResult("outcome_x", False, "dx")])
    res = v.run_all(tmp_path, qc_reviewed=qc, expected={"country": 1, "state": 1, "district": 1, "subdivisions": 1},
                    imd_subdivisions=simd, subdivision_map=smap, subdivision_reviewed=tmp_path / "none.csv",
                    outcomes_reviewed=tmp_path / "orev.csv")
    assert [r.name for r in res][-1] == "outcome_x" and seen == {"d": tmp_path / "outcomes", "rev": tmp_path / "orev.csv"}
    assert "| outcome_x | FAIL | dx |" in (tmp_path / "validation_report.md").read_text(encoding="utf-8")
    assert "| Tamil Nadu | 37 | 1.000 | 1.11 |  |" in text
    assert "| Tamil Nadu | 2011 |" in text


def test_power_outliers_lists_state_years_outside_ratio_band():
    imd, pw = _power_fixture(r_noise=5)
    imd.loc[imd.year == 2001, "rain_jjas_mm"] *= 3              # IMD 3x POWER
    o = v.power_outliers(imd, pw)
    assert o.year.tolist() == [2001] and o.region_name.tolist() == ["Sname"]
    assert o.columns.tolist() == ["region_id", "region_name", "year", "imd_jjas_mm", "power_jjas_mm", "ratio"]
    assert o.ratio.item() == pytest.approx(3.0, rel=0.05)


def test_format_result_labels_diagnostic():
    assert v.format_result(v.GateResult("power_vs_imd", True, "x")).startswith("DIAG power_vs_imd")
    assert v.format_result(v.GateResult("power_vs_imd", False, "x")).startswith("FAIL power_vs_imd")
    assert v.format_result(v.GateResult("blocklist", True, "x")).startswith("PASS blocklist")


def _rev_rows(rows):
    cols = ["level", "region_id", "region_name", "year", "variable", "ratio", "disposition", "reason", "evidence"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)


def test_nearzero_gate_requires_every_listed_region_year_reviewed():
    regions = pd.DataFrame({"level": ["district", "state"], "region_id": ["D1", "S1"], "region_name": ["d", "s"],
                            "year": [1999, 2001], "flagged_share": [0.4, 0.12], "n_flagged_cells": [3, 9],
                            "est_bias_pct": [-30.0, -8.0]})
    rev = _rev_rows([("district", "D1", "d", 1999, "rain_annual_mm", 0.5, "mask", "fill", "e"),
                     ("district", "D1", "d", 1999, "rain_jjas_mm", 0.5, "mask", "fill", "e")])
    g = v.gate_nearzero_reviewed(regions, rev, n_cells=12)
    assert not g.passed and g.name == "nearzero_reviewed"
    assert "unreviewed: state S1 2001" in g.detail and "cells flagged=12" in g.detail
    rev2 = pd.concat([rev, _rev_rows([("state", "S1", "s", 2001, "rain_annual_mm", 0.9, "keep", "genuine", "e")])])
    g_noref = v.gate_nearzero_reviewed(regions, rev2, n_cells=12)
    assert not g_noref.passed and "evidence without near-zero reference: district D1 1999; state S1 2001" in g_noref.detail
    rev2 = rev2.assign(evidence="cells at 8 mm (nearzero diagnostic)")
    g2 = v.gate_nearzero_reviewed(regions, rev2, n_cells=12)
    assert g2.passed and "region-years=2" in g2.detail and "keep=1 mask=1" in g2.detail
    # a reviewed row for another year does not count
    rev3 = rev2.assign(year=[1999, 1999, 2002])
    assert not v.gate_nearzero_reviewed(regions, rev3, n_cells=12).passed


def test_nearzero_gate_passes_when_nothing_listed():
    empty = pd.DataFrame(columns=["level", "region_id", "region_name", "year", "flagged_share", "n_flagged_cells",
                                  "est_bias_pct"])
    assert v.gate_nearzero_reviewed(empty, _rev_rows([]), n_cells=0).passed


def _subtable(rs):
    return pd.DataFrame({"subdivision": list(rs), "n_years": 37, "first_year": 1981, "last_year": 2017,
                         "r": list(rs.values()), "mean_ratio": 1.0})


def test_subdivision_gate_fails_on_low_r_unless_reviewed():
    t = _subtable({"A": 0.95, "B": 0.6, "C": 0.85})
    empty = pd.DataFrame(columns=["subdivision", "reason", "evidence"])
    g = v.gate_subdivision_jjas(t, empty)
    assert not g.passed and g.name == "subdivision_jjas"
    assert "subdivisions=3" in g.detail and "median r=0.850" in g.detail and "min r=0.600 (B)" in g.detail
    assert "unreviewed r<0.7: B" in g.detail
    rev = pd.DataFrame({"subdivision": ["B"], "reason": ["sparse"], "evidence": ["e"]})
    g2 = v.gate_subdivision_jjas(t, rev)
    assert g2.passed and "reviewed exceptions: B" in g2.detail
    assert not v.gate_subdivision_jjas(t.iloc[0:0], rev).passed


def _prop_fixture():
    rev = _rev_rows([("district", "D1", "d", 2011, "rain_jjas_mm", 4.0, "mask", "r", "e"),
                     ("district", "D2", "d", 2011, "rain_annual_mm", 4.0, "mask", "r", "e"),
                     ("district", "D3", "d", 2005, "rain_jjas_mm", 4.0, "keep", "r", "e")])
    prop = pd.DataFrame({"level": ["state", "state", "country", "country"], "region_id": ["S1", "S2", "IND", "IND"],
                         "year": 2011, "variable": ["rain_jjas_mm", "rain_annual_mm", "rain_annual_mm", "rain_jjas_mm"],
                         "action": ["infilled", "masked", "infilled", "infilled"], "n_masked_districts": 1,
                         "reviewed_mask": False})
    tables = {"state": pd.DataFrame({"region_id": ["S1", "S2"], "year": 2011, "rain_jjas_mm": [500.0, 400.0],
                                     "rain_annual_mm": [900.0, np.nan],
                                     "qc_masked": ["district_masks_infilled:rain_jjas_mm",
                                                   "rain_annual_mm;district_masks_masked:rain_annual_mm"]}),
              "country": pd.DataFrame({"region_id": ["IND"], "year": [2011], "rain_jjas_mm": [850.0],
                                       "rain_annual_mm": [1100.0],
                                       "qc_masked": ["district_masks_infilled:rain_annual_mm;rain_jjas_mm"]})}
    return rev, prop, tables, {"D1": "S1", "D2": "S2", "D3": "S1"}


def test_district_mask_propagation_gate_passes_when_every_parent_is_infilled_or_masked():
    rev, prop, tables, ds = _prop_fixture()
    g = v.gate_district_mask_propagation(rev, prop, tables, ds)
    assert g.passed and g.name == "district_mask_propagation", g.detail
    assert "state: infilled=1 masked=1" in g.detail and "country: infilled=2" in g.detail


def test_district_mask_propagation_gate_fails_when_missing_or_not_applied():
    rev, prop, tables, ds = _prop_fixture()
    g = v.gate_district_mask_propagation(rev, prop[prop.region_id != "S1"], tables, ds)
    assert not g.passed and "not propagated: state S1 2011 rain_jjas_mm" in g.detail
    t2 = {k: d.copy() for k, d in tables.items()}
    t2["state"].loc[t2["state"].region_id == "S2", "rain_annual_mm"] = 950.0       # "masked" but has a value
    g2 = v.gate_district_mask_propagation(rev, prop, t2, ds)
    assert not g2.passed and "not applied: state S2 2011 rain_annual_mm" in g2.detail
    t3 = {k: d.copy() for k, d in tables.items()}
    t3["state"].loc[t3["state"].region_id == "S1", "qc_masked"] = ""                 # infilled but untagged
    assert not v.gate_district_mask_propagation(rev, prop, t3, ds).passed


def test_subdivision_gate_checks_names_and_expected_count():
    t = _subtable({"A": 0.95, "B": 0.9, "C": 0.85})
    empty = pd.DataFrame(columns=["subdivision", "reason", "evidence"])
    assert v.gate_subdivision_jjas(t, empty, mapped=["A", "B", "C"], imd_names=["A", "B", "C", "D"], expected=3).passed
    g = v.gate_subdivision_jjas(t, empty, mapped=["A", "B", "C", "X"], imd_names=["A", "B", "C"], expected=3)
    assert not g.passed and "mapped subdivisions not in IMD file: X" in g.detail
    g2 = v.gate_subdivision_jjas(t, empty, mapped=["A", "B", "C"], imd_names=["A", "B", "C"], expected=4)
    assert not g2.passed and "compared 3 != expected 4" in g2.detail


def test_subdivision_check_missing_imd_file_is_a_fail_result(tmp_path):
    g, *_ = v.subdivision_check(tmp_path, tmp_path / "missing.csv", tmp_path / "map.csv", tmp_path / "rev.csv",
                                expected_districts=1)
    assert not g.passed and g.name == "subdivision_jjas" and "missing" in g.detail


def test_climate_unit_year_gate():
    units = ["OD", "GJ"]
    ok = pd.DataFrame([{"unit_id": u, "year": y, "rain_jjas_mm": 1.0} for u in units for y in range(1981, 1991)])
    r = v.gate_climate_unit_year(ok, units)
    assert r.name == "climate_unit_year" and r.passed and "1981-1990" in r.detail
    assert not v.gate_climate_unit_year(ok, units + ["KL"]).passed                       # unit absent
    assert not v.gate_climate_unit_year(ok, ["OD"]).passed                               # unexpected unit
    assert not v.gate_climate_unit_year(ok[ok.year != 1985], units).passed               # gap
    assert not v.gate_climate_unit_year(ok[ok.year != 1981], units).passed               # must start 1981
    assert not v.gate_climate_unit_year(ok[~((ok.unit_id == "GJ") & (ok.year == 1990))], units).passed
    assert not v.gate_climate_unit_year(pd.concat([ok, ok.head(1)]), units).passed       # duplicate key


def test_run_all_climate_unit_year_gate_missing_file_fails(tmp_path):
    r = v.climate_unit_year_check(tmp_path)
    assert r.name == "climate_unit_year" and not r.passed and "climate_unit_year.csv" in r.detail
