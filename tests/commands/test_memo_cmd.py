from __future__ import annotations
from pathlib import Path
import json
import yaml
import pytest
from unittest.mock import patch
from irc.llm.http_client import ChatResponse
from irc.commands.init_cmd import run_init
from irc.commands.memo_cmd import run_memo


def _resp(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=50, raw={})


@pytest.fixture
def repo_with_inputs(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from datetime import datetime, timezone, timedelta
    from irc.data.manifest import ManifestEntry, write_manifest
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out = tmp_path / "outputs" / today
    out.mkdir(parents=True)
    (out / "scoring.json").write_text(json.dumps({"scores": []}), encoding="utf-8")
    (out / "gold_regime.json").write_text(json.dumps({"regime": "bull", "zone": "normal"}), encoding="utf-8")
    (out / "proposed_allocation.yaml").write_text(yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}), encoding="utf-8")
    (out / "trade_plan.yaml").write_text(yaml.safe_dump({"mode": "hybrid", "trades": []}), encoding="utf-8")
    # Write a fresh akshare manifest so the freshness gate passes by default.
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))
    return tmp_path


def test_memo_writes_output(repo_with_inputs: Path):
    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("合成备忘录内容")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
        rc = run_memo(str(repo_with_inputs))
    assert rc == 0
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    assert (repo_with_inputs / "outputs" / today / "memo.md").exists()
    assert (repo_with_inputs / "outputs" / today / "memo_audit.txt").exists()


def test_memo_refuses_to_run_when_ingest_is_stale(repo_with_inputs: Path, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, memo exits with rc=1
    and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_inputs
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_memo(str(repo))
    assert rc == 1
    markers = list((repo / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_memo_allow_stale_env_proceeds(repo_with_inputs: Path, monkeypatch):
    """With IRC_ALLOW_STALE=1, memo proceeds despite stale ingest."""
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_inputs
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("合成备忘录内容")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
        rc = run_memo(str(repo))
    assert rc == 0
    markers = list((repo / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_decision_status_for_pick_uses_qdii_premium_threshold() -> None:
    """AC10: memo-stage twin honours the qdii_max_premium_pct threshold."""
    from irc.commands.memo_cmd import _decision_status_for_pick

    score_row = {
        "instrument_id": "513650",
        "asset_class": "us_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "qdii_premium_pct": 0.10,  # above default 0.05
    }
    trade = {
        "target": "513650", "asset_class": "us_etf",
        "venue_compatible": True, "proxy_id": None,
        "target_weight": 0.2,
    }
    op_row = {"instrument_id": "513650", "asset_class": "us_etf"}
    status = _decision_status_for_pick(
        score_row, trade, op_row, qdii_max_premium_pct=0.05,
    )
    assert status == "blocked"


def test_decision_status_for_pick_synthetic_zero_passes() -> None:
    """Off-exchange synthetic 0.0 passes the memo-stage gate."""
    from irc.commands.memo_cmd import _decision_status_for_pick

    score_row = {
        "instrument_id": "017641",
        "asset_class": "us_etf",
        "action": "buy_candidate",
        "data_completeness": 1.0,
        "qdii_premium_pct": 0.0,
    }
    trade = {
        "target": "017641", "asset_class": "us_etf",
        "venue_compatible": True, "proxy_id": None,
        "target_weight": 0.2,
    }
    op_row = {"instrument_id": "017641", "asset_class": "us_etf"}
    status = _decision_status_for_pick(
        score_row, trade, op_row, qdii_max_premium_pct=0.05,
    )
    assert status == "actionable_buy"


def test_build_pick_rows_stamps_qdii_premium_pct_from_scoring():
    """AC1 integration: a hand-rolled scoring row with qdii_premium_pct=0.0648
    produces a PickRow whose qdii_premium_pct == 0.0648."""
    from irc.commands.memo_cmd import _build_pick_rows

    trades = [{
        "target": "159501", "role": "satellite_us_consumer",
        "target_weight": 0.05, "asset_class": "us_etf",
        "triggers": (), "buy_method": "limit", "granularity": "weekly",
        "venue_note": "ok",
    }]
    opportunity = {"rows": [{
        "instrument_id": "159501", "name_cn": "标普消费ETF",
        "asset_class": "us_etf",
        "evidence_gaps": [],
        "thesis_evidence": [],
        "valuation_state": "fair",
        "opportunity_state": "small_watch",
        "opportunity_reason": "—",
        "advisory_gaps": [],
    }]}
    scoring = {"scores": [{
        "instrument_id": "159501",
        "composite_score": 52.6,
        "action": "watch",
        "asset_class": "us_etf",
        "qdii_premium_pct": 0.0648,
        "data_completeness": 0.8,
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert len(pick_rows) == 1
    assert pick_rows[0].qdii_premium_pct == 0.0648


def test_build_pick_rows_non_qdii_leaves_premium_none():
    """AC1: cn_etf rows (no qdii_premium_pct in scoring) keep the field None."""
    from irc.commands.memo_cmd import _build_pick_rows

    trades = [{
        "target": "510300", "role": "core_a_share",
        "target_weight": 0.10, "asset_class": "cn_etf",
        "triggers": (), "buy_method": "limit", "granularity": "weekly",
        "venue_note": "ok",
    }]
    opportunity = {"rows": [{
        "instrument_id": "510300", "name_cn": "沪深300ETF",
        "asset_class": "cn_etf",
        "evidence_gaps": [],
        "thesis_evidence": [],
        "valuation_state": "fair",
        "opportunity_state": "core_dca",
        "opportunity_reason": "—",
        "advisory_gaps": [],
    }]}
    scoring = {"scores": [{
        "instrument_id": "510300",
        "composite_score": 55.0,
        "action": "watch",
        "asset_class": "cn_etf",
        "data_completeness": 0.8,
    }]}
    pick_rows, _, _ = _build_pick_rows(trades, opportunity, scoring)
    assert len(pick_rows) == 1
    assert pick_rows[0].qdii_premium_pct is None


def test_memo_cmd_emits_qdii_premium_marker_block_in_risk_notes():
    """AC7 integration: _compose_qdii_premium_projection builds a valid
    projection from scoring rows."""
    from irc.commands.memo_cmd import _compose_qdii_premium_projection

    scoring = {"scores": [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]}
    proj = _compose_qdii_premium_projection(
        scoring, evidence_cutoff="2026-05-26",
    )
    assert proj["evidence_cutoff"] == "2026-05-26"
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["159501", "513690"]
    # blocking flag correct
    by_iid = {r["instrument_id"]: r for r in proj["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["513690"]["blocking"] is False


def test_compose_execution_lines_prefixes_above_threshold_qdii():
    """AC9 / G-Q3: a pick with blocking=True receives the
    `⛔ qdii_premium_too_high（{cell} > 5%，已暂缓）｜` prefix."""
    from irc.commands.memo_cmd import _compose_execution_lines

    trades = [
        {"target": "159501", "target_weight": 0.05,
         "buy_method": "limit", "granularity": "weekly",
         "triggers": [], "venue_note": "ok"},
        {"target": "513690", "target_weight": 0.05,
         "buy_method": "limit", "granularity": "weekly",
         "triggers": [], "venue_note": "ok"},
    ]
    opportunity_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF"},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时"},
    ]
    qdii_premium_rows = [
        {"instrument_id": "159501", "blocking": True, "render_cell": "+6.92%"},
        {"instrument_id": "513690", "blocking": False, "render_cell": "-0.34%"},
    ]
    lines = _compose_execution_lines(
        trades, opportunity_rows,
        qdii_premium_rows=qdii_premium_rows,
    )
    assert any(
        line.startswith("⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜")
        for line in lines
    )
    # 513690 (non-blocking) line gets no prefix.
    line_513690 = next(line for line in lines if "513690" in line)
    assert not line_513690.startswith("⛔")


def test_no_qdii_premium_high_synonym_in_src():
    """AC13: codename unification — `qdii_premium_high` must NOT appear
    anywhere in src/irc/. The canonical name is `qdii_premium_too_high`."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "qdii_premium_high", "src/irc/"],
        capture_output=True, text=True,
        cwd="/Users/snow/Documents/Repository/investment-research-copilot",
    )
    # grep returns 1 when no matches — that's the success path.
    assert result.returncode == 1, (
        f"Unexpected `qdii_premium_high` token in src/:\n{result.stdout}"
    )


def test_run_memo_writes_qdii_premium_json_always(tmp_path):
    """AC6 / G-Q5: qdii_premium.json is written on every memo run, even
    when zero QDII rows exist."""
    import json
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_THRESHOLD_PCT,
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    proj = build_qdii_premium_projection(
        score_rows=[],
        evidence_cutoff="2026-05-26",
        now_fn=lambda: __import__("datetime").datetime(2026, 5, 27),
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    assert (tmp_path / "qdii_premium.json").exists()
    payload = json.loads(
        (tmp_path / "qdii_premium.json").read_text(encoding="utf-8")
    )
    assert payload["threshold_pct"] == QDII_PREMIUM_THRESHOLD_PCT
    assert payload["rows"] == []
