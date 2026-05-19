from __future__ import annotations

from typing import Any

from irc.decision.gates import decide_row, target_weights_are_valid

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
) -> dict[str, Any]:
    target_weight_valid = target_weights_are_valid(allocation)
    selected_ids = {str(row.get("instrument_id")) for row in allocation.get("selected_instruments", [])}
    trades_by_target = {str(row.get("target")): row for row in trade_plan.get("trades", [])}
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
    )
    blocking_reasons = _overall_blocking_reasons(rows, pipeline_halted, target_weight_valid)
    return {
        "date": date,
        "overall_status": "blocked" if blocking_reasons else "ok",
        "blocking_reasons": blocking_reasons,
        "summary": _summary(rows),
        "rows": rows,
        # pipeline_incomplete: True when >50% of score rows lack an 'action' field,
        # signalling a corrupt/partial scoring run. Forces overall_status to 'blocked'.
        "pipeline_incomplete": pipeline_incomplete,
    }


def render_decision_markdown(report: dict[str, Any]) -> str:
    is_blocked = report["overall_status"] == "blocked"
    rows: list[dict[str, Any]] = report.get("rows", [])
    lines = [
        f"# Decision Report {report['date']}",
        "",
        "## Verdict",
        "",
        _render_verdict(report["overall_status"], report.get("summary", {})),
        "",
        "## Why Blocked" if is_blocked else "## Gates Passed",
        "",
    ]
    lines.extend(_blocking_section(report.get("blocking_reasons", [])))
    lines.append("")
    # Three reader-first sections replace the single 100-row instrument
    # table. JSON output is unchanged. See
    # docs/2026-05-18-fix-memo-audit/items/011-spec.md.
    lines.extend(_actionable_buys_section(rows))
    lines.append("")
    lines.extend(_blocked_fixable_section(rows))
    lines.append("")
    lines.extend(_watch_collapsed_section(rows))
    lines.append("")
    lines.extend(_glossary_section())
    lines.append("")
    return "\n".join(lines)


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
    return {
        "actionable_buy_count": statuses.count("actionable_buy"),
        "watch_count": statuses.count("watch_only"),
        "avoid_count": statuses.count("avoid"),
        "blocked_count": statuses.count("blocked"),
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
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score in scoring.get("scores", []):
        iid = str(score.get("instrument_id"))
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

_BLOCKING_REASON_LABEL: dict[str, str] = {
    "data_incomplete": "Data incomplete (required financial metrics missing)",
    "venue_blocked": "Venue blocked (no compatible account or proxy)",
    "target_weights_invalid": "Target weights invalid (allocation normalization broken)",
    "pipeline_halted": "Pipeline halted (an upstream stage failed)",
    "memo_narrative_only": "Memo narrative only (no verbatim evidence)",
    "score_avoid": "Score action is avoid",
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
}


def _actionable_buys_section(rows: list[dict[str, Any]]) -> list[str]:
    actionable = [r for r in rows if r.get("decision_status") == "actionable_buy"]
    out = ["## Actionable buys", ""]
    if not actionable:
        out.append("（无）")
        return out
    out.append("| Instrument | Score Action | Conviction | Completeness | Venue | Next Step |")
    out.append("|---|---|---|---:|---|---|")
    for row in actionable:
        out.append(
            "| {instrument_id} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {next_step} |".format(
                instrument_id=_md(row["instrument_id"]),
                score_action=_md(row["score_action"]),
                conviction=_md(row["conviction"]),
                data_completeness=row["data_completeness"],
                venue_status=row["venue_status"],
                next_step=_md(row["next_step"]),
            )
        )
    return out


def _blocked_fixable_section(rows: list[dict[str, Any]]) -> list[str]:
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
            "| Instrument | Score Action | Conviction | Completeness | Venue |",
            "|---|---|---|---:|---|",
        ])
        for row in group:
            out.append(
                "| {instrument_id} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} |".format(
                    instrument_id=_md(row["instrument_id"]),
                    score_action=_md(row["score_action"]),
                    conviction=_md(row["conviction"]),
                    data_completeness=row["data_completeness"],
                    venue_status=row["venue_status"],
                )
            )
        remediation = _BLOCKING_REMEDIATION.get(reason, "Investigate the root cause.")
        out.extend(["", f"_Remediation:_ {remediation}", ""])
    return out


def _watch_collapsed_section(rows: list[dict[str, Any]]) -> list[str]:
    watch_rows = [r for r in rows if r.get("decision_status") == "watch_only"]
    out = ["## Watch (no trade)", ""]
    if not watch_rows:
        out.append(f"0 个标的暂未触发交易决策。")
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
    out.append("| Instrument | Score Action | Conviction | Completeness | Venue | Why watch |")
    out.append("|---|---|---|---:|---|---|")
    for row in watch_rows:
        out.append(
            "| {instrument_id} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {watch_reason} |".format(
                instrument_id=_md(row["instrument_id"]),
                score_action=_md(row["score_action"]),
                conviction=_md(row["conviction"]),
                data_completeness=row["data_completeness"],
                venue_status=row["venue_status"],
                watch_reason=_watch_reason_cell(row),
            )
        )
    out.extend(["", "</details>"])
    return out


def _watch_reason_cell(row: dict[str, Any]) -> str:
    """Render the ``Why watch`` column. Empty string when the row isn't watch_only
    or watch_reason is missing — keeps non-watch rows visually clean.
    """
    reason = row.get("watch_reason")
    if not reason:
        return ""
    return _WATCH_REASON_LABEL.get(reason, str(reason))


