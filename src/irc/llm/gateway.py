from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
from irc.schemas.llm import LLMConfig

if TYPE_CHECKING:
    from irc.llm.http_client import ChatResponse


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


def call(
    task: str,
    messages: list[dict[str, str]],
    config: LLMConfig,
    **kwargs,
) -> ChatResponse:
    """Unified entry point: task + messages + config → ChatResponse.

    Hides ResolvedRoute from callers. Retries on 429/5xx.
    """
    from irc.llm.retry import retry_call_chat  # local import avoids cycle
    route = resolve_route(task, config)
    return retry_call_chat(route, messages, **kwargs)
