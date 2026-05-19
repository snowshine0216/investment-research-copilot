from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


VALUATION_STATES: tuple[str, ...] = (
    "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
)
HEAT_STATES: tuple[str, ...] = (
    "cold", "normal", "crowded", "overheated", "evidence_insufficient",
)
THESIS_STATES: tuple[str, ...] = (
    "intact", "under_pressure", "falsified", "evidence_insufficient",
)
PRODUCT_QUALITY_STATES: tuple[str, ...] = (
    "strong", "acceptable", "weak", "poor", "evidence_insufficient",
)
OPPORTUNITY_STATES: tuple[str, ...] = ("core_dca", "small_watch", "pause_wait", "exclude")
DCA_ACTIONS: tuple[str, ...] = (
    "accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy",
)
RISK_ACTIONS: tuple[str, ...] = (
    "none", "review_required", "trim_review", "exit_review",
)


ValuationState = Literal[
    "cheap", "reasonable_low", "fair", "expensive", "very_expensive", "evidence_insufficient",
]
HeatState = Literal["cold", "normal", "crowded", "overheated", "evidence_insufficient"]
ThesisState = Literal["intact", "under_pressure", "falsified", "evidence_insufficient"]
ProductQualityState = Literal["strong", "acceptable", "weak", "poor", "evidence_insufficient"]
OpportunityState = Literal["core_dca", "small_watch", "pause_wait", "exclude"]
DcaAction = Literal["accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy"]
RiskAction = Literal["none", "review_required", "trim_review", "exit_review"]


LookthroughKind = Literal[
    "broad_index", "sector_theme", "qdii_us", "qdii_hk", "bond", "gold", "active_fund",
]


@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind
    key: str
    display_cn: str


@dataclass(frozen=True)
class OpportunityInput:
    """Raw per-instrument metrics consumed by the state classifiers."""
    instrument_id: str
    asset_class: str
    market: str
    theme: str | None = None
    tracked_index: str | None = None
    name_cn: str = ""
    role: str = ""
    is_holding: bool = False
    portfolio_weight: float | None = None
    target_band_low: float | None = None
    target_band_high: float | None = None
    drawdown_since_entry: float | None = None
    valuation_percentile_self: float | None = None
    valuation_percentile_vs_benchmark: float | None = None
    # Adversarial review §B1: for cn_bond_fund the NAV-percentile says
    # nothing about whether duration is cheap or rich. A 10Y CGB yield
    # percentile (or analogous local-curve yield) is the right anchor.
    # Semantic: 0 = yields at floor (bonds expensive), 1 = yields at
    # ceiling (bonds cheap).
    cn_bond_yield_percentile: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None
    premium_discount_pct: float | None = None
    flow_pct_30d: float | None = None
    expense_ratio: float | None = None
    aum_cny: float | None = None
    aum_stability_pct: float | None = None
    tracking_error: float | None = None
    manager_tenure_years: float | None = None
    holdings_concentration_top10: float | None = None
    style_drift_flag: bool | None = None
    venue_compatible: bool = True
    # Adversarial review §B3: percentile-only valuation tells a long-horizon
    # DCA investor to underweight any multi-year bull. Earnings yield vs
    # real rate is the second-signal sanity anchor: positive ⇒ equity offers
    # positive expected real return even when its price percentile is high.
    earnings_yield: float | None = None
    real_yield_10y: float | None = None


ThesisEvidenceKind = Literal["filing", "broker", "news", "policy", "snapshot"]


@dataclass(frozen=True)
class ThesisEvidence:
    """Primary-source citation backing a `thesis_state`.

    `type` distinguishes the evidence shape: a filing digest, a broker report,
    a news article, a policy statement, or a snapshot summary line. Renderers
    can group by type; consumers should not infer state directly from `summary`.
    """
    type: ThesisEvidenceKind
    source: str
    url: str
    date: str
    summary: str


@dataclass(frozen=True)
class OpportunityRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    lookthrough_target: LookthroughTarget
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    opportunity_reason: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThesisCard:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    role: str
    lookthrough_target: str
    entry_reason: str
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    falsification_triggers: tuple[str, ...]
    trim_triggers: tuple[str, ...]
    do_not_sell_just_because: tuple[str, ...]
    review_cadence: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    expected_omissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DisciplineRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    note_cn: str
