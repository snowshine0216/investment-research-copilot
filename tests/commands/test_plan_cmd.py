from __future__ import annotations
from pathlib import Path
import yaml
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.plan_cmd import run_plan


@pytest.fixture
def repo_with_alloc(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    # Use today's date for the output dir so plan_cmd finds it
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    (out_dir / "proposed_allocation.yaml").write_text(yaml.safe_dump({
        "gold_tilt": "neutral",
        "target_weights_per_class": {"us_etf": 0.25, "gold": 0.20},
        "selected_instruments": [{
            "instrument_id": "006075", "asset_class": "us_etf",
            "target_weight": 0.18, "intra_class_share": 1.0,
            "composite_score": 75, "role": "core_us_equity"
        }],
        "diagnostics": {},
    }), encoding="utf-8")
    return tmp_path


def test_plan_writes_trade_plan_yaml(repo_with_alloc: Path):
    rc = run_plan(repo_root=str(repo_with_alloc))
    assert rc == 0
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    p = repo_with_alloc / "outputs" / today / "trade_plan.yaml"
    assert p.exists()
    plan_data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert plan_data["mode"] == "build"
    assert len(plan_data["trades"]) == 1
