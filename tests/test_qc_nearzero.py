import numpy as np
import pandas as pd
import pytest

from pipeline import qc_nearzero as nz

YEARS = list(range(1981, 2013))


def _grids(tmp_path, field_for_year):
    d = tmp_path / "grids"
    d.mkdir()
    for y in YEARS:
        np.savez_compressed(d / f"rain_monthly_{y}.npz", rain=field_for_year(y).astype(np.float32))
    return d


def _field(y):
    """3x2 grid, 12 months. Cell (0,0): 100 mm/month; near-zero fill (0.1 mm/month) in 2005 and 2012.
    Cell (0,1): 50 mm/month, NaN (R19-masked) in 1990. Cell (1,*): sea (NaN). Cell (2,0): 10 mm/month, 1995 = 0.4/12."""
    f = np.full((12, 3, 2), np.nan)
    f[:, 0, 0] = 0.1 if y in (2005, 2012) else 100.0
    f[:, 0, 1] = np.nan if y == 1990 else 50.0
    f[:, 2, 0] = 0.4 / 12 if y == 1995 else 10.0
    f[:, 2, 1] = 10.0
    return f


def test_annual_cell_totals_sums_months_and_keeps_nan(tmp_path):
    t = nz.annual_cell_totals(_grids(tmp_path, _field), YEARS)
    assert t.shape == (len(YEARS), 3, 2)
    assert t[YEARS.index(1981), 0, 0] == pytest.approx(1200.0)
    assert np.isnan(t[YEARS.index(1990), 0, 1]) and np.isnan(t[0, 1, 0])
    with pytest.raises(FileNotFoundError):
        nz.annual_cell_totals(tmp_path / "grids", [1980])


def test_nearzero_cells_flags_below_5pct_of_own_base_median(tmp_path):
    t = nz.annual_cell_totals(_grids(tmp_path, _field), YEARS)
    c = nz.nearzero_cells(t, YEARS, lats=np.array([10.0, 10.25, 10.5]), lons=np.array([70.0, 70.25]))
    assert c[["year", "ilat", "ilon"]].values.tolist() == [[1995, 2, 0], [2005, 0, 0], [2012, 0, 0]]
    r = c.set_index("year").loc[2005]
    assert r.lat == 10.0 and r.lon == 70.0 and r.annual_mm == pytest.approx(1.2, rel=1e-5)
    assert r.base_median_mm == pytest.approx(1200.0) and r.ratio == pytest.approx(0.001, rel=1e-4)
    assert c.columns.tolist() == ["year", "ilat", "ilon", "lat", "lon", "annual_mm", "base_median_mm", "ratio"]
    assert c.set_index("year").loc[1995].ratio == pytest.approx(0.4 / 120, rel=1e-4)   # 3.3% < 5%


def test_region_nearzero_shares_uses_valid_area_and_threshold(tmp_path):
    t = nz.annual_cell_totals(_grids(tmp_path, _field), YEARS)
    c = nz.nearzero_cells(t, YEARS, lats=np.array([10.0, 10.25, 10.5]), lons=np.array([70.0, 70.25]))
    w = pd.DataFrame({"region_id": ["A", "A", "A", "B", "B"], "ilat": [0, 0, 1, 2, 2], "ilon": [0, 1, 0, 0, 1],
                      "weight": [0.3, 0.6, 0.1, 0.05, 0.95]})
    s = nz.region_shares(t, YEARS, c, w, "district", min_share=0.10)
    # A: flagged cell (0,0) has weight 0.3 of valid weight 0.9 (sea cell excluded) -> 1/3.
    # B: flagged (2,0) is 5% of area -> below the 10% threshold, not listed.
    assert s[["level", "region_id", "year"]].values.tolist() == [["district", "A", 2005], ["district", "A", 2012]]
    a = s.iloc[0]
    assert a.flagged_share == pytest.approx(1 / 3) and a.n_flagged_cells == 1
    # region annual = (0.3*1.2 + 0.6*600)/0.9; counterfactual replaces the fill with its base median scaled by
    # the unflagged cells' median ratio (1.0): (0.3*1200 + 0.6*600)/0.9
    actual, cf = (0.3 * 1.2 + 0.6 * 600) / 0.9, (0.3 * 1200 + 0.6 * 600) / 0.9
    assert a.est_bias_pct == pytest.approx(100 * (actual / cf - 1), rel=1e-4)
    assert s.columns.tolist() == ["level", "region_id", "year", "flagged_share", "n_flagged_cells", "est_bias_pct"]
    assert len(nz.region_shares(t, YEARS, c, w, "district", min_share=0.04)) == 3     # B 1995 now listed


def test_build_writes_cells_and_region_tables(tmp_path):
    grids = _grids(tmp_path, _field)
    parts = tmp_path / "_parts"
    parts.mkdir()
    pd.DataFrame({"region_id": ["A", "A"], "ilat": [0, 0], "ilon": [0, 1], "area_km2": [1.0, 2.0],
                  "weight": [1 / 3, 2 / 3]}).to_csv(parts / "weights_r025_state.csv", index=False)
    pd.DataFrame({"region_id": ["A"], "region_name": ["Alpha"], "year": [2005]}).to_csv(
        tmp_path / "climate_state_year.csv", index=False)
    out = nz.build(grids_dir=grids, parts_dir=parts, out_dir=tmp_path, levels=("state",),
                   lats=np.array([10.0, 10.25, 10.5]), lons=np.array([70.0, 70.25]))
    cells = pd.read_csv(out["cells"])
    regions = pd.read_csv(out["regions"])
    assert out["cells"].name == "qc_rain_nearzero_cells.csv" and len(cells) == 3
    assert out["regions"].name == "qc_rain_nearzero_regions.csv"
    assert regions[["level", "region_id", "region_name", "year"]].values.tolist() == [
        ["state", "A", "Alpha", 2005], ["state", "A", "Alpha", 2012]]
