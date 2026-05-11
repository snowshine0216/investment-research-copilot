from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolvedRoute:
    """Outcome of routing a task to a concrete (provider, model, endpoint)."""
    task: str
    provider: str
    model: str
    base_url: str
    api_key_env: str


@dataclass(frozen=True)
class ChatResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int = 0
    raw: dict[str, Any] | None = None
