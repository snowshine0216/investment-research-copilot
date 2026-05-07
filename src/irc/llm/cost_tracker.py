from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CostEntry:
    task: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    ts: str  # ISO 8601 with offset


def append_cost(history: list[CostEntry], entry: CostEntry) -> list[CostEntry]:
    """Pure: returns history + entry as a NEW list (caller does not mutate)."""
    return [*history, entry]


def redact_secret(secret: str) -> str:
    """Mask all but last 4 characters of an API key for safe logging."""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "***"
    return f"{secret[:3]}***{secret[-4:]}"
