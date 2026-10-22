import pytest

from pipeline import copy_external, manifest
from pipeline.paths import BlockedSourceError


def test_copy_all_copies_files_and_dirs_and_records(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.csv").write_text("x\n1\n")
    (src / "pts").mkdir()
    (src / "pts" / "p1.json").write_text("{}")
    dest = tmp_path / "ext"
    m = tmp_path / "M.csv"
    out = copy_external.copy_all(
        {"a.csv": str(src / "a.csv"), "pts": str(src / "pts")}, dest=dest, manifest=m
    )
    assert (dest / "a.csv").read_text() == "x\n1\n"
    assert (dest / "pts" / "p1.json").exists()
    urls = {r["url"] for r in manifest.read(m)}
    assert f"file:{src / 'a.csv'}" in urls
    assert len(out) == 2


def test_copy_all_refuses_blocklisted(tmp_path):
    bad = tmp_path / "dengue_climate_india.csv"
    bad.write_text("x")
    with pytest.raises(BlockedSourceError):
        copy_external.copy_all({"d.csv": str(bad)}, dest=tmp_path / "e", manifest=tmp_path / "M.csv")
