from __future__ import annotations
from html import escape
from irc.monitor.types import Claim, NarrativeDoc, SignalRecord
from irc.monitor.render_factors import divergence_caveat
from irc.monitor.market_composite import MarketCompositeView

_HONESTY = "市场面综合分 前瞻验证累积中 · 目前仅趋势单因子有历史命中 ~0.54"

_BAND_PHRASE = {
    "ADD_BIAS": "落在偏多带",
    "REDUCE_BIAS": "落在偏空带",
    "NEUTRAL": "落在中性带内",
}

# Bias is a research lean, never an executable order (CONTEXT.md): gloss it in
# neutral lean language, never with a trade verb (买入/卖出).
_BIAS_GLOSS = {
    "ADD_BIAS": "偏多倾向",
    "REDUCE_BIAS": "偏空倾向",
    "NEUTRAL": "中性",
}


def _sup(cid: str, idx) -> str:
    """One numbered superscript anchor; '' when the cid isn't in the index."""
    n = idx.number(cid)
    if n is None:
        return ""
    title = escape(f"{idx.source(cid)} — {idx.title(cid)}")
    return f'<sup><a href="#ev-{cid}" title="{title}">{n}</a></sup>'


def decision_line_html(mv: MarketCompositeView | None, *, purchase_tag: str | None) -> str:
    """PURE Comp 1: the fact-backed decision line beneath the published badge.
    market anchor + news overlay delta (+易变) + optional 限购 tag + honesty line.
    '' when no market factor is present (mv is None)."""
    if mv is None:
        return ""
    tag = f' · {escape(purchase_tag)}' if purchase_tag else ""
    anchor = (
        f'市场面 决策锚: <b>{escape(mv.bias)}</b> ({mv.composite:+.2f}) · '
        f'新闻叠加 {mv.news_delta:+.2f} (易变){tag}'
    )
    return (
        f'<div class="decision-line">{anchor}'
        f'<span class="honesty muted">{_HONESTY}</span></div>'
    )


def _claim_html(claim: Claim, idx) -> str:
    text = escape(claim.claim)
    refs = "".join(_sup(cid, idx) for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"


def _ok_clause(rec: SignalRecord) -> str:
    bias = rec.bias or "NEUTRAL"
    rel = _BAND_PHRASE.get(bias, "落在中性带内")
    gloss = _BIAS_GLOSS.get(bias, "中性")
    return (
        f'综合分 C = {rec.composite:.4f}（{rel}）→ '
        f'<b>{escape(rec.bias)}</b>（{gloss}）'
    )


def _gate_clause(rec: SignalRecord) -> str:
    if rec.status == "insufficient_evidence":
        return (
            f"insufficient_evidence — families {len(rec.present_families)} / "
            f"available_weight {rec.available_weight:.2f} 未达门槛 → <b>NO_CALL</b>"
        )
    return (
        f"low_confidence — signal_confidence {rec.signal_confidence:.4f} "
        f"低于最低置信 → <b>NO_CALL</b>"
    )


def _comment(narr: NarrativeDoc, idx) -> str:
    if narr.status != "ok":
        return f'<p class="narr-degraded">narrative unavailable: {escape(narr.status)}</p>'
    lead = narr.signal_rationale_commentary[:1]
    return "".join(f'<blockquote>{_claim_html(c, idx)}</blockquote>' for c in lead)


def verdict_block_html(rec: SignalRecord, narr: NarrativeDoc, idx) -> str:
    """PURE: deterministic verdict clause + capped MiniMax comment."""
    clause = _ok_clause(rec) if rec.status == "ok" else _gate_clause(rec)
    return f'<div class="verdict"><p class="verdict-clause">{clause}</p>{_comment(narr, idx)}</div>'


def risk_block_html(rec: SignalRecord, narr: NarrativeDoc, idx) -> str:
    """PURE: divergence caveats + MiniMax risk claims; muted placeholder if empty."""
    caveats = [f"<li>{divergence_caveat(code)}</li>" for code in rec.divergence_codes]
    risk_claims = (
        [_claim_html(c, idx) for c in narr.risk_commentary] if narr.status == "ok" else []
    )
    if not caveats and not risk_claims:
        return '<div class="risk"><p class="muted">无显著风险信号</p></div>'
    cav_html = f"<ul class='caveats'>{''.join(caveats)}</ul>" if caveats else ""
    return (
        '<div class="risk"><h3>风险 / Risk</h3>'
        + cav_html + "".join(risk_claims) + "</div>"
    )


def narrative_sections_html(narr: NarrativeDoc, idx) -> str:
    """PURE: only price_action_commentary in its own section (signal→verdict, risk→risk)."""
    if narr.status != "ok":
        return ""
    if not narr.price_action_commentary:
        return ""
    body = "".join(_claim_html(c, idx) for c in narr.price_action_commentary)
    return f'<div class="price-action"><h3>价格走势 / Price action</h3>{body}</div>'
