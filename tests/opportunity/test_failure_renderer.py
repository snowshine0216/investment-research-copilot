"""Item 006 Slice H3 — failure section renderer + V1 systematic exclusion summary.

Tests cover acceptance criteria 17, 18, 24, 25, 27.
"""
from __future__ import annotations

import re


def _row(
    instrument_id="005827",
    name_cn="易方达蓝筹精选",
    asset_class="cn_equity_fund",
    evidence_gaps=("qdii_information_unavailable",),
    fetch_types_attempted=("nav",),
    opportunity_state="pause_wait",
    note_cn="暂停加仓",
    opportunity_reason="reason text",
):
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    return OpportunityRow(
        instrument_id=instrument_id,
        name_cn=name_cn,
        asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", "fund_005827", "易方达蓝筹精选", "005827",
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state=opportunity_state,
        opportunity_reason=opportunity_reason,
        evidence_gaps=evidence_gaps,
        fetch_types_attempted=fetch_types_attempted,
    )


def test_render_failure_section_single_row() -> None:
    from irc.opportunity.failure_renderer import render_failure_section
    rows = (_row(),)
    out = render_failure_section(rows)
    expected_line = (
        "- **005827 易方达蓝筹精选** ｜ 原因: qdii_information_unavailable "
        "｜ 已尝试: nav"
    )
    assert out == expected_line


def test_render_failure_section_empty_returns_no_data() -> None:
    from irc.opportunity.failure_renderer import render_failure_section
    assert render_failure_section(()) == "（无）"


def test_render_failure_section_does_not_leak_conclusion_fields() -> None:
    """Criterion 18: NO opportunity_state, dca, risk, note_cn tokens in output."""
    from irc.opportunity.failure_renderer import render_failure_section
    rows = (
        _row(
            opportunity_state="pause_wait",
            note_cn="暂停加仓",
            opportunity_reason="reason note",
        ),
    )
    out = render_failure_section(rows)
    assert "pause_wait" not in out
    assert "暂停加仓" not in out
    assert "reason note" not in out
    assert "opportunity_state" not in out
    assert "dca" not in out
    assert "risk" not in out
    assert "note_cn" not in out


def test_render_failure_section_sorts_by_asset_class_then_id() -> None:
    from irc.opportunity.failure_renderer import render_failure_section
    rows = (
        _row(instrument_id="Z", asset_class="qdii_us"),
        _row(instrument_id="A", asset_class="qdii_us"),
        _row(instrument_id="B", asset_class="cn_equity_fund"),
    )
    out = render_failure_section(rows)
    ordered_ids = re.findall(r"\*\*(\w+) ", out)
    assert ordered_ids == ["B", "A", "Z"]


def test_render_failure_section_format_regex() -> None:
    """Criterion 18: each line matches the locked regex.

    Pattern uses `.+?` for name_cn so names containing spaces (e.g. '华夏 蓝筹')
    are accepted — the canonical format is `{instrument_id} {name_cn}` where
    name_cn may contain internal spaces.
    """
    from irc.opportunity.failure_renderer import render_failure_section
    rows = (_row(),)
    out = render_failure_section(rows)
    pattern = re.compile(
        r"^- \*\*\S+ .+?\*\* ｜ 原因: .+ ｜ 已尝试: .+$"
    )
    for line in out.split("\n"):
        if line.strip():
            assert pattern.match(line), f"line does not match locked format: {line!r}"


def test_render_failure_section_format_regex_name_cn_with_spaces() -> None:
    """Nit-2 regression: name_cn containing an internal space must still match
    the criterion-18 locked format regex."""
    from irc.opportunity.failure_renderer import render_failure_section
    rows = (_row(name_cn="华夏 蓝筹"),)
    out = render_failure_section(rows)
    pattern = re.compile(
        r"^- \*\*\S+ .+?\*\* ｜ 原因: .+ ｜ 已尝试: .+$"
    )
    for line in out.split("\n"):
        if line.strip():
            assert pattern.match(line), (
                f"spaced name_cn causes criterion-18 format mismatch: {line!r}"
            )


def test_render_v1_systematic_exclusion_summary_zero_count() -> None:
    """Criterion 24: emitted unconditionally even with N=0."""
    from irc.opportunity.failure_renderer import render_v1_systematic_exclusion_summary
    out = render_v1_systematic_exclusion_summary(())
    assert out == (
        "## V1 systematic exclusions: 0 funds excluded due to "
        "US-heavy material holdings"
    )


def test_render_v1_systematic_exclusion_summary_counts_us_heavy() -> None:
    """Criterion 25: fund A has 3 of 5 US material holdings → us-heavy; fund B has 1 of 5 → not."""
    from irc.opportunity.policy_b import ConstituentCoverageEntry
    from irc.opportunity.failure_renderer import render_v1_systematic_exclusion_summary
    from irc.opportunity.rejection_log import RejectionRecord

    def _coverage(exchanges):
        return tuple(
            ConstituentCoverageEntry(
                symbol=f"S{i}", name_cn=f"S{i}",
                weight_pct=10.0 - i, weight_rank=i + 1,
                in_material_top_half=i < 5,
                exchange=ex,
                has_data_leg=True, has_info_leg=False,
                data_kind_count=1, information_kind_count=0,
                failure_reasons=(), audit_errors=(),
            )
            for i, ex in enumerate(exchanges)
        )
    fund_a = RejectionRecord(
        instrument_id="FUND_A", name_cn="A基金", asset_class="cn_equity_fund",
        rejection_reason="insufficient_info_coverage_top_half",
        decision_rule="x", rejection_at_stage="opportunity_write",
        constituent_coverage=_coverage(["US", "US", "US", "SH", "HK"]),
        fund_level_failure_reasons=(), fetch_types_attempted=(),
        evidence_gaps=("insufficient_info_coverage_top_half",),
    )
    fund_b = RejectionRecord(
        instrument_id="FUND_B", name_cn="B基金", asset_class="cn_equity_fund",
        rejection_reason="insufficient_info_coverage_top_half",
        decision_rule="x", rejection_at_stage="opportunity_write",
        constituent_coverage=_coverage(["SH", "SH", "SH", "SZ", "US"]),
        fund_level_failure_reasons=(), fetch_types_attempted=(),
        evidence_gaps=("insufficient_info_coverage_top_half",),
    )
    out = render_v1_systematic_exclusion_summary((fund_a, fund_b))
    assert out.startswith("## V1 systematic exclusions: 1 funds excluded")
    assert "FUND_A A基金" in out
    assert "FUND_B" not in out


def test_render_v1_systematic_exclusion_summary_ignores_non_quorum_reasons() -> None:
    """Only insufficient_info_coverage_top_half feeds the V1 tally."""
    from irc.opportunity.failure_renderer import render_v1_systematic_exclusion_summary
    from irc.opportunity.rejection_log import RejectionRecord
    record = RejectionRecord(
        instrument_id="X", name_cn="x", asset_class="qdii_us",
        rejection_reason="qdii_information_unavailable",
        decision_rule="x", rejection_at_stage="opportunity_write",
        constituent_coverage=(), fund_level_failure_reasons=(),
        fetch_types_attempted=(),
        evidence_gaps=("qdii_information_unavailable",),
    )
    out = render_v1_systematic_exclusion_summary((record,))
    assert "0 funds" in out
