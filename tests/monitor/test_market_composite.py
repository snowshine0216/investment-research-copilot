from __future__ import annotations
import math
from irc.monitor.market_composite import MarketCompositeView, market_composite_view
from irc.monitor.types import FactorContribution, SignalRecord

_BANDS = {"buy": 0.40, "sell": -0.40}


def _sig(contribs, composite):
    return SignalRecord(fund_id="x", status="ok", bias=None, composite=composite,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=(), contributions=tuple(contribs),
                        divergence_codes=())


def _c(name, renorm_weight, value):
    return FactorContribution(name, renorm_weight, value, renorm_weight * value, 1.0, True, "")


def test_full_active_four_market_factors_renormalized():
    # market factors w'=.25 each summing to 1.0 already (no news present)
    contribs = [_c("trend", .25, .8), _c("valuation", .25, .4),
                _c("flow", .25, -.2), _c("heat", .25, .0)]
    sig = _sig(contribs, composite=round(sum(c.contribution for c in contribs), 4))
    v = market_composite_view(sig, bands=_BANDS)
    # only market factors → renorm is identity; market composite == C
    assert math.isclose(v.composite, sig.composite, abs_tol=1e-9)
    assert v.news_delta == 0.0
    assert v.eligible_market_factors == 4
    # .25*.8 + .25*.4 + .25*(-.2) + .25*.0 = 0.2 + 0.1 - 0.05 + 0 = 0.25 → NEUTRAL
    assert v.bias == "NEUTRAL"


def test_market_excludes_news_and_renormalizes():
    # market w' = trend .3, flow .2 (sum .5); news macro_tilt .5 value 1.0
    contribs = [_c("trend", .3, 1.0), _c("flow", .2, 0.0), _c("macro_tilt", .5, 1.0)]
    C = round(sum(c.contribution for c in contribs), 4)  # .3 + 0 + .5 = .8
    sig = _sig(contribs, C)
    v = market_composite_view(sig, bands=_BANDS)
    # market-only: renorm over (.3,.2) → (.6,.4); composite = .6*1.0 + .4*0.0 = .6
    assert math.isclose(v.composite, 0.6, abs_tol=1e-9)
    assert math.isclose(v.news_delta, C - 0.6, abs_tol=1e-9)  # .8 - .6 = .2
    assert v.eligible_market_factors == 2
    assert v.bias == "ADD_BIAS"  # .6 >= .40


def test_qdii_trend_and_heat_only():
    contribs = [_c("trend", .7, -.5), _c("heat", .3, .3)]
    C = round(sum(c.contribution for c in contribs), 4)
    sig = _sig(contribs, C)
    v = market_composite_view(sig, bands=_BANDS)
    assert math.isclose(v.composite, C, abs_tol=1e-9)  # no news → identity
    assert v.news_delta == 0.0
    assert v.eligible_market_factors == 2
    # .7*(-.5) + .3*.3 = -.35 + .09 = -.26 → NEUTRAL (not REDUCE: -.26 > -0.40)
    assert v.bias == "NEUTRAL"


def test_none_when_no_market_factor_present():
    contribs = [_c("macro_tilt", .6, 1.0), _c("constituent", .4, .5)]
    sig = _sig(contribs, round(sum(c.contribution for c in contribs), 4))
    assert market_composite_view(sig, bands=_BANDS) is None
