from __future__ import annotations

from irc.opportunity.discipline import (
    PositionContext,
    derive_dca_action,
    derive_risk_action,
)
from irc.opportunity.types import OpportunityRow, ThesisCard


_FALSIFICATION_TRIGGERS: tuple[str, ...] = (
    "theme thesis moves to falsified",
    "product quality moves to poor",
    "manager change with style drift",
)

_TRIM_TRIGGERS: tuple[str, ...] = (
    "valuation_state in [expensive, very_expensive]",
    "heat_state in [crowded, overheated]",
    "portfolio weight exceeds target band high",
)

_DO_NOT_SELL_JUST_BECAUSE: tuple[str, ...] = (
    "drawdown_since_entry >= 0.20",
    "single-day price drop",
    "short-term volatility spike",
)


def build_thesis_card(
    row: OpportunityRow,
    position: PositionContext,
    role: str,
    entry_reason: str,
    review_cadence: str = "weekly_light_monthly_full",
) -> ThesisCard:
    """Compose a durable ThesisCard. Pure function — derives DCA + risk
    actions from the row + position context."""
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    return ThesisCard(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        role=role,
        lookthrough_target=row.lookthrough_target.display_cn,
        entry_reason=entry_reason,
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        falsification_triggers=_FALSIFICATION_TRIGGERS,
        trim_triggers=_TRIM_TRIGGERS,
        do_not_sell_just_because=_DO_NOT_SELL_JUST_BECAUSE,
        review_cadence=review_cadence,
        evidence_gaps=row.evidence_gaps,
        thesis_evidence=row.thesis_evidence,
    )
