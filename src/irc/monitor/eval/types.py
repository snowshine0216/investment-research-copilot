"""PURE eval types. ADR 0017 §3.3: no AkShare/provider/LLM/settings/filesystem imports.

NAMING GUARD: this GateDecision is DISTINCT from irc.spend.types.GateDecision
(the spend-preflight verdict). Import this one by qualified path in any module
that also touches irc.spend.types — never bare-import both.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from irc.monitor.impact_validate import ValidatedImpact
from irc.monitor.types import EvidenceItem

HealthStatus = Literal["PASS", "WARN", "FAIL", "UNKNOWN"]
Badge = Literal["validated", "caveated", "gated"]


@dataclass(frozen=True)
class StageHealth:
    stage: str
    status: HealthStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GateDecision:
    fund_id: str
    suppressed: bool
    failed_stages: tuple[str, ...]
    badge: Badge
    reason: str


@dataclass(frozen=True)
class FundTraceBundle:
    """Un-aggregated per-fund eval inputs, kept off the render FundView.
    For non-lookthrough funds (gold/qdii) constituent_* are ()."""
    fund_id: str
    macro_impacts: tuple[ValidatedImpact, ...]
    constituent_impacts: tuple[ValidatedImpact, ...]
    constituent_pool: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class PredictiveMetricView:
    name: str
    value: float
    status: str                       # "PASS" | "WARN"
    state: str                        # "ok" | "insufficient_data" | "undefined"
    ci_low: float
    ci_high: float
    random_delta: float | None
    momentum_delta: float | None      # None / absent on the rank_ic row
    buy_hold_delta: float | None      # None / absent on the rank_ic row
    n_observations: int


@dataclass(frozen=True)
class PredictivePanelModel:
    present: bool                     # a latest report exists
    stale: bool
    artifact_date: str | None
    metrics: tuple[PredictiveMetricView, ...]
    review_flag: bool
