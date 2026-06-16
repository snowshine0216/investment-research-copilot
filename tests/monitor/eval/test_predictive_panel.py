# tests/monitor/eval/test_predictive_panel.py
from __future__ import annotations
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html


def _metric(name, value, status, state="ok"):
    return PredictiveMetricView(
        name=name, value=value, status=status, state=state,
        ci_low=value - 0.1, ci_high=value + 0.1,
        random_delta=0.05, momentum_delta=0.02, buy_hold_delta=0.01,
        n_observations=12,
    )


def test_no_entry_renders_no_backtest():
    model = PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                 metrics=(), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "no backtest yet" in html
    assert "<script" not in html.lower()


def test_stale_renders_caveat_with_date():
    model = PredictivePanelModel(present=True, stale=True, artifact_date="2026-05-01",
                                 metrics=(_metric("publishable_bias_directional", 0.6, "PASS"),),
                                 review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "2026-05-01" in html and "rerun" in html.lower()


def test_normal_renders_metric_rows_and_no_js():
    model = PredictivePanelModel(
        present=True, stale=False, artifact_date="2026-06-16",
        metrics=(
            _metric("publishable_bias_directional", 0.6, "PASS"),
            _metric("raw_composite_directional", 0.55, "WARN"),
            _metric("rank_ic", 0.12, "WARN", state="insufficient_data"),
        ),
        review_flag=False,
    )
    html = predictive_validity_panel_html(model=model)
    assert "publishable_bias_directional" in html
    assert "<script" not in html.lower()


def test_review_flag_renders_warning():
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(_metric("publishable_bias_directional", 0.4, "WARN"),),
                                 review_flag=True)
    html = predictive_validity_panel_html(model=model)
    assert "review" in html.lower() and "underperforming" in html.lower()


def test_baseline_na_state_renders_na():
    m = PredictiveMetricView(
        name="publishable_bias_directional", value=0.6, status="PASS", state="ok",
        ci_low=0.5, ci_high=0.7, random_delta=0.05,
        momentum_delta=None, buy_hold_delta=0.01, n_observations=12,
    )
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "n/a" in html.lower()
