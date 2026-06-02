from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from irc.fundamentals.types import ConstituentAnalysis, ThesisEvidence
from irc.opportunity.types import (
    DcaAction,
    HeatState,
    OpportunityState,
    ProductQualityState,
    RiskAction,
    ThesisState,
    ValuationState,
)

RiskLevel = Literal["low", "moderate", "elevated", "high", "insufficient"]


@dataclass(frozen=True)
class BasketStock:
    """One stock that DEFINES a narrative."""

    symbol: str
    name_cn: str
    metal: str = ""


@dataclass(frozen=True)
class NarrativeBasket:
    """Curated, frozen reference basket loaded from config/narratives/<id>.yaml."""

    narrative_id: str
    display_name_cn: str
    display_name_en: str
    thesis_cn: str
    basket: tuple[BasketStock, ...]
    industries_sw: tuple[str, ...]
    min_basket_weight_pct: float
    min_overlap_count: int
    top_n: int


@dataclass(frozen=True)
class Holding:
    """One disclosed top-10 holding of a fund (percent units, 0.0–100.0)."""

    symbol: str
    name_cn: str
    weight_pct: float
    sw_industry: str = ""


@dataclass(frozen=True)
class OverlapResult:
    """Result of matching a fund's top-10 against a basket."""

    # Intentionally includes SW-industry-credit weight as well as direct basket-match
    # weight (spec §3.5): total thematic exposure, not just symbol-exact basket hits.
    basket_weight_pct: float
    overlap_count: int
    matched_symbols: tuple[str, ...]
    industry_credit_symbols: tuple[str, ...]


@dataclass(frozen=True)
class ShortlistRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    overlap: OverlapResult
    holdings: tuple[Holding, ...]


@dataclass(frozen=True)
class ProductMetrics:
    """M2 product-quality drivers, projected from OpportunityInput at the
    analyze edge. Display-only — no classifier reads it (RD-5). `None` means
    'unprovidable / not ingested' and renders as `—`. `tracking_error` is
    populated for passive vehicles only."""

    expense_ratio: float | None = None
    aum_cny: float | None = None
    manager_tenure_years: float | None = None
    tracking_error: float | None = None


@dataclass(frozen=True)
class NarrativeFundReport:
    """Per-fund analyze record. Carries the REAL OpportunityRow/ThesisCard state
    plus the prospective-buy risk level. `thesis_evidence` holds the ACTUAL
    `ThesisEvidence` objects (not a stringified projection) so the renderer can
    reuse `select_citations(thesis_evidence, cap=3)` and emit the locked
    `- [ref:{citation_id}] {type} · {source} · {date}` line."""

    instrument_id: str
    name_cn: str
    position_risk_level: RiskLevel
    risk_rationale: str
    risk_drivers: tuple[str, ...]
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    falsification_triggers: tuple[str, ...]
    trim_triggers: tuple[str, ...]
    review_cadence: str
    evidence_gaps: tuple[str, ...]
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    # Item 003: display-only carriers. constituent_analyses is threaded from
    # card/row (the renderer stopped dropping it); product_metrics is built from
    # OpportunityInput. Neither feeds any gate/classifier (RD-5).
    constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
    product_metrics: ProductMetrics | None = None


@dataclass(frozen=True)
class RiskEvalView:
    """Pure projection of OpportunityRow fields consumed by the risk core.

    Built at the analyze edge (Task 8 _risk_view_from_row) so risk.py never
    imports OpportunityRow. top_holdings is (symbol, name_cn, weight_pct) in
    percent units, weight DESC."""

    valuation_state: str
    heat_state: str
    thesis_state: str
    product_quality_state: str
    evidence_gaps: tuple[str, ...]
    top_holdings: tuple[tuple[str, str, float], ...]
