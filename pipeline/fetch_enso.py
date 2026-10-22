"""Download NOAA ENSO/IOD indices (fallback: local snapshots) and build ENSO tables."""
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from pipeline import enso
from pipeline import manifest as mf
from pipeline.paths import DERIVED, EXTERNAL, RAW

URLS = {
    "oni.ascii.txt": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
    "ersst5.nino.mth.91-20.ascii": "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii",
    "dmi.had.long.data": "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data",
    "RONI.ascii.txt": "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
}
SNAPSHOTS = {"oni.ascii.txt": "oni_snapshot.ascii.txt", "dmi.had.long.data": "dmi_snapshot.had.long.data"}


InvalidONIFile = enso.InvalidONIFile   # raised by enso.parse_oni_text and check_oni; triggers the snapshot fallback


def check_oni(text: str, today: date | None = None, min_seasons=900) -> None:
    """Raise InvalidONIFile unless the ONI text has >= min_seasons seasons, starts in 1950 and
    reaches at least the previous calendar year."""
    today = today or date.today()
    o = enso.parse_oni_text(text)
    if len(o) < min_seasons:
        raise InvalidONIFile(f"ONI file has {len(o)} seasons (< {min_seasons})")
    if int(o.year.min()) != 1950:
        raise InvalidONIFile(f"ONI file first year {int(o.year.min())} != 1950")
    if int(o.year.max()) < today.year - 1:
        raise InvalidONIFile(f"ONI file last year {int(o.year.max())} < {today.year - 1}")


def _looks_like_roni(content: bytes) -> bool:
    lines = (ln.split() for ln in content.decode("utf-8", errors="replace").splitlines())
    return sum(1 for p in lines if len(p) in (3, 4) and p[0] in enso.SEASONS) >= 12


def fetch(raw_dir=RAW / "enso", external=EXTERNAL, today: date | None = None) -> dict[str, Path]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, url in URLS.items():
        dest = raw_dir / name
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            if name == "oni.ascii.txt":
                check_oni(r.content.decode("utf-8", errors="replace"), today)
            elif name == "RONI.ascii.txt" and not _looks_like_roni(r.content):
                raise InvalidONIFile("RONI content has too few season rows")
            dest.write_bytes(r.content)
            mf.record(dest, url)
        except (requests.RequestException, InvalidONIFile) as e:
            snap = SNAPSHOTS.get(name)
            if name == "RONI.ascii.txt":      # optional series: no snapshot, continue without it
                print(f"WARNING: RONI download failed ({e}); continuing without RONI")
                continue
            if snap is None:
                raise
            shutil.copy2(Path(external) / snap, dest)
            mf.record(dest, f"local-snapshot-after-download-error:{type(e).__name__}")
            print(f"WARNING: {name} download failed ({e}); used local snapshot")
        out[name] = dest
    return out


def build(raw_dir=RAW / "enso", out_dir=DERIVED) -> dict[str, Path]:
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    c = enso.classify(enso.parse_oni(raw_dir / "oni.ascii.txt"))
    monthly = c.rename(columns={"anom": "oni_anom", "total": "oni_total"})
    if (raw_dir / "ersst5.nino.mth.91-20.ascii").exists():
        monthly = monthly.merge(enso.parse_nino34(raw_dir / "ersst5.nino.mth.91-20.ascii"), on=["year", "month"], how="left")
    monthly = monthly.merge(enso.parse_dmi(raw_dir / "dmi.had.long.data"), on=["year", "month"], how="left")
    roni = None
    if (raw_dir / "RONI.ascii.txt").exists():
        roni = enso.parse_roni(raw_dir / "RONI.ascii.txt")
        monthly = monthly.merge(roni[["year", "month", "roni"]], on=["year", "month"], how="left")
    extra = monthly[["year", "month", "nino34_anom", "dmi"]] if "nino34_anom" in monthly.columns else None
    paths = {
        "monthly": out_dir / "enso_monthly.csv",
        "episodes": out_dir / "enso_episodes.csv",
        "annual": out_dir / "enso_annual.csv",
    }
    monthly.to_csv(paths["monthly"], index=False)
    enso.episodes(c).to_csv(paths["episodes"], index=False)
    enso.annual(c, roni=roni, monthly_extra=extra).to_csv(paths["annual"], index=False)
    return paths


if __name__ == "__main__":
    fetch()
    for k, p in build().items():
        print(k, p, len(pd.read_csv(p)), "rows")
