from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedRoute:
    """Outcome of routing a task to a concrete (provider, model, endpoint)."""
    task: str
    provider: str
    model: str
    base_url: str
    api_key_env: str
