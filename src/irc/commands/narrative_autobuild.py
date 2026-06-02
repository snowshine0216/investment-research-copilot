from __future__ import annotations

import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from irc.commands.opportunity_cmd import (
    TOP_N_DEFAULT,
    FetchBudgetExceeded,
    FetchPlan,
    _fetch_budget,
)
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot, LookthroughTarget
from irc.narrative.schemas import ShortlistRow

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
        sys.stderr.write(
            f"cache_write_failed:{target.provider_symbol}:"
            f"{type(cache_exc).__name__}\n"
        )
