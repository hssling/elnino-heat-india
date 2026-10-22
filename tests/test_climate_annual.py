import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pipeline import climate_annual as ca


def monthly_series(values, start="1981-01"):
    return pd.Series(values, index=pd.period_range(start, periods=len(values), freq="M"))


def test_spi_is_standard_normal_in_base_period():
    rng = np.random.default_rng(1)
    s = monthly_series(rng.gamma(2.0, 50.0, size=12 * 30))
    z = ca.spi(s, scale=1)
    assert abs(z.mean()) < 0.15 and abs(z.std() - 1) < 0.15


def test_spi_handles_zero_months_and_short_base():
    v = np.where(np.arange(12 * 30) % 12 < 3, 0.0, 100.0 + np.arange(12 * 30) % 7)
    z = ca.spi(monthly_series(v), scale=1)
    assert np.isfinite(z[z.index.month == 6]).all()
    assert z[z.index.month == 1].isna().all()   # January always zero → no fit → NaN
    short = ca.spi(monthly_series(np.full(24, 50.0)), scale=1)
    assert short.isna().all()


def make_month(years, jjas_rain_by_year):
    rows = []
    for y in years:
        for m in range(1, 13):
            rain = jjas_rain_by_year.get(y, 100.0) if m in (6, 7, 8, 9) else 10.0
            rows.append(dict(region_id="R", year=y, month=m, rain_mm=rain, tmax_mean=35.0 + (m in (3, 4, 5, 6)),
                             tmin_mean=20.0, tmax_ge40_days=1.0, heatwave_days=0.5))
    return pd.DataFrame(rows)


def test_build_annual_departure_and_totals():
    years = list(range(1981, 2013))
    month = make_month(years, {2012: 50.0})
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    a = ca.build_annual(month, onset).set_index("year")
    assert a.loc[2012, "rain_jjas_mm"] == 200.0
    assert a.loc[1990, "rain_jjas_normal_mm"] == 400.0
    assert a.loc[2012, "rain_jjas_dep_pct"] == pytest.approx(-50.0)
    assert a.loc[2012, "rain_annual_mm"] == 200.0 + 80.0
    assert a.loc[2012, "tmax_ge40_days"] == 12.0 and a.loc[2012, "tmax_mamj_anom"] == 0.0
    assert a.loc[2012, "onset_anom_days"] == 0.0


def random_month(years, seed, region="R"):
    rng = np.random.default_rng(seed)
    rows = []
    for y in years:
        for m in range(1, 13):
            rows.append(dict(region_id=region, year=y, month=m, rain_mm=float(rng.gamma(2.0, 50.0)),
                             tmax_mean=35.0, tmin_mean=20.0, tmax_ge40_days=1.0, heatwave_days=0.5))
    return pd.DataFrame(rows)


def test_build_annual_rejects_duplicate_region_months():
    years = list(range(1981, 2013))
    month = make_month(years, {})
    dup = pd.concat([month, month.iloc[[5]]], ignore_index=True)
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    with pytest.raises(ValueError, match="duplicate"):
        ca.build_annual(dup, onset)


def test_build_annual_missing_month_does_not_shift_spi_windows():
    years = list(range(1981, 2013))
    full = random_month(years, seed=3)
    gap = full[~((full.year == 1990) & (full.month == 8))]   # Aug 1990 absent, inside base period
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    a = ca.build_annual(gap, onset).set_index("year")
    values = full.sort_values(["year", "month"]).rain_mm.to_numpy().copy()
    values[(1990 - 1981) * 12 + 7] = np.nan              # same gap as explicit NaN
    s = monthly_series(values)
    s3, s12 = ca.spi(s, 3), ca.spi(s, 12)
    assert s3.loc[pd.Period("1990-08", "M")] != s3.loc[pd.Period("1990-08", "M")]   # NaN window
    assert s3.loc[pd.Period("1990-09", "M")] != s3.loc[pd.Period("1990-09", "M")]
    assert 1990 not in a.index                            # year with missing month is skipped
    assert a.loc[2000, "spi3_sep"] == pytest.approx(s3.loc[pd.Period("2000-09", "M")], rel=1e-9)
    assert a.loc[2000, "spi12_dec"] == pytest.approx(s12.loc[pd.Period("2000-12", "M")], rel=1e-9)


def test_spi_zero_accumulation_uses_centre_of_mass_position():
    v = np.full(30 * 12, 100.0)
    years = np.arange(1981, 2011)
    zero_years = years[years % 5 == 0]                    # 6 of 30 base Januaries are zero, q = 0.2
    for i, y in enumerate(years):
        v[i * 12] = 0.0 if y in zero_years else 50.0 + y
    z = ca.spi(monthly_series(v), scale=1)
    zero_spi = z.loc[pd.Period("1985-01", "M")]
    assert zero_spi == pytest.approx(stats.norm.ppf(0.1))             # H(0) = q/2
    pos = [z.loc[pd.Period(f"{y}-01", "M")] for y in years if y not in zero_years]
    assert zero_spi < min(pos)


def test_build_annual_spi_selection_matches_spi_series():
    years = list(range(1981, 2013))
    month = random_month(years, seed=5)
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    a = ca.build_annual(month, onset).set_index("year")
    s = monthly_series(month.sort_values(["year", "month"]).rain_mm.to_numpy())
    s3, s12 = ca.spi(s, 3), ca.spi(s, 12)
    for y in (1995, 2012):
        assert a.loc[y, "spi3_sep"] == pytest.approx(s3.loc[pd.Period(f"{y}-09", "M")], rel=1e-9)
        assert a.loc[y, "spi12_dec"] == pytest.approx(s12.loc[pd.Period(f"{y}-12", "M")], rel=1e-9)


def test_build_annual_seasonal_means_nan_when_a_month_value_is_missing():
    years = list(range(1981, 2013))
    month = make_month(years, {})
    month.loc[(month.year == 2005) & (month.month == 4), "tmax_mean"] = np.nan
    month.loc[(month.year == 2005) & (month.month == 11), "tmin_mean"] = np.nan
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    a = ca.build_annual(month, onset).set_index("year")
    assert np.isnan(a.loc[2005, "tmax_mamj_mean"])
    assert np.isnan(a.loc[2005, "tmin_mean"])
    assert a.loc[2004, "tmax_mamj_mean"] == 36.0


def test_build_annual_applies_qc_masks_before_normals():
    years = list(range(1981, 2013))
    month = make_month(years, {1990: 1000.0, 2012: 50.0})      # 1990 JJAS = 4000 mm artefact in base period
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    mask = pd.DataFrame({"region_id": ["R", "R"], "year": [1990, 2012],
                         "variable": ["rain_jjas_mm", "rain_annual_mm"]})
    a = ca.build_annual(month, onset, qc_mask=mask).set_index("year")
    # masked JJAS and its dependants are NaN; the annual total of that year is untouched
    for col in ("rain_jjas_mm", "rain_jjas_dep_pct", "spi3_sep", "onset_doy", "onset_anom_days"):
        assert np.isnan(a.loc[1990, col]), col
    assert a.loc[1990, "rain_annual_mm"] == 4000.0 + 80.0
    assert a.loc[1990, "qc_masked"] == "rain_jjas_mm"
    # normal excludes the masked artefact
    assert a.loc[2000, "rain_jjas_normal_mm"] == 400.0
    # masked annual total and SPI-12; JJAS of that year kept
    assert np.isnan(a.loc[2012, "rain_annual_mm"]) and np.isnan(a.loc[2012, "spi12_dec"])
    assert a.loc[2012, "rain_jjas_mm"] == 200.0 and a.loc[2012, "qc_masked"] == "rain_annual_mm"
    assert a.loc[2000, "qc_masked"] == ""


def test_build_annual_rejects_unknown_qc_variable():
    years = list(range(1981, 2013))
    month = make_month(years, {})
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    with pytest.raises(ValueError, match="qc variable"):
        ca.build_annual(month, onset, qc_mask=pd.DataFrame({"region_id": ["R"], "year": [1990], "variable": ["tmax"]}))


def test_qc_mask_for_level_reads_only_mask_dispositions(tmp_path):
    p = tmp_path / "qc_reviewed.csv"
    pd.DataFrame({"level": ["state", "state", "district"], "region_id": ["A", "B", "C"], "region_name": "x",
                  "year": [2011, 2012, 2011], "variable": "rain_jjas_mm", "ratio": 3.0,
                  "disposition": ["mask", "keep", "mask"], "reason": "r", "evidence": "e"}).to_csv(p, index=False)
    m = ca.qc_mask_for_level("state", p)
    assert m[["region_id", "year", "variable"]].values.tolist() == [["A", 2011, "rain_jjas_mm"]]
    with pytest.raises(ValueError, match="disposition"):
        pd.read_csv(p).assign(disposition="drop").to_csv(p, index=False)
        ca.qc_mask_for_level("state", p)


def test_normal_period_constant():
    assert ca.BASE == (1981, 2010) and ca.NORMAL_PERIOD == "1981–2010"


def _series_with_nan(month, region, year, months):
    m = month.sort_values(["year", "month"]).copy()
    m.loc[(m.region_id == region) & (m.year == year) & m.month.isin(months), "rain_mm"] = np.nan
    return monthly_series(m.rain_mm.to_numpy())


def test_build_annual_spi_fits_exclude_annual_masked_months():
    # R22: an annual mask blanks all 12 months of that year in the series fed to spi(),
    # so a near-zero base-period artefact never enters the gamma / zero-probability fits.
    years = list(range(1981, 2013))
    month = random_month(years, seed=7)
    month.loc[month.year == 1995, "rain_mm"] *= 0.01          # near-zero fill in the base period
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    mask = pd.DataFrame({"region_id": ["R"], "year": [1995], "variable": ["rain_annual_mm"]})
    a = ca.build_annual(month, onset, qc_mask=mask).set_index("year")
    s = _series_with_nan(month, "R", 1995, range(1, 13))
    s3, s12 = ca.spi(s, 3), ca.spi(s, 12)
    for y in (2000, 2012):
        assert a.loc[y, "spi12_dec"] == pytest.approx(s12.loc[pd.Period(f"{y}-12", "M")], rel=1e-9)
        assert a.loc[y, "spi3_sep"] == pytest.approx(s3.loc[pd.Period(f"{y}-09", "M")], rel=1e-9)
    unmasked = ca.build_annual(month, onset).set_index("year")
    assert a.loc[2000, "spi12_dec"] != pytest.approx(unmasked.loc[2000, "spi12_dec"], rel=1e-6)
    # totals of other years are unchanged by the SPI blanking
    assert a.loc[2000, "rain_annual_mm"] == unmasked.loc[2000, "rain_annual_mm"]


def test_build_annual_spi_fits_exclude_jjas_masked_months_only():
    years = list(range(1981, 2013))
    month = random_month(years, seed=8)
    month.loc[(month.year == 1990) & month.month.isin([6, 7, 8, 9]), "rain_mm"] *= 20   # JJAS artefact
    onset = pd.DataFrame({"region_id": "R", "year": years, "onset_doy": 152.0})
    mask = pd.DataFrame({"region_id": ["R"], "year": [1990], "variable": ["rain_jjas_mm"]})
    a = ca.build_annual(month, onset, qc_mask=mask).set_index("year")
    s = _series_with_nan(month, "R", 1990, [6, 7, 8, 9])
    s3, s12 = ca.spi(s, 3), ca.spi(s, 12)
    assert a.loc[2005, "spi3_sep"] == pytest.approx(s3.loc[pd.Period("2005-09", "M")], rel=1e-9)
    assert a.loc[2005, "spi12_dec"] == pytest.approx(s12.loc[pd.Period("2005-12", "M")], rel=1e-9)
    # the JJAS mask leaves that year's annual total but its 12-month SPI window contains masked months
    assert np.isfinite(a.loc[1990, "rain_annual_mm"]) and np.isnan(a.loc[1990, "spi12_dec"])


def _month_two_regions():
    rows = [dict(region_id=r, year=y, month=m, rain_mm=10.0 * m, rainy_days=1.0, tmax_mean=30.0)
            for r in ("A", "B") for y in (2011, 2012) for m in range(1, 13)]
    return pd.DataFrame(rows)


def test_mask_months_annual_blanks_12_months_and_jjas_blanks_jun_sep():
    month = _month_two_regions()
    mask = pd.DataFrame({"region_id": ["A", "B"], "year": [2011, 2012],
                         "variable": ["rain_annual_mm", "rain_jjas_mm"]})
    out = ca.mask_months(month, mask)
    assert list(out.index) == list(month.index) and out.columns.tolist() == month.columns.tolist() + ["qc_masked"]
    a11 = out[(out.region_id == "A") & (out.year == 2011)]
    assert a11.rain_mm.isna().all() and a11.rainy_days.isna().all() and a11.qc_masked.all()
    assert (a11.tmax_mean == 30.0).all()                                 # temperature untouched
    b12 = out[(out.region_id == "B") & (out.year == 2012)].set_index("month")
    assert b12.loc[[6, 7, 8, 9], "rain_mm"].isna().all() and b12.loc[[6, 7, 8, 9], "qc_masked"].all()
    assert b12.loc[[1, 5, 10, 12], "rain_mm"].notna().all() and not b12.loc[[1, 5, 10, 12], "qc_masked"].any()
    rest = out[~(((out.region_id == "A") & (out.year == 2011)) | ((out.region_id == "B") & (out.year == 2012)))]
    assert rest.rain_mm.notna().all() and not rest.qc_masked.any()
    assert month.rain_mm.notna().all()                                   # input not modified


def test_mask_months_empty_mask_and_unknown_variable():
    month = _month_two_regions()
    out = ca.mask_months(month, None)
    assert out.rain_mm.notna().all() and not out.qc_masked.any()
    with pytest.raises(ValueError, match="qc variable"):
        ca.mask_months(month, pd.DataFrame({"region_id": ["A"], "year": [2011], "variable": ["tmax"]}))


def test_apply_qc_to_month_reads_reviewed_masks_for_level(tmp_path):
    p = tmp_path / "qc_reviewed.csv"
    pd.DataFrame({"level": ["district", "district", "state"], "region_id": ["A", "B", "A"], "region_name": "x",
                  "year": [2011, 2012, 2012], "variable": ["rain_jjas_mm", "rain_annual_mm", "rain_annual_mm"],
                  "ratio": 3.0, "disposition": ["mask", "keep", "mask"], "reason": "r", "evidence": "e"}).to_csv(p, index=False)
    out = ca.apply_qc_to_month(_month_two_regions(), "district", p)
    assert out.qc_masked.sum() == 4                                      # A 2011 Jun-Sep only (B is "keep")
    assert set(out[out.qc_masked].month) == {6, 7, 8, 9} and set(out[out.qc_masked].region_id) == {"A"}
    pd.DataFrame(columns=["level", "region_id", "year", "month", "action", "rain_mm", "masked_share",
                          "rest_area_km2"]).to_csv(tmp_path / "qc_month_adjustments.csv", index=False)
    assert ca.apply_qc_to_month(_month_two_regions(), "state", p, derived=tmp_path).qc_masked.sum() == 12


def test_read_qc_reviewed_rejects_duplicate_keys(tmp_path):
    p = tmp_path / "qc_reviewed.csv"
    rows = pd.DataFrame({"level": ["state", "state", "state"], "region_id": ["A", "A", "A"], "region_name": "x",
                         "year": [2011, 2011, 2012], "variable": ["rain_jjas_mm", "rain_annual_mm", "rain_jjas_mm"],
                         "ratio": 3.0, "disposition": ["mask", "mask", "keep"], "reason": "r", "evidence": "e"})
    rows.to_csv(p, index=False)
    assert len(ca.read_qc_reviewed(p)) == 3                              # same region-year, different variable: ok
    pd.concat([rows, rows.iloc[[2]].assign(disposition="mask")]).to_csv(p, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        ca.read_qc_reviewed(p)


def _country_fixture(tmp_path):
    """1x3 grid (cells c0, c1, c2) of equal area; district A = c0, B = c1 + c2; country = all three.
    Base years 2009-2010: c0 10 mm/month, c1 and c2 30 mm/month (the climatology)."""
    grids = tmp_path / "grids"
    grids.mkdir()
    for y in (2009, 2010, 2011, 2012):
        f = np.zeros((12, 1, 3))
        f[:, 0, 0] = {2011: 300.0, 2012: 20.0}.get(y, 10.0)    # A: artefact in 2011
        f[:, 0, 1] = 60.0 if y in (2011, 2012) else 30.0       # rest of the country at 2x normal
        f[:, 0, 2] = np.nan if y == 2012 else f[:, 0, 1]       # c2 missing in 2012
        np.savez_compressed(grids / f"rain_monthly_{y}.npz", rain=f.astype(np.float32))
    cw = pd.DataFrame({"region_id": "IND", "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0, "weight": 1 / 3})
    dw = pd.DataFrame({"region_id": ["A", "B", "B"], "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0,
                       "weight": [1.0, 0.5, 0.5]})
    month = pd.DataFrame([{"region_id": "IND", "year": y, "month": m, "rain_mm": 99.0, "rainy_days": 1.0}
                          for y in (2011, 2012) for m in range(1, 13)])
    return grids, cw, dw, month


def test_monthly_climatology_from_base_years(tmp_path):
    grids, *_ = _country_fixture(tmp_path)
    clim = ca.monthly_climatology(grids, base=(2009, 2010))
    assert clim.shape == (12, 1, 3) and clim[6, 0, 0] == pytest.approx(10.0) and clim[6, 0, 2] == pytest.approx(30.0)
    with pytest.raises(FileNotFoundError):
        ca.monthly_climatology(grids, base=(1981, 1990))


IND = {"A": "IND", "B": "IND"}


def _infill(month, mask, grids, cw, dw, region=IND, **kw):
    clim = ca.monthly_climatology(grids, base=(2009, 2010))
    kw.setdefault("min_rest_km2", 0.0)
    return ca.infill_masked_districts(month, mask, grids, cw, dw, clim, region, **kw)


def test_infill_masked_districts_at_rest_of_region_ratio_to_normal(tmp_path):
    grids, cw, dw, month = _country_fixture(tmp_path)
    mask = pd.DataFrame({"region_id": ["A"], "year": [2011], "variable": ["rain_jjas_mm"]})
    out, adj, summ = _infill(month, mask, grids, cw, dw)
    o = out.set_index(["year", "month"])
    # rest (c1, c2) = 60 mm = 2x its normal 30; A's cell takes 2x its normal 10 = 20: (20 + 60 + 60) / 3
    assert o.loc[(2011, 7), "rain_mm"] == pytest.approx(140.0 / 3)
    assert np.isnan(o.loc[(2011, 7), "rainy_days"])                     # cannot be infilled
    assert o.loc[(2011, 1), "rain_mm"] == 99.0 and o.loc[(2011, 1), "rainy_days"] == 1.0
    assert o.loc[(2012, 7), "rain_mm"] == 99.0                          # unmasked year untouched
    assert month.rain_mm.eq(99.0).all()
    assert sorted(adj.month) == [6, 7, 8, 9] and set(adj.action) == {"infilled"}
    assert adj.columns.tolist() == ["region_id", "year", "month", "action", "rain_mm", "masked_share", "rest_area_km2"]
    assert adj.masked_share.iloc[0] == pytest.approx(1 / 3) and adj.rest_area_km2.iloc[0] == pytest.approx(20.0)
    assert summ.values.tolist() == [["IND", 2011, "rain_jjas_mm", "infilled", 1]]
    assert summ.columns.tolist() == ["region_id", "year", "variable", "action", "n_masked_districts"]


def test_infill_masked_districts_annual_mask_with_missing_cells(tmp_path):
    grids, cw, dw, month = _country_fixture(tmp_path)
    mask = pd.DataFrame({"region_id": ["A"], "year": [2012], "variable": ["rain_annual_mm"]})
    out, adj, summ = _infill(month, mask, grids, cw, dw)
    o = out.set_index(["year", "month"])
    # valid cells c0, c1 (c2 missing); rest = c1 at 60 = 2x normal -> c0 infilled at 20: (20 + 60) / 2
    assert all(o.loc[(2012, m), "rain_mm"] == pytest.approx(40.0) for m in range(1, 13))
    assert summ.action.tolist() == ["infilled"] and len(adj) == 12


def test_infill_masks_region_when_masked_share_above_half(tmp_path):
    grids, cw, dw, month = _country_fixture(tmp_path)
    mask = pd.DataFrame({"region_id": ["B"], "year": [2011], "variable": ["rain_annual_mm"]})   # B = 2/3 of area
    out, adj, summ = _infill(month, mask, grids, cw, dw)
    o = out.set_index(["year", "month"])
    assert all(np.isnan(o.loc[(2011, m), "rain_mm"]) for m in range(1, 13))
    assert summ.action.tolist() == ["masked"] and set(adj.action) == {"masked"}


def test_infill_masks_region_when_unmasked_remainder_is_small(tmp_path):
    grids, cw, dw, month = _country_fixture(tmp_path)
    mask = pd.DataFrame({"region_id": ["A"], "year": [2011], "variable": ["rain_jjas_mm"]})
    out, adj, summ = _infill(month, mask, grids, cw, dw, min_rest_km2=25.0)     # rest is 20 km2
    o = out.set_index(["year", "month"])
    assert all(np.isnan(o.loc[(2011, m), "rain_mm"]) for m in (6, 7, 8, 9))
    assert o.loc[(2011, 5), "rain_mm"] == 99.0
    assert summ.action.tolist() == ["masked"]


def test_infill_skips_districts_without_valid_cells(tmp_path):
    grids, cw, dw, month = _country_fixture(tmp_path)
    dw = pd.concat([dw, pd.DataFrame({"region_id": ["Z"], "ilat": [0], "ilon": [2], "area_km2": [0.0],
                                      "weight": [1.0]})])
    mask = pd.DataFrame({"region_id": ["Z", "Q"], "year": [2012, 2012], "variable": "rain_annual_mm"})
    out, adj, summ = _infill(month, mask, grids, cw, dw, region={"Z": "IND", "Q": "IND"})
    assert out.rain_mm.eq(99.0).all() and adj.empty
    assert summ.values.tolist() == [["IND", 2012, "rain_annual_mm", "no_valid_cells", 2]]


def test_infill_state_level_uses_rest_of_state_only(tmp_path):
    grids, _, _, _ = _country_fixture(tmp_path)
    clim = ca.monthly_climatology(grids, base=(2009, 2010))
    sw = pd.DataFrame({"region_id": ["S1", "S1", "S2"], "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0,
                       "weight": [0.5, 0.5, 1.0]})
    dw = pd.DataFrame({"region_id": ["A", "B", "C"], "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0, "weight": 1.0})
    month = pd.DataFrame([{"region_id": r, "year": 2011, "month": m, "rain_mm": 99.0, "rainy_days": 1.0}
                          for r in ("S1", "S2") for m in range(1, 13)])
    mask = pd.DataFrame({"region_id": ["A"], "year": [2011], "variable": ["rain_jjas_mm"]})
    out, adj, summ = ca.infill_masked_districts(month, mask, grids, sw, dw, clim, {"A": "S1", "B": "S1", "C": "S2"},
                                                max_share=0.6, min_rest_km2=0.0)
    o = out.set_index(["region_id", "month"])
    assert o.loc[("S1", 7), "rain_mm"] == pytest.approx(40.0)          # (2 x 10 + 60) / 2
    assert o.loc[("S2", 7), "rain_mm"] == 99.0
    assert summ.values.tolist() == [["S1", 2011, "rain_jjas_mm", "infilled", 1]]
    # default max_share 0.5: A is exactly half of S1 -> still infilled (mask only when > 0.5)
    _, _, s2 = ca.infill_masked_districts(month, mask, grids, sw, dw, clim, {"A": "S1", "B": "S1", "C": "S2"},
                                          min_rest_km2=0.0)
    assert s2.action.tolist() == ["infilled"]


def _write_build_inputs(tmp_path, grids, cw, dw, level, regions):
    parts = tmp_path / "_parts"
    parts.mkdir(exist_ok=True)
    cw.to_csv(parts / f"weights_r025_{level}.csv", index=False)
    dw.to_csv(parts / "weights_r025_district.csv", index=False)
    years = list(range(1981, 2013))
    rows = []
    for rid in regions:
        for y in years:
            for m in range(1, 13):
                rain = 99.0 if (y == 2011 and m in (6, 7, 8, 9)) else 30.0 * (1 + 0.1 * np.sin(y + m))
                rows.append(dict(region_id=rid, region_name=rid, state_id=rid, state_name=rid, year=y,
                                 month=m, rain_mm=rain, rainy_days=1.0, tmax_mean=30.0, tmin_mean=20.0,
                                 tmax_ge40_days=0.0, heatwave_days=0.0))
    pd.DataFrame(rows).to_csv(tmp_path / f"climate_{level}_month.csv", index=False)
    pd.DataFrame([{"region_id": r, "year": y, "onset_doy": 152.0} for r in regions for y in years]).to_csv(
        tmp_path / f"climate_{level}_onset.csv", index=False)
    return parts, years


def _qc(tmp_path, rows):
    qc = tmp_path / "qc.csv"
    pd.DataFrame([dict(level="district", region_id=r, region_name="a", year=y, variable=v, ratio=5.0,
                       disposition="mask", reason="r", evidence="e") for r, y, v in rows],
                 columns=ca.QC_COLUMNS).to_csv(qc, index=False)
    return qc


def test_build_all_country_infills_masked_district_cells(tmp_path):
    grids, cw, dw, _ = _country_fixture(tmp_path)
    parts, _ = _write_build_inputs(tmp_path, grids, cw, dw, "country", ["IND"])
    qc = _qc(tmp_path, [("A", 2011, "rain_jjas_mm")])
    out = ca.build_all(levels=("country",), derived=tmp_path, qc_reviewed=qc, grids_dir=grids, parts_dir=parts,
                       district_state={"A": "S", "B": "S"}, min_rest_km2=0.0)
    c = pd.read_csv(out["country"], keep_default_na=False, na_values=[""]).set_index("year")
    assert c.loc[2011, "rain_jjas_mm"] == pytest.approx(4 * 140.0 / 3)
    assert c.loc[2011, "qc_masked"] == "district_masks_infilled:rain_jjas_mm"
    assert pd.isna(c.loc[2010, "qc_masked"]) or c.loc[2010, "qc_masked"] == ""
    assert c.loc[2010, "rain_jjas_mm"] == pytest.approx(
        sum(30.0 * (1 + 0.1 * np.sin(2010 + m)) for m in (6, 7, 8, 9)))
    summ = pd.read_csv(tmp_path / "qc_district_mask_propagation.csv")
    assert summ[["level", "region_id", "year", "variable", "action"]].values.tolist() == [
        ["country", "IND", 2011, "rain_jjas_mm", "infilled"]]
    adj = pd.read_csv(tmp_path / "qc_month_adjustments.csv")
    assert len(adj) == 4 and set(adj.level) == {"country"}


def test_build_all_state_masks_state_year_when_masked_share_large(tmp_path):
    grids, _, _, _ = _country_fixture(tmp_path)
    sw = pd.DataFrame({"region_id": "S", "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0, "weight": 1 / 3})
    dw = pd.DataFrame({"region_id": ["A", "B", "B"], "ilat": 0, "ilon": [0, 1, 2], "area_km2": 10.0,
                       "weight": [1.0, 0.5, 0.5]})
    parts, _ = _write_build_inputs(tmp_path, grids, sw, dw, "state", ["S"])
    qc = _qc(tmp_path, [("B", 2011, "rain_annual_mm")])                 # B = 2/3 of S
    out = ca.build_all(levels=("state",), derived=tmp_path, qc_reviewed=qc, grids_dir=grids, parts_dir=parts,
                       district_state={"A": "S", "B": "S"}, min_rest_km2=0.0)
    s = pd.read_csv(out["state"], keep_default_na=False, na_values=[""]).set_index("year")
    assert np.isnan(s.loc[2011, "rain_annual_mm"]) and np.isnan(s.loc[2011, "spi12_dec"])
    assert s.loc[2011, "qc_masked"] == "rain_annual_mm;district_masks_masked:rain_annual_mm"
    assert np.isfinite(s.loc[2010, "rain_annual_mm"])


def test_apply_qc_to_month_state_and_country_use_adjustments(tmp_path):
    grids, cw, dw, _ = _country_fixture(tmp_path)
    parts, _ = _write_build_inputs(tmp_path, grids, cw, dw, "country", ["IND"])
    qc = _qc(tmp_path, [("A", 2011, "rain_jjas_mm")])
    ca.build_all(levels=("country",), derived=tmp_path, qc_reviewed=qc, grids_dir=grids, parts_dir=parts,
                 district_state={"A": "S", "B": "S"}, min_rest_km2=0.0)
    month = pd.read_csv(tmp_path / "climate_country_month.csv")
    out = ca.apply_qc_to_month(month, "country", qc, derived=tmp_path).set_index(["year", "month"])
    assert out.loc[(2011, 7), "rain_mm"] == pytest.approx(140.0 / 3) and bool(out.loc[(2011, 7), "qc_infilled"])
    assert np.isnan(out.loc[(2011, 7), "rainy_days"]) and not bool(out.loc[(2011, 7), "qc_masked"])
    assert out.loc[(2011, 5), "rain_mm"] != pytest.approx(140.0 / 3) and not bool(out.loc[(2011, 5), "qc_infilled"])
    with pytest.raises(ValueError, match="level"):
        ca.apply_qc_to_month(month, "block", qc, derived=tmp_path)
    (tmp_path / "qc_month_adjustments.csv").unlink()
    with pytest.raises(FileNotFoundError):
        ca.apply_qc_to_month(month, "country", qc, derived=tmp_path)


def test_apply_qc_to_month_state_masked_rows(tmp_path):
    month = pd.DataFrame([{"region_id": "S", "year": 2011, "month": m, "rain_mm": 50.0, "rainy_days": 2.0}
                          for m in range(1, 13)])
    pd.DataFrame([{"level": "state", "region_id": "S", "year": 2011, "month": m, "action": "masked",
                   "rain_mm": np.nan, "masked_share": 0.7, "rest_area_km2": 500.0} for m in (6, 7, 8, 9)]).to_csv(
        tmp_path / "qc_month_adjustments.csv", index=False)
    qc = _qc(tmp_path, [])
    out = ca.apply_qc_to_month(month, "state", qc, derived=tmp_path).set_index("month")
    assert out.loc[[6, 7, 8, 9], "rain_mm"].isna().all() and out.loc[[6, 7, 8, 9], "qc_masked"].all()
    assert out.loc[[1, 12], "rain_mm"].eq(50.0).all() and not out.loc[[1, 12], "qc_masked"].any()
