"""research command recorder integration: synthesize_report token counts flow to spend actuals."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from irc.llm._types import ChatResponse, ResolvedRoute
from irc.research.synthesize import Citation, ResearchReport


@pytest.fixture
def research_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config/spend_pricing.yaml").write_text(
        yaml.safe_dump({
            "margin": 1.2,
            "llm": {
                "deepseek": {
                    "currency": "CNY",
                    "models": {
                        "deepseek-chat": {
                            "input_per_mtok": 1.0,
                            "output_per_mtok": 2.0,
                        },
                    },
                },
            },
            "seeds": {
                "research_synth": {
                    "calls": 7,
                    "prompt_tokens": 3000,
                    "completion_tokens": 800,
                },
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "config/spend_balances.yaml").write_text(
        yaml.safe_dump({}), encoding="utf-8",
    )
    (tmp_path / "outputs" / "2026-06-06").mkdir(parents=True)
    return tmp_path


def test_research_run_records_research_synth_samples_0_to_1(research_repo, monkeypatch):
    """Shape B: synthesize_report returns (ResearchReport, ChatResponse | None);
    run_research records the token counts from each LLM call."""
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")

    import irc.commands.research_cmd as research_mod
    from irc.research.pipeline import run_research_pipeline

    fake_route = ResolvedRoute(
        task="research_synth",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )

    fake_report = ResearchReport(
        report_md="Gold report [1].",
        citations=[Citation(index=1, title="Reuters gold", url="https://reuters.com/gold")],
        failure_reason="",
    )
    fake_resp = ChatResponse(
        text="Gold report [1].", prompt_tokens=900, completion_tokens=200,
        latency_ms=0, raw={},
    )

    # Stub the pipeline to return 1 cost entry from a single synth call
    # record_command_run is called inside run_research after run_research_pipeline
    from irc.llm.cost_tracker import CostEntry
    from datetime import datetime, timezone, timedelta

    _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    fake_cost_entry = CostEntry(
        task="research_synth",
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=900,
        completion_tokens=200,
        latency_ms=0,
        ts=_ts,
    )

    class _FakeBundle:
        llm = None
        preferences = _FakePrefs()

    monkeypatch.setattr(research_mod, "load_repo_configs", lambda _r: _FakeBundle())
    monkeypatch.setattr(research_mod, "resolve_route", lambda task, llm: fake_route)

    # Stub run_research_pipeline to return (rc, cost_entries) — Shape B signature
    with patch("irc.commands.research_cmd.run_research_pipeline", return_value=(0, [fake_cost_entry])):
        with patch("irc.commands.research_cmd.build_providers", return_value=(object(),)):
            with patch("irc.commands.research_cmd.build_extractor", return_value=object()):
                rc = research_mod.run_research(str(research_repo))

    assert rc == 0

    # 1. spend_actuals.json written
    actuals_path = research_repo / "outputs" / "2026-06-06" / "spend_actuals.json"
    assert actuals_path.exists(), "spend_actuals.json not found after run_research"
    actuals = json.loads(actuals_path.read_text())
    assert "research_synth" in actuals["tasks"]
    assert actuals["tasks"]["research_synth"]["avg_prompt_tokens"] == 900.0

    # 2. usage_profile.json samples 0→1
    prof_path = research_repo / "data" / "spend" / "usage_profile.json"
    assert prof_path.exists()
    prof = json.loads(prof_path.read_text())
    assert prof["research_synth"]["samples"] == 1
    # 3. EWMA: 0.3 * 900 + 0.7 * 3000 = 270 + 2100 = 2370
    assert prof["research_synth"]["avg_prompt_tokens"] == pytest.approx(2370.0)


class _FakePrefs:
    asset_class_targets: dict = {}
