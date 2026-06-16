from __future__ import annotations
from irc.monitor.render_html import render_report
from irc.monitor.render_types import Provenance
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel


def test_render_report_default_omits_predictive_panel():
    html = render_report((), Provenance("1", "1", "1", ""), prior_signal=None, now="t")
    assert "Predictive validity" not in html        # back-compat: default None


def test_render_report_includes_predictive_panel_when_passed():
    model = PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(PredictiveMetricView(
            name="publishable_bias_directional", value=0.6, status="PASS", state="ok",
            ci_low=0.5, ci_high=0.7, random_delta=0.05, momentum_delta=0.02,
            buy_hold_delta=0.01, n_observations=9),),
        review_flag=False)
    html = render_report((), Provenance("1", "1", "1", ""), prior_signal=None, now="t",
                         predictive_panel=model)
    assert "Predictive validity" in html
    assert "publishable_bias_directional" in html
    assert "<script" not in html.lower()             # no JS
