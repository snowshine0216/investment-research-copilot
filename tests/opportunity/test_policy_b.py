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


def _snapshot(analyses=(), fund_level_failure_reasons=()):
    """Tiny ActiveFundSnapshot factory."""
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=analyses,
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
    )


def test_evaluate_policy_b_rule_1_holdings_fetch_failed() -> None:
    from irc.opportunity.policy_b import evaluate_policy_b
    snap = _snapshot(
        analyses=(),
        fund_level_failure_reasons=("holdings_fetch_failed:005827:Timeout",),
    )
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("holdings_fetch_failed",)
    assert v.decision_rule == "holdings adapter empty/failed"
    assert v.constituent_coverage == ()
    assert v.material_symbols == ()


def test_evaluate_policy_b_rule_2_missing_constituent_record_audit_error() -> None:
    """Constituent with evidence==() AND failure_reasons==() is shape-corrupt."""
    from irc.opportunity.policy_b import evaluate_policy_b
    analyses = (
        _ca("600519", 6.0, evidence=(), failure_reasons=()),  # ← audit error
        _ca("000333", 4.0, evidence=(), failure_reasons=()),  # ← audit error
    )
    snap = _snapshot(analyses=analyses)
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("incomplete_constituent_record",)
    assert "missing_constituent_record:600519" in v.audit_errors
    assert "missing_constituent_record:000333" in v.audit_errors
    assert v.decision_rule == "missing constituent records: 2 of 10"


def test_evaluate_policy_b_rule_2_coverage_entries_carry_audit_errors() -> None:
    """The coverage entry for an audit-error symbol carries the audit_errors string."""
    from irc.opportunity.policy_b import evaluate_policy_b
    analyses = (
        _ca("600519", 6.0, evidence=(), failure_reasons=()),
    )
    snap = _snapshot(analyses=analyses)
    v = evaluate_policy_b(snap, top_n=10)
    [entry] = [e for e in v.constituent_coverage if e.symbol == "600519"]
    assert entry.audit_errors == ("missing_constituent_record:600519",)


def test_evaluate_policy_b_empty_analyses_no_failure_reason_defensive_path() -> None:
    """Edge case: len(constituent_analyses)==0 AND fund_level_failure_reasons==()."""
    from irc.opportunity.policy_b import evaluate_policy_b
    snap = _snapshot(analyses=(), fund_level_failure_reasons=())
    v = evaluate_policy_b(snap, top_n=10)
    assert v.gap_codes == ("incomplete_constituent_record",)
    assert v.audit_errors == ("empty_constituent_analyses_without_failure_reason",)
    assert v.decision_rule == "empty constituent_analyses; 0 of 10 holdings"


def test_evaluate_policy_b_does_not_mutate_input_snapshot_cache_file(tmp_path) -> None:
    """Spec edge case: replace(c, audit_errors=...) does NOT modify the cached snapshot."""
    import hashlib
    import json
    from irc.opportunity.policy_b import evaluate_policy_b
    analyses = (
        _ca("600519", 6.0, evidence=(), failure_reasons=()),  # forces rule 2
    )
    snap = _snapshot(analyses=analyses)
    # Serialise the snapshot pre-evaluation.
    pre = json.dumps({
        "fund_id": snap.fund_id,
        "constituent_analyses": [
            {
                "symbol": c.symbol,
                "weight_pct": c.weight_pct,
                "audit_errors": list(c.audit_errors),
            }
            for c in snap.constituent_analyses
        ],
    }, sort_keys=True).encode("utf-8")
    pre_sha = hashlib.sha256(pre).hexdigest()
    # Evaluate Policy B.
    _ = evaluate_policy_b(snap, top_n=10)
    # Re-serialise the SAME snapshot object; sha must be unchanged.
    post = json.dumps({
        "fund_id": snap.fund_id,
        "constituent_analyses": [
            {
                "symbol": c.symbol,
                "weight_pct": c.weight_pct,
                "audit_errors": list(c.audit_errors),
            }
            for c in snap.constituent_analyses
        ],
    }, sort_keys=True).encode("utf-8")
    post_sha = hashlib.sha256(post).hexdigest()
    assert pre_sha == post_sha
