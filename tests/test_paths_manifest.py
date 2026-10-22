import csv
from pathlib import Path

import pytest

from pipeline import manifest, paths


def test_blocklist_rejects_synthetic_sources():
    bad = Path("elsewhere") / "x" / "data" / "climate_india_2000_2023.csv"
    with pytest.raises(paths.BlockedSourceError):
        paths.check_source(bad)


def test_blocklist_allows_real_sources(tmp_path):
    ok = tmp_path / "malaria_india_official_1995_2025.csv"
    assert paths.check_source(ok) == ok


def test_manifest_record_upserts_and_marks_deleted(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    m = tmp_path / "MANIFEST.csv"
    row = manifest.record(f, "https://example.org/a", manifest=m)
    assert row["sha256"] == manifest.sha256_file(f)
    assert row["bytes"] == "3" and row["deleted"] == "0"
    f.write_bytes(b"abcd")
    manifest.record(f, "https://example.org/a", manifest=m)
    rows = manifest.read(m)
    assert len(rows) == 1 and rows[0]["bytes"] == "4"
    manifest.mark_deleted(f, manifest=m)
    assert manifest.read(m)[0]["deleted"] == "1"
    with open(m, newline="") as fh:
        assert next(csv.reader(fh)) == manifest.FIELDS


def test_month_table_resolves_csv_or_gz(tmp_path):
    from pipeline.paths import month_table
    assert month_table("state", tmp_path) == tmp_path / "climate_state_month.csv"
    (tmp_path / "climate_state_month.csv").write_text("a")
    assert month_table("state", tmp_path).name == "climate_state_month.csv"
    (tmp_path / "climate_district_month.csv.gz").write_bytes(b"x")
    assert month_table("district", tmp_path).name == "climate_district_month.csv.gz"


def test_month_table_raises_when_both_forms_exist(tmp_path):
    from pipeline.paths import month_table
    (tmp_path / "climate_district_month.csv").write_text("a")
    (tmp_path / "climate_district_month.csv.gz").write_bytes(b"x")
    with pytest.raises(ValueError, match="climate_district_month.csv.*climate_district_month.csv.gz"):
        month_table("district", tmp_path)


def test_retrieval_date_latest_of_listed_paths(tmp_path):
    from datetime import date
    m = tmp_path / "MANIFEST.csv"
    rows = [{"path": "data/external/a.csv", "url": "u", "retrieved_utc": "2026-10-14T05:34:17Z", "sha256": "x",
             "bytes": "1", "deleted": "0"},
            {"path": "data/external/b.csv", "url": "u", "retrieved_utc": "2026-10-16T01:00:00Z", "sha256": "x",
             "bytes": "1", "deleted": "0"}]
    manifest._write(rows, m)
    assert manifest.retrieval_date(["data/external/a.csv"], m) == date(2026, 10, 14)
    assert manifest.retrieval_date(["data/external/a.csv", "data/external/b.csv"], m) == date(2026, 10, 16)
    with pytest.raises(KeyError, match="c.csv"):
        manifest.retrieval_date(["data/external/c.csv"], m)
