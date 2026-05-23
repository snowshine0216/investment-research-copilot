"""Item 006 Slice H1 — rejection_log schema + writer + classifier tests.

Tests cover acceptance criteria 1–7, 19, 22, 26.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_rejection_reason_code_literal_values() -> None:
    """Criterion 19: closed Literal of reason codes."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    expected = {
        "holdings_fetch_failed",
        "incomplete_constituent_record",
        "incomplete_constituent_data",
        "insufficient_info_coverage_top_half",
        "incomplete_constituent_coverage",
        "qdii_information_unavailable",
        "fund_nav_unavailable",
    }
    assert expected.issubset(set(_GAP_TO_REASON.values()))


def test_rejection_record_construction() -> None:
    from irc.opportunity.policy_b import ConstituentCoverageEntry
    from irc.opportunity.rejection_log import RejectionRecord

    coverage = (
        ConstituentCoverageEntry(
            symbol="600519", name_cn="贵州茅台", weight_pct=8.2, weight_rank=1,
            in_material_top_half=True, exchange="SH",
            has_data_leg=True, has_info_leg=True,
            data_kind_count=1, information_kind_count=1,
            failure_reasons=(), audit_errors=(),
        ),
    )
    r = RejectionRecord(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        rejection_reason="insufficient_info_coverage_top_half",
        decision_rule="info-leg quorum 5 of 10; 3 of material top-half satisfied",
        rejection_at_stage="opportunity_write",
        constituent_coverage=coverage,
        fund_level_failure_reasons=(),
        fetch_types_attempted=("filing", "broker", "news"),
        evidence_gaps=("insufficient_info_coverage_top_half",),
    )
    assert r.instrument_id == "005827"
    assert r.constituent_coverage[0].symbol == "600519"


def test_rejections_document_construction() -> None:
    from irc.opportunity.rejection_log import RejectionsDocument
    d = RejectionsDocument(
        run_date="2026-05-23",
        plan_hash="a3f9c1b2d8e4",
        entries=(),
    )
    assert d.run_date == "2026-05-23"
    assert d.entries == ()


def _row(evidence_gaps=()):
    """Tiny OpportunityRow factory with default conclusion fields."""
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    return OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", "fund_005827", "易方达蓝筹精选", "005827",
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
    )


def test_classify_rejection_reason_qdii_first_precedence() -> None:
    """Edge case: row carries both qdii_information_unavailable AND a Policy B code.
    Classifier returns the QDII reason (dict-literal order)."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=(
        "qdii_information_unavailable",
        "insufficient_info_coverage_top_half",
    ))
    assert _classify_rejection_reason(row) == "qdii_information_unavailable"


def test_classify_rejection_reason_holdings_fetch_failed() -> None:
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=("holdings_fetch_failed",))
    assert _classify_rejection_reason(row) == "holdings_fetch_failed"


def test_classify_rejection_reason_insufficient_info_quorum() -> None:
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=("insufficient_info_coverage_top_half",))
    assert _classify_rejection_reason(row) == "insufficient_info_coverage_top_half"


def test_classify_rejection_reason_unknown_gap_raises_runtime_error() -> None:
    """Criterion 19: adding a new gap code without updating _GAP_TO_REASON raises."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=("unknown_synthetic_gap",))
    with pytest.raises(RuntimeError) as exc_info:
        _classify_rejection_reason(row)
    assert "unknown_synthetic_gap" in str(exc_info.value)


def test_classify_rejection_reason_empty_gaps_raises() -> None:
    """Defensive: a row with empty evidence_gaps in the gapped partition is a bug."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=())
    with pytest.raises(RuntimeError):
        _classify_rejection_reason(row)


def _active_fund_snapshot(
    constituent_analyses=(),
    fund_level_failure_reasons=(),
):
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=constituent_analyses,
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
    )


def _verdict_for(snapshot, top_n=10):
    from irc.opportunity.policy_b import evaluate_policy_b
    return evaluate_policy_b(snapshot, top_n=top_n)


def test_record_fund_rejection_with_active_fund_verdict() -> None:
    """Criterion 1: every required field is populated from the verdict + row + snapshot."""
    from irc.opportunity.rejection_log import record_fund_rejection
    snap = _active_fund_snapshot(
        fund_level_failure_reasons=("holdings_fetch_failed:005827:Timeout",),
    )
    verdict = _verdict_for(snap)
    row = _row(evidence_gaps=("holdings_fetch_failed",))
    record = record_fund_rejection(
        row=row,
        snapshot=snap,
        verdict=verdict,
        rejection_reason="holdings_fetch_failed",
        decision_rule="holdings adapter empty/failed",
    )
    assert record.instrument_id == "005827"
    assert record.name_cn == "易方达蓝筹精选"
    assert record.asset_class == "cn_equity_fund"
    assert record.rejection_reason == "holdings_fetch_failed"
    assert record.decision_rule == "holdings adapter empty/failed"
    assert record.rejection_at_stage == "opportunity_write"
    assert record.fund_level_failure_reasons == ("holdings_fetch_failed:005827:Timeout",)
    assert record.evidence_gaps == ("holdings_fetch_failed",)


def test_record_fund_rejection_with_no_verdict_non_active_fund_row() -> None:
    """G-Q6: FundLevelSnapshot rows have no Policy B verdict. Fallback decision_rule."""
    from irc.opportunity.rejection_log import (
        _decision_rule_for,
        record_fund_rejection,
    )
    row = _row(evidence_gaps=("qdii_information_unavailable",))
    rule = _decision_rule_for(row, verdict=None)
    record = record_fund_rejection(
        row=row,
        snapshot=None,
        verdict=None,
        rejection_reason="qdii_information_unavailable",
        decision_rule=rule,
    )
    assert record.constituent_coverage == ()
    assert record.fund_level_failure_reasons == ()
    assert "qdii_information_unavailable" in record.decision_rule


def test_decision_rule_for_active_fund_uses_verdict() -> None:
    from irc.opportunity.rejection_log import _decision_rule_for
    snap = _active_fund_snapshot(
        fund_level_failure_reasons=("holdings_fetch_failed:fund:Boom",),
    )
    verdict = _verdict_for(snap)
    row = _row(evidence_gaps=("holdings_fetch_failed",))
    rule = _decision_rule_for(row, verdict=verdict)
    assert rule == "holdings adapter empty/failed"


def test_decision_rule_for_non_active_fund_template_locked() -> None:
    """Template-format locked (extends criterion 11 to fallback path)."""
    from irc.opportunity.rejection_log import _decision_rule_for
    row = _row(evidence_gaps=("qdii_information_unavailable",))
    rule = _decision_rule_for(row, verdict=None)
    assert rule == "qdii_information_unavailable (non-active-fund row; no Policy B verdict)"


def test_record_fund_rejection_uses_fund_level_failure_reasons_from_fund_level_snapshot() -> None:
    from irc.fundamentals.types import FundLevelSnapshot
    from irc.opportunity.rejection_log import record_fund_rejection
    snap = FundLevelSnapshot(
        fund_id="518880",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        fund_level_failure_reasons=("nav_fetch_failed:518880:Timeout",),
        evidence_gaps=("fund_nav_unavailable",),
    )
    row = _row(evidence_gaps=("fund_nav_unavailable",))
    record = record_fund_rejection(
        row=row,
        snapshot=snap,
        verdict=None,
        rejection_reason="fund_nav_unavailable",
        decision_rule="fund_nav_unavailable (non-active-fund row; no Policy B verdict)",
    )
    assert record.fund_level_failure_reasons == ("nav_fetch_failed:518880:Timeout",)
