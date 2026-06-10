from __future__ import annotations

import yaml

from irc.commands.init_cmd import _read_template


def _packaged_llm_tasks() -> dict:
    """Parse the shipped packaged llm.yaml task routing (the shipped contract)."""
    cfg = yaml.safe_load(_read_template("config/llm.yaml"))
    assert cfg is not None, "packaged config/llm.yaml is empty — template not installed correctly"
    assert "tasks" in cfg, f"packaged llm.yaml missing 'tasks' key; got keys: {list(cfg)}"
    return cfg["tasks"]


def test_memo_synthesis_routes_to_openrouter_anthropic() -> None:
    # Memo LLM routing (shipped default): memo_synthesis -> OpenRouter Anthropic.
    route = _packaged_llm_tasks()["memo_synthesis"]
    assert route["provider"] == "openrouter"
    assert route["model"].startswith("anthropic/")


def test_memo_audit_routes_to_openrouter_anthropic() -> None:
    # Memo LLM routing (shipped default): memo_audit -> OpenRouter Anthropic.
    route = _packaged_llm_tasks()["memo_audit"]
    assert route["provider"] == "openrouter"
    assert route["model"].startswith("anthropic/")
