from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from irc.config_loader import load_repo_configs
from irc.data.freshness import require_fresh_ingest
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.memo.auditor import audit_blocks_publish
from irc.memo.diagnostics import (
    compose_execution_drift_lines,
    compose_fx_qdii_lines,
    compose_role_bucket_banner,
)
from irc.memo.aliases import build_alias_maps
from irc.memo.evidence_pool import build_evidence_pool
from irc.memo.citation_selector import select_citations
from irc.memo.macro_pillar import (
    MacroSnapshot,
    ThemeReportRef,
    evidence_by_source_key,
    render_gold_evidence_body,
    render_macro_section_body,
)
from irc.memo.picks_table import (
    PickRow,
    _format_trigger_status_compact,
    render_failure_sections,
    render_picks_table,
)
from irc.memo.template import MemoInputs
from irc.memo.pipeline import extract_evidence_cutoff, run_memo_pipeline
from irc.opportunity.types import ThesisEvidence
from irc.commands.opportunity_cmd import (
    _is_canonical_out_dir,
    _resolve_enforce_mode,
    _write_citation_audit_shadow_log,
)
from irc.decision.completeness import MIN_BUY_COMPLETENESS
from irc.decision.gates import (
    compute_blocking_reasons,
    compute_decision_status,
    derive_venue_status,
)
from irc.decision.live_inputs import read_live_decision_inputs
from irc.decision.sizing import suggest_tranche_pct
from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT
from irc.scoring.qdii_premium import _QDII_ASSET_CLASSES
from irc.memo.numeric_audit import find_missing_pick_citations, find_uncited_conclusions
from irc.opportunity.citation_map import build_cited_map, build_constituent_cited_map


_DEFAULT_TIMELINESS_NOTE = (
    "数据时效：行情/净值通常为T+1；具体日期见证据池。"
)


# Anti-fabrication fallback used by §2 only when gold_regime.json is missing
# its macro_snapshots / theme_refs payload (or both are empty). Audit P1
# (2026-05-20) flagged the prior "实际利率与美元走向是黄金定价的主导变量"
# phrasing as a deterministic causal claim. Softened text frames real-yield/
# USD as one set of reference variables among several (地缘 + 央行购金) and
# defers A-share valuation specifics to the evidence pool.
_MACRO_SUMMARY = (
    "实际利率与美元走向通常被视为黄金定价的重要参考变量之一；"
    "地缘风险、央行购金行为等其他因素同样可能对金价产生显著影响。"
    "本期 A 股宽基估值数据采集不完整：仅对证据池已覆盖的标的作有限披露，"
    "其余宽基指数估值百分位未采集，相关宏观判断存在数据缺口，"
    "不要自行编造、补足或外推。"
)


def _snapshots_from_gold(gold: dict) -> tuple[MacroSnapshot, ...]:
    """Rebuild `MacroSnapshot`s from the dict form written by `gold_cmd`."""
    out: list[MacroSnapshot] = []
    for d in gold.get("macro_snapshots") or []:
        try:
            out.append(MacroSnapshot(
                series_id=str(d["series_id"]),
                display_name=str(d["display_name"]),
                value=float(d["value"]),
                unit=str(d.get("unit", "")),
                date=str(d["date"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def _theme_refs_from_gold(gold: dict) -> tuple[ThemeReportRef, ...]:
    out: list[ThemeReportRef] = []
    for d in gold.get("theme_refs") or []:
        try:
            out.append(ThemeReportRef(
                theme=str(d["theme"]),
                display_name=str(d["display_name"]),
                summary=str(d.get("summary") or ""),
                date=str(d["date"]),
            ))
        except (KeyError, TypeError):
            continue
    return tuple(out)


def _format_threshold(threshold: object) -> str:
    """Render a trigger threshold for display.

    Numeric thresholds (real_yield, VIX, weekly_return) render with default
    ``f"{n}"`` formatting to preserve sign and decimals; categorical string
    thresholds (valuation_state, heat_state) render verbatim. A missing
    threshold (yaml key absent → ``None``) is shown as ``"（未设阈值）"``
    rather than the literal string ``"None"``.
    """
    if threshold is None:
        return "（未设阈值）"
    if isinstance(threshold, bool):
        return str(threshold)
    if isinstance(threshold, (int, float)):
        return f"{threshold}"
    return str(threshold)


def _format_trigger(trigger: dict) -> str:
    """Render a single trigger as `name (data_field comparator threshold)`.

    Audit P4 (2026-05-20) flagged the prior bare-code form
    ('real_yield_low，weekly_drawdown_4pct') as ambiguous — executors had
    no comparator or threshold without consulting trade_plan.yaml.
    """
    name = str(trigger.get("name", "") or "")
    data_field = str(trigger.get("data_field", "") or "")
    comparator = str(trigger.get("comparator", "") or "")
    threshold = _format_threshold(trigger.get("threshold"))
    if not (name and data_field and comparator):
        return name or "无"
    return f"{name} ({data_field} {comparator} {threshold})"


def _format_suspended_venue_note(venue_note: str) -> str:
    if "proxy via" in venue_note:
        return "venue mismatch；无可用代理渠道，暂缓执行，待渠道开通后重新评估"
    return venue_note


def _compose_execution_lines(
    trades: list[dict],
    opportunity_rows: list[dict],
    extra_names: dict[str, str] | None = None,
    require_opportunity_row: bool = False,
) -> tuple[str, ...]:
    """Build one bullet per trade row for memo section 7.

    Sourcing data deterministically from the trade plan removes the
    LLM-fillable placeholder that left section 7 empty in 2026-05-18.
    Each bullet carries: id+name, target weight cap, buy_method,
    granularity, fully-qualified triggers (or "无"), and venue_note.

    Multi-trigger trades render with a 满足任一 (any-of / OR) marker —
    triggers in the plan are independent by construction
    (see ``src/irc/trades/triggers.py:emit_triggers_for_trade``).

    In production memo rendering, ``require_opportunity_row=True`` marks trade
    targets missing from opportunity_report.json as suspended instead of
    emitting actionable triggers from incomplete opportunity data.
    """
    extra_names = extra_names or {}
    name_by_id = {str(r.get("instrument_id")): r.get("name_cn", "")
                  for r in opportunity_rows}
    lines: list[str] = []
    for t in trades:
        iid = str(t.get("target", ""))
        resolved_iid = iid if iid in name_by_id else _strip_venue_suffix(iid)
        name = str(name_by_id.get(resolved_iid) or extra_names.get(iid) or "")
        weight = float(t.get("target_weight") or 0.0)
        label = f"{iid} {name}".strip()
        venue_note = str(t.get("venue_note", ""))
        if require_opportunity_row and resolved_iid not in name_by_id:
            suspended_venue = _format_suspended_venue_note(venue_note)
            lines.append(
                f"**{label}** | 目标权重 ≤ {weight*100:.1f}% | "
                f"暂缓执行·待机会数据补充 | 渠道 {suspended_venue}"
            )
            continue
        raw_triggers = list(t.get("triggers") or [])
        formatted = [_format_trigger(tr) for tr in raw_triggers]
        formatted = [f for f in formatted if f]
        if not formatted:
            triggers = "无"
        elif len(formatted) == 1:
            triggers = formatted[0]
        else:
            triggers = "满足任一：" + "；".join(formatted)
        bullet = (
            f"**{label}** | 目标权重 ≤ {weight*100:.1f}% | "
            f"建仓方式 {t.get('buy_method', 'unknown')} ({t.get('granularity', 'default')}) | "
            f"触发 {triggers} | 渠道 {venue_note}"
        )
        lines.append(bullet)
    return tuple(lines)


def _compose_risk_notes(cutoff: str | None) -> tuple[str, ...]:
    """Return the memo risk-notes tuple, with the data-timeliness bullet
    rewritten when we know the evidence-pool cutoff date.

    When ``cutoff`` is non-None, the bullet calls out the exact ISO date the
    snapshot was taken plus the typical lag patterns (境内 T+1, QDII 跨境结算
    更长). When None, fall back to today's boilerplate so the path is
    backwards-compatible.
    """
    if cutoff is None:
        timeliness = _DEFAULT_TIMELINESS_NOTE
    else:
        timeliness = (
            f"数据时效：证据池截止 {cutoff}（akshare 净值/价格快照）；"
            "境内净值/价格通常滞后 1 个交易日，QDII 跨境结算可能滞后更长，"
            "节假日/停牌将进一步延长。所有数值不代表实时市场状态，执行前须自行核实。"
        )
    return (
        "实际利率风险：在部分历史时期，实际利率上行曾对金价形成压制，"
        "但该关系并非稳定规律，不构成对未来走势的预测；"
        "本期实际利率数据缺失，该风险敞口暂无法量化。",
        "估值压力：在部分历史时期，宽基ETF估值百分位偏高时曾出现较大回撤，"
        "但该关系并非稳定规律，不构成对未来走势的预测；执行前须自行核实风险承受能力。",
        "渠道与汇率：venue_compatible=false的标的不可执行，仅观察。",
        timeliness,
    )


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _latest_file(root: Path, pattern: str) -> Path | None:
    candidates = sorted(root.glob(pattern))
    return candidates[-1] if candidates else None


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_discovery_diagnostics(out_dir: Path) -> list[dict]:
    """Best-effort read of discovery_diagnostics.csv for the role-bucket
    banner (item 010, 2026-05-19). Returns an empty list when the file
    is absent or unreadable so memo can still render."""
    import csv

    path = out_dir / "discovery_diagnostics.csv"
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return []


def _names_from_watchlist_csv(out_dir: Path) -> dict[str, str]:
    """Best-effort `instrument_id → name_cn` map from discovered_watchlist.csv.

    Used as a fallback when opportunity_report.json is absent (e.g. earlier
    pipeline run skipped the opportunity stage) so picks-table rows never
    render their id in the 名称 column.
    """
    import csv

    path = out_dir / "discovered_watchlist.csv"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return {
                str(row.get("instrument_id") or ""): str(row.get("name_cn") or "")
                for row in csv.DictReader(f)
                if row.get("instrument_id") and row.get("name_cn")
            }
    except (OSError, csv.Error):
        return {}


def _names_from_universes(bundle) -> dict[str, str]:
    """`instrument_id → name_cn` from configured universes.

    Covers venue proxies (e.g. ``cmb_paper_gold`` → ``招商银行账户金``) that
    appear in trade_plan.yaml as targets but are never scored, so they
    don't appear in scoring.json or opportunity_report.json.
    """
    names: dict[str, str] = {}
    for uni in (
        getattr(bundle, "universe_qdii_us", None),
        getattr(bundle, "universe_qdii_hk", None),
        getattr(bundle, "universe_cn_funds", None),
        getattr(bundle, "universe_gold", None),
    ):
        if uni is None:
            continue
        for instr in getattr(uni, "instruments", ()) or ():
            iid = getattr(instr, "instrument_id", None)
            name = getattr(instr, "name_cn", None)
            if iid and name and iid not in names:
                names[iid] = name
    return names


def _derive_tldr_lines(
    gold: dict,
    alloc: dict,
    opportunity: dict,
    plan: dict,
    pick_rows: list | tuple = (),
) -> tuple[str, ...]:
    summary = opportunity.get("summary") or {}
    n_core = summary.get("core_dca_count", 0)
    n_watch = summary.get("small_watch_count", 0)
    n_pause = summary.get("pause_wait_count", 0)
    actionable = [str(r.instrument_id) for r in pick_rows
                  if getattr(r, "decision_status", "") == "actionable_buy"]
    if actionable:
        banner = (
            f"✅ 候选可执行：{', '.join(actionable)}"
            "（仍需人工核对 venue/溢价/合规）。"
        )
    else:
        banner = "⚪ 本周无候选可执行（详见 §5 决策列与 §6 风险提示）。"
    lines: list[str] = [banner]
    lines.append(
        f"黄金：regime={gold.get('regime', '?')}，zone={gold.get('zone', '?')}，"
        f"仓位倾斜={alloc.get('gold_tilt', '?')}。"
    )
    lines.append(f"建仓模式：{plan.get('mode') or 'build'}（按节奏定投，不一次性投入）。")
    lines.append(
        f"机会面：core_dca={n_core}，small_watch={n_watch}，pause_wait={n_pause}。"
    )
    return tuple(lines)


_VENUE_SUFFIX_RE = re.compile(r"\.[A-Z]{2,3}$")


def _strip_venue_suffix(iid: str) -> str:
    """Strip a trailing `.SH` / `.SZ` / `.OF` / `.HK` venue suffix if present,
    and a single leading letter prefix (e.g. `A` in `A510300.SH` → `510300`).

    Conservative: only strips suffixes matching `\\.[A-Z]{2,3}$` and a leading
    single uppercase letter followed by digits. Canonical iids in
    `config/universe/*.yaml` are 6-digit bare codes (e.g. `510300`, `005827`)
    and venue proxies like `cmb_paper_gold` carry no dot — both pass through
    unchanged.
    """
    stripped = _VENUE_SUFFIX_RE.sub("", iid)
    # Strip leading single letter prefix (A-share proxy: A510300 → 510300).
    if len(stripped) >= 2 and stripped[0].isalpha() and stripped[1:].isdigit():
        return stripped[1:]
    return stripped


def _format_pick_reason(op: dict) -> str:
    reason = (op.get("opportunity_reason") or "").split(" | ")[0].replace(
        "\n", " ").strip()
    valuation = str(op.get("valuation_state") or "")
    heat = str(op.get("heat_state") or "")
    if valuation in {"expensive", "very_expensive"} or heat in {"crowded", "overheated"}:
        return f"估值={valuation or 'unknown'}、热度={heat or 'unknown'}，暂停加仓；详见本节补充披露。"
    return reason or "—"


def _evidence_from_dict(d: dict) -> ThesisEvidence:
    """Deprecated shim — delegates to ThesisEvidence.from_dict."""
    return ThesisEvidence.from_dict(d)


def _reconstruct_opportunity_rows(
    rebuilt_op_rows: list[dict],
) -> tuple:
    """Reconstruct OpportunityRow dataclasses from rebuilt dict-form rows
    for the alias-builder. Publishable rows only (evidence_gaps == ()).

    Best-effort — fields not strictly needed by build_alias_maps default
    to neutral placeholders so the function never raises on a partial dict.
    """
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    rows: list = []
    for r in rebuilt_op_rows:
        if (r.get("evidence_gaps") or ()):
            continue
        constituent_analyses = tuple(
            ConstituentAnalysis(
                symbol=c.get("symbol", ""),
                name_cn=c.get("name_cn", ""),
                weight_pct=float(c.get("weight_pct", 0.0)),
                evidence=tuple(
                    ThesisEvidence.from_dict(e) for e in c.get("evidence", [])
                ),
                failure_reasons=tuple(c.get("failure_reasons", ())),
                one_line_view=c.get("one_line_view", ""),
                audit_errors=tuple(c.get("audit_errors", ())),
            )
            for c in (r.get("constituent_analyses") or [])
            if c.get("symbol")
        )
        lt = LookthroughTarget(
            kind=r.get("lookthrough_kind", "broad_index"),
            key=r.get("lookthrough_key", r["instrument_id"]),
            display_cn=r.get("lookthrough_target", ""),
            provider_symbol="",
        )
        rows.append(OpportunityRow(
            instrument_id=r["instrument_id"],
            name_cn=r.get("name_cn", ""),
            asset_class=r.get("asset_class", ""),
            theme=r.get("theme"),
            lookthrough_target=lt,
            valuation_state=r.get("valuation_state", "evidence_insufficient"),
            heat_state=r.get("heat_state", "evidence_insufficient"),
            thesis_state=r.get("thesis_state", "evidence_insufficient"),
            product_quality_state=r.get("product_quality_state", "evidence_insufficient"),
            opportunity_state=r.get("opportunity_state", "small_watch"),
            opportunity_reason=r.get("opportunity_reason", ""),
            evidence_gaps=tuple(r.get("evidence_gaps", ())),
            thesis_evidence=r["thesis_evidence"]
                if isinstance(r.get("thesis_evidence"), tuple)
                else tuple(r.get("thesis_evidence") or ()),
            constituent_analyses=constituent_analyses,
        ))
    return tuple(rows)


def _decision_status_for_pick(
    score_row: dict,
    trade: dict | None,
    op_row: dict,
    *,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
) -> str:
    """Compute the decision-readiness verdict for a single pick row.

    Mirrors the logic `decision_cmd` runs over the full universe, restricted
    to the fields the memo stage already has in scope. Three favourable
    assumptions are baked in here (and only here) because memo runs AFTER
    plan/opportunity and BEFORE decision in the pipeline:

      • pipeline_halted=False   — memo wouldn't be running otherwise.
      • target_weight_valid=True — allocate would have failed earlier.
      • evidence_status="evidence_linked" — memo always emits evidence.

    qdii_premium_unknown fires for QDII rows where premium is None;
    qdii_premium_too_high fires when premium is known and exceeds threshold.
    The two codes are mutually exclusive (mirrors decide_row logic).
    """
    _MEMO_BUY_ACTIONS = {"buy_candidate", "strong_buy_candidate"}
    score_action = str(score_row.get("action", "watch"))
    asset_class = str(op_row.get("asset_class") or score_row.get("asset_class") or "")
    completeness_raw = score_row.get("data_completeness", 1.0)
    try:
        completeness = float(completeness_raw) if completeness_raw is not None else 1.0
    except (TypeError, ValueError):
        completeness = 0.0
    venue_status = derive_venue_status(trade)
    raw_premium = score_row.get("qdii_premium_pct")
    try:
        premium_value = float(raw_premium) if raw_premium is not None else None
    except (TypeError, ValueError):
        premium_value = None
    is_qdii_buy = (
        asset_class in _QDII_ASSET_CLASSES
        and score_action in _MEMO_BUY_ACTIONS
    )
    qdii_premium_unknown = is_qdii_buy and premium_value is None
    qdii_premium_too_high = (
        is_qdii_buy
        and premium_value is not None
        and premium_value > qdii_max_premium_pct
    )
    blocking = compute_blocking_reasons(
        pipeline_halted=False,
        completeness=completeness,
        completeness_threshold=MIN_BUY_COMPLETENESS,
        target_weight_valid=True,
        venue_status=venue_status,
        evidence_status="evidence_linked",
        score_action=score_action,
        qdii_premium_unknown=qdii_premium_unknown,
        qdii_premium_too_high=qdii_premium_too_high,
    )
    allocation_selected = trade is not None
    return compute_decision_status(score_action, blocking, allocation_selected)

def _build_pick_rows(
    trades: list[dict],
    opportunity: dict,
    scoring: dict,
    extra_names: dict[str, str] | None = None,
    *,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
    build_mode: str = "build",
    macro_snapshot: dict[str, float] | None = None,
    weekly_return_by_id: dict[str, float] | None = None,
) -> tuple[list[PickRow], list[dict], list[dict]]:
    """Classify each trade target into one of three buckets:

    - `pick_rows`: trade target whose opportunity row has `evidence_gaps == ()`.
    - `absent_targets`: trade target whose iid is NOT in `opportunity["rows"]`
      after venue-proxy suffix strip. Memo renders an absence sub-block.
    - `gapped_targets`: trade target whose op row has `evidence_gaps != ()`.
      Memo renders a gap sub-block (no conclusions emitted).

    Each `gapped_targets` entry is enriched with `_matched_row` so the renderer
    can reach the op row's name and gap labels.
    """
    rows_list = opportunity.get("rows") or []
    rows_by_id = {r["instrument_id"]: r for r in rows_list}
    score_by_id = {s["instrument_id"]: s for s in (scoring.get("scores") or [])}
    extra_names = extra_names or {}
    macro_snapshot = macro_snapshot or {}
    weekly_return_by_id = weekly_return_by_id or {}

    pick_rows: list[PickRow] = []
    absent: list[dict] = []
    gapped: list[dict] = []
    seen: set[str] = set()

    for t in trades:
        iid_raw = t.get("target")
        if not iid_raw or iid_raw in seen:
            continue
        seen.add(iid_raw)

        # Resolution: direct hit, else venue-proxy suffix strip, else absent.
        op = rows_by_id.get(iid_raw) or rows_by_id.get(_strip_venue_suffix(iid_raw))
        if op is None:
            absent.append(t)
            continue
        if op.get("evidence_gaps"):
            gapped.append({**t, "_matched_row": op})
            continue

        # Eligible: build PickRow with citations.
        raw_evidence = tuple(
            _evidence_from_dict(d) for d in (op.get("thesis_evidence") or [])
        )
        citations = select_citations(raw_evidence, cap=3)

        sc = score_by_id.get(iid_raw) or {}
        reason = _format_pick_reason(op)
        opp_state = op.get("opportunity_state", "small_watch")
        dca = {"core_dca": "normal_dca", "small_watch": "slow_dca",
               "pause_wait": "pause_dca", "exclude": "do_not_buy"}.get(
                   opp_state, "slow_dca")
        score = t.get("composite_score")
        if score is None:
            score = sc.get("composite_score") or 0.0
        name = op.get("name_cn") or extra_names.get(str(iid_raw)) or iid_raw
        decision_status = _decision_status_for_pick(
            sc, t, op, qdii_max_premium_pct=qdii_max_premium_pct
        )
        target_weight = float(t.get("target_weight") or 0.0)
        tranche_cap_pct = suggest_tranche_pct(target_weight, build_mode)
        trigger_status = _format_trigger_status_compact(
            tuple(t.get("triggers") or ()),
            macro_snapshot,
            weekly_return_by_id,
            str(iid_raw),
        )
        pick_rows.append(PickRow(
            instrument_id=iid_raw,
            name_cn=name,
            asset_class=op.get("asset_class") or t.get("asset_class", ""),
            role=t.get("role") or "",
            target_weight=target_weight,
            composite_score=float(score),
            opportunity_state=opp_state,
            dca_action=dca,
            risk_action="none",
            one_line_reason=reason,
            valuation_state=op.get("valuation_state", ""),
            venue_note=str(t.get("venue_note", "")),
            citations=citations,
            decision_status=decision_status,
            tranche_cap_pct=tranche_cap_pct,
            trigger_status=trigger_status,
        ))

    return pick_rows, absent, gapped


def run_memo(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="memo"):
        print("ERROR: memo stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    bundle = load_repo_configs(root)
    today = _today()

    scoring_path = root / "outputs" / today / "scoring.json"
    if not scoring_path.exists():
        p = _latest_file(root, "outputs/*/scoring.json")
        if p is None:
            print("ERROR: no scoring.json; run `irc score` first.")
            return 2
        scoring_path = p

    out_today = scoring_path.parent  # use same date dir as scoring

    scoring = json.loads(scoring_path.read_text(encoding="utf-8"))
    gold = _load_json(out_today / "gold_regime.json")
    alloc = _load_yaml(out_today / "proposed_allocation.yaml")
    plan = _load_yaml(out_today / "trade_plan.yaml")
    opportunity = _load_json(out_today / "opportunity_report.json")

    trades = list(plan.get("trades") or [])
    # Resilience: when opportunity_report.json is missing (e.g. an older
    # pipeline run that skipped the opportunity stage) or when the trade
    # target is a venue proxy that doesn't exist in opportunity rows,
    # fall back to universe-config / watchlist-CSV names so the 名称
    # column never renders an instrument id verbatim.
    fallback_names = {
        **_names_from_watchlist_csv(out_today),
        **_names_from_universes(bundle),
    }
    try:
        _qdii_max = bundle.discovery.hard_filters.qdii_max_premium_pct
    except Exception:
        _qdii_max = QDII_MAX_PREMIUM_DEFAULT
    # Item 003: feed the same (macro_snapshot, weekly_return_by_id) into the
    # picks-table renderer that the Decision Sheet uses, so 单次定投上限 +
    # 触发状态 columns can compute live trigger states. Graceful degrade:
    # read_live_decision_inputs returns ({}, {}) when data/local.duckdb is
    # absent — renderer then shows em-dash.
    trade_ids = {str(t.get("target")) for t in trades if t.get("target")}
    macro_snapshot, weekly_return_by_id = read_live_decision_inputs(root, trade_ids)
    build_mode = str(plan.get("mode") or "build")
    pick_rows, absent_targets, gapped_targets = _build_pick_rows(
        trades, opportunity, scoring, fallback_names,
        qdii_max_premium_pct=_qdii_max,
        build_mode=build_mode,
        macro_snapshot=macro_snapshot,
        weekly_return_by_id=weekly_return_by_id,
    )
    picks_table_md = render_picks_table(pick_rows) + render_failure_sections(
        absent_targets, gapped_targets, fallback_names,
    )

    gold_regime = {
        "regime": gold.get("regime", "unknown"),
        "zone": gold.get("zone", "unknown"),
        "tilt": alloc.get("gold_tilt", "neutral"),
    }

    # Item 016 — macro evidence pillar. The gold stage now emits a
    # `macro_snapshots`, `theme_refs`, and `evidence` payload in
    # `gold_regime.json`. Memo §2 and §3 surface this verbatim with the
    # exact citation_ids that the publishable universe already contains
    # (gold_regime.json["evidence"] is part of the citation universe per
    # `tests/integration/_publishable_set_helper.py`).
    macro_snapshots = _snapshots_from_gold(gold)
    theme_refs = _theme_refs_from_gold(gold)
    macro_evidence = tuple(
        ThesisEvidence.from_dict(d) for d in (gold.get("evidence") or [])
    )
    macro_evidence_by_source = evidence_by_source_key(macro_evidence)
    macro_summary_md = render_macro_section_body(
        macro_snapshots, theme_refs, macro_evidence_by_source,
    )
    gold_evidence_md = render_gold_evidence_body(
        macro_snapshots, theme_refs, macro_evidence_by_source,
    )
    # Item 007 D1a: reconstruct ThesisEvidence dataclasses from the JSON
    # dict form so build_evidence_pool can pass them through select_citations
    # without a third-call-site _evidence_from_dict copy.
    raw_op_rows = list(opportunity.get("rows") or [])
    rebuilt_op_rows: list[dict] = []
    for row in raw_op_rows:
        ev_tuple = tuple(
            ThesisEvidence.from_dict(d) for d in (row.get("thesis_evidence") or [])
        )
        rebuilt_op_rows.append({**row, "thesis_evidence": ev_tuple})

    raw_ref_pool = build_evidence_pool(
        opportunity_rows=rebuilt_op_rows,
        scoring_rows=list(scoring.get("scores") or []),
        plan_trades=trades,
        gold_regime=gold_regime,
        macro_evidence=macro_evidence,
    )

    # Item 007 D1c: build alias maps from publishable rows. Item 009's
    # find_uncited_conclusions consumes these via the audit-gate wiring;
    # item 007 ships only the producer side. Wrap the call so an
    # `InstrumentAliasCollisionError` surfaces as a user-readable ERROR
    # line (not a Python traceback) — production data has occasionally
    # produced duplicate `name_cn` strings across share-class variants of
    # the same parent fund family.
    from irc.memo.aliases import InstrumentAliasCollisionError
    publishable_rows_for_aliases = _reconstruct_opportunity_rows(rebuilt_op_rows)
    try:
        _instrument_aliases, _constituent_aliases = build_alias_maps(
            publishable_rows_for_aliases,
        )
    except InstrumentAliasCollisionError as exc:
        print(
            f"ERROR: alias-builder collision while preparing memo: {exc}\n"
            "Investigate opportunity_report.json for duplicate `name_cn` "
            "or shared `lookthrough_target.key` across publishable rows."
        )
        return 1

    tldr = _derive_tldr_lines(gold, alloc, opportunity, plan, pick_rows=pick_rows)

    cutoff = extract_evidence_cutoff(raw_ref_pool)
    risk_notes = _compose_risk_notes(cutoff)
    # Deterministic diagnostics injected into risk_notes so the LLM can't
    # omit them and the audit gate can verify presence
    # (adversarial-review items 013, 014).
    cash_target_center = float(
        getattr(bundle.preferences.asset_class_targets.get("cash", None), "center", 0.05) or 0.05
    )
    drift_lines = compose_execution_drift_lines(alloc, cash_target_center)
    if drift_lines:
        risk_notes = tuple(drift_lines) + risk_notes
    usd_tol_pair: tuple[float, float] | None = None
    _usd_tol = getattr(bundle.preferences.currency_tolerance, "usd", None)
    if _usd_tol and len(_usd_tol) >= 2:
        usd_tol_pair = (float(_usd_tol[0]), float(_usd_tol[1]))
    fx_policy = getattr(getattr(bundle.preferences, "fx_hedge", None), "policy", None)
    fx_lines = compose_fx_qdii_lines(alloc, usd_tol_pair, fx_hedge_policy=fx_policy)
    if fx_lines:
        risk_notes = tuple(fx_lines) + risk_notes
    # Role-bucket banner (item 010): adversarial review §E.
    diag_rows = _load_discovery_diagnostics(out_today)
    role_lines = compose_role_bucket_banner(diag_rows)
    if role_lines:
        risk_notes = tuple(role_lines) + risk_notes
    execution_lines = _compose_execution_lines(
        trades, opportunity.get("rows") or [],
        extra_names=fallback_names,
        require_opportunity_row=True,
    )

    # §2: prefer the dynamic macro_summary_md (carries real values + refs);
    # fall back to the legacy static text when gold_regime emitted no data.
    macro_summary_text = (
        macro_summary_md.strip() if macro_summary_md.strip() else _MACRO_SUMMARY
    )
    inputs = MemoInputs(
        date_str=today,
        gold_regime=gold.get("regime", "unknown"),
        gold_zone=gold.get("zone", "unknown"),
        gold_tilt=alloc.get("gold_tilt", "neutral"),
        allocation_mode=plan.get("mode", "unknown"),
        macro_summary=macro_summary_text,
        top_picks=tuple(r.instrument_id for r in pick_rows),
        risk_notes=risk_notes,
        tldr_lines=tldr,
        picks_table_md=picks_table_md,
        execution_lines=execution_lines,
        gold_evidence_md=gold_evidence_md,
    )

    synth_route = resolve_route("memo_synthesis", bundle.llm)
    audit_route = resolve_route("memo_audit", bundle.llm)
    output = run_memo_pipeline(inputs, raw_ref_pool, synth_route, audit_route)

    out_dir = root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    # Audit-blocking gate (item 009, 2026-05-19): if the auditor returned
    # 审核未通过 OR P-tier 高风险 findings, refuse to publish memo.md;
    # write memo_blocked.md instead and exit non-zero.
    blocked, block_reasons = audit_blocks_publish(output.audit_notes)
    atomic_write_text(out_dir / "memo_audit.txt", output.audit_notes)
    atomic_write_text(out_dir / "memo_traceability.json", json.dumps({
        "n_refs_provided": output.traceability["n_refs_provided"],
        "n_refs_quoted_verbatim": output.traceability["n_refs_quoted_verbatim"],
        "n_refs": output.traceability["n_refs"],
    }, indent=2))
    if blocked:
        block_header = (
            "# 备忘录发布被审核拒绝\n\n"
            "审核报告含 P-tier 高风险项或 '审核未通过' 明确否决；"
            "下面是被拒草稿，仅供修订使用，请勿直接对外发布。\n\n"
            "## 阻断原因\n\n"
            + "\n".join(f"- {r}" for r in block_reasons)
            + "\n\n---\n\n"
        )
        atomic_write_text(out_dir / "memo_blocked.md", block_header + output.draft)
        # Remove a stale memo.md from a prior good run so it can't be
        # mistaken for the current verdict.
        memo_path = out_dir / "memo.md"
        if memo_path.exists():
            memo_path.unlink()
        print(
            "memo BLOCKED: audit gate flagged the draft — "
            f"see {out_dir/'memo_blocked.md'} and {out_dir/'memo_audit.txt'}"
        )
        for reason in block_reasons:
            print(f"  - {reason}")
        return 2

    # ── Item 009 — memo-stage citation gate ───────────────────────────────────
    # Q7 + F1 lock: use out_dir (write path), NOT out_today (read path).
    publishable_rows_for_gate = _reconstruct_opportunity_rows(rebuilt_op_rows)
    cited_map_for_gate = build_cited_map(tuple(publishable_rows_for_gate))
    constituent_cited_for_gate = build_constituent_cited_map(
        tuple(publishable_rows_for_gate),
    )
    pick_findings = find_missing_pick_citations(pick_rows, cited_map_for_gate)
    prose_findings = find_uncited_conclusions(
        output.draft,
        cited_map=cited_map_for_gate,
        instrument_aliases=_instrument_aliases,
        constituent_aliases=_constituent_aliases,
        constituent_cited_map=constituent_cited_for_gate,
        strict_empty_alias_check=bool(rebuilt_op_rows),
    )
    memo_findings = pick_findings + prose_findings
    enforce_mode = _resolve_enforce_mode(out_dir, today)

    # RMW the shared shadow log: read whatever the opportunity stage wrote,
    # overlay memo_findings + summary.
    audit_path = out_dir / "citation_audit.json"
    if audit_path.exists():
        shadow: dict = json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        # Fallback when memo runs standalone (no opportunity stage). Compute
        # `canonical_path` from the actual `out_dir` instead of hardcoding
        # False — production runs always have a canonical out_dir, so the
        # previous False default mislabeled the shadow log (code-reviewer P1.5).
        shadow = {
            "run_date": today,
            "enforce_mode": enforce_mode,
            "canonical_path": _is_canonical_out_dir(out_dir),
            "out_dir": str(out_dir.resolve()),
            "opportunity_findings": [],
            "constituent_findings": [],
            "discipline_findings": [],
            "memo_findings": [],
            "summary": {"total": 0, "blocking": False},
        }
    shadow["memo_findings"] = [
        {
            "instrument_id": f.instrument_id,
            "kind": f.kind,
            "prose_excerpt": f.prose_excerpt,
            "evidence_excerpt": f.evidence_excerpt,
        }
        for f in memo_findings
    ]
    shadow["summary"]["total"] = (
        len(shadow.get("opportunity_findings", []))
        + len(shadow.get("constituent_findings", []))
        + len(shadow.get("discipline_findings", []))
        + len(memo_findings)
    )
    shadow["summary"]["blocking"] = bool(shadow.get("constituent_findings", [])) or (
        enforce_mode == "block"
        and bool(
            shadow.get("opportunity_findings", [])
            or shadow.get("discipline_findings", [])
            or memo_findings
        )
    )
    # Wrap shadow log write so an OSError doesn't suppress the gate's
    # subsequent block/warn decision (silent-failure P0.2 parallel to the
    # opportunity-stage wrapper).
    try:
        _write_citation_audit_shadow_log(out_dir, shadow)
    except OSError as exc:
        print(
            f"WARN: citation_audit.json write failed ({exc!r}); "
            "memo gate verdict still applies",
            file=sys.stderr,
        )

    if memo_findings and enforce_mode == "block":
        reasons = [f"{f.instrument_id}:{f.kind}" for f in memo_findings]
        block_header = (
            "# 备忘录发布被引用审核拒绝\n\n"
            "Item 009 citation gate flagged missing citations on picks/prose; "
            "see citation_audit.json for details.\n\n"
            "## 阻断原因\n\n"
            + "\n".join(f"- {r}" for r in reasons)
            + "\n\n---\n\n"
        )
        atomic_write_text(out_dir / "memo_blocked.md", block_header + output.draft)
        memo_path = out_dir / "memo.md"
        if memo_path.exists():
            memo_path.unlink()
        print(
            "memo BLOCKED by citation gate: see "
            f"{out_dir / 'memo_blocked.md'} and {out_dir / 'citation_audit.json'}"
        )
        for r in reasons:
            print(f"  - {r}")
        return 2
    if memo_findings and enforce_mode == "warn":
        print(
            "WARN citation-audit (memo): "
            + "; ".join(f"{f.instrument_id}:{f.kind}" for f in memo_findings),
            file=sys.stderr,
        )

    atomic_write_text(out_dir / "memo.md", output.published_draft)
    blocked_path = out_dir / "memo_blocked.md"
    if blocked_path.exists():
        blocked_path.unlink()
    print(
        f"memo OK: {output.traceability['n_refs_quoted_verbatim']}/"
        f"{output.traceability['n_refs_provided']} refs quoted verbatim "
        f"→ {out_dir/'memo.md'}"
    )
    return 0
