import run_all


def test_steps_order_and_skip_download(monkeypatch):
    called = []
    monkeypatch.setattr(run_all, "STEPS", [(n, (lambda n=n: lambda a: called.append(n))()) for n in
                                           ["copy_external", "fetch_enso", "imd", "assemble", "annual", "power", "validate"]])
    monkeypatch.setattr(run_all, "DOWNLOAD_STEPS", {"copy_external", "fetch_enso", "imd"})
    monkeypatch.setattr(run_all, "_gates_ok", lambda: True)
    assert run_all.main(["--skip-download"]) == 0
    assert called == ["assemble", "annual", "power", "validate"]


def test_real_steps_structure():
    names = [n for n, _ in run_all.STEPS]
    assert run_all.DOWNLOAD_STEPS <= set(names)
    assert "enso_build" in names and "enso_build" not in run_all.DOWNLOAD_STEPS
    assert names.index("enso_build") == names.index("fetch_enso") + 1
    assert names[-1] == "validate"
    assert names.index("nearzero") == names.index("annual") + 1 and "nearzero" not in run_all.DOWNLOAD_STEPS
    assert names.index("climate_units") == names.index("nearzero") + 1 and "climate_units" not in run_all.DOWNLOAD_STEPS
    assert names.index("climate_units") > names.index("annual")
    assert names.index("outcomes") == names.index("power") + 1 and "outcomes" in run_all.DOWNLOAD_STEPS
    assert names.index("model_inputs") == names.index("outcomes") + 1 and "model_inputs" not in run_all.DOWNLOAD_STEPS


def test_main_returns_1_when_gates_fail(monkeypatch):
    monkeypatch.setattr(run_all, "STEPS", [])
    monkeypatch.setattr(run_all, "_gates_ok", lambda: False)
    assert run_all.main(["--skip-download"]) == 1
