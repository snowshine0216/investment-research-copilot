from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DecisionStatus = Literal[
    "actionable_buy",
    "watch_only",
    "avoid",
    "blocked",
    # TODO (Phase 3): add "review_sell_later" when sell/trim signal emission is implemented
]
PortfolioAction = Literal["no_trade"]
VenueStatus = Literal["direct", "proxy_available", "blocked_no_proxy", "unknown"]


@dataclass(frozen=True)
class DecisionRow:
    instrument_id: str
    asset_class: str
    score_action: str
    decision_status: DecisionStatus
    portfolio_action: PortfolioAction
    conviction: str
    data_completeness: float
    missing_data: tuple[str, ...]
    target_weight_valid: bool
    venue_status: VenueStatus
    memo_evidence_status: str
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    next_step: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
