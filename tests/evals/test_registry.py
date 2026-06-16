"""Registry contract tests.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/002-spec.md
"""
from __future__ import annotations

import pytest

from evals._shared.registry import (
    REGISTRY,
    active_suite_stages,
    get_spec,
    is_inactive,
)


def test_all_known_stages_present() -> None:
    expected = {
        "data", "research", "discovery", "scoring", "gold_score",
        "allocation", "trade_plan", "memo", "architecture", "opportunity",
        "triggers", "news", "queries",
        "monitor_signal", "monitor_impact", "monitor_narrative",
        "monitor_forward",
    }
    assert set(REGISTRY) == expected


def test_active_suite_excludes_news_and_queries() -> None:
    stages = active_suite_stages()
    assert "news" not in stages
    assert "queries" not in stages


def test_active_suite_includes_triggers_as_unimplemented_active() -> None:
    assert "triggers" in active_suite_stages()
    assert REGISTRY["triggers"].lifecycle == "unimplemented_active"


def test_news_is_inactive_legacy() -> None:
    spec = REGISTRY["news"]
    assert spec.lifecycle == "inactive_legacy"
    assert spec.in_all_suite is False
    assert is_inactive(spec) is True


def test_queries_is_inactive_uninstrumented() -> None:
    spec = REGISTRY["queries"]
    assert spec.lifecycle == "inactive_uninstrumented"
    assert spec.in_all_suite is False
    assert is_inactive(spec) is True


def test_active_lifecycle_is_not_inactive() -> None:
    assert is_inactive(REGISTRY["data"]) is False
    assert is_inactive(REGISTRY["triggers"]) is False


def test_get_spec_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_spec("ghost")


def test_runner_module_path_is_dotted_evals_path() -> None:
    for stage, spec in REGISTRY.items():
        assert spec.runner_module == f"evals.{stage}.runner"


def test_live_gated_is_a_lifecycle_value() -> None:
    import typing
    from evals._shared.registry import Lifecycle
    assert "live_gated" in typing.get_args(Lifecycle)


def test_monitor_signal_registered_active_in_all_suite() -> None:
    spec = REGISTRY["monitor_signal"]
    assert spec.lifecycle == "active"
    assert spec.in_all_suite is True
    assert spec.runner_module == "evals.monitor_signal.runner"
    assert "monitor_signal" in active_suite_stages()


def test_monitor_llm_suites_are_live_gated_placeholders() -> None:
    from evals._shared.registry import is_live_gated
    for stage in ("monitor_impact", "monitor_narrative"):
        spec = REGISTRY[stage]
        assert spec.lifecycle == "live_gated"
        assert spec.in_all_suite is False
        assert is_live_gated(spec) is True
        assert stage not in active_suite_stages()


def test_is_live_gated_false_for_active() -> None:
    from evals._shared.registry import is_live_gated
    assert is_live_gated(REGISTRY["monitor_signal"]) is False


def test_live_gated_placeholder_importability_not_required() -> None:
    # The placeholder runner module need not import in M0 — only the path string matters.
    spec = REGISTRY["monitor_impact"]
    assert spec.runner_module == "evals.monitor_impact.runner"  # string, lazily resolved


def test_eval_stage_spec_is_frozen() -> None:
    spec = REGISTRY["data"]
    with pytest.raises(Exception):
        spec.stage = "other"  # type: ignore[misc]
