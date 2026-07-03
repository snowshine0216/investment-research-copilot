"""D1 properties for aggregate_news_factor.

VALUE = clamp(Σ wᵢ·impactᵢ·confᵢ / Σwᵢ) — the weight-NORMALIZED mean (engine 4).
CONFIDENCE is likewise the weighted mean Σ(wᵢ·confᵢ)/Σwᵢ.
None on empty pool or non-positive total weight; value non-decreasing in a row's
impact when that row's weight ≥ 0 and confidence ≥ 0.

History: the original M2 property (spec §3.1 P2) locked an UNNORMALIZED sum;
with percent-scale constituent weights (Σw ≈ 30–50) and unit theme weights the
sum clamped to ±1.00 for nearly every fund (2026-07-02 trace: constituent 1.0
on 6/7 active funds), erasing magnitude discrimination — normalized as an
engine 3→4 scoring change.
"""
from __future__ import annotations
import dataclasses
from hypothesis import given, strategies as st
from irc.monitor.news_factor import aggregate_news_factor, ImpactRow

_EPS = 1e-9


@st.composite
def _rows(draw, min_size=0, max_size=5):
    n = draw(st.integers(min_size, max_size))
    return tuple(
        ImpactRow(
            key=f"k{i}",
            weight=draw(st.floats(0.0, 100.0, allow_nan=False)),
            impact=draw(st.floats(-1.0, 1.0, allow_nan=False)),
            confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
        )
        for i in range(n)
    )


def _clamp(x):
    return max(-1.0, min(1.0, x))


@given(rows=_rows())
def test_value_is_weight_normalized_mean(rows):
    value, _ = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if not rows or wsum <= 0:
        assert value is None
        return
    expected = _clamp(sum(r.weight * r.impact * r.confidence for r in rows) / wsum)
    assert abs(value - expected) < _EPS


@given(rows=_rows())
def test_value_in_unit_interval(rows):
    value, _ = aggregate_news_factor(rows)
    if value is not None:
        assert -1.0 <= value <= 1.0


@given(rows=_rows(min_size=1))
def test_confidence_is_weighted_mean(rows):
    _, conf = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if wsum > 0:
        expected = sum(r.weight * r.confidence for r in rows) / wsum
        assert abs(conf - expected) < _EPS


@given(rows=_rows(min_size=1), idx=st.integers(0, 4), bump=st.floats(0.0, 2.0))
def test_value_nondecreasing_in_a_rows_impact(rows, idx, bump):
    # Raising one row's impact (its weight ≥ 0 and confidence ≥ 0 by strategy) must
    # never lower the unclamped sum; clamp is monotone, so the clamped value too.
    i = idx % len(rows)
    base_val, _ = aggregate_news_factor(rows)
    raised = list(rows)
    raised[i] = dataclasses.replace(raised[i], impact=min(1.0, rows[i].impact + bump))
    raised_val, _ = aggregate_news_factor(tuple(raised))
    if base_val is None:        # Σw ≤ 0 → both None; nothing to compare
        assert raised_val is None
        return
    assert raised_val >= base_val - _EPS


@given(rows=_rows())
def test_none_on_empty_or_nonpositive_weight(rows):
    value, conf = aggregate_news_factor(rows)
    wsum = sum(r.weight for r in rows)
    if not rows or wsum <= 0:
        assert value is None and conf == 0.0
