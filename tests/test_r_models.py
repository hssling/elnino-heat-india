import shutil
import subprocess
from pathlib import Path

import pytest

MODELS = Path(__file__).resolve().parents[1] / "models"
pytestmark = [pytest.mark.r,
              pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not on PATH")]


def run_r(args, timeout=3600):
    return subprocess.run(["Rscript", *args], cwd=MODELS, capture_output=True, text=True, timeout=timeout)


def test_r_common_suite():
    p = run_r(["common/tests/run.R"])
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-4000:]


def test_r_results_json_written(tmp_path):
    out = tmp_path / "results.json"
    code = ('source("common/R/load.R"); write_results(list(`C.k` = res_entry(2, fmt_int(1234567), '
            '"models/C/x.R", "d")), commandArgs(TRUE)[1])')
    p = run_r(["-e", code, str(out)])
    assert p.returncode == 0, p.stderr[-2000:]
    import json
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["C.k"]["display"] == "1,234,567" and res["C.k"]["value"] == 2
