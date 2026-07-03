from __future__ import annotations
import statistics
from html import escape
from irc.monitor.types import FactorContribution, FactorScore, SignalRecord
from irc.monitor.annotate import factor_annotation, composite_annotation
from irc.monitor.signal import _LOW_AGREEMENT_STDEV

CANONICAL_FACTOR_ORDER = ("trend", "valuation", "flow", "heat", "macro_tilt", "constituent")

_DIVERGENCE_CAVEATS = {
    "trend_valuation_conflict": "趋势与估值背离：价格动能与估值方向相反",
    "trend_macro_conflict": "趋势与宏观背离：价格动能与宏观信号方向相反",
    "low_factor_agreement": "因子分歧较大：各因子方向/强度不一致",
    "valuation_flow_conflict": "估值与资金流背离：便宜但资金流出 / 偏贵但资金流入",
}

_PAIRWISE = {  # code → (title, factor_a, factor_b); factor order follows the code name
    "trend_valuation_conflict": ("趋势与估值背离", "trend", "valuation"),
    "trend_macro_conflict": ("趋势与宏观背离", "trend", "macro_tilt"),
    "valuation_flow_conflict": ("估值与资金流背离", "valuation", "flow"),
}
_DISPLAY_NAME = {"trend": "趋势", "macro_tilt": "宏观", "valuation": "估值", "flow": "资金流"}
_SIGN_GLOSS = {  # factor → (gloss when value >= 0, gloss when value < 0)
    "trend": ("价格动能向上", "价格动能向下"),
    "macro_tilt": ("新闻/宏观偏多", "新闻/宏观偏空"),
    "valuation": ("估值偏便宜", "估值偏贵"),
    "flow": ("资金净流入", "资金净流出"),
}


def divergence_caveat(code: str) -> str:
    """PURE: divergence code → fixed Chinese caveat; unknown → escaped raw code."""
    return _DIVERGENCE_CAVEATS.get(code, escape(code))


def _signed(v: float) -> str:
    return f"{v + 0.0:+.2f}"  # +0.0 normalizes -0.0 so it renders +0.00, never -0.00 (G8)


def _factor_phrase(name: str, value: float) -> str:
    pos_gloss, neg_gloss = _SIGN_GLOSS[name]
    gloss = neg_gloss if value < 0 else pos_gloss
    return f"{_DISPLAY_NAME[name]} {_signed(value)}（{gloss}）"


def _pairwise_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str:
    title, a, b = _PAIRWISE[code]
    by = {c.name: c.value for c in contributions}
    if a not in by or b not in by:
        return divergence_caveat(code)  # AC-5: required factor absent → static fallback
    return f"{title}：{_factor_phrase(a, by[a])} vs {_factor_phrase(b, by[b])}"


def _canonical_order(cs: tuple[FactorContribution, ...]) -> tuple[FactorContribution, ...]:
    rank = {n: i for i, n in enumerate(CANONICAL_FACTOR_ORDER)}
    return tuple(sorted(cs, key=lambda c: rank.get(c.name, len(CANONICAL_FACTOR_ORDER))))


def _group(ordered: tuple[FactorContribution, ...], keep) -> str:
    return "、".join(f"{escape(c.name)} {_signed(c.value)}" for c in ordered if keep(c.value))


def _grouped_by_sign(contributions: tuple[FactorContribution, ...]) -> str:
    ordered = _canonical_order(contributions)
    pos = _group(ordered, lambda v: v > 0)
    neg = _group(ordered, lambda v: v < 0)
    zero = _group(ordered, lambda v: v == 0)
    tail = f"、中性 {zero}" if zero else ""  # Q5: exact-zero factors trail as 中性
    return f"因子分歧较大：偏多 {pos} ↔ 偏空 {neg}{tail}"


def _low_agreement_detail(contributions: tuple[FactorContribution, ...]) -> str:
    vals = [c.value for c in contributions]
    if len(vals) < 2:
        return divergence_caveat("low_factor_agreement")  # AC-5 fallback
    if any(v > 0 for v in vals) and any(v < 0 for v in vals):
        return _grouped_by_sign(contributions)  # Q4: grouped wins when signs conflict
    sigma = statistics.pstdev(vals)  # RAW value gates (G2); rounding is display-only
    if sigma < _LOW_AGREEMENT_STDEV:
        return divergence_caveat("low_factor_agreement")  # Q9: never a false σ claim
    return f"因子分歧较大：强度离散 σ={sigma:.2f} ≥ {_LOW_AGREEMENT_STDEV:g}"


def divergence_caveat_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str:
    """PURE: divergence code + present contributions → parametrized caveat naming the
    disagreeing factors with signed values; every degraded case delegates to
    divergence_caveat(code) (static map / escaped-passthrough fallback, G5)."""
    if code in _PAIRWISE:
        return _pairwise_detail(code, contributions)
    if code == "low_factor_agreement":
        return _low_agreement_detail(contributions)
    return divergence_caveat(code)


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
