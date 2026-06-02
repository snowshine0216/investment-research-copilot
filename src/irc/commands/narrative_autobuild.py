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
    _load_latest_nav_cached,
)
import duckdb

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
from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.types import OpportunityInput
from irc.narrative.schemas import ShortlistRow
from irc.schemas.universe import Instrument

_QDII_KINDS = ("qdii_us", "qdii_hk", "qdii_global")

_log = logging.getLogger(__name__)


def _narrative_autobuild_on() -> bool:
    """Independent kill-switch; default-on, IRC_NARRATIVE_AUTOBUILD=0 disables."""
    return os.environ.get("IRC_NARRATIVE_AUTOBUILD", "1") != "0"


_ACTIVE_ASSET_CLASS = "cn_equity_fund"


def _is_eligible(row: ShortlistRow) -> bool:
    """Eligibility gate decided before any I/O (AC1)."""
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
    *, con: object,  # accepted for signature parity but unused — eligibility is instr-only
) -> LookthroughTarget | None:
    """Resolve the row's LookthroughTarget via map_lookthrough; return it only
    when fund-level-eligible AND it carries a provider_symbol (AC1/AC2, RD-3).

    Effect-free: builds a minimal OpportunityInput skeleton from instr (no DB
    round-trip; map_lookthrough reads only asset_class/theme/tracked_index).
    cn_equity_fund routes to active_fund (item 001's domain) → excluded.
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
    eligible_kind = target.kind in _QDII_KINDS or target.kind in _FUND_LEVEL_KINDS
    if eligible_kind and target.provider_symbol:
        return target
    return None


def _build_and_cache_fund_level_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Effects edge: build one FundLevelSnapshot and cache-write it under nav/.

    Mirrors opportunity_cmd._resolve_fund_level_snapshot:374-384. Skips the write
    on the QDII sentinel (qdii_information_unavailable gap) or an empty
    source_report_quarter (path-collapse guard). Degrades on any failure (logged,
    no write); re-raises FetchBudgetExceeded.
    """
    try:
        snap = build_snapshot(target, provider=provider)
    except FetchBudgetExceeded:
        raise
    except Exception as exc:  # degrade — never crash the run (AC10)
        _log.warning("narrative_autobuild: fund-level build failed for %s — %s",
                     target.provider_symbol, exc)
        return
    if not isinstance(snap, FundLevelSnapshot):
        return
    if "qdii_information_unavailable" in snap.evidence_gaps or not snap.source_report_quarter:
        _log.warning("narrative_autobuild: no cacheable fund-level snapshot for %s",
                     target.provider_symbol)
        return
    to_cache = replace(snap, cache_probed_at=today_iso)
    try:
        write_nav_cache(to_cache, data_dir)
    except Exception as cache_exc:  # disk error is environmental — degrade
        _log.error("narrative_autobuild: nav cache write failed for %s — %s",
                   target.provider_symbol, cache_exc)


def _build_and_cache_one(
    target: LookthroughTarget, *, provider: object, data_dir: Path,
    today_iso: str,
) -> None:
    """Effects edge: build one ActiveFundSnapshot and cache-write it.

    Degrades on any failure (logged, no write); never raises. Mirrors
    opportunity_cmd.py:868-884. Skips the write on empty source_report_quarter
    to avoid the data/fundamentals//active_fund path-collapse.
    """
    try:
        snap = build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)
    except FetchBudgetExceeded:
        raise
    except Exception as exc:  # degrade — never crash the run (AC6)
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
    except Exception as cache_exc:  # disk error is environmental — degrade
        _log.error("narrative_autobuild: cache write failed for %s — %s",
                   target.provider_symbol, cache_exc)


def _eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *, quarter: str, data_dir: Path,
) -> tuple[ShortlistRow, ...]:
    """Eligible rows with NO cached snapshot for the RESOLVED quarter (AC2)."""
    out: list[ShortlistRow] = []
    for row in shortlist:
        if not _is_eligible(row):
            continue
        if load_active_fund_cache(row.instrument_id, quarter, data_dir) is None:
            out.append(row)
    return tuple(out)


def _fund_level_eligible_missing(
    shortlist: tuple[ShortlistRow, ...], *,
    instr_index: dict[str, Instrument], con: object,
    data_dir: Path,
) -> tuple[tuple[ShortlistRow, LookthroughTarget], ...]:
    """Fund-level-eligible rows with NO cached nav/ snapshot (latest-nav scan, AC3)."""
    out: list[tuple[ShortlistRow, LookthroughTarget]] = []
    for row in shortlist:
        target = _fund_level_eligible_target(
            row, instr_index.get(row.instrument_id), con=con,
        )
        if target is None:
            continue
        if _load_latest_nav_cached(target.provider_symbol, data_dir) is None:
            out.append((row, target))
    return tuple(out)


def autobuild_active_funds(
    shortlist: tuple[ShortlistRow, ...], *, provider: object, quarter: str,
    data_dir: Path, today_iso: str,
) -> None:
    """Command-layer narrative active-fund autobuild (effects edge).

    No-op when IRC_NARRATIVE_AUTOBUILD=0. Builds + caches an ActiveFundSnapshot
    for each eligible cn_equity_fund row missing a resolved-quarter cache.
    Raises FetchBudgetExceeded BEFORE any fetch when the estimate exceeds budget.
    """
    if not _narrative_autobuild_on():
        return
    missing = _eligible_missing(shortlist, quarter=quarter, data_dir=data_dir)
    if not missing:
        return
    plan = FetchPlan(
        active_fund_misses=len(missing), active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=TOP_N_DEFAULT,
    )
    total = plan.total_calls()
    budget = _fetch_budget()
    if total > budget:
        raise FetchBudgetExceeded(plan, total, budget)
    for row in missing:
        _build_and_cache_one(
            _target_for_row(row), provider=provider, data_dir=data_dir,
            today_iso=today_iso,
        )
