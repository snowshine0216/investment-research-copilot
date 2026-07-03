"""End-to-end wiring: run_decision embeds the promotion diff (vs the most
recent prior opportunity_report.json) into decision_report.{json,md} and the
summary keys notify-status reads."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from irc.commands.decision_cmd import run_decision
from irc.commands.init_cmd import run_init


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _opp_report(rows: list[dict]) -> str:
    return json.dumps({"rows": rows}, ensure_ascii=False)


def _opp_row(iid: str, state: str, dca: str = "normal_dca") -> dict:
    return {
        "instrument_id": iid, "name_cn": f"基金{iid}",
        "opportunity_state": state, "dca_action": dca, "risk_action": "none",
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out = tmp_path / "outputs" / _today()
    out.mkdir(parents=True)
    (out / "scoring.json").write_text(json.dumps({"scores": []}), encoding="utf-8")
    (out / "proposed_allocation.yaml").write_text(
        yaml.safe_dump({"gold_tilt": "neutral", "selected_instruments": []}), encoding="utf-8")
    (out / "trade_plan.yaml").write_text(
        yaml.safe_dump({"mode": "build", "trades": []}), encoding="utf-8")
    (out / "memo_traceability.json").write_text(json.dumps({}), encoding="utf-8")
    (out / "opportunity_report.json").write_text(
        _opp_report([_opp_row("161903", "core_dca", "accelerate_dca")]), encoding="utf-8")
    prior = tmp_path / "outputs" / "2026-01-02"
    prior.mkdir(parents=True)
    (prior / "opportunity_report.json").write_text(
        _opp_report([_opp_row("161903", "small_watch", "normal_dca")]), encoding="utf-8")
    return tmp_path


def test_run_decision_embeds_promotions(repo: Path) -> None:
    rc = run_decision(str(repo))
    assert rc == 0
    out = repo / "outputs" / _today()
    report = json.loads((out / "decision_report.json").read_text(encoding="utf-8"))
    assert report["promotions"]["prior_date"] == "2026-01-02"
    kinds = sorted(r["kind"] for r in report["promotions"]["rows"])
    assert kinds == ["dca", "state"]
    assert report["summary"]["promotion_count"] == 2
    assert report["summary"]["promotion_ids"] == ["161903"]
    md = (out / "decision_report.md").read_text(encoding="utf-8")
    assert "新晋关注" in md
    assert "161903" in md


def test_run_decision_survives_wrong_shape_prior_report(repo: Path, capsys) -> None:
    """A prior opportunity_report.json that PARSES but has the wrong shape
    (top-level list) must degrade to an empty diff with a warning — never
    crash the decision stage (silent-failure review P1, 2026-07-03)."""
    (repo / "outputs" / "2026-01-02" / "opportunity_report.json").write_text(
        json.dumps([{"instrument_id": "161903"}]), encoding="utf-8"
    )
    rc = run_decision(str(repo))
    assert rc == 0
    out = repo / "outputs" / _today()
    report = json.loads((out / "decision_report.json").read_text(encoding="utf-8"))
    assert report["promotions"]["rows"] == []
    assert "WARNING" in capsys.readouterr().out


def test_run_decision_skips_non_dict_prior_rows(repo: Path) -> None:
    """Garbage entries inside a well-formed prior rows list are filtered at
    the I/O edge, not passed into the pure diff."""
    (repo / "outputs" / "2026-01-02" / "opportunity_report.json").write_text(
        json.dumps({"rows": ["garbage", 42,
                             {"instrument_id": "161903",
                              "opportunity_state": "small_watch",
                              "dca_action": "normal_dca"}]}),
        encoding="utf-8",
    )
    rc = run_decision(str(repo))
    assert rc == 0
    out = repo / "outputs" / _today()
    report = json.loads((out / "decision_report.json").read_text(encoding="utf-8"))
    # the one valid prior row still drives the diff: state promotion detected
    kinds = sorted(r["kind"] for r in report["promotions"]["rows"])
    assert kinds == ["dca", "state"]


def test_run_decision_without_prior_report_has_empty_promotions(repo: Path) -> None:
    import shutil
    shutil.rmtree(repo / "outputs" / "2026-01-02")
    rc = run_decision(str(repo))
    assert rc == 0
    out = repo / "outputs" / _today()
    report = json.loads((out / "decision_report.json").read_text(encoding="utf-8"))
    assert report["promotions"] == {"prior_date": None, "rows": []}
    assert report["summary"]["promotion_count"] == 0
    md = (out / "decision_report.md").read_text(encoding="utf-8")
    assert "新晋关注" not in md
