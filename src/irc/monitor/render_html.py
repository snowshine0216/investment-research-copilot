from __future__ import annotations
from html import escape
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.render_cards import (
    narrative_sections_html, risk_block_html, verdict_block_html,
)
from irc.monitor.render_factors import factor_table_html, returns_table_html
from irc.monitor.svg_chart import EventMarker, render_nav_chart
from irc.monitor.eval.gate import published_state
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html
from irc.monitor.eval.types import GateDecision, ValidationPanelRow, PredictivePanelModel

_NO_CALL = "NO_CALL"
_EVAL_GATED = "EVAL_GATED"
_CHIP = {"validated": ("val-validated", "✓ validated"),
         "caveated": ("val-caveated", "⚠ caveated")}

_CSS = (
    "<style>"
    "body{font-family:sans-serif}"
    ".badge{padding:2px 6px;border-radius:4px}"
    ".no-call{background:#6e7781;color:#fff}"
    ".add_bias{background:#1a7f37;color:#fff}"
    ".neutral{background:#6e7781;color:#fff}"
    ".reduce_bias{background:#cf222e;color:#fff}"
    ".navchart{width:100%;max-width:680px;height:auto;display:block;"
    "margin:8px 0;background:#fff;border:1px solid #d0d7de;border-radius:6px}"
    ".navchart .hit:hover{fill:#0969da;fill-opacity:.08}"
    ".verdict{margin:8px 0;padding:8px;border-left:3px solid #0969da;background:#f6f8fa}"
    ".verdict-clause{font-weight:600;margin:0 0 4px}"
    ".verdict blockquote{margin:4px 0;padding-left:8px;border-left:2px solid #d0d7de;color:#57606a}"
    ".factors{border-collapse:collapse;width:100%;max-width:680px;margin:8px 0;font-size:13px}"
    ".factors th,.factors td{border:1px solid #d0d7de;padding:3px 6px;text-align:right}"
    ".factors th:first-child,.factors td:first-child{text-align:left}"
    ".factor-na{color:#8c959f;background:#f6f8fa}"
    ".factor-foot td{text-align:left;background:#f6f8fa;font-size:12px}"
    ".returns{border-collapse:collapse;margin:8px 0;font-size:13px}"
    ".returns td{border:1px solid #d0d7de;padding:3px 8px}"
    ".risk{margin:8px 0;padding:8px;border-left:3px solid #cf222e;background:#fff8f6}"
    ".risk h3{margin:0 0 4px;color:#cf222e;font-size:14px}"
    ".price-action h3{font-size:14px;margin:8px 0 4px}"
    ".muted{color:#8c959f}"
    ".eval-gated{background:#57606a;color:#fff}"
    ".val-chip{font-size:11px;margin-left:6px;padding:1px 4px;border-radius:3px}"
    ".val-validated{color:#1a7f37}"
    ".val-caveated{color:#bf8700}"
    ".validation-panel{margin:16px 0;padding:8px;border:1px solid #d0d7de;border-radius:6px}"
    ".validation{border-collapse:collapse;font-size:13px;margin:4px 0}"
    ".validation th,.validation td{border:1px solid #d0d7de;padding:3px 6px}"
    ".predictive-panel{margin:16px 0;padding:8px;border:1px solid #d0d7de;border-radius:6px}"
    ".predictive{border-collapse:collapse;font-size:13px;margin:4px 0}"
    ".predictive th,.predictive td{border:1px solid #d0d7de;padding:3px 6px}"
    ".review-flag{color:#cf222e;font-weight:600}"
    ".explainer{margin:8px 0;padding:8px 10px;border:1px solid #d0d7de;"
    "border-left:4px solid #0969da;border-radius:6px;background:#ddf4ff;"
    "font-size:13px;line-height:1.55}"
    ".explainer .legend{display:block;margin-top:4px;color:#57606a}"
    ".explainer .legend-en{display:block;margin-top:2px;color:#8c959f;font-size:12px}"
    "</style>"
)

# Static, deterministic explainer: a directional bias is a research lean, never an
# executable portfolio action (CONTEXT.md). Decodes the bias badges + validation chips.
_EXPLAINER = (
    '<aside class="explainer">'
    '<b>方向性倾向 = 研究参考信号，非买卖指令。</b>'
    '本监控不读取持仓 / 权重 / 估值，<b>不构成投资建议</b>。'
    '<span class="legend">'
    'ADD_BIAS=偏多 · NEUTRAL=中性 · REDUCE_BIAS=偏空　|　'
    '✓ validated 全项校验通过 · ⚠ caveated 有保留（存在 WARN/UNKNOWN，无新 FAIL）'
    '</span>'
    '<span class="legend-en">Directional bias is a research lean, '
    'not a buy/sell order and not investment advice.</span>'
    '</aside>'
)


def _badge(view: FundView, gate: GateDecision | None) -> str:
    if gate is None:
        if view.signal.status != "ok":
            return f'<span class="badge no-call">{_NO_CALL}</span>'
        return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'
    state = published_state(view.signal, gate)
    if state == _NO_CALL:
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    if state == _EVAL_GATED:
        return '<span class="badge eval-gated">EVAL-GATED 🛡</span>'
    chip = ""
    cls_label = _CHIP.get(gate.badge)
    if cls_label:
        cls, label = cls_label
        chip = f'<span class="val-chip {cls}">{label}</span>'
    return f'<span class="badge {state.lower()}">{escape(state)}</span>{chip}'


def _markers(view: FundView) -> tuple[EventMarker, ...]:
    return tuple(
        EventMarker(
            date=ev.date,
            sign=0,
            title=f"{escape(ev.title)} · {escape(ev.source)} · {ev.date}",
        )
        for ev in view.evidence_pool
    )


def _summary_row(view: FundView, prior: dict | None, gate: GateDecision | None) -> str:
    changed = ""
    if prior is not None:
        prev = (prior.get(view.fund_id) or {}).get("bias")
        if prev != view.signal.bias:
            changed = '<span class="changed-since-yesterday" style="color:#bf8700">●</span>'
    return (
        f"<tr><td>{escape(view.name_cn)}</td>"
        f"<td>{view.latest_nav:.4f} @ {view.as_of_date}</td>"
        f"<td>{_badge(view, gate)}</td>"
        f"<td>C={view.signal.composite:+.4f}</td>"
        f"<td>{changed}</td></tr>"
    )


def _card(view: FundView, gate: GateDecision | None) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{verdict_block_html(view.signal, view.narrative)}"
        f"{chart}"
        f"{returns_table_html(view.return_table)}"
        f"{factor_table_html(view.signal, view.factor_scores, view.factor_freshness)}"
        f"{narrative_sections_html(view.narrative)}"
        f"{risk_block_html(view.signal, view.narrative)}"
        "</section>"
    )


def _appendix(views: tuple[FundView, ...]) -> str:
    items = []
    seen: set[str] = set()
    for v in views:
        for ev in v.evidence_pool:
            if ev.citation_id in seen:
                continue
            seen.add(ev.citation_id)
            items.append(
                f'<li id="ev-{ev.citation_id}">{escape(ev.title)} — '
                f'{escape(ev.source)} ({ev.date}) '
                f'<code>[ref:{ev.citation_id}]</code></li>'
            )
    return (
        "<details><summary>证据 / Evidence</summary><ul>"
        + "".join(items)
        + "</ul></details>"
    )


def _badge_counts(views: tuple[FundView, ...], gates: dict[str, GateDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in views:
        g = gates.get(v.fund_id)
        if g is not None:
            counts[g.badge] = counts.get(g.badge, 0) + 1
    return counts


def _panel(
    views: tuple[FundView, ...], gates: dict[str, GateDecision] | None,
    panel_rows: tuple[ValidationPanelRow, ...],
) -> str:
    if not gates or not panel_rows:
        return ""
    return validation_panel_html(rows=panel_rows, badge_counts=_badge_counts(views, gates))


def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    gates: dict[str, GateDecision] | None = None,
    panel_rows: tuple[ValidationPanelRow, ...] = (),
    predictive_panel: PredictivePanelModel | None = None,
) -> str:
    """PURE: self-contained HTML. No I/O, no JS, no remote refs."""
    header = (
        f'<header>as_of {now} · engine {provenance.engine_version} · '
        f'prompt {provenance.prompt_version} · schema {provenance.schema_version} · '
        f'{escape(provenance.spend_summary)}</header>'
    )
    g = gates or {}
    summary = (
        "<table class='summary'>"
        + "".join(_summary_row(v, prior_signal, g.get(v.fund_id)) for v in views)
        + "</table>"
    )
    cards = "".join(_card(v, g.get(v.fund_id)) for v in views)
    panel = _panel(views, gates, panel_rows)
    predictive = (
        predictive_validity_panel_html(model=predictive_panel)
        if predictive_panel is not None else ""
    )
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor</title>" + _CSS + "</head><body>"
        + header + _EXPLAINER + summary + cards + panel + predictive
        + _appendix(views) + "</body></html>"
    )
