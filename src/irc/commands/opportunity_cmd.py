from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, replace
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from irc.opportunity.failure_renderer import (
    render_failure_section,
    render_v1_systematic_exclusion_summary,
)
from irc.opportunity.policy_b import PolicyBVerdict, evaluate_policy_b
from irc.opportunity.rejection_log import (
    RejectionsDocument,
    _classify_rejection_reason,
    _decision_rule_for,
    record_fund_rejection,
    write_rejections_json,
)
from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.snapshot import _FUND_LEVEL_KINDS, build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    load_nav_cache,
    write_active_fund_cache,
    write_nav_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot, LookthroughTarget
from irc.config_loader import load_repo_configs
from irc.data.freshness import require_fresh_ingest
from irc.data.duckdb_helper import connect, ensure_schema
from irc.opportunity.inputs_loader import populate_inputs
from irc.io_utils import atomic_write_text
from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import (
    PositionContext,
    derive_dca_action,
    derive_risk_action,
)
from irc.opportunity.report import (
    compose_discipline_markdown,
    compose_opportunity_report,
    compose_thesis_cards_yaml,
)
from irc.commands.theme_thesis import load_theme_thesis
from irc.fundamentals.snapshot import load_latest_cached_snapshot
from irc.opportunity.lookthrough import map_lookthrough, _QDII_US_KEYS, _QDII_HK_KEYS
from irc.opportunity.selection import SelectionQuality, demote_unstable_active, reduce_same_theme
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import (
    DisciplineRow,
    OpportunityInput,
    OpportunityRow,
)
from irc.schemas.inputs import AccountFile, Holding
from irc.research.persistence import load_theme_reports
from irc.research.theme_research import ThemeReport
from irc.schemas.universe import Instrument, UniverseConfig


# ── Item 003: constants + primitives ─────────────────────────────────────────

TOP_N_DEFAULT = 10
IRC_FETCH_BUDGET_DEFAULT = 2000
IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7


@dataclass(frozen=True)
class FetchPlan:
    active_fund_misses: int
    active_fund_stale: int
    passive_misses: int
    passive_stale: int
    top_n: int
    fund_level_misses: int = 0  # Item 005: gold/bond/cn_etf rows w/ provider_symbol
    fund_level_stale: int = 0   # Item 005

    def total_calls(self) -> int:
        per_active = 1 + self.top_n * 3
        per_fund_level = 4  # 1 NAV + 3 announcement endpoints (ADR 0002 §5)
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + (self.fund_level_misses + self.fund_level_stale) * per_fund_level
            + self.passive_misses * 2
            + self.passive_stale * 2
        )


class FetchBudgetExceeded(RuntimeError):
    def __init__(self, plan: FetchPlan, total: int, budget: int) -> None:
        super().__init__(
            f"FetchBudgetExceeded: "
            f"active_fund_misses={plan.active_fund_misses} "
            f"active_fund_stale={plan.active_fund_stale} "
            f"fund_level_misses={plan.fund_level_misses} "
            f"fund_level_stale={plan.fund_level_stale} "
            f"passive_misses={plan.passive_misses} "
            f"passive_stale={plan.passive_stale} "
            f"cost={total} budget={budget}"
        )
        self.plan = plan
        self.total = total
        self.budget = budget


def compute_plan_hash(output_date: str, instrument_ids: list[str], top_n: int) -> str:
    payload = f"{output_date}:{','.join(sorted(instrument_ids))}:{top_n}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


# ── Item 003: fcntl.flock + state file ───────────────────────────────────────

try:
    import fcntl  # type: ignore[import-not-found]
    _HAS_FCNTL = True
except ImportError:
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False
    sys.stderr.write(
        "WARNING: fcntl unavailable on this platform — "
        "concurrent-run lock disabled.\n"
    )


class FetchLockBusy(RuntimeError):
    """Raised when another process holds the fetch lock."""


def _fetch_state_path(root_fundamentals: Path, plan_hash: str) -> Path:
    return root_fundamentals / f".fetch_state_{plan_hash}.json"


def load_fetch_state(root_fundamentals: Path, plan_hash: str) -> dict | None:
    """Load state file if plan_hash matches; else None (caller starts fresh)."""
    path = _fetch_state_path(root_fundamentals, plan_hash)
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    if body.get("plan_hash") != plan_hash:
        return None
    return body


def write_fetch_state(state: dict, root_fundamentals: Path, plan_hash: str) -> Path:
    path = _fetch_state_path(root_fundamentals, plan_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    # P1-g: PID-qualified tmp to prevent concurrent-writer collisions.
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def acquire_fetch_lock(path: Path) -> int:
    """Acquire an advisory exclusive lock; retry once after 100ms.

    Returns the OS file descriptor on success. Raises `FetchLockBusy` after
    second failure. Windows fallback: returns a sentinel fd, no real lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    if not _HAS_FCNTL:
        return fd  # Windows fallback: no lock.
    for attempt in (0, 1):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if attempt == 0:
                time.sleep(0.1)
                continue
            os.close(fd)
            raise FetchLockBusy(
                "concurrent run detected — set IRC_OPPORTUNITY_AUTOBUILD=0 "
                "or wait for the other run"
            )
    return fd


# ── Item 003: autobuild env var + freshness probe ─────────────────────────────

def _is_active_fund_target_autobuild_on() -> bool:
    return os.environ.get("IRC_OPPORTUNITY_AUTOBUILD", "1") != "0"


def _freshness_days() -> int:
    try:
        return int(os.environ.get("IRC_CACHE_FRESHNESS_DAYS", IRC_CACHE_FRESHNESS_DAYS_DEFAULT))
    except ValueError:
        return IRC_CACHE_FRESHNESS_DAYS_DEFAULT


def _fetch_budget() -> int:
    try:
        return int(os.environ.get("IRC_FETCH_BUDGET", IRC_FETCH_BUDGET_DEFAULT))
    except ValueError:
        return IRC_FETCH_BUDGET_DEFAULT


def _is_stale(snap: ActiveFundSnapshot, *, today: date_cls, threshold_days: int) -> bool:
    if not snap.cache_probed_at:
        return True
    try:
        probed = date_cls.fromisoformat(snap.cache_probed_at)
    except ValueError:
        return True
    days = (today - probed).days
    # P1-h: clamp negative days (future cache_probed_at = clock skew) → treat as stale.
    if days < 0:
        return True
    return days > threshold_days


def _maybe_freshness_probe(
    snap: ActiveFundSnapshot,
    *,
    today: date_cls,
    root: Path,
) -> tuple[ActiveFundSnapshot, bool]:
    """Probe and return (possibly-updated snapshot, schedule_full_refetch).

    Fail-closed: any probe failure or empty result → schedule_full_refetch=True.
    """
    if not _is_stale(snap, today=today, threshold_days=_freshness_days()):
        return snap, False
    try:
        probe = fetch_cn_etf_holdings(snap.fund_id, top_n=1)
    except Exception:
        return snap, True
    if not probe.source_report_quarter:
        # Can't determine quarter → fail-closed.
        return snap, True
    if probe.source_report_quarter != snap.source_report_quarter:
        return snap, True
    updated = replace(snap, cache_probed_at=today.isoformat())
    # P1-d: wrap cache write; disk errors are environmental — degrade gracefully.
    try:
        write_active_fund_cache(updated, root)
    except Exception as cache_exc:
        sys.stderr.write(
            f"cache_write_failed:{snap.fund_id}:{type(cache_exc).__name__}\n"
        )
        # Return stale data (not fail-closed — disk error is environmental).
        return snap, False
    return updated, False


def _load_latest_active_fund_cached(
    fund_id: str, root: Path,
) -> ActiveFundSnapshot | None:
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/active_fund/fund_{fund_id}.json"))
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        loaded = load_active_fund_cache(fund_id, quarter, root)
        if loaded is not None:
            return loaded
    return None


# ── Item 005: fund-level + QDII dispatch helpers ──────────────────────────────
# _FUND_LEVEL_KINDS is imported from irc.fundamentals.snapshot (single source of truth).


def _load_latest_nav_cached(
    fund_id: str, root: Path,
) -> FundLevelSnapshot | None:
    """Scan `root/fundamentals/*/nav/fund_{fund_id}.json`; return most-recent quarter."""
    base = root / "fundamentals"
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"*/nav/fund_{fund_id}.json"))
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        loaded = load_nav_cache(fund_id, quarter, root)
        if loaded is not None:
            return loaded
    return None


def _is_nav_stale(
    snap: FundLevelSnapshot, *, today: date_cls, threshold_days: int,
) -> bool:
    if not snap.cache_probed_at:
        return True
    try:
        probed = date_cls.fromisoformat(snap.cache_probed_at)
    except ValueError:
        return True
    days = (today - probed).days
    if days < 0:
        return True
    return days > threshold_days


def _resolve_fund_level_snapshot(
    target: LookthroughTarget,
    root: Path,
    *,
    rebuild: bool,
    today: date_cls,
) -> FundLevelSnapshot:
    """Item 005 fund-level + QDII dispatch with cache reuse.

    - QDII kinds: returns the in-process sentinel (never cached).
    - Other fund-level kinds: load latest cached snapshot; if missing,
      stale (per `IRC_CACHE_FRESHNESS_DAYS`), or `--rebuild-fundamentals`,
      do a full refetch (no cheap probe per grill Q3) and write the cache.
    """
    if target.kind in ("qdii_us", "qdii_hk", "qdii_global"):
        return build_snapshot(target)  # type: ignore[return-value]

    fund_id = target.provider_symbol
    cached = None if rebuild else _load_latest_nav_cached(fund_id, root)
    if cached is not None and not _is_nav_stale(
        cached, today=today, threshold_days=_freshness_days(),
    ):
        return cached

    snap = build_snapshot(target)
    if not isinstance(snap, FundLevelSnapshot):
        raise RuntimeError(
            f"build_snapshot returned {type(snap).__name__} for fund-level dispatch "
            f"(target.kind={target.kind!r}, provider_symbol={target.provider_symbol!r})"
        )
    # Skip cache write for QDII sentinel (handled in write_nav_cache).
    if "qdii_information_unavailable" not in snap.evidence_gaps and snap.source_report_quarter:
        try:
            write_nav_cache(replace(snap, cache_probed_at=today.isoformat()), root)
        except Exception as cache_exc:
            reason = f"nav_cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
            sys.stderr.write(reason + "\n")
            snap = replace(
                snap,
                fund_level_failure_reasons=snap.fund_level_failure_reasons + (reason,),
            )
    return snap


# ── Item 003: validate_cli_args ───────────────────────────────────────────────

def validate_cli_args(
    *,
    output_dir: str | None,
    limit: int | None,
    rebuild_fundamentals: bool,
    today: str,
    root: Path | None = None,
) -> Path | None:
    """Reject `--limit` on canonical `outputs/<today>/` paths (exit code 2).

    P0-4 fixes:
    - When output_dir is None, resolve to `outputs/<today>/` (canonical) and
      apply the same rejection rule for --limit.
    - Call Path.resolve() BEFORE the suffix check to close the symlink bypass.
    - Return the resolved path so callers don't re-default downstream.
    """
    if limit is None:
        # No limit → nothing to reject; return resolved path for callers.
        if output_dir is None:
            return None
        return Path(output_dir).resolve()
    # limit is set — check whether the (resolved) path is canonical.
    if output_dir is None:
        # Default canonical path: outputs/<today>/.
        resolved = (root / "outputs" / today).resolve() if root is not None else None
        _reject_limit_on_canonical(resolved, today)
    else:
        resolved = Path(output_dir).resolve()
        _reject_limit_on_canonical(resolved, today)
    return resolved


def _reject_limit_on_canonical(resolved: Path | None, today: str) -> None:
    """Raise SystemExit(2) if the resolved path is the canonical outputs/<today>/."""
    canonical_suffix = f"outputs/{today}"
    # When output_dir was None and root was not provided, we conservatively reject
    # (the caller in run_opportunity always provides root, so resolved is not None there).
    if resolved is None:
        print("--limit is rejected on canonical output paths", file=sys.stderr)
        raise SystemExit(2)
    # Use the resolved absolute path string for the suffix check.
    resolved_str = str(resolved).rstrip("/")
    if resolved_str.endswith(canonical_suffix):
        print("--limit is rejected on canonical output paths", file=sys.stderr)
        raise SystemExit(2)


# ─────────────────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _locate_scoring(root: Path, today: str) -> Path | None:
    today_path = root / "outputs" / today / "scoring.json"
    if today_path.exists():
        return today_path
    candidates = sorted((root / "outputs").glob("*/scoring.json"))
    return candidates[-1] if candidates else None


def _load_scores(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return list(raw.get("scores", []))
    if isinstance(raw, list):
        return list(raw)
    return []


def _instrument_index(uni_list: list[UniverseConfig]) -> dict[str, Instrument]:
    index: dict[str, Instrument] = {}
    for u in uni_list:
        for instr in u.instruments:
            index.setdefault(instr.instrument_id, instr)
    return index


def _holdings_index(account: AccountFile) -> dict[str, Holding]:
    idx: dict[str, Holding] = {}
    for acc in account.accounts:
        for h in acc.holdings:
            if h.instrument_id is not None:
                idx[h.instrument_id] = h
    return idx


def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
    available_venues: set[str],
    con: duckdb.DuckDBPyConnection,
) -> OpportunityInput:
    asset_class = score_row.get("asset_class") or (instr.asset_class if instr else "unknown")
    market = instr.market if instr else "cn_off_exchange"
    theme = instr.theme if instr else None
    tracked_index = instr.tracked_index if instr else None
    # When the instrument isn't in any universe yaml, mark the row with a
    # placeholder rather than the raw id. The discipline report previously
    # rendered "110022 110022" because the fallback was the id itself; the
    # placeholder makes future unknown IDs visually distinct.
    iid = score_row.get("instrument_id", "")
    name_cn = instr.name_cn if instr is not None else f"未登记({iid})"
    weight = None
    if holding is not None and portfolio_total_cny > 0:
        weight = holding.cost_basis_cny / portfolio_total_cny
    # Empty available_venues means no venue restriction configured — treat as compatible.
    if available_venues and instr is not None and instr.venue_required:
        venue_ok = bool(set(instr.venue_required) & available_venues)
    else:
        venue_ok = True
    skeleton = OpportunityInput(
        instrument_id=score_row.get("instrument_id", ""),
        asset_class=asset_class,
        market=market,
        theme=theme,
        tracked_index=tracked_index,
        name_cn=name_cn,
        role=score_row.get("role", ""),
        is_holding=holding is not None,
        portfolio_weight=weight,
        target_band_low=target_band[0] if target_band else None,
        target_band_high=target_band[1] if target_band else None,
        venue_compatible=venue_ok,
    )
    entry_date: date_cls | None = None
    if holding is not None and holding.hold_since:
        try:
            entry_date = date_cls.fromisoformat(holding.hold_since)
        except ValueError:
            pass  # Malformed date string; drawdown_since_entry will remain None
    return populate_inputs(con, skeleton, holding_entry_date=entry_date)


def _selection_quality_from(input_row: OpportunityInput) -> SelectionQuality:
    return SelectionQuality(
        expense_ratio=input_row.expense_ratio,
        aum_cny=input_row.aum_cny,
        tracking_error=input_row.tracking_error,
        premium_discount_abs=(
            abs(input_row.premium_discount_pct)
            if input_row.premium_discount_pct is not None else None
        ),
        history_days=None,
        data_completeness=1.0,
    )


def _role_for(row: OpportunityRow, roles: dict[str, str]) -> str:
    """Return the role label for a row; falls back to 'watchlist' if absent."""
    return roles.get(row.instrument_id) or "watchlist"


def _discipline_row_from(
    row: OpportunityRow, position: PositionContext,
) -> DisciplineRow:
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    note = row.opportunity_reason.split(" | ")[0] if row.opportunity_reason else ""
    return DisciplineRow(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        note_cn=note,
        # Item 002: propagate gap state and provenance.
        thesis_evidence=row.thesis_evidence,
        constituent_analyses=getattr(row, "constituent_analyses", ()),
        evidence_gaps=row.evidence_gaps,
        fetch_types_attempted=getattr(row, "fetch_types_attempted", ()),
    )


def _resolve_research_theme(
    inp: OpportunityInput,
    theme_reports: dict[str, ThemeReport],
) -> ThemeReport | None:
    """Map an instrument to its relevant research theme report."""
    # Direct theme match first
    if inp.theme and inp.theme in theme_reports:
        return theme_reports[inp.theme]
    # Asset-class based mapping
    if inp.asset_class == "gold":
        return theme_reports.get("gold_drivers")
    if inp.asset_class == "cn_bond_fund":
        return theme_reports.get("cn_monetary")
    if inp.asset_class in ("us_etf", "hk_etf", "qdii_global"):
        return theme_reports.get("geopolitics")
    # CN equity funds without a direct theme match → holdings_sector
    if inp.asset_class == "cn_equity_fund":
        return theme_reports.get("holdings_sector")
    return None


def _classify_active_fund_scores(
    scores: list[dict],
    root: Path,
    *,
    today: date_cls,
    threshold_days: int,
    rebuild_fundamentals: bool,
    completed_ids: set[str] | None = None,
) -> tuple[int, int]:
    """Count (misses, stale) among cn_equity_fund rows — for preflight budget.

    A miss  = no cache file on disk.
    A stale = cache exists but probe is overdue.
    rebuild_fundamentals = True → every fund counts as a miss (full re-fetch forced).
    completed_ids: funds already finished in the current resume state are excluded
        from both miss and stale counts (resume credit, spec AC item 4 hardening).
    """
    _completed = completed_ids or set()
    misses = 0
    stale = 0
    seen: set[str] = set()
    for score in scores:
        if score.get("asset_class") != "cn_equity_fund":
            continue
        iid = score.get("instrument_id", "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        # Credit already-completed funds — no fetch cost on a resumed run.
        if iid in _completed:
            continue
        if rebuild_fundamentals:
            misses += 1
            continue
        cached = _load_latest_active_fund_cached(iid, root)
        if cached is None:
            misses += 1
        elif _is_stale(cached, today=today, threshold_days=threshold_days):
            stale += 1
    return misses, stale


def _is_qdii_bound_cn_etf(iid: str, instr_index: dict) -> bool:
    """Return True if a cn_etf row routes to the zero-cost QDII sentinel.

    A cn_etf whose tracked_index is in the QDII US or HK key sets dispatches
    to `_build_qdii_sentinel_snapshot` (zero AkShare calls) rather than the
    fund-level NAV+announcement engine. Counting such rows inflates the budget
    estimate and can trigger spurious FetchBudgetExceeded.
    """
    instr = instr_index.get(iid)
    if instr is None:
        return False
    tracked = (instr.tracked_index or "").strip().lower()
    return bool(tracked) and (tracked in _QDII_US_KEYS or tracked in _QDII_HK_KEYS)


def _classify_fund_level_scores(
    scores: list[dict],
    root: Path,
    *,
    instr_index: dict | None = None,
    today: date_cls,
    threshold_days: int,
    rebuild_fundamentals: bool,
) -> tuple[int, int]:
    """Count (misses, stale) among fund-level rows (gold/cn_bond_fund/cn_etf).

    QDII rows are NOT counted — they fire zero AkShare calls (sentinel).
    cn_etf rows whose tracked_index routes to a QDII key are excluded.
    """
    misses = 0
    stale = 0
    seen: set[str] = set()
    _instr_index: dict = instr_index or {}
    for score in scores:
        cls = score.get("asset_class")
        if cls not in ("gold", "cn_bond_fund", "cn_etf"):
            continue
        iid = score.get("instrument_id", "")
        if not iid or iid in seen:
            continue
        # cn_etf rows that map to a QDII kind cost zero AkShare calls — skip.
        if cls == "cn_etf" and _is_qdii_bound_cn_etf(iid, _instr_index):
            continue
        seen.add(iid)
        if rebuild_fundamentals:
            misses += 1
            continue
        cached = _load_latest_nav_cached(iid, root)
        if cached is None:
            misses += 1
        elif _is_nav_stale(cached, today=today, threshold_days=threshold_days):
            stale += 1
    return misses, stale


def _build_rows(
    scores: list[dict],
    instr_index: dict[str, Instrument],
    holdings: dict[str, Holding],
    portfolio_total_cny: float,
    available_venues: set[str],
    theme_thesis: object,
    theme_reports: dict,
    root: Path,
    asset_class_targets: dict,
    con: duckdb.DuckDBPyConnection,
    *,
    output_date: str,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
) -> tuple[list[OpportunityRow], dict, dict, dict, dict]:
    """Build opportunity rows for each score entry; return (rows, positions, qualities, roles, pending_verdicts)."""
    # ── Step 1: Apply --limit BEFORE any fetch cost computation ─────────────────
    if limit is not None:
        active_fund_scores = sorted(
            [s for s in scores if s.get("asset_class") == "cn_equity_fund"],
            key=lambda s: s.get("instrument_id", ""),
        )
        capped_active_ids = {s["instrument_id"] for s in active_fund_scores[:limit]}
        scores = [
            s for s in scores
            if s.get("asset_class") != "cn_equity_fund"
            or s.get("instrument_id") in capped_active_ids
        ]

    autobuild_on = _is_active_fund_target_autobuild_on()
    today = date_cls.today()

    if autobuild_on:
        # ── Step 2a: Compute plan_hash + load existing fetch state (P0-3) ────────
        # Must happen BEFORE the budget gate so completed_ids can be credited.
        active_fund_ids = sorted({
            s.get("instrument_id", "")
            for s in scores
            if s.get("asset_class") == "cn_equity_fund" and s.get("instrument_id")
        })
        plan_hash = compute_plan_hash(output_date, active_fund_ids, TOP_N_DEFAULT)
        fundamentals_dir = root / "data" / "fundamentals"
        state_path = _fetch_state_path(fundamentals_dir, plan_hash)

        existing_state = load_fetch_state(fundamentals_dir, plan_hash)
        if existing_state is None:
            # Stale state file (different plan_hash) is silently discarded — spec AC 20.
            fetch_state: dict = {
                "plan_hash": plan_hash,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "items": [],
            }
        else:
            fetch_state = existing_state

        completed_ids: set[str] = {
            item["fund_id"]
            for item in fetch_state.get("items", [])
            if item.get("status") == "complete"
        }

        # ── Step 2b: Preflight budget gate (P0-1) ────────────────────────────────
        # completed_ids are excluded from the cost count (resume credit).
        misses, stale = _classify_active_fund_scores(
            scores, root / "data",
            today=today, threshold_days=_freshness_days(),
            rebuild_fundamentals=rebuild_fundamentals,
            completed_ids=completed_ids,
        )
        fl_misses, fl_stale = _classify_fund_level_scores(
            scores, root / "data",
            instr_index=instr_index,
            today=today, threshold_days=_freshness_days(),
            rebuild_fundamentals=rebuild_fundamentals,
        )
        plan = FetchPlan(
            active_fund_misses=misses,
            active_fund_stale=stale,
            passive_misses=0,
            passive_stale=0,
            top_n=TOP_N_DEFAULT,
            fund_level_misses=fl_misses,
            fund_level_stale=fl_stale,
        )
        total = plan.total_calls()
        budget = _fetch_budget()
        if total > budget:
            raise FetchBudgetExceeded(plan, total, budget)

        # ── Step 3: Acquire advisory lock keyed on plan_hash (P0-2) ─────────────
        lock_path = fundamentals_dir / f".fetch_lock_{plan_hash}.lock"
        lock_fd = acquire_fetch_lock(lock_path)
    else:
        plan_hash = ""
        fundamentals_dir = root / "data" / "fundamentals"
        fetch_state = {}
        completed_ids = set()
        lock_fd = -1

    rows: list[OpportunityRow] = []
    positions: dict[str, PositionContext] = {}
    qualities: dict[str, SelectionQuality] = {}
    roles: dict[str, str] = {}
    snapshot_cache: dict[str, object] = {}
    pending_verdicts: dict[str, PolicyBVerdict] = {}

    try:
        for score in scores:
            iid = score.get("instrument_id", "")
            if not iid:
                print(f"WARNING: skipping score row with missing instrument_id: {score}")
                continue
            instr = instr_index.get(iid)
            holding = holdings.get(iid)
            target_band: tuple[float, float] | None = None
            if instr is not None:
                tgt = asset_class_targets.get(instr.asset_class)
                if tgt is not None:
                    target_band = (tgt.band[0], tgt.band[1])
            inp = _build_input(
                score, instr, holding,
                target_band,
                portfolio_total_cny, available_venues,
                con,
            )
            target = map_lookthrough(inp)
            snap_obj: object | None = None
            if target.kind == "active_fund" and autobuild_on:
                if target.key in snapshot_cache:
                    snap_obj = snapshot_cache[target.key]
                else:
                    fund_id = target.provider_symbol
                    # P0-3: skip if already complete in resume state.
                    if fund_id in completed_ids:
                        snap_obj = _load_latest_active_fund_cached(fund_id, root / "data")
                    elif rebuild_fundamentals:
                        # --rebuild-fundamentals: skip cache-read, skip freshness
                        # probe, force full re-fetch and force-write cache after build.
                        snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                        if isinstance(snap_obj, ActiveFundSnapshot):
                            snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                            # P0-5: skip cache write when quarter is empty.
                            if snap_to_cache.source_report_quarter:
                                try:
                                    write_active_fund_cache(snap_to_cache, root / "data")
                                except Exception as cache_exc:
                                    reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                    sys.stderr.write(reason + "\n")
                                    snap_obj = replace(
                                        snap_obj,
                                        fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                    )
                        _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                    else:
                        # 1. Try disk cache for the latest known quarter.
                        cached = _load_latest_active_fund_cached(fund_id, root / "data")
                        if cached is None:
                            snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                            if isinstance(snap_obj, ActiveFundSnapshot):
                                snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                                # P0-5: skip cache write when quarter is empty.
                                if snap_to_cache.source_report_quarter:
                                    try:
                                        write_active_fund_cache(snap_to_cache, root / "data")
                                    except Exception as cache_exc:
                                        reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                        sys.stderr.write(reason + "\n")
                                        snap_obj = replace(
                                            snap_obj,
                                            fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                        )
                            _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                        else:
                            probed, refresh = _maybe_freshness_probe(
                                cached, today=today, root=root / "data",
                            )
                            if refresh:
                                snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
                                if isinstance(snap_obj, ActiveFundSnapshot):
                                    snap_to_cache = replace(snap_obj, cache_probed_at=today.isoformat())
                                    # P0-5: skip cache write when quarter is empty.
                                    if snap_to_cache.source_report_quarter:
                                        try:
                                            write_active_fund_cache(snap_to_cache, root / "data")
                                        except Exception as cache_exc:
                                            reason = f"cache_write_failed:{fund_id}:{type(cache_exc).__name__}"
                                            sys.stderr.write(reason + "\n")
                                            snap_obj = replace(
                                                snap_obj,
                                                fund_level_failure_reasons=snap_obj.fund_level_failure_reasons + (reason,),
                                            )
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                            else:
                                snap_obj = probed
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
                    snapshot_cache[target.key] = snap_obj
            elif autobuild_on and (
                target.kind in ("qdii_us", "qdii_hk", "qdii_global")
                or (target.kind in _FUND_LEVEL_KINDS and target.provider_symbol)
            ):
                # ── Item 005: fund-level + QDII sentinel dispatch ──
                cache_key = target.provider_symbol or target.key
                if cache_key in snapshot_cache:
                    snap_obj = snapshot_cache[cache_key]
                else:
                    snap_obj = _resolve_fund_level_snapshot(
                        target, root / "data",
                        rebuild=rebuild_fundamentals,
                        today=today,
                    )
                    snapshot_cache[cache_key] = snap_obj
            else:
                target_name = target.display_cn
                if target_name not in snapshot_cache:
                    snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
                snap_obj = snapshot_cache[target_name]
            row = build_opportunity_row(
                inp,
                theme_thesis or None,
                snapshot=snap_obj,
                theme_report=_resolve_research_theme(inp, theme_reports),
            )
            # Item 006: Policy B verdict stamping for ActiveFundSnapshot rows.
            if isinstance(snap_obj, ActiveFundSnapshot):
                verdict = evaluate_policy_b(snap_obj, top_n=TOP_N_DEFAULT)
                if verdict.gap_codes:
                    row = replace(
                        row,
                        evidence_gaps=row.evidence_gaps + verdict.gap_codes,
                    )
                pending_verdicts[row.instrument_id] = verdict
            rows.append(row)
            positions[iid] = PositionContext(
                portfolio_weight=inp.portfolio_weight,
                target_band_low=inp.target_band_low,
                target_band_high=inp.target_band_high,
                drawdown_since_entry=inp.drawdown_since_entry,
                is_holding=inp.is_holding,
            )
            qualities[iid] = _selection_quality_from(inp)
            roles[iid] = inp.role or (instr.theme if instr else "") or ""

        # P0-3: clean up state file on successful full loop.
        if autobuild_on and plan_hash:
            state_path.unlink(missing_ok=True)

    finally:
        # P0-2: release advisory lock (kernel reclaims on FD close; explicit is cleaner).
        if lock_fd >= 0:
            try:
                os.close(lock_fd)
            except OSError:
                pass

    return rows, positions, qualities, roles, pending_verdicts


def _write_state_complete(
    state: dict,
    fund_id: str,
    snap_obj: object | None,
    fundamentals_dir: Path,
    plan_hash: str,
) -> None:
    """Atomically append a 'complete' entry to the fetch state file."""
    if not plan_hash:
        return
    quarter = ""
    if isinstance(snap_obj, ActiveFundSnapshot):
        quarter = snap_obj.source_report_quarter
    # Remove any existing entry for this fund_id, then append the new one.
    items = [i for i in state.get("items", []) if i.get("fund_id") != fund_id]
    items.append({
        "fund_id": fund_id,
        "status": "complete",
        "source_report_quarter": quarter,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    })
    state["items"] = items
    write_fetch_state(state, fundamentals_dir, plan_hash)


def _print_quality_warnings(rows: list[OpportunityRow]) -> None:
    """Print skeleton-mode or partial data warnings to stdout."""
    _insuf = "evidence_insufficient"
    all_insuf = all(
        r.valuation_state == _insuf
        and r.heat_state == _insuf
        and r.thesis_state == _insuf
        and r.product_quality_state == _insuf
        for r in rows
    )
    if all_insuf:
        print(
            f"WARNING: opportunity layer running in skeleton mode — "
            f"valuation/heat/thesis/product data not yet wired from ingest; "
            f"all {len(rows)} instruments show evidence_insufficient. "
            "See TODOS.md."
        )
    else:
        n_missing_val = sum(1 for r in rows if r.valuation_state == _insuf)
        if n_missing_val:
            print(
                f"WARNING: {n_missing_val}/{len(rows)} instruments missing "
                "valuation data — those states degraded to evidence_insufficient."
            )


def _apply_reduction(
    rows: list[OpportunityRow],
    qualities: dict[str, SelectionQuality],
    held_ids: set[str],
) -> list[OpportunityRow]:
    """Apply same-theme reduction, hold-preservation, and active-fund demotion."""
    by_theme: dict[str, list[OpportunityRow]] = {}
    for r in rows:
        by_theme.setdefault(r.theme or "_unthemed", []).append(r)
    kept: list[OpportunityRow] = []
    dropped: list[OpportunityRow] = []
    for theme, group in by_theme.items():
        if theme == "_unthemed":
            kept.extend(group)
            continue
        k, d = reduce_same_theme(group, qualities, max_per_theme=2)
        kept.extend(k)
        dropped.extend(d)
    for r in dropped:
        if r.instrument_id in held_ids and r not in kept:
            kept.append(r)
    kept_t, demoted_active = demote_unstable_active(kept, qualities)
    if demoted_active:
        print(
            f"INFO: demoted {len(demoted_active)} active fund(s) to small_watch "
            "(passive alternative available in same theme)"
        )
    return list(kept_t)


def _write_opportunity_outputs(
    kept_rows: list[OpportunityRow],
    positions: dict[str, PositionContext],
    qualities: dict[str, SelectionQuality],
    roles: dict[str, str],
    holdings: dict[str, Holding],
    out_dir: Path,
    today: str,
    *,
    pending_verdicts: dict[str, PolicyBVerdict] | None = None,
    snapshot_cache_by_instrument: dict[str, object] | None = None,
    plan_hash: str = "",
) -> None:
    """Compose the per-run opportunity outputs.

    Item 006 H3 invariant: gapped rows (rows with non-empty `evidence_gaps`)
    are partitioned out BEFORE any thesis_card / opportunity_report / discipline
    bucket emission. Gapped rows surface ONLY in `rejections.json` and the
    `## 证据不足 / Failed fetch` section of `discipline_report.md`.

    See ADR 0003 §3 for the H3 invariant rationale.
    """
    # Step 1 — H3 fatal pre-gate: fetch_budget_exhausted is run-level only.
    for r in kept_rows:
        if "fetch_budget_exhausted" in r.evidence_gaps:
            raise RuntimeError(
                f"fetch_budget_exhausted appeared on row {r.instrument_id} — "
                "this gap is run-level fatal and must be caught at preflight; "
                "row-level emission is a programming error"
            )

    # Step 2 — H3 partition.
    publishable_rows = [r for r in kept_rows if not r.evidence_gaps]
    gapped_rows = [r for r in kept_rows if r.evidence_gaps]

    # Step 3 — emit thesis_cards.yaml + opportunity_report.json from publishable only.
    cards = [
        build_thesis_card(
            row=r,
            position=positions[r.instrument_id],
            role=_role_for(r, roles),
            entry_reason=r.opportunity_reason.split(" | ")[0] if r.opportunity_reason else "",
        )
        for r in publishable_rows
        if r.instrument_id in holdings or r.opportunity_state in ("core_dca", "small_watch")
    ]
    discipline_rows = [
        _discipline_row_from(r, positions[r.instrument_id]) for r in publishable_rows
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "opportunity_report.json",
        json.dumps(
            compose_opportunity_report(publishable_rows, today),
            ensure_ascii=False, indent=2,
        ),
    )
    atomic_write_text(out_dir / "thesis_cards.yaml", compose_thesis_cards_yaml(cards))

    # Step 4 — build rejections.json from gapped rows.
    _verdicts = pending_verdicts or {}
    _snapshots = snapshot_cache_by_instrument or {}
    rejection_records: list = []
    for r in gapped_rows:
        reason = _classify_rejection_reason(r)
        verdict = _verdicts.get(r.instrument_id)
        snapshot = _snapshots.get(r.instrument_id)
        rejection_records.append(record_fund_rejection(
            row=r,
            snapshot=snapshot,
            verdict=verdict,
            rejection_reason=reason,
            decision_rule=_decision_rule_for(r, verdict),
        ))
    rejection_doc = RejectionsDocument(
        run_date=today,
        plan_hash=plan_hash,
        entries=tuple(rejection_records),
    )
    write_rejections_json(rejection_doc, out_dir)

    # Step 5 — compose discipline_report.md: publishable buckets + V1 summary + failure section.
    publishable_md = compose_discipline_markdown(discipline_rows, today)
    v1_summary = render_v1_systematic_exclusion_summary(rejection_doc.entries)
    failure_section = render_failure_section(gapped_rows)
    discipline_md = (
        publishable_md
        + "\n\n" + v1_summary
        + "\n\n## 证据不足 / Failed fetch\n\n" + failure_section + "\n"
    )
    atomic_write_text(out_dir / "discipline_report.md", discipline_md)

    print(
        f"opportunity OK: {len(publishable_rows)} rows, {len(cards)} cards, "
        f"{len(discipline_rows)} discipline entries, "
        f"{len(rejection_records)} rejections -> {out_dir}"
    )


def run_opportunity(
    repo_root: str,
    *,
    output_dir: str | None = None,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
) -> int:
    root = Path(repo_root)
    today = _today()
    # Validate CLI args before touching any I/O (exits with code 2 if invalid).
    validate_cli_args(
        output_dir=output_dir,
        limit=limit,
        rebuild_fundamentals=rebuild_fundamentals,
        today=today,
        root=root,
    )
    if not require_fresh_ingest(root, stage="opportunity"):
        print("ERROR: opportunity stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    bundle = load_repo_configs(root)
    available_venues: set[str] = {
        v for acc in bundle.account.accounts for v in acc.available_venues
    }
    scoring_path = _locate_scoring(root, today)
    if scoring_path is None:
        print("ERROR: no scoring.json; run `irc score` first.")
        return 2
    if scoring_path.parent.name != today:
        print(f"WARNING: using stale scoring from {scoring_path.parent.name}")
    scores = _load_scores(scoring_path)
    try:
        theme_thesis = load_theme_thesis(root)
    except ValueError as exc:
        print(f"ERROR: theme_thesis.yaml invalid: {exc}")
        return 2
    instr_index = _instrument_index([
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    ])
    holdings = _holdings_index(bundle.account)
    portfolio_total_cny = sum(
        h.cost_basis_cny for acc in bundle.account.accounts for h in acc.holdings
    )
    theme_reports = load_theme_reports(root)
    con = connect(root / "data" / "local.duckdb")
    ensure_schema(con)
    out_dir = Path(output_dir) if output_dir is not None else (root / "outputs" / today)
    try:
        rows, positions, qualities, roles, pending_verdicts = _build_rows(
            scores, instr_index, holdings, portfolio_total_cny,
            available_venues, theme_thesis, theme_reports, root,
            bundle.preferences.asset_class_targets,
            con,
            output_date=today,
            limit=limit,
            rebuild_fundamentals=rebuild_fundamentals,
        )
        if rows:
            _print_quality_warnings(rows)
        kept_rows = _apply_reduction(rows, qualities, set(holdings.keys()))
        _write_opportunity_outputs(
            kept_rows, positions, qualities, roles, holdings, out_dir, today,
            pending_verdicts=pending_verdicts,
        )
    except FetchBudgetExceeded as exc:
        sys.stderr.write(str(exc) + "\n")
        con.close()
        raise SystemExit(3)
    except FetchLockBusy as exc:
        sys.stderr.write(str(exc) + "\n")
        con.close()
        raise SystemExit(4)
    finally:
        try:
            con.close()
        except Exception:
            pass
    return 0
