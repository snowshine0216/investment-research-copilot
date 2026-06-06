"""discover command recorder integration: write_reason token counts flow to spend actuals."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

from irc.discovery.reason_writer import ReasonResult
from irc.discovery.universe import UniverseRow


def _row(iid: str) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_on_exchange",
        name_cn=f"{iid}ETF", asset_class="gold", currency="cny",
        tracked_index="gold_spot", theme=None, venue_required=(),
    )


@pytest.fixture
def discover_repo(tmp_path: Path) -> Path:
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
                "watchlist_reason": {
                    "calls": 3,
                    "prompt_tokens": 2500,
                    "completion_tokens": 400,
                },
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "config/spend_balances.yaml").write_text(
        yaml.safe_dump({}), encoding="utf-8",
    )
    # Minimal DuckDB — all EXPECTED_TABLES must include _raw_ref for ref_index_from_duckdb
    import duckdb
    db_path = tmp_path / "data" / "local.duckdb"
    db_path.parent.mkdir(parents=True)
    con = duckdb.connect(str(db_path))
    _PROVENANCE = "_raw_ref VARCHAR"
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS prices (
            instrument_id VARCHAR, date DATE, close DOUBLE, volume DOUBLE, {_PROVENANCE}
        )
    """)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS nav_history (
            instrument_id VARCHAR, date DATE, nav DOUBLE, nav_acc DOUBLE, {_PROVENANCE}
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS instruments (
            instrument_id VARCHAR, inception_date DATE,
            expense_ratio DOUBLE, aum DOUBLE, manager_tenure_years DOUBLE,
            _raw_ref VARCHAR
        )
    """)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS fund_metrics (
            instrument_id VARCHAR, as_of_date DATE,
            drawdown_3y DOUBLE, tracking_error DOUBLE, {_PROVENANCE}
        )
    """)
    # Remaining EXPECTED_TABLES (minimal — only need _raw_ref column)
    for tbl in ("macro_series", "fund_holdings", "events_log",
                "index_valuation_history", "stock_valuation_history"):
        con.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" (_raw_ref VARCHAR)')
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_ref_index (
            ref_id VARCHAR, source VARCHAR, topic VARCHAR,
            instrument_id VARCHAR, date DATE
        )
    """)
    con.execute("INSERT INTO instruments VALUES ('518880', '2004-01-01', 0.006, 1e10, 5.0, NULL)")
    con.execute("INSERT INTO instruments VALUES ('518810', '2010-01-01', 0.005, 5e9, 3.0, NULL)")
    # Fund metrics for 518880 so it passes the quality filter (drawdown_3y required)
    con.execute("INSERT INTO fund_metrics VALUES ('518880', '2026-01-01', 0.12, 0.01, NULL)")
    con.close()
    return tmp_path


def test_discover_run_records_watchlist_reason_samples_0_to_1(discover_repo, monkeypatch):
    """Shape B: write_reason returns ReasonResult with tokens; run_discover records."""
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")

    from irc.llm._types import ResolvedRoute

    fake_route = ResolvedRoute(
        task="watchlist_reason",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )

    import irc.commands.discover_cmd as disc_mod
    from irc.llm._types import ResolvedRoute

    class _FakeBundle:
        llm = None
        universe_qdii_us = _empty_uni()
        universe_qdii_hk = _empty_uni()
        universe_cn_funds = _empty_uni()
        universe_gold = _gold_uni()
        overrides = None
        discovery = None
        preferences = _FakePrefs()

    monkeypatch.setattr(disc_mod, "load_repo_configs", lambda _r: _FakeBundle())
    monkeypatch.setattr(disc_mod, "resolve_route", lambda task, llm: fake_route)
    monkeypatch.setattr(disc_mod, "_now_iso_date", lambda: "2026-06-06")

    # write_reason returns a ReasonResult with known token counts
    fake_result = ReasonResult(
        instrument_id="518880",
        reason_text="Gold ETF (r1). Low cost. Solid AUM. Risk: none.",
        cited_refs=("r1",),
        prompt_tokens=700,
        completion_tokens=120,
    )
    with patch("irc.discovery.pipeline.write_reason", return_value=fake_result):
        rc = disc_mod.run_discover(str(discover_repo))

    assert rc == 0

    # 1. spend_actuals.json written
    actuals_path = discover_repo / "outputs" / "2026-06-06" / "spend_actuals.json"
    assert actuals_path.exists(), "spend_actuals.json not found after run_discover"
    actuals = json.loads(actuals_path.read_text())
    assert "watchlist_reason" in actuals["tasks"]
    assert actuals["tasks"]["watchlist_reason"]["avg_prompt_tokens"] == 700.0

    # 2. usage_profile.json samples 0→1
    prof_path = discover_repo / "data" / "spend" / "usage_profile.json"
    assert prof_path.exists()
    prof = json.loads(prof_path.read_text())
    assert prof["watchlist_reason"]["samples"] == 1
    # 3. EWMA: 0.3 * 700 + 0.7 * 2500 = 210 + 1750 = 1960
    assert prof["watchlist_reason"]["avg_prompt_tokens"] == pytest.approx(1960.0)


def _empty_uni():
    from irc.schemas.universe import UniverseConfig
    return UniverseConfig(instruments=[])


def _gold_uni():
    from irc.schemas.universe import Instrument, UniverseConfig
    return UniverseConfig(instruments=[
        Instrument(
            instrument_id="518880", ticker="518880", market="cn_on_exchange",
            name_cn="黄金ETF", asset_class="gold", currency="cny",
            tracked_index="gold_spot", theme=None, venue_required=[],
        ),
    ])


class _FakePrefs:
    class risk_band:
        max_drawdown = [0.05, 0.30]

    class constraints:
        exclude_themes: list = []
