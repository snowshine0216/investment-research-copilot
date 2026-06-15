from __future__ import annotations
from html import escape
from irc.monitor.types import Claim, NarrativeDoc, SignalRecord
from irc.monitor.render_factors import divergence_caveat

_BAND_PHRASE = {
    "ADD_BIAS": "≥ 买入阈值",
    "REDUCE_BIAS": "≤ 卖出阈值",
    "NEUTRAL": "落在中性带内",
}


def _claim_html(claim: Claim) -> str:
    text = escape(claim.claim)
    refs = "".join(f"[ref:{cid}]" for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"


def _ok_clause(rec: SignalRecord) -> str:
    rel = _BAND_PHRASE.get(rec.bias or "NEUTRAL", "落在中性带内")
    return (
        f'综合分 C = {rec.composite:.4f}（{rel}）→ '
        f'<b>{escape(rec.bias)}</b>'
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


def _comment(narr: NarrativeDoc) -> str:
    if narr.status != "ok":
        return f'<p class="narr-degraded">narrative unavailable: {escape(narr.status)}</p>'
    lead = narr.signal_rationale_commentary[:1]
    return "".join(f'<blockquote>{_claim_html(c)}</blockquote>' for c in lead)


def verdict_block_html(rec: SignalRecord, narr: NarrativeDoc) -> str:
    """PURE: deterministic verdict clause + capped MiniMax comment."""
    clause = _ok_clause(rec) if rec.status == "ok" else _gate_clause(rec)
    return f'<div class="verdict"><p class="verdict-clause">{clause}</p>{_comment(narr)}</div>'


def risk_block_html(rec: SignalRecord, narr: NarrativeDoc) -> str:
    """PURE: divergence caveats + MiniMax risk claims; muted placeholder if empty."""
    caveats = [f"<li>{divergence_caveat(code)}</li>" for code in rec.divergence_codes]
    risk_claims = (
        [_claim_html(c) for c in narr.risk_commentary] if narr.status == "ok" else []
    )
    if not caveats and not risk_claims:
        return '<div class="risk"><p class="muted">无显著风险信号</p></div>'
    cav_html = f"<ul class='caveats'>{''.join(caveats)}</ul>" if caveats else ""
    return (
        '<div class="risk"><h3>风险 / Risk</h3>'
        + cav_html + "".join(risk_claims) + "</div>"
    )


def narrative_sections_html(narr: NarrativeDoc) -> str:
    """PURE: only price_action_commentary in its own section (signal→verdict, risk→risk)."""
    if narr.status != "ok":
        return ""
    if not narr.price_action_commentary:
        return ""
    body = "".join(_claim_html(c) for c in narr.price_action_commentary)
    return f'<div class="price-action"><h3>价格走势 / Price action</h3>{body}</div>'
