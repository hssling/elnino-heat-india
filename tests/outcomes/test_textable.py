import math
import warnings

import pytest

from pipeline.outcomes import textable as t


@pytest.mark.parametrize("tok,dash,expected", [
    ("1,23,456", "nan", 123456), ("2,345*", "nan", 2345), ("12P", "nan", 12), ("0", "nan", 0),
    ("-", "zero", 0), ("–", "zero", 0), ("Nil", "zero", 0), ("3.5", "nan", 3.5),
])
def test_parse_number_values(tok, dash, expected):
    assert t.parse_number(tok, dash) == expected


@pytest.mark.parametrize("tok", ["-", "NR", "NA", "N.A.", ""])
def test_parse_number_missing(tok):
    assert math.isnan(t.parse_number(tok, "nan"))


def test_em_dash_missing_and_zero():
    assert math.isnan(t.parse_number("—", "nan"))
    assert t.parse_number("—", "zero") == 0


def test_split_row_label_and_numbers():
    label, nums = t.split_row("  5   Andhra Pradesh    8,718,569   38,053   21,416    0")
    assert label == "5 Andhra Pradesh" and nums == ["8,718,569", "38,053", "21,416", "0"]
    label, nums = t.split_row("Dadra & Nagar Haveli   NR  12*  -")
    assert label == "Dadra & Nagar Haveli" and nums == ["NR", "12*", "-"]


@pytest.mark.parametrize("line,nums", [
    ("Bihar          217632 4006 1286 1", ["217632", "4006", "1286", "1"]),
    ("Andhra Pradesh   8,718,569   38,053 21,416  0", ["8,718,569", "38,053", "21,416", "0"]),
    ("Andhra Pradesh   8,718,569 38,053 21,416 0", ["8,718,569", "38,053", "21,416", "0"]),
])
def test_split_row_maximal_trailing_numeric_run(line, nums):
    label, toks = t.split_row(line)
    assert toks == nums
    assert label in ("Bihar", "Andhra Pradesh")


@pytest.mark.parametrize("line,label,nums", [
    ("Goa 12 *", "Goa", ["12"]),
    ("Goa 2,345 *", "Goa", ["2,345"]),
    ("Goa  12  *", "Goa", ["12"]),
    ("Goa  —  5", "Goa", ["—", "5"]),
    ("Goa 500 20 3 *", "Goa", ["500", "20", "3"]),
])
def test_footnote_marks_and_em_dash_in_split(line, label, nums):
    assert t.split_row(line) == (label, nums)


def test_state_rows_resolves_totals_pools_and_joins_split_names():
    lines = ["Sl State/UT  BSE  Cases",
             "1 Andhra Pradesh  100  10",
             "2 Telangana  50  5",
             "3 ARUNACHAL",
             "  PRADESH  20  2",
             "Total (All India)  170  17",
             "Note: provisional"]
    rows = t.state_rows(lines, expected_numbers=2)
    assert [r["unit_id"] for r in rows] == ["AP_TG", "AP_TG", "AR", "TOTAL"]
    assert rows[2]["tokens"] == ["20", "2"]


def test_state_rows_header_before_state_is_not_joined():
    lines = ["Sl No  State", "Sl No Andhra Pradesh  100  10"]
    rows = t.state_rows(lines, expected_numbers=2)
    assert len(rows) == 1 and rows[0]["unit_id"] == "AP_TG"
    assert rows[0]["raw_label"] == "Sl No Andhra Pradesh"


def test_state_rows_join_disabled_skips_split_names():
    lines = ["3 ARUNACHAL", "  PRADESH  20  2"]
    assert t.state_rows(lines, expected_numbers=2, join_split_names=False) == []


def test_state_rows_expected_numbers_trims_leading_tokens():
    rows = t.state_rows(["Bihar 2 217632 4006 1286 1"], expected_numbers=4)
    assert len(rows) == 1
    r = rows[0]
    assert r["tokens"] == ["217632", "4006", "1286", "1"]
    assert r["raw_label"] == "Bihar 2" and r["trimmed"] == 1


def test_state_rows_trimmed_is_zero_by_default():
    rows = t.state_rows(["Bihar  217632  4006"], expected_numbers=2)
    assert rows[0]["trimmed"] == 0


@pytest.mark.parametrize("line,expected,unit,tokens,trimmed,label_has", [
    ("Tamil Nadu 2  8,718,569 38,053 21,416 0", 4, "TN", ["8,718,569", "38,053", "21,416", "0"], 1, "Tamil Nadu 2"),
    ("Andaman & Nicobar Islands 2  100  10", 2, "AN", ["100", "10"], 1, "Islands 2"),
    ("Sikkim 2011  100  20", 2, "SK", ["100", "20"], 1, "Sikkim 2011"),
    ("Goa    500 — 3 4", 4, "GA", ["500", "—", "3", "4"], 0, None),
    ("Goa   500 20 3 *", 3, "GA", ["500", "20", "3"], 0, None),
    ("Lakshadweep   0 0 0 0", 4, "LD", ["0", "0", "0", "0"], 0, None),
    ("Delhi   100 2.5 3.4", 3, "DL", ["100", "2.5", "3.4"], 0, None),
    ("Dadra & Nagar Haveli and Daman & Diu   5 6 7", 3, "DNH_DD", ["5", "6", "7"], 0, None),
])
def test_state_rows_documented_shapes(line, expected, unit, tokens, trimmed, label_has):
    rows = t.state_rows([line], expected_numbers=expected)
    assert len(rows) == 1
    r = rows[0]
    assert r["unit_id"] == unit and r["tokens"] == tokens and r["trimmed"] == trimmed
    if label_has:
        assert label_has in r["raw_label"]


def test_state_rows_warns_on_resolved_row_with_too_few_values():
    with pytest.warns(UserWarning, match="Bihar"):
        rows = t.state_rows(["Bihar  7"], expected_numbers=2)
    assert rows == []


def test_state_rows_warns_on_resolved_label_with_no_values_not_joined():
    with pytest.warns(UserWarning, match="Bihar"):
        rows = t.state_rows(["Bihar", "Gujarat  10  20"], expected_numbers=2)
    assert [r["unit_id"] for r in rows] == ["GJ"]


def test_state_rows_no_warning_for_unresolved_labels_with_numbers():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rows = t.state_rows(["Some District  1  2", "Gujarat  10  20"], expected_numbers=2)
    assert [r["unit_id"] for r in rows] == ["GJ"] and not w


def test_state_rows_split_name_join_does_not_warn():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rows = t.state_rows(["3 ARUNACHAL", "  PRADESH  20  2"], expected_numbers=2)
    assert [r["unit_id"] for r in rows] == ["AR"] and not w


def test_pdf_lines_refuses_blocklisted_source():
    from pipeline.paths import BlockedSourceError
    with pytest.raises(BlockedSourceError):
        t.pdf_lines("india_dengue_monthly_real.csv")
