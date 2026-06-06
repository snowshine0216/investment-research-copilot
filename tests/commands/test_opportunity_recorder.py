"""opportunity command recorder integration: debate LLM calls flow to spend actuals."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from irc.llm._types import ChatResponse, ResolvedRoute
from irc.llm.cost_tracker import CostEntry
from datetime import datetime, timezone, timedelta


@pytest.fixture
def opp_repo(tmp_path: Path) -> Path:
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
                "thesis_defend": {
                    "calls": 3,
                    "prompt_tokens": 1500,
                    "completion_tokens": 200,
                },
                "thesis_falsify": {
                    "calls": 3,
                    "prompt_tokens": 1500,
                    "completion_tokens": 200,
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


def test_opportunity_run_records_debate_tasks_samples_0_to_1(opp_repo, monkeypatch):
    """Shape B: run_debates returns (debates, list[CostEntry]);
    run_opportunity records the token counts."""
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")

    import irc.commands.opportunity_cmd as opp_mod

    fake_defend_route = ResolvedRoute(
        task="thesis_defend",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )
    fake_falsify_route = ResolvedRoute(
        task="thesis_falsify",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )

    _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    fake_cost_entries = [
        CostEntry(
            task="thesis_defend",
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=600,
            completion_tokens=100,
            latency_ms=0,
            ts=_ts,
        ),
        CostEntry(
            task="thesis_falsify",
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=600,
            completion_tokens=100,
            latency_ms=0,
            ts=_ts,
        ),
    ]

    # Stub _write_opportunity_outputs to return fake_cost_entries (the debate LLM call entries)
    with patch("irc.commands.opportunity_cmd._write_opportunity_outputs", return_value=fake_cost_entries) as mock_write, \
             patch("irc.commands.opportunity_cmd._build_rows", return_value=(
                 [], [], {}, {}, [], "hash0", {}
             )), \
             patch("irc.commands.opportunity_cmd.load_repo_configs") as mock_cfg, \
             patch("irc.commands.opportunity_cmd.require_fresh_ingest", return_value=True), \
             patch("irc.commands.opportunity_cmd.validate_cli_args"), \
             patch("irc.commands.opportunity_cmd.connect"), \
             patch("irc.commands.opportunity_cmd.ensure_schema"), \
             patch("irc.commands.opportunity_cmd._locate_scoring", return_value=opp_repo / "outputs" / "2026-06-06" / "scoring.json"), \
             patch("irc.commands.opportunity_cmd._load_scores", return_value=[]), \
             patch("irc.commands.opportunity_cmd.load_theme_thesis", return_value={}), \
             patch("irc.commands.opportunity_cmd._instrument_index", return_value={}), \
             patch("irc.commands.opportunity_cmd._holdings_index", return_value={}), \
             patch("irc.commands.opportunity_cmd.load_theme_reports", return_value={}), \
             patch("irc.commands.opportunity_cmd._apply_reduction", return_value=[]), \
             patch("irc.commands.opportunity_cmd._today", return_value="2026-06-06"), \
             patch("irc.commands.opportunity_cmd.default_cn_provider", return_value=object()):

            mock_bundle = MagicMock()
            mock_bundle.account.accounts = []
            mock_bundle.preferences.asset_class_targets = {}
            mock_bundle.valuation_buckets.active_fund_lookthrough = None
            mock_bundle.valuation_buckets.sector_index_grounding.activated_slugs = []
            mock_cfg.return_value = mock_bundle

            # Patch resolve_route (imported locally in run_opportunity) so adversarial=True gets fake routes
            with patch("irc.llm.gateway.resolve_route", side_effect=[fake_defend_route, fake_falsify_route]):
                rc = opp_mod.run_opportunity(str(opp_repo), adversarial=True)

    assert rc == 0

    # 1. spend_actuals.json written
    actuals_path = opp_repo / "outputs" / "2026-06-06" / "spend_actuals.json"
    assert actuals_path.exists(), "spend_actuals.json not found after run_opportunity"
    actuals = json.loads(actuals_path.read_text())
    assert "thesis_defend" in actuals["tasks"]
    assert actuals["tasks"]["thesis_defend"]["avg_prompt_tokens"] == 600.0

    # 2. usage_profile.json samples 0→1
    prof_path = opp_repo / "data" / "spend" / "usage_profile.json"
    assert prof_path.exists()
    prof = json.loads(prof_path.read_text())
    assert prof["thesis_defend"]["samples"] == 1
    # 3. EWMA: 0.3 * 600 + 0.7 * 1500 = 180 + 1050 = 1230
    assert prof["thesis_defend"]["avg_prompt_tokens"] == pytest.approx(1230.0)
