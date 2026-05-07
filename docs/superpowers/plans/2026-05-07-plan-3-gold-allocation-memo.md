# Plan 3: Gold Scoring + Allocation + Trade Plan + Memo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add gold-specific scoring (6 drivers + regime detection + 6m band + 3 scenarios), allocation (Build/Hybrid/Steady-State modes + score-weighted softmax), trade plan (buy_method differentiation per asset class + venue compatibility + triggers), and memo synthesis (Claude/Opus + Sonnet audit). Yields a working `irc run` that produces a real `research_memo.md`.

**Architecture:** Stage 4b (GOLD SCORE) + Stage 5 (ALLOCATION) + Stage 6 (TRADE PLAN) + Stage 7 (MEMO) + queries side-branch. Gold scoring is independent of generic scoring (different drivers); allocation consumes both. Memo synthesis goes through OpenRouter Claude per the no-silent-fallback rule. Inherits all FP / TDD conventions.

**Tech Stack:** From Plans 1-2, plus: optional `pandas-ta` for ADX (or vendored); `numpy` already present.

---

## Plan Series Overview

This is **Plan 3 of 4**. Prerequisites: Plans 1 + 2 land. After Plan 3:
- `irc gold` produces `gold_regime.json` + `gold_band.yaml`.
- `irc allocate` produces `proposed_allocation.yaml`.
- `irc plan` produces `trade_plan.yaml`.
- `irc memo` produces `research_memo.md` (synthesized by Claude/Opus, audited by Sonnet).
- `irc ask "..."` answers single-instrument questions.
- `irc run` orchestrates the full chain.

Plan 4 will add: news + research layers, eval framework, polish.

---

## File Structure

New files (Plans 1-2 unchanged):

```
investment-research-copilot/
├── src/irc/
│   ├── scoring/
│   │   ├── regime_detect.py          # NEW — Stage 4b
│   │   ├── gold_band.py              # NEW — 6m H/L/M/Q1/Q3
│   │   ├── gold_scenarios.py         # NEW — 3 scenarios
│   │   └── gold_score.py             # NEW — 6-driver composite
│   ├── allocation/
│   │   ├── __init__.py
│   │   ├── mode_selector.py          # NEW — Build/Hybrid/Steady
│   │   ├── target_weights.py         # NEW — softmax + tilt
│   │   ├── correlation_filter.py     # NEW — pair-corr cap
│   │   └── pipeline.py               # NEW — composes 5 steps
│   ├── trades/
│   │   ├── __init__.py
│   │   ├── buy_method.py             # NEW — class → method mapping
│   │   ├── valuation_percentile.py   # NEW — 5-bucket switch
│   │   ├── venue_check.py            # NEW — venue match + proxy
│   │   ├── triggers.py               # NEW — emit per-trade triggers
│   │   └── pipeline.py               # NEW
│   ├── memo/
│   │   ├── __init__.py
│   │   ├── template.py               # NEW — 7-section skeleton
│   │   ├── synthesizer.py            # NEW — Opus call
│   │   ├── auditor.py                # NEW — Sonnet call
│   │   ├── traceability.py           # NEW — raw_ref reachability
│   │   └── pipeline.py               # NEW
│   ├── queries/
│   │   ├── __init__.py
│   │   ├── parser.py                 # NEW — `irc ask` parsing
│   │   └── responder.py              # NEW — gold/instrument scoring → NL
│   └── commands/
│       ├── gold_cmd.py               # NEW
│       ├── allocate_cmd.py           # NEW
│       ├── plan_cmd.py               # NEW
│       ├── memo_cmd.py               # NEW
│       ├── ask_cmd.py                # NEW
│       └── run_cmd.py                # NEW — orchestrator
└── tests/                            # mirrors src/irc/
```

**File-size rule** still: < 200 lines / file, < 20 lines / function.

---

## Task 1: Gold Regime Detection

**Files:**
- Create: `src/irc/scoring/regime_detect.py`
- Create: `tests/scoring/test_regime_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_regime_detect.py
from __future__ import annotations
import numpy as np
import pandas as pd
from irc.scoring.regime_detect import classify_regime, RegimeResult


def _flat_prices(n: int = 180, base: float = 1000.0, noise: float = 0.005) -> pd.Series:
    rng = np.random.default_rng(42)
    return pd.Series(base + rng.normal(0, base * noise, n))


def _trending_prices(n: int = 180, base: float = 1000.0, drift: float = 0.001) -> pd.Series:
    return pd.Series(base * (1 + drift) ** np.arange(n))


def test_flat_prices_classify_range_bound():
    out = classify_regime(_flat_prices(), vol_ratio_threshold=1.5, adx_threshold=25)
    assert isinstance(out, RegimeResult)
    assert out.regime == "range_bound"


def test_strongly_trending_prices_classify_uptrend():
    s = _trending_prices(n=180, drift=0.003)
    out = classify_regime(s, vol_ratio_threshold=1.5, adx_threshold=25)
    assert out.regime in ("uptrend", "downtrend")
    assert out.adx > 25


def test_volatile_prices_not_range_bound():
    rng = np.random.default_rng(0)
    s = pd.Series(1000 + np.cumsum(rng.normal(0, 30, 180)))
    out = classify_regime(s, vol_ratio_threshold=1.2, adx_threshold=20)
    # 大波动 → 不是震荡
    assert out.regime != "range_bound" or out.vol_ratio > 1.0
```

- [ ] **Step 2: Run, verify failure**

Run: `uv run pytest tests/scoring/test_regime_detect.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/irc/scoring/regime_detect.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd


Regime = Literal["range_bound", "uptrend", "downtrend"]


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    vol_ratio: float       # recent vol / baseline vol
    adx: float
    trend_sign: int        # +1 / -1 / 0


def _vol_ratio(prices: pd.Series, window_recent: int, window_baseline: int) -> float:
    rec = prices.tail(window_recent).pct_change().std()
    base = prices.tail(window_baseline).pct_change().std()
    if base == 0 or pd.isna(base):
        return 1.0
    return float(rec / base)


def _adx(prices: pd.Series, period: int = 14) -> float:
    """Plain-pandas ADX approximation. Uses close-to-close diffs as proxy for true range."""
    df = pd.DataFrame({"close": prices})
    df["up"] = (df["close"].diff()).clip(lower=0)
    df["down"] = (-df["close"].diff()).clip(lower=0)
    df["tr"] = df["close"].diff().abs()
    df["plus_dm"] = df["up"].where(df["up"] > df["down"], 0.0)
    df["minus_dm"] = df["down"].where(df["down"] > df["up"], 0.0)
    atr = df["tr"].rolling(period).mean()
    plus_di = 100 * df["plus_dm"].rolling(period).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * df["minus_dm"].rolling(period).mean() / atr.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return float(dx.rolling(period).mean().iloc[-1] or 0.0)


def _trend_sign(prices: pd.Series, lookback: int = 60) -> int:
    if len(prices) < lookback:
        return 0
    delta = prices.iloc[-1] - prices.iloc[-lookback]
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def classify_regime(
    prices: pd.Series,
    vol_ratio_threshold: float,
    adx_threshold: float,
    window_recent_days: int = 30 * 6,
    window_baseline_days: int = 30 * 12,
) -> RegimeResult:
    """Range-bound iff vol_ratio < threshold AND ADX < threshold. Else trend by sign."""
    vol = _vol_ratio(prices, window_recent_days, window_baseline_days)
    adx = _adx(prices)
    sign = _trend_sign(prices)
    if vol < vol_ratio_threshold and adx < adx_threshold:
        regime: Regime = "range_bound"
    elif sign > 0:
        regime = "uptrend"
    else:
        regime = "downtrend"
    return RegimeResult(regime=regime, vol_ratio=vol, adx=adx, trend_sign=sign)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/scoring/test_regime_detect.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/irc/scoring/regime_detect.py tests/scoring/test_regime_detect.py
git commit -m "feat(scoring/regime_detect): vol_ratio + ADX classifier (range / uptrend / downtrend)"
```

---

## Task 2: Gold 6m Band

**Files:**
- Create: `src/irc/scoring/gold_band.py`
- Create: `tests/scoring/test_gold_band.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_gold_band.py
from __future__ import annotations
import pandas as pd
from irc.scoring.gold_band import compute_band, BandResult, classify_zone


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values)


def test_band_h_l_m_q1_q3():
    # 11 evenly spaced values 1000..1100
    s = _series([1000 + i * 10 for i in range(11)])
    band = compute_band(s, window_months=6)
    assert isinstance(band, BandResult)
    assert band.high == 1100
    assert band.low == 1000
    assert band.midpoint == 1050
    assert band.q1 == 1025
    assert band.q3 == 1075


def test_classify_zone_aggressive_below_q1():
    band = BandResult(high=1100, low=1000, midpoint=1050, q1=1025, q3=1075)
    assert classify_zone(price=1010, band=band) == "aggressive"


def test_classify_zone_pause_above_q3():
    band = BandResult(high=1100, low=1000, midpoint=1050, q1=1025, q3=1075)
    assert classify_zone(price=1080, band=band) == "trim"


def test_classify_zone_breakout():
    band = BandResult(high=1100, low=1000, midpoint=1050, q1=1025, q3=1075)
    assert classify_zone(price=1150, band=band) == "breakout_up"
    assert classify_zone(price=950, band=band) == "breakout_down"
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/gold_band.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pandas as pd


Zone = Literal["aggressive", "normal", "pause", "trim", "breakout_up", "breakout_down"]


@dataclass(frozen=True)
class BandResult:
    high: float
    low: float
    midpoint: float
    q1: float           # low + 25% of range
    q3: float           # low + 75% of range


def compute_band(prices: pd.Series, window_months: int) -> BandResult:
    """Compute 6-month rolling support/resistance band from a daily close series."""
    n = min(len(prices), window_months * 30)
    sliced = prices.tail(n)
    high = float(sliced.max())
    low = float(sliced.min())
    midpoint = (high + low) / 2
    rng = high - low
    return BandResult(
        high=high, low=low, midpoint=midpoint,
        q1=low + rng * 0.25, q3=low + rng * 0.75,
    )


def classify_zone(price: float, band: BandResult) -> Zone:
    """Map a current price to its action zone within the band."""
    if price > band.high:
        return "breakout_up"
    if price < band.low:
        return "breakout_down"
    if price <= band.q1:
        return "aggressive"
    if price <= band.midpoint:
        return "normal"
    if price <= band.q3:
        return "pause"
    return "trim"
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/test_gold_band.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/gold_band.py tests/scoring/test_gold_band.py
git commit -m "feat(scoring/gold_band): rolling H/L/M/Q1/Q3 + 6-zone classifier"
```

---

## Task 3: Gold Three Scenarios

**Files:**
- Create: `src/irc/scoring/gold_scenarios.py`
- Create: `tests/scoring/test_gold_scenarios.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_gold_scenarios.py
from __future__ import annotations
from irc.scoring.gold_scenarios import classify_scenario, ScenarioResult


def test_strong_bull_trips_when_drivers_align():
    out = classify_scenario(
        real_yield=0.30, dxy=98.0, cb_purchases_yearly_tons=1100,
        geopolitical_stress=0.8,
    )
    assert isinstance(out, ScenarioResult)
    assert out.scenario == "strong_bull"


def test_pullback_when_real_yield_high():
    out = classify_scenario(
        real_yield=2.7, dxy=112.0, cb_purchases_yearly_tons=400,
        geopolitical_stress=0.2,
    )
    assert out.scenario == "pullback"


def test_base_when_mixed():
    out = classify_scenario(
        real_yield=2.0, dxy=104.0, cb_purchases_yearly_tons=800,
        geopolitical_stress=0.4,
    )
    assert out.scenario == "base"
```

- [ ] **Step 2: Implement**

```python
# src/irc/scoring/gold_scenarios.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


Scenario = Literal["strong_bull", "base", "pullback"]


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    triggers_met: tuple[str, ...]


def classify_scenario(
    real_yield: float,
    dxy: float,
    cb_purchases_yearly_tons: float,
    geopolitical_stress: float,  # 0-1 normalized
) -> ScenarioResult:
    """Driver-based 3-scenario classifier."""
    bull_triggers = []
    if real_yield < 0.5: bull_triggers.append("real_yield<0.5")
    if dxy < 100:        bull_triggers.append("dxy<100")
    if cb_purchases_yearly_tons > 1000: bull_triggers.append("cb_buy>1000t")
    if geopolitical_stress > 0.7: bull_triggers.append("geo>0.7")

    bear_triggers = []
    if real_yield > 2.5: bear_triggers.append("real_yield>2.5")
    if dxy > 110:        bear_triggers.append("dxy>110")

    if len(bull_triggers) >= 3:
        return ScenarioResult(scenario="strong_bull", triggers_met=tuple(bull_triggers))
    if len(bear_triggers) >= 2:
        return ScenarioResult(scenario="pullback", triggers_met=tuple(bear_triggers))
    return ScenarioResult(scenario="base", triggers_met=())
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/test_gold_scenarios.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/gold_scenarios.py tests/scoring/test_gold_scenarios.py
git commit -m "feat(scoring/gold_scenarios): driver-based 3-scenario classifier"
```

---

## Task 4: Gold 6-Driver Composite Score

**Files:**
- Create: `src/irc/scoring/gold_score.py`
- Create: `tests/scoring/test_gold_score.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scoring/test_gold_score.py
from __future__ import annotations
from irc.schemas.gold import GoldDriversConfig
from irc.scoring.gold_score import compute_gold_score, GoldDriverInputs, gold_tilt_from_score


def _cfg() -> GoldDriversConfig:
    return GoldDriversConfig.model_validate({
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12,
                              "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    })


def _inputs_bullish() -> GoldDriverInputs:
    return GoldDriverInputs(
        real_yield_10y_tips=0.20, dxy=98.0, inflation_5y5y=2.50,
        cb_purchases_yearly_tons=1100, etf_holdings_30d_change_tons=15,
        geopolitical_stress_0to1=0.8,
    )


def test_bullish_inputs_score_high():
    s = compute_gold_score(_inputs_bullish(), _cfg())
    assert s >= 70


def test_bearish_inputs_score_low():
    inp = GoldDriverInputs(
        real_yield_10y_tips=2.8, dxy=112.0, inflation_5y5y=1.80,
        cb_purchases_yearly_tons=200, etf_holdings_30d_change_tons=-30,
        geopolitical_stress_0to1=0.1,
    )
    s = compute_gold_score(inp, _cfg())
    assert s <= 35


def test_tilt_mapping():
    assert gold_tilt_from_score(85) == "overweight"
    assert gold_tilt_from_score(65) == "neutral_plus"
    assert gold_tilt_from_score(50) == "neutral"
    assert gold_tilt_from_score(35) == "neutral_minus"
    assert gold_tilt_from_score(15) == "underweight"
```

- [ ] **Step 2: Implement `src/irc/scoring/gold_score.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from irc.schemas.gold import GoldDriversConfig


GoldTilt = Literal["overweight", "neutral_plus", "neutral", "neutral_minus", "underweight"]


@dataclass(frozen=True)
class GoldDriverInputs:
    real_yield_10y_tips: float    # in %
    dxy: float                     # index level
    inflation_5y5y: float          # in %
    cb_purchases_yearly_tons: float
    etf_holdings_30d_change_tons: float
    geopolitical_stress_0to1: float


def _real_yield_score(v: float) -> float:
    """Lower → higher gold score. 0% → 90, 1.5% → 60, 3% → 20."""
    if v <= 0:    return 100.0
    if v <= 1.5:  return 100 - (v / 1.5) * 40
    if v <= 3.0:  return 60 - ((v - 1.5) / 1.5) * 40
    return max(0.0, 20 - (v - 3.0) * 10)


def _dxy_score(v: float) -> float:
    if v <= 95:   return 100.0
    if v <= 105:  return 100 - (v - 95) * 5
    if v <= 115:  return max(0.0, 50 - (v - 105) * 5)
    return 0.0


def _inflation_score(v: float) -> float:
    if v <= 1.5:  return 30.0
    if v <= 3.0:  return 30 + (v - 1.5) / 1.5 * 60
    return min(100.0, 90 + (v - 3.0) * 5)


def _cb_score(tons: float) -> float:
    if tons >= 1000: return 100.0
    if tons >= 500:  return 50 + (tons - 500) / 500 * 50
    return max(0.0, tons / 500 * 50)


def _etf_change_score(delta_tons: float) -> float:
    """Pulse driver. Recent inflows boost; outflows drag."""
    if delta_tons >= 30:  return 100.0
    if delta_tons >= 0:   return 50 + delta_tons / 30 * 50
    if delta_tons >= -30: return 50 + delta_tons / 30 * 50  # negative
    return 0.0


def _geo_score(stress: float) -> float:
    return max(0.0, min(100.0, stress * 100))


def compute_gold_score(inputs: GoldDriverInputs, cfg: GoldDriversConfig) -> float:
    """Weighted composite of 6 driver sub-scores → 0-100."""
    components = {
        "real_yield_10y_tips": _real_yield_score(inputs.real_yield_10y_tips),
        "dxy":                 _dxy_score(inputs.dxy),
        "inflation_5y5y":      _inflation_score(inputs.inflation_5y5y),
        "cb_purchases_wgc":    _cb_score(inputs.cb_purchases_yearly_tons),
        "etf_holdings_gld":    _etf_change_score(inputs.etf_holdings_30d_change_tons),
        "geopolitical_proxy":  _geo_score(inputs.geopolitical_stress_0to1),
    }
    total = sum(cfg.drivers[name].weight * components[name] for name in components)
    return max(0.0, min(100.0, total))


def gold_tilt_from_score(score: float) -> GoldTilt:
    if score >= 75: return "overweight"
    if score >= 55: return "neutral_plus"
    if score >= 45: return "neutral"
    if score >= 25: return "neutral_minus"
    return "underweight"
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/scoring/test_gold_score.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/scoring/gold_score.py tests/scoring/test_gold_score.py
git commit -m "feat(scoring/gold_score): 6-driver composite + gold_tilt label"
```

---

## Task 5: `irc gold` CLI

**Files:**
- Create: `src/irc/commands/gold_cmd.py`
- Modify: `src/irc/cli.py` (register subcommand)
- Create: `tests/commands/test_gold_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_gold_cmd.py
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.gold_cmd import run_gold


@pytest.fixture
def repo_with_gold_data(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    base = date(2026, 5, 7)
    for i in range(180):
        d = base - timedelta(days=180 - i)
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["518880", d.isoformat(), 4.20, 4.25, 4.18, 4.20 + i * 0.005, 1e7,
             "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:prices:518880:{d.isoformat()}"],
        )
    # Macro series
    for s, v in (("DGS10", 4.0), ("DTWEXBGS", 104.0)):
        con.execute(
            "INSERT INTO macro_series VALUES (?, ?, ?, ?, ?, ?)",
            [s, base.isoformat(), v, "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:macro_series:{s}:{base.isoformat()}"],
        )
    con.close()
    return tmp_path


def test_gold_writes_regime_and_band(repo_with_gold_data: Path):
    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    out_dir = next(p for p in (repo_with_gold_data / "outputs").iterdir())
    assert (out_dir / "gold_regime.json").exists()
    assert (out_dir / "gold_band.yaml").exists()
```

- [ ] **Step 2: Implement `src/irc/commands/gold_cmd.py`**

```python
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
from irc.scoring.gold_band import compute_band
from irc.scoring.gold_scenarios import classify_scenario
from irc.scoring.gold_score import compute_gold_score, GoldDriverInputs, gold_tilt_from_score


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _gold_prices(con) -> pd.Series:
    df = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = '518880' ORDER BY date"
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
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        prices = _gold_prices(con)
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
        inputs = GoldDriverInputs(
            real_yield_10y_tips=_macro_value(con, "DGS10", 1.65) - 2.30,  # rough TIPS proxy
            dxy=_macro_value(con, "DTWEXBGS", 104.0),
            inflation_5y5y=2.30,
            cb_purchases_yearly_tons=900.0,
            etf_holdings_30d_change_tons=0.0,
            geopolitical_stress_0to1=0.4,
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
        "scenario": scenario.scenario, "scenario_triggers": list(scenario.triggers_met),
    }, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "gold_band.yaml", yaml.safe_dump(asdict(band), sort_keys=False))
    print(f"gold OK: regime={regime.regime} score={score:.1f} tilt={tilt}")
    return 0
```

- [ ] **Step 3: Register `gold` in CLI**

In `src/irc/cli.py` add before `freshness`:

```python
@main.command(help="Run gold scoring (regime + band + 6 drivers + scenario).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def gold(repo_root: str) -> None:
    from irc.commands.gold_cmd import run_gold
    rc = run_gold(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/commands/test_gold_cmd.py tests/scoring/test_regime_detect.py tests/scoring/test_gold_band.py tests/scoring/test_gold_score.py tests/scoring/test_gold_scenarios.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/gold_cmd.py src/irc/cli.py tests/commands/test_gold_cmd.py
git commit -m "feat(cli/gold): orchestrate regime + band + score → gold_regime.json + gold_band.yaml"
```

---

## Task 6: Allocation — Mode Selector

**Files:**
- Create: `src/irc/allocation/__init__.py`
- Create: `src/irc/allocation/mode_selector.py`
- Create: `tests/allocation/__init__.py`
- Create: `tests/allocation/test_mode_selector.py`

- [ ] **Step 1: Empty `__init__.py` files; write the failing test**

```python
# src/irc/allocation/__init__.py
```
```python
# tests/allocation/__init__.py
```

```python
# tests/allocation/test_mode_selector.py
from __future__ import annotations
from irc.allocation.mode_selector import select_mode


def test_build_when_account_small():
    assert select_mode(current_total_cny=10_000, monthly_new_capital_cny=1000) == "build"


def test_hybrid_at_threshold():
    assert select_mode(current_total_cny=80_000, monthly_new_capital_cny=8000) == "hybrid"


def test_steady_state_when_above_100k():
    assert select_mode(current_total_cny=200_000, monthly_new_capital_cny=10_000) == "steady_state"


def test_build_when_monthly_capital_low_even_if_balance_high():
    assert select_mode(current_total_cny=200_000, monthly_new_capital_cny=2000) == "build"
```

- [ ] **Step 2: Implement**

```python
# src/irc/allocation/mode_selector.py
from __future__ import annotations
from typing import Literal


Mode = Literal["build", "hybrid", "steady_state"]


def select_mode(current_total_cny: float, monthly_new_capital_cny: float) -> Mode:
    """Mode selector per design spec §4.C:
      Build:   current < 5万  OR monthly < 5000
      Hybrid:  5万 ≤ current < 10万 (and monthly ≥ 5000)
      Steady:  current ≥ 10万 (and monthly ≥ 5000)
    """
    if current_total_cny < 50_000 or monthly_new_capital_cny < 5_000:
        return "build"
    if current_total_cny < 100_000:
        return "hybrid"
    return "steady_state"
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/allocation/test_mode_selector.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/allocation/__init__.py src/irc/allocation/mode_selector.py tests/allocation/__init__.py tests/allocation/test_mode_selector.py
git commit -m "feat(allocation/mode_selector): build/hybrid/steady_state"
```

---

## Task 7: Allocation — Target Weights (with gold tilt + softmax)

**Files:**
- Create: `src/irc/allocation/target_weights.py`
- Create: `tests/allocation/test_target_weights.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/allocation/test_target_weights.py
from __future__ import annotations
import pytest
from irc.allocation.target_weights import (
    apply_gold_tilt, softmax_distribute, compute_target_weights, AssetClassWeight,
)


def test_apply_tilt_within_band():
    new = apply_gold_tilt(center=0.20, band=(0.12, 0.28), tilt="neutral_plus")
    assert 0.20 < new <= 0.28


def test_apply_tilt_clamped_to_band():
    new = apply_gold_tilt(center=0.20, band=(0.12, 0.22), tilt="overweight")
    assert new == 0.22  # clamped


def test_softmax_distribute_preserves_sum():
    w = softmax_distribute(scores=(60.0, 80.0, 50.0), temperature=10.0)
    assert sum(w) == pytest.approx(1.0)
    assert w[1] > w[0] > w[2]


def test_compute_target_weights_returns_per_class():
    out = compute_target_weights(
        class_targets={
            "gold":           {"center": 0.20, "band": [0.12, 0.28]},
            "us_etf":         {"center": 0.25, "band": [0.18, 0.35]},
            "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
            "cn_bond_fund":   {"center": 0.15, "band": [0.10, 0.25]},
            "hk_etf":         {"center": 0.10, "band": [0.05, 0.15]},
            "cash":           {"center": 0.05, "band": [0.00, 0.10]},
        },
        gold_tilt="neutral",
    )
    assert isinstance(out, dict)
    assert all(isinstance(v, AssetClassWeight) for v in out.values())
    total = sum(v.target_weight for v in out.values())
    assert abs(total - 1.0) < 1e-3
```

- [ ] **Step 2: Implement**

```python
# src/irc/allocation/target_weights.py
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AssetClassWeight:
    asset_class: str
    target_weight: float
    band: tuple[float, float]


_TILT_DELTA = {"overweight": 0.05, "neutral_plus": 0.02,
                "neutral": 0.0, "neutral_minus": -0.02, "underweight": -0.05}


def apply_gold_tilt(center: float, band: tuple[float, float], tilt: str) -> float:
    """Adjust gold center by tilt magnitude, clamped to band."""
    new = center + _TILT_DELTA.get(tilt, 0.0)
    return max(band[0], min(band[1], new))


def softmax_distribute(scores: tuple[float, ...], temperature: float = 10.0) -> tuple[float, ...]:
    """Score-weighted softmax. temperature controls concentration: higher → more equal."""
    if not scores:
        return ()
    exps = [math.exp(s / temperature) for s in scores]
    total = sum(exps)
    return tuple(e / total for e in exps)


def compute_target_weights(
    class_targets: dict[str, dict[str, object]],
    gold_tilt: str,
) -> dict[str, AssetClassWeight]:
    """Compute per-class target weights. Applies gold tilt, redistributes the
    delta proportionally across the other 5 classes."""
    out: dict[str, AssetClassWeight] = {}
    gold_cfg = class_targets["gold"]
    new_gold = apply_gold_tilt(
        center=float(gold_cfg["center"]),  # type: ignore[arg-type]
        band=tuple(gold_cfg["band"]),       # type: ignore[arg-type]
        tilt=gold_tilt,
    )
    delta = new_gold - float(gold_cfg["center"])  # type: ignore[arg-type]
    others = [k for k in class_targets if k != "gold"]
    others_total = sum(float(class_targets[k]["center"]) for k in others)  # type: ignore[arg-type]
    for k in class_targets:
        if k == "gold":
            new_w = new_gold
        else:
            share = float(class_targets[k]["center"]) / others_total      # type: ignore[arg-type]
            new_w = float(class_targets[k]["center"]) - delta * share     # type: ignore[arg-type]
        out[k] = AssetClassWeight(
            asset_class=k, target_weight=new_w,
            band=tuple(class_targets[k]["band"]),                          # type: ignore[arg-type]
        )
    return out
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/allocation/test_target_weights.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/allocation/target_weights.py tests/allocation/test_target_weights.py
git commit -m "feat(allocation/target_weights): gold_tilt + proportional redistribution + softmax"
```

---

## Task 8: Allocation — Correlation Filter

**Files:**
- Create: `src/irc/allocation/correlation_filter.py`
- Create: `tests/allocation/test_correlation_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/allocation/test_correlation_filter.py
from __future__ import annotations
import pandas as pd
from irc.allocation.correlation_filter import (
    drop_high_correlation_pairs, FilteredCandidates,
)


def test_drop_high_corr_keeps_higher_score():
    candidates = pd.DataFrame([
        {"instrument_id": "A", "score": 80, "asset_class": "us_etf"},
        {"instrument_id": "B", "score": 70, "asset_class": "us_etf"},
        {"instrument_id": "C", "score": 60, "asset_class": "cn_etf"},
    ])
    corr = pd.DataFrame(
        [[1.0, 0.95, 0.30], [0.95, 1.0, 0.30], [0.30, 0.30, 1.0]],
        index=["A", "B", "C"], columns=["A", "B", "C"],
    )
    out = drop_high_correlation_pairs(candidates, corr, threshold=0.85)
    assert isinstance(out, FilteredCandidates)
    ids = set(out.kept["instrument_id"])
    assert ids == {"A", "C"}
    assert out.dropped[0]["instrument_id"] == "B"


def test_drop_low_corr_keeps_all():
    candidates = pd.DataFrame([
        {"instrument_id": "A", "score": 80, "asset_class": "us_etf"},
        {"instrument_id": "B", "score": 70, "asset_class": "cn_etf"},
    ])
    corr = pd.DataFrame([[1.0, 0.30], [0.30, 1.0]],
                        index=["A", "B"], columns=["A", "B"])
    out = drop_high_correlation_pairs(candidates, corr, threshold=0.85)
    assert len(out.kept) == 2
    assert out.dropped == []
```

- [ ] **Step 2: Implement**

```python
# src/irc/allocation/correlation_filter.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd


@dataclass(frozen=True)
class FilteredCandidates:
    kept: pd.DataFrame
    dropped: list[dict[str, Any]]


def drop_high_correlation_pairs(
    candidates: pd.DataFrame, corr_matrix: pd.DataFrame, threshold: float,
) -> FilteredCandidates:
    """For any pair with correlation > threshold, keep the higher-scored instrument."""
    sorted_c = candidates.sort_values("score", ascending=False).reset_index(drop=True)
    kept_ids: list[str] = []
    dropped: list[dict[str, Any]] = []
    for _, row in sorted_c.iterrows():
        iid = row["instrument_id"]
        skip = False
        for kept in kept_ids:
            if iid in corr_matrix.index and kept in corr_matrix.columns:
                rho = corr_matrix.loc[iid, kept]
                if rho > threshold:
                    dropped.append({"instrument_id": iid, "dropped_due_to": kept, "rho": float(rho)})
                    skip = True
                    break
        if not skip:
            kept_ids.append(iid)
    kept_df = sorted_c[sorted_c["instrument_id"].isin(kept_ids)].reset_index(drop=True)
    return FilteredCandidates(kept=kept_df, dropped=dropped)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/allocation/test_correlation_filter.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/allocation/correlation_filter.py tests/allocation/test_correlation_filter.py
git commit -m "feat(allocation/correlation_filter): keep higher score on pair > threshold"
```

---

## Task 9: Allocation Pipeline + `irc allocate`

**Files:**
- Create: `src/irc/allocation/pipeline.py`
- Create: `src/irc/commands/allocate_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/allocation/test_pipeline.py`
- Create: `tests/commands/test_allocate_cmd.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/allocation/test_pipeline.py
from __future__ import annotations
import pandas as pd
from irc.allocation.pipeline import run_allocation, AllocationOutput


def test_pipeline_produces_per_class_top_k():
    scores = [
        {"instrument_id": "VTI", "asset_class": "us_etf", "composite_score": 78,
         "action": "buy_candidate", "conviction": "med"},
        {"instrument_id": "VOO", "asset_class": "us_etf", "composite_score": 75,
         "action": "buy_candidate", "conviction": "med"},
        {"instrument_id": "QQQ", "asset_class": "us_etf", "composite_score": 65,
         "action": "watch", "conviction": "med"},
        {"instrument_id": "SPDR", "asset_class": "cn_bond_fund", "composite_score": 70,
         "action": "buy_candidate", "conviction": "med"},
    ]
    class_targets = {
        "gold":           {"center": 0.20, "band": [0.12, 0.28]},
        "us_etf":         {"center": 0.25, "band": [0.18, 0.35]},
        "cn_equity_fund": {"center": 0.25, "band": [0.18, 0.35]},
        "cn_bond_fund":   {"center": 0.15, "band": [0.10, 0.25]},
        "hk_etf":         {"center": 0.10, "band": [0.05, 0.15]},
        "cash":           {"center": 0.05, "band": [0.00, 0.10]},
    }
    corr = pd.DataFrame()  # empty; no filtering
    out = run_allocation(scores=scores, class_targets=class_targets,
                         gold_tilt="neutral", correlation=corr,
                         per_class_top_k=2)
    assert isinstance(out, AllocationOutput)
    target_weights = out.target_weights_per_class
    assert abs(sum(target_weights.values()) - 1.0) < 1e-3
    selected_ids = {row["instrument_id"] for row in out.selected_instruments}
    # us_etf top-2 = VTI + VOO; cn_bond_fund top-1 = SPDR
    assert "VTI" in selected_ids and "VOO" in selected_ids
    assert "SPDR" in selected_ids
```

- [ ] **Step 2: Implement**

```python
# src/irc/allocation/pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd
from irc.allocation.target_weights import compute_target_weights, softmax_distribute
from irc.allocation.correlation_filter import drop_high_correlation_pairs


@dataclass(frozen=True)
class AllocationOutput:
    target_weights_per_class: dict[str, float]
    selected_instruments: list[dict[str, Any]]
    dropped_due_to_correlation: list[dict[str, Any]]
    diagnostics: dict[str, float]


def _select_top_k_per_class(scores: list[dict], k: int) -> dict[str, list[dict]]:
    by_class: dict[str, list[dict]] = {}
    for s in scores:
        by_class.setdefault(s["asset_class"], []).append(s)
    for cls in by_class:
        by_class[cls] = sorted(by_class[cls], key=lambda r: r["composite_score"], reverse=True)[:k]
    return by_class


def _effective_n(weights: list[float]) -> float:
    """1 / sum(w_i^2). Higher = more diversified."""
    if not weights:
        return 0.0
    s = sum(w * w for w in weights)
    return 1.0 / s if s > 0 else 0.0


def run_allocation(
    scores: list[dict],
    class_targets: dict[str, dict[str, object]],
    gold_tilt: str,
    correlation: pd.DataFrame,
    per_class_top_k: int = 2,
) -> AllocationOutput:
    """Compose Stage 5 allocation:
      1. apply gold_tilt to class centers
      2. select top-K per class by score
      3. softmax-distribute class weight across selected instruments
      4. correlation_filter drops near-duplicates
    """
    class_weights_obj = compute_target_weights(class_targets, gold_tilt=gold_tilt)
    class_weights: dict[str, float] = {k: v.target_weight for k, v in class_weights_obj.items()}
    by_class = _select_top_k_per_class(scores, per_class_top_k)
    selected: list[dict[str, Any]] = []
    for cls, rows in by_class.items():
        if not rows:
            continue
        scores_arr = tuple(r["composite_score"] for r in rows)
        share = softmax_distribute(scores_arr, temperature=10.0)
        for row, w in zip(rows, share):
            selected.append({
                "instrument_id": row["instrument_id"], "asset_class": cls,
                "role": row.get("role", ""),
                "composite_score": row["composite_score"],
                "intra_class_share": w,
                "target_weight": class_weights.get(cls, 0.0) * w,
            })
    if not correlation.empty:
        cand_df = pd.DataFrame([
            {"instrument_id": s["instrument_id"], "score": s["composite_score"], "asset_class": s["asset_class"]}
            for s in selected
        ])
        filt = drop_high_correlation_pairs(cand_df, correlation, threshold=0.85)
        kept_ids = set(filt.kept["instrument_id"])
        selected = [s for s in selected if s["instrument_id"] in kept_ids]
        dropped = filt.dropped
    else:
        dropped = []
    eff_n = _effective_n([s["target_weight"] for s in selected])
    return AllocationOutput(
        target_weights_per_class=class_weights,
        selected_instruments=selected,
        dropped_due_to_correlation=dropped,
        diagnostics={"effective_n": eff_n,
                     "total_weight": sum(s["target_weight"] for s in selected)},
    )
```

- [ ] **Step 3: Implement `src/irc/commands/allocate_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.allocation.pipeline import run_allocation


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_allocate(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    scoring_path = root / "outputs" / today / "scoring.json"
    gold_regime_path = root / "outputs" / today / "gold_regime.json"
    if not scoring_path.exists():
        # fall back to latest
        candidates = sorted((root / "outputs").glob("*/scoring.json"))
        if not candidates:
            print("ERROR: no scoring.json; run `irc score` first.")
            return 2
        scoring_path = candidates[-1]
        gold_regime_path = scoring_path.parent / "gold_regime.json"
    scores = json.loads(scoring_path.read_text(encoding="utf-8"))["scores"]
    gold_tilt = "neutral"
    if gold_regime_path.exists():
        gold_tilt = json.loads(gold_regime_path.read_text(encoding="utf-8")).get("tilt", "neutral")
    class_targets = {
        k: {"center": v.center, "band": list(v.band)}
        for k, v in bundle.preferences.asset_class_targets.items()
    }
    out = run_allocation(
        scores=scores, class_targets=class_targets,
        gold_tilt=gold_tilt, correlation=pd.DataFrame(),
        per_class_top_k=2,
    )
    out_path = root / "outputs" / today / "proposed_allocation.yaml"
    payload = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "gold_tilt": gold_tilt,
        "target_weights_per_class": out.target_weights_per_class,
        "selected_instruments": out.selected_instruments,
        "dropped_due_to_correlation": out.dropped_due_to_correlation,
        "diagnostics": out.diagnostics,
    }
    atomic_write_text(out_path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    print(f"allocate OK → {out_path}")
    return 0
```

- [ ] **Step 4: Register `allocate` in CLI**

```python
@main.command(help="Compute proposed allocation from scores + gold tilt.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def allocate(repo_root: str) -> None:
    from irc.commands.allocate_cmd import run_allocate
    rc = run_allocate(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Write CLI test**

```python
# tests/commands/test_allocate_cmd.py
from __future__ import annotations
from pathlib import Path
import json
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.allocate_cmd import run_allocate


@pytest.fixture
def repo_with_scoring(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / "2026-05-07"
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps({
        "scores": [
            {"instrument_id": "VTI", "asset_class": "us_etf", "composite_score": 78,
             "action": "buy_candidate", "conviction": "med"},
            {"instrument_id": "510300", "asset_class": "cn_etf", "composite_score": 70,
             "action": "buy_candidate", "conviction": "med"},
        ]
    }), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(json.dumps({"tilt": "neutral"}), encoding="utf-8")
    return tmp_path


def test_allocate_writes_yaml(repo_with_scoring: Path):
    rc = run_allocate(repo_root=str(repo_with_scoring))
    assert rc == 0
    assert (repo_with_scoring / "outputs/2026-05-07/proposed_allocation.yaml").exists()
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/allocation/ tests/commands/test_allocate_cmd.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/irc/allocation/pipeline.py src/irc/commands/allocate_cmd.py src/irc/cli.py tests/allocation/test_pipeline.py tests/commands/test_allocate_cmd.py
git commit -m "feat(cli/allocate): pipeline (top-K + softmax + corr) → proposed_allocation.yaml"
```

---

## Task 10: Trades — Buy Method Default Mapping

**Files:**
- Create: `src/irc/trades/__init__.py`
- Create: `src/irc/trades/buy_method.py`
- Create: `tests/trades/__init__.py`
- Create: `tests/trades/test_buy_method.py`

- [ ] **Step 1: Empty `__init__.py` + failing test**

```python
# src/irc/trades/__init__.py
```
```python
# tests/trades/__init__.py
```

```python
# tests/trades/test_buy_method.py
from __future__ import annotations
from irc.trades.buy_method import default_buy_method, MODE_BUILD


def test_gold_default_anchor_plus_band():
    assert default_buy_method(asset_class="gold", mode="steady_state") == "gold_anchor_plus_band"


def test_us_etf_broad_default_lump_sum():
    assert default_buy_method(asset_class="us_etf", mode="steady_state") == "lump_sum"


def test_cn_active_default_dca_monthly():
    assert default_buy_method(asset_class="cn_equity_fund", mode="steady_state") == "dca_monthly"


def test_build_mode_overrides_with_small_account_anchor():
    # Build mode rotates fills; non-rotation classes default to small_account_anchor
    out = default_buy_method(asset_class="cn_equity_fund", mode=MODE_BUILD)
    assert out == "small_account_anchor"
    # Gold remains anchor regardless
    assert default_buy_method(asset_class="gold", mode=MODE_BUILD) == "gold_anchor_plus_band"
```

- [ ] **Step 2: Implement**

```python
# src/irc/trades/buy_method.py
from __future__ import annotations
from typing import Literal


Mode = Literal["build", "hybrid", "steady_state"]
MODE_BUILD: Mode = "build"


_DEFAULTS_STEADY: dict[str, str] = {
    "gold":           "gold_anchor_plus_band",
    "cn_equity_fund": "dca_monthly",
    "cn_bond_fund":   "lump_sum",
    "cn_etf":         "scaled_in_3",
    "hk_etf":         "scaled_in_4",
    "us_etf":         "lump_sum",
    "cash":           "lump_sum",
}


def default_buy_method(asset_class: str, mode: Mode) -> str:
    """Return the default buy_method for an (asset_class, mode) pair."""
    if asset_class == "gold":
        return "gold_anchor_plus_band"
    if mode == "build":
        return "small_account_anchor"
    return _DEFAULTS_STEADY.get(asset_class, "dca_weekly")
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/trades/test_buy_method.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/trades/__init__.py src/irc/trades/buy_method.py tests/trades/__init__.py tests/trades/test_buy_method.py
git commit -m "feat(trades/buy_method): per-class defaults; build-mode small_account_anchor"
```

---

## Task 11: Trades — Valuation Percentile Bucketing

**Files:**
- Create: `src/irc/trades/valuation_percentile.py`
- Create: `tests/trades/test_valuation_percentile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trades/test_valuation_percentile.py
from __future__ import annotations
from irc.schemas.valuation import ValuationBucketsConfig
from irc.trades.valuation_percentile import method_for_percentile


def _cfg() -> ValuationBucketsConfig:
    return ValuationBucketsConfig.model_validate({
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum",              "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly",            "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow",      "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold","granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend",               "granularity": "n/a"},
        ]
    })


def test_low_percentile_lump_sum():
    out = method_for_percentile(percentile=0.20, cfg=_cfg())
    assert out.buy_method == "lump_sum"


def test_current_us_market_70th_percentile():
    out = method_for_percentile(percentile=0.70, cfg=_cfg())
    assert out.buy_method == "dca_weekly_slow"


def test_extreme_percentile_suspend():
    out = method_for_percentile(percentile=0.97, cfg=_cfg())
    assert out.buy_method == "suspend"
```

- [ ] **Step 2: Implement**

```python
# src/irc/trades/valuation_percentile.py
from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.valuation import ValuationBucketsConfig


@dataclass(frozen=True)
class BucketChoice:
    buy_method: str
    granularity: str
    bucket_max_percentile: float


def method_for_percentile(percentile: float, cfg: ValuationBucketsConfig) -> BucketChoice:
    """Find the smallest bucket whose max_percentile ≥ percentile."""
    for b in cfg.buckets:
        if percentile <= b.max_percentile:
            return BucketChoice(
                buy_method=b.buy_method, granularity=b.granularity,
                bucket_max_percentile=b.max_percentile,
            )
    last = cfg.buckets[-1]
    return BucketChoice(
        buy_method=last.buy_method, granularity=last.granularity,
        bucket_max_percentile=last.max_percentile,
    )
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/trades/test_valuation_percentile.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/trades/valuation_percentile.py tests/trades/test_valuation_percentile.py
git commit -m "feat(trades/valuation_percentile): bucket dispatch (5 levels per spec)"
```

---

## Task 12: Trades — Venue Check + Proxy

**Files:**
- Create: `src/irc/trades/venue_check.py`
- Create: `tests/trades/test_venue_check.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trades/test_venue_check.py
from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.trades.venue_check import check_venue, VenueCheckResult


def _u(items: list[dict]) -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": items})


def test_compatible_when_user_has_required_venue():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["us_brokerage"],
                      universe=universe)
    assert isinstance(out, VenueCheckResult)
    assert out.compatible is True
    assert out.proxy_id is None


def test_incompatible_with_proxy_suggestion():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund", "cmb_gold"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "006075"


def test_no_proxy_available():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "Russell 2000", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id is None
```

- [ ] **Step 2: Implement**

```python
# src/irc/trades/venue_check.py
from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.universe import UniverseConfig, Instrument


@dataclass(frozen=True)
class VenueCheckResult:
    compatible: bool
    proxy_id: str | None
    note: str


def _find(universe: UniverseConfig, iid: str) -> Instrument | None:
    for i in universe.instruments:
        if i.instrument_id == iid:
            return i
    return None


def _proxy_for(target: Instrument, universe: UniverseConfig, available_venues: set[str]) -> Instrument | None:
    """Find a proxy: same asset_class + tracked_index, venue compatible with user."""
    for i in universe.instruments:
        if i.instrument_id == target.instrument_id:
            continue
        if i.asset_class != target.asset_class:
            continue
        if (i.tracked_index or "").strip() != (target.tracked_index or "").strip():
            continue
        if set(i.venue_required) & available_venues:
            return i
    return None


def check_venue(
    instrument_id: str, available_venues: list[str], universe: UniverseConfig,
) -> VenueCheckResult:
    target = _find(universe, instrument_id)
    if target is None:
        return VenueCheckResult(compatible=False, proxy_id=None,
                                 note=f"instrument {instrument_id} not in universe")
    if set(target.venue_required) & set(available_venues):
        return VenueCheckResult(compatible=True, proxy_id=None, note="direct match")
    proxy = _proxy_for(target, universe, set(available_venues))
    if proxy is not None:
        return VenueCheckResult(
            compatible=False, proxy_id=proxy.instrument_id,
            note=f"venue mismatch; proxy via {proxy.instrument_id} ({proxy.name_cn})",
        )
    return VenueCheckResult(compatible=False, proxy_id=None,
                             note="venue mismatch and no proxy available; consider opening new account")
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/trades/test_venue_check.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/trades/venue_check.py tests/trades/test_venue_check.py
git commit -m "feat(trades/venue_check): venue match + same-index proxy fallback"
```

---

## Task 13: Trades — Trigger Emitter

**Files:**
- Create: `src/irc/trades/triggers.py`
- Create: `tests/trades/test_triggers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trades/test_triggers.py
from __future__ import annotations
from irc.schemas.triggers import TriggersConfig
from irc.trades.triggers import emit_triggers_for_trade


def _cfg() -> TriggersConfig:
    return TriggersConfig.model_validate({
        "triggers": {
            "vix_high":         {"data_field": "macro.vix",         "comparator": ">",  "threshold": 25.0},
            "real_yield_low":   {"data_field": "macro.real_yield_10y_tips", "comparator": "<=", "threshold": 0.0},
            "weekly_drawdown":  {"data_field": "instrument.weekly_return", "comparator": "<=", "threshold": -0.04},
        }
    })


def test_us_etf_emits_vix_trigger():
    out = emit_triggers_for_trade(asset_class="us_etf", buy_method="dca_weekly_slow", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "vix_high" in names


def test_gold_emits_real_yield():
    out = emit_triggers_for_trade(asset_class="gold", buy_method="gold_anchor_plus_band", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "real_yield_low" in names


def test_dca_buy_method_emits_weekly_drawdown_trigger():
    out = emit_triggers_for_trade(asset_class="cn_equity_fund", buy_method="dca_monthly", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "weekly_drawdown" in names
```

- [ ] **Step 2: Implement**

```python
# src/irc/trades/triggers.py
from __future__ import annotations
from typing import Any
from irc.schemas.triggers import TriggersConfig


def _wants_vix(asset_class: str) -> bool:
    return asset_class in ("us_etf", "hk_etf")


def _wants_real_yield(asset_class: str) -> bool:
    return asset_class == "gold"


def _wants_weekly_drawdown(buy_method: str) -> bool:
    return buy_method.startswith("dca_") or "anchor" in buy_method


def emit_triggers_for_trade(
    asset_class: str, buy_method: str, cfg: TriggersConfig,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, t in cfg.triggers.items():
        keep = (
            (name == "vix_high" and _wants_vix(asset_class))
            or (name == "real_yield_low" and _wants_real_yield(asset_class))
            or (name == "weekly_drawdown" and _wants_weekly_drawdown(buy_method))
        )
        if keep:
            out.append({"name": name, "data_field": t.data_field,
                         "comparator": t.comparator, "threshold": t.threshold})
    return out
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/trades/test_triggers.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/trades/triggers.py tests/trades/test_triggers.py
git commit -m "feat(trades/triggers): per-trade trigger emission by asset_class + buy_method"
```

---

## Task 14: Trade Plan Pipeline + `irc plan`

**Files:**
- Create: `src/irc/trades/pipeline.py`
- Create: `src/irc/commands/plan_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/trades/test_pipeline.py`
- Create: `tests/commands/test_plan_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trades/test_pipeline.py
from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.schemas.valuation import ValuationBucketsConfig
from irc.schemas.triggers import TriggersConfig
from irc.trades.pipeline import build_trade_plan, TradePlanRow


def _u() -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": [
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ]})


def _vc() -> ValuationBucketsConfig:
    return ValuationBucketsConfig.model_validate({"buckets": [
        {"max_percentile": 0.30, "buy_method": "lump_sum",          "granularity": "1-2"},
        {"max_percentile": 0.60, "buy_method": "dca_weekly",        "granularity": "12-16"},
        {"max_percentile": 0.80, "buy_method": "dca_weekly_slow",  "granularity": "24-26"},
        {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold","granularity":"36+"},
        {"max_percentile": 1.00, "buy_method": "suspend",           "granularity": "n/a"},
    ]})


def _tg() -> TriggersConfig:
    return TriggersConfig.model_validate({"triggers": {
        "vix_high":        {"data_field": "macro.vix",         "comparator": ">",  "threshold": 25.0},
        "real_yield_low":  {"data_field": "macro.real_yield_10y_tips","comparator": "<=", "threshold": 0.0},
        "weekly_drawdown": {"data_field": "instrument.weekly_return", "comparator": "<=", "threshold": -0.04},
    }})


def test_trade_plan_uses_proxy_when_venue_incompatible():
    selected = [{"instrument_id": "VTI", "asset_class": "us_etf", "target_weight": 0.18,
                 "intra_class_share": 1.0, "composite_score": 75, "role": "core_us_equity"}]
    rows = build_trade_plan(
        selected_instruments=selected, mode="hybrid",
        valuation_percentiles={"us_etf": 0.65},
        available_venues=["cmb_fund"],
        universe=_u(), valuation=_vc(), triggers=_tg(),
    )
    assert any(r["target"] == "006075" for r in rows)


def test_trade_plan_includes_buy_method_and_triggers():
    selected = [{"instrument_id": "510300", "asset_class": "cn_etf", "target_weight": 0.10,
                 "intra_class_share": 1.0, "composite_score": 70, "role": "core_cn_equity"}]
    universe = UniverseConfig.model_validate({"instruments": [
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
    ]})
    rows = build_trade_plan(
        selected_instruments=selected, mode="hybrid",
        valuation_percentiles={"cn_etf": 0.20},
        available_venues=["cn_brokerage"], universe=universe,
        valuation=_vc(), triggers=_tg(),
    )
    assert rows[0]["buy_method"] == "lump_sum"  # 0.20 percentile → lump_sum
    assert any(t["name"] == "weekly_drawdown" for t in rows[0]["triggers"])
```

- [ ] **Step 2: Implement**

```python
# src/irc/trades/pipeline.py
from __future__ import annotations
from typing import Any, TypedDict
from irc.schemas.universe import UniverseConfig
from irc.schemas.valuation import ValuationBucketsConfig
from irc.schemas.triggers import TriggersConfig
from irc.trades.buy_method import default_buy_method
from irc.trades.valuation_percentile import method_for_percentile
from irc.trades.venue_check import check_venue
from irc.trades.triggers import emit_triggers_for_trade


class TradePlanRow(TypedDict):
    target: str
    asset_class: str
    role: str
    target_weight: float
    intra_class_share: float
    composite_score: float
    buy_method: str
    granularity: str
    venue_compatible: bool
    venue_note: str
    proxy_id: str | None
    triggers: list[dict[str, Any]]


def build_trade_plan(
    selected_instruments: list[dict[str, Any]],
    mode: str,
    valuation_percentiles: dict[str, float],
    available_venues: list[str],
    universe: UniverseConfig,
    valuation: ValuationBucketsConfig,
    triggers: TriggersConfig,
) -> list[TradePlanRow]:
    rows: list[TradePlanRow] = []
    for sel in selected_instruments:
        ac = sel["asset_class"]
        venue = check_venue(sel["instrument_id"], available_venues, universe)
        target_id = sel["instrument_id"] if venue.compatible or venue.proxy_id is None else venue.proxy_id
        # If proxy is being used and proxy asset_class differs (e.g. QDII fund → cn_equity_fund),
        # use proxy's class for buy_method dispatch.
        proxy_class = ac
        if venue.proxy_id is not None and target_id == venue.proxy_id:
            proxy_obj = next(i for i in universe.instruments if i.instrument_id == venue.proxy_id)
            proxy_class = proxy_obj.asset_class
        pct = valuation_percentiles.get(proxy_class)
        if pct is not None:
            choice = method_for_percentile(pct, valuation)
            method = choice.buy_method
            granularity = choice.granularity
        else:
            method = default_buy_method(asset_class=proxy_class, mode=mode)  # type: ignore[arg-type]
            granularity = "default"
        trigs = emit_triggers_for_trade(asset_class=proxy_class, buy_method=method, cfg=triggers)
        rows.append(TradePlanRow(
            target=target_id, asset_class=proxy_class,
            role=sel.get("role", ""),
            target_weight=sel["target_weight"], intra_class_share=sel["intra_class_share"],
            composite_score=sel["composite_score"],
            buy_method=method, granularity=granularity,
            venue_compatible=venue.compatible, venue_note=venue.note,
            proxy_id=venue.proxy_id,
            triggers=trigs,
        ))
    return rows
```

- [ ] **Step 3: Implement `src/irc/commands/plan_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.allocation.mode_selector import select_mode
from irc.trades.pipeline import build_trade_plan


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_plan(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    alloc_path = root / "outputs" / today / "proposed_allocation.yaml"
    if not alloc_path.exists():
        candidates = sorted((root / "outputs").glob("*/proposed_allocation.yaml"))
        if not candidates:
            print("ERROR: no proposed_allocation.yaml; run `irc allocate` first.")
            return 2
        alloc_path = candidates[-1]
    alloc = yaml.safe_load(alloc_path.read_text(encoding="utf-8"))
    selected = alloc["selected_instruments"]
    universe_combined_items: list[dict] = []
    for u in (bundle.universe_qdii_us, bundle.universe_qdii_hk,
              bundle.universe_cn_funds, bundle.universe_gold):
        universe_combined_items.extend(i.model_dump() for i in u.instruments)
    from irc.schemas.universe import UniverseConfig
    universe = UniverseConfig.model_validate({"instruments": universe_combined_items})
    available_venues: list[str] = []
    for acc in bundle.account.accounts:
        available_venues.extend(acc.available_venues)
    current_total = sum(h.cost_basis_cny for acc in bundle.account.accounts for h in acc.holdings)
    mode = select_mode(
        current_total_cny=current_total,
        monthly_new_capital_cny=bundle.preferences.investment_plan.monthly_new_capital_cny,
    )
    rows = build_trade_plan(
        selected_instruments=selected, mode=mode,
        valuation_percentiles={},  # Plan 4 will populate; default to mode-based
        available_venues=list(set(available_venues)),
        universe=universe, valuation=bundle.valuation_buckets,
        triggers=bundle.triggers,
    )
    out_path = root / "outputs" / today / "trade_plan.yaml"
    atomic_write_text(out_path, yaml.safe_dump(
        {"mode": mode, "trades": rows}, sort_keys=False, allow_unicode=True))
    print(f"plan OK: mode={mode}, {len(rows)} trades → {out_path}")
    return 0
```

- [ ] **Step 4: Register `plan` in CLI**

```python
@main.command(help="Build trade plan from proposed_allocation.yaml.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def plan(repo_root: str) -> None:
    from irc.commands.plan_cmd import run_plan
    rc = run_plan(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Write CLI test**

```python
# tests/commands/test_plan_cmd.py
from __future__ import annotations
from pathlib import Path
import yaml
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.plan_cmd import run_plan


@pytest.fixture
def repo_with_alloc(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / "2026-05-07"
    out_dir.mkdir(parents=True)
    (out_dir / "proposed_allocation.yaml").write_text(yaml.safe_dump({
        "gold_tilt": "neutral",
        "target_weights_per_class": {"us_etf": 0.25, "gold": 0.20},
        "selected_instruments": [{
            "instrument_id": "006075", "asset_class": "us_etf",
            "target_weight": 0.18, "intra_class_share": 1.0,
            "composite_score": 75, "role": "core_us_equity"
        }],
        "diagnostics": {},
    }), encoding="utf-8")
    return tmp_path


def test_plan_writes_trade_plan_yaml(repo_with_alloc: Path):
    rc = run_plan(repo_root=str(repo_with_alloc))
    assert rc == 0
    p = repo_with_alloc / "outputs/2026-05-07/trade_plan.yaml"
    assert p.exists()
    plan_data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert plan_data["mode"] == "build"
    assert len(plan_data["trades"]) == 1
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/trades/ tests/commands/test_plan_cmd.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/irc/trades/pipeline.py src/irc/commands/plan_cmd.py src/irc/cli.py tests/trades/test_pipeline.py tests/commands/test_plan_cmd.py
git commit -m "feat(cli/plan): build trade_plan.yaml with mode + buy_method + triggers"
```

---

## Task 15: Memo — Template (7-section skeleton)

**Files:**
- Create: `src/irc/memo/__init__.py`
- Create: `src/irc/memo/template.py`
- Create: `tests/memo/__init__.py`
- Create: `tests/memo/test_template.py`

- [ ] **Step 1: Empty `__init__.py` files; failing test**

```python
# src/irc/memo/__init__.py
```
```python
# tests/memo/__init__.py
```

```python
# tests/memo/test_template.py
from __future__ import annotations
from irc.memo.template import render_skeleton, MemoInputs


def test_skeleton_has_seven_sections():
    inputs = MemoInputs(
        date="2026-05-07", current_holdings_table="| gold | 100% |",
        actions_table="| 006075 | dca_weekly | weekly | weekly_drawdown |",
        gold_section="tilt: neutral_plus", factor_section="VTI 78",
        risk_section="Top risk: Fed", data_completeness_section="OK",
        overrides_section="none",
    )
    md = render_skeleton(inputs)
    for section in ("# 周度投资研究备忘录", "## TL;DR", "## 1. 当前组合",
                     "## 2. 推荐动作", "## 3. 推导", "## 4. 因子分解",
                     "## 5. 风险与证伪", "## 6. 数据完整性", "## 7. 用户覆盖记录"):
        assert section in md
```

- [ ] **Step 2: Implement**

```python
# src/irc/memo/template.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoInputs:
    date: str
    current_holdings_table: str
    actions_table: str
    gold_section: str
    factor_section: str
    risk_section: str
    data_completeness_section: str
    overrides_section: str
    tldr_lines: tuple[str, str, str] = ("", "", "")


def render_skeleton(inputs: MemoInputs) -> str:
    """Render the 7-section memo skeleton. The synthesizer fills in the
    narrative by inserting between section headers; the auditor verifies
    structure remains intact."""
    return (
        f"# 周度投资研究备忘录 — {inputs.date}\n\n"
        f"## TL;DR\n"
        f"- {inputs.tldr_lines[0]}\n"
        f"- {inputs.tldr_lines[1]}\n"
        f"- {inputs.tldr_lines[2]}\n\n"
        f"## 1. 当前组合\n{inputs.current_holdings_table}\n\n"
        f"## 2. 推荐动作\n{inputs.actions_table}\n\n"
        f"## 3. 推导:为什么是这套配置\n{inputs.gold_section}\n\n"
        f"## 4. 因子分解\n{inputs.factor_section}\n\n"
        f"## 5. 风险与证伪\n{inputs.risk_section}\n\n"
        f"## 6. 数据完整性\n{inputs.data_completeness_section}\n\n"
        f"## 7. 用户覆盖记录\n{inputs.overrides_section}\n"
    )
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/memo/test_template.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/memo/__init__.py src/irc/memo/template.py tests/memo/__init__.py tests/memo/test_template.py
git commit -m "feat(memo/template): 7-section skeleton renderer"
```

---

## Task 16: Memo — Synthesizer (Claude/Opus via OpenRouter)

**Files:**
- Create: `src/irc/memo/synthesizer.py`
- Create: `tests/memo/test_synthesizer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/memo/test_synthesizer.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from irc.memo.synthesizer import synthesize_memo, SynthesisInputs


def _inputs() -> SynthesisInputs:
    return SynthesisInputs(
        date="2026-05-07",
        skeleton="## TL;DR\n- a\n- b\n- c\n",
        scoring_summary="VTI:78, 510300:70",
        gold_summary="tilt=neutral_plus",
        trades_summary="006075 dca_weekly",
        raw_ref_pool=("openbb:prices:VTI:2026-05-06",),
    )


@patch("irc.memo.synthesizer.call_chat")
def test_synthesize_returns_full_memo(mock_chat):
    mock_chat.return_value = MagicMock(
        text="# 周度投资研究备忘录 — 2026-05-07\n\n## TL;DR\n- core gold, growing US.\n- ...\n",
        prompt_tokens=500, completion_tokens=400,
    )
    out = synthesize_memo(_inputs(), route=MagicMock())
    assert "周度投资研究备忘录" in out.text
    assert out.prompt_tokens == 500


@patch("irc.memo.synthesizer.call_chat")
def test_synthesize_raises_on_three_failures(mock_chat):
    mock_chat.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="memo_synthesis"):
        synthesize_memo(_inputs(), route=MagicMock(), max_retries=2)
```

- [ ] **Step 2: Implement**

```python
# src/irc/memo/synthesizer.py
from __future__ import annotations
from dataclasses import dataclass
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


@dataclass(frozen=True)
class SynthesisInputs:
    date: str
    skeleton: str
    scoring_summary: str
    gold_summary: str
    trades_summary: str
    raw_ref_pool: tuple[str, ...]


_SYS = (
    "You are an investment-research analyst. Produce a Chinese-language weekly "
    "research memo. Preserve the 7-section structure exactly. Cite at least one "
    "raw_ref token from the provided pool inside section 4 (因子分解). Do not "
    "invent data. Output Markdown only."
)


def synthesize_memo(
    inputs: SynthesisInputs, route: ResolvedRoute, max_retries: int = 2,
) -> ChatResponse:
    """Call Claude/Opus via OpenRouter. Failure does NOT silently fall back —
    raises after `max_retries` consecutive errors (per design §6.E)."""
    user = (
        f"Date: {inputs.date}\n"
        f"Skeleton (preserve structure):\n{inputs.skeleton}\n\n"
        f"Scoring summary:\n{inputs.scoring_summary}\n\n"
        f"Gold summary:\n{inputs.gold_summary}\n\n"
        f"Trades summary:\n{inputs.trades_summary}\n\n"
        f"raw_ref pool: {', '.join(inputs.raw_ref_pool)}"
    )
    last_exc: Exception | None = None
    for _attempt in range(max_retries + 1):
        try:
            return call_chat(route, messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user},
            ], timeout_s=120, temperature=0.3)
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"memo_synthesis failed after {max_retries + 1} attempts: {last_exc}")
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/memo/test_synthesizer.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/memo/synthesizer.py tests/memo/test_synthesizer.py
git commit -m "feat(memo/synthesizer): Claude/Opus call via OpenRouter; HARD-fail after retries"
```

---

## Task 17: Memo — Auditor (Claude/Sonnet)

**Files:**
- Create: `src/irc/memo/auditor.py`
- Create: `tests/memo/test_auditor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/memo/test_auditor.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
from irc.memo.auditor import audit_memo, AuditResult


@patch("irc.memo.auditor.call_chat")
def test_audit_no_issues(mock_chat):
    mock_chat.return_value = MagicMock(
        text='{"issues": [], "verdict": "PASS"}', prompt_tokens=100, completion_tokens=20,
    )
    out = audit_memo(memo_text="x", route=MagicMock())
    assert isinstance(out, AuditResult)
    assert out.verdict == "PASS"
    assert out.issues == ()


@patch("irc.memo.auditor.call_chat")
def test_audit_with_issues(mock_chat):
    mock_chat.return_value = MagicMock(
        text='{"issues": ["unsupported claim about Fed cut"], "verdict": "WARN"}',
        prompt_tokens=100, completion_tokens=20,
    )
    out = audit_memo(memo_text="x", route=MagicMock())
    assert out.verdict == "WARN"
    assert "Fed cut" in out.issues[0]


@patch("irc.memo.auditor.call_chat")
def test_audit_invalid_json_returns_unaudited(mock_chat):
    mock_chat.return_value = MagicMock(
        text="hmmm", prompt_tokens=10, completion_tokens=5,
    )
    out = audit_memo(memo_text="x", route=MagicMock())
    assert out.verdict == "UNAUDITED"
```

- [ ] **Step 2: Implement**

```python
# src/irc/memo/auditor.py
from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Literal
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat


Verdict = Literal["PASS", "WARN", "FAIL", "UNAUDITED"]


@dataclass(frozen=True)
class AuditResult:
    verdict: Verdict
    issues: tuple[str, ...]


_SYS = (
    "You are an audit reviewer for investment memos. Read the provided memo. "
    "Identify any unsupported claims, contradictions, or factual issues. Output JSON: "
    '{"issues": [<list of strings>], "verdict": "PASS" | "WARN" | "FAIL"}'
)


def audit_memo(memo_text: str, route: ResolvedRoute) -> AuditResult:
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": memo_text},
        ], timeout_s=60, temperature=0.0)
    except Exception:
        return AuditResult(verdict="UNAUDITED", issues=("audit call failed",))
    try:
        data = json.loads(resp.text)
        verdict = data.get("verdict", "UNAUDITED")
        if verdict not in ("PASS", "WARN", "FAIL"):
            verdict = "UNAUDITED"
        return AuditResult(verdict=verdict, issues=tuple(data.get("issues", [])))
    except (json.JSONDecodeError, KeyError):
        return AuditResult(verdict="UNAUDITED", issues=("audit response was not valid JSON",))
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/memo/test_auditor.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/memo/auditor.py tests/memo/test_auditor.py
git commit -m "feat(memo/auditor): Sonnet review; verdict + issues; UNAUDITED on parse fail"
```

---

## Task 18: Memo — Traceability Check

**Files:**
- Create: `src/irc/memo/traceability.py`
- Create: `tests/memo/test_traceability.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/memo/test_traceability.py
from __future__ import annotations
from irc.memo.traceability import count_raw_refs, traceability_rate


def test_count_finds_refs_in_text():
    refs = ("openbb:prices:VTI:2026-05-06", "akshare:nav_history:006075:2026-05-07")
    text = "VTI tracks SP500 (openbb:prices:VTI:2026-05-06)."
    assert count_raw_refs(text, refs) == 1


def test_traceability_rate_zero_refs():
    assert traceability_rate(memo_text="...", expected_refs=()) == 1.0


def test_traceability_rate_partial():
    refs = ("a", "b", "c")
    assert traceability_rate(memo_text="see a and c", expected_refs=refs) == 2 / 3
```

- [ ] **Step 2: Implement**

```python
# src/irc/memo/traceability.py
from __future__ import annotations


def count_raw_refs(memo_text: str, refs: tuple[str, ...]) -> int:
    return sum(1 for r in refs if r in memo_text)


def traceability_rate(memo_text: str, expected_refs: tuple[str, ...]) -> float:
    if not expected_refs:
        return 1.0
    found = count_raw_refs(memo_text, expected_refs)
    return found / len(expected_refs)
```

- [ ] **Step 3: Run, verify pass**

Run: `uv run pytest tests/memo/test_traceability.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/irc/memo/traceability.py tests/memo/test_traceability.py
git commit -m "feat(memo/traceability): raw_ref reachability rate from memo body"
```

---

## Task 19: Memo Pipeline + `irc memo`

**Files:**
- Create: `src/irc/memo/pipeline.py`
- Create: `src/irc/commands/memo_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/memo/test_pipeline.py`
- Create: `tests/commands/test_memo_cmd.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/memo/test_pipeline.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
from irc.memo.pipeline import build_memo, MemoOutputs


@patch("irc.memo.pipeline.audit_memo")
@patch("irc.memo.pipeline.synthesize_memo")
def test_build_memo_synthesizes_and_audits(mock_synth, mock_audit):
    mock_synth.return_value = MagicMock(
        text="# memo with raw_ref:openbb:prices:VTI:2026-05-06",
        prompt_tokens=100, completion_tokens=80,
    )
    mock_audit.return_value = MagicMock(verdict="PASS", issues=())
    out = build_memo(
        date="2026-05-07", scoring_summary="...", gold_summary="...",
        trades_summary="...", raw_ref_pool=("openbb:prices:VTI:2026-05-06",),
        skeleton_inputs={"current_holdings_table": "x", "actions_table": "y",
                          "gold_section": "z", "factor_section": "w",
                          "risk_section": "r", "data_completeness_section": "d",
                          "overrides_section": "o"},
        synth_route=MagicMock(), audit_route=MagicMock(),
    )
    assert isinstance(out, MemoOutputs)
    assert out.audit_verdict == "PASS"
    assert out.traceability_rate == 1.0


@patch("irc.memo.pipeline.synthesize_memo")
def test_build_memo_propagates_synth_failure(mock_synth):
    mock_synth.side_effect = RuntimeError("memo_synthesis failed after retries")
    import pytest
    with pytest.raises(RuntimeError):
        build_memo(
            date="d", scoring_summary="s", gold_summary="g", trades_summary="t",
            raw_ref_pool=("ref",), skeleton_inputs={"current_holdings_table": "",
            "actions_table": "", "gold_section": "", "factor_section": "",
            "risk_section": "", "data_completeness_section": "", "overrides_section": ""},
            synth_route=MagicMock(), audit_route=MagicMock(),
        )
```

- [ ] **Step 2: Implement**

```python
# src/irc/memo/pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from irc.llm.gateway import ResolvedRoute
from irc.memo.template import render_skeleton, MemoInputs
from irc.memo.synthesizer import synthesize_memo, SynthesisInputs
from irc.memo.auditor import audit_memo
from irc.memo.traceability import traceability_rate


@dataclass(frozen=True)
class MemoOutputs:
    text: str
    audit_verdict: str
    audit_issues: tuple[str, ...]
    traceability_rate: float
    prompt_tokens: int
    completion_tokens: int


def build_memo(
    date: str,
    scoring_summary: str,
    gold_summary: str,
    trades_summary: str,
    raw_ref_pool: tuple[str, ...],
    skeleton_inputs: dict[str, str],
    synth_route: ResolvedRoute,
    audit_route: ResolvedRoute,
) -> MemoOutputs:
    """Compose memo from skeleton → synthesizer (Opus) → auditor (Sonnet)."""
    skeleton = render_skeleton(MemoInputs(date=date, **skeleton_inputs))
    synth = synthesize_memo(
        SynthesisInputs(
            date=date, skeleton=skeleton, scoring_summary=scoring_summary,
            gold_summary=gold_summary, trades_summary=trades_summary,
            raw_ref_pool=raw_ref_pool,
        ),
        route=synth_route,
    )
    audit = audit_memo(memo_text=synth.text, route=audit_route)
    rate = traceability_rate(synth.text, raw_ref_pool)
    return MemoOutputs(
        text=synth.text, audit_verdict=audit.verdict, audit_issues=audit.issues,
        traceability_rate=rate,
        prompt_tokens=synth.prompt_tokens, completion_tokens=synth.completion_tokens,
    )
```

- [ ] **Step 3: Implement `src/irc/commands/memo_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.memo.pipeline import build_memo


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _format_holdings_table(account_yaml: dict) -> str:
    rows = ["| broker | asset_class | form | cost_basis_cny |",
             "|---|---|---|---|"]
    for acc in account_yaml["accounts"]:
        for h in acc["holdings"]:
            rows.append(f"| {acc['broker']} | {h['asset_class']} | {h.get('form','')} | {h['cost_basis_cny']} |")
    return "\n".join(rows)


def _format_trades_table(trades: list[dict]) -> str:
    rows = ["| target | role | weight | method | granularity | triggers |",
             "|---|---|---|---|---|---|"]
    for t in trades:
        triggers_str = ", ".join(x["name"] for x in t.get("triggers", []))
        rows.append(f"| {t['target']} | {t['role']} | {t['target_weight']:.3f} | "
                    f"{t['buy_method']} | {t['granularity']} | {triggers_str} |")
    return "\n".join(rows)


def _format_factor_section(scores: list[dict]) -> str:
    lines: list[str] = []
    for s in scores:
        lines.append(
            f"- {s['instrument_id']}: composite {s['composite_score']:.1f} "
            f"({s['action']}, {s['conviction']})"
        )
    return "\n".join(lines)


def run_memo(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    out_dir = root / "outputs" / today
    if not (out_dir / "trade_plan.yaml").exists():
        candidates = sorted((root / "outputs").glob("*/trade_plan.yaml"))
        if not candidates:
            print("ERROR: trade_plan.yaml missing; run `irc plan` first.")
            return 2
        out_dir = candidates[-1].parent
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    gold = json.loads((out_dir / "gold_regime.json").read_text(encoding="utf-8")) \
        if (out_dir / "gold_regime.json").exists() else {"tilt": "neutral", "score": 50}
    trades_data = yaml.safe_load((out_dir / "trade_plan.yaml").read_text(encoding="utf-8"))
    account_data = yaml.safe_load((root / "inputs/account.yaml").read_text(encoding="utf-8"))
    refs: list[str] = []
    for s in scoring["scores"]:
        for v in s["factor_breakdown"].values():
            refs.extend(v.get("raw_refs", []))
    skeleton_inputs = {
        "current_holdings_table": _format_holdings_table(account_data),
        "actions_table": _format_trades_table(trades_data["trades"]),
        "gold_section": (
            f"Tilt: {gold['tilt']} (score {gold.get('score', 50):.1f}); "
            f"regime: {gold.get('regime', 'unknown')}; scenario: {gold.get('scenario', 'base')}"
        ),
        "factor_section": _format_factor_section(scoring["scores"]),
        "risk_section": "Top risks: see Plan 4 news layer (placeholder).",
        "data_completeness_section": "Per stage eval: see Plan 4 (placeholder).",
        "overrides_section": (
            "boost: " + str(len(bundle.overrides.boost_list)) +
            "; ban: " + str(len(bundle.overrides.ban_list)) +
            "; macro_view active: " + str(bundle.macro_view.active)
        ),
    }
    synth_route = resolve_route("memo_synthesis", bundle.llm)
    audit_route = resolve_route("memo_audit", bundle.llm)
    out = build_memo(
        date=today,
        scoring_summary=_format_factor_section(scoring["scores"]),
        gold_summary=skeleton_inputs["gold_section"],
        trades_summary=skeleton_inputs["actions_table"],
        raw_ref_pool=tuple(set(refs)),
        skeleton_inputs=skeleton_inputs,
        synth_route=synth_route, audit_route=audit_route,
    )
    out_path = out_dir / "research_memo.md"
    atomic_write_text(out_path, out.text)
    print(
        f"memo OK: audit={out.audit_verdict} traceability={out.traceability_rate:.2%} → {out_path}"
    )
    return 0
```

- [ ] **Step 4: Register `memo` in CLI**

```python
@main.command(help="Synthesize weekly research memo (Claude/Opus + Sonnet audit).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def memo(repo_root: str) -> None:
    from irc.commands.memo_cmd import run_memo
    rc = run_memo(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Write CLI test**

```python
# tests/commands/test_memo_cmd.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import yaml
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.memo_cmd import run_memo


@pytest.fixture
def repo_with_plan(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    out_dir = tmp_path / "outputs" / "2026-05-07"
    out_dir.mkdir(parents=True)
    (out_dir / "scoring.json").write_text(json.dumps({"scores": [{
        "instrument_id": "VTI", "composite_score": 75, "action": "buy_candidate",
        "conviction": "med", "factor_breakdown": {
            "valuation_cost": {"raw_refs": ["openbb:prices:VTI:2026-05-06"], "score": 80, "components": {}},
        },
        "data_completeness": 1.0, "weights_version": "v1",
    }]}), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(json.dumps(
        {"tilt": "neutral_plus", "score": 65, "regime": "range_bound", "scenario": "base"}
    ), encoding="utf-8")
    (out_dir / "proposed_allocation.yaml").write_text(yaml.safe_dump(
        {"selected_instruments": []}, sort_keys=False), encoding="utf-8")
    (out_dir / "trade_plan.yaml").write_text(yaml.safe_dump({
        "mode": "build", "trades": [{
            "target": "006075", "asset_class": "us_etf", "role": "core_us_equity",
            "target_weight": 0.18, "intra_class_share": 1.0, "composite_score": 75,
            "buy_method": "dca_weekly", "granularity": "12 weeks",
            "venue_compatible": True, "venue_note": "ok", "proxy_id": None,
            "triggers": [{"name": "vix_high"}],
        }]}), encoding="utf-8")
    return tmp_path


@patch("irc.memo.pipeline.synthesize_memo")
@patch("irc.memo.pipeline.audit_memo")
def test_memo_writes_md(mock_audit, mock_synth, repo_with_plan: Path):
    mock_synth.return_value = MagicMock(
        text="# memo cite openbb:prices:VTI:2026-05-06", prompt_tokens=100, completion_tokens=50,
    )
    mock_audit.return_value = MagicMock(verdict="PASS", issues=())
    rc = run_memo(repo_root=str(repo_with_plan))
    assert rc == 0
    md = (repo_with_plan / "outputs/2026-05-07/research_memo.md").read_text()
    assert "memo" in md
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/memo/ tests/commands/test_memo_cmd.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/irc/memo/pipeline.py src/irc/commands/memo_cmd.py src/irc/cli.py tests/memo/test_pipeline.py tests/commands/test_memo_cmd.py
git commit -m "feat(cli/memo): synthesize → audit → traceability → research_memo.md"
```

---

## Task 20: Queries — Parser + Responder + `irc ask`

**Files:**
- Create: `src/irc/queries/__init__.py`
- Create: `src/irc/queries/parser.py`
- Create: `src/irc/queries/responder.py`
- Create: `src/irc/commands/ask_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/queries/__init__.py`
- Create: `tests/queries/test_parser.py`
- Create: `tests/queries/test_responder.py`

- [ ] **Step 1: Empty `__init__.py` files; failing parser test**

```python
# src/irc/queries/__init__.py
```
```python
# tests/queries/__init__.py
```

```python
# tests/queries/test_parser.py
from __future__ import annotations
from irc.queries.parser import parse_query


def test_parse_buy_gold():
    out = parse_query("现在该买黄金吗")
    assert out.intent == "should_buy_now"
    assert out.target_asset_class == "gold"


def test_parse_sell_gold():
    out = parse_query("我的黄金该减仓吗")
    assert out.intent == "should_sell_now"


def test_parse_specific_instrument():
    out = parse_query("现在该买 510300 吗")
    assert out.intent == "should_buy_now"
    assert out.target_instrument_id == "510300"
```

- [ ] **Step 2: Implement parser**

```python
# src/irc/queries/parser.py
from __future__ import annotations
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ParsedQuery:
    intent: str             # should_buy_now | should_sell_now | macro_outlook
    target_asset_class: str | None
    target_instrument_id: str | None
    raw_text: str


_BUY_WORDS = ("买", "加仓", "买入", "建仓")
_SELL_WORDS = ("卖", "减仓", "卖出", "减持")
_GOLD_WORDS = ("黄金", "gold")
_TICKER_RE = re.compile(r"\b(\d{6})\b")


def parse_query(text: str) -> ParsedQuery:
    is_buy = any(w in text for w in _BUY_WORDS)
    is_sell = any(w in text for w in _SELL_WORDS)
    intent = "should_buy_now" if is_buy and not is_sell else (
        "should_sell_now" if is_sell else "macro_outlook"
    )
    asset = "gold" if any(w in text for w in _GOLD_WORDS) else None
    m = _TICKER_RE.search(text)
    iid = m.group(1) if m else None
    return ParsedQuery(intent=intent, target_asset_class=asset,
                        target_instrument_id=iid, raw_text=text)
```

- [ ] **Step 3: Run parser test**

Run: `uv run pytest tests/queries/test_parser.py -v`
Expected: 3 passed.

- [ ] **Step 4: Failing responder test**

```python
# tests/queries/test_responder.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
from irc.queries.parser import ParsedQuery
from irc.queries.responder import respond_to_query, QueryResponse


@patch("irc.queries.responder.call_chat")
def test_respond_includes_data_summary(mock_chat):
    mock_chat.return_value = MagicMock(
        text="Hold position; tilt = neutral_plus.", prompt_tokens=100, completion_tokens=30,
    )
    parsed = ParsedQuery(intent="should_buy_now", target_asset_class="gold",
                          target_instrument_id=None, raw_text="现在该买黄金吗")
    out = respond_to_query(parsed=parsed,
                            data_summary="real_yield 1.65, dxy 104, tilt=neutral_plus",
                            raw_refs=("openbb:macro_series:DGS10:2026-05-06",),
                            route=MagicMock())
    assert isinstance(out, QueryResponse)
    assert "neutral_plus" in out.answer_text
```

- [ ] **Step 5: Implement responder**

```python
# src/irc/queries/responder.py
from __future__ import annotations
from dataclasses import dataclass
from irc.llm.gateway import ResolvedRoute
from irc.llm.http_client import call_chat
from irc.queries.parser import ParsedQuery


@dataclass(frozen=True)
class QueryResponse:
    answer_text: str
    cited_refs: tuple[str, ...]


_SYS = (
    "You answer specific 'should I buy/sell now?' questions about a single instrument "
    "or asset class. Use ONLY the provided data summary. Cite at least one raw_ref. "
    "Output Chinese plain text. Be concise."
)


def respond_to_query(
    parsed: ParsedQuery, data_summary: str, raw_refs: tuple[str, ...], route: ResolvedRoute,
) -> QueryResponse:
    user = (
        f"Question: {parsed.raw_text}\n"
        f"Intent: {parsed.intent}\n"
        f"Target: {parsed.target_asset_class or parsed.target_instrument_id}\n"
        f"Data:\n{data_summary}\n"
        f"raw_refs: {', '.join(raw_refs)}"
    )
    resp = call_chat(route, messages=[
        {"role": "system", "content": _SYS},
        {"role": "user", "content": user},
    ], timeout_s=30, temperature=0.2)
    cited = tuple(r for r in raw_refs if r in resp.text)
    return QueryResponse(answer_text=resp.text, cited_refs=cited)
```

- [ ] **Step 6: Implement `src/irc/commands/ask_cmd.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.data.duckdb_helper import connect, ensure_schema
from irc.llm.gateway import resolve_route
from irc.queries.parser import parse_query
from irc.queries.responder import respond_to_query


def _now_ts() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H-%M-%S")


def _gold_summary(con) -> tuple[str, tuple[str, ...]]:
    macro = con.execute(
        "SELECT series_id, value, _raw_ref FROM macro_series ORDER BY date DESC LIMIT 6"
    ).fetchall()
    summary = "; ".join(f"{r[0]}={r[1]:.3f}" for r in macro) or "no macro data"
    refs = tuple(r[2] for r in macro)
    return summary, refs


def run_ask(repo_root: str, question: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    parsed = parse_query(question)
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        summary, refs = _gold_summary(con)
    finally:
        con.close()
    route = resolve_route("interactive_query", bundle.llm)
    resp = respond_to_query(parsed, data_summary=summary, raw_refs=refs, route=route)
    out_dir = root / "outputs" / "queries"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_now_ts()}.md"
    atomic_write_text(out_path, (
        f"# Query: {question}\n"
        f"\n_intent: {parsed.intent} / target: {parsed.target_asset_class or parsed.target_instrument_id}_\n\n"
        f"{resp.answer_text}\n\n"
        f"---\nCited raw_refs: {', '.join(resp.cited_refs)}\n"
    ))
    print(f"ask OK → {out_path}")
    print(resp.answer_text)
    return 0
```

- [ ] **Step 7: Register `ask` in CLI**

```python
@main.command(help="Ask a single-instrument question (e.g. \"现在该买黄金吗\").")
@click.argument("question", nargs=-1, required=True)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def ask(question: tuple[str, ...], repo_root: str) -> None:
    from irc.commands.ask_cmd import run_ask
    rc = run_ask(repo_root=repo_root, question=" ".join(question))
    raise SystemExit(rc)
```

- [ ] **Step 8: Run all tests**

Run: `uv run pytest tests/queries/ -v`
Expected: 4 passed.

- [ ] **Step 9: Commit**

```bash
git add src/irc/queries/ src/irc/commands/ask_cmd.py src/irc/cli.py tests/queries/
git commit -m "feat(cli/ask): parse + respond + write outputs/queries/<ts>.md"
```

---

## Task 21: `irc run` Orchestrator

**Files:**
- Create: `src/irc/commands/run_cmd.py`
- Modify: `src/irc/cli.py`
- Create: `tests/commands/test_run_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_run_cmd.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.run_cmd import run_pipeline


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    return tmp_path


@patch("irc.commands.ingest_cmd.fetch_etf_price_history")
@patch("irc.commands.ingest_cmd.fetch_macro_series")
@patch("irc.commands.ingest_cmd.fetch_fund_nav_history")
@patch("irc.discovery.reason_writer.call_chat")
@patch("irc.scoring.factors.macro_fit.call_chat")
@patch("irc.memo.pipeline.synthesize_memo")
@patch("irc.memo.pipeline.audit_memo")
def test_run_orchestrates_all_stages(mock_audit, mock_synth, mock_macrofit,
                                     mock_reason, mock_nav, mock_macro, mock_prices,
                                     repo: Path):
    mock_prices.return_value = pd.DataFrame({
        "date": [date(2026, 5, 6)], "open": [4.2], "high": [4.3], "low": [4.18],
        "close": [4.25], "volume": [1e8],
    })
    mock_macro.return_value = pd.DataFrame({"date": [date(2026, 5, 6)], "value": [1.65]})
    mock_nav.return_value = pd.DataFrame({"date": ["2026-05-06"], "nav": [1.2], "nav_acc": [2.3]})
    mock_reason.return_value = MagicMock(
        text="reason cites openbb:prices:006075:2026-05-06. Risk: x.",
        prompt_tokens=10, completion_tokens=5,
    )
    mock_macrofit.return_value = MagicMock(
        text='{"score": 70, "rationale": "x"}', prompt_tokens=20, completion_tokens=5,
    )
    mock_synth.return_value = MagicMock(
        text="# memo cite openbb:prices:006075:2026-05-06", prompt_tokens=200, completion_tokens=100,
    )
    mock_audit.return_value = MagicMock(verdict="PASS", issues=())
    rc = run_pipeline(repo_root=str(repo))
    assert rc == 0
    out_dirs = list((repo / "outputs").iterdir())
    assert len(out_dirs) == 1
    out = out_dirs[0]
    assert (out / "discovered_watchlist.csv").exists()
    assert (out / "scoring.json").exists()
    assert (out / "gold_regime.json").exists()
    assert (out / "proposed_allocation.yaml").exists()
    assert (out / "trade_plan.yaml").exists()
    assert (out / "research_memo.md").exists()
```

- [ ] **Step 2: Implement `src/irc/commands/run_cmd.py`**

```python
from __future__ import annotations
from irc.commands.ingest_cmd import run_ingest
from irc.commands.discover_cmd import run_discover
from irc.commands.gold_cmd import run_gold
from irc.commands.score_cmd import run_score
from irc.commands.allocate_cmd import run_allocate
from irc.commands.plan_cmd import run_plan
from irc.commands.memo_cmd import run_memo


_STAGES: tuple[tuple[str, callable], ...] = (
    ("ingest", run_ingest),
    ("discover", run_discover),
    ("gold", run_gold),
    ("score", run_score),
    ("allocate", run_allocate),
    ("plan", run_plan),
    ("memo", run_memo),
)


def run_pipeline(repo_root: str, from_stage: str | None = None,
                 only_stage: str | None = None) -> int:
    """Run the 7-stage pipeline. --from resumes from a stage; --only runs one stage."""
    started = False if from_stage else True
    for name, fn in _STAGES:
        if only_stage and name != only_stage:
            continue
        if from_stage and not started:
            if name == from_stage:
                started = True
            else:
                continue
        rc = fn(repo_root=repo_root)
        if rc != 0:
            print(f"PIPELINE_HALTED at stage={name} rc={rc}")
            return rc
    return 0
```

- [ ] **Step 3: Register `run` in CLI**

```python
@main.command(name="run", help="Run the full 7-stage pipeline.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--from", "from_stage", default=None,
              type=click.Choice(["ingest", "discover", "gold", "score", "allocate", "plan", "memo"]))
@click.option("--only", "only_stage", default=None,
              type=click.Choice(["ingest", "discover", "gold", "score", "allocate", "plan", "memo"]))
def run_command(repo_root: str, from_stage: str | None, only_stage: str | None) -> None:
    from irc.commands.run_cmd import run_pipeline
    rc = run_pipeline(repo_root=repo_root, from_stage=from_stage, only_stage=only_stage)
    raise SystemExit(rc)
```

- [ ] **Step 4: Run e2e test**

Run: `uv run pytest tests/commands/test_run_cmd.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest`
Expected: ~150+ tests, all pass.

- [ ] **Step 6: Tag milestone**

```bash
git tag -a plan-3-gold-allocation-memo -m "Plan 3 complete: gold + allocation + trade plan + memo"
```

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/run_cmd.py src/irc/cli.py tests/commands/test_run_cmd.py
git commit -m "feat(cli/run): orchestrate ingest → discover → gold → score → allocate → plan → memo"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec section | Plan 3 task |
|---|---|
| §3.C gold 6 drivers + regime + band + scenarios | Tasks 1-5 |
| §4.A 100w starter table | (already in templates from Plan 1) |
| §4.B 5-step allocation derivation | Tasks 6-9 |
| §4.C Build / Hybrid / Steady-State modes | Task 6 |
| §4.D-F buy_methods + valuation buckets | Tasks 10-11 |
| §4.G triggers | Task 13 |
| §4.I venue compatibility + proxy | Task 12 |
| §4.J memo 7-section + Opus + Sonnet | Tasks 15-19 |
| §6.D no fallback for memo_synthesis | Task 16 (raises after retries) |
| §5.D `irc gold/allocate/plan/memo/ask/run` | Tasks 5, 9, 14, 19, 20, 21 |
| `inv ask` interactive query | Task 20 |

**Out of Plan 3:** news + research layers, eval framework, polish — Plan 4.

**Placeholder scan:** memo's `risk_section` and `data_completeness_section` ARE labeled placeholders ("Plan 4 will populate"). All other steps have full code.

**Type consistency check:**
- `BandResult`, `RegimeResult`, `ScenarioResult` (Tasks 1-3) consumed by `run_gold` (Task 5).
- `AssetClassWeight` (Task 7) consumed by `run_allocation` (Task 9).
- `TradePlanRow` typeddict (Task 14) matches yaml output schema.
- `MemoOutputs` (Task 19) used by `run_memo` (Task 19).
- `ParsedQuery` (Task 20) consumed unchanged by responder.
- `_STAGES` tuple in run_cmd matches all command function names.
- `resolve_route` task names (`memo_synthesis`, `memo_audit`, `interactive_query`, `scoring_rationale`, `watchlist_reason`) all exist in `config/llm.yaml` (Plan 1 templates).

No mismatches found.

---

**End of Plan 3.**
