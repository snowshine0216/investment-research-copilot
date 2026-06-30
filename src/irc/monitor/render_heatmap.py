"""PURE Comp 3a: cross-fund factor heatmap. Rows=funds (by full C desc), columns
grouped market(trend,valuation,flow,heat) | news(macro_tilt,constituent) | 市场面C |
完整C. Diverging fill reuses the report's badge convention (add_bias green / reduce_bias
red), intensity ∝ |value|. No JS, no remote refs. Byte-stable."""
from __future__ import annotations
from html import escape
from irc.monitor.annotate import factor_annotation

_MARKET = ("trend", "valuation", "flow", "heat")
_NEWS = ("macro_tilt", "constituent")
_GREEN = "#1a7f37"
_RED = "#cf222e"


def _fill(value: float | None) -> str:
    if value is None:
        return ""
    a = min(abs(value), 1.0)
    colour = _GREEN if value > 0 else (_RED if value < 0 else "")
    if not colour:
        return ""
    return f'background:{colour};opacity:{a:.2f}'


def _value_of(view, name: str) -> float | None:
    for c in view.signal.contributions:
        if c.name == name:
            return c.value
    return None


def _cell(view, name: str) -> str:
    v = _value_of(view, name)
    if v is None:
        return '<td class="muted">—</td>'
    ann = escape(factor_annotation(name, v))
    return f'<td style="{_fill(v)}" title="{ann}">{v:+.2f}</td>'


def _composite_cell(value: float | None) -> str:
    if value is None:
        return '<td class="muted">—</td>'
    return f'<td style="{_fill(value)}">{value:+.2f}</td>'


def _row(view) -> str:
    mc = view.market_view.composite if view.market_view else None
    cells = "".join(_cell(view, n) for n in (*_MARKET, *_NEWS))
    return (f"<tr><td>{escape(view.name_cn)}</td>{cells}"
            f"{_composite_cell(mc)}{_composite_cell(view.signal.composite)}</tr>")


def _header() -> str:
    cols = "".join(f"<th>{escape(n)}</th>" for n in (*_MARKET, *_NEWS))
    return f"<tr><th>基金</th>{cols}<th>市场面C</th><th>完整C</th></tr>"


def factor_heatmap_html(views: tuple) -> str:
    if not views:
        return ""
    ordered = sorted(views, key=lambda v: v.signal.composite, reverse=True)
    body = "".join(_row(v) for v in ordered)
    legend = '<p class="muted heatmap-legend">正=偏多 / 负=偏空</p>'
    return ('<section class="heatmap"><h2>跨基金因子热力图</h2>'
            f'<table class="heatmap-table">{_header()}{body}</table>{legend}</section>')
