"""Item 006 Slice H2.v2 — Policy B weight-aware quorum tests.

Tests cover acceptance criteria 7–16 and the edge cases locked in the spec.
"""
from __future__ import annotations

import pytest


def test_material_holding_quorum_top_10_is_5() -> None:
    from irc.opportunity.policy_b import MATERIAL_HOLDING_QUORUM
    assert MATERIAL_HOLDING_QUORUM(10) == 5


def test_material_holding_quorum_top_3_is_2() -> None:
    from irc.opportunity.policy_b import MATERIAL_HOLDING_QUORUM
    assert MATERIAL_HOLDING_QUORUM(3) == 2


def test_material_holding_quorum_top_1_is_1() -> None:
    from irc.opportunity.policy_b import MATERIAL_HOLDING_QUORUM
    assert MATERIAL_HOLDING_QUORUM(1) == 1


def test_material_holding_quorum_top_0_is_0() -> None:
    from irc.opportunity.policy_b import MATERIAL_HOLDING_QUORUM
    assert MATERIAL_HOLDING_QUORUM(0) == 0


def test_constituent_coverage_entry_construction() -> None:
    from irc.opportunity.policy_b import ConstituentCoverageEntry
    e = ConstituentCoverageEntry(
        symbol="600519",
        name_cn="贵州茅台",
        weight_pct=8.2,
        weight_rank=1,
        in_material_top_half=True,
        exchange="SH",
        has_data_leg=True,
        has_info_leg=True,
        data_kind_count=1,
        information_kind_count=1,
        failure_reasons=(),
        audit_errors=(),
    )
    assert e.symbol == "600519"
    assert e.weight_rank == 1
    assert e.in_material_top_half is True


def test_policy_b_verdict_publishable_default() -> None:
    from irc.opportunity.policy_b import PolicyBVerdict
    v = PolicyBVerdict(
        gap_codes=(),
        audit_errors=(),
        decision_rule="publishable",
        material_symbols=(),
        constituent_coverage=(),
    )
    assert v.gap_codes == ()
