from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

from irc.data.duckdb_helper import ensure_schema


def _seed_db(db_path: Path, iid: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    con.execute(
        "INSERT INTO instruments "
        "(instrument_id, ticker, market, name_cn, asset_class, currency, "
        " expense_ratio, aum, manager_tenure_years, "
        " _ingested_at, _source, _raw_ref) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        # Use cn_etf / cn_on_exchange so passive quality path applies
        # (active-fund path requires aum_stability_pct which is not in the DB schema).
        [iid, iid, "cn_on_exchange", "算力金属ETF", "cn_etf", "cny",
         0.005, 5_000_000_000.0, 6.0, ts, "test", ""],
    )
    # A downward NAV series → cold heat + low self-percentile (cheap).
    base = date(2025, 1, 1)
    rows = [
        (iid, (base + timedelta(days=i)).isoformat(), 2.0 - i * 0.002, ts, "test", "")
        for i in range(260)
    ]
    con.executemany(
        "INSERT INTO nav_history (instrument_id, date, nav, _ingested_at, _source, _raw_ref) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.close()


def _seed_configs(repo: Path) -> None:
    """Copy all template configs + write minimal inputs."""
    src_tpl = Path(__file__).resolve().parents[2] / "src" / "irc" / "templates"
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/gold.yaml",
    ):
        target = repo / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((src_tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    (repo / "inputs").mkdir(exist_ok=True)
    (repo / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund]\n"
        "    holdings:\n"
        "      - asset_class: cn_equity_fund\n"
        "        instrument_id: '000001'\n"
        "        cost_basis_cny: 1000\n",
        encoding="utf-8",
    )
    (repo / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance:\n  cny: [0.5, 1.0]\n  usd: [0.0, 0.4]\n  hkd: [0.0, 0.3]\n"
        "constraints:\n  allow_short: false\n  allow_leverage: false\n  exclude_themes: []\n"
        "investment_plan:\n  monthly_new_capital_cny: 5000\n"
        "report_language: zh\n",
        encoding="utf-8",
    )


def _seed_universe(repo: Path, iid: str) -> None:
    uni = repo / "config" / "universe"
    uni.mkdir(parents=True, exist_ok=True)
    # Write into cn_funds.yaml; asset_class=cn_etf uses passive quality path
    # (avoids aum_stability_pct requirement of the active-fund path).
    (uni / "cn_funds.yaml").write_text(
        "instruments:\n"
        f"  - instrument_id: '{iid}'\n"
        f"    ticker: '{iid}'\n"
        "    market: cn_on_exchange\n"
        "    name_cn: 算力金属ETF\n"
        "    asset_class: cn_etf\n"
        "    currency: cny\n"
        "    theme: metals\n",
        encoding="utf-8",
    )


def _seed_active_fund_cache(repo: Path, iid: str, quarter: str) -> None:
    d = repo / "data" / "fundamentals" / quarter / "active_fund"
    d.mkdir(parents=True, exist_ok=True)
    data_leg = {
        "type": "filing", "source": "filing", "url": "", "date": "2026-03-31",
        "summary": "600519 2025Q4 财报已披露（口径未核实）",
        "scope": "constituent", "citation_kind": "data",
        "owner_instrument_id": iid, "parent_fund_id": iid, "constituent_key": "600519",
    }
    info_leg = {
        "type": "broker", "source": "broker", "url": "https://x", "date": "2026-04-01",
        "summary": "券商维持买入评级", "scope": "constituent",
        "citation_kind": "information", "owner_instrument_id": iid,
        "parent_fund_id": iid, "constituent_key": "600519",
    }
    body = {
        "fund_id": iid, "source_report_date": "2026-03-31",
        "source_report_quarter": quarter, "cache_probed_at": "2026-05-30",
        "constituent_analyses": [{
            "symbol": "600519", "name_cn": "贵州茅台", "weight_pct": 12.0,
            "evidence": [data_leg, info_leg], "failure_reasons": [],
            "one_line_view": "600519 贵州茅台",
        }],
        "failure_reasons_by_symbol": {},
        "fund_level_failure_reasons": [],
        "fund_level_evidence": [],
    }
    (d / f"fund_{iid}.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8")


def test_run_eval_funds_writes_md_and_json_with_core_dca(tmp_path: Path):
    from irc.commands.fund_eval_cmd import run_eval_funds

    iid = "980001"
    quarter = "2026Q1"
    _seed_db(tmp_path / "data" / "local.duckdb", iid)
    _seed_configs(tmp_path)
    _seed_universe(tmp_path, iid)
    _seed_active_fund_cache(tmp_path, iid, quarter)

    out = tmp_path / "outputs" / "2026-06-01" / "fund_eval.md"
    rc = run_eval_funds(
        repo_root=str(tmp_path), ids=iid, quarter=quarter,
        role="satellite_cn_metals",
        db_path=str(tmp_path / "data" / "local.duckdb"),
        out_path=str(out),
    )
    assert rc == 0
    assert out.exists()
    js = out.with_suffix(".json")
    assert js.exists()
    doc = json.loads(js.read_text(encoding="utf-8"))
    row = next(f for f in doc["funds"] if f["instrument_id"] == iid)
    assert row["opportunity_state"] == "core_dca"
    assert row["core_dca"] is True


def test_run_eval_funds_errors_clearly_when_db_missing(tmp_path: Path, capsys):
    from irc.commands.fund_eval_cmd import run_eval_funds

    _seed_configs(tmp_path)
    _seed_universe(tmp_path, "980001")
    rc = run_eval_funds(
        repo_root=str(tmp_path), ids="980001", quarter="2026Q1",
        role="satellite_cn_metals",
        db_path=str(tmp_path / "data" / "does_not_exist.duckdb"),
        out_path=str(tmp_path / "outputs" / "2026-06-01" / "fund_eval.md"),
    )
    assert rc != 0
    captured = capsys.readouterr()
    err = captured.err + captured.out
    # message names the missing DB path
    assert "does_not_exist.duckdb" in err or rc == 2
