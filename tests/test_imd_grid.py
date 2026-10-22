import numpy as np
import pytest
import requests

from pipeline import imd_grid


class FakeResp:
    def __init__(self, content, status=200):
        self.content, self.status_code = content, status


def test_grid_coordinates():
    assert imd_grid.RAIN.lats[0] == 6.5 and imd_grid.RAIN.lats[-1] == 38.5
    assert imd_grid.RAIN.lons[-1] == 100.0
    assert imd_grid.TEMP.lons[0] == 67.5 and imd_grid.TEMP.lats[-1] == 37.5


def test_expected_bytes_handles_leap_years():
    assert imd_grid.expected_bytes("tmax", 2023) == 365 * 31 * 31 * 4  # 1,403,060 (verified on IMD file)
    assert imd_grid.expected_bytes("rain", 2024) == 366 * 129 * 135 * 4


def test_download_retries_until_size_is_right(tmp_path, monkeypatch):
    monkeypatch.setattr(imd_grid.mf, "record", lambda *a, **k: None)
    good = b"\x00" * imd_grid.expected_bytes("tmax", 2023)
    calls = iter([FakeResp(b"<html>error</html>"), requests.ConnectionError("reset"), FakeResp(good)])

    def post(url, data, timeout):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    p = imd_grid.download("tmax", 2023, tmp_path, post=post, sleep=lambda s: None)
    assert p.name == "tmax_2023.grd" and p.stat().st_size == len(good)


def test_download_retries_on_chunked_encoding_error(tmp_path, monkeypatch):
    monkeypatch.setattr(imd_grid.mf, "record", lambda *a, **k: None)
    good = b"\x00" * imd_grid.expected_bytes("tmax", 2023)
    calls = iter([requests.exceptions.ChunkedEncodingError("mid-body reset"), FakeResp(good)])

    def post(url, data, timeout):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    p = imd_grid.download("tmax", 2023, tmp_path, post=post, sleep=lambda s: None)
    assert p.stat().st_size == len(good)


def test_download_gives_up_and_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(imd_grid.mf, "record", lambda *a, **k: None)
    post = lambda url, data, timeout: FakeResp(b"short")
    with pytest.raises(imd_grid.IMDDownloadError):
        imd_grid.download("tmax", 2023, tmp_path, post=post, sleep=lambda s: None, retries=3)
    assert not (tmp_path / "tmax_2023.grd").exists()


def test_read_masks_missing_and_keeps_orientation(tmp_path):
    g = imd_grid.TEMP
    arr = np.full((366, g.nlat, g.nlon), 30.0, dtype="<f4")
    arr[0, 0, 0] = 99.9          # missing (south-west corner)
    arr[0, g.nlat - 1, 0] = 12.0  # north-west corner marker
    f = tmp_path / "tmax_2024.grd"
    arr.tofile(f)
    out = imd_grid.read("tmax", f, 2024)
    assert out.shape == (366, 31, 31)
    assert np.isnan(out[0, 0, 0]) and out[0, 30, 0] == 12.0


def test_read_rejects_wrong_size(tmp_path):
    f = tmp_path / "rain_2023.grd"
    f.write_bytes(b"\x00" * 100)
    with pytest.raises(ValueError):
        imd_grid.read("rain", f, 2023)


@pytest.mark.network
def test_live_tmax_download(tmp_path, monkeypatch):
    real_record = imd_grid.mf.record
    monkeypatch.setattr(
        imd_grid.mf, "record",
        lambda path, url, **k: real_record(path, url, manifest=tmp_path / "manifest.csv"),
    )
    p = imd_grid.download("tmax", 2023, tmp_path, sleep=lambda s: None)
    a = imd_grid.read("tmax", p, 2023)
    assert 25 < np.nanmean(a) < 35
