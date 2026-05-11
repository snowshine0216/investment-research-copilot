from __future__ import annotations

import pandas as pd

from irc.discovery.metrics import (
    DISCOVERY_METRIC_COLUMNS,
    _tenure_or_zero,
    derive_discovery_metrics,
    empty_discovery_metrics,
    max_drawdown,
    merge_discovery_metrics,
)


def test_merge_discovery_metrics_fills_missing_primary_fields_from_fallback() -> None:
    primary = pd.DataFrame([{
        "instrument_id": "006075",
        "drawdown_3y": float("nan"),
        "tracking_error": 0.004,
        "manager_tenure_years": float("nan"),
    }])
    fallback = pd.DataFrame([{
        "instrument_id": "006075",
        "drawdown_3y": 0.18,
        "tracking_error": 0.0,
        "manager_tenure_years": 5.0,
    }])

    merged = merge_discovery_metrics(primary, fallback)
    row = merged.set_index("instrument_id").loc["006075"]

    assert row["drawdown_3y"] == 0.18
    assert row["tracking_error"] == 0.004
    assert row["manager_tenure_years"] == 5.0


def test_max_drawdown_empty_series_returns_zero() -> None:
    assert max_drawdown(pd.Series([], dtype=float)) == 0.0


def test_max_drawdown_all_negative_values_returns_zero() -> None:
    assert max_drawdown(pd.Series([-1.0, -2.0, -3.0])) == 0.0


def test_max_drawdown_typical_peak_to_trough() -> None:
    # 100 → 80 is a 20% drawdown
    result = max_drawdown(pd.Series([100.0, 80.0, 90.0]))
    assert abs(result - 0.20) < 1e-9


def test_derive_discovery_metrics_empty_dataframe_returns_empty() -> None:
    result = derive_discovery_metrics(pd.DataFrame(), "nav", {})
    assert list(result.columns) == list(DISCOVERY_METRIC_COLUMNS)
    assert result.empty


def test_derive_discovery_metrics_missing_value_col_returns_empty() -> None:
    df = pd.DataFrame({"instrument_id": ["A"], "price": [1.0]})
    result = derive_discovery_metrics(df, "nav", {})
    assert result.empty


def test_derive_discovery_metrics_computes_per_group() -> None:
    df = pd.DataFrame({
        "instrument_id": ["A", "A", "A"],
        "nav": [100.0, 80.0, 90.0],
    })
    result = derive_discovery_metrics(df, "nav", {"A": 3.5})
    row = result.set_index("instrument_id").loc["A"]
    assert abs(row["drawdown_3y"] - 0.20) < 1e-9
    assert row["manager_tenure_years"] == 3.5


def test_merge_discovery_metrics_both_empty_returns_empty() -> None:
    result = merge_discovery_metrics(empty_discovery_metrics(), empty_discovery_metrics())
    assert result.empty


def test_merge_discovery_metrics_primary_only_returns_primary() -> None:
    primary = pd.DataFrame([{
        "instrument_id": "A",
        "drawdown_3y": 0.10,
        "tracking_error": 0.01,
        "manager_tenure_years": 5.0,
    }])
    result = merge_discovery_metrics(primary, empty_discovery_metrics())
    assert len(result) == 1
    assert result.iloc[0]["drawdown_3y"] == 0.10


def test_tenure_or_zero_none_returns_zero() -> None:
    assert _tenure_or_zero(None) == 0.0


def test_tenure_or_zero_float_passes_through() -> None:
    assert _tenure_or_zero(5.5) == 5.5


# ── Task 27: rolling_tracking_error ──────────────────────────────────────────
from datetime import date, timedelta
from irc.discovery.metrics import rolling_tracking_error


def _series(start: date, values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [start + timedelta(days=i) for i in range(len(values))],
        "close": values,
    })


def test_rolling_tracking_error_zero_when_returns_match():
    instr = _series(date(2026, 1, 1), [100, 101, 102, 103, 104, 105])
    bench = _series(date(2026, 1, 1), [100, 101, 102, 103, 104, 105])
    te = rolling_tracking_error(instrument_prices=instr, benchmark_prices=bench, window=4)
    assert te == 0.0


def test_rolling_tracking_error_positive_when_returns_diverge():
    instr = _series(date(2026, 1, 1), [100, 102, 99, 105, 103, 110])
    bench = _series(date(2026, 1, 1), [100, 100, 100, 100, 100, 100])
    te = rolling_tracking_error(instrument_prices=instr, benchmark_prices=bench, window=4)
    assert te > 0.0


def test_rolling_tracking_error_returns_zero_with_insufficient_data():
    instr = _series(date(2026, 1, 1), [100, 101])
    bench = _series(date(2026, 1, 1), [100, 101])
    te = rolling_tracking_error(instrument_prices=instr, benchmark_prices=bench, window=20)
    assert te == 0.0
