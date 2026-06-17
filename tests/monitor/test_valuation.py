from __future__ import annotations

import pytest

from irc.monitor.valuation import percentile_to_valuation_state


@pytest.mark.parametrize("pct,expected", [
    (0.0, "cheap"),
    (0.19, "cheap"),
    (0.20, "reasonable_low"),   # boundary: < 0.20 is cheap; 0.20 rolls to next band
    (0.39, "reasonable_low"),
    (0.40, "fair"),
    (0.69, "fair"),
    (0.70, "expensive"),
    (0.89, "expensive"),
    (0.90, "very_expensive"),
    (1.0, "very_expensive"),
])
def test_percentile_maps_to_band(pct, expected):
    assert percentile_to_valuation_state(pct) == expected


def test_none_percentile_is_none():
    assert percentile_to_valuation_state(None) is None


def test_nan_percentile_is_none():
    assert percentile_to_valuation_state(float("nan")) is None
