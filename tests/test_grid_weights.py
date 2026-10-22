import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from pipeline.grid_weights import Aggregator, cell_polygons, compute_weights
from pipeline.imd_grid import Grid

G = Grid(0.0, 0.0, 1.0, 4, 4)  # cells centred 0..3, edges -0.5..3.5


def regions(*boxes):
    return gpd.GeoDataFrame(
        {"region_id": [f"R{i}" for i in range(len(boxes))]}, geometry=list(boxes), crs="EPSG:4326"
    )


def test_cell_polygons_cover_grid():
    c = cell_polygons(G)
    assert len(c) == 16
    assert c.geometry.iloc[0].bounds == (-0.5, -0.5, 0.5, 0.5)


def test_weights_sum_to_one_and_split_partial_cells():
    w = compute_weights(G, regions(box(-0.5, -0.5, 1.5, 1.5), box(-0.5, -0.5, 0.5, 1.0)))
    assert w.groupby("region_id").weight.sum().round(6).tolist() == [1.0, 1.0]
    r0 = w[w.region_id == "R0"].weight
    assert len(r0) == 4 and np.allclose(r0, 0.25, atol=1e-3)
    r1 = w[w.region_id == "R1"].set_index(["ilat", "ilon"]).weight
    assert r1[(0, 0)] == pytest.approx(2 / 3, abs=1e-2) and r1[(1, 0)] == pytest.approx(1 / 3, abs=1e-2)


def test_aggregator_weighted_mean_ignores_nan_cells():
    agg = Aggregator(G, regions(box(-0.5, -0.5, 1.5, 1.5)))
    f = np.zeros((1, 4, 4), dtype=np.float32)
    f[0, 0, 0], f[0, 0, 1], f[0, 1, 0], f[0, 1, 1] = 1, 2, 3, np.nan
    out = agg.apply(f)
    assert out.shape == (1, 1) and out[0, 0] == pytest.approx(2.0, abs=1e-3)
    assert agg.fallback_regions == []


def test_aggregator_falls_back_to_nearest_valid_cell():
    agg = Aggregator(G, regions(box(2.6, 2.6, 3.4, 3.4), box(-0.5, -0.5, 0.5, 0.5)))
    f = np.full((2, 4, 4), np.nan, dtype=np.float32)
    f[:, 2, 2] = [7.0, 8.0]   # nearest valid cell to R0 (whose own cell [3,3] is NaN)
    f[:, 0, 0] = [1.0, 1.0]
    out = agg.apply(f)
    assert out[:, 0].tolist() == [7.0, 8.0]
    assert out[:, 1].tolist() == [1.0, 1.0]
    assert agg.fallback_regions == ["R0"]


def test_aggregator_all_nan_raises():
    agg = Aggregator(G, regions(box(-0.5, -0.5, 0.5, 0.5)))
    with pytest.raises(ValueError, match="no valid"):
        agg.apply(np.full((2, 4, 4), np.nan, dtype=np.float32))


def test_aggregator_fallback_is_per_timestep():
    agg = Aggregator(G, regions(box(2.6, 2.6, 3.4, 3.4)))
    f = np.full((3, 4, 4), np.nan, dtype=np.float32)
    f[:, 2, 2] = [7.0, 8.0, 9.0]       # valid neighbour at every step
    f[1, 3, 3] = 5.0                   # own cell valid only at t=1
    out = agg.apply(f)
    assert out[:, 0].tolist() == [7.0, 5.0, 9.0]
    assert agg.fallback_regions == ["R0"]
    f2 = f.copy()
    f2[:, 3, 3] = 5.0                  # own cell valid everywhere -> no fallback
    agg.apply(f2)
    assert agg.fallback_regions == []
