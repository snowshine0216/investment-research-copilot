"""PURE per-stock drill-down rendering for `irc monitor` (ADR 0019). No I/O.

Renders the top-5 holdings board (PB/PE + 5d/20d 净占比 + flow score + dual-track
industry columns) and the flow/valuation roll-up reconciliation lines.
ADR 0015 lean line: 估值/资金流/偏多/偏空 only — NO 买入/卖出, no target weights,
no per-instrument action.

Slice 3 additions: industry columns (行业/行业PE/r/行业分), value-trap badge,
valuation_rollup_html with industry-coverage note.
"""
from __future__ import annotations
from html import escape

from irc.monitor.holding_metrics import FlowAggregate, HoldingMetric, ValuationAggregate
from irc.monitor.types import SignalRecord

_INDUSTRY_COVERAGE_NOTE_FLOOR = 0.50


def _cell_num(v: float | None, fmt: str = "{:.2f}") -> str:
    return "—" if v is None else escape(fmt.format(v))


def _cell_state(state: str | None, reason: str | None) -> str:
    if state is not None:
        return escape(state)
    return f"— <span class='na-reason'>{escape(reason)}</span>" if reason else "—"


def _flow_cell(score: float | None, reason: str | None) -> str:
    if score is not None:
        return f"{score:+.1f}"
    return f"— <span class='na-reason'>{escape(reason)}</span>" if reason else "—"


def _trap_badge(m: HoldingMetric) -> str:
    if not m.false_cheap:
        return ""
    return " <span class='trap-badge'>价值陷阱 便宜(自身)/偏贵(行业)→中性</span>"


def _row(i: int, m: HoldingMetric) -> str:
    return (
        f"<tr><td>{i}</td><td>{escape(m.symbol)}</td><td>{escape(m.name)}</td>"
        f"<td>{m.weight_pct:.2f}</td>"
        f"<td>{_cell_num(m.pb)}</td><td>{_cell_num(m.pe)}</td>"
        f"<td>{_cell_num(m.pe_percentile, '{:.0%}')}</td>"
        f"<td>{_cell_state(m.valuation_state, m.valuation_reason)}</td>"
        f"<td>{escape(m.industry) if m.industry else '—'}</td>"
        f"<td>{_cell_num(m.industry_pe)}</td>"
        f"<td>{_cell_num(m.industry_richness)}</td>"
        f"<td>{_cell_num(m.industry_score, '{:+.1f}')}{_trap_badge(m)}</td>"
        f"<td>{_cell_num(m.flow_pct_5d)}</td><td>{_cell_num(m.flow_pct_20d)}</td>"
        f"<td>{_flow_cell(m.flow_score, m.flow_reason)}</td></tr>"
    )


def holdings_board_html(metrics: tuple[HoldingMetric, ...]) -> str:
    """PURE: top-holdings board, rows sorted by weight desc, N/A cells dashed."""
    head = (
        "<tr><th>#</th><th>代码</th><th>名称</th><th>权重%</th><th>PB</th><th>PE</th>"
        "<th>PE分位</th><th>估值</th><th>行业</th><th>行业PE</th><th>r</th><th>行业分</th>"
        "<th>5d净占比</th><th>20d净占比</th><th>资金流分</th></tr>"
    )
    ordered = sorted(metrics, key=lambda m: m.weight_pct, reverse=True)
    rows = "".join(_row(i, m) for i, m in enumerate(ordered, start=1))
    return f"<table class='holdings-board'>{head}{rows}</table>"


def _aum_share(metrics: tuple[HoldingMetric, ...]) -> float:
    return sum(m.weight_pct for m in metrics)


def flow_rollup_html(
    metrics: tuple[HoldingMetric, ...], agg: FlowAggregate, signal: SignalRecord,
) -> str:
    """PURE: the reconciliation line — flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ), covered ratio,
    and top-5 representativeness (% of fund AUM, ALWAYS shown). Lean language only."""
    aum = _aum_share(metrics)
    if agg.value is None:
        body = (
            f"资金流因子 = N/A（{escape(agg.reason or 'flow_no_data')}）· "
            f"前五大 = {aum:.0f}% of 基金资产"
        )
    else:
        body = (
            f"资金流因子 = Σ(wᵢ·sᵢ)/Σ(wᵢ) = {agg.value:+.4f} "
            f"（覆盖 {agg.covered_weight_ratio:.0%} of 前五大；"
            f"前五大 = {aum:.0f}% of 基金资产）· "
            f"综合 C = {signal.composite:+.4f} → {escape(signal.bias or 'NEUTRAL')}"
        )
    return f"<div class='flow-rollup'>{body}</div>"


def _industry_coverage_ratio(metrics: tuple[HoldingMetric, ...]) -> float | None:
    """Fraction of COVERED-valuation weight whose industry leg resolved."""
    covered = [m for m in metrics if m.val_score is not None]
    cw = sum(m.weight_pct for m in covered)
    if cw <= 0.0:
        return None
    with_industry = sum(m.weight_pct for m in covered if m.industry_score is not None)
    return with_industry / cw


def valuation_rollup_html(
    metrics: tuple[HoldingMetric, ...], agg: ValuationAggregate,
) -> str:
    """PURE: dual-track reconciliation line. Lean only."""
    ind_cov = _industry_coverage_ratio(metrics)
    clamped = [m for m in metrics if m.false_cheap]
    if agg.value is None:
        body = f"估值因子 = N/A（{escape(agg.reason or 'valuation_no_data')}）"
    else:
        ind_txt = f"{ind_cov:.0%}" if ind_cov is not None else "—"
        body = (
            f"估值因子 = Σ(wᵢ·vᵢ)/Σ(wᵢ) = {agg.value:+.4f} "
            f"（NAV覆盖 {agg.covered_weight_ratio:.0%}；行业覆盖 {ind_txt}）"
        )
    if clamped:
        body += f"·已剔除价值陷阱 {len(clamped)} 只"
    if ind_cov is not None and ind_cov < _INDUSTRY_COVERAGE_NOTE_FLOOR:
        body += "·价值陷阱检测数据有限/不可用"
    return f"<div class='valuation-rollup'>{body}</div>"


_DRILLDOWN_CSS = (
    "<style>"
    "body{font-family:sans-serif}"
    ".holdings-board{border-collapse:collapse;font-size:13px;margin:8px 0;width:100%}"
    ".holdings-board th,.holdings-board td{border:1px solid #d0d7de;padding:3px 6px;text-align:right}"
    ".holdings-board th:nth-child(-n+3),.holdings-board td:nth-child(-n+3){text-align:left}"
    ".na-reason{color:#8c959f;font-size:11px}"
    ".flow-rollup{margin:8px 0;padding:6px 8px;background:#f6f8fa;border-left:3px solid #0969da;font-size:13px}"
    ".trap-badge{color:#9a6700;font-size:11px;background:#fff8c5;padding:0 4px;border-radius:3px}"
    ".valuation-rollup{margin:8px 0;padding:6px 8px;background:#f6f8fa;border-left:3px solid #8250df;font-size:13px}"
    "</style>"
)


def drilldown_section_html(name_cn: str, fund_id: str, metrics, agg, signal) -> str:
    """PURE: one fund's board + roll-up section (reused by card + standalone page)."""
    return (
        f"<section class='drilldown' id='dd-{escape(fund_id)}'>"
        f"<h2>{escape(name_cn)} ({escape(fund_id)})</h2>"
        f"{holdings_board_html(metrics)}{flow_rollup_html(metrics, agg, signal)}"
        "</section>"
    )


def drilldown_page_html(views) -> str:
    """PURE: full standalone drilldown.html. views = iterable of
    (fund_id, name_cn, metrics, agg, signal). Self-contained: inline CSS, no JS."""
    sections = "".join(
        drilldown_section_html(name_cn, fund_id, metrics, agg, signal)
        for fund_id, name_cn, metrics, agg, signal in views
    )
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor — 个股钻取</title>" + _DRILLDOWN_CSS + "</head><body>"
        + sections + "</body></html>"
    )
