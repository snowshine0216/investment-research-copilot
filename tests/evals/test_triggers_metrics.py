from __future__ import annotations
import pandas as pd
from evals.triggers.metrics import coverage_check, hit_rate_12m


def test_coverage_check_true_when_data_recent():
    out = coverage_check(triggers={"vix_high": "macro.vix"},
                          field_freshness_days={"macro.vix": 2})
    assert out["vix_high"] is True


def test_coverage_check_false_when_stale():
    out = coverage_check(triggers={"vix_high": "macro.vix"},
                          field_freshness_days={"macro.vix": 30})
    assert out["vix_high"] is False


def test_hit_rate():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=52, freq="W"),
                        "fired": [True] * 5 + [False] * 47})
    rate = hit_rate_12m(df)
    assert 0.05 < rate < 0.15
