"""Item 006 Slice H1 — rejection log dataclasses + atomic JSON writer.

Reads gapped `OpportunityRow`s + their (optional) `PolicyBVerdict`s and emits
the canonical `outputs/{date}/rejections.json` audit trail. Empty-rejections
case still writes `entries: []` (criterion 6).

See ADR 0003 §4 for the atomic-write-at-end decision and §2 for the three-field
failure taxonomy (`failure_reasons` / `evidence_gaps` / `audit_errors`).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot
from irc.io_utils import atomic_write_text
from irc.opportunity.policy_b import ConstituentCoverageEntry, PolicyBVerdict
from irc.opportunity.types import OpportunityRow


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


_GAP_TO_REASON: dict[str, RejectionReasonCode] = {
    "qdii_information_unavailable":         "qdii_information_unavailable",
    "holdings_fetch_failed":                "holdings_fetch_failed",
    "incomplete_constituent_record":        "incomplete_constituent_record",
    "incomplete_constituent_data":          "incomplete_constituent_data",
    "insufficient_info_coverage_top_half":  "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage":      "incomplete_constituent_coverage",
    "fund_nav_unavailable":                 "fund_nav_unavailable",
    # Non-Policy-B evidence gaps emitted by states.py for data-poor instruments
    # (ETF/passive rows where constituent-level data is unavailable):
    "missing_valuation_data":               "incomplete_constituent_data",
    "missing_flow_or_return_data":          "incomplete_constituent_data",
    "missing_product_metadata":             "incomplete_constituent_record",
}


def _decision_rule_for(
    row: OpportunityRow,
    verdict: PolicyBVerdict | None,
) -> str:
    """Compose the `decision_rule` string for a rejection record.

    - Active-fund rows: use `verdict.decision_rule` (carries the info-leg
      quorum math from Policy B).
    - Non-active-fund rows (FundLevelSnapshot QDII sentinel / NAV-failed /
      legacy ConstituentSnapshot): verdict is None → fall back to a
      template-format-locked string composed from the first gap code.
    """
    if verdict is not None:
        return verdict.decision_rule
    first = row.evidence_gaps[0] if row.evidence_gaps else "unknown"
    return f"{first} (non-active-fund row; no Policy B verdict)"


def record_fund_rejection(
    *,
    row: OpportunityRow,
    snapshot: ActiveFundSnapshot | FundLevelSnapshot | None,
    verdict: PolicyBVerdict | None,
    rejection_reason: RejectionReasonCode,
    decision_rule: str,
    rejection_at_stage: Literal[
        "opportunity_build", "opportunity_write"
    ] = "opportunity_write",
) -> RejectionRecord:
    """Pure builder. Composes a RejectionRecord from a gapped row + the
    (optional) per-fund snapshot + (optional) Policy B verdict.

    `verdict` is `None` for non-active-fund rows (FundLevelSnapshot QDII /
    NAV-failed / legacy ConstituentSnapshot). When present, the verdict's
    `constituent_coverage` is propagated verbatim.
    """
    if verdict is not None:
        coverage = verdict.constituent_coverage
    else:
        coverage = ()

    if isinstance(snapshot, ActiveFundSnapshot):
        fund_level_failure_reasons = snapshot.fund_level_failure_reasons
    elif isinstance(snapshot, FundLevelSnapshot):
        fund_level_failure_reasons = snapshot.fund_level_failure_reasons
    else:
        fund_level_failure_reasons = ()

    return RejectionRecord(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        rejection_reason=rejection_reason,
        decision_rule=decision_rule,
        rejection_at_stage=rejection_at_stage,
        constituent_coverage=coverage,
        fund_level_failure_reasons=fund_level_failure_reasons,
        fetch_types_attempted=row.fetch_types_attempted,
        evidence_gaps=row.evidence_gaps,
    )


def _record_sort_key(record: RejectionRecord) -> tuple[str, str]:
    return (record.asset_class, record.instrument_id)


def write_rejections_json(
    document: RejectionsDocument,
    out_dir: Path,
) -> None:
    """Atomic write of `outputs/{date}/rejections.json`.

    Parent dir auto-created. Empty-entries case writes `entries: []` rather
    than skipping (stable presence is the monitoring signal). Determinism:
    entries are sorted by `(asset_class, instrument_id)` ascending before
    serialisation.

    Uses `atomic_write_text` from `irc.io_utils` (the project I/O convention —
    `tmpfile + os.replace + fsync`, identical to item 003's snapshot cache).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    sorted_entries = tuple(sorted(document.entries, key=_record_sort_key))
    sorted_doc = RejectionsDocument(
        run_date=document.run_date,
        plan_hash=document.plan_hash,
        entries=sorted_entries,
    )
    payload = asdict(sorted_doc)
    atomic_write_text(
        out_dir / "rejections.json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
    )


def _classify_rejection_reason(row: OpportunityRow) -> RejectionReasonCode:
    """Return the dominant RejectionReasonCode for a gapped row.

    Precedence: iterates `row.evidence_gaps` in row order; the first gap that
    matches a key in `_GAP_TO_REASON` (dict-literal insertion order) wins.
    QDII precedes Policy B codes by construction.

    Raises RuntimeError on unknown gap codes — defence against silent
    acceptance of new codes that bypass the rejection log (criterion 19).
    Pre-scan: ALL gaps are validated before returning any result, so a row
    with mixed known + unknown codes raises rather than silently returning
    the first-match.
    """
    unknown = [gap for gap in row.evidence_gaps if gap not in _GAP_TO_REASON]
    if unknown:
        raise RuntimeError(
            f"unknown evidence_gap code: {unknown[0]!r} not in _GAP_TO_REASON "
            f"(row {row.instrument_id}, all gaps: {row.evidence_gaps})"
        )
    for gap in row.evidence_gaps:
        if gap in _GAP_TO_REASON:
            return _GAP_TO_REASON[gap]
    raise RuntimeError(
        f"row {row.instrument_id} carries unrecognised evidence_gaps: "
        f"{row.evidence_gaps}"
    )
