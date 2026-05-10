from __future__ import annotations
from datetime import date
from evals.gold_score.metrics import (
    drivers_freshness,
    regime_flip_4w,
    tilt_within_preferences_band,
)


def test_drivers_freshness_recent():
    today = date.today()
    drivers = [
        {"name": "momentum", "updated_at": today.isoformat()},
        {"name": "value", "updated_at": today.isoformat()},
    ]
    result = drivers_freshness(drivers, reference_date=today)
    assert result["momentum"] == 0
    assert result["value"] == 0


def test_drivers_freshness_stale():
    ref = date(2024, 1, 15)
    drivers = [{"name": "macro", "updated_at": "2024-01-08"}]
    result = drivers_freshness(drivers, reference_date=ref)
    assert result["macro"] == 7


def test_drivers_freshness_invalid_date():
    drivers = [{"name": "bad", "updated_at": "not-a-date"}]
    result = drivers_freshness(drivers)
    assert result["bad"] == 9999


def test_regime_flip_4w_no_flips():
    history = [{"regime": "bull"}, {"regime": "bull"}, {"regime": "bull"}]
    assert regime_flip_4w(history) == 0


def test_regime_flip_4w_with_flips():
    history = [
        {"regime": "bull"}, {"regime": "bear"}, {"regime": "bull"},
        {"regime": "bear"}, {"regime": "bear"},
    ]
    assert regime_flip_4w(history) == 3


def test_regime_flip_4w_empty():
    assert regime_flip_4w([]) == 0


def test_tilt_within_preferences_band_all_in():
    tilt = {"equity": 0.6, "bond": 0.3, "cash": 0.1}
    prefs = {"equity": (0.4, 0.8), "bond": (0.2, 0.5)}
    assert tilt_within_preferences_band(tilt, prefs) == 1.0


def test_tilt_within_preferences_band_some_out():
    tilt = {"equity": 0.9, "bond": 0.3}
    prefs = {"equity": (0.4, 0.8), "bond": (0.2, 0.5)}
    assert tilt_within_preferences_band(tilt, prefs) == 0.5


def test_tilt_within_preferences_band_empty_prefs():
    assert tilt_within_preferences_band({}, {}) == 1.0
