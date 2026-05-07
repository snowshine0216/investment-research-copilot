from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.llm import LLMConfig


@dataclass(frozen=True)
class ResolvedRoute:
    """Outcome of routing a task to a concrete (provider, model, endpoint)."""
    task: str
    provider: str
    model: str
    base_url: str
    api_key_env: str


def resolve_route(task: str, config: LLMConfig) -> ResolvedRoute:
    """Pure: task name → ResolvedRoute. Raises KeyError on unknown task."""
    if task not in config.tasks:
        raise KeyError(f"unknown task: {task!r}")
    route = config.tasks[task]
    if route.provider not in config.providers:
        raise KeyError(f"task {task!r} references unknown provider {route.provider!r}")
    provider_cfg = config.providers[route.provider]
    return ResolvedRoute(
        task=task,
        provider=route.provider,
        model=route.model,
        base_url=provider_cfg.base_url,
        api_key_env=provider_cfg.api_key_env,
    )
