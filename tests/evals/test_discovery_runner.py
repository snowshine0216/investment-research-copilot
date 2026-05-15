from __future__ import annotations
import json
from pathlib import Path
from evals.discovery.runner import run


def test_discovery_runner_fails_when_input_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    candidates = list(tmp_path.rglob("evals/discovery/report.json"))
    assert candidates, "runner must write a FAIL report"
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
