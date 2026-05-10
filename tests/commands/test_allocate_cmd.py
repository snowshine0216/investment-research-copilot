from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from unittest.mock import patch
import pytest
import yaml
from irc.allocation.pipeline import AllocationOutput
from irc.commands.init_cmd import run_init
from irc.commands.allocate_cmd import run_allocate


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


@pytest.fixture
def repo_with_scoring(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    today = _today()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps({
        "scores": [
            {"instrument_id": "VTI", "asset_class": "us_etf", "composite_score": 78,
             "action": "buy_candidate", "conviction": "med", "role": "core_us_equity"},
            {"instrument_id": "510300", "asset_class": "cn_etf", "composite_score": 70,
             "action": "buy_candidate", "conviction": "med", "role": "core_cn_equity"},
        ]
    }), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(json.dumps({"tilt": "neutral"}), encoding="utf-8")
    return tmp_path


def test_allocate_writes_yaml(repo_with_scoring: Path):
    rc = run_allocate(repo_root=str(repo_with_scoring))
    assert rc == 0
    assert (repo_with_scoring / "outputs" / _today() / "proposed_allocation.yaml").exists()


def test_allocate_preserves_roles_in_yaml(repo_with_scoring: Path) -> None:
    rc = run_allocate(repo_root=str(repo_with_scoring))

    assert rc == 0
    payload = yaml.safe_load(
        (repo_with_scoring / "outputs" / _today() / "proposed_allocation.yaml").read_text(
            encoding="utf-8"
        )
    )
    roles_by_id = {
        row["instrument_id"]: row["role"]
        for row in payload["selected_instruments"]
    }
    assert roles_by_id == {"VTI": "core_us_equity", "510300": "core_cn_equity"}


def test_allocate_default_preferences_give_cn_etfs_nonzero_weight(
    repo_with_scoring: Path,
) -> None:
    rc = run_allocate(repo_root=str(repo_with_scoring))

    assert rc == 0
    payload = yaml.safe_load(
        (repo_with_scoring / "outputs" / _today() / "proposed_allocation.yaml").read_text(
            encoding="utf-8"
        )
    )
    weights_by_id = {
        row["instrument_id"]: row["target_weight"]
        for row in payload["selected_instruments"]
    }
    assert weights_by_id["510300"] > 0.0


def test_allocate_uses_four_candidates_per_class(repo_with_scoring: Path) -> None:
    with patch("irc.commands.allocate_cmd.run_allocation") as mocked:
        mocked.return_value = AllocationOutput(
            target_weights_per_class={"cn_etf": 0.25, "us_etf": 0.25},
            selected_instruments=[],
            dropped_due_to_correlation=[],
            diagnostics={"effective_n": 0.0, "total_weight": 0.0},
        )
        rc = run_allocate(repo_root=str(repo_with_scoring))

    assert rc == 0
    assert mocked.call_args.kwargs["per_class_top_k"] == 4

