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
