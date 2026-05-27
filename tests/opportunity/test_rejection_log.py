"""Item 006 Slice H1 — rejection_log schema + writer + classifier tests.

Tests cover acceptance criteria 1–7, 19, 22, 26.
"""
from __future__ import annotations

import json

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


def test_classify_rejection_reason_qdii_precedence_holds_when_qdii_gap_last() -> None:
    """Regression — pre-item-008 the classifier iterated `evidence_gaps` tuple
    order, so a structural gap appearing FIRST in the tuple wrongly won the
    classification. The fix iterates `_GAP_TO_REASON.items()` (dict-literal
    order) so QDII wins regardless of tuple ordering. Lock both tuple shapes."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=(
        "insufficient_info_coverage_top_half",
        "qdii_information_unavailable",
    ))
    assert _classify_rejection_reason(row) == "qdii_information_unavailable"


def test_gap_to_reason_first_key_locks_qdii_precedence() -> None:
    """Structural invariant — the precedence semantics depend on
    `qdii_information_unavailable` being the FIRST key in `_GAP_TO_REASON`'s
    dict-literal insertion order. A contributor reordering the dict would
    silently change precedence; lock this with a machine-checked assertion."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    assert next(iter(_GAP_TO_REASON)) == "qdii_information_unavailable", (
        "_GAP_TO_REASON insertion order MUST place qdii_information_unavailable "
        "first — its precedence over Policy B / structural gaps is the contract "
        "tested by the AC11 adversarial integration test"
    )


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


def test_write_rejections_json_writes_file_with_full_schema(tmp_path) -> None:
    """Criterion 4 + 26: atomic write, JSON has run_date/plan_hash/entries keys."""
    from irc.opportunity.policy_b import ConstituentCoverageEntry
    from irc.opportunity.rejection_log import (
        RejectionRecord,
        RejectionsDocument,
        write_rejections_json,
    )
    coverage = (
        ConstituentCoverageEntry(
            symbol="600519", name_cn="贵州茅台", weight_pct=8.2, weight_rank=1,
            in_material_top_half=True, exchange="SH",
            has_data_leg=True, has_info_leg=True,
            data_kind_count=1, information_kind_count=1,
            failure_reasons=(), audit_errors=(),
        ),
    )
    record = RejectionRecord(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        rejection_reason="insufficient_info_coverage_top_half",
        decision_rule="info-leg quorum 5 of 10; 3 of material top-half satisfied",
        rejection_at_stage="opportunity_write",
        constituent_coverage=coverage,
        fund_level_failure_reasons=(),
        fetch_types_attempted=("filing", "broker", "news"),
        evidence_gaps=("insufficient_info_coverage_top_half",),
    )
    doc = RejectionsDocument(
        run_date="2026-05-23",
        plan_hash="abc123",
        entries=(record,),
    )
    out_dir = tmp_path / "outputs" / "2026-05-23"
    write_rejections_json(doc, out_dir)
    path = out_dir / "rejections.json"
    assert path.exists()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["run_date"] == "2026-05-23"
    assert body["plan_hash"] == "abc123"
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["instrument_id"] == "005827"
    assert entry["rejection_reason"] == "insufficient_info_coverage_top_half"
    assert entry["constituent_coverage"][0]["weight_rank"] == 1
    assert entry["constituent_coverage"][0]["in_material_top_half"] is True


def test_write_rejections_json_creates_parent_dir(tmp_path) -> None:
    """Criterion 4: parent dir auto-created."""
    from irc.opportunity.rejection_log import (
        RejectionsDocument,
        write_rejections_json,
    )
    out_dir = tmp_path / "deeply" / "nested" / "outputs"
    doc = RejectionsDocument(run_date="2026-05-23", plan_hash="x", entries=())
    write_rejections_json(doc, out_dir)
    assert (out_dir / "rejections.json").exists()


def test_write_rejections_json_empty_entries_still_writes(tmp_path) -> None:
    """Criterion 6: empty-rejections case writes entries: []."""
    from irc.opportunity.rejection_log import (
        RejectionsDocument,
        write_rejections_json,
    )
    out_dir = tmp_path
    doc = RejectionsDocument(run_date="2026-05-23", plan_hash="x", entries=())
    write_rejections_json(doc, out_dir)
    body = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    assert body["entries"] == []


def test_write_rejections_json_orders_entries_by_asset_class_then_id(tmp_path) -> None:
    """Criterion 5: entries sorted (asset_class, instrument_id) ascending."""
    from irc.opportunity.rejection_log import (
        RejectionRecord,
        RejectionsDocument,
        write_rejections_json,
    )
    def _rec(iid, cls):
        return RejectionRecord(
            instrument_id=iid, name_cn=iid, asset_class=cls,
            rejection_reason="qdii_information_unavailable",
            decision_rule="x", rejection_at_stage="opportunity_write",
            constituent_coverage=(), fund_level_failure_reasons=(),
            fetch_types_attempted=(), evidence_gaps=("qdii_information_unavailable",),
        )
    doc = RejectionsDocument(
        run_date="2026-05-23", plan_hash="x",
        entries=(
            _rec("Z", "qdii_us"),
            _rec("A", "qdii_us"),
            _rec("B", "cn_equity_fund"),
        ),
    )
    write_rejections_json(doc, tmp_path)
    body = json.loads((tmp_path / "rejections.json").read_text(encoding="utf-8"))
    ordered = [(e["asset_class"], e["instrument_id"]) for e in body["entries"]]
    assert ordered == [
        ("cn_equity_fund", "B"),
        ("qdii_us", "A"),
        ("qdii_us", "Z"),
    ]


def test_write_rejections_json_byte_identical_two_runs(tmp_path) -> None:
    """Criterion 5: two runs over the same fixture produce byte-identical JSON."""
    import hashlib
    from irc.opportunity.rejection_log import (
        RejectionRecord,
        RejectionsDocument,
        write_rejections_json,
    )
    record = RejectionRecord(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        rejection_reason="holdings_fetch_failed",
        decision_rule="r", rejection_at_stage="opportunity_write",
        constituent_coverage=(), fund_level_failure_reasons=(),
        fetch_types_attempted=(), evidence_gaps=("holdings_fetch_failed",),
    )
    doc = RejectionsDocument(run_date="2026-05-23", plan_hash="x", entries=(record,))
    path = tmp_path / "rejections.json"
    write_rejections_json(doc, tmp_path)
    first = hashlib.sha256(path.read_bytes()).hexdigest()
    write_rejections_json(doc, tmp_path)
    second = hashlib.sha256(path.read_bytes()).hexdigest()
    assert first == second


# ---------------------------------------------------------------------------
# P0-1 regression: mixed known + unknown gap codes must raise, not silently accept
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap_tuple", [
    ("unknown_synthetic_gap", "holdings_fetch_failed"),   # unknown-first
    ("holdings_fetch_failed", "unknown_synthetic_gap"),   # known-first
])
def test_classify_rejection_reason_mixed_known_and_unknown_raises(
    gap_tuple: tuple[str, ...],
) -> None:
    """P0-1 regression: unknown gap code alongside a known one must raise RuntimeError
    regardless of ordering (pre-scan validates ALL gaps before returning)."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=gap_tuple)
    with pytest.raises(RuntimeError, match="unknown evidence_gap code"):
        _classify_rejection_reason(row)


# ---------------------------------------------------------------------------
# P1-1 regression: legacy-path gap codes must resolve via _GAP_TO_REASON
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap_code,expected_reason", [
    ("news_stage_skipped",        "incomplete_constituent_data"),
    ("news_search_empty",         "incomplete_constituent_data"),
    ("news_llm_failed",           "incomplete_constituent_data"),
    ("missing_constituent_snapshot", "incomplete_constituent_record"),
    ("constituent_missing",       "incomplete_constituent_record"),
    ("missing_broker_coverage",   "incomplete_constituent_data"),
    # L1 fix: forward-declared H4 systematic-exclusion code must resolve
    ("missing_us_news_adapter",   "missing_us_news_adapter"),
    # Item 008 fix: fund_announcements_unavailable emitted by snapshot.py:223
    # must resolve via the dict, else criterion-19 raises at runtime.
    ("fund_announcements_unavailable", "fund_announcements_unavailable"),
])
def test_classify_rejection_reason_handles_legacy_gap_codes(
    gap_code: str, expected_reason: str,
) -> None:
    """P1-1 regression: each legacy gap code resolves to the correct RejectionReasonCode."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    row = _row(evidence_gaps=(gap_code,))
    assert _classify_rejection_reason(row) == expected_reason


# ── Item 009 Q4 — citation_gate_blocked ──────────────────────────────────────

def test_rejection_reason_code_includes_citation_gate_blocked() -> None:
    """Item 009 Q4 — citation_gate_blocked is a first-class RejectionReasonCode."""
    from irc.opportunity.rejection_log import RejectionReasonCode
    # typing.Literal exposes __args__ at runtime.
    args = set(RejectionReasonCode.__args__)
    assert "citation_gate_blocked" in args


def test_gap_to_reason_maps_citation_gate_blocked_to_self() -> None:
    """Item 009 Q4 — identity mapping (same shape as qdii_information_unavailable)."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    assert _GAP_TO_REASON["citation_gate_blocked"] == "citation_gate_blocked"


def test_gap_to_reason_citation_gate_blocked_is_last_entry() -> None:
    """Item 009 Q4 — appended at end to preserve existing precedence.
    Item 001 (decision-confidence-followup) appended `foreign_heavy_fund_level_evidence_missing`
    AFTER `citation_gate_blocked` — it is now the final entry.

    Item 008 AC11 hard-codes `qdii_information_unavailable` precedence over
    other gaps; that ordering must NOT change."""
    from irc.opportunity.rejection_log import _GAP_TO_REASON
    keys = list(_GAP_TO_REASON.keys())
    # Item 001: new last entry is the foreign-heavy code (appended after citation_gate_blocked).
    assert keys[-1] == "foreign_heavy_fund_level_evidence_missing"
    # citation_gate_blocked is second-to-last (item 009 precedent still holds).
    assert "citation_gate_blocked" in keys
    # First entry stays qdii_information_unavailable (item 008 AC11 contract).
    assert keys[0] == "qdii_information_unavailable"


def test_classify_rejection_reason_handles_citation_gate_blocked() -> None:
    """A row with only the new gap classifies cleanly (no RuntimeError)."""
    from irc.opportunity.rejection_log import _classify_rejection_reason
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    row = OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=("citation_gate_blocked",),
        thesis_evidence=(),
        constituent_analyses=(),
    )
    assert _classify_rejection_reason(row) == "citation_gate_blocked"
