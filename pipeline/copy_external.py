"""Copy user-supplied third-party files into data/external/ and record them in the MANIFEST.

These inputs are not redistributed in this repository. Obtain each one from its publisher (origins in
EXTERNAL_FILES and in README.md), put them together in one folder and set the environment variable
ELNINO_EXTERNAL_SOURCE_DIR to that folder (a "power_points" sub-folder holds the NASA POWER JSON files),
or place them directly under data/external/. With the variable unset, copy_all() copies nothing.
"""
import os
import shutil
from pathlib import Path

from pipeline import manifest as mf
from pipeline.paths import EXTERNAL, MANIFEST_PATH, check_source

EXTERNAL_FILES = {
    "gadm41_IND.gpkg": "GADM 4.1 India boundaries, https://gadm.org/download_country.html (GADM licence)",
    "malaria_india_official_1995_2025.csv": "national annual malaria counts transcribed from NCVBDC "
                                            "publications (cross-check only)",
    "dengue_india_national_searo.csv": "WHO SEARO national dengue series for India (cross-check only)",
    "opendengue_india_admin1_year.csv": "OpenDengue India records aggregated to admin-1 x year "
                                        "(https://opendengue.org, CC BY 4.0)",
    "oni_snapshot.ascii.txt": "snapshot of https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt "
                              "(fallback if the download fails)",
    "dmi_snapshot.had.long.data": "snapshot of https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data "
                                  "(fallback if the download fails)",
    "climate_grid_points.csv": "NASA POWER grid points (lat, lon) used for the POWER cross-check",
    "power_points": "NASA POWER monthly point JSON files power_*.json (https://power.larc.nasa.gov/)",
}


def _default_sources() -> dict:
    d = os.environ.get("ELNINO_EXTERNAL_SOURCE_DIR", "")
    return {name: str(Path(d) / name) for name in EXTERNAL_FILES} if d else {}


SOURCES = _default_sources()


def copy_all(sources=None, dest=EXTERNAL, manifest=MANIFEST_PATH) -> list[Path]:
    sources = SOURCES if sources is None else sources
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for name, src in sources.items():
        s = check_source(src)
        target = dest / name
        if s.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for f in sorted(s.iterdir()):
                if f.is_file() and (name != "power_points" or f.name.startswith("power_")):
                    check_source(f)
                    shutil.copy2(f, target / f.name)
                    mf.record(target / f.name, f"file:{f}", manifest=manifest)
        else:
            shutil.copy2(s, target)
            mf.record(target, f"file:{s}", manifest=manifest)
        out.append(target)
    if not sources:
        absent = [n for n in EXTERNAL_FILES if not (dest / n).exists()]
        if absent:
            print("copy_external: ELNINO_EXTERNAL_SOURCE_DIR not set; not in data/external/:", ", ".join(absent))
    return out


if __name__ == "__main__":
    for p in copy_all():
        print("copied", p)
