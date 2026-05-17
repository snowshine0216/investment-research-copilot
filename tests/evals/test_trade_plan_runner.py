from __future__ import annotations
import json
from pathlib import Path
from evals.trade_plan.runner import run


def test_trade_plan_runner_fails_when_input_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/trade_plan/report.json"))
    assert candidates, "runner must write a FAIL report"
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
