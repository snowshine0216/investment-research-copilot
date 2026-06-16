"""PURE predictive-validity panel HTML (M3). No I/O, no JS, no remote refs.
Mirrors panel.py's validation_panel_html shape."""
from __future__ import annotations
from html import escape
from irc.monitor.eval.types import PredictiveMetricView, PredictivePanelModel


def _delta_cell(d: float | None) -> str:
    return "n/a" if d is None else f"{d:+.3f}"


def _ci_cell(lo: float | None, hi: float | None) -> str:
    """Render the CI interval, or 'CI pending' when no real CI exists yet (e.g. a
    thin/undefined Rank-IC) — never a faked [v, v] interval."""
    if lo is None or hi is None:
        return "CI pending"
    return f"[{lo:+.3f}, {hi:+.3f}]"


def _metric_row(m: PredictiveMetricView) -> str:
    return (
        f"<tr><td>{escape(m.name)}</td>"
        f"<td>{m.value:+.3f}</td>"
        f"<td>{escape(m.status)}</td>"
        f"<td>{_ci_cell(m.ci_low, m.ci_high)}</td>"
        f"<td>{_delta_cell(m.random_delta)}</td>"
        f"<td>{_delta_cell(m.momentum_delta)}</td>"
        f"<td>{_delta_cell(m.buy_hold_delta)}</td>"
        f"<td>{escape(m.state)}</td>"
        f"<td>{m.n_observations}</td></tr>"
    )


def predictive_validity_panel_html(*, model: PredictivePanelModel) -> str:
    head = '<section class="predictive-panel"><h2>Predictive validity</h2>'
    if not model.present:
        return head + ('<p class="muted">no backtest yet — run '
                       '<code>irc eval monitor_forward</code></p></section>')
    banner = ""
    if model.stale:
        banner = (f'<p class="muted">⚠ stale backtest ({escape(model.artifact_date or "")}) '
                  f'— rerun <code>irc eval monitor_forward</code></p>')
    review = ('<p class="review-flag">⚠ review: signal underperforming</p>'
              if model.review_flag else "")
    rows = "".join(_metric_row(m) for m in model.metrics)
    note = ('<p class="muted">retro = evidence-free sub-composite; forward = full raw '
            'signal — directionally analogous, not directly comparable.</p>')
    return (
        head + banner + review +
        '<table class="predictive"><tr><th>metric</th><th>value</th><th>status</th>'
        '<th>CI</th><th>Δrandom</th><th>Δmomentum</th><th>Δbuy_hold</th>'
        '<th>state</th><th>n</th></tr>' + rows + '</table>' + note + '</section>'
    )
