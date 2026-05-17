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
    rows = _build_rows(scoring, selected_ids, trades_by_target, target_weight_valid, pipeline_halted, coverage)
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
    lines.extend(["", "## Instrument Decisions", ""])
    lines.extend(_table_section(report.get("rows", [])))
    lines.append("")
    return "\n".join(lines)


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


def _overall_blocking_reasons(rows: list[dict[str, Any]], pipeline_halted: bool, target_weight_valid: bool) -> list[str]:
    reasons: list[str] = []
    if pipeline_halted:
        reasons.append("pipeline_halted")
    if not target_weight_valid:
        reasons.append("target_weights_invalid")
    if any(row.get("memo_evidence_status") == "narrative_only" for row in rows):
        reasons.append("memo_narrative_only")
    if any("data_incomplete" in row.get("blocking_reasons", []) for row in rows):
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
) -> list[dict[str, Any]]:
    return [
        decide_row(
            score=score,
            allocation_selected=str(score.get("instrument_id")) in selected_ids,
            target_weight_valid=target_weight_valid,
            trade=trades_by_target.get(str(score.get("instrument_id"))),
            pipeline_halted=pipeline_halted,
            memo_traceability_coverage=coverage,
        )
        for score in scoring.get("scores", [])
    ]


def _blocking_section(blocking_reasons: list[str]) -> list[str]:
    if blocking_reasons:
        return [f"- {reason}" for reason in blocking_reasons]
    else:
        return ["- No system-level blocking reason detected."]


def _md(s: object) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _table_section(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Instrument | Status | Score Action | Conviction | Completeness | Venue | Next Step |",
        "|---|---|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {instrument_id} | {decision_status} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {next_step} |".format(
                instrument_id=_md(row["instrument_id"]),
                decision_status=row["decision_status"],
                score_action=_md(row["score_action"]),
                conviction=_md(row["conviction"]),
                data_completeness=row["data_completeness"],
                venue_status=row["venue_status"],
                next_step=_md(row["next_step"]),
            )
        )
    return lines
