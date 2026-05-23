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


def _ca(symbol: str, weight: float, evidence: tuple = (), failure_reasons: tuple = ()):
    """Tiny ConstituentAnalysis factory for tests."""
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol,
        name_cn=symbol,
        weight_pct=weight,
        evidence=evidence,
        failure_reasons=failure_reasons,
        one_line_view="",
    )


def test_rank_by_weight_descending_no_ties() -> None:
    from irc.opportunity.policy_b import _rank_by_weight
    analyses = (
        _ca("A", 3.0),
        _ca("B", 5.0),
        _ca("C", 1.0),
    )
    ranked = _rank_by_weight(analyses)
    assert [c.symbol for c in ranked] == ["B", "A", "C"]


def test_rank_by_weight_ties_broken_by_symbol_ascending() -> None:
    from irc.opportunity.policy_b import _rank_by_weight
    analyses = (
        _ca("C", 5.0),
        _ca("A", 5.0),
        _ca("B", 5.0),
    )
    ranked = _rank_by_weight(analyses)
    assert [c.symbol for c in ranked] == ["A", "B", "C"]


def test_material_set_with_ties_top_10_no_ties() -> None:
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    weights = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    ranked = _rank_by_weight(tuple(_ca(f"S{i}", w) for i, w in enumerate(weights)))
    material = _material_set_with_ties(ranked, top_n=10)
    # ceil(10/2) = 5, no tie at the cutoff → material has 5 entries.
    assert len(material) == 5
    assert [c.symbol for c in material] == ["S0", "S1", "S2", "S3", "S4"]


def test_material_set_with_ties_boundary_tie_extends_set() -> None:
    """Spec material-set tie rule: ties at the cutoff weight EXTEND the set."""
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    weights = [8.2, 7.1, 6.5, 5.0, 4.2, 4.2, 3.8, 2.0, 1.0, 0.5]
    ranked = _rank_by_weight(tuple(_ca(f"S{i}", w) for i, w in enumerate(weights)))
    material = _material_set_with_ties(ranked, top_n=10)
    # ceil(10/2) = 5; positions 5 + 6 tied at 4.2 → material extends to 6.
    assert len(material) == 6
    assert all(c.weight_pct >= 4.2 for c in material)


def test_material_set_with_ties_all_weights_equal_becomes_full_set() -> None:
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    ranked = _rank_by_weight(tuple(_ca(f"S{i}", 10.0) for i in range(10)))
    material = _material_set_with_ties(ranked, top_n=10)
    assert len(material) == 10  # full quorum since every weight ties at cutoff


def test_material_set_with_ties_top_0_is_empty() -> None:
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    ranked = _rank_by_weight(())
    assert _material_set_with_ties(ranked, top_n=0) == ()


def test_material_set_with_ties_top_1_keeps_single_holding() -> None:
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    ranked = _rank_by_weight((_ca("X", 100.0),))
    material = _material_set_with_ties(ranked, top_n=1)
    assert len(material) == 1
    assert material[0].symbol == "X"


def test_material_set_with_ties_shortfall_uses_actual_count() -> None:
    """Edge case from spec: top_n=10 but only 7 constituents present."""
    from irc.opportunity.policy_b import _material_set_with_ties, _rank_by_weight
    weights = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0]
    ranked = _rank_by_weight(tuple(_ca(f"S{i}", w) for i, w in enumerate(weights)))
    material = _material_set_with_ties(ranked, top_n=10)
    # ceil(10/2) = 5, no tie at the rank-5 boundary in this set.
    assert len(material) == 5


def test_build_coverage_entries_orders_by_weight_rank_ascending() -> None:
    from irc.opportunity.policy_b import _build_coverage_entries, _rank_by_weight
    weights = [3.0, 5.0, 1.0]
    ranked = _rank_by_weight(tuple(_ca(f"S{i}", w) for i, w in enumerate(weights)))
    entries = _build_coverage_entries(ranked, top_n=10)
    assert [e.weight_rank for e in entries] == [1, 2, 3]
    assert entries[0].symbol == "S1"  # weight 5.0
    assert entries[0].in_material_top_half is True


def test_build_coverage_entries_audit_overrides_applied() -> None:
    from irc.opportunity.policy_b import _build_coverage_entries, _rank_by_weight
    ranked = _rank_by_weight((_ca("X", 5.0),))
    entries = _build_coverage_entries(
        ranked, top_n=10,
        audit_overrides={"X": ("missing_constituent_record:X",)},
    )
    assert entries[0].audit_errors == ("missing_constituent_record:X",)
