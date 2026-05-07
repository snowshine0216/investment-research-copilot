from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.llm import LLMConfig


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
    from irc.schemas.llm import ProviderConfig
    cfg = ProviderConfig.model_validate({"base_url": "http://localhost:8080", "api_key_env": "KEY"})
    assert "localhost" in cfg.base_url
    cfg2 = ProviderConfig.model_validate({"base_url": "http://127.0.0.1:11434/v1", "api_key_env": "KEY"})
    assert "127.0.0.1" in cfg2.base_url
