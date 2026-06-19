from irc.monitor.render_types import FundView


def test_fundview_holding_metrics_defaults_empty():
    # trailing, defaulted → existing construction sites stay green.
    import inspect
    sig = inspect.signature(FundView)
    assert sig.parameters["holding_metrics"].default == ()
