from __future__ import annotations

import yaml

from irc.commands.init_cmd import _read_template


def _packaged_valuation_buckets() -> dict:
    """Parse the shipped packaged template (the shipped contract, never the runtime copy)."""
    cfg = yaml.safe_load(_read_template("config/valuation_buckets.yaml"))
    assert cfg is not None, (
        "packaged config/valuation_buckets.yaml is empty — template not installed correctly"
    )
    assert "active_fund_lookthrough" in cfg, (
        f"packaged valuation_buckets.yaml missing 'active_fund_lookthrough'; got keys: {list(cfg)}"
    )
    return cfg


def test_lookthrough_axis_is_enabled_in_packaged_template() -> None:
    # Phase D PR2 (commit cb1642d, PR #111): the active-fund look-through axis ships ON.
    cfg = _packaged_valuation_buckets()
    assert cfg["active_fund_lookthrough"]["enabled"] is True


def test_lookthrough_coverage_floor_is_half_in_packaged_template() -> None:
    # gate-#5 decision (ADR 0012 addendum 2026-06-05): coverage_floor settled at 0.50.
    cfg = _packaged_valuation_buckets()
    assert cfg["active_fund_lookthrough"]["coverage_floor"] == 0.50
