import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline import build_climate as bc
from pipeline import imd_grid


def fake_regions(level):
    return gpd.GeoDataFrame(
        {"region_id": [f"{level}-A"], "region_name": ["A"], "state_id": ["S"], "state_name": ["S"]},
        geometry=[box(77.0, 12.0, 79.0, 14.0)], crs="EPSG:4326",
    )


def make_fetch(calls):
    def fetch(var, year, dest_dir, **kw):
        calls.append((var, year))
        g = imd_grid.GRID_OF[var]
        n = imd_grid.days_in_year(year)
        val = 5.0 if var == "rain" else (42.0 if var == "tmax" else 25.0)
        p = dest_dir / f"{var}_{year}.grd"
        dest_dir.mkdir(parents=True, exist_ok=True)
        np.full((n, g.nlat, g.nlon), val, dtype="<f4").tofile(p)
        return p
    return fetch


def test_build_is_resumable_and_assembles(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", lambda level: fake_regions(level))
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    calls = []
    kw = dict(levels=("state",), raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts",
              fetch=make_fetch(calls))
    bc.build_temperature([2023, 2024], base=(2023, 2024), **kw)
    bc.build_rain([2023, 2024], grids_dir=tmp_path / "grids", **kw)
    assert not list((tmp_path / "raw").glob("rain_*.grd"))          # raw rain deleted
    assert (tmp_path / "grids" / "rain_monthly_2024.npz").exists()
    n_calls = len(calls)
    bc.build_rain([2023, 2024], grids_dir=tmp_path / "grids", **kw)  # resume: nothing re-downloaded
    bc.build_temperature([2023, 2024], base=(2023, 2024), **kw)
    assert len(calls) == n_calls
    out = bc.assemble(levels=("state",), parts_dir=tmp_path / "parts", out_dir=tmp_path / "out")
    m = pd.read_csv(out["state_month"])
    assert len(m) == 24 and not m.duplicated(["region_id", "year", "month"]).any()
    feb24 = m[(m.year == 2024) & (m.month == 2)].iloc[0]
    assert feb24.rain_mm == pytest.approx(5.0 * 29) and feb24.rainy_days == pytest.approx(29)
    assert feb24.tmax_ge40_days == pytest.approx(29) and feb24.tmax_mean == pytest.approx(42.0)
    on = pd.read_csv(out["state_onset"])
    assert on.onset_doy.tolist() == [121.0, 122.0]                  # 1 May (non-leap / leap)


def two_regions(level):
    return gpd.GeoDataFrame(
        {"region_id": [f"{level}-A", f"{level}-B"], "region_name": ["A", "B"],
         "state_id": ["S", "S"], "state_name": ["S", "S"]},
        geometry=[box(77.0, 12.0, 79.0, 14.0), box(78.2, 12.0, 79.0, 14.0)], crs="EPSG:4326",
    )


def make_masking_fetch(masked):
    """tmax/rain with a hot spell / rain; cells with lon >= 78 hold the IMD missing sentinel if masked."""
    def fetch(var, year, dest_dir, **kw):
        g = imd_grid.GRID_OF[var]
        n = imd_grid.days_in_year(year)
        a = np.full((n, g.nlat, g.nlon), 5.0 if var == "rain" else (42.0 if var == "tmax" else 25.0), dtype="<f4")
        if var == "tmax":
            a[130:140] = 52.0
        if masked:
            a[:, :, np.asarray(g.lons) >= 78.0] = -999.0 if var == "rain" else 99.9
        p = dest_dir / f"{var}_{year}.grd"
        dest_dir.mkdir(parents=True, exist_ok=True)
        a.tofile(p)
        return p
    return fetch


def _build_month(tmp_path, monkeypatch, masked):
    monkeypatch.setattr(bc.boundaries, "load", two_regions)
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    kw = dict(levels=("state",), raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts",
              fetch=make_masking_fetch(masked))
    bc.build_temperature([2023], base=(2023, 2023), **kw)
    bc.build_rain([2023], grids_dir=tmp_path / "grids", **kw)
    out = bc.assemble(levels=("state",), parts_dir=tmp_path / "parts", out_dir=tmp_path / "out")
    return pd.read_csv(out["state_month"]).sort_values(["region_id", "month"]).reset_index(drop=True)


def test_masked_cells_are_not_diluted_and_fully_masked_region_falls_back(tmp_path, monkeypatch):
    full = _build_month(tmp_path / "full", monkeypatch, masked=False)
    half = _build_month(tmp_path / "half", monkeypatch, masked=True)
    cols = ["rain_mm", "rainy_days", "tmax_mean", "tmin_mean", "tmax_ge40_days", "heatwave_days"]
    assert full.heatwave_days.max() > 0                      # the spell is detected
    for rid in ("state-A", "state-B"):                       # A half masked, B fully masked
        a, b = full[full.region_id == rid], half[half.region_id == rid]
        np.testing.assert_allclose(b[cols].to_numpy(), a[cols].to_numpy(), rtol=1e-6)
    assert not half[half.region_id == "state-A"][["fallback_rain", "fallback_temp"]].any().any()
    assert half[half.region_id == "state-B"][["fallback_rain", "fallback_temp"]].all().all()


def test_writes_are_atomic_and_truncated_tmp_does_not_count_as_done(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", lambda level: fake_regions(level))
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    parts, grids = tmp_path / "parts", tmp_path / "grids"
    parts.mkdir()
    (parts / "temp_state_2023.csv.tmp").write_text("region_id,yea")      # interrupted write
    calls = []
    kw = dict(levels=("state",), raw_dir=tmp_path / "raw", parts_dir=parts, fetch=make_fetch(calls))
    bc.build_temperature([2023], base=(2023, 2023), **kw)
    bc.build_rain([2023], grids_dir=grids, **kw)
    assert ("tmax", 2023) in calls and ("rain", 2023) in calls
    assert len(pd.read_csv(parts / "temp_state_2023.csv")) == 12
    assert not list(parts.glob("*.tmp*")) and not list(grids.glob("*.tmp*"))


def test_assemble_gzips_district_month_only(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", lambda level: fake_regions(level))
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    levels = ("state", "district")
    kw = dict(levels=levels, raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts", fetch=make_fetch([]))
    bc.build_temperature([2023, 2024], base=(2023, 2024), **kw)
    bc.build_rain([2023, 2024], grids_dir=tmp_path / "grids", **kw)
    out = bc.assemble(levels=levels, parts_dir=tmp_path / "parts", out_dir=tmp_path / "out")
    assert out["district_month"].name == "climate_district_month.csv.gz"
    assert out["state_month"].name == "climate_state_month.csv"
    assert len(pd.read_csv(out["district_month"])) == 24


def test_assemble_leaves_exactly_one_month_form(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", lambda level: fake_regions(level))
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    levels = ("state", "district")
    kw = dict(levels=levels, raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts", fetch=make_fetch([]))
    bc.build_temperature([2023, 2024], base=(2023, 2024), **kw)
    bc.build_rain([2023, 2024], grids_dir=tmp_path / "grids", **kw)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "climate_district_month.csv").write_text("stale")      # stale other forms
    (out_dir / "climate_state_month.csv.gz").write_bytes(b"stale")
    bc.assemble(levels=levels, parts_dir=tmp_path / "parts", out_dir=out_dir)
    assert sorted(p.name for p in out_dir.glob("climate_*_month.csv*")) == [
        "climate_district_month.csv.gz", "climate_state_month.csv"]


def make_zero_fill_fetch():
    """Rain 5 mm/day everywhere except cells with lon >= 78 and 12 <= lat <= 14, which are 0 all year (no-station fill)."""
    def fetch(var, year, dest_dir, **kw):
        g = imd_grid.GRID_OF[var]
        n = imd_grid.days_in_year(year)
        a = np.full((n, g.nlat, g.nlon), 5.0 if var == "rain" else (42.0 if var == "tmax" else 25.0), dtype="<f4")
        if var == "tmax":
            a[130:140] = 52.0
        if var == "rain":
            lat_sel = (g.lats >= 12.0) & (g.lats <= 14.0)
            lon_sel = g.lons >= 78.0
            a[np.ix_(np.arange(n), lat_sel, lon_sel)] = 0.0
        p = dest_dir / f"{var}_{year}.grd"
        dest_dir.mkdir(parents=True, exist_ok=True)
        a.tofile(p)
        return p
    return fetch


def test_zero_annual_mask_only_flags_valid_cells_with_exact_zero_total():
    d = np.full((365, 2, 3), 1.0, dtype=np.float32)
    d[:, 0, 0] = 0.0                    # zero all year -> masked
    d[:, 0, 1] = np.nan                 # outside the grid -> not masked
    d[:, 0, 2] = 0.0
    d[100, 0, 2] = 0.1                  # one rainy day -> kept
    m = bc.zero_annual_mask(d)
    assert m.tolist() == [[True, False, False], [False, False, False]]


def test_zero_filled_cells_are_masked_for_the_whole_year_and_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", two_regions)
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    kw = dict(levels=("state",), raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts",
              fetch=make_zero_fill_fetch())
    bc.build_temperature([2023], base=(2023, 2023), **kw)
    bc.build_rain([2023], grids_dir=tmp_path / "grids", **kw)
    out = bc.assemble(levels=("state",), parts_dir=tmp_path / "parts", out_dir=tmp_path / "out")
    m = pd.read_csv(out["state_month"]).sort_values(["region_id", "month"])
    jan = m[m.month == 1].set_index("region_id")
    # zero-filled cells are missing, not 0 mm: A (partly zero-filled) and B (fully) both show 5 mm/day
    assert jan.loc["state-A", "rain_mm"] == pytest.approx(5.0 * 31)
    assert jan.loc["state-B", "rain_mm"] == pytest.approx(5.0 * 31)
    assert bool(jan.loc["state-B", "fallback_rain"]) and not bool(jan.loc["state-A", "fallback_rain"])
    grid = np.load(tmp_path / "grids" / "rain_monthly_2023.npz")["rain"]
    g = imd_grid.RAIN
    i, j = int(np.argmin(np.abs(g.lats - 13.0))), int(np.argmin(np.abs(g.lons - 78.5)))
    assert np.isnan(grid[:, i, j]).all()
    q = pd.read_csv(out["qc_rain_masked_cells"])
    n_expected = int(((g.lats >= 12.0) & (g.lats <= 14.0)).sum() * (g.lons >= 78.0).sum())
    row = q[q.year == 2023].iloc[0]
    assert row.n_cells == n_expected
    assert (row.lat_min, row.lat_max, row.lon_min) == (12.0, 14.0, 78.0)
    assert row.cells.count(";") == n_expected - 1


def test_qc_masked_cells_table_lists_years_with_no_masked_cells(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.boundaries, "load", lambda level: fake_regions(level))
    monkeypatch.setattr(bc.mf, "mark_deleted", lambda *a, **k: None)
    bc._AGG.clear()
    bc._REGIONS.clear()
    kw = dict(levels=("state",), raw_dir=tmp_path / "raw", parts_dir=tmp_path / "parts", fetch=make_fetch([]))
    bc.build_temperature([2023], base=(2023, 2023), **kw)
    bc.build_rain([2023], grids_dir=tmp_path / "grids", **kw)
    out = bc.assemble(levels=("state",), parts_dir=tmp_path / "parts", out_dir=tmp_path / "out")
    q = pd.read_csv(out["qc_rain_masked_cells"])
    assert q.year.tolist() == [2023] and q.n_cells.tolist() == [0]


def test_gzip_output_is_deterministic(tmp_path):
    df = pd.DataFrame({"a": [1, 2]})
    p = tmp_path / "x.csv.gz"
    bc._write_csv(df, p)
    raw = p.read_bytes()
    assert raw[:2] == b"\x1f\x8b" and raw[4:8] == b"\x00\x00\x00\x00"     # gzip MTIME field = 0
    assert pd.read_csv(p).a.tolist() == [1, 2]
