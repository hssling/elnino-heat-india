from pathlib import Path

import numpy as np

from pipeline import enso

FIX = Path(__file__).parent / "fixtures"


def test_parse_oni_centre_months():
    oni = enso.parse_oni(FIX / "oni_sample.txt")
    assert len(oni) == 19
    assert oni.iloc[0][["season", "year", "month"]].tolist() == ["DJF", 2020, 1]
    assert oni.iloc[11][["season", "month"]].tolist() == ["NDJ", 12]


def test_round_half_away_is_symmetric():
    assert enso.round_half_away(np.array([0.45, -0.45, 0.44, -0.55])).tolist() == [0.5, -0.5, 0.4, -0.6]


def test_classify_episodes_and_trailing_provisional_run():
    c = enso.classify(enso.parse_oni(FIX / "oni_sample.txt"))
    ep = enso.episodes(c)
    assert ep["phase"].tolist() == ["el_nino", "la_nina", "el_nino"]
    first, cold, trail = ep.iloc[0], ep.iloc[1], ep.iloc[2]
    assert (first.start_season, first.start_year, first.n_seasons) == ("FMA", 2020, 6)
    assert first.intensity == "very_strong" and not first.provisional
    assert (cold.start_season, cold.end_season, cold.n_seasons) == ("SON", "JFM", 5)
    assert trail.provisional and trail.ongoing and trail.n_seasons == 3
    assert trail.peak_anom == 1.8
    # seasons outside runs stay neutral
    assert c.loc[(c.season == "ASO") & (c.year == 2020), "phase"].item() == "neutral"


def test_intensity_classes():
    assert [enso.intensity(x) for x in (0.5, 1.0, 1.5, 2.0)] == ["weak", "moderate", "strong", "very_strong"]


def test_annual_exposures():
    a = enso.annual(enso.classify(enso.parse_oni(FIX / "oni_sample.txt"))).set_index("year")
    # JJAS = mean of seasons centred Jun..Sep = MJJ, JJA, JAS, ASO
    assert a.loc[2020, "oni_jjas"] == np.mean([1.2, 1.6, 2.1, 0.3])
    assert a.loc[2020, "oni_djf_next"] == -1.1
    assert bool(a.loc[2020, "el_nino_developing"]) is True
    assert bool(a.loc[2021, "el_nino_decaying"]) is False  # 2020 event ended before DJF 2021
    assert bool(a.loc[2020, "la_nina_developing"]) is False  # La Niña not active in JAS 2020


def test_parse_dmi_missing_to_nan():
    d = enso.parse_dmi(FIX / "dmi_sample.data")
    assert len(d) == 24
    assert d.loc[(d.year == 2019) & (d.month == 12), "dmi"].item() == 1.2
    assert d.loc[(d.year == 2020) & (d.month == 3), "dmi"].isna().item()


import pytest  # noqa: E402


@pytest.mark.parametrize("line", ["  DJF 2020  27.00   x.10", "  DJF 2020  27.00", "  JFM 20x0  27.00   0.10",
                                  "  FMA 2020  27.00   0.10  9"])
def test_parse_oni_text_malformed_season_line_raises(line):
    text = "SEAS  YR   TOTAL   ANOM\n  NDJ 2019  27.00   0.10\n" + line + "\n"
    with pytest.raises(enso.InvalidONIFile, match="malformed"):
        enso.parse_oni_text(text)


def test_parse_oni_text_ignores_non_season_lines():
    o = enso.parse_oni_text("SEAS  YR   TOTAL   ANOM\n\nfooter text here\n  DJF 2020  27.00   0.10\n")
    assert o.season.tolist() == ["DJF"]


def test_parse_roni_uses_last_column():
    r = enso.parse_roni(FIX / "roni_sample.txt")
    assert r.loc[(r.season == "JAS") & (r.year == 2020), "roni"].item() == 1.0
    assert r.loc[(r.season == "NDJ") & (r.year == 2020), "month"].item() == 12


def test_parse_roni_accepts_four_columns(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("SEAS YR TOTAL ANOM\nJAS 2020 27.00 1.00\n")
    assert enso.parse_roni(p).roni.item() == 1.0


def test_annual_includes_roni_when_given():
    oni = enso.classify(enso.parse_oni(FIX / "oni_sample.txt"))
    roni = enso.parse_roni(FIX / "roni_sample.txt")
    a = enso.annual(oni, roni=roni).set_index("year")
    assert a.loc[2020, "roni_jjas"] == pytest.approx((0.5 + 0.8 + 1.0 + 1.2) / 4)
    assert a.loc[2020, "roni_djf_next"] == 1.4


def test_annual_monthly_extra_means_and_nan_rule():
    import pandas as pd
    oni = enso.classify(enso.parse_oni(FIX / "oni_sample.txt"))
    rows = []
    for y in (2020, 2021):
        for m in range(1, 13):
            if (y, m) == (2021, 10):
                continue
            rows.append((y, m, m * 0.1 + (y - 2020), m * 1.0 + 10 * (y - 2020)))
    extra = pd.DataFrame(rows, columns=["year", "month", "nino34_anom", "dmi"])
    a = enso.annual(oni, monthly_extra=extra).set_index("year")
    assert a.loc[2020, "nino34_jjas"] == pytest.approx((0.6 + 0.7 + 0.8 + 0.9) / 4)
    assert a.loc[2020, "dmi_jjas"] == pytest.approx(7.5)
    assert a.loc[2020, "dmi_son"] == pytest.approx(10.0)
    assert a.loc[2021, "dmi_jjas"] == pytest.approx(17.5)
    assert np.isnan(a.loc[2021, "dmi_son"])          # Oct 2021 missing
    assert "roni_jjas" not in a.columns


def test_annual_without_extras_unchanged_columns():
    oni = enso.classify(enso.parse_oni(FIX / "oni_sample.txt"))
    assert list(enso.annual(oni).columns) == [
        "year", "oni_jjas", "oni_djf_next", "el_nino_developing", "el_nino_decaying", "la_nina_developing"]
