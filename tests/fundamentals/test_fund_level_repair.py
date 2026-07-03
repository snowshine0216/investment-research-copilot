"""Mirror tests for `src/irc/fundamentals/fund_level_repair.py` (item 004).

Locks the leg-wise monotone merge (grill R3) — the four named AC2 cases —
plus the producer invariant (leg-failure string present ⟺ leg absent in
MERGED evidence), field/immutability guarantees, and the fail-safe refetch
wrapper (AC3).
"""
from __future__ import annotations

import copy


def _fund_evidence(kind: str, *, fund_id: str = "006809", summary: str = ""):
    """Fund-level ThesisEvidence in the exact producer shapes
    (`_fetch_active_fund_level_evidence`, snapshot.py:489-524)."""
    from irc.fundamentals.types import ThesisEvidence
    if kind == "data":
        return ThesisEvidence(
            type="snapshot", source=fund_id, url="", date="2026-07-01",
            summary=summary or "NAV=1.5000 @ 2026-07-01",
            scope="instrument", citation_kind="data",
            owner_instrument_id=fund_id, parent_fund_id=None,
            constituent_key=None,
        )
    return ThesisEvidence(
        type="news", source="fund_announcement_report_em", url="",
        date="2026-07-01", summary=summary or "[REP-001] 季度报告",
        scope="instrument", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=None,
        constituent_key=None,
    )


def _snap(fund_level_evidence=(), fund_level_failure_reasons=()):
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="006809",
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at="2026-07-01",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
        fund_level_evidence=fund_level_evidence,
    )


# ── merge_fund_level_evidence: the four named AC2 cases ──────────────────────

def test_merge_cached_info_only_plus_fresh_data_only_heals_both_legs() -> None:
    """AC2 case 1 — the heal-under-throttle case (the TODO's own motivating
    shape): NAV recovered, announcements still throttled the other way round.
    Full replacement would SWAP legs and oscillate; the leg-wise merge heals
    to BOTH legs in one run with zero leg-failure strings."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information", summary="[OLD-1] 旧公告")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    fresh_data = _fund_evidence("data")
    merged = merge_fund_level_evidence(
        snap, (fresh_data,), ["fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == (fresh_data, cached_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_cached_data_only_plus_fresh_info_only_heals_both_legs() -> None:
    """AC2 case 2 — mirror direction; merged tuple stays data-leg-first."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_data = _fund_evidence("data", summary="NAV=1.4000 @ 2026-06-01")
    snap = _snap(
        fund_level_evidence=(cached_data,),
        fund_level_failure_reasons=("fund_announcements_unavailable:006809",),
    )
    fresh_info = _fund_evidence("information")
    merged = merge_fund_level_evidence(
        snap, (fresh_info,), ["fund_nav_unavailable:006809"],
    )
    assert merged.fund_level_evidence == (cached_data, fresh_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_cached_empty_plus_fresh_both_takes_fresh_verbatim() -> None:
    """AC2 case 3."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    fresh = (_fund_evidence("data"), _fund_evidence("information"))
    merged = merge_fund_level_evidence(snap, fresh, [])
    assert merged.fund_level_evidence == fresh
    assert merged.fund_level_failure_reasons == ()


def test_merge_fresh_empty_keeps_cached_evidence_byte_identical() -> None:
    """AC2 case 4 — both fetch legs failed → merged evidence byte-identical
    to cached (so the AC4 call site writes nothing); leg-failure strings
    re-pinned to merged-leg absence (data still missing → nav failure only)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    merged = merge_fund_level_evidence(
        snap, (),
        ["fund_nav_unavailable:006809", "fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == snap.fund_level_evidence
    assert merged.fund_level_failure_reasons == ("fund_nav_unavailable:006809",)


# ── merge: monotonicity, failure-reason invariant, immutability ──────────────

def test_merge_fresh_leg_wins_over_cached_leg_when_produced() -> None:
    """Fresh entries replace the cached leg they cover; the other cached leg
    is retained untouched (leg presence monotone non-decreasing)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_data = _fund_evidence("data", summary="NAV=1.4000 @ 2026-06-01")
    cached_info = _fund_evidence("information", summary="[OLD-1] 旧公告")
    snap = _snap(fund_level_evidence=(cached_data, cached_info))
    fresh_data = _fund_evidence("data", summary="NAV=1.5000 @ 2026-07-01")
    merged = merge_fund_level_evidence(snap, (fresh_data,), [])
    assert merged.fund_level_evidence == (fresh_data, cached_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_preserves_unrelated_failure_reasons_in_order() -> None:
    """Both leg-failure strings stripped; unrelated reasons keep their
    original relative order; missing-leg failures re-appended NAV-first
    (the producer order, snapshot.py:505-506/:522-523)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "holdings_quarter_parse_failed:006809",
            "fund_nav_unavailable:006809",
            "cache_write_failed:006809:OSError",
            "fund_announcements_unavailable:006809",
        ),
    )
    fresh = (_fund_evidence("data"),)
    merged = merge_fund_level_evidence(
        snap, fresh, ["fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == fresh
    assert merged.fund_level_failure_reasons == (
        "holdings_quarter_parse_failed:006809",
        "cache_write_failed:006809:OSError",
        "fund_announcements_unavailable:006809",
    )


def test_merge_returns_new_instance_all_other_fields_identical() -> None:
    """New frozen instance; input unmutated; every field other than the two
    merged ones — INCLUDING cache_probed_at — byte-identical (AC2)."""
    from dataclasses import replace
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    before = copy.deepcopy(snap)
    merged = merge_fund_level_evidence(snap, (_fund_evidence("data"),), [])
    assert merged is not snap
    assert snap == before, "input snapshot must not be mutated"
    assert merged.cache_probed_at == snap.cache_probed_at
    assert replace(
        merged,
        fund_level_evidence=snap.fund_level_evidence,
        fund_level_failure_reasons=snap.fund_level_failure_reasons,
    ) == snap


# ── refetch_fund_level_evidence: fail-safe I/O edge (AC3) ────────────────────

def test_refetch_raising_fetch_returns_snapshot_unchanged(monkeypatch) -> None:
    """AC3 — ANY exception from the fetch → original snapshot returned;
    no exception escapes (a repair attempt must never crash a row build
    that previously served fine from cache)."""
    from irc.fundamentals.fund_level_repair import refetch_fund_level_evidence

    def _boom(fund_id):
        raise ConnectionError("akshare 502")

    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        _boom,
    )
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    out = refetch_fund_level_evidence(snap)
    assert out is snap


def test_refetch_success_merges_fresh_evidence(monkeypatch) -> None:
    from irc.fundamentals.fund_level_repair import refetch_fund_level_evidence
    fresh = (_fund_evidence("data"), _fund_evidence("information"))
    seen: list[str] = []
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: (seen.append(fund_id) or fresh, []),
    )
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    out = refetch_fund_level_evidence(snap)
    assert seen == ["006809"]
    assert out.fund_level_evidence == fresh
    assert out.fund_level_failure_reasons == ()
