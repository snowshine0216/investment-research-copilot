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


def test_ci_pending_rendered_when_ci_is_none():
    """A row with no real CI (ci_low/ci_high None) must render 'CI pending' — never
    a faked interval and never the literal 'None' in the CI cell."""
    m = PredictiveMetricView(
        name="rank_ic", value=0.12, status="WARN", state="insufficient_data",
        ci_low=None, ci_high=None, random_delta=None,
        momentum_delta=None, buy_hold_delta=None, n_observations=3,
    )
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "CI pending" in html
    assert "None" not in html


def test_real_ci_still_rendered_as_interval():
    """A row WITH a real CI still renders the bracketed interval (regression guard)."""
    m = _metric("rank_ic", 0.30, "PASS")     # ci_low=0.20, ci_high=0.40
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-16",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "[+0.200, +0.400]" in html
    assert "CI pending" not in html


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


def test_engine_population_row_renders_ci_pending_and_na_deltas():
    """The engine_population row (None CIs, None deltas) renders 'engine_population',
    'CI pending', and 'n/a' for ALL THREE baseline (Δrandom/Δmomentum/Δbuy_hold)
    cells. Renderer is unchanged; this guards the new row's render shape."""
    m = PredictiveMetricView(
        name="engine_population", value=0.5, status="WARN",
        state="engine_transition", ci_low=None, ci_high=None,
        random_delta=None, momentum_delta=None, buy_hold_delta=None,
        n_observations=3,
    )
    model = PredictivePanelModel(present=True, stale=False, artifact_date="2026-06-20",
                                 metrics=(m,), review_flag=False)
    html = predictive_validity_panel_html(model=model)
    assert "engine_population" in html
    assert "engine_transition" in html
    assert "CI pending" in html
    assert html.count("n/a") >= 3        # all three Δ cells render n/a
