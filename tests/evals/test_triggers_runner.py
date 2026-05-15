from __future__ import annotations
import json
from pathlib import Path
from evals.triggers.runner import run


def test_triggers_runner_fails_when_no_trigger_data(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2
    report = next((tmp_path / "outputs").rglob("evals/triggers/report.json"))
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert "not yet implemented" in body["notes"].lower()
