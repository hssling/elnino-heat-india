import math

import pandas as pd
import pytest

from pipeline import climate_units


def test_area_weighted_pooling_and_masked_members():
    cy = pd.DataFrame({"region_id": ["IND.2_1", "IND.32_1", "IND.1_1"], "year": [2010] * 3,
                       "rain_jjas_mm": [600.0, 900.0, math.nan]})
    areas = {"IND.2_1": 160000.0, "IND.32_1": 115000.0, "IND.1_1": 7600.0}
    out = climate_units.aggregate(cy, areas, columns=["rain_jjas_mm"]).set_index(["unit_id", "year"])
    exp = (600 * 160000 + 900 * 115000) / 275000
    assert abs(out.loc[("AP_TG", 2010), "rain_jjas_mm"] - exp) < 1e-9
    assert math.isnan(out.loc[("AN", 2010), "rain_jjas_mm"])
    assert out.loc[("AP_TG", 2010), "n_members_used"] == 2
    assert out.loc[("AN", 2010), "n_members_used"] == 0


def test_masked_member_renormalises_and_never_becomes_zero():
    cy = pd.DataFrame({"region_id": ["IND.2_1", "IND.32_1"] * 2, "year": [2010, 2010, 2011, 2011],
                       "rain_jjas_mm": [600.0, math.nan, math.nan, math.nan],
                       "tmin_mean": [20.0, 24.0, 21.0, 25.0]})
    areas = {"IND.2_1": 3.0, "IND.32_1": 1.0}
    out = climate_units.aggregate(cy, areas, columns=["rain_jjas_mm", "tmin_mean"]).set_index(["unit_id", "year"])
    assert out.loc[("AP_TG", 2010), "rain_jjas_mm"] == 600.0          # only the unmasked member
    assert math.isnan(out.loc[("AP_TG", 2011), "rain_jjas_mm"])        # all members masked -> NaN, not 0
    assert abs(out.loc[("AP_TG", 2011), "tmin_mean"] - 22.0) < 1e-9    # each column renormalises on its own
    assert out.loc[("AP_TG", 2010), "n_members_used"] == 1             # least-covered column
    assert out.loc[("AP_TG", 2010), "n_members"] == 2


def test_missing_area_raises():
    cy = pd.DataFrame({"region_id": ["IND.2_1"], "year": [2010], "rain_jjas_mm": [1.0]})
    with pytest.raises(KeyError):
        climate_units.aggregate(cy, {}, columns=["rain_jjas_mm"])


def test_state_areas_from_weights(tmp_path):
    parts = tmp_path / "_parts"
    parts.mkdir()
    pd.DataFrame({"region_id": ["A", "A", "B"], "ilat": [0, 1, 0], "ilon": [0, 0, 0],
                  "area_km2": [1.0, 2.0, 5.0], "weight": [0.3, 0.7, 1.0]}).to_csv(
        parts / "weights_r025_state.csv", index=False)
    assert climate_units.state_areas(tmp_path) == {"A": 3.0, "B": 5.0}
