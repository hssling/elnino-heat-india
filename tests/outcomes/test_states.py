import pytest

from pipeline.outcomes import states


def test_frame_has_34_units_and_all_36_gadm_states():
    f = states.frame()
    assert len(f) == 34 and len(states.UNITS) == 34
    members = [g for gs in f.gid1_members for g in gs]
    assert len(members) == 36 and len(set(members)) == 36


@pytest.mark.parametrize("label,unit", [
    ("Andhra Pradesh", "AP_TG"), ("TELANGANA", "AP_TG"), ("Orissa", "OD"),
    ("Odisha*", "OD"), ("12. Uttaranchal", "UK"), ("Pondicherry", "PY"),
    ("A & N Islands", "AN"), ("D & N Haveli", "DNH_DD"), ("Daman & Diu", "DNH_DD"),
    ("Jammu & Kashmir", "JK"), ("Ladakh", "JK"), ("NCT of Delhi", "DL"),
    ("Chattisgarh", "CG"), ("ARUNACHAL PRADESH", "AR"), ("Tamilnadu", "TN"),
])
def test_resolve_variants(label, unit):
    assert states.resolve(label) == unit


@pytest.mark.parametrize("label", ["Total (States)", "TOTAL (UTs)", "All India", "Grand Total",
                                   "Total (All India)", "INDIA"])
def test_resolve_totals(label):
    assert states.resolve(label) == "TOTAL"


@pytest.mark.parametrize("label", ["Sl. No.", "State/UT", "Malaria situation in India", ""])
def test_resolve_non_state(label):
    assert states.resolve(label) is None


def test_unit_of_gid1():
    assert states.unit_of_gid1("IND.32_1") == "AP_TG"
    assert states.unit_of_gid1("IND.9_1") == "DNH_DD"


@pytest.mark.parametrize("label", ["Sub-total", "Sub Total", "TOTALS", "India (Total)"])
def test_resolve_subtotal_variants(label):
    assert states.resolve(label) == "TOTAL"


@pytest.mark.parametrize("label", ["INDIA", "India"])
def test_bare_india_is_total(label):
    assert states.resolve(label) == "TOTAL"


@pytest.mark.parametrize("label", ["India Central", "Indiana"])
def test_india_prefix_not_total(label):
    assert states.resolve(label) is None


@pytest.mark.parametrize("label,unit", [
    ("ARUNACHAL\nPRADESH", "AR"), ("Daman &\nDiu", "DNH_DD"),
])
def test_split_names_resolve(label, unit):
    assert states.resolve(label) == unit


@pytest.mark.parametrize("label,unit", [
    ("NCT Delhi", "DL"), ("Lakshadweep Islands", "LD"), ("Jammu-Kashmir", "JK"),
])
def test_new_aliases(label, unit):
    assert states.resolve(label) == unit


def test_conflicting_aliases_raise(tmp_path, monkeypatch):
    csv = tmp_path / "frame.csv"
    csv.write_text(
        "unit_id,unit_name,gid1_members,aliases\n"
        "AA,Alpha,IND.1_1,Shared Name\n"
        "BB,Beta,IND.2_1,Shared Name\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(states, "FRAME", csv)
    states.frame.cache_clear()
    states._alias_map.cache_clear()
    try:
        with pytest.raises(ValueError, match="SHARED NAME"):
            states._alias_map()
    finally:
        monkeypatch.undo()
        states.frame.cache_clear()
        states._alias_map.cache_clear()


@pytest.mark.parametrize("label,unit", [
    ("A.N.Islands", "AN"), ("30A.N.Islands", "AN"), ("Rajsthan", "RJ"), ("Andhra Pra.", "AP_TG"),
    ("Andhra Padesh", "AP_TG"), ("Arunachal Pra.", "AR"), ("Lakshdweep", "LD"),
    ("DN Haveli & Daman & Diu", "DNH_DD"), ("DN H & D D", "DNH_DD"),
    ("The Dadra And Nagar Haveli And Daman", "DNH_DD"),
])
def test_malaria_document_aliases(label, unit):
    assert states.resolve(label) == unit
