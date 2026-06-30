from __future__ import annotations
from irc.monitor.render_heatmap import factor_heatmap_html
from irc.monitor.market_composite import MarketCompositeView
from irc.monitor.render_types import FundView
from irc.monitor.types import FactorContribution, FactorScore, NarrativeDoc, SignalRecord


def _view(fid, C, market_c, contribs, scores):
    rec = SignalRecord(fid, "ok", "ADD_BIAS", C, 1.0, 1.0, (), tuple(contribs), ())
    return FundView(fund_id=fid, name_cn=fid, latest_nav=1.0, as_of_date="d",
                    nav_series=(), signal=rec, narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=tuple(scores),
                    market_view=MarketCompositeView(market_c, "ADD_BIAS", C - market_c, 2))


def _views():
    c = [FactorContribution("trend", .5, .8, .4, 1.0, True, ""),
         FactorContribution("macro_tilt", .5, -.4, -.2, 1.0, True, "")]
    s = [FactorScore("trend", .8, True, "", 1.0), FactorScore("macro_tilt", -.4, True, "", 1.0),
         FactorScore("valuation", None, False, "valuation_no_index", 1.0)]
    return (_view("AAA", 0.2, 0.4, c, s),)


def test_heatmap_groups_market_then_news_then_composites():
    html = factor_heatmap_html(_views())
    # column order tokens appear left-to-right
    assert html.index("trend") < html.index("macro") < html.index("市场面")
    assert html.index("市场面") < html.index("完整")


def test_heatmap_uses_badge_palette_not_inverted():
    html = factor_heatmap_html(_views())
    assert "#1a7f37" in html  # add_bias green for positive
    assert "#cf222e" in html  # reduce_bias red for negative


def test_heatmap_na_cell_is_dash():
    html = factor_heatmap_html(_views())
    assert "—" in html  # valuation N/A


def test_heatmap_cell_title_is_annotation():
    html = factor_heatmap_html(_views())
    assert 'title="强上行"' in html


def test_heatmap_legend_present():
    html = factor_heatmap_html(_views())
    assert "正=偏多" in html and "负=偏空" in html


def test_heatmap_byte_stable():
    assert factor_heatmap_html(_views()) == factor_heatmap_html(_views())


def test_heatmap_no_script_no_remote():
    html = factor_heatmap_html(_views())
    assert "<script" not in html.lower() and "http" not in html
