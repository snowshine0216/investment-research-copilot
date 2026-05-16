from __future__ import annotations

import math

import pandas as pd
import pytest

from irc.opportunity.returns import (
    drawdown_since_entry,
    rolling_returns,
    self_history_percentile,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def test_rolling_returns_picks_each_window():
    s = _series([100.0] * 200 + [110.0] * 60)  # 260 points
    r = rolling_returns(s, as_of=s.index[-1])
    assert r["ret_1m"] == pytest.approx(0.0, abs=1e-9)
    assert r["ret_3m"] == pytest.approx(0.10, abs=1e-3)
    assert r["ret_6m"] == pytest.approx(0.10, abs=1e-3)
    assert r["ret_12m"] == pytest.approx(0.10, abs=1e-3)


def test_rolling_returns_returns_none_when_window_unavailable():
    s = _series([100.0, 101.0, 102.0])
    r = rolling_returns(s, as_of=s.index[-1])
    assert r["ret_1m"] is None
    assert r["ret_3m"] is None
    assert r["ret_6m"] is None
    assert r["ret_12m"] is None


def test_drawdown_since_entry_uses_running_peak_after_entry_date():
    s = _series([100.0, 120.0, 110.0, 130.0, 117.0])
    entry_date = s.index[1]
    dd = drawdown_since_entry(s, entry_date=entry_date)
    assert dd == pytest.approx((130.0 - 117.0) / 130.0)


def test_drawdown_since_entry_returns_none_when_no_data_after_entry():
    s = _series([100.0, 110.0])
    entry_date = s.index[-1] + pd.Timedelta(days=10)
    assert drawdown_since_entry(s, entry_date=entry_date) is None


def test_self_history_percentile_returns_fraction():
    # 30 values: 1..29 then 15 as the last value
    values = [float(i) for i in range(1, 30)] + [15.0]
    s = _series(values)
    pct = self_history_percentile(s)
    # count_le(15) in [1..29, 15]: values <= 15 are 1,2,...,15 and the extra 15 = 16 items
    # n=30, so pct = 16/30
    assert pct == pytest.approx(16.0 / 30.0)


def test_self_history_percentile_returns_none_for_short_series():
    s = _series([math.nan])
    assert self_history_percentile(s) is None
