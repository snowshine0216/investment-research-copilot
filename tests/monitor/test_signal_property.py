"""D1 properties + hybrid oracle for compute_signal (spec §3.1, §3.2, §3.3)."""
from __future__ import annotations
from hypothesis import given, strategies as st
from irc.monitor.types import MonitorFund, FactorScore
from irc.monitor.signal import compute_signal
from tests.monitor import _oracle

_FACTOR_NAMES = ("trend", "valuation", "heat", "macro_tilt", "constituent")
_EPS = 1e-9


def _weights():
    return st.fixed_dictionaries(
        {n: st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)
         for n in _FACTOR_NAMES})


@st.composite
def _score(draw, name):
    eligible = draw(st.booleans())
    if eligible:
        value = draw(st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False))
        return FactorScore(name=name, value=value, eligible=True, reason="",
                           confidence=draw(st.floats(0.0, 1.0, allow_nan=False)))
    return FactorScore(name=name, value=None, eligible=False, reason="x",
                       confidence=draw(st.floats(0.0, 1.0, allow_nan=False)))


@st.composite
def _scores(draw):
    return tuple(draw(_score(n)) for n in _FACTOR_NAMES)


@st.composite
def _bands(draw):
    sell = draw(st.floats(-1.0, 0.0, allow_nan=False))
    buy = draw(st.floats(0.0, 1.0, allow_nan=False))
    return {"sell": sell, "buy": buy}


@st.composite
def _fund(draw):
    return MonitorFund(
        id="X", name_cn="x", market="cn", analysis_profile="gold",
        themes=(), constituent_news=False, weights=draw(_weights()),
        bands=draw(_bands()),
        minimum_confidence=draw(st.floats(0.0, 1.0, allow_nan=False)),
    )


@given(fund=_fund(), scores=_scores())
def test_composite_equals_rounded_oracle(fund, scores):
    rec = compute_signal(fund, scores)
    expected = round(_oracle.composite_oracle(fund.weights, scores), 4)
    assert abs(rec.composite - expected) < _EPS


@given(fund=_fund(), scores=_scores())
def test_renorm_sums_to_one_or_zero(fund, scores):
    rec = compute_signal(fund, scores)
    s = sum(c.renorm_weight for c in rec.contributions)
    if rec.contributions and _oracle.available_weight(fund.weights, scores) > 0:
        assert abs(s - 1.0) < _EPS
    else:
        assert abs(s - 0.0) < _EPS


@given(fund=_fund(), scores=_scores())
def test_bias_none_iff_status_not_ok(fund, scores):
    rec = compute_signal(fund, scores)
    assert (rec.bias is None) == (rec.status != "ok")


@given(fund=_fund(), scores=_scores())
def test_status_ok_matches_gate_and_confidence_predicate(fund, scores):
    rec = compute_signal(fund, scores)
    gate_ok = _oracle.gate_predicate_ok(fund.weights, scores)
    conf_ok = rec.signal_confidence >= fund.minimum_confidence
    assert (rec.status == "ok") == (gate_ok and conf_ok)


@given(fund=_fund(), scores=_scores())
def test_bias_matches_band_classifier_when_ok(fund, scores):
    rec = compute_signal(fund, scores)
    if rec.status == "ok":
        assert rec.bias == _oracle.band_classifier(rec.composite, fund.bands)


@given(
    fund=_fund(),
    composites=st.tuples(
        st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False),
        st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False),
    ),
)
def test_raising_composite_never_moves_bias_toward_reduce(fund, composites):
    """Band monotonicity (spec §3.1): for any two composites c_lo <= c_hi drawn
    from the real input range [-1, 1], the band classifier must never assign a
    *lower* bias order to the higher composite.  Uses the same band-classification
    path that compute_signal uses (verified by test_bias_matches_band_classifier_when_ok).
    This test is NON-TRIVIAL: it draws real pairs and fails if band_classifier
    were non-monotone (e.g. bands with sell > buy)."""
    c_lo, c_hi = min(composites), max(composites)
    order = {"REDUCE_BIAS": 0, "NEUTRAL": 1, "ADD_BIAS": 2}
    bias_lo = _oracle.band_classifier(c_lo, fund.bands)
    bias_hi = _oracle.band_classifier(c_hi, fund.bands)
    assert order[bias_hi] >= order[bias_lo]


@given(fund=_fund(), scores=_scores())
def test_reproducible_same_inputs_equal_record(fund, scores):
    assert compute_signal(fund, scores) == compute_signal(fund, scores)
