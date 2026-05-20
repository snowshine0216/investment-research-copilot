from __future__ import annotations
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from pathlib import Path
import json
import yaml
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.data.freshness import require_fresh_ingest
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.wgc_ingest import cb_purchases_yearly_tons, etf_holdings_30d_change_tons
from irc.io_utils import atomic_write_text
from irc.research.persistence import load_theme_reports
from irc.research.geopolitical_stress import geopolitical_stress_from_theme_report
from irc.scoring.regime_detect import classify_regime
from irc.scoring.gold_band import compute_band, classify_zone
from irc.scoring.gold_scenarios import classify_scenario
from irc.scoring.gold_score import (
    compute_gold_score,
    GoldDriverInputs,
    GoldTilt,
    gold_tilt_from_score,
)


# Tilt magnitude ordering for the regime-vs-drivers clamp.
_TILT_ORDER: tuple[GoldTilt, ...] = (
    "underweight", "neutral_minus", "neutral", "neutral_plus", "overweight",
)


def _combine_tilts(
    regime: str,
    drivers_tilt: GoldTilt,
    drivers_availability: str,
) -> GoldTilt:
    """Combine the regime-only tilt and the driver-score tilt.

    Adversarial review §B2: drivers_tilt should drive the decision when
    data is complete. When the regime contradicts the drivers (e.g.
    drivers say overweight but the price is trending down), clamp to
    neutral_plus so we never aggressively buy into a downtrend.
    """
    if drivers_availability == "unavailable":
        return "neutral"  # honest fallback — no driver signal
    if drivers_availability == "partial":
        # Be conservative: take the more cautious of regime-neutral vs drivers.
        idx = _TILT_ORDER.index(drivers_tilt)
        cautious_idx = min(idx, _TILT_ORDER.index("neutral_plus"))
        return _TILT_ORDER[cautious_idx]
    # complete: drivers dominate; clamp on trending_down + overweight
    if regime == "trending_down" and drivers_tilt == "overweight":
        return "neutral_plus"
    return drivers_tilt


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _gold_prices(con, instrument_id: str) -> pd.Series:
    df = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetch_df()
    return df["close"]


def _macro_value_or_none(con, series: str) -> float | None:
    row = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [series],
    ).fetchone()
    return float(row[0]) if row else None


def _macro_value(con, series: str, default: float) -> float:
    value = _macro_value_or_none(con, series)
    return value if value is not None else default


def _real_yield_10y_tips(con) -> float:
    value = _macro_value_or_none(con, "real_yield_10y_tips")
    if value is not None:
        return value
    return _macro_value(con, "DGS10", 1.65) - 2.30


def run_gold(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="gold"):
        print("ERROR: gold stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
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
        today = _today()
        wgc = root / "data" / "wgc"
        cb_tons = cb_purchases_yearly_tons(wgc / "cb_purchases.csv", as_of_year=int(today[:4]))
        etf_change = etf_holdings_30d_change_tons(wgc / "etf_holdings.csv", as_of=today)
        reports = load_theme_reports(root)
        # Use the "geopolitics" theme report — geopolitical risk is computed
        # from the dedicated geopolitics research (not the gold theme report).
        # This intentionally deviates from 010-spec.md which referenced "gold";
        # the geopolitics report is the semantically correct source for this signal.
        geo_stress = geopolitical_stress_from_theme_report(
            reports.get("geopolitics"),
        )
        # Track which drivers are real vs fallback so the gold report
        # can honestly say "drivers_availability=partial" when WGC data
        # is missing. Adversarial review §B2.
        unavailable_drivers: list[str] = []
        if cb_tons == 0.0:
            unavailable_drivers.append("cb_purchases_wgc")
        if etf_change == 0.0:
            unavailable_drivers.append("etf_holdings_gld")
        inputs = GoldDriverInputs(
            real_yield_10y_tips=_real_yield_10y_tips(con),
            dxy=_macro_value(con, "DXY", 104.0),
            inflation_5y5y=_macro_value(con, "inflation_5y5y", 2.30),
            cb_purchases_yearly_tons=cb_tons,
            etf_holdings_30d_change_tons=etf_change,
            geopolitical_stress_0to1=geo_stress,
        )
        if unavailable_drivers:
            print(
                "WARN: gold driver(s) using stub value; "
                f"WGC CSV absent for {', '.join(unavailable_drivers)} → 0.0 fallback"
            )
        drivers_score = compute_gold_score(inputs, cfg)
        drivers_tilt = gold_tilt_from_score(drivers_score)
        # 2 or more unavailable → "unavailable"; 1 → "partial"; 0 → "complete"
        if len(unavailable_drivers) >= 2:
            drivers_availability = "unavailable"
        elif unavailable_drivers:
            drivers_availability = "partial"
        else:
            drivers_availability = "complete"
        tilt = _combine_tilts(regime.regime, drivers_tilt, drivers_availability)
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
        "trend_sign": regime.trend_sign,
        # Legacy "score" preserved as alias of drivers_score for downstream
        # consumers; new fields are the source of truth.
        "score": drivers_score,
        "drivers_score": drivers_score,
        "drivers_tilt": drivers_tilt,
        "drivers_availability": drivers_availability,
        "drivers_unavailable": unavailable_drivers,
        "tilt": tilt,
        "zone": zone,
        "scenario": scenario.scenario, "scenario_triggers": list(scenario.triggers_met),
    }, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "gold_band.yaml", yaml.safe_dump(asdict(band), sort_keys=False))
    print(
        f"gold OK: regime={regime.regime} drivers={drivers_score:.1f} "
        f"({drivers_availability}) tilt={tilt}"
    )
    return 0
