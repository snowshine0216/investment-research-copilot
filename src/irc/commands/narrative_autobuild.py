from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path

from irc.commands.opportunity_cmd import (
    TOP_N_DEFAULT,
    FetchBudgetExceeded,
    FetchPlan,
    _fetch_budget,
)
from irc.fundamentals.snapshot_cache import load_latest_nav_cached as _load_latest_nav_cached
from irc.fundamentals.snapshot import _FUND_LEVEL_KINDS, build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
    write_nav_cache,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    FundLevelSnapshot,
    LookthroughTarget,
)
from irc.opportunity.lookthrough import map_lookthrough, QDII_KINDS
from irc.opportunity.types import OpportunityInput
from irc.narrative.schemas import ShortlistRow
from irc.schemas.universe import Instrument

_log = logging.getLogger(__name__)


def _narrative_autobuild_on() -> bool:
    """Independent kill-switch; default-on, IRC_NARRATIVE_AUTOBUILD=0 disables."""
    return os.environ.get("IRC_NARRATIVE_AUTOBUILD", "1") != "0"


_ACTIVE_ASSET_CLASS = "cn_equity_fund"


def _is_eligible(row: ShortlistRow) -> bool:
    """Active-fund eligibility gate; effect-free (AC1 item 001)."""
    return row.asset_class == _ACTIVE_ASSET_CLASS


def _target_for_row(row: ShortlistRow) -> LookthroughTarget:
    """Effect-free; equals map_lookthrough(inp) for a cn_equity_fund row."""
    iid = row.instrument_id
    return LookthroughTarget(
        kind="active_fund", key=f"fund_{iid}",
        display_cn=row.name_cn, provider_symbol=iid,
    )


def _fund_level_eligible_target(
    row: ShortlistRow, instr: Instrument | None,
    *, con: object,  # accepted for signature parity; unused — eligibility is instr-only
) -> LookthroughTarget | None:
    """Resolve lookthrough target from instr; return only if fund-level+provider_symbol.

    Effect-free: builds OpportunityInput skeleton (no DB). cn_equity_fund → None (item 001).
    """
    iid = row.instrument_id
    asset_class = instr.asset_class if instr else row.asset_class
    inp = OpportunityInput(
        instrument_id=iid, asset_class=asset_class,
        market=instr.market if instr else "cn_off_exchange",
        theme=instr.theme if instr else None,
        tracked_index=instr.tracked_index if instr else None,
        name_cn=instr.name_cn if instr else iid,
        role="", is_holding=False, portfolio_weight=None,
        target_band_low=None, target_band_high=None, venue_compatible=True,
    )
    target = map_lookthrough(inp)
    if (target.kind in QDII_KINDS or target.kind in _FUND_LEVEL_KINDS) and target.provider_symbol:
        return target
    return None


def _build_and_cache_fund_level_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Build one FundLevelSnapshot and cache-write it (effects edge, AC9/AC10).

    Skips write on QDII sentinel or empty source_report_quarter.
    Degrades on failure; re-raises FetchBudgetExceeded.
    """
    try:
        snap = build_snapshot(target, provider=provider)
    except FetchBudgetExceeded:
        # Budget is enforced pre-flight by autobuild_fund_level_funds; guard kept for symmetry.
        raise
    except Exception as exc:
        _log.warning("narrative_autobuild: fund-level build failed for %s — %s",
                     target.provider_symbol, exc)
        return
    if not isinstance(snap, FundLevelSnapshot):
        _log.warning(
            "narrative_autobuild: build_snapshot returned unexpected type %s for %s — skip write",
            type(snap).__name__, target.provider_symbol,
        )
        return
    if "qdii_information_unavailable" in snap.evidence_gaps or not snap.source_report_quarter:
        _log.warning("narrative_autobuild: no cacheable fund-level snapshot for %s",
                     target.provider_symbol)
        return
    to_cache = replace(snap, cache_probed_at=today_iso)
    try:
        write_nav_cache(to_cache, data_dir)
    except Exception as cache_exc:
        _log.error("narrative_autobuild: nav cache write failed for %s — %s",
                   target.provider_symbol, cache_exc)


def _build_and_cache_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Build one ActiveFundSnapshot and cache-write it (effects edge).

    Degrades on failure; re-raises FetchBudgetExceeded.
    """
    try:
        snap = build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)
    except FetchBudgetExceeded:
        raise
    except Exception as exc:
        _log.warning("narrative_autobuild: build failed for %s — %s",
                     target.provider_symbol, exc)
        return
    if not isinstance(snap, ActiveFundSnapshot):
        return
    if not snap.source_report_quarter:
        _log.warning("narrative_autobuild: empty quarter for %s — skip write",
                     target.provider_symbol)
        return
    to_cache = replace(snap, cache_probed_at=today_iso)
    try:
        write_active_fund_cache(to_cache, data_dir)
    except Exception as cache_exc:
        _log.error("narrative_autobuild: cache write failed for %s — %s",
                   target.provider_symbol, cache_exc)


def _eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *, quarter: str, data_dir: Path,
) -> tuple[ShortlistRow, ...]:
    """Active-fund rows missing a resolved-quarter cache (AC2 item 001)."""
    return tuple(
        row for row in shortlist
        if _is_eligible(row)
        and load_active_fund_cache(row.instrument_id, quarter, data_dir) is None
    )


def _fund_level_eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *,
    instr_index: dict[str, Instrument], con: object,
    data_dir: Path,
) -> tuple[tuple[ShortlistRow, LookthroughTarget], ...]:
    """Fund-level-eligible rows with NO cached nav/ snapshot (AC3)."""
    out: list[tuple[ShortlistRow, LookthroughTarget]] = []
    for row in shortlist:
        target = _fund_level_eligible_target(
            row, instr_index.get(row.instrument_id), con=con,
        )
        if target is not None and _load_latest_nav_cached(target.provider_symbol, data_dir) is None:
            out.append((row, target))
    return tuple(out)


def autobuild_active_funds(
    shortlist: tuple[ShortlistRow, ...], *, provider: object, quarter: str,
    data_dir: Path, today_iso: str,
) -> None:
    """Narrative active-fund autobuild edge (standalone, for unit-test isolation).

    No-op when IRC_NARRATIVE_AUTOBUILD=0; raises FetchBudgetExceeded pre-fetch.
    """
    if not _narrative_autobuild_on():
        return
    missing = _eligible_missing(shortlist, quarter=quarter, data_dir=data_dir)
    if not missing:
        return
    plan = FetchPlan(active_fund_misses=len(missing), active_fund_stale=0,
                     passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT)
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for row in missing:
        _build_and_cache_one(_target_for_row(row), provider=provider,
                             data_dir=data_dir, today_iso=today_iso)


def autobuild_fund_level_funds(
    shortlist: tuple[ShortlistRow, ...], *, provider: object,
    instr_index: dict[str, Instrument], con: object,
    data_dir: Path, today_iso: str,
) -> None:
    """Narrative passive fund-level autobuild edge (standalone, for unit-test isolation).

    No-op when IRC_NARRATIVE_AUTOBUILD=0; raises FetchBudgetExceeded pre-fetch (AC8/AC11).
    """
    if not _narrative_autobuild_on():
        return
    missing = _fund_level_eligible_missing(
        shortlist, instr_index=instr_index, con=con, data_dir=data_dir,
    )
    if not missing:
        return
    plan = FetchPlan(active_fund_misses=0, active_fund_stale=0, passive_misses=0,
                     passive_stale=0, top_n=TOP_N_DEFAULT, fund_level_misses=len(missing))
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for _row, target in missing:
        _build_and_cache_fund_level_one(target, provider=provider,
                                        data_dir=data_dir, today_iso=today_iso)


def autobuild_narrative(
    shortlist: tuple[ShortlistRow, ...], *, provider: object,
    instr_index: dict[str, Instrument], con: object,
    quarter: str, data_dir: Path, today_iso: str,
) -> None:
    """Shared-budget preflight over BOTH narrative autobuild edges (RD-7a).

    No-op when IRC_NARRATIVE_AUTOBUILD=0. One combined FetchPlan is checked
    pre-fetch; raises FetchBudgetExceeded before any build.
    """
    if not _narrative_autobuild_on():
        return
    active_missing = _eligible_missing(shortlist, quarter=quarter, data_dir=data_dir)
    fund_level_missing = _fund_level_eligible_missing(
        shortlist, instr_index=instr_index, con=con, data_dir=data_dir,
    )
    if not active_missing and not fund_level_missing:
        return
    plan = FetchPlan(active_fund_misses=len(active_missing), active_fund_stale=0,
                     passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT,
                     fund_level_misses=len(fund_level_missing))
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for row in active_missing:
        _build_and_cache_one(_target_for_row(row), provider=provider,
                             data_dir=data_dir, today_iso=today_iso)
    for _row, target in fund_level_missing:
        _build_and_cache_fund_level_one(target, provider=provider,
                                        data_dir=data_dir, today_iso=today_iso)
