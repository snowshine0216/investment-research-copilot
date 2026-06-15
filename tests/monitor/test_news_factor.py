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


def test_zero_impact_row_counts_toward_confidence():
    rows = (
        ImpactRow(key="a", weight=0.5, impact=0.0, confidence=0.8),
        ImpactRow(key="b", weight=0.5, impact=0.4, confidence=0.4),
    )
    value, conf = aggregate_news_factor(rows)
    assert conf == pytest.approx((0.5 * 0.8 + 0.5 * 0.4) / 1.0)
