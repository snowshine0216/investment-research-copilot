"""Item 009 — memo-stage citation gate unit tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _resp(text):
    from irc.llm.http_client import ChatResponse
    return ChatResponse(
        text=text, prompt_tokens=10, completion_tokens=20,
        latency_ms=50, raw={},
    )


def test_memo_gate_clean_publishable_set_passes(tmp_path, monkeypatch):
    """AC14 — clean run with dual-leg pick rows → memo.md written, exit 0."""
    # Use the lifted helper to seed a publishable set.
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
        _patch_memo_routes,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))
    with _patch_memo_routes("# memo draft"):
        rc = run_memo(str(tmp_path))
    assert rc == 0
    today = next((tmp_path / "outputs").iterdir()).name
    out_dir = tmp_path / "outputs" / today
    assert (out_dir / "memo.md").exists()
    audit = json.loads((out_dir / "citation_audit.json").read_text())
    # memo_findings list exists (may be empty if all picks have dual-leg).
    assert "memo_findings" in audit


def test_memo_gate_uses_out_dir_not_out_today(tmp_path, monkeypatch):
    """AC25 + Q7 — _resolve_enforce_mode is called with out_dir (write-path),
    not out_today (read-path which may be stale-dated).

    Strategy: monkey-patch `_locate_scoring` / `_latest_file` to return a
    yesterday-dated scoring.json; assert the shadow log lands in TODAY's
    output dir, not yesterday's."""
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
        _patch_memo_routes,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo, _today

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))

    today = _today()
    # Move today's scoring.json sideways so _latest_file falls back.
    today_dir = tmp_path / "outputs" / today
    yesterday = "2026-05-21"  # any earlier ISO date
    ydir = tmp_path / "outputs" / yesterday
    ydir.mkdir(parents=True, exist_ok=True)
    (today_dir / "scoring.json").rename(ydir / "scoring.json")
    # Also move the other upstream artifacts so memo_cmd's READ-path resolves
    # to yesterday.
    for name in ("gold_regime.json", "proposed_allocation.yaml",
                 "trade_plan.yaml", "opportunity_report.json"):
        src = today_dir / name
        if src.exists():
            src.rename(ydir / name)

    with _patch_memo_routes("# memo draft"):
        rc = run_memo(str(tmp_path))

    # The shadow log MUST live under today's dir (write path), not yesterday.
    audit_today = today_dir / "citation_audit.json"
    audit_yesterday = ydir / "citation_audit.json"
    assert audit_today.exists(), f"shadow log not under {today_dir}"
    assert not audit_yesterday.exists(), f"shadow log leaked into {ydir}"


def test_memo_gate_audit_blocks_publish_still_takes_precedence(tmp_path, monkeypatch):
    """AC16 — the existing audit_blocks_publish gate runs first; citation
    findings do not change the exit code if the audit gate fires."""
    from tests.integration._publishable_set_helper import (
        _seed_publishable_set_repo, _install_ak_call_dispatch,
    )
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.commands.memo_cmd import run_memo
    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(str(tmp_path))
    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("# memo")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核未通过 P-tier 高风险")):
        rc = run_memo(str(tmp_path))
    assert rc == 2  # blocked by audit gate, NOT citation gate
    today = next((tmp_path / "outputs").iterdir()).name
    out_dir = tmp_path / "outputs" / today
    assert (out_dir / "memo_blocked.md").exists()
    assert not (out_dir / "memo.md").exists()
