"""Common long-format record schema for all outcome parsers."""
import pandas as pd

from pipeline.outcomes.states import UNITS

COLUMNS = ["unit_id", "raw_label", "year", "variable", "value", "source_id", "provisional"]
# Ruling P17: a record of a year that its document marks as covering only part of the year ("2006**
# Report received till 25th November", "*Till 13.9.2023", "*Upto October") carries this suffix in
# raw_label (and provisional=True). Assembly masks such a cell through a reviewed row whenever the
# partial-year value would be the chosen one (gate outcome_partial_year).
PARTIAL_YEAR = " [partial_year]"


def partial_label(label: str) -> str:
    """raw_label of a partial-year record."""
    return label if is_partial(label) else f"{label}{PARTIAL_YEAR}"


def is_partial(label) -> bool:
    return PARTIAL_YEAR.strip() in str(label)


def make(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)
    df["provisional"] = df["provisional"].astype(bool)
    return df


def validate(df: pd.DataFrame) -> None:
    bad = set(df.unit_id) - set(UNITS) - {"TOTAL"}
    if bad:
        raise ValueError(f"unknown unit ids: {sorted(bad)}")
    if not pd.api.types.is_integer_dtype(df.year):
        raise ValueError("year must be integer")
    if (df.value.dropna() < 0).any():
        raise ValueError("negative values")
    key = ["unit_id", "raw_label", "year", "variable", "source_id"]
    if df.duplicated(key).any():
        raise ValueError(f"duplicate records: {df[df.duplicated(key, keep=False)][key].values[:5]}")
