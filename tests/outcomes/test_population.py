import pandas as pd
import pytest

from pipeline.outcomes import population


@pytest.mark.network
def test_census_totals_match_national_golden_values():
    c = population.census_state_totals()
    assert c[c.year == 2001].population.sum() == pytest.approx(1_028_737_436, rel=1e-4)
    assert c[c.year == 2011].population.sum() == pytest.approx(1_210_854_977, rel=1e-4)
    assert set(c.unit_id) == set(population.states.UNITS)


@pytest.mark.network
def test_projections_cover_units_and_are_in_persons():
    p = population.projections()
    assert set(p.unit_id) == set(population.states.UNITS)
    assert sorted(p.year.unique()) == list(range(2012, 2028))
    assert p[p.year == 2025].population.sum() == pytest.approx(1_411_016_000, rel=2e-3)


def test_rgi_2026_2027_golden_kerala_from_cached_source():
    """Printed RGI Table 8 (1 March), Kerala persons in '000: 2025 36,063; 2026 36,207; 2027 36,304."""
    if not population.cached():
        pytest.skip("raw files not cached")
    p = population.projections().set_index(["unit_id", "year"]).population
    assert p[("KL", 2025)] == 36_063_000.0
    assert p[("KL", 2026)] == 36_207_000.0
    assert p[("KL", 2027)] == 36_304_000.0


def test_interpolation_and_projection_joins(tmp_path, monkeypatch):
    census = pd.DataFrame({"unit_id": ["OD", "OD"], "year": [2001, 2011], "population": [100.0, 200.0]})
    proj = pd.DataFrame({"unit_id": ["OD"] * 16, "year": range(2012, 2028), "population": [210.0 + i for i in range(16)]})
    monkeypatch.setattr(population, "census_state_totals", lambda: census)
    monkeypatch.setattr(population, "projections", lambda: proj)
    monkeypatch.setattr(population.states, "UNITS", ["OD"])
    p = pd.read_csv(population.build(out=tmp_path / "p.csv")).set_index("year").population
    assert p[2006] == 150.0 and p[2011] == 200.0 and p[2012] == 210.0 and p[2025] == 223.0 and p[2027] == 225.0
    assert list(p.index) == list(range(2001, 2028))


def _pop(units=("OD", "GJ"), years=range(2001, 2028)):
    return pd.DataFrame([{"unit_id": u, "year": y, "population": 1000.0 + y, "source": "s"}
                         for u in units for y in years])


def test_population_gate_shape_positivity_and_rebuild(tmp_path):
    from pipeline.outcomes import gates
    f = tmp_path / "population_unit_year.csv"
    _pop().to_csv(f, index=False)
    ok = gates.population_gate(f, units=["OD", "GJ"], rebuild=_pop)
    assert ok.name == "outcome_population" and ok.passed and "identical to the rebuild" in ok.detail
    assert not gates.population_gate(f, units=["OD", "GJ", "KL"], rebuild=_pop).passed      # KL rows absent
    assert not gates.population_gate(f, units=["OD", "GJ"], rebuild=lambda: _pop().assign(population=7.0)).passed
    nr = gates.population_gate(f, units=["OD", "GJ"], rebuild=None)
    assert nr.passed and "rebuild skipped" in nr.detail
    for bad in (_pop().assign(population=0.0), _pop().assign(population=float("nan")),
                pd.concat([_pop(), _pop().head(1)]), _pop(years=range(2001, 2026))):
        bad.to_csv(f, index=False)
        assert not gates.population_gate(f, units=["OD", "GJ"], rebuild=_pop).passed
    f.unlink()
    assert not gates.population_gate(f, units=["OD", "GJ"]).passed


def test_population_table_equals_build_output(tmp_path, monkeypatch):
    census = pd.DataFrame({"unit_id": ["OD", "OD"], "year": [2001, 2011], "population": [100.0, 200.0]})
    proj = pd.DataFrame({"unit_id": ["OD"] * 16, "year": range(2012, 2028), "population": [210.0 + i for i in range(16)]})
    monkeypatch.setattr(population, "census_state_totals", lambda: census)
    monkeypatch.setattr(population, "projections", lambda: proj)
    monkeypatch.setattr(population.states, "UNITS", ["OD"])
    built = pd.read_csv(population.build(out=tmp_path / "p.csv"))
    pd.testing.assert_frame_equal(built, population.table(), check_exact=True)
