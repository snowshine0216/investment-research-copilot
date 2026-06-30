from irc.monitor.render_types import FundView
from irc.monitor.market_composite import MarketCompositeView


def test_fundview_holding_metrics_defaults_empty():
    # trailing, defaulted → existing construction sites stay green.
    import inspect
    sig = inspect.signature(FundView)
    assert sig.parameters["holding_metrics"].default == ()


def test_fundview_market_view_defaults_none():
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc, SignalRecord
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    v = FundView(fund_id="x", name_cn="x", latest_nav=1.0, as_of_date="d",
                 nav_series=(), signal=rec, narrative=NarrativeDoc("x", (), (), (), "ok"),
                 evidence_pool=(), return_table={}, factor_freshness={},
                 missing_factor_reasons=())
    assert v.market_view is None
    assert v.purchase_tag is None
    mv = MarketCompositeView(0.3, "NEUTRAL", 0.1, 2)
    v2 = dataclasses_replace(v, market_view=mv, purchase_tag="限购 ¥100/日")
    assert v2.market_view.composite == 0.3
    assert v2.purchase_tag == "限购 ¥100/日"


def dataclasses_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)
