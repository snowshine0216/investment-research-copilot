from __future__ import annotations

from dataclasses import asdict
from typing import Any

import yaml

from irc.opportunity.types import (
    DisciplineRow,
    OpportunityRow,
    ThesisCard,
)


def _row_to_dict(row: OpportunityRow) -> dict[str, Any]:
    return {
        "instrument_id": row.instrument_id,
        "name_cn": row.name_cn,
        "asset_class": row.asset_class,
        "theme": row.theme,
        "lookthrough_target": row.lookthrough_target.display_cn,
        "lookthrough_kind": row.lookthrough_target.kind,
        "lookthrough_key": row.lookthrough_target.key,
        "valuation_state": row.valuation_state,
        "heat_state": row.heat_state,
        "thesis_state": row.thesis_state,
        "product_quality_state": row.product_quality_state,
        "opportunity_state": row.opportunity_state,
        "opportunity_reason": row.opportunity_reason,
        "evidence_gaps": list(row.evidence_gaps),
        "expected_omissions": list(row.expected_omissions),
        # New schema (item 002):
        "thesis_evidence": [asdict(e) for e in row.thesis_evidence],
        "contributing_dimensions": sorted(row.contributing_dimensions),
        "constituent_analyses": [
            asdict(c) for c in getattr(row, "constituent_analyses", ())
        ],
        "fetch_types_attempted": list(row.fetch_types_attempted),
    }


def compose_opportunity_report(
    rows: list[OpportunityRow] | tuple[OpportunityRow, ...],
    date: str,
) -> dict[str, Any]:
    summary = {
        "core_dca_count": 0,
        "small_watch_count": 0,
        "pause_wait_count": 0,
        "exclude_count": 0,
    }
    for r in rows:
        summary[f"{r.opportunity_state}_count"] += 1
    return {
        "date": date,
        "summary": summary,
        "rows": [_row_to_dict(r) for r in rows],
    }


def _card_to_dict(card: ThesisCard) -> dict[str, Any]:
    d = asdict(card)
    for key in ("falsification_triggers", "trim_triggers",
                "do_not_sell_just_because", "evidence_gaps",
                "expected_omissions"):
        d[key] = list(d.get(key, []))
    # Every ThesisEvidence dict must carry its citation_id (computed in
    # __post_init__; never empty after construction).
    for ev_dict in d.get("thesis_evidence", []):
        if not ev_dict.get("citation_id"):
            raise RuntimeError(
                f"thesis_evidence entry missing citation_id: {ev_dict}"
            )
    return d


def compose_thesis_cards_yaml(cards: list[ThesisCard] | tuple[ThesisCard, ...]) -> str:
    payload = {"cards": [_card_to_dict(c) for c in cards]}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


_DCA_BUCKET = {
    "accelerate_dca": "今日可定投",
    "normal_dca": "今日可定投",
    "slow_dca": "减速定投",
    "pause_dca": "暂停加仓",
    "do_not_buy": "暂停加仓",
}

_RISK_BUCKET = {
    "review_required": "风险复核",
    "trim_review": "调仓复核",
    "exit_review": "退出复核",
}


def _bucket_rows(rows: list[DisciplineRow] | tuple[DisciplineRow, ...]) -> dict[str, list[DisciplineRow]]:
    buckets: dict[str, list[DisciplineRow]] = {
        "今日可定投": [],
        "减速定投": [],
        "暂停加仓": [],
        "风险复核": [],
        "调仓复核": [],
        "退出复核": [],
    }
    for r in rows:
        if r.risk_action in _RISK_BUCKET:
            buckets[_RISK_BUCKET[r.risk_action]].append(r)
        else:
            # Unknown dca_action values fall back to "今日可定投"; see TODOS.md
            # for a future robustness improvement (log or raise on unknown values).
            buckets[_DCA_BUCKET.get(r.dca_action, "今日可定投")].append(r)
    return buckets


def _render_section(title: str, rows: list[DisciplineRow]) -> str:
    if not rows:
        return f"## {title}\n\n（无）\n"
    lines = [f"## {title}\n"]
    for r in rows:
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** "
            f"｜ {r.opportunity_state} ｜ dca={r.dca_action} ｜ risk={r.risk_action} "
            f"｜ {r.note_cn}"
        )
    lines.append("")
    return "\n".join(lines)


_DRAWDOWN_NOTE_CN = (
    "## 关于回撤的说明\n\n"
    "持仓回撤达到 20% 或更高时，本系统**不会**自动卖出。\n"
    "回撤只触发风险复核，是否减仓或退出需结合：\n"
    "- 主题长期逻辑是否被证伪；\n"
    "- 产品质量是否变差；\n"
    "- 组合权重是否超出目标区间。\n"
    "短期价格下跌、单日波动不构成卖出理由。\n"
)


def compose_discipline_markdown(
    rows: list[DisciplineRow] | tuple[DisciplineRow, ...],
    date: str,
) -> str:
    buckets = _bucket_rows(rows)
    parts = [
        f"# Discipline Report — {date}\n",
        _render_section("今日可定投", buckets["今日可定投"]),
        _render_section("减速定投", buckets["减速定投"]),
        _render_section("暂停加仓", buckets["暂停加仓"]),
        _render_section("风险复核", buckets["风险复核"]),
        _render_section("调仓复核", buckets["调仓复核"]),
        _render_section("退出复核", buckets["退出复核"]),
        _DRAWDOWN_NOTE_CN,
    ]
    return "\n".join(parts)
