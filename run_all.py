"""Phase-1 orchestrator: rebuild the shared ENSO/climate layer and run validation gates."""
import argparse
import sys
from datetime import date

from pipeline import build_climate, climate_annual, climate_units, copy_external, fetch_enso, model_inputs, power, qc_nearzero, validate
from pipeline.outcomes import assemble


def _imd(a):
    years = list(range(a.start, a.end + 1))
    build_climate.build_temperature(years)
    build_climate.build_rain(years)


STEPS = [
    ("copy_external", lambda a: copy_external.copy_all()),
    ("fetch_enso", lambda a: fetch_enso.fetch()),
    ("enso_build", lambda a: fetch_enso.build()),
    ("imd", _imd),
    ("assemble", lambda a: build_climate.assemble()),
    ("annual", lambda a: climate_annual.build_all()),
    ("nearzero", lambda a: qc_nearzero.build()),
    ("climate_units", lambda a: climate_units.build()),
    ("power", lambda a: power.build()),
    ("outcomes", lambda a: assemble.build_all()),
    ("model_inputs", lambda a: model_inputs.build()),
    ("validate", lambda a: None),
]
# "outcomes" parses the cached raw outcome files and downloads the missing ones
DOWNLOAD_STEPS = {"copy_external", "fetch_enso", "imd", "outcomes"}


def _gates_ok() -> bool:
    res = validate.run_all()
    for r in res:
        print(validate.format_result(r))
    return all(r.passed for r in res)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--start", type=int, default=1981)
    ap.add_argument("--end", type=int, default=date.today().year - 1)
    a = ap.parse_args(argv)
    for name, fn in STEPS:
        if a.skip_download and name in DOWNLOAD_STEPS:
            continue
        print(f"== {name}")
        fn(a)
    return 0 if _gates_ok() else 1


if __name__ == "__main__":
    sys.exit(main())
