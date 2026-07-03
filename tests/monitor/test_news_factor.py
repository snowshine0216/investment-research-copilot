import pytest
from irc.monitor.news_factor import aggregate_news_factor, ImpactRow


def test_weighted_impact_and_confidence():
    rows = (
        ImpactRow(key="us_monetary", weight=0.5, impact=0.8, confidence=0.9),
        ImpactRow(key="geopolitics", weight=0.5, impact=-0.4, confidence=0.6),
    )
    value, conf = aggregate_news_factor(rows)
    # value = 0.5*0.8*0.9 + 0.5*(-0.4)*0.6 = 0.36 - 0.12 = 0.24
    assert value == pytest.approx(0.24)
    # conf = (0.5*0.9 + 0.5*0.6) / (0.5+0.5) = 0.75
    assert conf == pytest.approx(0.75)


def test_empty_rows_is_none():
    value, conf = aggregate_news_factor(())
    assert value is None and conf == 0.0


def test_value_is_clamped():
    rows = (ImpactRow(key="t", weight=1.0, impact=5.0, confidence=1.0),)
    value, _ = aggregate_news_factor(rows)
    assert value == 1.0


def test_percent_scale_weights_do_not_saturate():
    """Constituent rows carry percent-scale holding weights (weight_pct, e.g.
    9.4 for 9.4%). The aggregate must be the weight-NORMALIZED mean — before
    the Σw normalization, Σ(w·i·c) ≈ 37·0.18 clamped to 1.0, pinning the
    constituent factor at ±1.00 for every active fund (observed in the
    2026-07-02 eval_trace: 6/7 funds at exactly 1.0)."""
    rows = tuple(
        ImpactRow(key=s, weight=w, impact=0.3, confidence=0.6)
        for s, w in (("600519", 9.4), ("601318", 8.1), ("601899", 7.5),
                     ("600036", 6.2), ("688256", 5.8))
    )
    value, conf = aggregate_news_factor(rows)
    assert value == pytest.approx(0.18)  # 0.3 * 0.6, not clamp(37 * 0.18) = 1.0
    assert conf == pytest.approx(0.6)


def test_equal_weight_theme_rows_average_not_sum():
    """Macro rows carry weight=1.0 per theme — the factor must be the mean
    impact across themes, not their sum (a 4-theme fund at impact 0.5 ×
    conf 0.8 each must score 0.4, not clamp(4 × 0.4) = 1.0)."""
    rows = tuple(
        ImpactRow(key=t, weight=1.0, impact=0.5, confidence=0.8)
        for t in ("us_monetary", "geopolitics", "cn_monetary", "global_growth")
    )
    value, _ = aggregate_news_factor(rows)
    assert value == pytest.approx(0.4)


def test_value_is_weight_scale_invariant():
    """Percent-scale and fraction-scale weights with the same relative mix
    must produce the same aggregate."""
    pct = (
        ImpactRow(key="a", weight=30.0, impact=0.6, confidence=0.5),
        ImpactRow(key="b", weight=10.0, impact=-0.2, confidence=1.0),
    )
    frac = (
        ImpactRow(key="a", weight=0.30, impact=0.6, confidence=0.5),
        ImpactRow(key="b", weight=0.10, impact=-0.2, confidence=1.0),
    )
    v_pct, c_pct = aggregate_news_factor(pct)
    v_frac, c_frac = aggregate_news_factor(frac)
    assert v_pct == pytest.approx(v_frac)
    assert c_pct == pytest.approx(c_frac)


def test_zero_impact_row_counts_toward_confidence():
    rows = (
        ImpactRow(key="a", weight=0.5, impact=0.0, confidence=0.8),
        ImpactRow(key="b", weight=0.5, impact=0.4, confidence=0.4),
    )
    value, conf = aggregate_news_factor(rows)
    assert conf == pytest.approx((0.5 * 0.8 + 0.5 * 0.4) / 1.0)
