import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.run([sys.executable, "-m", "experiment.excel_extractor", *args], cwd=BACKEND, capture_output=True, text=True)


def test_inspect_prints_counts_and_no_content(fx):
    r = run("inspect", str(fx["radar"]), "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["sheets"][0]["pictures"]["in_cell"] == 10
    assert "Radar Market Study" not in r.stdout and "BOSCH" not in r.stdout  # no cell text leaves in inspect output
    assert "req" not in r.stdout.lower() or "00165101" not in r.stdout


def test_extract_writes_all_outputs(fx, tmp_path):
    out = tmp_path / "out"
    r = run("extract", str(fx["radar"]), "--out", str(out))
    assert r.returncode == 0, r.stderr
    for name in ("model.json", "layout.json", "report.html"):
        assert (out / name).exists()
    assert any((out / "cells").iterdir()) and any((out / "media").iterdir())


def test_compare_runs_with_app_on_path(fx):
    r = run("compare", str(fx["radar"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "in-cell pictures the old reader ignored" in r.stdout


def test_errors_are_one_readable_line(tmp_path):
    r = run("extract", str(tmp_path / "missing.xlsx"), "--out", str(tmp_path / "o"))
    assert r.returncode == 1 and r.stdout.startswith("error:") and "Traceback" not in r.stdout
