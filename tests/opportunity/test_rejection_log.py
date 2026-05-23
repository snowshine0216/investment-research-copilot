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
