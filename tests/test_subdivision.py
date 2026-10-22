import numpy as np
import pandas as pd
import pytest

from pipeline import subdivision as sd


def test_read_imd_subdivisions_long_jjas(tmp_path):
    p = tmp_path / "sub.csv"
    pd.DataFrame({"SUBDIVISION": ["A", "A", "B"], "YEAR": [2000, 2001, 2000], "JUN": 1.0,
                  "JJAS": [500.0, np.nan, 300.0], "ANNUAL": 900.0}).to_csv(p, index=False)
    s = sd.read_imd_subdivisions(p)
    assert s.columns.tolist() == ["subdivision", "year", "imd_jjas_mm"]
    assert s.values.tolist() == [["A", 2000, 500.0], ["B", 2000, 300.0]]       # NA rows dropped


def _mapping(tmp_path, rows):
    p = tmp_path / "map.csv"
    pd.DataFrame(rows, columns=["region_id", "district_name", "state_name", "imd_subdivision"]).to_csv(p, index=False)
    return p


def test_read_mapping_validates_rows(tmp_path):
    good = _mapping(tmp_path, [("D1", "a", "S", "A"), ("D2", "b", "S", "B")])
    assert len(sd.read_mapping(good, expected=2)) == 2
    with pytest.raises(ValueError, match="expected 3"):
        sd.read_mapping(good, expected=3)
    dup = _mapping(tmp_path, [("D1", "a", "S", "A"), ("D1", "b", "S", "B")])
    with pytest.raises(ValueError, match="duplicate"):
        sd.read_mapping(dup, expected=2)
    blank = _mapping(tmp_path, [("D1", "a", "S", "A"), ("D2", "b", "S", None)])
    with pytest.raises(ValueError, match="no subdivision"):
        sd.read_mapping(blank, expected=2)


def test_aggregate_area_weighted_and_min_area():
    dy = pd.DataFrame({"region_id": ["D1", "D2", "D3", "D1", "D2", "D3"], "year": [2000] * 3 + [2001] * 3,
                       "rain_jjas_mm": [100.0, 400.0, 50.0, np.nan, 200.0, 60.0]})
    mapping = pd.DataFrame({"region_id": ["D1", "D2", "D3"], "imd_subdivision": ["A", "A", "B"]})
    areas = pd.Series({"D1": 3.0, "D2": 1.0, "D3": 2.0})
    a = sd.aggregate(dy, mapping, areas, min_area_frac=0.5).set_index(["subdivision", "year"])
    assert a.loc[("A", 2000), "ours_mm"] == pytest.approx((3 * 100 + 400) / 4)
    assert a.loc[("A", 2000), "area_frac"] == 1.0
    assert ("A", 2001) not in a.index                       # only 25% of A's area has data in 2001
    assert a.loc[("B", 2001), "ours_mm"] == 60.0
    b = sd.aggregate(dy, mapping, areas, min_area_frac=0.2).set_index(["subdivision", "year"])
    assert b.loc[("A", 2001), "ours_mm"] == 200.0 and b.loc[("A", 2001), "area_frac"] == 0.25


def test_compare_per_subdivision_r_and_mean_ratio():
    years = list(range(1981, 2018))
    rng = np.random.default_rng(0)
    x = 500 + rng.normal(0, 80, len(years))
    ours = pd.DataFrame({"subdivision": "A", "year": years, "ours_mm": 1.1 * x, "area_frac": 1.0})
    imd = pd.DataFrame({"subdivision": "A", "year": years + [2018], "imd_jjas_mm": list(x) + [1.0]})
    t = sd.compare(ours, imd)
    assert t.columns.tolist() == ["subdivision", "n_years", "first_year", "last_year", "r", "mean_ratio"]
    row = t.iloc[0]
    assert row.n_years == 37 and row.first_year == 1981 and row.last_year == 2017
    assert row.r == pytest.approx(1.0) and row.mean_ratio == pytest.approx(1.1)
    assert sd.compare(ours[ours.year < 1986], imd).empty             # < min_years overlap


def test_read_reviewed_requires_reason(tmp_path):
    p = tmp_path / "rev.csv"
    pd.DataFrame({"subdivision": ["A"], "reason": ["sparse"], "evidence": ["e"]}).to_csv(p, index=False)
    assert sd.read_reviewed(p).subdivision.tolist() == ["A"]
    pd.DataFrame({"subdivision": ["A"], "reason": [None], "evidence": ["e"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="reason"):
        sd.read_reviewed(p)
    assert sd.read_reviewed(tmp_path / "missing.csv").empty
