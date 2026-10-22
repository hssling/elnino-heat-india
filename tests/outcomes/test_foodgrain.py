import json
import math
from pathlib import Path

import numpy as np
import pytest

from pipeline.outcomes import fetch, foodgrain, records

FIX = Path(__file__).parent / "fixtures"


def get(df, unit, year, var="foodgrain_t"):
    s = df[(df.unit_id == unit) & (df.year == year) & (df.variable == var)]
    assert len(s) == 1, s
    return s.iloc[0]


def test_agri_year_convention():
    assert foodgrain.agri_year("2015-16") == 2015 and foodgrain.agri_year("1999-00") == 1999
    with pytest.raises(ValueError):
        foodgrain.agri_year("2015-17")


def test_no_unregistered_source_ids():
    # every source id the module can emit is registered (SOURCES / outcomes_sources.csv); the DES CSV
    # fixture path ("foodgrain_rbi_sample", "foodgrain_rbi_local") was removed
    assert not hasattr(foodgrain, "des_state") and not hasattr(foodgrain, "des_csv")
    assert set(foodgrain.RBI_FILES) <= set(foodgrain.SOURCES)


def test_rbi2023_missing_reason_is_repo_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(foodgrain.fetch, "RAW_ROOT", foodgrain.ROOT / "data" / "raw" / "outcomes_test_absent")
    with pytest.raises(fetch.LocalSourceMissing) as e:
        foodgrain.rbi_pdf("foodgrain_rbi2023")
    msg = str(e.value)
    assert "data/raw/outcomes_test_absent/foodgrain_rbi2023/" + foodgrain.RBI_FILES["foodgrain_rbi2023"] in msg
    assert str(foodgrain.ROOT) not in msg and "\\" not in msg


RBI54 = lambda: (FIX / "foodgrain_rbi54.txt").read_text(encoding="utf-8").splitlines()  # noqa: E731


def parse54():
    # the printed 2011-12 state rows add up to 1.15% more than the printed ALL INDIA (source inconsistency)
    with pytest.warns(UserWarning, match="2011 state rows sum"):
        return foodgrain.rbi_table(RBI54(), "foodgrain_rbi2019")


def test_rbi_table54_golden_cells():
    # printed cells: "Punjab ... 21143.2 22906.9" (1990-91..1998-99), "Tamil Nadu ... 4442.1 ..." (2002-03),
    # "Uttar Pradesh ... 41558.8 40417.2"
    df = parse54()
    records.validate(df)
    assert get(df, "PB", 1997).value == pytest.approx(21143.2 * 1000)
    assert get(df, "TN", 2002).value == pytest.approx(4442.1 * 1000)
    assert get(df, "UP", 1997).value == pytest.approx(41558.8 * 1000)
    assert not get(df, "UP", 1997).provisional
    assert get(df, "TOTAL", 1997).value == pytest.approx(192263.0 * 1000)


def test_rbi_table54_pooling_and_not_applicable():
    df = parse54()
    # AP 10522.3 + Telangana 9142.9 in 2013-14; Telangana "." (not applicable) before 2011-12 -> AP alone
    assert get(df, "AP_TG", 2013).value == pytest.approx((10522.3 + 9142.9) * 1000)
    assert get(df, "AP_TG", 2010).value == pytest.approx(20315.0 * 1000)
    # Chhattisgarh "." in 1999-00 is NaN, not 0; 2901.3 printed in 2000-01
    assert math.isnan(get(df, "CG", 1999).value)          # row present, NaN
    assert get(df, "CG", 2000).value == pytest.approx(2901.3 * 1000)
    assert not (df.value == 0).any()
    assert df.year.min() == 1990 and df.year.max() == 2016
    assert not df.duplicated(["unit_id", "year", "variable"]).any()


def test_rbi_table_unresolved_state_row_raises():
    lines = RBI54()
    bad = [ln.replace("Karnataka ", "Karnatakaa ", 1) if ln.startswith("Karnataka ") else ln for ln in lines]
    with pytest.raises(ValueError):
        foodgrain.rbi_table(bad, "foodgrain_rbi2019")


def test_rbi_table_total_mismatch_warns():
    lines = [ln.replace("41558.8", "1558.8", 1) for ln in RBI54()]
    with pytest.warns(UserWarning, match="1997 state rows sum"):
        foodgrain.rbi_table(lines, "foodgrain_rbi2019")


def test_rbi_provisional_last_edition_year_flagged():
    lines = ["States/Union Territories  2021-22 2022-23",
             "Punjab  100.0 200.0",
             "ALL INDIA  100.0 200.0"]
    df = foodgrain.rbi_table(lines, "foodgrain_rbi2023")      # PROVISIONAL: 2022 (3rd advance estimates)
    assert get(df, "PB", 2021).provisional is np.False_ or not get(df, "PB", 2021).provisional
    assert get(df, "PB", 2022).provisional
    assert get(df, "PB", 2022).value == 200_000.0
    df19 = foodgrain.rbi_table(lines, "foodgrain_rbi2019")    # no provisional years configured
    assert not df19.provisional.any()


def test_rbi_table54_ap_tg_2011_first_telangana_year():
    # printed 2011-12 cells: Andhra Pradesh "10868.1", Telangana "7495.0"
    df = parse54()
    assert get(df, "AP_TG", 2011).value == pytest.approx((10868.1 + 7495.0) * 1000)
    assert get(df, "AP_TG", 2011).raw_label == "Andhra Pradesh + Telangana"


def test_dld_golden_state_sums_tonnes_and_area():
    df = foodgrain.dld_state(path=FIX / "foodgrain_dld_sample.json")
    records.validate(df)
    # Punjab 2012 (agri year 2012-13): district cells e.g. Gurdaspur RICE PRODUCTION "618.0", AREA "201.0" ('000 t/'000 ha)
    assert get(df, "PB", 2012).value == pytest.approx(28549.8 * 1000)
    assert get(df, "PB", 2012, "foodgrain_ha").value == pytest.approx(6527.8 * 1000)
    assert get(df, "KL", 2015).value == pytest.approx(553.83 * 1000)
    assert get(df, "KL", 2015, "foodgrain_ha").value == pytest.approx(200.94 * 1000)


def test_dld_pools_andhra_and_telangana():
    df = foodgrain.dld_state(path=FIX / "foodgrain_dld_sample.json")
    rows = json.loads((FIX / "foodgrain_dld_sample.json").read_text())
    names = {r[11] for r in rows["data"] if r[1] == "2014"}
    assert names == {"Andhra Pradesh", "Telangana"}
    s = get(df, "AP_TG", 2014)
    assert s.raw_label == "Andhra Pradesh + Telangana"
    parts = [foodgrain._dld_sums(rows, st, 2014)[0] for st in names]
    assert s.value == pytest.approx(sum(parts) * 1000)


def test_dld_missing_sentinel_gives_nan_not_sum():
    rows = json.loads((FIX / "foodgrain_dld_sample.json").read_text())
    H = [h["header"] for h in rows["headers"]]
    i = next(k for k, r in enumerate(rows["data"]) if r[11] == "Kerala")
    rows["data"][i][H.index("RICE PRODUCTION")] = "-1.0"
    df = foodgrain.dld_state(data=rows)
    assert math.isnan(get(df, "KL", 2015).value)
    assert get(df, "PB", 2012).value > 0


def test_dld_unknown_state_raises():
    rows = json.loads((FIX / "foodgrain_dld_sample.json").read_text())
    rows["data"][0][11] = "Atlantis"
    with pytest.raises(ValueError):
        foodgrain.dld_state(data=rows)


def test_all_records_skips_missing_sources(monkeypatch):
    def boom(*a, **k):
        raise fetch.FetchError("offline")
    monkeypatch.setattr(foodgrain, "dld_state", boom)
    monkeypatch.setattr(foodgrain, "rbi_pdf", lambda sid: foodgrain.rbi_table(RBI54(), sid) if sid == "foodgrain_rbi2019" else (_ for _ in ()).throw(fetch.LocalSourceMissing("x")))
    with pytest.warns(UserWarning) as w:
        df = foodgrain.all_records()
    msgs = [str(x.message) for x in w]
    assert any("foodgrain_dld: source unavailable" in m for m in msgs)
    assert any("foodgrain_rbi2023: source unavailable" in m for m in msgs)
    assert df.attrs["missing_sources"] == ["foodgrain_dld", "foodgrain_rbi2023"]
    assert set(df.attrs["missing_reasons"]) == {"foodgrain_dld", "foodgrain_rbi2023"}
    assert set(df.source_id) == {"foodgrain_rbi2019"}
