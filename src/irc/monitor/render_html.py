from __future__ import annotations
from html import escape
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.render_cards import (
    narrative_sections_html, risk_block_html, verdict_block_html,
)
from irc.monitor.render_factors import factor_table_html, returns_table_html
from irc.monitor.svg_chart import EventMarker, render_nav_chart

_NO_CALL = "NO_CALL"

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
    "</style>"
)


def _badge(view: FundView) -> str:
    if view.signal.status != "ok":
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'


def _markers(view: FundView) -> tuple[EventMarker, ...]:
    return tuple(
        EventMarker(
            date=ev.date,
            sign=0,
            title=f"{escape(ev.title)} · {escape(ev.source)} · {ev.date}",
        )
        for ev in view.evidence_pool
    )


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
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view)}</h2>"
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
