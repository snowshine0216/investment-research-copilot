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
PortfolioAction = Literal["no_trade", "buy", "trim_review", "exit_review", "review"]
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
    # Human-readable name resolved from universe configs / discovered watchlist.
    # None when the caller didn't pass a names map or the id wasn't found.
    instrument_name: str | None = None
    # Target weight from proposed_allocation.yaml when the row was selected;
    # 0.0 when the row isn't in the allocation. Used by the "Today's only
    # action" headline to size each actionable buy.
    target_weight: float = 0.0
    # Item 001: holdings-aware weights for the 持仓行动 section.
    # current_weight is COST-BASIS (portfolio_weight = cost_basis_cny /
    # portfolio_total_cny), not live market value (ADR 0015 §2 / OQ3).
    # weight_delta = current_weight - target_weight (fraction units; 0.02 = +2pp).
    current_weight: float = 0.0
    weight_delta: float = 0.0
    # is_holding: True when the operator holds a position in this instrument
    # (sourced from inputs/account.yaml via positions[iid].is_holding).
    # Required by _holdings_action_section to filter the 持仓行动 table
    # (P0-1: was dropped before reaching DecisionRow.to_dict()).
    is_holding: bool = False
    # Allocation/trade-plan role tag (e.g. "defensive_cn_bond",
    # "core_gold_hedge"). Empty when no trade exists for this id.
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
