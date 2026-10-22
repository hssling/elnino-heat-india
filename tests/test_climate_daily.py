import numpy as np
import pytest

from pipeline import climate_daily as cd


def test_month_index_and_doy366_for_leap_and_non_leap():
    assert np.bincount(cd.month_index(2024)).tolist()[:3] == [31, 29, 31]
    idx = cd.doy366_index(2023)
    assert len(idx) == 365 and 59 not in idx and idx[59] == 60
    assert cd.doy366_index(2024).tolist() == list(range(366))


def test_daily_to_monthly_sum_and_mean():
    d = np.ones((366, 2, 2))
    s = cd.daily_to_monthly(d, 2024, "sum")
    assert s.shape == (12, 2, 2) and s[1, 0, 0] == 29 and s[2, 0, 0] == 31
    assert np.all(cd.daily_to_monthly(d, 2024, "mean") == 1)


def test_daily_to_monthly_mean_ignores_nan():
    d = np.ones((365, 1))
    d[0, 0] = np.nan
    assert cd.daily_to_monthly(d, 2023, "mean")[0, 0] == 1.0


def test_monthly_counts():
    m = np.zeros((365, 1), dtype=bool)
    m[[0, 1, 40]] = True
    assert cd.monthly_counts(m, 2023)[:2, 0].tolist() == [2, 1]


def test_climatology_constant_and_shape():
    clim = cd.tmax_climatology({2020: np.full((366, 2, 2), 38.0), 2021: np.full((365, 2, 2), 38.0)})
    assert clim.shape == (366, 2, 2) and np.allclose(clim, 38.0)


def test_heatwave_mask_rules():
    clim = np.full((366, 1, 4), 38.0)
    t = np.zeros((365, 1, 4))
    t[100] = [41.0, 43.0, 45.5, 39.0]
    hw = cd.heatwave_mask(t, 2023, clim)
    assert hw[100, 0].tolist() == [False, True, True, False]


def test_onset_simple_and_false_onset():
    r = np.zeros(365)
    r[155:] = 6.0                      # from 5 June 2023 (index 155)
    assert cd.onset_doy(r, 2023) == 156
    r2 = np.zeros(365)
    r2[129:131] = 15.0                 # 30 mm burst 10-11 May, then dry
    r2[160:] = 6.0                     # real rains from 10 June (index 160)
    assert cd.onset_doy(r2, 2023) == 161
    assert np.isnan(cd.onset_doy(np.zeros(365), 2023))


def test_daily_to_monthly_mean_all_nan_cell_is_nan_without_warning():
    import warnings
    daily = np.ones((365, 2, 1))
    daily[:, 1, 0] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = cd.daily_to_monthly(daily, 2023, "mean")
    assert np.all(out[:, 0, 0] == 1.0) and np.all(np.isnan(out[:, 1, 0]))
