from __future__ import annotations

import json
from pathlib import Path

from evals.research.runner import run


def test_research_runner_fails_when_status_file_missing(tmp_path: Path):
    rc = run(tmp_path)
    assert rc == 2, "missing input must be FAIL (rc=2), not PASS"
    report_path = next((tmp_path / "outputs").rglob("evals/research/report.json"))
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert body["based_on"] == ["data/research/research_status.json"]


def test_research_runner_fails_when_status_file_unreadable(tmp_path: Path):
    p = tmp_path / "data" / "research"
    p.mkdir(parents=True)
    (p / "research_status.json").write_text("this is not json", encoding="utf-8")
    rc = run(tmp_path)
    assert rc == 2
    report_path = next((tmp_path / "outputs").rglob("evals/research/report.json"))
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert "unreadable" in body["notes"]


def test_research_runner_returns_pass_when_themes_all_succeed(tmp_path: Path):
    p = tmp_path / "data" / "research"
    p.mkdir(parents=True)
    themes = [
        {"theme": t, "citation_count": 4, "failure_reason": ""}
        for t in (
            "us_monetary", "us_fiscal_politics", "cn_monetary",
            "cn_equity_property_policy", "geopolitics", "gold_drivers", "holdings_sector",
        )
    ]
    (p / "research_status.json").write_text(json.dumps({"themes": themes}), encoding="utf-8")
    rc = run(tmp_path)
    assert rc == 0
