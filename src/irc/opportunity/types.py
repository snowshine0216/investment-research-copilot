from __future__ import annotations

import hashlib
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
    "broad_index", "sector_theme", "qdii_us", "qdii_hk", "bond", "gold", "active_fund", "qdii_global",
]


@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind
    key: str
    display_cn: str
    provider_symbol: str = ""


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
CitationKind = Literal["data", "information"]
CitationScope = Literal["instrument", "constituent", "asset_class_macro", "policy"]


@dataclass(frozen=True)
class ThesisEvidence:
    """Primary-source citation backing a `thesis_state`, with content-addressed
    provenance.

    `citation_id` is a 16-hex-char prefix of sha256 over the preimage
    (owner_instrument_id : scope : constituent_key : type : canonical_id : date)
    where canonical_id = url or f"{source}:{date}:{summary[:64]}". The id is
    computed in `__post_init__` and overrides any caller-supplied value.

    See `docs/adr/0001-citation-data-model.md` for the binding contract.
    """
    type: ThesisEvidenceKind
    source: str
    url: str
    date: str
    summary: str
    # Required provenance fields (no defaults; callers MUST supply).
    scope: CitationScope
    citation_kind: CitationKind
    owner_instrument_id: str
    parent_fund_id: str | None
    constituent_key: str | None
    # Computed in __post_init__; never accept caller-supplied value.
    citation_id: str = ""
    # Item 003: weight of holding in the parent fund (percent, 0.0–100.0).
    # Appended AFTER citation_id; NOT part of the hash preimage (ADR 0001 §2).
    holding_weight_pct: float | None = None

    def __post_init__(self) -> None:
        if not self.owner_instrument_id:
            raise ValueError("ThesisEvidence.owner_instrument_id must be non-empty")
        if self.citation_kind not in ("data", "information"):
            raise ValueError(f"invalid citation_kind: {self.citation_kind!r}")
        if self.scope not in ("instrument", "constituent",
                              "asset_class_macro", "policy"):
            raise ValueError(f"invalid scope: {self.scope!r}")
        if not self.type or not self.source or not self.date:
            raise ValueError(
                "ThesisEvidence.type/source/date must be non-empty"
            )
        canonical_id = self.url or f"{self.source}:{self.date}:{self.summary[:64]}"
        preimage = (
            f"{self.owner_instrument_id}:{self.scope}:"
            f"{self.constituent_key or ''}:{self.type}:"
            f"{canonical_id}:{self.date}"
        ).encode("utf-8")
        object.__setattr__(
            self, "citation_id", hashlib.sha256(preimage).hexdigest()[:16]
        )


@dataclass(frozen=True)
class CitationMeta:
    """Per-citation metadata indexed by `citation_id` in `CitedMap`.

    `asset_class` is the asset class of the row whose `instrument_id ==
    owner_instrument_id` at `build_cited_map` time. Required because the
    portfolio-section audit (item 007/009) rejects scope-mismatched citations
    from `CitationMeta.asset_class` alone, without alias lookup.
    """
    scope: CitationScope
    citation_kind: CitationKind
    owner_instrument_id: str
    asset_class: str
    parent_fund_id: str | None
    constituent_key: str | None


# Type aliases consumed by build_cited_map and downstream audit gates (item 009).
CitedMap = dict[str, dict[str, CitationMeta]]
"""instrument_id → {citation_id: CitationMeta}"""

ConstituentCitedMap = dict[str, dict[str, dict[str, CitationMeta]]]
"""instrument_id → constituent_key → {citation_id: CitationMeta}"""


@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str
    name_cn: str
    weight_pct: float
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("ConstituentAnalysis.symbol must be non-empty")
        if self.weight_pct < 0:
            raise ValueError(
                f"ConstituentAnalysis.weight_pct must be >= 0; got {self.weight_pct}"
            )


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
    contributing_dimensions: frozenset[str] = field(default_factory=frozenset)
    # Item 002: fetch pipeline diagnostics — mirrors DisciplineRow.fetch_types_attempted.
    # Serialized by _row_to_dict so render_failure_sections can populate 已尝试:.
    fetch_types_attempted: tuple[str, ...] = ()
    # Item 003: per-constituent structured evidence for active-fund rows.
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()


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
    # Item 003: per-constituent structured evidence (threaded from OpportunityRow).
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()


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
    # Item 002: gap state and provenance carried through to renderers.
    # Item 003: `constituent_analyses` narrowed from `tuple[object, ...]` to typed.
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    fetch_types_attempted: tuple[str, ...] = ()
