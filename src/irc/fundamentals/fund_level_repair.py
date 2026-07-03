"""Fund-level evidence repair (repair probe) — todos-critical-fixes item 004.

The third cached-active-fund fetch class beside the full refetch (~35 calls)
and the fail-closed freshness probe (1 call): when a cached foreign-heavy
`ActiveFundSnapshot` serves with a rule-2.5 leg gap
(`foreign_heavy_fund_level_gap` in `irc.opportunity.policy_b`), ONLY the
fund-level legs are re-fetched (4 AkShare calls: 1 NAV + 3 announcement
endpoints) and leg-wise merged into the snapshot.

Pure merge (`merge_fund_level_evidence`) is separated from the single I/O
edge (`refetch_fund_level_evidence`) per repo conventions. See CONTEXT.md
"Fund-level evidence repair (repair probe)" and ADR 0003 §7.
"""
from __future__ import annotations

from dataclasses import replace
import logging

from irc.fundamentals.snapshot import _fetch_active_fund_level_evidence
from irc.fundamentals.types import ActiveFundSnapshot, ThesisEvidence

_log = logging.getLogger(__name__)


def _leg(
    evidence: tuple[ThesisEvidence, ...], kind: str,
) -> tuple[ThesisEvidence, ...]:
    """All entries of one `citation_kind`, original order preserved."""
    return tuple(e for e in evidence if e.citation_kind == kind)


def _merged_failure_reasons(
    snap: ActiveFundSnapshot, merged: tuple[ThesisEvidence, ...],
) -> tuple[str, ...]:
    """Re-pin the producer invariant: leg-failure string present ⟺ leg absent.

    Both leg-failure strings are stripped, then re-appended — NAV first, then
    announcements, the producer order of `_fetch_active_fund_level_evidence`
    (snapshot.py:505-506, :522-523) — iff the MERGED evidence lacks that leg.
    Unrelated reasons (e.g. `holdings_quarter_parse_failed:{fund_id}`) are
    preserved in their original relative order.
    """
    nav_failure = f"fund_nav_unavailable:{snap.fund_id}"
    ann_failure = f"fund_announcements_unavailable:{snap.fund_id}"
    kept = tuple(
        r for r in snap.fund_level_failure_reasons
        if r not in (nav_failure, ann_failure)
    )
    if not _leg(merged, "data"):
        kept = kept + (nav_failure,)
    if not _leg(merged, "information"):
        kept = kept + (ann_failure,)
    return kept


def merge_fund_level_evidence(
    snap: ActiveFundSnapshot,
    evidence: tuple[ThesisEvidence, ...],
    failures: list[str],
) -> ActiveFundSnapshot:
    """Leg-wise monotone merge of a fresh fund-level fetch into `snap` (pure).

    Per leg (by `citation_kind`): the fresh entries win when the refetch
    produced ≥1 entry for that leg; the cached entries are retained when it
    didn't (grill R3 — full replacement would drop a surviving cached leg
    under the 2026-06-21 throttle pattern and oscillate instead of healing).
    The merged tuple orders the data leg first, then the information leg
    (the producer order — NAV then announcements). Leg presence is monotone
    non-decreasing across a repair.

    `failures` — the fresh fetch's failure list — is accepted for signature
    parity with the producer but deliberately NOT merged: leg-failure strings
    are recomputed from leg ABSENCE in the merged evidence via
    `_merged_failure_reasons` (appending a fresh leg-failure while the merge
    retains that cached leg would break the producer invariant).
    Every other field — including `cache_probed_at` — is byte-identical:
    the repair is orthogonal to holdings-quarter freshness.
    """
    merged = (
        (_leg(evidence, "data") or _leg(snap.fund_level_evidence, "data"))
        + (_leg(evidence, "information")
           or _leg(snap.fund_level_evidence, "information"))
    )
    return replace(
        snap,
        fund_level_evidence=merged,
        fund_level_failure_reasons=_merged_failure_reasons(snap, merged),
    )


def refetch_fund_level_evidence(snap: ActiveFundSnapshot) -> ActiveFundSnapshot:
    """Fail-safe I/O edge: 4-call fund-level refetch merged via the pure merge.

    4 AkShare calls (1 NAV + 3 announcement endpoints) through the existing
    `_fetch_active_fund_level_evidence` (same-package private import;
    precedent: `opportunity_cmd.py` imports `_FUND_LEVEL_KINDS`). ANY
    exception → returns `snap` unchanged — a repair attempt must never crash
    a row build that previously served fine from cache (spec AC3;
    `fetch_fund_announcements` documents "Never raises" but this wrapper
    does not rely on that).
    """
    try:
        evidence, failures = _fetch_active_fund_level_evidence(snap.fund_id)
    except Exception as exc:
        detail = str(exc)
        if len(detail) > 200:
            detail = detail[:200] + "..."
        _log.warning(
            "fund_level_repair refetch failed fund_id=%s exc_type=%s detail=%s "
            "— serving cached snapshot unchanged",
            snap.fund_id, type(exc).__name__, detail,
        )
        return snap
    return merge_fund_level_evidence(snap, evidence, failures)
