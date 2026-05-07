from __future__ import annotations
from typing import TYPE_CHECKING
from irc.schemas.llm import LLMConfig
from irc.llm._types import ResolvedRoute

if TYPE_CHECKING:
    from irc.llm.http_client import ChatResponse
    from tenacity import wait_base

__all__ = ["ResolvedRoute", "resolve_route", "call"]


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
    *,
    wait: wait_base | None = None,
    **kwargs,
) -> ChatResponse:
    """Unified entry point: task + messages + config → ChatResponse.

    Hides ResolvedRoute from callers. Retries on 429/5xx.
    Pass ``wait=wait_none()`` in tests to skip sleeping.
    """
    from irc.llm.retry import retry_call_chat  # local import avoids cycle
    route = resolve_route(task, config)
    return retry_call_chat(route, messages, wait=wait, **kwargs)
