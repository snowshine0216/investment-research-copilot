from __future__ import annotations
from importlib import resources
import yaml
from irc.llm.gateway import resolve_route
from irc.schemas.llm import LLMConfig


def _load_template_cfg() -> LLMConfig:
    text = resources.files("irc.templates.config").joinpath("llm.yaml").read_text(encoding="utf-8")
    return LLMConfig.model_validate(yaml.safe_load(text))


def test_thesis_defend_resolves_to_deepseek_reasoner():
    cfg = _load_template_cfg()
    route = resolve_route("thesis_defend", cfg)
    assert route.model == "deepseek-reasoner"
    assert route.provider == "deepseek"


def test_thesis_defend_matches_thesis_falsify_model():
    cfg = _load_template_cfg()
    assert resolve_route("thesis_defend", cfg).model == resolve_route("thesis_falsify", cfg).model


def test_config_still_validates_with_extra_task():
    # Extra tasks are allowed (REQUIRED_TASKS = memo_synthesis/memo_audit only).
    cfg = _load_template_cfg()
    assert "thesis_defend" in cfg.tasks
