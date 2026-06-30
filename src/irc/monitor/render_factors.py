from __future__ import annotations
from html import escape
from irc.monitor.types import FactorContribution, FactorScore, SignalRecord
from irc.monitor.annotate import factor_annotation, composite_annotation

CANONICAL_FACTOR_ORDER = ("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")

_DIVERGENCE_CAVEATS = {
    "trend_valuation_conflict": "趋势与估值背离：价格动能与估值方向相反",
    "trend_macro_conflict": "趋势与宏观背离：价格动能与宏观信号方向相反",
    "low_factor_agreement": "因子分歧较大：各因子方向/强度不一致",
    "valuation_flow_conflict": "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入",
}


def divergence_caveat(code: str) -> str:
    """PURE: divergence code → fixed Chinese caveat; unknown → escaped raw code."""
    return _DIVERGENCE_CAVEATS.get(code, escape(code))


def _num(x: float) -> str:
    return f"{x:.4f}"


def _present_row(c: FactorContribution, fresh: str) -> str:
    ann = factor_annotation(c.name, c.value)
    val_cell = (
        f'<td title="{escape(ann)}">{_num(c.value)}</td>' if ann
        else f"<td>{_num(c.value)}</td>"
    )
    return (
        f"<tr><td>{escape(c.name)}</td>{val_cell}"
        f"<td>{_num(c.renorm_weight)}</td><td>{_num(c.contribution)}</td>"
        f"<td>{_num(c.confidence)}</td><td>{escape(fresh)}</td>"
        f"<td>{escape(ann)}</td></tr>"
    )


def _na_row(s: FactorScore) -> str:
    return (
        f'<tr class="factor-na"><td>{escape(s.name)}</td>'
        "<td>—</td><td>—</td><td>—</td><td>—</td>"
        f"<td>{escape(s.reason)}</td><td>—</td></tr>"
    )


def factor_table_html(
    rec: SignalRecord, scores: tuple[FactorScore, ...], freshness: dict[str, str],
) -> str:
    """PURE: all-factors contribution table in canonical order, N/A rows dimmed."""
    by_contrib = {c.name: c for c in rec.contributions}
    by_score = {s.name: s for s in scores}
    rows = []
    for name in CANONICAL_FACTOR_ORDER:
        if name in by_contrib:
            rows.append(_present_row(by_contrib[name], freshness.get(name, "fresh")))
        elif name in by_score:
            rows.append(_na_row(by_score[name]))
    head = (
        "<tr><th>因子</th><th>值 sᵢ</th><th>权重 w'ᵢ</th>"
        "<th>贡献 w'ᵢ·sᵢ</th><th>置信</th><th>状态</th><th>解读</th></tr>"
    )
    fams = "、".join(escape(f) for f in rec.present_families)
    verdict = escape(composite_annotation(rec))
    footer = (
        f'<tr class="factor-foot"><td colspan="7">综合 C = {_num(rec.composite)} · '
        f"置信 {_num(rec.signal_confidence)} · available wt {_num(rec.available_weight)} · "
        f"families: {fams} · {verdict}</td></tr>"
    )
    return f"<table class='factors'>{head}{''.join(rows)}{footer}</table>"


def _ret_cell(w: int, v: float | None) -> str:
    return f"<td>{w}d: —</td>" if v is None else f"<td>{w}d: {v:+.2%}</td>"


def returns_table_html(rt: dict[int, float | None]) -> str:
    """PURE: [5,20,60,120,250]d returns row; None → —."""
    cells = "".join(_ret_cell(w, rt.get(w)) for w in (5, 20, 60, 120, 250))
    return f"<table class='returns'><tr>{cells}</tr></table>"
