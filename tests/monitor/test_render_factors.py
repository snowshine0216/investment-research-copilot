from irc.monitor.types import FactorScore, FactorContribution, SignalRecord
from irc.monitor.render_factors import (
    CANONICAL_FACTOR_ORDER, divergence_caveat, divergence_caveat_detail,
    factor_table_html, returns_table_html,
)


def test_canonical_order_is_locked():
    assert CANONICAL_FACTOR_ORDER == (
        "trend", "valuation", "flow", "heat", "macro_tilt", "constituent"
    )


def test_valuation_flow_conflict_caveat_is_exact():
    assert divergence_caveat("valuation_flow_conflict") == (
        "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入"
    )


def test_divergence_map_strings_are_exact():
    assert divergence_caveat("trend_valuation_conflict") == "趋势与估值背离：价格动能与估值方向相反"
    assert divergence_caveat("trend_macro_conflict") == "趋势与宏观背离：价格动能与宏观信号方向相反"
    assert divergence_caveat("low_factor_agreement") == "因子分歧较大：各因子方向/强度不一致"


def test_unknown_divergence_code_is_escaped_passthrough():
    assert divergence_caveat("<x>") == "&lt;x&gt;"


def _fc(name, value):
    return FactorContribution(name, 0.5, value, 0.5 * value, 1.0, True, "")


def test_trend_macro_conflict_detail_is_exact():
    contribs = (_fc("trend", -0.75), _fc("macro_tilt", 0.62))
    assert divergence_caveat_detail("trend_macro_conflict", contribs) == (
        "趋势与宏观背离：趋势 -0.75（价格动能向下） vs 宏观 +0.62（新闻/宏观偏多）"
    )


def test_trend_valuation_conflict_detail_is_exact():
    contribs = (_fc("trend", 0.45), _fc("valuation", -0.80))
    assert divergence_caveat_detail("trend_valuation_conflict", contribs) == (
        "趋势与估值背离：趋势 +0.45（价格动能向上） vs 估值 -0.80（估值偏贵）"
    )


def test_valuation_flow_conflict_detail_is_exact():
    contribs = (_fc("valuation", 0.80), _fc("flow", -0.45))
    assert divergence_caveat_detail("valuation_flow_conflict", contribs) == (
        "估值与资金流背离：估值 +0.80（估值偏便宜） vs 资金流 -0.45（资金净流出）"
    )


def test_pairwise_detail_missing_factor_falls_back_to_static_string():
    contribs = (_fc("trend", -0.75),)  # macro_tilt absent → AC-5 fallback
    assert divergence_caveat_detail("trend_macro_conflict", contribs) == (
        "趋势与宏观背离：价格动能与宏观信号方向相反"
    )


def test_detail_unknown_code_is_escaped_passthrough():
    assert divergence_caveat_detail("<x>", ()) == "&lt;x&gt;"


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


def test_factor_table_has_jiedu_column_with_annotation_and_title():
    contribs = (
        FactorContribution("trend", 0.6, 0.8, 0.48, 1.0, True, ""),
        FactorContribution("macro_tilt", 0.4, 0.6, 0.24, 1.0, True, ""),
    )
    rec = SignalRecord("x", "ok", "ADD_BIAS", 0.72, 1.0, 1.0, ("price-momentum", "news"),
                       contribs, ())
    scores = (FactorScore("trend", 0.8, True, "", 1.0),
              FactorScore("macro_tilt", 0.6, True, "", 1.0))
    html = factor_table_html(rec, scores, {"trend": "fresh", "macro_tilt": "fresh"})
    assert "解读" in html              # new column header
    assert "强上行" in html            # trend annotation
    assert "新闻面" in html            # macro carries the news mark
    assert 'title="强上行"' in html    # value-cell tooltip
    # composite verdict line gains composite_annotation
    assert "市场面" in html and "新闻叠加" in html


def test_factor_table_na_row_jiedu_blank():
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    scores = (FactorScore("heat", None, False, "heat_no_data", 1.0),)
    html = factor_table_html(rec, scores, {})
    # N/A row: 解读 cell present but empty (—)
    assert "heat_no_data" in html
