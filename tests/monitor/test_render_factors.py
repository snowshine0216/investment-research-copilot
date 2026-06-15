from irc.monitor.types import FactorScore, FactorContribution, SignalRecord
from irc.monitor.render_factors import (
    CANONICAL_FACTOR_ORDER, divergence_caveat, factor_table_html, returns_table_html,
)


def test_canonical_order_is_locked():
    assert CANONICAL_FACTOR_ORDER == ("trend", "valuation", "heat", "macro_tilt", "constituent")


def test_divergence_map_strings_are_exact():
    assert divergence_caveat("trend_valuation_conflict") == "趋势与估值背离：价格动能与估值方向相反"
    assert divergence_caveat("trend_macro_conflict") == "趋势与宏观背离：价格动能与宏观信号方向相反"
    assert divergence_caveat("low_factor_agreement") == "因子分歧较大：各因子方向/强度不一致"


def test_unknown_divergence_code_is_escaped_passthrough():
    assert divergence_caveat("<x>") == "&lt;x&gt;"


def _rec(contribs, divergence=()):
    return SignalRecord(
        fund_id="x", status="ok", bias="NEUTRAL", composite=0.0, signal_confidence=1.0,
        available_weight=0.8, present_families=("price-momentum",),
        contributions=contribs, divergence_codes=divergence,
    )


def test_present_factor_renders_numeric_row():
    c = FactorContribution("trend", 0.5625, 0.6, 0.3375, 1.0, True, "")
    scores = (FactorScore("trend", 0.6, True, "", 1.0),)
    html = factor_table_html(_rec((c,)), scores, {"trend": "fresh"})
    assert "trend" in html
    assert "0.6000" in html or "0.6" in html  # value sᵢ formatted
    assert "fresh" in html


def test_na_factor_renders_dim_row_with_structured_reason():
    scores = (
        FactorScore("trend", 0.6, True, "", 1.0),
        FactorScore("heat", None, False, "heat_no_data", 1.0),
    )
    c = FactorContribution("trend", 1.0, 0.6, 0.6, 1.0, True, "")
    html = factor_table_html(_rec((c,)), scores, {"trend": "fresh"})
    assert "factor-na" in html           # dim class present
    assert "heat_no_data" in html        # structured reason, not string-split
    assert html.count("—") >= 3          # dashed numeric cells on the N/A row


def test_factor_rows_render_in_canonical_order():
    scores = (
        FactorScore("constituent", 0.2, True, "", 1.0),
        FactorScore("trend", 0.6, True, "", 1.0),
    )
    cs = (
        FactorContribution("constituent", 0.4, 0.2, 0.08, 1.0, True, ""),
        FactorContribution("trend", 0.6, 0.6, 0.36, 1.0, True, ""),
    )
    html = factor_table_html(_rec(cs), scores, {"trend": "fresh", "constituent": "fresh"})
    assert html.index(">trend<") < html.index(">constituent<")


def test_footer_row_has_composite_confidence_weight_families():
    c = FactorContribution("trend", 1.0, 0.6, 0.6, 1.0, True, "")
    html = factor_table_html(_rec((c,)), (FactorScore("trend", 0.6, True, "", 1.0),), {"trend": "fresh"})
    assert "综合 C" in html and "0.0000" in html  # composite
    assert "available wt" in html and "price-momentum" in html


def test_returns_table_renders_na_for_none_windows():
    html = returns_table_html({5: 0.0123, 20: None, 60: None, 120: None, 250: None})
    assert "+1.23%" in html
    assert "—" in html  # None windows show dash, not crash
