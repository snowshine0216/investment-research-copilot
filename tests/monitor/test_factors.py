from irc.monitor.factors import build_factor_scores, FactorInputs
from irc.monitor.news_factor import ImpactRow


def _nav(n):
    return tuple((f"d{i}", 1.0 + 0.001 * i) for i in range(n))


def _inputs(**kw):
    base = dict(
        acc_nav=_nav(300), minimum_observations=251,
        valuation_state=None, valuation_cached=False,
        restricted=None, aum_delta_pct=None,
        macro_rows=(), constituent_rows=(),
    )
    base.update(kw)
    return FactorInputs(**base)


def _by_name(scores):
    return {s.name: s for s in scores}


def test_gold_valuation_and_constituent_are_na_by_profile():
    scores = build_factor_scores("gold", _inputs())
    bn = _by_name(scores)
    assert bn["valuation"].eligible is False
    assert bn["valuation"].reason == "profile_ineligible"
    assert bn["constituent"].eligible is False


def test_trend_na_when_too_few_observations():
    scores = build_factor_scores("gold", _inputs(acc_nav=_nav(100)))
    assert _by_name(scores)["trend"].reason == "trend_insufficient_history"
    assert _by_name(scores)["trend"].value is None


def test_trend_present_with_enough_history():
    t = _by_name(build_factor_scores("gold", _inputs()))["trend"]
    assert t.eligible and t.value is not None and t.confidence == 1.0


def test_macro_tilt_requires_two_themes_with_citations():
    one = (ImpactRow("us_monetary", 1.0, 0.5, 0.9),)
    s1 = _by_name(build_factor_scores("gold", _inputs(macro_rows=one)))["macro_tilt"]
    assert s1.eligible is False and s1.reason == "macro_insufficient_families"
    two = one + (ImpactRow("geopolitics", 1.0, -0.2, 0.7),)
    s2 = _by_name(build_factor_scores("gold", _inputs(macro_rows=two)))["macro_tilt"]
    assert s2.eligible and s2.value is not None


def test_valuation_eligible_profile_but_no_anchor_is_na():
    s = _by_name(build_factor_scores(
        "qdii_china_us_internet",
        _inputs(valuation_state=None, valuation_cached=False),
    ))["valuation"]
    assert s.eligible is False and s.reason == "valuation_no_anchor"


def test_valuation_present_when_cached_state():
    s = _by_name(build_factor_scores(
        "active_cn_equity",
        _inputs(valuation_state="cheap", valuation_cached=True),
    ))["valuation"]
    assert s.eligible and s.value == 1.0


def test_heat_na_when_no_data():
    s = _by_name(build_factor_scores("gold", _inputs()))["heat"]
    assert s.eligible is False and s.reason == "heat_no_data"
