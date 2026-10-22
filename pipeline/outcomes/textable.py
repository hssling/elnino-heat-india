"""Generic helpers for extracting state rows from PDF/HTML text tables.

Rule (controller ruling P3): a row's values are the MAXIMAL trailing run of
numeric-like whitespace-separated tokens; the label is the text before them.
Standalone footnote marks are removed first. No column-gap requirement is applied.

Known ambiguity: a number-like word glued to a label ("Islands 2", "Sikkim 2011")
is swept into the values. state_rows resolves this with expected_numbers: extra
LEADING tokens are moved back into the label and counted in row["trimmed"].
"""
import math
import re
import subprocess
import warnings

from pipeline.outcomes import states
from pipeline.paths import check_source

_NUMTOK = re.compile(r"^(?:[-–—]|NR|NA|N\.A\.|Nil|\(?P\)?|\d[\d,]*(?:\.\d+)?[*P#@$†‡]*)$", re.I)
_FOOTNOTE = re.compile(r"\s+[*#@$†‡]+(?=\s|$)")   # standalone footnote mark: dropped


def parse_number(tok: str, dash: str = "nan") -> float:
    s = str(tok).strip()
    if s.lower() in ("-", "–", "—", "nil") and dash == "zero":
        return 0.0
    s = re.sub(r"[*#@$†‡]|\(?P\)?$", "", s, flags=re.I).replace(",", "").strip()
    if s == "" or s.upper() in ("-", "–", "—", "NR", "NA", "N.A.", "NIL"):
        return math.nan
    return float(s)


def pdf_lines(path) -> list[str]:
    check_source(path)
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True)
    return out.stdout.decode("utf-8", errors="replace").splitlines()


def split_row(line: str) -> tuple[str, list[str]]:
    """(label, trailing numeric-like tokens). Label keeps its words, single-spaced."""
    words = _FOOTNOTE.sub("", line).split()
    k = len(words)
    while k > 0 and _NUMTOK.match(words[k - 1]):
        k -= 1
    return " ".join(words[:k]), words[k:]


def _row(uid, label, toks, expected_numbers):
    trimmed = len(toks) - expected_numbers
    if trimmed > 0:
        label = f"{label} {' '.join(toks[:trimmed])}".strip()
        toks = toks[trimmed:]
    else:
        trimmed = 0
    return {"unit_id": uid, "raw_label": label, "tokens": toks, "trimmed": trimmed}


def state_rows(lines, expected_numbers: int, join_split_names: bool = True) -> list[dict]:
    """Rows whose label resolves to a unit (or TOTAL), with their values.

    - Values: see split_row. If a resolved row has MORE than expected_numbers tokens,
      the extra leading tokens move into raw_label and row["trimmed"] is set to their
      count (0 otherwise). FEWER tokens: warnings.warn and the row is dropped.
    - A label that does not resolve alone is joined with a numberless line directly
      above it when the joined text resolves ("3 ARUNACHAL" + "  PRADESH  20  2").
      A line that resolves by itself always wins over a join.
    - Unresolved labels with numbers are ignored silently (district rows); the
      national-total gate catches losses.
    """
    rows, pending, pending_uid = [], None, None

    def flush():
        nonlocal pending, pending_uid
        if pending_uid is not None:
            warnings.warn(f"state row {pending!r} resolves to a unit but has no values "
                          f"(expected {expected_numbers}); skipped", UserWarning, stacklevel=3)
        pending, pending_uid = None, None

    for line in lines:
        label, toks = split_row(line)
        uid = states.resolve(label) if label else None
        n = len(toks)
        if uid and n >= expected_numbers:
            flush()
            rows.append(_row(uid, label, toks, expected_numbers))
            continue
        if pending is not None and n >= expected_numbers:
            joined = f"{pending} {label}".strip()
            juid = states.resolve(joined)
            if juid:
                pending, pending_uid = None, None
                rows.append(_row(juid, joined, toks, expected_numbers))
                continue
        flush()
        if uid and n:
            warnings.warn(f"state row {label!r} resolves to a unit but has {n} value(s) "
                          f"(expected {expected_numbers}); skipped", UserWarning, stacklevel=2)
        elif join_split_names and n == 0 and label:
            pending, pending_uid = label, uid
    flush()
    return rows
