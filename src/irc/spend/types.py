from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskUsage:
    task: str
    avg_calls_per_run: float
    avg_prompt_tokens: float
    avg_completion_tokens: float
    samples: int           # 0 ⇒ seeded (no learned data yet)


@dataclass(frozen=True)
class UsageProfile:
    tasks: Mapping[str, TaskUsage]
    alpha: float = 0.3


@dataclass(frozen=True)
class CostEstimate:
    provider: str
    currency: str
    amount: float
    breakdown: Mapping[str, float]


@dataclass(frozen=True)
class BalanceReading:
    provider: str
    currency: str
    amount: float | None   # None ⇒ unreadable → never hard-stops
    available: bool
    source: str            # "api" | "ledger" | "probe_failed" | "no_balance_api"


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    estimate: float | None
    balance: float | None
    status: str            # "ok" | "blocked" | "warning" | "info"
    detail: str


@dataclass(frozen=True)
class GateDecision:
    blocked: tuple[ProviderVerdict, ...]
    warnings: tuple[ProviderVerdict, ...]
    ok: tuple[ProviderVerdict, ...]


@dataclass(frozen=True)
class TaskActual:
    """One run's observed usage for a single llm.yaml task (means per call)."""
    task: str
    calls: float
    avg_prompt_tokens: float
    avg_completion_tokens: float


@dataclass(frozen=True)
class RunActuals:
    """A gated command's measured paid usage: LLM per task + search units per provider."""
    tasks: Mapping[str, TaskActual]
    search_units: Mapping[str, int]
