from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pytest
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
             "action": "buy_candidate", "conviction": "med"},
            {"instrument_id": "510300", "asset_class": "cn_etf", "composite_score": 70,
             "action": "buy_candidate", "conviction": "med"},
        ]
    }), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(json.dumps({"tilt": "neutral"}), encoding="utf-8")
    return tmp_path


def test_allocate_writes_yaml(repo_with_scoring: Path):
    rc = run_allocate(repo_root=str(repo_with_scoring))
    assert rc == 0
    assert (repo_with_scoring / "outputs" / _today() / "proposed_allocation.yaml").exists()

