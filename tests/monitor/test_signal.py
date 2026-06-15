import pytest
from irc.monitor.types import MonitorFund, FactorScore
from irc.monitor.signal import compute_signal


def _fund(weights, bands=None, min_conf=0.50, profile="gold"):
    return MonitorFund(
        id="X", name_cn="x", market="cn_off_exchange", analysis_profile=profile,
        themes=(), constituent_news=False, weights=weights,
        bands=bands or {"buy": 0.40, "sell": -0.40}, minimum_confidence=min_conf,
    )


def _fs(name, value, eligible=True, conf=1.0, reason=""):
    return FactorScore(name=name, value=value, eligible=eligible, reason=reason, confidence=conf)


def test_gold_worked_example_passes_off_trend_and_macro_even_with_heat_na():
    # gold vector: trend .45, macro_tilt .35, heat .20. heat N/A.
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (
        _fs("trend", 0.6), _fs("macro_tilt", 0.5),
        _fs("heat", None, eligible=False, reason="heat_no_data"),
    )
    rec = compute_signal(fund, scores)
    assert rec.status == "ok"
    # available_weight = .45+.35 = .80 ≥ .60; families = price-momentum, news = 2 ≥ 2.
    assert rec.available_weight == pytest.approx(0.80)
    # C = (.45*0.6 + .35*0.5)/.80 = (.27+.175)/.80 = .55625 ≥ buy(.40) → ADD_BIAS
    assert rec.bias == "ADD_BIAS"
    assert rec.composite == pytest.approx(0.5563, abs=1e-4)


def test_insufficient_when_below_available_weight():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (
        _fs("trend", 0.6),
        _fs("macro_tilt", None, eligible=False, reason="macro_insufficient_families"),
        _fs("heat", None, eligible=False, reason="heat_no_data"),
    )
    rec = compute_signal(fund, scores)   # only trend present = .45 < .60
    assert rec.status == "insufficient_evidence" and rec.bias is None


def test_insufficient_when_trend_missing():
    fund = _fund({"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                  "macro_tilt": 0.20, "constituent": 0.15}, profile="active_cn_equity")
    scores = (
        _fs("trend", None, eligible=False, reason="trend_insufficient_history"),
        _fs("valuation", 0.5), _fs("heat", -0.5),
        _fs("macro_tilt", 0.3), _fs("constituent", 0.2),
    )
    rec = compute_signal(fund, scores)
    assert rec.status == "insufficient_evidence" and rec.bias is None


def test_low_confidence_yields_no_call():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20}, min_conf=0.95)
    scores = (
        _fs("trend", 0.6, conf=1.0), _fs("macro_tilt", 0.5, conf=0.30),
        _fs("heat", None, eligible=False, reason="heat_no_data"),
    )
    rec = compute_signal(fund, scores)
    # signal_confidence = w'·conf with low macro conf → below 0.95
    assert rec.status == "low_confidence" and rec.bias is None


def test_no_call_is_not_neutral():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (_fs("trend", 0.0),)   # only trend, available .45 < .60
    rec = compute_signal(fund, scores)
    assert rec.status != "ok"
    assert rec.bias is None          # NOT NEUTRAL — structural distinction
    assert rec.bias != "NEUTRAL"


def test_band_neutral_center():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (_fs("trend", 0.10), _fs("macro_tilt", 0.10),
              _fs("heat", None, eligible=False, reason="heat_no_data"))
    rec = compute_signal(fund, scores)
    assert rec.status == "ok" and rec.bias == "NEUTRAL"   # |C| < 0.40


def test_reduce_bias_below_sell_band():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (_fs("trend", -0.7), _fs("macro_tilt", -0.6),
              _fs("heat", None, eligible=False, reason="heat_no_data"))
    rec = compute_signal(fund, scores)
    assert rec.bias == "REDUCE_BIAS"


def test_divergence_trend_valuation_conflict():
    fund = _fund({"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                  "macro_tilt": 0.20, "constituent": 0.15}, profile="active_cn_equity")
    scores = (_fs("trend", 0.6), _fs("valuation", -0.5), _fs("heat", -0.5),
              _fs("macro_tilt", 0.1), _fs("constituent", 0.1))
    rec = compute_signal(fund, scores)
    assert "trend_valuation_conflict" in rec.divergence_codes


def test_reproducible_same_inputs_same_record():
    fund = _fund({"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20})
    scores = (_fs("trend", 0.6), _fs("macro_tilt", 0.5),
              _fs("heat", None, eligible=False, reason="heat_no_data"))
    assert compute_signal(fund, scores) == compute_signal(fund, scores)
