from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "insufficient_evidence", "low_confidence"]
Bias = Literal["ADD_BIAS", "NEUTRAL", "REDUCE_BIAS"]
AttributionStrength = Literal[
    "supported_attribution", "consistent_with", "possible_driver", "unknown"
]


@dataclass(frozen=True)
class EvidenceItem:
    """Monitor's OWN evidence record — no `scope` field (ADR 0017). Owner-bound by
    construction. citation_id = 16 hex of sha256(owner_fund_id:url_or_fallback:date)."""
    source: str
    title: str
    date: str
    url: str
    owner_fund_id: str
    citation_id: str


@dataclass(frozen=True)
class MonitorFund:
    id: str
    name_cn: str
    market: str
    analysis_profile: str
    themes: tuple[str, ...]
    constituent_news: bool
    weights: dict[str, float]          # effective (profile ⊕ override), sums to 1.0
    bands: dict[str, float]            # {"buy":.., "sell":..}
    minimum_confidence: float


@dataclass(frozen=True)
class FactorScore:
    name: str
    value: float | None                # None ⇒ N/A
    eligible: bool
    reason: str                        # "" when eligible & present, else N/A reason code
    confidence: float = 1.0            # deterministic factors → 1.0


@dataclass(frozen=True)
class FactorContribution:
    name: str
    renorm_weight: float               # w'ᵢ
    value: float
    contribution: float                # w'ᵢ·sᵢ
    confidence: float
    eligible: bool
    reason: str


@dataclass(frozen=True)
class SignalRecord:
    fund_id: str
    status: Status
    bias: Bias | None                  # null iff status != ok
    composite: float                   # C, rounded 4dp
    signal_confidence: float           # rounded 4dp
    available_weight: float
    present_families: tuple[str, ...]
    contributions: tuple[FactorContribution, ...]
    divergence_codes: tuple[str, ...]


@dataclass(frozen=True)
class Claim:
    claim: str
    attribution_strength: AttributionStrength
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class NarrativeDoc:
    fund_id: str
    price_action_commentary: tuple[Claim, ...]
    signal_rationale_commentary: tuple[Claim, ...]
    risk_commentary: tuple[Claim, ...]
    status: str                        # "ok" | typed failure reason
