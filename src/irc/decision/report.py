from __future__ import annotations

from typing import Any

from irc.decision.gates import decide_row, target_weights_are_valid


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
    coverage = float(memo_traceability.get("coverage_ratio", 0.0))
    rows = _build_rows(scoring, selected_ids, trades_by_target, target_weight_valid, pipeline_halted, coverage)
    blocking_reasons = _overall_blocking_reasons(rows, pipeline_halted, target_weight_valid)
    return {
        "date": date,
        "overall_status": "blocked" if blocking_reasons else "ok",
        "blocking_reasons": blocking_reasons,
        "summary": _summary(rows),
        "rows": rows,
    }


def render_decision_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Decision Report {report['date']}",
        "",
        "## Verdict",
        "",
        _verdict_section(report["overall_status"]),
        "",
        "## Why Blocked",
        "",
    ]
    lines.extend(_blocking_section(report.get("blocking_reasons", [])))
    lines.extend(["", "## Instrument Decisions", ""])
    lines.extend(_table_section(report.get("rows", [])))
    lines.append("")
    return "\n".join(lines)


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


def _verdict_section(overall_status: str) -> str:
    return (
        "No buy/sell decision is supported today."
        if overall_status == "blocked"
        else "At least one instrument passed decision-readiness gates. Review manually before execution."
    )


def _blocking_section(blocking_reasons: list[str]) -> list[str]:
    if blocking_reasons:
        return [f"- {reason}" for reason in blocking_reasons]
    else:
        return ["- No system-level blocking reason detected."]


def _table_section(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Instrument | Status | Score Action | Conviction | Completeness | Venue | Next Step |",
        "|---|---|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {instrument_id} | {decision_status} | {score_action} | {conviction} | {data_completeness:.2f} | {venue_status} | {next_step} |".format(**row)
        )
    return lines
