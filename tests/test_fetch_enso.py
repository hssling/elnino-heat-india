from datetime import date

import pytest

from pipeline import enso
from pipeline import fetch_enso as fe


def oni_text(first=1950, last=2025):
    lines = ["SEAS  YR   TOTAL   ANOM"]
    for y in range(first, last + 1):
        for s in enso.SEASONS:
            lines.append(f"  {s} {y}  27.00   0.10")
    return "\n".join(lines) + "\n"


class Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


def _run(tmp_path, monkeypatch, oni_payload: bytes):
    ext = tmp_path / "external"
    ext.mkdir()
    (ext / "oni_snapshot.ascii.txt").write_text(oni_text(1950, 2026), encoding="utf-8")
    (ext / "dmi_snapshot.had.long.data").write_text("snapshot dmi\n", encoding="utf-8")
    recorded = []
    monkeypatch.setattr(fe.mf, "record", lambda path, url, **k: recorded.append((path.name, url)))
    monkeypatch.setattr(fe.requests, "get",
                        lambda url, timeout: Resp(oni_payload if url.endswith("oni.ascii.txt") else b"other\n"))
    out = fe.fetch(tmp_path / "raw", external=ext, today=date(2026, 10, 14))
    return out, dict(recorded)


def test_check_oni_accepts_full_record():
    fe.check_oni(oni_text(1950, 2026), today=date(2026, 10, 14))     # 924 seasons, 1950..2026


@pytest.mark.parametrize("text, why", [
    ("<html>Service unavailable</html>", "seasons"),
    (oni_text(1951, 2026), "first year"),
    (oni_text(1950, 2024), "last year"),
])
def test_check_oni_rejects_bad_content(text, why):
    with pytest.raises(ValueError, match=why):
        fe.check_oni(text, today=date(2026, 10, 14))


def test_fetch_falls_back_to_snapshot_when_download_content_is_bad(tmp_path, monkeypatch, capsys):
    out, rec = _run(tmp_path, monkeypatch, b"<html>maintenance</html>")
    assert out["oni.ascii.txt"].read_text(encoding="utf-8") == oni_text(1950, 2026)
    assert rec["oni.ascii.txt"].startswith("local-snapshot-after-download-error:InvalidONIFile")
    assert "used local snapshot" in capsys.readouterr().out


def test_fetch_keeps_valid_download(tmp_path, monkeypatch):
    good = oni_text(1950, 2026).replace("0.10", "0.20").encode()
    out, rec = _run(tmp_path, monkeypatch, good)
    assert out["oni.ascii.txt"].read_bytes() == good
    assert rec["oni.ascii.txt"] == fe.URLS["oni.ascii.txt"]


def test_fetch_falls_back_to_snapshot_on_malformed_season_line(tmp_path, monkeypatch, capsys):
    bad = oni_text(1950, 2026).replace("  MAM 1990  27.00   0.10", "  MAM 1990  27.00   n/a").encode()
    out, rec = _run(tmp_path, monkeypatch, bad)
    assert out["oni.ascii.txt"].read_text(encoding="utf-8") == oni_text(1950, 2026)
    assert rec["oni.ascii.txt"].startswith("local-snapshot-after-download-error:InvalidONIFile")
    assert fe.InvalidONIFile is enso.InvalidONIFile


def test_build_includes_roni_when_present_and_omits_when_absent(tmp_path):
    import pandas as pd
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "oni.ascii.txt").write_text(oni_text(2019, 2021))
    (raw / "dmi.had.long.data").write_text(" 2019 " + " ".join(["0.1"] * 12) + "\n")
    p = fe.build(raw, tmp_path / "out1")
    assert "roni" not in pd.read_csv(p["monthly"]).columns
    assert "roni_jjas" not in pd.read_csv(p["annual"]).columns
    (raw / "RONI.ascii.txt").write_text(
        "SEAS YR ANOM\n" + "".join(f"{s} 2020 0.{i}\n" for i, s in enumerate(enso.SEASONS)))
    p = fe.build(raw, tmp_path / "out2")
    m = pd.read_csv(p["monthly"])
    assert m.loc[(m.year == 2020) & (m.month == 8), "roni"].item() == pytest.approx(0.7)
    a = pd.read_csv(p["annual"]).set_index("year")
    assert a.loc[2020, "roni_jjas"] == pytest.approx((0.5 + 0.6 + 0.7 + 0.8) / 4)


def test_fetch_roni_failure_warns_and_continues(tmp_path, monkeypatch, capsys):
    out, rec = _run(tmp_path, monkeypatch, oni_text(1950, 2026).encode())
    assert "RONI.ascii.txt" not in out
    assert "RONI" in capsys.readouterr().out
