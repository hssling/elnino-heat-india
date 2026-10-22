import geopandas as gpd
from shapely.geometry import box

from pipeline import boundaries


def test_disputed_z_units_merge_into_indian_ids(tmp_path):
    p = tmp_path / "t.gpkg"
    a, b = box(0, 0, 1, 1), box(1, 0, 2, 1)
    gpd.GeoDataFrame(
        {"GID_1": ["IND.13_1", "Z04.13_1"], "NAME_1": ["Himachal Pradesh"] * 2}, geometry=[a, b], crs="EPSG:4326"
    ).to_file(p, layer="ADM_ADM_1", driver="GPKG")
    gpd.GeoDataFrame(
        {"GID_2": ["IND.13.5_1", "Z04.13.5_1"], "NAME_2": ["Kinnaur"] * 2,
         "GID_1": ["IND.13_1", "Z04.13_1"], "NAME_1": ["Himachal Pradesh"] * 2},
        geometry=[a, b], crs="EPSG:4326",
    ).to_file(p, layer="ADM_ADM_2", driver="GPKG")
    s = boundaries.load("state", p)
    assert s.region_id.tolist() == ["IND.13_1"] and s.geometry.iloc[0].area == 2.0
    d = boundaries.load("district", p)
    assert d.region_id.tolist() == ["IND.13.5_1"] and d.state_id.tolist() == ["IND.13_1"]
