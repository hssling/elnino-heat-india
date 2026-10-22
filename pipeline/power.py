"""NASA POWER (MERRA-2) monthly point data → state-month cross-check table."""
import calendar
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline import boundaries
from pipeline.paths import DERIVED, EXTERNAL


def parse_power_json(path) -> pd.DataFrame:
    d = json.loads(Path(path).read_text())
    lon, lat = d["geometry"]["coordinates"][:2]
    p = d["properties"]["parameter"]
    rows = []
    for key, mmday in p["PRECTOTCORR"].items():
        y, m = int(key[:4]), int(key[4:])
        if m == 13 or mmday is None or mmday < -900:
            continue
        rows.append({"lat": float(lat), "lon": float(lon), "year": y, "month": m,
                     "rain_mm": mmday * calendar.monthrange(y, m)[1],
                     "t2m": p["T2M"].get(key), "rh2m": p["RH2M"].get(key)})
    return pd.DataFrame(rows)


def state_month(points: pd.DataFrame, states: gpd.GeoDataFrame) -> pd.DataFrame:
    locs = points[["lat", "lon"]].drop_duplicates().reset_index(drop=True)
    g = gpd.GeoDataFrame(locs, geometry=gpd.points_from_xy(locs.lon, locs.lat), crs="EPSG:4326")
    j = gpd.sjoin(g, states[["region_id", "geometry"]], how="left", predicate="within")
    pairs = [j.dropna(subset=["region_id"])[["lat", "lon", "region_id"]]]
    covered = set(pairs[0].region_id)
    for _, st in states[~states.region_id.isin(covered)].iterrows():
        c = st.geometry.representative_point()
        k = np.argmin(np.hypot(locs.lat - c.y, locs.lon - c.x))
        pairs.append(pd.DataFrame({"lat": [locs.lat[k]], "lon": [locs.lon[k]], "region_id": [st.region_id]}))
    m = points.merge(pd.concat(pairs, ignore_index=True), on=["lat", "lon"])
    return m.groupby(["region_id", "year", "month"], as_index=False)[["rain_mm", "t2m"]].mean()


def build(ext=EXTERNAL, out=DERIVED) -> Path:
    pts = pd.concat([parse_power_json(f) for f in sorted(Path(ext, "power_points").glob("power_*.json"))],
                    ignore_index=True)
    res = state_month(pts, boundaries.load("state"))
    path = Path(out) / "power_state_month.csv"
    res.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    print(build())
