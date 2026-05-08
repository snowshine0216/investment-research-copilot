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
