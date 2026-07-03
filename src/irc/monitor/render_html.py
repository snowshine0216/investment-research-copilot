from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from html import escape
from urllib.parse import urlparse
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.source_tiers import SourceTiers, TIER_LABEL, classify
from irc.monitor.render_cards import (
    narrative_sections_html, risk_block_html, verdict_block_html, decision_line_html,
    theme_chips_html,
)
from irc.monitor.narrative_macro import MacroNarrativeDoc, theme_display_name
from irc.monitor.types import EvidenceItem
from irc.monitor.render_factors import factor_table_html, returns_table_html
from irc.monitor.render_drilldown import (
    holdings_board_html, flow_rollup_html, provisional_flow_annotation_html,
)
from irc.monitor.holding_metrics import aggregate_flow
from irc.monitor.svg_chart import EventMarker, render_nav_chart
from irc.monitor.eval.gate import published_state
from irc.monitor.eval.panel import validation_panel_html
from irc.monitor.eval.predictive_panel import predictive_validity_panel_html
from irc.monitor.eval.types import GateDecision, ValidationPanelRow, PredictivePanelModel
from irc.monitor.render_heatmap import factor_heatmap_html
from irc.monitor.render_timeline import BiasTimeline, bias_timeline_html
from irc.monitor.render_contrib import contribution_bars_svg
from irc.monitor.render_overview import (
    caveat_row, caveat_tooltip, compute_actionable, compute_data_health,
    compute_flips, fund_specific_segments, overview_html,
)


@dataclass(frozen=True)
class CitationIndex:
    """PURE cid -> 1-based N + (source, title, date, tier_label). Multiple cids
    sharing a canonical identity key (url or title, date) collapse to ONE
    appendix entry (Comp 4 — exact post-Comp-2-consolidation; query-string
    stripping was considered and rejected, spec §6)."""
    entries: tuple[tuple[str, str, str, str, str], ...]   # (canonical_cid, source, title, date, tier_label)
    cid_to_entry_index: dict[str, int]

    def number(self, cid: str) -> int | None:
        i = self.cid_to_entry_index.get(cid)
        return None if i is None else i + 1

    def source(self, cid: str) -> str | None:
        i = self.cid_to_entry_index.get(cid)
        return None if i is None else self.entries[i][1]

    def title(self, cid: str) -> str | None:
        i = self.cid_to_entry_index.get(cid)
        return None if i is None else self.entries[i][2]

    def date(self, cid: str) -> str | None:
        i = self.cid_to_entry_index.get(cid)
        return None if i is None else self.entries[i][3]

    def tier_label(self, cid: str) -> str | None:
        i = self.cid_to_entry_index.get(cid)
        return None if i is None else self.entries[i][4]


def _identity_key(ev) -> tuple[str, str]:
    """Canonical dedup identity: (url or title, date). Exact-string URL match —
    query-string stripping rejected (spec §6): query-routed pages would merge
    wrongly, and post-Comp-2-consolidation the same article yields byte-identical
    URLs anyway."""
    return (ev.url or ev.title, ev.date)


def build_tier_badges(
    items: tuple[EvidenceItem, ...], *, tiers: SourceTiers,
    constituent_cids: frozenset[str],
) -> dict[str, str]:
    """PURE: citation_id -> Chinese tier-badge label. Constituent-pool items
    (their cids passed in constituent_cids) always get 快照 (ADR 0022 — a
    domain tier is meaningless for snapshot-grounded evidence, never 未分级
    which would misread as 'unvetted web source'). Everything else classifies
    via classify(domain, tiers) -> TIER_LABEL. Blocked items should never reach
    here (dropped at ingest), but a defensive fallback still labels them 已屏蔽
    rather than crashing."""
    out: dict[str, str] = {}
    for ev in items:
        if ev.citation_id in constituent_cids:
            out[ev.citation_id] = "快照"
            continue
        domain = urlparse(ev.url).hostname or ev.source if ev.url else ev.source
        tier = classify(domain or "", tiers)
        out[ev.citation_id] = TIER_LABEL.get(tier, "未分级")
    return out


def build_citation_index(
    views: tuple[FundView, ...], macro_pool_items: tuple[EvidenceItem, ...] = (),
    *, tier_badges: dict[str, str] | None = None,
) -> CitationIndex:
    """PURE: first-seen (url-or-title, date) identity index over every fund's
    evidence pool PLUS the macro pool. Same iteration order as _appendix so
    superscript-N == appendix-N. `tier_badges` maps citation_id -> tier label
    (source_tiers.TIER_LABEL value, or '快照' for constituent-pool items) —
    each appendix ENTRY carries the badge of its first-seen cid (later cids
    sharing the identity key do not override it)."""
    badges = tier_badges or {}
    seen_identity: dict[tuple[str, str], int] = {}
    cid_to_entry_index: dict[str, int] = {}
    entries: list[list] = []   # mutable during build; frozen to tuples at the end

    def _absorb(ev) -> None:
        key = _identity_key(ev)
        idx_pos = seen_identity.get(key)
        if idx_pos is None:
            idx_pos = len(entries)
            seen_identity[key] = idx_pos
            entries.append([ev.citation_id, ev.source, ev.title, ev.date,
                            badges.get(ev.citation_id, "")])
        cid_to_entry_index[ev.citation_id] = idx_pos

    for v in views:
        for ev in v.evidence_pool:
            _absorb(ev)
    for ev in macro_pool_items:
        _absorb(ev)
    return CitationIndex(
        tuple(tuple(e) for e in entries), cid_to_entry_index,
    )


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
    "a.val-chip{text-decoration:none}"
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
    ".holdings-board{border-collapse:collapse;font-size:13px;margin:8px 0;width:100%}"
    ".holdings-board th,.holdings-board td{border:1px solid #d0d7de;padding:3px 6px;text-align:right}"
    ".holdings-board th:nth-child(-n+3),.holdings-board td:nth-child(-n+3){text-align:left}"
    ".na-reason{color:#8c959f;font-size:11px}"
    ".tier-badge{color:#57606a;font-size:11px}"
    ".flow-rollup{margin:8px 0;padding:6px 8px;background:#f6f8fa;border-left:3px solid #0969da;font-size:13px}"
    ".flow-outage{margin:8px 0;padding:6px 8px;background:#fff8c5;border:1px solid #d4a72c;border-radius:6px}"
    "sup a{text-decoration:none}"
    ".decision-line{margin:6px 0;padding:6px 8px;background:#f6f8fa;"
    "border-left:3px solid #1a7f37;font-size:13px;line-height:1.5}"
    ".decision-line .honesty{display:block;margin-top:3px;font-size:12px}"
    ".heatmap-table,.timeline-table{border-collapse:collapse;font-size:12px;margin:8px 0}"
    ".heatmap-table td,.heatmap-table th,.timeline-table td,.timeline-table th"
    "{border:1px solid #d0d7de;padding:2px 5px;text-align:center}"
    ".tl-cell.add_bias{color:#1a7f37}.tl-cell.reduce_bias{color:#cf222e}.tl-cell.neutral{color:#6e7781}"
    ".engine-boundary{border-left:2px solid #bf8700}"
    ".contrib{width:100%;max-width:280px;height:auto;display:block;margin:6px 0}"
    ".heatmap-legend{font-size:11px}"
    ".overview{margin:8px 0;padding:8px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa}"
    ".overview-row{margin:4px 0}"
    ".flip-from{color:#6e7781}.flip-to{font-weight:600}"
    ".restricted-tag{font-size:11px;color:#9a6700;background:#fff8c5;padding:0 4px;border-radius:3px}"
    ".panel-amber{background:#fff8c5}"
    ".age-amber{color:#bf8700}"
    ".dark-chip{font-size:11px;color:#bf8700;background:#fff8c5;padding:0 4px;border-radius:3px}"
    ".provisional-flow{font-size:12px;margin-top:4px}"
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
    '<span class="legend">估值 + 资金流 → 倾向（偏多/偏空），仍为研究参考、非买卖指令</span>'
    '<span class="legend-en">Directional bias is a research lean, '
    'not a buy/sell order and not investment advice.</span>'
    '</aside>'
)


def _drilldown_block(view: FundView) -> str:
    if not view.holding_metrics:
        return ""
    agg = aggregate_flow(view.holding_metrics)
    provisional = provisional_flow_annotation_html(
        symbol_value=view.provisional_flow_pct,
        as_of_hhmm=view.provisional_flow_as_of or "")
    return (holdings_board_html(view.holding_metrics)
            + flow_rollup_html(view.holding_metrics, agg, view.signal)
            + provisional)


def _flow_eligible(view: FundView) -> bool:
    """A fund is flow-eligible iff its flow factor is present OR N/A for a
    data/coverage reason (NOT profile_ineligible)."""
    for s in view.factor_scores:
        if s.name == "flow":
            return s.reason != "profile_ineligible"
    return False


def _flow_present(view: FundView) -> bool:
    return any(s.name == "flow" and s.eligible for s in view.factor_scores)


def _flow_outage_note(views: tuple[FundView, ...]) -> str:
    """PURE: ONE run-level header line iff set-wide flow coverage collapses — every
    flow-eligible fund lost its flow leg (0 usable). No flow-eligible fund → "" (not
    an outage). Driven by factor N/A reasons, not a side effect. Per-fund N/A stays
    non-caveating (KNOWN_NA_REASONS)."""
    eligible = [v for v in views if _flow_eligible(v)]
    if not eligible:
        return ""
    if any(_flow_present(v) for v in eligible):
        return ""
    return ('<div class="flow-outage">⚠ 资金流数据今日不可用——倾向回退至五因子 '
            "(flow unavailable today; lean fell back to 5-factor)</div>")


def _chip(gate: GateDecision) -> str:
    """P2: caveated chip = anchor to #validation-panel with the Chinese-labeled
    caveat reason as an escaped tooltip; validated stays a plain span (no
    tooltip, no anchor — an anchor with an empty tooltip invites misreading)."""
    cls_label = _CHIP.get(gate.badge)
    if not cls_label:
        return ""
    cls, label = cls_label
    if gate.badge != "caveated":
        return f'<span class="val-chip {cls}">{label}</span>'
    title = escape(caveat_tooltip(gate.reason))
    return (f'<a class="val-chip {cls}" href="#validation-panel" '
            f'title="{title}">{label}</a>')


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
    return f'<span class="badge {state.lower()}">{escape(state)}</span>{_chip(gate)}'


def _markers(view: FundView) -> tuple[EventMarker, ...]:
    return tuple(
        EventMarker(
            date=ev.date,
            sign=0,
            title=f"{escape(ev.title)} · {escape(ev.source)} · {ev.date}",
        )
        for ev in view.evidence_pool
    )


def _market_cell(view: FundView) -> str:
    mv = view.market_view
    if mv is None:
        return "<td class='muted'>—</td>"
    return f"<td>市场面 {mv.composite:+.2f} {escape(mv.bias)}</td>"


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
        f"{_market_cell(view)}"
        f"<td>{changed}</td></tr>"
    )


def _card_caveat(gate: GateDecision | None) -> str:
    """P2: 为何有保留 — fund-specific caveat segments only. Run-global causes
    dedupe to the ONE overview line; gated funds (prefix-free FAIL reasons)
    and validated funds render nothing."""
    if gate is None or gate.badge != "caveated":
        return ""
    segments = fund_specific_segments(gate.reason)
    if not segments:
        return ""
    return f'<p class="card-caveat muted">为何有保留：{escape("; ".join(segments))}</p>'


def _card(view: FundView, gate: GateDecision | None, idx: CitationIndex) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{_card_caveat(gate)}"
        f"{decision_line_html(view.market_view, purchase_tag=view.purchase_tag)}"
        f"{verdict_block_html(view.signal, view.narrative, idx)}"
        f"{chart}"
        f"{contribution_bars_svg(view.signal.contributions)}"
        f"{returns_table_html(view.return_table)}"
        f"{factor_table_html(view.signal, view.factor_scores, view.factor_freshness)}"
        f"{_drilldown_block(view)}"
        f"{theme_chips_html(view.themes)}"
        f"{narrative_sections_html(view.narrative, idx)}"
        f"{risk_block_html(view.signal, view.narrative, idx)}"
        "</section>"
    )


def _appendix(idx: CitationIndex) -> str:
    items = []
    for n, (cid, source, title, ev_date, tier_label) in enumerate(idx.entries, start=1):
        date_part = f" · {escape(ev_date)}" if ev_date else ""
        badge_part = f' · <span class="tier-badge">{escape(tier_label)}</span>' if tier_label else ""
        items.append(
            f'<li id="ev-{cid}">{n}. {escape(title)} — {escape(source)}'
            f'{date_part}{badge_part}</li>'
        )
    return (
        "<details><summary>证据 / Evidence</summary><ol>"
        + "".join(items)
        + "</ol></details>"
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
    panel_rows: tuple[ValidationPanelRow, ...], *, now_dt: datetime,
) -> str:
    if not gates or not panel_rows:
        return ""
    return validation_panel_html(rows=panel_rows,
                                 badge_counts=_badge_counts(views, gates), now=now_dt)


def _macro_claim_html(claim, idx: "CitationIndex") -> str:
    text = escape(claim.claim)
    refs = "".join(_sup_local(cid, idx) for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"


def _sup_local(cid: str, idx: "CitationIndex") -> str:
    n = idx.number(cid)
    if n is None:
        return ""
    date = idx.date(cid)
    date_part = f" · {date}" if date else ""
    title = escape(f"{idx.source(cid)} — {idx.title(cid)}{date_part}")
    return f'<sup><a href="#ev-{cid}" title="{title}">{n}</a></sup>'


def _macro_theme_section(
    block, fund_themes_by_theme: dict[str, tuple[str, ...]], idx: "CitationIndex | None",
) -> str:
    label = escape(theme_display_name(block.theme))
    funds = fund_themes_by_theme.get(block.theme, ())
    chips = "".join(f'<span class="fund-chip">{escape(fid)}</span>' for fid in funds)
    body = "".join(_macro_claim_html(c, idx) if idx is not None else f"<p>{escape(c.claim)}</p>"
                   for c in block.claims)
    return (
        f'<div class="macro-theme" id="macro-{escape(block.theme)}">'
        f"<h3>{label}</h3><div class=\"fund-chips\">{chips}</div>{body}</div>"
    )


def macro_narrative_html(
    doc: MacroNarrativeDoc | None,
    *, fund_themes_by_theme: dict[str, tuple[str, ...]],
    idx: "CitationIndex | None" = None,
) -> str:
    """PURE: 宏观面速览 section, theme-labeled Chinese subsections with #macro-<theme>
    anchors + affected-fund chips (spec §5). None doc or 'empty_pool'/non-'ok'
    status or zero blocks -> '' (degrades like the timeline/predictive panel)."""
    if doc is None or doc.status != "ok" or not doc.blocks:
        return ""
    sections = "".join(_macro_theme_section(b, fund_themes_by_theme, idx) for b in doc.blocks)
    return f'<section class="macro-narrative"><h2>宏观面速览</h2>{sections}</section>'


def _invert_fund_themes(views: tuple[FundView, ...]) -> dict[str, tuple[str, ...]]:
    """PURE: theme -> tuple of fund_ids whose fund.themes include it (deterministic
    from config, spec §5 — 'affected-fund chips ... reverse of the card→anchor
    links'). Stable order: iteration order of views."""
    out: dict[str, list[str]] = {}
    for v in views:
        for theme in v.themes:
            out.setdefault(theme, []).append(v.fund_id)
    return {theme: tuple(fids) for theme, fids in out.items()}


def render_report(
    views: tuple[FundView, ...],
    provenance: Provenance,
    *,
    prior_signal: dict | None,
    now: str,
    now_dt: datetime,
    gates: dict[str, GateDecision] | None = None,
    panel_rows: tuple[ValidationPanelRow, ...] = (),
    predictive_panel: PredictivePanelModel | None = None,
    timeline: BiasTimeline | None = None,
    macro_narrative: MacroNarrativeDoc | None = None,
    macro_pool_items: tuple[EvidenceItem, ...] = (),
    tiers: SourceTiers | None = None,
    constituent_pool_items: tuple[EvidenceItem, ...] = (),
    prior_run_date: str | None = None,
    purchase_tags: dict[str, str | None] | None = None,
    stale_eval_days: int = 10,
) -> str:
    """PURE: self-contained HTML. No I/O, no JS, no remote refs."""
    header = (
        f'<header>as_of {now} · engine {provenance.engine_version} · '
        f'prompt {provenance.prompt_version} · schema {provenance.schema_version} · '
        f'{escape(provenance.spend_summary)}</header>'
    )
    g = gates or {}
    constituent_cids = frozenset(ev.citation_id for ev in constituent_pool_items)
    all_pool_items = (tuple(ev for v in views for ev in v.evidence_pool)
                      + macro_pool_items + constituent_pool_items)
    tier_badges = build_tier_badges(
        all_pool_items, tiers=tiers or SourceTiers((), (), ()),
        constituent_cids=constituent_cids,
    )
    idx = build_citation_index(views, macro_pool_items + constituent_pool_items,
                               tier_badges=tier_badges)
    flips = compute_flips(views, prior_signal, prior_run_date)
    actionable = compute_actionable(views, g, purchase_tags or {})
    # `today` derived PURELY from the as_of stamp (first 10 chars of the ISO
    # `now` string); `predictive_stale` from the already-computed
    # PredictivePanelModel — NO clock read anywhere under render_* (spec §2,
    # Global Constraints).
    health = compute_data_health(
        views, g, panel_rows, stale_eval_days=stale_eval_days, today=now[:10],
        predictive_stale=(predictive_panel.stale if predictive_panel is not None else False),
    )
    overview = overview_html(flips=flips, actionable=actionable, health=health,
                             caveat_row_html=caveat_row(panel_rows, g))
    summary = (
        "<table class='summary'>"
        + "".join(_summary_row(v, prior_signal, g.get(v.fund_id)) for v in views)
        + "</table>"
    )
    heatmap = factor_heatmap_html(views)
    fund_names = {v.fund_id: v.name_cn for v in views}
    timeline_html = bias_timeline_html(timeline, fund_names=fund_names) if timeline is not None else ""
    fund_themes_by_theme = _invert_fund_themes(views)
    macro_html = macro_narrative_html(
        macro_narrative, fund_themes_by_theme=fund_themes_by_theme, idx=idx)
    cards = "".join(_card(v, g.get(v.fund_id), idx) for v in views)
    panel = _panel(views, gates, panel_rows, now_dt=now_dt)
    outage_note = _flow_outage_note(views)
    predictive = (
        predictive_validity_panel_html(model=predictive_panel)
        if predictive_panel is not None else ""
    )
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>irc monitor</title>" + _CSS + "</head><body>"
        + header + outage_note + overview + _EXPLAINER + summary + heatmap + timeline_html
        + macro_html + cards + panel + predictive
        + _appendix(idx) + "</body></html>"
    )
