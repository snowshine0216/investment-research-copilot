from __future__ import annotations

from typing import Any


def _format_instrument_evidence(
    op_row: dict[str, Any],
    score_row: dict[str, Any] | None,
    trade: dict[str, Any] | None,
) -> str:
    iid = op_row.get("instrument_id", "")
    name = op_row.get("name_cn", "")
    parts: list[str] = [f"[{iid} {name}]"]
    parts.append(
        "状态=" + "/".join([
            op_row.get("valuation_state", "?"),
            op_row.get("heat_state", "?"),
            op_row.get("thesis_state", "?"),
            op_row.get("product_quality_state", "?"),
        ])
    )
    parts.append(f"opportunity={op_row.get('opportunity_state', '?')}")
    if score_row is not None:
        cs = score_row.get("composite_score")
        if cs is not None:
            parts.append(f"score={cs:.1f}")
        fb = score_row.get("factor_breakdown") or {}
        for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news"):
            sub = fb.get(k) or {}
            if "score" in sub:
                parts.append(f"{k}={sub['score']:.0f}")
    if trade is not None:
        tw = trade.get("target_weight")
        if tw is not None:
            parts.append(f"target_weight={tw * 100:.1f}%")
        role = trade.get("role")
        if role:
            parts.append(f"role={role}")
    reason = op_row.get("opportunity_reason") or ""
    if reason:
        parts.append("reason=" + reason.split(" | ")[0])
    return " ".join(parts)


def build_evidence_pool(
    *,
    opportunity_rows: list[dict[str, Any]],
    scoring_rows: list[dict[str, Any]],
    plan_trades: list[dict[str, Any]],
    gold_regime: dict[str, Any] | None = None,
) -> list[str]:
    """Return a flat list of evidence strings to feed the LLM.

    Each instrument contributes one compact line of numeric facts. The gold
    regime contributes one line if provided. Order: gold regime first,
    then instruments in plan_trades order, then remaining opportunity rows.
    """
    score_by_id = {s.get("instrument_id"): s for s in scoring_rows}
    op_by_id = {r.get("instrument_id"): r for r in opportunity_rows}

    pool: list[str] = []
    if gold_regime:
        pool.append(
            f"[gold] regime={gold_regime.get('regime', '?')} "
            f"zone={gold_regime.get('zone', '?')} "
            f"tilt={gold_regime.get('tilt', '?')}"
        )

    seen_ids: set[str] = set()
    for t in plan_trades:
        iid = t.get("target")
        if not iid or iid in seen_ids:
            continue
        seen_ids.add(iid)
        op = op_by_id.get(iid)
        if op is None:
            continue
        pool.append(_format_instrument_evidence(op, score_by_id.get(iid), t))

    for op in opportunity_rows:
        iid = op.get("instrument_id")
        if iid in seen_ids:
            continue
        # Watchlist-only instruments (small_watch, not in plan_trades) are excluded
        # from the evidence pool: they lack trade context and would dilute the
        # actionable picks. They appear in the opportunity report instead.
        if op.get("opportunity_state") == "small_watch":
            continue
        seen_ids.add(iid)
        pool.append(_format_instrument_evidence(op, score_by_id.get(iid), None))

    return pool
