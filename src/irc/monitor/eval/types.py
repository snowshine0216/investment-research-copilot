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
class ValidationPanelRow:
    stage: str
    status: str                  # PASS | WARN | FAIL | UNKNOWN
    ran_at: str
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
