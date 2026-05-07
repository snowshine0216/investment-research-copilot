from __future__ import annotations
import pytest
from irc.schemas.llm import LLMConfig
from irc.llm.gateway import resolve_route, ResolvedRoute


def _cfg() -> LLMConfig:
    return LLMConfig.model_validate({
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "news_summary": {"provider": "deepseek", "model": "deepseek-chat"},
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
            "memo_audit": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"},
        },
    })


def test_resolve_route_returns_provider_model_url():
    r = resolve_route("news_summary", _cfg())
    assert isinstance(r, ResolvedRoute)
    assert r.provider == "deepseek"
    assert r.model == "deepseek-chat"
    assert r.base_url == "https://api.deepseek.com"
    assert r.api_key_env == "DEEPSEEK_API_KEY"


def test_resolve_route_unknown_task_raises():
    with pytest.raises(KeyError, match="unknown task"):
        resolve_route("ghost_task", _cfg())


def test_resolve_route_is_pure():
    cfg1 = _cfg()
    r1 = resolve_route("memo_synthesis", cfg1)
    r2 = resolve_route("memo_synthesis", cfg1)
    assert r1 == r2
    assert cfg1.tasks["memo_synthesis"].model == "anthropic/claude-opus-4.7"


def test_resolve_route_missing_provider_raises():
    from irc.schemas.llm import LLMConfig, ProviderConfig, TaskRoute
    cfg = LLMConfig.model_construct(
        providers={
            "deepseek": ProviderConfig(base_url="https://api.deepseek.com", api_key_env="DEEPSEEK_API_KEY"),
        },
        tasks={
            "memo_synthesis": TaskRoute(provider="openrouter", model="anthropic/claude-opus-4.7"),
            "memo_audit": TaskRoute(provider="deepseek", model="deepseek-chat"),
        },
    )
    with pytest.raises(KeyError, match="unknown provider"):
        resolve_route("memo_synthesis", cfg)
