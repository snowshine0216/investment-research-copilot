"""Structural invariants for Monitor Report v2 (market-composite anchor + news overlay).
All five tests are PURE — no I/O, no network."""
from __future__ import annotations
from irc.monitor.render_html import render_report
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.types import SignalRecord, FactorContribution, NarrativeDoc
from irc.monitor.market_composite import MarketCompositeView

_NOW = "2026-06-30T09:00:00+08:00"


def _signal(fund_id="519069"):
    contribs = (
        FactorContribution("trend", .5, .8, .40, 1.0, True, ""),
        FactorContribution("flow", .2, -.5, -.10, 1.0, True, ""),
        FactorContribution("macro_tilt", .3, 1.0, .30, 1.0, True, ""),
    )
    return SignalRecord(fund_id, "ok", "ADD_BIAS", 0.7, 1.0, 1.0,
                        ("price-momentum", "news"), contribs, ())


def _view(fund_id="519069", *, with_market_view=True, purchase_tag=None):
    mv = MarketCompositeView(0.3, "NEUTRAL", 0.4, 2) if with_market_view else None
    return FundView(
        fund_id=fund_id, name_cn="测试", latest_nav=2.0, as_of_date="2026-06-30",
        nav_series=(("2026-06-30", 2.0),),
        signal=_signal(fund_id),
        narrative=NarrativeDoc(fund_id, (), (), (), "ok"),
        evidence_pool=(), return_table={}, factor_freshness={}, missing_factor_reasons=(),
        market_view=mv, purchase_tag=purchase_tag,
    )


def _prov():
    return Provenance("3", "1", "1", "")


def _report(*views, **kw):
    return render_report(views, _prov(), prior_signal=None, now=_NOW, **kw)


# 1. No <script> tags (pure HTML; no JS injection)
def test_no_script_tags():
    html = _report(_view())
    assert "<script" not in html.lower()


# 2. No https:// remote refs (SVG xmlns http:// OK; no external assets)
def test_no_https_remote_refs():
    html = _report(_view())
    assert "https://" not in html


# 3. 基金概況 forbidden (production fetch guard)
def test_no_forbidden_kpzk_string():
    html = _report(_view())
    assert "基金概況" not in html


# 4. market_composite_view is None → no decision-line div rendered but page still valid
def test_no_market_view_no_decision_line():
    html = _report(_view(with_market_view=False))
    assert '<div class="decision-line">' not in html
    # still a valid HTML document
    assert "<!doctype html>" in html.lower()


# 5. purchase_tag surfaced when present
def test_purchase_tag_surfaced_in_html():
    html = _report(_view(purchase_tag="限购"))
    assert "限购" in html
