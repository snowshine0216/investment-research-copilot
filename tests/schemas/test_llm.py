from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.llm import LLMConfig, ProviderConfig, TaskRoute


def test_llm_config_minimal():
    raw = {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "news_summary": {"provider": "deepseek", "model": "deepseek-chat"},
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
            "memo_audit": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.6"},
        },
    }
    cfg = LLMConfig.model_validate(raw)
    assert cfg.tasks["memo_synthesis"].provider == "openrouter"


def test_llm_config_unknown_provider_in_task_fails():
    raw = {
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
        },
        "tasks": {"memo_synthesis": {"provider": "ghost", "model": "y"}, "memo_audit": {"provider": "ghost", "model": "y"}},
    }
    with pytest.raises(ValidationError):
        LLMConfig.model_validate(raw)


def test_llm_config_required_tasks_present():
    """memo_synthesis and memo_audit are required tasks (HARD-fail criticality)."""
    raw = {
        "providers": {
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
        },
        "tasks": {
            "memo_synthesis": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
        },
    }
    with pytest.raises(ValidationError, match="memo_audit"):
        LLMConfig.model_validate(raw)


def test_llm_provider_rejects_private_ip_base_url():
    """base_url pointing to private IP range must be rejected (SSRF guard)."""
    from irc.schemas.llm import ProviderConfig
    with pytest.raises(ValidationError, match="private/reserved"):
        ProviderConfig.model_validate({"base_url": "https://169.254.169.254/v1", "api_key_env": "KEY"})


def test_llm_provider_allows_localhost_base_url():
    """localhost and 127.0.0.1 are allowed for dev mock servers."""
    cfg = ProviderConfig.model_validate({"base_url": "http://localhost:8080", "api_key_env": "KEY"})
    assert "localhost" in cfg.base_url
    cfg2 = ProviderConfig.model_validate({"base_url": "http://127.0.0.1:11434/v1", "api_key_env": "KEY"})
    assert "127.0.0.1" in cfg2.base_url


# --- Phase D: Task 14 tests ---


def test_provider_requires_exactly_one_base_url_source():
    with pytest.raises(ValidationError):
        ProviderConfig(api_key_env="K")  # neither base_url nor base_url_env
    with pytest.raises(ValidationError):
        ProviderConfig(base_url="https://x.com", base_url_env="X_BASE", api_key_env="K")


def test_provider_base_url_env_only_is_valid():
    p = ProviderConfig(base_url_env="MINIMAX_BASE_URL", api_key_env="MINIMAX_API_KEY",
                       default_model_env="MINIMAX_MODEL")
    assert p.base_url is None and p.base_url_env == "MINIMAX_BASE_URL"


def test_task_model_optional_resolves_from_provider_default_env():
    cfg = LLMConfig(
        providers={
            "minimax": ProviderConfig(base_url_env="MINIMAX_BASE_URL",
                                      api_key_env="MINIMAX_API_KEY",
                                      default_model_env="MINIMAX_MODEL"),
            "deepseek": ProviderConfig(base_url="https://api.deepseek.com",
                                       api_key_env="DEEPSEEK_API_KEY"),
        },
        tasks={
            "monitor_impact": TaskRoute(provider="minimax"),       # model omitted
            "memo_synthesis": TaskRoute(provider="deepseek", model="deepseek-reasoner"),
            "memo_audit": TaskRoute(provider="deepseek", model="deepseek-reasoner"),
        },
    )
    assert cfg.tasks["monitor_impact"].model is None


def test_task_model_omitted_with_no_default_model_env_raises():
    with pytest.raises(ValidationError, match="model"):
        LLMConfig(
            providers={"p": ProviderConfig(base_url="https://x.com", api_key_env="K"),
                       "deepseek": ProviderConfig(base_url="https://api.deepseek.com",
                                                  api_key_env="DEEPSEEK_API_KEY")},
            tasks={"t": TaskRoute(provider="p"),
                   "memo_synthesis": TaskRoute(provider="deepseek", model="m"),
                   "memo_audit": TaskRoute(provider="deepseek", model="m")},
        )
