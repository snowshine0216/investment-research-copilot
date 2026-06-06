"""score command recorder integration: macro_fit ChatResponse flows up to spend actuals."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture
def score_repo(tmp_path: Path) -> Path:
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
                "scoring_rationale": {
                    "calls": 5,
                    "prompt_tokens": 3000,
                    "completion_tokens": 500,
                },
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "config/spend_balances.yaml").write_text(
        yaml.safe_dump({}), encoding="utf-8",
    )
    today = "2026-06-06"
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True)
    # Write a minimal discovered_watchlist.csv
    import csv
    wl_path = out_dir / "discovered_watchlist.csv"
    with wl_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "instrument_id", "ticker", "market", "name_cn", "asset_class",
            "currency", "tracked_index", "venue_required", "role", "reason_text",
            "cited_refs", "relaxed",
        ])
        writer.writeheader()
        writer.writerow({
            "instrument_id": "518880", "ticker": "518880", "market": "cn_on_exchange",
            "name_cn": "黄金ETF", "asset_class": "gold", "currency": "cny",
            "tracked_index": "gold_spot", "venue_required": "", "role": "hedge",
            "reason_text": "gold hedge", "cited_refs": "r1", "relaxed": "False",
        })
    # Minimal DuckDB
    import duckdb
    db_path = tmp_path / "data" / "local.duckdb"
    db_path.parent.mkdir(parents=True)
    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS macro_series (
            series_id VARCHAR, value DOUBLE, date DATE
        )
    """)
    con.execute(
        "INSERT INTO macro_series VALUES ('DGS10', 4.5, '2026-06-06')"
    )
    con.close()
    return tmp_path


def _fake_scoring_cfg():
    from irc.schemas.scoring import ScoringConfig
    return ScoringConfig.model_validate({
        "factor_weights": {
            "valuation_cost": 0.10, "risk": 0.25, "quality": 0.20,
            "macro_fit": 0.25, "thesis_news": 0.20,
        },
        "action_thresholds": {
            "strong_buy_candidate": 80, "buy_candidate": 60,
            "watch": 40, "avoid": 20,
        },
        "conviction_data_completeness_threshold": 0.80,
        "weights_version": "v1",
    })


class _FakePreferences:
    risk_band = type("rb", (), {"max_drawdown": [0.05, 0.30]})()


def test_score_run_records_scoring_rationale_samples_0_to_1(score_repo, monkeypatch):
    """Shape B: score_macro_fit returns (FactorScore, ChatResponse); run_score records."""
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")
    from irc.llm._types import ChatResponse, ResolvedRoute
    from irc.scoring.factors.valuation_cost import FactorScore

    fake_route = ResolvedRoute(
        task="scoring_rationale",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )
    fake_resp = ChatResponse(
        text='{"score": 72, "rationale": "ok"}',
        prompt_tokens=900,
        completion_tokens=150,
    )

    import irc.commands.score_cmd as score_mod

    class _FakeBundle:
        llm = None
        scoring = _fake_scoring_cfg()
        preferences = _FakePreferences()

    monkeypatch.setattr(score_mod, "load_repo_configs", lambda _r: _FakeBundle())
    monkeypatch.setattr(score_mod, "resolve_route", lambda task, llm: fake_route)
    monkeypatch.setattr(score_mod, "_today", lambda: "2026-06-06")

    # Patch score_macro_fit to return (FactorScore, ChatResponse) tuple
    with patch("irc.scoring.pipeline.score_macro_fit") as mock_mf:
        mock_mf.return_value = (
            FactorScore(score=72.0, raw_refs=("r1",), components={"llm_score": 72.0}),
            fake_resp,
        )
        rc = score_mod.run_score(str(score_repo))

    assert rc == 0

    # 1. spend_actuals.json written
    actuals_path = score_repo / "outputs" / "2026-06-06" / "spend_actuals.json"
    assert actuals_path.exists(), "spend_actuals.json not found"
    actuals = json.loads(actuals_path.read_text())
    assert "scoring_rationale" in actuals["tasks"]
    assert actuals["tasks"]["scoring_rationale"]["avg_prompt_tokens"] == 900.0

    # 2. usage_profile.json samples 0→1
    prof_path = score_repo / "data" / "spend" / "usage_profile.json"
    assert prof_path.exists()
    prof = json.loads(prof_path.read_text())
    assert prof["scoring_rationale"]["samples"] == 1
    # 3. EWMA: 0.3 * 900 + 0.7 * 3000 = 270 + 2100 = 2370
    assert prof["scoring_rationale"]["avg_prompt_tokens"] == pytest.approx(2370.0)
