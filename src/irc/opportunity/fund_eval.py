from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.discipline import derive_dca_action
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import (
    DcaAction,
    HeatState,
    OpportunityInput,
    OpportunityState,
    ProductQualityState,
    ThesisState,
    ValuationState,
)


@dataclass(frozen=True)
class FundEval:
    instrument_id: str
    name_cn: str
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    core_dca: bool
    note_cn: str
    top_holdings: tuple[tuple[str, str, float], ...]
    evidence_gaps: tuple[str, ...]
    role: str


@dataclass(frozen=True)
class EvalItem:
    inp: OpportunityInput
    snapshot: ActiveFundSnapshot | None
    role: str


def evaluate_fund(
    inp: OpportunityInput,
    snapshot: ActiveFundSnapshot | None,
    *,
    role: str,
) -> FundEval:
    """Pure: classify one fund via the pipeline's build_opportunity_row +
    derive_dca_action. theme_report is None (v1 snapshot-only thesis, spec §6)."""
    row = build_opportunity_row(inp, None, snapshot=snapshot)
    dca = derive_dca_action(row)
    top = tuple(
        (c.symbol, c.name_cn, c.weight_pct) for c in row.constituent_analyses
    )
    return FundEval(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        core_dca=(row.opportunity_state == "core_dca"),
        note_cn=row.opportunity_reason,
        top_holdings=top,
        evidence_gaps=row.evidence_gaps,
        role=role,
    )


def evaluate_funds(items: Iterable[EvalItem]) -> tuple[FundEval, ...]:
    """Pure: evaluate each item, then sort core_dca-first then by state severity."""
    evals = [evaluate_fund(it.inp, it.snapshot, role=it.role) for it in items]
    return tuple(sorted(evals, key=_sort_key))


_STATE_SEVERITY: dict[str, int] = {
    "core_dca": 0, "small_watch": 1, "pause_wait": 2, "exclude": 3,
}


def _sort_key(ev: FundEval) -> tuple[int, int, str]:
    return (
        0 if ev.core_dca else 1,
        _STATE_SEVERITY.get(ev.opportunity_state, 9),
        ev.instrument_id,
    )


def render_fund_eval_md(evals: tuple[FundEval, ...]) -> str:
    """Deterministic markdown: core_dca headline list + a full sub-state table."""
    core = [e for e in evals if e.core_dca]
    lines: list[str] = ["# 基金评估 / Fund evaluation", ""]
    lines.append(f"## core_dca 候选（{len(core)} / {len(evals)}）")
    if core:
        for e in core:
            lines.append(f"- {e.instrument_id} {e.name_cn} — {e.dca_action}")
    else:
        lines.append("- （无）")
    lines.append("")
    lines.append("## 全部评估 / Full sub-state table")
    lines.append(
        "| 代码 | 名称 | 估值 | 热度 | 逻辑 | 质量 | 机会 | 定投 | core_dca |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for e in evals:
        lines.append(
            f"| {e.instrument_id} | {e.name_cn} | {e.valuation_state} | "
            f"{e.heat_state} | {e.thesis_state} | {e.product_quality_state} | "
            f"{e.opportunity_state} | {e.dca_action} | "
            f"{'✅' if e.core_dca else '—'} |"
        )
    return "\n".join(lines) + "\n"


def render_fund_eval_json(evals: tuple[FundEval, ...]) -> str:
    """Deterministic JSON string. top_holdings serialise as lists of [sym, name, wt]."""
    doc = {
        "funds": [
            {
                "instrument_id": e.instrument_id,
                "name_cn": e.name_cn,
                "valuation_state": e.valuation_state,
                "heat_state": e.heat_state,
                "thesis_state": e.thesis_state,
                "product_quality_state": e.product_quality_state,
                "opportunity_state": e.opportunity_state,
                "dca_action": e.dca_action,
                "core_dca": e.core_dca,
                "note_cn": e.note_cn,
                "top_holdings": [list(h) for h in e.top_holdings],
                "evidence_gaps": list(e.evidence_gaps),
                "role": e.role,
            }
            for e in evals
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)
