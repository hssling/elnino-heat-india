from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline import power

FIX = Path(__file__).parent / "fixtures"


def test_parse_power_json_converts_to_monthly_mm():
    d = power.parse_power_json(FIX / "power_sample.json")
    assert len(d) == 2 and d.month.tolist() == [1, 2]
    assert d.rain_mm.tolist() == [31.0, 58.0]       # 1 mm/d × 31; 2 mm/d × 29 (2024 leap)
    assert (d.lat.iloc[0], d.lon.iloc[0]) == (13.0, 78.0)


def test_state_month_mean_and_nearest_fallback():
    pts = pd.DataFrame({"lat": [13.0, 13.0], "lon": [77.0, 78.0], "year": 2024, "month": 1,
                        "rain_mm": [10.0, 30.0], "t2m": [20.0, 22.0], "rh2m": [50.0, 50.0]})
    states = gpd.GeoDataFrame({"region_id": ["IN", "FAR"]},
                              geometry=[box(76.5, 12.5, 78.5, 13.5), box(90, 25, 91, 26)], crs="EPSG:4326")
    s = power.state_month(pts, states).set_index("region_id")
    assert s.loc["IN", "rain_mm"] == 20.0
    assert s.loc["FAR", "rain_mm"] == 30.0            # nearest point is (13, 78)
