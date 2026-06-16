from __future__ import annotations
import json
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html


def _model(review=False):
    return PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(PredictiveMetricView(
            name="publishable_bias_directional", value=0.6, status="WARN", state="ok",
            ci_low=0.5, ci_high=0.7, random_delta=-0.05, momentum_delta=None,
            buy_hold_delta=0.01, n_observations=9),),
        review_flag=review)


def test_panel_is_byte_stable_across_reruns():
    a = predictive_validity_panel_html(model=_model())
    b = predictive_validity_panel_html(model=_model())
    assert a == b


def test_panel_has_no_js():
    html = predictive_validity_panel_html(model=_model(review=True))
    assert "<script" not in html.lower() and "onclick" not in html.lower()


def test_fail_report_does_not_carry_published_state():
    # A monitor_forward StageReport never contains any published_state field —
    # it is informational only. Guard the contract at the schema level.
    from evals._shared.report_schema import StageReport, MetricReport
    rep = StageReport("monitor_forward", "t", [], [MetricReport("x", 0.0, "FAIL")], "FAIL")
    from evals._shared.report_schema import report_to_dict
    d = report_to_dict(rep)
    assert "published_state" not in json.dumps(d)
