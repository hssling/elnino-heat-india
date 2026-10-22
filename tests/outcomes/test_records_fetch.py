from pathlib import Path

import pandas as pd
import pytest

from pipeline.outcomes import fetch, records


def test_records_make_and_validate():
    df = records.make([{"unit_id": "OD", "raw_label": "Orissa", "year": 2010, "variable": "cases",
                        "value": 357320.0, "source_id": "up2011", "provisional": False}])
    assert list(df.columns) == records.COLUMNS
    records.validate(df)
    bad = df.assign(unit_id="XX")
    with pytest.raises(ValueError):
        records.validate(bad)
    with pytest.raises(ValueError):
        records.validate(pd.concat([df, df]))


def test_validate_rejects_negative_and_non_int_year():
    df = records.make([{"unit_id": "OD", "raw_label": "Orissa", "year": 2010, "variable": "cases",
                        "value": 1.0, "source_id": "s", "provisional": False}])
    with pytest.raises(ValueError):
        records.validate(df.assign(value=-1.0))
    with pytest.raises(ValueError):
        records.validate(df.assign(year=2010.5))


def test_validate_allows_nan_and_total():
    df = records.make([
        {"unit_id": "TOTAL", "raw_label": "Total", "year": 2010, "variable": "cases",
         "value": float("nan"), "source_id": "s", "provisional": False},
    ])
    records.validate(df)


def test_wayback_url():
    assert fetch.wayback("http://nvbdcp.gov.in/Doc/x.pdf", 2012) == \
        "https://web.archive.org/web/2012id_/http://nvbdcp.gov.in/Doc/x.pdf"


class Resp:
    def __init__(self, content, status=200):
        self.content, self.status_code = content, status


def test_fetch_caches_and_records(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    calls = []
    rows = []

    def fake_record(p, u, **k):
        calls.append(u)
        rows.append({"path": fetch.mf._key(p)})
    monkeypatch.setattr(fetch.mf, "record", fake_record)
    monkeypatch.setattr(fetch.mf, "read", lambda *a, **k: list(rows))
    seen = {}

    class S:
        def get(self, url, headers, timeout):
            assert "Mozilla" in headers["User-Agent"]
            seen["timeout"] = timeout
            return Resp(b"%PDF-1.4 data")
    p1 = fetch.get("srcA", "https://x.org/a.pdf", session=S(), sleep=lambda s: None)
    p2 = fetch.get("srcA", "https://x.org/a.pdf", session=None, sleep=lambda s: None)  # cached: no session needed
    assert p1 == p2 and p1.read_bytes() == b"%PDF-1.4 data" and calls == ["https://x.org/a.pdf"]
    assert seen["timeout"] == (30, 300)
    assert p1 == tmp_path / "srcA" / "a.pdf"


def test_cache_hit_rejects_bad_pdf_magic(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)
    d = tmp_path / "srcA"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"<html>cached error page</html>")
    with pytest.raises(fetch.FetchError):
        fetch.get("srcA", "https://x.org/a.pdf", session=None, sleep=lambda s: None)


def test_cache_hit_records_manifest_when_row_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "read", lambda *a, **k: [])
    calls = []
    monkeypatch.setattr(fetch.mf, "record", lambda p, u, **k: calls.append((p, u)))
    d = tmp_path / "srcA"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"%PDF-1.4 cached")
    fetch.get("srcA", "https://x.org/a.pdf", session=None, sleep=lambda s: None)
    assert calls == [(d / "a.pdf", "https://x.org/a.pdf")]


def test_cache_hit_no_manifest_write_when_row_present(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    d = tmp_path / "srcA"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"%PDF-1.4 cached")
    monkeypatch.setattr(fetch.mf, "read", lambda *a, **k: [{"path": fetch.mf._key(d / "a.pdf")}])
    calls = []
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: calls.append(a))
    fetch.get("srcA", "https://x.org/a.pdf", session=None, sleep=lambda s: None)
    assert calls == []


def test_kind_html_checks_magic(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)

    class Good:
        def get(self, url, headers, timeout):
            return Resp(b"<!DOCTYPE html><html>ok</html>")

    class Bad:
        def get(self, url, headers, timeout):
            return Resp(b"plain text, no markup")
    p = fetch.get("srcH", "https://x.org/page", kind="html", session=Good(), sleep=lambda s: None)
    assert p.name == "page"
    with pytest.raises(fetch.FetchError):
        fetch.get("srcH", "https://x.org/other", kind="html", session=Bad(), sleep=lambda s: None)


def test_kind_pdf_checks_magic_without_pdf_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)

    class S:
        def get(self, url, headers, timeout):
            return Resp(b"<html>error</html>")
    with pytest.raises(fetch.FetchError):
        fetch.get("srcP", "https://x.org/download?id=7", kind="pdf", session=S(), sleep=lambda s: None)


def test_same_basename_different_url_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)

    class S:
        def get(self, url, headers, timeout):
            return Resp(b"%PDF-1.4 x")
    fetch.get("srcC", "https://a.org/report.pdf", session=S(), sleep=lambda s: None)
    with pytest.raises(ValueError, match="report.pdf"):
        fetch.get("srcC", "https://b.org/report.pdf", session=S(), sleep=lambda s: None)
    # an explicit filename bypasses the clash check
    p = fetch.get("srcC", "https://b.org/report.pdf", filename="b_report.pdf", session=S(),
                  sleep=lambda s: None)
    assert p.name == "b_report.pdf"
    # same URL again is fine (cache hit, no session needed)
    assert fetch.get("srcC", "https://a.org/report.pdf", session=None, sleep=lambda s: None).name == "report.pdf"


def test_fetch_rejects_html_error_page_for_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)

    class S:
        def get(self, url, headers, timeout):
            return Resp(b"<html>not found</html>")
    with pytest.raises(fetch.FetchError):
        fetch.get("srcA", "https://x.org/a.pdf", session=S(), sleep=lambda s: None)


def test_fetch_retries_then_fails_on_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(fetch.mf, "record", lambda *a, **k: None)
    attempts, sleeps = [], []

    class S:
        def get(self, url, headers, timeout):
            attempts.append(url)
            return Resp(b"", status=503)
    with pytest.raises(fetch.FetchError, match="HTTP 503"):
        fetch.get("srcA", "https://x.org/a.pdf", session=S(), sleep=sleeps.append)
    assert len(attempts) == 4 and sleeps == [5, 10, 15, 20]
    assert not (tmp_path / "srcA" / "a.pdf").exists()


def _fake_manifest(monkeypatch, tmp_path):
    rows = []
    monkeypatch.setattr(fetch, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(fetch.mf, "read", lambda *a, **k: rows)
    monkeypatch.setattr(fetch.mf, "record", lambda p, url, *a, **k: rows.append(
        {"path": fetch.mf._key(p), "url": url, "sha256": fetch.mf.sha256_file(p)}))
    return rows


def test_local_copy_recopies_on_hash_change(tmp_path, monkeypatch):
    rows = _fake_manifest(monkeypatch, tmp_path)
    src = tmp_path / "Malaria_Annual_Report_2099.pdf"
    src.write_bytes(b"%PDF-1 a")
    dest = fetch.local_copy("mal_ar_2099", src)
    assert dest == tmp_path / "raw" / "mal_ar_2099" / src.name
    assert dest.read_bytes() == b"%PDF-1 a" and len(rows) == 1
    assert fetch.manifest_sha(dest) == fetch.mf.sha256_file(src)
    fetch.local_copy("mal_ar_2099", src)
    assert len(rows) == 1                                             # unchanged: no new record
    src.write_bytes(b"%PDF-1 b")                                      # same size, new content
    fetch.local_copy("mal_ar_2099", src)
    assert dest.read_bytes() == b"%PDF-1 b" and len(rows) == 2


def test_local_copy_missing_source_raises_dedicated_error(tmp_path, monkeypatch):
    _fake_manifest(monkeypatch, tmp_path)
    with pytest.raises(fetch.LocalSourceMissing, match="nope.pdf"):
        fetch.local_copy("x", tmp_path / "nope.pdf")
    assert not issubclass(fetch.LocalSourceMissing, fetch.FetchError)


def test_local_copy_falls_back_to_manifest_verified_cache(tmp_path, monkeypatch):
    rows = _fake_manifest(monkeypatch, tmp_path)
    src = tmp_path / "ext" / "ADSI_2099.pdf"
    src.parent.mkdir()
    src.write_bytes(b"%PDF-1 a")
    dest = fetch.local_copy("ncrb_2099", src)                         # original present: copied + recorded
    src.unlink()                                                      # external drive absent
    assert fetch.local_copy("ncrb_2099", src) == dest and len(rows) == 1
    dest.write_bytes(b"%PDF-1 X")                                     # cache no longer matches its MANIFEST row
    with pytest.raises(fetch.CacheIntegrityError, match="SHA-256"):
        fetch.local_copy("ncrb_2099", src)
    assert not issubclass(fetch.CacheIntegrityError, FileNotFoundError)   # never skipped as a missing source
    rows.clear()                                                      # cached copy without a MANIFEST row
    with pytest.raises(fetch.CacheIntegrityError, match="MANIFEST"):
        fetch.local_copy("ncrb_2099", src)
    dest.unlink()                                                     # neither original nor cache
    with pytest.raises(fetch.LocalSourceMissing):
        fetch.local_copy("ncrb_2099", src)
