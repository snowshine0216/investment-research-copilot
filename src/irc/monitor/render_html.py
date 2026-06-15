from __future__ import annotations
from html import escape
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.svg_chart import EventMarker, render_nav_chart
from irc.monitor.types import Claim, NarrativeDoc

_NO_CALL = "NO_CALL"

_CSS = (
    "<style>"
    "body{font-family:sans-serif}"
    ".badge{padding:2px 6px;border-radius:4px}"
    ".no-call{background:#6e7781;color:#fff}"
    ".add_bias{background:#1a7f37;color:#fff}"
    ".neutral{background:#6e7781;color:#fff}"
    ".reduce_bias{background:#cf222e;color:#fff}"
    "</style>"
)


def _badge(view: FundView) -> str:
    if view.signal.status != "ok":
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'


def _claim_html(claim: Claim) -> str:
    text = escape(claim.claim)
    refs = "".join(f"[ref:{cid}]" for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"


def _narrative_html(narr: NarrativeDoc) -> str:
    if narr.status != "ok":
        return f'<p class="narr-degraded">narrative unavailable: {escape(narr.status)}</p>'
    blocks = [_claim_html(c) for c in narr.price_action_commentary]
    blocks += [_claim_html(c) for c in narr.signal_rationale_commentary]
    blocks += [_claim_html(c) for c in narr.risk_commentary]
    return "".join(blocks)


def _markers(view: FundView) -> tuple[EventMarker, ...]:
    return tuple(
        EventMarker(
            date=ev.date,
            sign=0,
            title=f"{escape(ev.title)} · {escape(ev.source)} · {ev.date}",
        )
        for ev in view.evidence_pool
    )


def _returns_html(rt: dict[int, float]) -> str:
    cells = "".join(f"<td>{w}d: {v:+.2%}</td>" for w, v in sorted(rt.items()))
    return f"<table class='returns'><tr>{cells}</tr></table>"


def _summary_row(view: FundView, prior: dict | None) -> str:
    changed = ""
    if prior is not None:
        prev = (prior.get(view.fund_id) or {}).get("bias")
        if prev != view.signal.bias:
            changed = '<span class="changed-since-yesterday" style="color:#bf8700">●</span>'
    return (
        f"<tr><td>{escape(view.name_cn)}</td>"
        f"<td>{view.latest_nav:.4f} @ {view.as_of_date}</td>"
        f"<td>{_badge(view)}</td>"
        f"<td>C={view.signal.composite:+.4f}</td>"
        f"<td>{changed}</td></tr>"
    )


def _card(view: FundView) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    miss = "".join(f"<li>{escape(r)}</li>" for r in view.missing_factor_reasons)
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view)}</h2>"
        f"{chart}{_returns_html(view.return_table)}"
        f"{_narrative_html(view.narrative)}"
        f"<ul class='missing'>{miss}</ul></section>"
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


def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
) -> str:
    """PURE: self-contained HTML. No I/O, no JS, no remote refs. Byte-stable given
    identical inputs (only `now` is volatile and injected)."""
    header = (
        f'<header>as_of {now} · engine {provenance.engine_version} · '
        f'prompt {provenance.prompt_version} · schema {provenance.schema_version} · '
        f'{escape(provenance.spend_summary)}</header>'
    )
    summary = (
        "<table class='summary'>"
        + "".join(_summary_row(v, prior_signal) for v in views)
        + "</table>"
    )
    cards = "".join(_card(v) for v in views)
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor</title>" + _CSS + "</head><body>"
        + header + summary + cards + _appendix(views) + "</body></html>"
    )
