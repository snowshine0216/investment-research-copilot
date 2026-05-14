from __future__ import annotations

import pytest

from evals.opportunity.metrics import (
    thesis_card_required_field_completeness,
    opportunity_evidence_gap_visibility,
    same_theme_distinct_index_limit,
    drawdown_not_auto_sell,
    hot_chase_prevention,
    valid_action_enums,
    no_external_worktree_path,
)


def _card(**overrides) -> dict:
    base = {
        "instrument_id": "510300",
        "name_cn": "X",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "core",
        "lookthrough_target": "沪深300",
        "entry_reason": "core",
        "valuation_state": "reasonable_low",
        "heat_state": "normal",
        "thesis_state": "intact",
        "product_quality_state": "acceptable",
        "opportunity_state": "core_dca",
        "dca_action": "normal_dca",
        "risk_action": "none",
        "falsification_triggers": ["a"],
        "trim_triggers": ["a"],
        "do_not_sell_just_because": ["drawdown_since_entry >= 0.20"],
        "review_cadence": "weekly_light_monthly_full",
        "evidence_gaps": [],
    }
    base.update(overrides)
    return base


def test_card_completeness_full_when_all_required_present():
    assert thesis_card_required_field_completeness([_card()]) == 1.0


def test_card_completeness_drops_when_field_missing():
    c = _card()
    del c["entry_reason"]
    result = thesis_card_required_field_completeness([c])
    assert 0.0 < result < 1.0


def test_evidence_gap_visibility_full_when_gaps_listed():
    rows = [
        {"valuation_state": "evidence_insufficient", "evidence_gaps": ["valuation"]},
        {"valuation_state": "cheap", "evidence_gaps": []},
    ]
    assert opportunity_evidence_gap_visibility(rows) == 1.0


def test_evidence_gap_visibility_partial_when_gap_hidden():
    rows = [
        {"valuation_state": "evidence_insufficient", "evidence_gaps": []},
        {"valuation_state": "evidence_insufficient", "evidence_gaps": ["valuation"]},
    ]
    assert opportunity_evidence_gap_visibility(rows) == 0.5


def test_same_theme_limit_passes_with_two_distinct_indices():
    rows = [
        {"theme": "healthcare", "lookthrough_key": "broad_healthcare"},
        {"theme": "healthcare", "lookthrough_key": "innovative_drugs"},
    ]
    assert same_theme_distinct_index_limit(rows) == 1.0


def test_same_theme_limit_fails_with_three_distinct_indices():
    rows = [
        {"theme": "healthcare", "lookthrough_key": "a"},
        {"theme": "healthcare", "lookthrough_key": "b"},
        {"theme": "healthcare", "lookthrough_key": "c"},
    ]
    result = same_theme_distinct_index_limit(rows)
    assert result < 1.0


def test_drawdown_not_auto_sell_full_when_section_present_and_cards_have_clause():
    md = "## 关于回撤的说明\n回撤 20% 不构成卖出。"
    cards = [_card()]
    assert drawdown_not_auto_sell(md, cards) == 1.0


def test_drawdown_not_auto_sell_fails_when_section_missing():
    md = "no chinese section"
    cards = [_card()]
    assert drawdown_not_auto_sell(md, cards) < 1.0


def test_drawdown_not_auto_sell_fails_when_card_missing_clause():
    md = "## 关于回撤的说明"
    bad = _card(do_not_sell_just_because=[])
    assert drawdown_not_auto_sell(md, [bad]) < 1.0


def test_hot_chase_prevention_full_when_no_overheated_in_buy_buckets():
    rows = [
        {"heat_state": "normal", "opportunity_state": "core_dca"},
        {"heat_state": "overheated", "opportunity_state": "pause_wait"},
    ]
    assert hot_chase_prevention(rows) == 1.0


def test_hot_chase_prevention_drops_when_overheated_in_core_dca():
    rows = [
        {"heat_state": "overheated", "opportunity_state": "core_dca"},
        {"heat_state": "normal", "opportunity_state": "core_dca"},
    ]
    assert hot_chase_prevention(rows) == 0.5


def test_valid_action_enums_full_when_all_legal():
    assert valid_action_enums([_card()]) == 1.0


def test_valid_action_enums_drops_when_invalid_value():
    bad = _card(dca_action="ramp_up_dca")
    assert valid_action_enums([bad]) < 1.0


def test_no_external_worktree_path_full_when_substring_absent():
    src = "from pathlib import Path\nrun(...)"
    assert no_external_worktree_path(src) == 1.0


def test_no_external_worktree_path_fails_when_substring_present():
    src = "Path('/Users/snow/Documents/Repository/investment-research-copilot.worktrees/x/cn_funds.generated.yaml')"
    assert no_external_worktree_path(src) == 0.0
