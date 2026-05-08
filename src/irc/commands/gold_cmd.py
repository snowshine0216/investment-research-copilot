from __future__ import annotations
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from pathlib import Path
import json
import yaml
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.scoring.regime_detect import classify_regime
from irc.scoring.gold_band import compute_band, classify_zone
from irc.scoring.gold_scenarios import classify_scenario
from irc.scoring.gold_score import compute_gold_score, GoldDriverInputs, gold_tilt_from_score


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _gold_prices(con, instrument_id: str) -> pd.Series:
    df = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetch_df()
    return df["close"]


def _macro_value(con, series: str, default: float) -> float:
    row = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [series],
    ).fetchone()
    return float(row[0]) if row else default


def run_gold(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    cfg = bundle.gold_drivers
    exchange_gold = [i for i in bundle.universe_gold.instruments if i.market != "cmb_internal"]
    if not exchange_gold:
        print("WARN: no exchange-traded gold instrument in universe/gold.yaml")
        return 1
    gold_id = exchange_gold[0].instrument_id
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        prices = _gold_prices(con, gold_id)
        if prices.empty:
            print("WARN: no gold prices in DuckDB; run `irc ingest` first.")
            return 1
        regime = classify_regime(
            prices,
            vol_ratio_threshold=cfg.regime_detection.vol_ratio_range_threshold,
            adx_threshold=cfg.regime_detection.adx_range_threshold,
            window_recent_days=cfg.regime_detection.vol_window_months * 30,
            window_baseline_days=cfg.regime_detection.vol_baseline_window_months * 30,
        )
        band = compute_band(prices, window_months=cfg.band.rolling_window_months)
        current_price = float(prices.iloc[-1])
        zone = classify_zone(current_price, band)
        inputs = GoldDriverInputs(
            real_yield_10y_tips=_macro_value(con, "DGS10", 1.65) - 2.30,  # rough TIPS proxy
            dxy=_macro_value(con, "DTWEXBGS", 104.0),
            inflation_5y5y=_macro_value(con, "T5YIFR", 2.30),
            cb_purchases_yearly_tons=900.0,  # TODO(plan-4): wire from CB flow data source
            etf_holdings_30d_change_tons=0.0,  # TODO(plan-4): wire from ETF holdings API
            geopolitical_stress_0to1=0.4,  # TODO(plan-4): wire from news sentiment pipeline
        )
        score = compute_gold_score(inputs, cfg)
        tilt = gold_tilt_from_score(score)
        scenario = classify_scenario(
            real_yield=inputs.real_yield_10y_tips, dxy=inputs.dxy,
            cb_purchases_yearly_tons=inputs.cb_purchases_yearly_tons,
            geopolitical_stress=inputs.geopolitical_stress_0to1,
        )
    finally:
        con.close()
    out_dir = root / "outputs" / _today()
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "gold_regime.json", json.dumps({
        "regime": regime.regime, "vol_ratio": regime.vol_ratio, "adx": regime.adx,
        "trend_sign": regime.trend_sign, "score": score, "tilt": tilt,
        "zone": zone,
        "scenario": scenario.scenario, "scenario_triggers": list(scenario.triggers_met),
    }, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "gold_band.yaml", yaml.safe_dump(asdict(band), sort_keys=False))
    print(f"gold OK: regime={regime.regime} score={score:.1f} tilt={tilt}")
    return 0
