from __future__ import annotations
import json
from pathlib import Path
from evals.architecture.metrics import (
    dag_acyclic_check, max_file_loc, output_files_present,
)
from evals.architecture.runner import run


def test_dag_acyclic_check_true_for_valid_imports():
    # this codebase: no cycles allowed
    assert dag_acyclic_check(package_root=Path("src/irc")) is True


def test_max_file_loc_returns_int(tmp_path: Path):
    (tmp_path / "a.py").write_text("\n".join(["x = 1"] * 100))
    (tmp_path / "b.py").write_text("\n".join(["y = 1"] * 50))
    assert max_file_loc(tmp_path) == 100


def test_output_files_present(tmp_path: Path):
    out_dir = tmp_path / "outputs/2026-05-07"
    out_dir.mkdir(parents=True)
    for name in ("discovered_watchlist.csv", "scoring.json", "gold_regime.json",
                  "gold_band.yaml", "proposed_allocation.yaml", "trade_plan.yaml",
                  "memo.md"):
        (out_dir / name).touch()
    out = output_files_present(out_dir)
    assert out["completeness"] == 1.0


def test_output_files_present_uses_current_memo_name(tmp_path: Path):
    """Regression: producer writes memo.md (not research_memo.md). The
    completeness metric must look for the current name."""
    out_dir = tmp_path / "outputs/2026-05-07"
    out_dir.mkdir(parents=True)
    (out_dir / "memo.md").touch()
    out = output_files_present(out_dir)
    assert out["found"] >= 1.0


def test_architecture_runner_fails_when_input_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/architecture/report.json"))
    assert candidates, "runner must write a FAIL report"
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_architecture_runner_finds_latest_dated_dir_when_today_absent(tmp_path: Path):
    """When no outputs/<today>/ exists, the runner falls back to the latest
    dated output directory and writes the report under THAT date."""
    out_dir = tmp_path / "outputs/2026-05-07"
    out_dir.mkdir(parents=True)
    for name in ("discovered_watchlist.csv", "scoring.json", "gold_regime.json",
                  "gold_band.yaml", "proposed_allocation.yaml", "trade_plan.yaml",
                  "memo.md"):
        (out_dir / name).touch()
    rc = run(tmp_path)
    assert rc in (0, 1, 2)
    report_path = tmp_path / "outputs" / "2026-05-07" / "evals" / "architecture" / "report.json"
    assert report_path.exists(), "report must land under the evaluated artifact's date"
    body = json.loads(report_path.read_text(encoding="utf-8"))
    completeness = next(m for m in body["metrics"] if m["name"] == "output_files_completeness")
    assert completeness["value"] == 1.0
