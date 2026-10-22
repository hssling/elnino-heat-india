"""Model-ready input tables: panels joined to climate, ENSO exposures, indicators and folds.

Missing is NaN, never 0. Lags are built by merging on year-1, never by shift(), so a gap
in the calendar can never move a value to the wrong year.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.paths import DERIVED

CLIMATE_VARS = ["rain_jjas_dep_pct", "spi3_sep", "tmax_mamj_anom", "heatwave_days", "onset_anom_days"]


def _lag(df: pd.DataFrame, cols, keys, rename) -> pd.DataFrame:
    """df[keys + year + cols] with year advanced by one, so merging on year gives x(t-1)."""
    prev = df[list(keys) + ["year"] + list(cols)].copy()
    prev["year"] = prev["year"] + 1
    return prev.rename(columns=rename)


def exposures(enso: pd.DataFrame) -> pd.DataFrame:
    lag_cols = ["oni_jjas", "roni_jjas", "nino34_jjas", "dmi_jjas"]
    out = enso[["year"] + lag_cols + ["el_nino_developing", "el_nino_decaying", "la_nina_developing"]].copy()
    lag = _lag(enso, lag_cols, [], {c: f"{c}_lag1" for c in lag_cols})
    prev = _lag(enso, ["oni_djf_next", "roni_djf_next", "dmi_son"], [],
                {"oni_djf_next": "oni_djf_prev", "roni_djf_next": "roni_djf_prev", "dmi_son": "dmi_son_prev"})
    out = out.merge(lag, on="year", how="left").merge(prev, on="year", how="left")
    cols = ["year", "oni_jjas", "oni_jjas_lag1", "roni_jjas", "roni_jjas_lag1", "nino34_jjas",
            "nino34_jjas_lag1", "dmi_jjas", "dmi_jjas_lag1", "oni_djf_prev", "roni_djf_prev",
            "dmi_son_prev", "el_nino_developing", "el_nino_decaying", "la_nina_developing"]
    return out[cols]


def climate(cu: pd.DataFrame) -> pd.DataFrame:
    base = cu[["unit_id", "year"] + CLIMATE_VARS].copy()
    lag = _lag(base, CLIMATE_VARS, ["unit_id"], {c: f"{c}_lag1" for c in CLIMATE_VARS})
    return base.merge(lag, on=["unit_id", "year"], how="left")


def indicators(years: pd.Series) -> pd.DataFrame:
    y = pd.Series(years).reset_index(drop=True)
    return pd.DataFrame({
        "year": y,
        "nfme2016": (y >= 2016).astype(int),
        "web_report2019": (y >= 2019).astype(int),
        "tested_def2022": (y >= 2022).astype(int),
        "covid2020_21": y.isin([2020, 2021]).astype(int),
        "label2014": (y >= 2014).astype(int),
        "covid2020": (y == 2020).astype(int),
    })


def folds(episodes: pd.DataFrame, years: range, anchor: str) -> pd.DataFrame:
    if anchor not in ("developing", "decaying"):
        raise ValueError("anchor must be 'developing' or 'decaying'")
    ep = episodes[(episodes.phase == "el_nino") & (~episodes.ongoing.astype(bool))].sort_values("start_year")
    spans = []
    for s, e in zip(ep.start_year.astype(int), ep.end_year.astype(int)):
        if anchor == "developing":
            rng = range(s, max(s + 1, e) + 1)
        else:
            rng = range(s + 1, max(s + 1, e) + 2)
        yrs = {y for y in rng if y in years}
        if yrs:
            spans.append({"years": yrs, "starts": [s]})
    merged = []
    for sp in spans:  # merge overlapping spans only; adjacent ones stay separate
        if merged and merged[-1]["years"] & sp["years"]:
            merged[-1]["years"] |= sp["years"]
            merged[-1]["starts"] += sp["starts"]
        else:
            merged.append(sp)
    rows = []
    for i, sp in enumerate(merged, 1):
        label = "+".join(str(s) for s in sp["starts"])
        rows += [{"fold_id": i, "year": y, "label": label} for y in sorted(sp["years"])]
    return pd.DataFrame(rows, columns=["fold_id", "year", "label"])


def foodgrain_dev(df: pd.DataFrame) -> pd.Series:
    """Percent deviation of foodgrain from its per-unit log-linear trend (NaN if <10 valid years)."""
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for _, g in df.groupby("unit_id"):
        ok = g[g.foodgrain_t.notna() & (g.foodgrain_t > 0)]
        if len(ok) < 10:
            continue
        x = ok.year.astype(float)
        slope, icpt = np.polyfit(x, np.log(ok.foodgrain_t.astype(float)), 1)
        out.loc[ok.index] = 100 * (ok.foodgrain_t / np.exp(icpt + slope * x) - 1)
    return out


def _log1p_lag1(df: pd.DataFrame, col: str) -> np.ndarray:
    lag = _lag(df, [col], ["unit_id"], {col: "_prev"})
    m = df[["unit_id", "year"]].merge(lag, on=["unit_id", "year"], how="left")
    return np.log1p(m["_prev"]).to_numpy()


def build(out_dir=DERIVED / "model", derived=DERIVED) -> dict:
    derived, out_dir = Path(derived), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    enso = pd.read_csv(derived / "enso_annual.csv")
    episodes = pd.read_csv(derived / "enso_episodes.csv")
    cl = climate(pd.read_csv(derived / "climate_unit_year.csv"))
    ex = exposures(enso)
    pop = pd.read_csv(derived / "outcomes" / "population_unit_year.csv")[["unit_id", "year", "population"]]

    def prep(name):
        p = pd.read_csv(derived / "outcomes" / f"{name}_state_year.csv")
        if "population" not in p.columns:
            p = p.merge(pop, on=["unit_id", "year"], how="left")
        n = len(p)
        ind = indicators(pd.Series(sorted(p.year.unique())))
        p = p.merge(cl, on=["unit_id", "year"], how="left").merge(ex, on="year", how="left")
        p = p.merge(ind, on="year", how="left")
        assert len(p) == n, f"{name}: join changed row count"
        p["log_pop"] = np.log(p.population.where(p.population > 0))
        return p

    files = {}

    def save(key, fname, df):
        files[key] = out_dir / fname
        df.to_csv(files[key], index=False)

    # Panels of a separate study (malaria, dengue) are not distributed with this repository; their
    # model inputs are built only when a full outcome rebuild has produced them.
    have = lambda name: (derived / "outcomes" / f"{name}_state_year.csv").exists()   # noqa: E731
    if have("malaria"):
        m = prep("malaria")
        m["log_aber"] = np.log(m.aber.where(m.aber > 0))
        m["log1p_cases_lag1"] = _log1p_lag1(m, "cases")
        save("malaria", "malaria_model.csv", m)
    if have("dengue"):
        d = prep("dengue")
        d["log1p_cases_lag1"] = _log1p_lag1(d, "cases")
        save("dengue", "dengue_model.csv", d)
    h = prep("heat_deaths")
    h["log1p_heat_deaths_lag1"] = _log1p_lag1(h, "heat_deaths")
    save("heat", "heat_model.csv", h)
    f = prep("farmer_suicides")
    f["log1p_farming_sector_lag1"] = _log1p_lag1(f, "farming_sector")
    save("farmers", "farmers_model.csv", f)
    g = prep("foodgrain")
    g["foodgrain_dev_pct"] = foodgrain_dev(g)
    save("foodgrain", "foodgrain_model.csv", g)
    pop_all = pop.copy()
    pop_all["log_pop"] = np.log(pop_all.population.where(pop_all.population > 0))
    save("population", "population_2001_2027.csv", pop_all[["unit_id", "year", "population", "log_pop"]])
    yrs = range(1997, 2026)
    save("folds_developing", "folds_developing.csv", folds(episodes, yrs, "developing"))
    save("folds_decaying", "folds_decaying.csv", folds(episodes, yrs, "decaying"))
    return files


if __name__ == "__main__":
    for k, v in build().items():
        print(k, v)
