from __future__ import annotations

from typing import Any

from irc.decision.gates import decide_row, target_weights_are_valid
from irc.decision.sizing import (
    TriggerSpec,
    format_why_when_line,
    resolve_trigger_current_value,
    suggest_tranche_pct,
)
from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT

_PIPELINE_INCOMPLETE_THRESHOLD = 0.5


def compose_decision_report(
    date: str,
    scoring: dict[str, Any],
    allocation: dict[str, Any],
    trade_plan: dict[str, Any],
    memo_traceability: dict[str, Any],
    pipeline_halted: bool,
    *,
    venue_requirements_by_id: dict[str, list[str]] | None = None,
    available_venues: list[str] | tuple[str, ...] | set[str] | None = None,
    proxies_by_id: dict[str, str] | None = None,
    names_by_id: dict[str, str] | None = None,
    audit_summary: dict[str, Any] | None = None,
    opportunity_published_ids: set[str] | None = None,
    macro_snapshot: dict[str, float] | None = None,
    weekly_return_by_id: dict[str, float] | None = None,
    opportunity_state_by_id: dict[str, dict[str, Any]] | None = None,
    qdii_max_premium_pct: float | None = None,
) -> dict[str, Any]:
    target_weight_valid = target_weights_are_valid(allocation)
    selected_ids = {str(row.get("instrument_id")) for row in allocation.get("selected_instruments", [])}
    trades_by_target = {str(row.get("target")): row for row in trade_plan.get("trades", [])}
    target_weight_by_id: dict[str, float] = {
        str(row.get("instrument_id")): float(row.get("target_weight") or 0.0)
        for row in allocation.get("selected_instruments", [])
    }
    role_by_id: dict[str, str] = {
        str(row.get("target")): str(row.get("role") or "")
        for row in trade_plan.get("trades", [])
        if row.get("role")
    }
    # Compute coverage from the verbatim-count schema.
    # • Key absent → legacy on-disk file (old coverage_ratio schema); do not block.
    # • n_refs_provided == 0 → no evidence was available; vacuous truth, do not block.
    # • n_refs_quoted_verbatim > 0 → at least one ref quoted; coverage = 1.0.
    # • n_refs_provided > 0 but n_quoted == 0 → narrative only; coverage = 0.0.
    if "n_refs_quoted_verbatim" not in memo_traceability:
        coverage = 1.0  # legacy schema — cannot evaluate, do not penalise
    else:
        _n_provided = int(memo_traceability.get("n_refs_provided") or 0)
        _n_quoted = int(memo_traceability.get("n_refs_quoted_verbatim") or 0)
        coverage = 1.0 if (_n_provided == 0 or _n_quoted > 0) else 0.0
    threshold = (
        QDII_MAX_PREMIUM_DEFAULT
        if qdii_max_premium_pct is None
        else qdii_max_premium_pct
    )
    scores = scoring.get("scores", [])
    pipeline_incomplete = _scores_missing_action(scores)
    if pipeline_incomplete:
        pipeline_halted = True
    rows = _build_rows(
        scoring, selected_ids, trades_by_target, target_weight_valid,
        pipeline_halted, coverage,
        venue_requirements_by_id=venue_requirements_by_id or {},
        available_venues=available_venues,
        proxies_by_id=proxies_by_id or {},
        names_by_id=names_by_id or {},
        target_weight_by_id=target_weight_by_id,
        role_by_id=role_by_id,
        # Set of instrument_ids that survived to opportunity_report.json.
        # None = unknown (legacy callers without an opportunity input);
        # an empty set = "nothing published" (treat all as excluded).
        opportunity_published_ids=opportunity_published_ids,
        trade_plan_targets={str(t.get("target")) for t in trade_plan.get("trades", [])},
        qdii_max_premium_pct=threshold,
        opportunity_state_by_id=opportunity_state_by_id or {},
    )
    blocking_reasons = _overall_blocking_reasons(rows, pipeline_halted, target_weight_valid)
    proxy_coverage = _build_proxy_coverage(trade_plan)
    execution_drift = _execution_drift(allocation)
    return {
        "date": date,
        "overall_status": "blocked" if blocking_reasons else "ok",
        "blocking_reasons": blocking_reasons,
        "summary": _summary(rows),
        "rows": rows,
        # pipeline_incomplete: True when >50% of score rows lack an 'action' field,
        # signalling a corrupt/partial scoring run. Forces overall_status to 'blocked'.
        "pipeline_incomplete": pipeline_incomplete,
        # Asset classes that have at least one proxy-fulfilled trade with non-zero
        # target_weight. Used by the markdown renderer to surface "role already met"
        # banners next to blocked rows whose class is already covered.
        "proxy_coverage": proxy_coverage,
        # Banner-trigger payload when the allocation parked >= 5pp of NAV in cash
        # beyond its target — the layperson's view never showed this; the trust-check
        # priority #3 demanded it surface here, not just in memo.md §4.
        "execution_drift": execution_drift,
        # Structured summary of memo_audit.txt: verdict + P1 count + first 10
        # findings. None when the caller did not pass one in (back-compat).
        "audit_summary": audit_summary,
        # Decision Sheet inputs — passed through to the renderer for the
        # per-instrument why/when/how-much cards. Optional; empty when the
        # caller (legacy paths, tests) hasn't gathered live macro + return
        # snapshots.
        "trade_plan_trades": list(trade_plan.get("trades") or []),
        "build_mode": str(trade_plan.get("mode") or "build"),
        "macro_snapshot": macro_snapshot or {},
        "weekly_return_by_id": weekly_return_by_id or {},
        "opportunity_state_by_id": opportunity_state_by_id or {},
    }


_EXECUTION_DRIFT_THRESHOLD = 0.05


def _execution_drift(allocation: dict[str, Any]) -> dict[str, float] | None:
    target_weights = allocation.get("target_weights_per_class") or {}
    diagnostics = allocation.get("diagnostics") or {}
    cash_target = float(target_weights.get("cash") or 0.0)
    cash_residual = float(diagnostics.get("cash_residual_weight") or 0.0)
    drift = round(max(0.0, cash_residual - cash_target), 6)
    if drift < _EXECUTION_DRIFT_THRESHOLD:
        return None
    return {
        "drift_pct": drift,
        "cash_target": cash_target,
        "cash_residual": cash_residual,
    }


def _build_proxy_coverage(trade_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    coverage: dict[str, list[dict[str, Any]]] = {}
    for trade in trade_plan.get("trades", []):
        proxy_id = trade.get("proxy_id")
        if not proxy_id:
            continue
        target_weight = float(trade.get("target_weight") or 0.0)
        if target_weight <= 0:
            continue
        asset_class = str(trade.get("asset_class") or "")
        if not asset_class:
            continue
        coverage.setdefault(asset_class, []).append({
            "target": str(trade.get("target") or ""),
            "target_weight": target_weight,
            "proxy_id": str(proxy_id),
        })
    return coverage


def render_decision_markdown(report: dict[str, Any]) -> str:
    is_blocked = report["overall_status"] == "blocked"
    rows: list[dict[str, Any]] = report.get("rows", [])
    lines = [
        f"# Decision Report {report['date']}",
        "",
    ]
    lines.extend(_todays_only_action_section(rows))
    lines.extend([
        "## Verdict",
        "",
        _render_verdict(report["overall_status"], report.get("summary", {})),
        "",
    ])
    lines.extend(_execution_drift_banner(report.get("execution_drift")))
    lines.extend(_audit_summary_banner(report.get("audit_summary")))
    lines.extend([
        "## Why Blocked" if is_blocked else "## Gates Passed",
        "",
    ])
    lines.extend(_blocking_section(report.get("blocking_reasons", [])))
    lines.append("")
    # Three reader-first sections replace the single 100-row instrument
    # table. JSON output is unchanged. See
    # docs/2026-05-18-fix-memo-audit/items/011-spec.md.
    lines.extend(_actionable_buys_section(rows))
    lines.append("")
    lines.extend(_decision_sheet_section(
        rows,
        trades=report.get("trade_plan_trades") or [],
        build_mode=report.get("build_mode") or "build",
        macro_snapshot=report.get("macro_snapshot") or {},
        weekly_return_by_id=report.get("weekly_return_by_id") or {},
        opportunity_state_by_id=report.get("opportunity_state_by_id") or {},
    ))
    lines.append("")
    lines.extend(_holdings_action_section(rows))
    lines.append("")
    lines.extend(_blocked_fixable_section(rows, report.get("proxy_coverage", {})))
    lines.append("")
    lines.extend(_watch_collapsed_section(rows))
    lines.append("")
    lines.extend(_glossary_section())
    lines.append("")
    return "\n".join(lines)


def _todays_only_action_section(rows: list[dict[str, Any]]) -> list[str]:
    """Render the layperson-first headline. Shown above Verdict so the
    reader's first impression is "this is what to do today", not "here's
    a 100-row table"."""
    actionable = [r for r in rows if r.get("decision_status") == "actionable_buy"]
    out = ["## 今日唯一行动 / Today's only action", ""]
    if not actionable:
        out.extend([
            "⏸️ 本周无可执行标的 — 详见下方 Verdict 阻断原因。",
            "",
        ])
        return out
    for row in actionable:
        iid = _md(row["instrument_id"])
        name = row.get("instrument_name") or ""
        name_part = f" {_md(name)}" if name else ""
        role = row.get("role") or ""
        role_part = _md(role) if role else "—"
        target_pct = float(row.get("target_weight") or 0.0) * 100
        out.append(
            f"✅ **{iid}{name_part}** — {role_part}, target {target_pct:.1f}%."
        )
    out.append("")
    return out


def _audit_summary_banner(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []
    verdict = str(summary.get("verdict") or "未知")
    p1_count = int(summary.get("p1_count") or 0)
    if verdict == "审核通过" and p1_count == 0:
        return []
    return [
        f"> 🛑 **合规审核未达标 / Memo compliance audit failed**: 审核结论 "
        f"\"{verdict}\", 含 P1 必改项 {p1_count} 条 (见 memo_audit.txt). "
        f"本周决策应视 memo §5 为草稿，**不应**直接执行。",
        "",
    ]


def _execution_drift_banner(drift: dict[str, float] | None) -> list[str]:
    if not drift:
        return []
    drift_pp = drift["drift_pct"] * 100
    residual_pp = drift["cash_residual"] * 100
    target_pp = drift["cash_target"] * 100
    return [
        f"> ⚠️ **执行漂移提醒 / Execution drift**: 现金残余权重 "
        f"{residual_pp:.0f}% > 目标 {target_pp:.0f}% (drift +{drift_pp:.0f}pp). "
        f"多个目标未填仓 — 详见 memo.md §4 与 trade_plan.yaml. "
        f"仅做提醒，不阻断本周决策。",
        "",
    ]


def _glossary_section() -> list[str]:
    return [
        "## 术语速查 (Glossary)",
        "",
        "- **buy_candidate / 候选买入**: 评分模型给出的买入候选，*尚未*等同于"
        "\"立即执行\"。执行前需人工核对 venue、溢价、合规审核。",
        "- **actionable_buy**: 候选买入 ∩ 资产配置选中 ∩ 通过所有阻断闸口。"
        "仍需人工核对。",
        "- **core_dca / 正常定投**: 当前评估状态适合按月常规定投。",
        "- **pause_wait / 暂停加仓**: 当前估值/事件层面建议本周不加仓，"
        "等待下次重评。",
        "- **venue_status=direct**: 你的主账户支持直接下单（不代表已开通 "
        "QDII 权限；首次交易前请在券商 App 内确认）。",
        "- **venue_status=blocked_no_proxy**: 当前账户无法直接交易，"
        "且未配置代理 (proxy)。",
        "- **venue_status=unknown**: 系统未确认 venue 状态，"
        "请勿据此判断可执行性。",
        "- **data_completeness**: 必需字段的*填充率*（0–1），**不等于**"
        "信心或胜率。1.00 仅表示字段齐全，*不代表*该笔交易高确定性。",
        "- **watch_reason=scored watch**: 评分本身给出 watch 行动。",
        "- **watch_reason=not_selected_by_allocation**: "
        "评分尚可，但资产配置未选中。",
        "- **watch_reason=venue_unknown**: venue 数据缺失。",
    ]


def _render_verdict(overall_status: str, summary: dict[str, int]) -> str:
    if overall_status == "blocked":
        return "No buy/sell decision is supported today."
    if summary.get("actionable_buy_count", 0) == 0:
        return "System gates are clear but no instrument has reached actionable_buy status. Review per-row statuses."
    return "At least one instrument passed all decision-readiness gates. Review manually before execution."


def _scores_missing_action(scores: list[dict[str, Any]]) -> bool:
    """Return True when >50% of scores lack an 'action' field (pipeline ran without scoring)."""
    if not scores:
        return False
    missing = sum(1 for s in scores if s.get("action") is None)
    return missing / len(scores) > _PIPELINE_INCOMPLETE_THRESHOLD


_BUY_ACTIONS = frozenset({"buy_candidate", "strong_buy_candidate"})


def _overall_blocking_reasons(rows: list[dict[str, Any]], pipeline_halted: bool, target_weight_valid: bool) -> list[str]:
    reasons: list[str] = []
    if pipeline_halted:
        reasons.append("pipeline_halted")
    if not target_weight_valid:
        reasons.append("target_weights_invalid")
    if any(row.get("memo_evidence_status") == "narrative_only" for row in rows):
        reasons.append("memo_narrative_only")
    # data_incomplete is a system-level blocker only when an *actionable buy
    # candidate* is missing required data. A watch-only or avoid row with
    # missing fields is a watchlist-quality issue, not a portfolio-decision
    # blocker — surfacing it as a system blocker stops the whole report even
    # when no buy decision actually depends on the missing field.
    if any(
        "data_incomplete" in row.get("blocking_reasons", [])
        and row.get("score_action") in _BUY_ACTIONS
        for row in rows
    ):
        reasons.append("data_incomplete")
    return reasons


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [row.get("decision_status") for row in rows]
    actions = [row.get("portfolio_action") for row in rows]
    return {
        "actionable_buy_count": statuses.count("actionable_buy"),
        "watch_count": statuses.count("watch_only"),
        "avoid_count": statuses.count("avoid"),
        "blocked_count": statuses.count("blocked"),
        # Item 001 (ADR 0015 §3): additive sell/review counts keyed off
        # portfolio_action. NO sell_count — item 002 sums trim+exit itself.
        "trim_count": actions.count("trim_review"),
        "exit_count": actions.count("exit_review"),
        "review_count": actions.count("review"),
    }


def _build_rows(
    scoring: dict[str, Any],
    selected_ids: set[str],
    trades_by_target: dict[str, Any],
    target_weight_valid: bool,
    pipeline_halted: bool,
    coverage: float,
    *,
    venue_requirements_by_id: dict[str, list[str]],
    available_venues: list[str] | tuple[str, ...] | set[str] | None,
    proxies_by_id: dict[str, str],
    names_by_id: dict[str, str],
    target_weight_by_id: dict[str, float],
    role_by_id: dict[str, str],
    opportunity_published_ids: set[str] | None,
    trade_plan_targets: set[str],
    opportunity_state_by_id: dict[str, dict[str, Any]] | None = None,
    qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score in scoring.get("scores", []):
        iid = str(score.get("instrument_id"))
        # An instrument is "opportunity_excluded" only when it has a trade
        # plan entry (so we expected it to publish) AND it did not survive
        # to opportunity_report.json. Legacy / non-opportunity-aware callers
        # pass opportunity_published_ids=None — preserve old behavior then.
        excluded = (
            opportunity_published_ids is not None
            and iid in trade_plan_targets
            and iid not in opportunity_published_ids
        )
        opp = (opportunity_state_by_id or {}).get(iid, {})
        rows.append(decide_row(
            score=score,
            allocation_selected=iid in selected_ids,
            target_weight_valid=target_weight_valid,
            trade=trades_by_target.get(iid),
            pipeline_halted=pipeline_halted,
            memo_traceability_coverage=coverage,
            venue_required=venue_requirements_by_id.get(iid),
            available_venues=available_venues,
            proxy_id=proxies_by_id.get(iid),
            instrument_name=names_by_id.get(iid),
            target_weight=target_weight_by_id.get(iid, 0.0),
            role=role_by_id.get(iid, ""),
            excluded_from_opportunity=excluded,
            qdii_max_premium_pct=qdii_max_premium_pct,
            risk_action=str(opp.get("risk_action", "none")),
            dca_action=opp.get("dca_action"),
            portfolio_weight=opp.get("portfolio_weight"),
            is_holding=bool(opp.get("is_holding", False)),
        ))
    return rows


def _blocking_section(blocking_reasons: list[str]) -> list[str]:
    if blocking_reasons:
        return [f"- {reason}" for reason in blocking_reasons]
    else:
        return ["- No system-level blocking reason detected."]


def _md(s: object) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


_WATCH_REASON_LABEL: dict[str, str] = {
    "score_watch": "scored watch",
    "not_selected_by_allocation": "not selected by allocation",
    "venue_unknown": "venue unknown",
}

# Bilingual labels for score_action. The trust-check doc (B2) noted the same
# row reads bullish in English (`buy_candidate`) and bearish in Chinese
# (`暂停加仓` from discipline_report). Pairing the English machine label with
# a Chinese gloss in-place forces the reader to see both sides at once.
_SCORE_ACTION_LABEL: dict[str, str] = {
    "strong_buy_candidate": "strong_buy_candidate / 重点候选买入",
    "buy_candidate": "buy_candidate / 候选买入",
    "watch": "watch / 观察",
    "avoid": "avoid / 回避",
    "strong_avoid": "strong_avoid / 重点回避",
}


def _score_action_cell(row: dict[str, Any]) -> str:
    action = row.get("score_action")
    if not action:
        return ""
    return _md(_SCORE_ACTION_LABEL.get(action, str(action)))

_BLOCKING_REASON_LABEL: dict[str, str] = {
    "data_incomplete": "Data incomplete (required financial metrics missing)",
    "venue_blocked": "Venue blocked (no compatible account or proxy)",
    "target_weights_invalid": "Target weights invalid (allocation normalization broken)",
    "pipeline_halted": "Pipeline halted (an upstream stage failed)",
    "memo_narrative_only": "Memo narrative only (no verbatim evidence)",
    "score_avoid": "Score action is avoid",
    "qdii_premium_unknown": "QDII premium-to-NAV / FX status not collected",
    "qdii_premium_too_high": "QDII premium-to-NAV above threshold",
    "opportunity_excluded": "Excluded from opportunity_report (Policy B / dual-coverage gate)",
}

_BLOCKING_REMEDIATION: dict[str, str] = {
    "data_incomplete":
        "Repair the required financial metrics in the data layer and rerun scoring.",
    "venue_blocked":
        "Add a compatible account venue, register a proxy in the universe, or accept the position is not reachable.",
    "target_weights_invalid":
        "Fix allocation normalization before using target weights.",
    "pipeline_halted":
        "Fix the halted stage and rerun the pipeline.",
    "memo_narrative_only":
        "Improve memo traceability before treating narrative claims as evidence.",
    "score_avoid":
        "Scoring action is avoid — review the underlying factor scores.",
    "qdii_premium_unknown":
        "AkShare returned no premium snapshot for this QDII symbol. "
        "Refresh fund_etf_spot_em data or wait for the next ingest. "
        "QDII feeders frequently trade 5–15% above NAV — premium must "
        "be known before treating as actionable.",
    "qdii_premium_too_high":
        "QDII premium-to-NAV exceeds the configured ceiling "
        "(qdii_max_premium_pct in config/discovery.yaml; default 5%). "
        "Wait for the premium to normalise or use an alternative venue.",
    "opportunity_excluded":
        "The instrument scored well enough to enter trade_plan but Policy B / "
        "the dual-coverage gate rejected it at opportunity_write. Common cause: "
        "constituents are foreign-listed (HK/US) and per-holding filings aren't "
        "available. See `rejections.json` for the per-instrument gap codes.",
}


def _decision_sheet_section(
    rows: list[dict[str, Any]],
    *,
    trades: list[dict[str, Any]],
    build_mode: str,
    macro_snapshot: dict[str, float],
    weekly_return_by_id: dict[str, float],
    opportunity_state_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Render the per-instrument 'why / when / how-much' cards.

    One card per actionable_buy row (the visible decision set). Each card
    shows: role + target cap, the trade plan's triggers WITH current
    values resolved against `macro_snapshot` + `weekly_return_by_id`, and
    a suggested per-tranche % cap derived from build_mode.

    Empty when no actionable rows exist or no trade entries match the
    actionable ids.
    """
    actionable = [r for r in rows if r.get("decision_status") == "actionable_buy"]
    out: list[str] = ["## 决策面板 / Per-pick decision summary", ""]
    if not actionable:
        out.append("（无 actionable_buy 行，跳过本节。）")
        return out
    trades_by_target = {str(t.get("target")): t for t in trades}
    out.append(
        f"_构建模式: `{build_mode}`. `build` = 累积至目标的 4 个等分 tranche；"
        "实际行动只在触发条件满足时执行，否则本期保持 0 仓位。_"
    )
    out.append("")
    for row in actionable:
        iid = str(row.get("instrument_id"))
        name = row.get("instrument_name") or ""
        role = row.get("role") or "—"
        target_weight = float(row.get("target_weight") or 0.0)
        per_tranche = suggest_tranche_pct(target_weight, build_mode)
        out.append(f"### ✅ {_md(iid)} {_md(name)}")
        out.append(f"- **Role / 角色**: `{role}`")
        out.append(
            f"- **Target cap / 权重上限**: {target_weight * 100:.2f}% of total portfolio"
        )
        out.append(
            f"- **Per-tranche cap / 单次定投上限**: "
            f"≤ {per_tranche * 100:.2f}% of total portfolio "
            f"({build_mode} mode → target ÷ 4 tranches)"
        )
        # Triggers from trade_plan
        trade = trades_by_target.get(iid)
        triggers = (trade or {}).get("triggers") or []
        if not triggers:
            out.append("- **Trigger / 触发条件**: 无 — 本期可考虑常规定投（参考备忘录第7节）.")
        else:
            out.append("- **Trigger / 触发条件**:")
            for trig in triggers:
                spec = TriggerSpec(
                    name=str(trig.get("name") or "trigger"),
                    comparator=str(trig.get("comparator") or "<="),
                    threshold=float(trig.get("threshold") or 0.0),
                )
                current, unit = resolve_trigger_current_value(
                    trig, iid, macro_snapshot, weekly_return_by_id,
                )
                out.append(f"  - {format_why_when_line(spec, current, unit)}")
        # Why YES / Why NOT / Why WHEN — prefer the opportunity_report's
        # operational state (valuation/heat/thesis/quality) over the generic
        # 'gates are clear' reason because the former is what the system
        # actually believes about the row TODAY.
        opp = (opportunity_state_by_id or {}).get(iid) or {}
        if opp:
            valuation = opp.get("valuation_state") or "unknown"
            heat = opp.get("heat_state") or "unknown"
            thesis = opp.get("thesis_state") or "unknown"
            quality = opp.get("product_quality_state") or "unknown"
            opp_state = opp.get("opportunity_state") or "unknown"
            opp_reason = (opp.get("opportunity_reason") or "").split("|", 1)[0].strip()
            out.append(
                f"- **Why (operational) / 理由**: opportunity_state=`{opp_state}` · "
                f"valuation=`{valuation}` · heat=`{heat}` · thesis=`{thesis}` · "
                f"quality=`{quality}`."
            )
            if opp_reason:
                out.append(f"  - 备注: {opp_reason}")
        else:
            reason = row.get("reason") or ""
            if reason:
                out.append(f"- **Why / 理由**: {reason}")
        out.append("")
    return out


def _actionable_buys_section(rows: list[dict[str, Any]]) -> list[str]:
    actionable = [r for r in rows if r.get("decision_status") == "actionable_buy"]
    out = ["## Actionable buys", ""]
    if not actionable:
        out.append("（无）")
        return out
    out.append("| Instrument | Name | Score Action | Conviction | Completeness | Venue | Next Step |")
    out.append("|---|---|---|---|---:|---|---|")
    for row in actionable:
        out.append(
            "| {instrument_id} | {instrument_name} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {next_step} |".format(
                instrument_id=_md(row["instrument_id"]),
                instrument_name=_name_cell(row),
                score_action=_score_action_cell(row),
                conviction=_md(row["conviction"]),
                data_completeness=row["data_completeness"],
                venue_status=row["venue_status"],
                next_step=_md(row["next_step"]),
            )
        )
    return out


_HOLDINGS_ACTION_SET = frozenset({"trim_review", "exit_review", "review"})


def _holdings_action_section(rows: list[dict[str, Any]]) -> list[str]:
    """Render the 持仓行动 / Sell·Trim·Review table.

    One row per HELD instrument carrying a trim/exit/review portfolio_action
    (ADR 0015 §2: the sell branches are is_holding-gated, so is_holding is
    True here by construction; the explicit filter is belt-and-suspenders for
    legacy/hand-built rows). Empty-state line `（无持仓调整建议）` when none.
    Current % is COST-BASIS weight (OQ3).
    """
    held = [
        r for r in rows
        if r.get("portfolio_action") in _HOLDINGS_ACTION_SET and r.get("is_holding")
    ]
    out = ["## 持仓行动 / Sell · Trim · Review", ""]
    if not held:
        out.extend(["（无持仓调整建议）", ""])
        return out
    out.append(
        "| Instrument | Name | Action | Current % (cost-basis) | Target % | Δ (pp) | Why |"
    )
    out.append("|---|---|---|---:|---:|---:|---|")
    for r in held:
        current_pct = float(r.get("current_weight") or 0.0) * 100
        target_pct = float(r.get("target_weight") or 0.0) * 100
        delta_pp = float(r.get("weight_delta") or 0.0) * 100
        out.append(
            "| {iid} | {name} | {action} | {cur:.1f} | {tgt:.1f} | {delta:+.1f} | {why} |".format(
                iid=_md(r["instrument_id"]),
                name=_name_cell(r),
                action=_md(r.get("portfolio_action") or ""),
                cur=current_pct,
                tgt=target_pct,
                delta=delta_pp,
                why=_md(r.get("reason") or _score_action_cell(r)),
            )
        )
    out.append("")
    return out


def _blocked_fixable_section(
    rows: list[dict[str, Any]],
    proxy_coverage: dict[str, list[dict[str, Any]]],
) -> list[str]:
    blocked = [r for r in rows if r.get("decision_status") == "blocked"]
    out = ["## Blocked — fixable today", ""]
    if not blocked:
        out.append("（无）")
        return out
    # Group by first blocking_reason.
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in blocked:
        reasons = r.get("blocking_reasons") or ["unknown"]
        groups.setdefault(reasons[0], []).append(r)
    for reason, group in groups.items():
        label = _BLOCKING_REASON_LABEL.get(reason, reason)
        out.extend([
            f"### Blocked by: {label}",
            "",
            "| Instrument | Name | Score Action | Conviction | Completeness | Venue |",
            "|---|---|---|---|---:|---|",
        ])
        for row in group:
            out.append(
                "| {instrument_id} | {instrument_name} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} |".format(
                    instrument_id=_md(row["instrument_id"]),
                    instrument_name=_name_cell(row),
                    score_action=_score_action_cell(row),
                    conviction=_md(row["conviction"]),
                    data_completeness=row["data_completeness"],
                    venue_status=row["venue_status"],
                )
            )
        remediation = _BLOCKING_REMEDIATION.get(reason, "Investigate the root cause.")
        out.extend(["", f"_Remediation:_ {remediation}"])
        out.extend(_proxy_coverage_banners(group, proxy_coverage))
        out.append("")
    return out


def _proxy_coverage_banners(
    group: list[dict[str, Any]],
    proxy_coverage: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """For each asset_class in the blocked group that has a proxy filling the
    role, emit a one-line "Role already met" note so the reader knows the
    blocked rows are redundant."""
    if not proxy_coverage:
        return []
    classes_in_group: dict[str, int] = {}
    for row in group:
        cls = str(row.get("asset_class") or "")
        if cls and cls in proxy_coverage:
            classes_in_group[cls] = classes_in_group.get(cls, 0) + 1
    lines: list[str] = []
    for cls, count in classes_in_group.items():
        entries = proxy_coverage[cls]
        descriptions = ", ".join(
            f"{e['proxy_id']} ({e['target_weight'] * 100:.0f}% target_weight)"
            for e in entries
        )
        lines.append(
            f"_✓ Role already met for {cls}: {descriptions} — "
            f"the {count} blocked row(s) above in this class are redundant; "
            f"no action required._"
        )
    return lines


def _watch_collapsed_section(rows: list[dict[str, Any]]) -> list[str]:
    watch_rows = [r for r in rows if r.get("decision_status") == "watch_only"]
    out = ["## Watch (no trade)", ""]
    if not watch_rows:
        out.append("0 个标的暂未触发交易决策。")
        return out
    by_reason: dict[str, int] = {}
    for r in watch_rows:
        by_reason[r.get("watch_reason") or "unknown"] = by_reason.get(r.get("watch_reason") or "unknown", 0) + 1
    out.append(f"{len(watch_rows)} 个标的暂未触发交易决策。")
    out.append("")
    for reason_key in ("score_watch", "not_selected_by_allocation", "venue_unknown"):
        cnt = by_reason.get(reason_key, 0)
        if cnt:
            label = _WATCH_REASON_LABEL[reason_key]
            out.append(f"- {label}: {cnt}")
    out.extend(["", "<details><summary>展开所有 watch 标的</summary>", "", ])
    out.append("| Instrument | Name | Score Action | Conviction | Completeness | Venue | Why watch |")
    out.append("|---|---|---|---|---:|---|---|")
    for row in watch_rows:
        out.append(
            "| {instrument_id} | {instrument_name} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {watch_reason} |".format(
                instrument_id=_md(row["instrument_id"]),
                instrument_name=_name_cell(row),
                score_action=_score_action_cell(row),
                conviction=_md(row["conviction"]),
                data_completeness=row["data_completeness"],
                venue_status=row["venue_status"],
                watch_reason=_watch_reason_cell(row),
            )
        )
    out.extend(["", "</details>"])
    return out


def _name_cell(row: dict[str, Any]) -> str:
    """Render the ``Name`` column. Empty string when name is missing — keeps
    rows clean (avoids a literal ``None`` token in the rendered table).
    """
    name = row.get("instrument_name")
    if not name:
        return ""
    return _md(name)


def _watch_reason_cell(row: dict[str, Any]) -> str:
    """Render the ``Why watch`` column. Empty string when the row isn't watch_only
    or watch_reason is missing — keeps non-watch rows visually clean.
    """
    reason = row.get("watch_reason")
    if not reason:
        return ""
    return _WATCH_REASON_LABEL.get(reason, str(reason))


