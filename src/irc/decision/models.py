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

# Annotates rows that landed in `watch_only`. Three distinct sub-cases used to
# collapse into one "Keep on watchlist and rerun after new data." bucket,
# which made the markdown report unreadable when 86 of 103 rows had that
# generic line. `watch_reason` makes the cause explicit:
#   - "score_watch": scoring decided the action is `watch` outright.
#   - "not_selected_by_allocation": scoring would have bought but allocation
#     dropped the candidate (correlation filter, intra-class loser, etc.).
#   - "venue_unknown": scoring + allocation both fine, but no trade entry
#     exists yet so venue isn't known. Item 008 reduces this case further.
WatchReason = Literal[
    "score_watch",
    "not_selected_by_allocation",
    "venue_unknown",
]


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
    # Populated only when ``decision_status == "watch_only"``. None on every other row.
    watch_reason: WatchReason | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
