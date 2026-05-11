from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DecisionStatus = Literal[
    "actionable_buy",
    "watch_only",
    "avoid",
    "blocked",
    "review_sell_later",
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
    missing_data: list[str]
    target_weight_valid: bool
    venue_status: VenueStatus
    memo_evidence_status: str
    blocking_reasons: list[str] = field(default_factory=list)
    reason: str = ""
    next_step: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
