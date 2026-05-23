"""Item 006 Slice H1 — rejection log dataclasses + atomic JSON writer.

Reads gapped `OpportunityRow`s + their (optional) `PolicyBVerdict`s and emits
the canonical `outputs/{date}/rejections.json` audit trail. Empty-rejections
case still writes `entries: []` (criterion 6).

See ADR 0003 §4 for the atomic-write-at-end decision and §2 for the three-field
failure taxonomy (`failure_reasons` / `evidence_gaps` / `audit_errors`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from irc.opportunity.policy_b import ConstituentCoverageEntry


RejectionReasonCode = Literal[
    "holdings_fetch_failed",
    "incomplete_constituent_record",
    "incomplete_constituent_data",
    "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage",
    "qdii_information_unavailable",
    "fund_nav_unavailable",
    "missing_us_news_adapter",
]


@dataclass(frozen=True)
class RejectionRecord:
    """One entry in `rejections.json`. Built by `record_fund_rejection`."""
    instrument_id: str
    name_cn: str
    asset_class: str
    rejection_reason: RejectionReasonCode
    decision_rule: str
    rejection_at_stage: Literal["opportunity_build", "opportunity_write"]
    constituent_coverage: tuple[ConstituentCoverageEntry, ...]
    fund_level_failure_reasons: tuple[str, ...]
    fetch_types_attempted: tuple[str, ...]
    evidence_gaps: tuple[str, ...]


@dataclass(frozen=True)
class RejectionsDocument:
    """Top-level container serialised to `outputs/{date}/rejections.json`.

    `entries` ordered by `(asset_class, instrument_id)` ascending (criterion 5).
    """
    run_date: str
    plan_hash: str
    entries: tuple[RejectionRecord, ...]


# Populated in task 9 — full classifier.
_GAP_TO_REASON: dict[str, RejectionReasonCode] = {
    "qdii_information_unavailable":         "qdii_information_unavailable",
    "holdings_fetch_failed":                "holdings_fetch_failed",
    "incomplete_constituent_record":        "incomplete_constituent_record",
    "incomplete_constituent_data":          "incomplete_constituent_data",
    "insufficient_info_coverage_top_half":  "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage":      "incomplete_constituent_coverage",
    "fund_nav_unavailable":                 "fund_nav_unavailable",
}
