from __future__ import annotations
from evals._shared.registry import (
    get_spec, active_suite_stages, is_inactive, is_live_gated,
)


def test_monitor_forward_is_active_but_not_in_all_suite():
    spec = get_spec("monitor_forward")
    assert spec.lifecycle == "active"
    assert spec.in_all_suite is False
    assert spec.runner_module == "evals.monitor_forward.runner"


def test_monitor_forward_excluded_from_active_suite():
    assert "monitor_forward" not in active_suite_stages()


def test_monitor_forward_is_not_inactive_nor_live_gated():
    spec = get_spec("monitor_forward")
    assert is_inactive(spec) is False
    assert is_live_gated(spec) is False
