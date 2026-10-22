import math

import pandas as pd
import pytest

from pipeline import model_inputs as mi
from pipeline.paths import DERIVED


def enso():
    return pd.read_csv(DERIVED / "enso_annual.csv")


def test_exposure_lags_and_previous_winter():
    e = enso().set_index("year")
    x = mi.exposures(enso()).set_index("year")
    assert x.loc[2003, "oni_jjas_lag1"] == pytest.approx(e.loc[2002, "oni_jjas"])
    assert x.loc[2016, "oni_djf_prev"] == pytest.approx(e.loc[2015, "oni_djf_next"])
    assert x.loc[2016, "dmi_son_prev"] == pytest.approx(e.loc[2015, "dmi_son"])
    assert x.loc[2003, "roni_jjas_lag1"] == pytest.approx(e.loc[2002, "roni_jjas"])


def test_developing_folds_paper_a():
    ep = pd.read_csv(DERIVED / "enso_episodes.csv")
    f = mi.folds(ep, range(2002, 2026), "developing")
    spans = f.groupby("fold_id").year.apply(lambda s: (s.min(), s.max())).tolist()
    assert spans == [(2002, 2003), (2004, 2005), (2006, 2007), (2009, 2010), (2014, 2016),
                     (2018, 2020), (2023, 2024)]
    assert f[f.fold_id == 6].label.iloc[0] == "2018+2019"


def test_decaying_folds_paper_c():
    ep = pd.read_csv(DERIVED / "enso_episodes.csv")
    f = mi.folds(ep, range(2001, 2025), "decaying")
    spans = f.groupby("fold_id").year.apply(lambda s: (s.min(), s.max())).tolist()
    assert spans == [(2003, 2004), (2005, 2006), (2007, 2008), (2010, 2011), (2015, 2017),
                     (2019, 2021), (2024, 2024)]


def test_indicators():
    ind = mi.indicators(pd.Series([2013, 2014, 2016, 2019, 2020, 2021, 2022]))
    assert ind.label2014.tolist() == [0, 1, 1, 1, 1, 1, 1]
    assert ind.covid2020_21.tolist() == [0, 0, 0, 0, 1, 1, 0]
    assert ind.covid2020.tolist() == [0, 0, 0, 0, 1, 0, 0]
    assert ind.tested_def2022.tolist() == [0, 0, 0, 0, 0, 0, 1]


def test_foodgrain_dev_exact_trend_is_zero():
    yrs = list(range(1997, 2017))
    df = pd.DataFrame({"unit_id": "PB", "year": yrs, "foodgrain_t": [1000 * math.exp(0.02 * (y - 1997)) for y in yrs]})
    assert mi.foodgrain_dev(df).abs().max() < 1e-9


def test_build_keeps_rows_and_nan(tmp_path):
    out = mi.build(out_dir=tmp_path)
    hd = pd.read_csv(out["heat"])
    assert len(hd) == 34 * 24 and hd.unit_id.nunique() == 34
    an = hd[hd.unit_id == "AN"]
    assert an.rain_jjas_dep_pct.isna().all()          # A&N rain masked upstream: stays NaN, never 0
    f = pd.read_csv(out["farmers"]).set_index(["unit_id", "year"])
    assert len(f) == 34 * 23
    assert pd.isna(f.loc[("WB", 2012), "farming_sector"])        # printed "NR": NaN, never 0
    assert pd.isna(f.loc[("WB", 2013), "log1p_farming_sector_lag1"])
    assert "malaria" not in out or len(pd.read_csv(out["malaria"])) == 34 * 24   # not distributed here
    h = hd.set_index(["unit_id", "year"])
    assert h.loc[("RJ", 2016), "log1p_heat_deaths_lag1"] == pytest.approx(math.log1p(h.loc[("RJ", 2015), "heat_deaths"]))
    assert {"oni_jjas", "oni_jjas_lag1", "oni_djf_prev", "dmi_son_prev", "log_pop", "label2014"} <= set(h.columns)


def test_build_writes_population_2001_2027(tmp_path):
    out = mi.build(out_dir=tmp_path)
    pop = pd.read_csv(out["population"])
    assert list(pop.columns) == ["unit_id", "year", "population", "log_pop"]
    assert len(pop) == 34 * 27 and pop.year.min() == 2001 and pop.year.max() == 2027
    assert pop[["population", "log_pop"]].notna().all().all()
    kl = pop[pop.unit_id == "KL"].set_index("year")
    assert kl.loc[2027, "population"] == 36_304_000.0
    assert kl.loc[2027, "log_pop"] == pytest.approx(math.log(36_304_000.0))
    h = pd.read_csv(out["heat"]).merge(pop, on=["unit_id", "year"], suffixes=("", "_p"))
    assert (h.log_pop == h.log_pop_p).all()
