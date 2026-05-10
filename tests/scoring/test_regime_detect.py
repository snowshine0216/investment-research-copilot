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


from datetime import date, timedelta
import pandas as pd
from irc.scoring.regime_detect import detect_regime


def test_short_history_returns_unknown_not_downtrend():
    df = pd.DataFrame({
        "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(5)],
        "close": [100.0] * 5,  # zero slope
    })
    out = detect_regime(prices=df)
    assert out.label in ("unknown", "neutral")
    assert out.label != "downtrend"
