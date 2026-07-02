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


def all_na_columns(rows: list[dict], *, columns: tuple[str, ...]) -> frozenset[str]:
    """PURE: columns whose value is None/absent for EVERY row (dead-dash column
    collapse, spec §8). Empty rows -> frozenset() (no rows is not 'all dark')."""
    if not rows:
        return frozenset()
    return frozenset(
        col for col in columns
        if all(row.get(col) is None for row in rows)
    )


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


_BOARD_NA_COLUMNS = ("pb", "pe", "pe_percentile", "valuation_state", "industry",
                     "industry_pe", "industry_richness", "industry_score",
                     "flow_pct_5d", "flow_pct_20d", "flow_score")

_COL_LABEL = {
    "pb": "PB", "pe": "PE", "pe_percentile": "PE分位", "valuation_state": "估值",
    "industry": "行业", "industry_pe": "行业PE", "industry_richness": "r",
    "industry_score": "行业分", "flow_pct_5d": "5d净占比", "flow_pct_20d": "20d净占比",
    "flow_score": "资金流分",
}


def _row_reason(rows: list[dict], column: str) -> str:
    for r in rows:
        reason = r.get(f"{column}_reason") or r.get("industry_reason") or r.get("flow_reason") \
                 or r.get("valuation_reason")
        if reason:
            return reason
    return "no_data"


def _board_rows_dict(ordered: tuple[HoldingMetric, ...]) -> list[dict]:
    return [
        {"pb": m.pb, "pe": m.pe, "pe_percentile": m.pe_percentile,
         "valuation_state": m.valuation_state, "industry": m.industry,
         "industry_pe": m.industry_pe, "industry_richness": m.industry_richness,
         "industry_score": m.industry_score, "flow_pct_5d": m.flow_pct_5d,
         "flow_pct_20d": m.flow_pct_20d, "flow_score": m.flow_score,
         "industry_reason": m.industry_reason, "flow_reason": m.flow_reason,
         "valuation_reason": m.valuation_reason}
        for m in ordered
    ]


def _board_dark_note(rows_dict: list[dict], dark_cols: frozenset[str]) -> str:
    if not dark_cols:
        return ""
    parts = "、".join(
        f"{_COL_LABEL.get(c, c)}（{_row_reason(rows_dict, c)}）"
        for c in sorted(dark_cols)
    )
    return f'<p class="na-reason board-dark-note">本表全暗列：{parts}</p>'


def holdings_board_html(metrics: tuple[HoldingMetric, ...]) -> str:
    """PURE: top-holdings board, rows sorted by weight desc, N/A cells dashed.
    A column that is N/A for EVERY row collapses to a single header note
    carrying the structured reason code instead of a wall of dashes (spec §8)."""
    head = (
        "<tr><th>#</th><th>代码</th><th>名称</th><th>权重%</th><th>PB</th><th>PE</th>"
        "<th>PE分位</th><th>估值</th><th>行业</th><th>行业PE</th><th>r</th><th>行业分</th>"
        "<th>5d净占比</th><th>20d净占比</th><th>资金流分</th></tr>"
    )
    ordered = tuple(sorted(metrics, key=lambda m: m.weight_pct, reverse=True))
    rows_dict = _board_rows_dict(ordered)
    dark_cols = all_na_columns(rows_dict, columns=_BOARD_NA_COLUMNS)
    rows = "".join(_row(i, m) for i, m in enumerate(ordered, start=1))
    note = _board_dark_note(rows_dict, dark_cols)
    return f"<table class='holdings-board'>{head}{rows}</table>{note}"


def _aum_share(metrics: tuple[HoldingMetric, ...]) -> float:
    return sum(m.weight_pct for m in metrics)


def flow_rollup_html(
    metrics: tuple[HoldingMetric, ...], agg: FlowAggregate, signal: SignalRecord,
) -> str:
    """PURE: the reconciliation line — flow factor = Σ(wᵢ·sᵢ)/Σ(wᵢ), covered ratio,
    and top-5 representativeness (% of fund AUM, ALWAYS shown). Lean language only.
    N/A (agg.value is None) renders a 暗·覆盖不足 chip (spec §8 — 'PASS' elsewhere
    must not read as 'data fine')."""
    aum = _aum_share(metrics)
    if agg.value is None:
        chip = '<span class="dark-chip">暗·覆盖不足</span> '
        body = (
            f"{chip}资金流因子 = N/A（{escape(agg.reason or 'flow_no_data')}）· "
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


def provisional_flow_annotation_html(*, symbol_value: float | None, as_of_hhmm: str) -> str:
    """PURE: render-only 盘中提示 annotation for the per-fund flow rollup line
    (spec §8 — obligation inherited from CONTEXT.md 'Flow freshness state').
    symbol_value is the aggregate intraday flow reading (already computed at
    the edge from _provisional_flow_note); None -> '' (degrades silently, the
    edge already logs the fetch failure). NEVER implies this value feeds the
    factor — the trailing 非因子输入 clause is load-bearing."""
    if symbol_value is None:
        return ""
    return (
        f'<div class="provisional-flow muted">盘中主力净流入(截至{escape(as_of_hhmm)}) '
        f'{symbol_value:+.2f}% · 盘中值，非因子输入</div>'
    )


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
    ".dark-chip{font-size:11px;color:#bf8700;background:#fff8c5;padding:0 4px;border-radius:3px}"
    ".provisional-flow{font-size:12px;margin-top:4px}"
    "</style>"
)


def drilldown_section_html(
    name_cn: str, fund_id: str, metrics, agg, signal, val_agg=None,
) -> str:
    """PURE: one fund's board + roll-up section (reused by card + standalone page).
    val_agg: optional ValuationAggregate; when present, appends valuation rollup."""
    val_html = valuation_rollup_html(metrics, val_agg) if val_agg is not None else ""
    return (
        f"<section class='drilldown' id='dd-{escape(fund_id)}'>"
        f"<h2>{escape(name_cn)} ({escape(fund_id)})</h2>"
        f"{holdings_board_html(metrics)}{flow_rollup_html(metrics, agg, signal)}"
        f"{val_html}</section>"
    )


def drilldown_page_html(views) -> str:
    """PURE: full standalone drilldown.html. views = iterable of
    (fund_id, name_cn, metrics, agg, signal) or
    (fund_id, name_cn, metrics, agg, signal, val_agg).
    Self-contained: inline CSS, no JS."""
    def _section(row) -> str:
        fund_id, name_cn, metrics, agg, signal = row[:5]
        val_agg = row[5] if len(row) > 5 else None
        return drilldown_section_html(name_cn, fund_id, metrics, agg, signal, val_agg)

    sections = "".join(_section(row) for row in views)
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor — 个股钻取</title>" + _DRILLDOWN_CSS + "</head><body>"
        + sections + "</body></html>"
    )
