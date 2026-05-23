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

from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_active_fund_cache,
    write_active_fund_cache,
)
from irc.fundamentals.types import ActiveFundSnapshot
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
from irc.opportunity.lookthrough import map_lookthrough
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

    def total_calls(self) -> int:
        per_active = 1 + self.top_n * 3
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + self.passive_misses * 2
            + self.passive_stale * 2
        )


class FetchBudgetExceeded(RuntimeError):
    def __init__(self, plan: FetchPlan, total: int, budget: int) -> None:
        super().__init__(
            f"FetchBudgetExceeded: "
            f"active_fund_misses={plan.active_fund_misses} "
            f"active_fund_stale={plan.active_fund_stale} "
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
    tmp = path.with_suffix(".json.tmp")
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
    return (today - probed).days > threshold_days


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
    if not probe.source_report_quarter or not probe.constituents:
        return snap, True
    if probe.source_report_quarter != snap.source_report_quarter:
        return snap, True
    updated = replace(snap, cache_probed_at=today.isoformat())
    write_active_fund_cache(updated, root)
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


# ── Item 003: validate_cli_args ───────────────────────────────────────────────

def validate_cli_args(
    *,
    output_dir: str | None,
    limit: int | None,
    rebuild_fundamentals: bool,
    today: str,
) -> None:
    """Reject `--limit` on canonical `outputs/<today>/` paths (exit code 2)."""
    if output_dir is None:
        return
    if limit is None:
        return
    canonical_suffix = f"outputs/{today}"
    if output_dir.rstrip("/").endswith(canonical_suffix):
        print(
            "--limit is rejected on canonical output paths",
            file=sys.stderr,
        )
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
    entry_date: date | None = None
    if holding is not None and holding.hold_since:
        try:
            entry_date = date.fromisoformat(holding.hold_since)
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
) -> tuple[list[OpportunityRow], dict, dict, dict]:
    """Build opportunity rows for each score entry; return (rows, positions, qualities, roles)."""
    rows: list[OpportunityRow] = []
    positions: dict[str, PositionContext] = {}
    qualities: dict[str, SelectionQuality] = {}
    roles: dict[str, str] = {}
    snapshot_cache: dict[str, object] = {}
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
        target_name = map_lookthrough(inp).display_cn
        if target_name not in snapshot_cache:
            snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
        row = build_opportunity_row(
            inp,
            theme_thesis or None,
            snapshot=snapshot_cache[target_name],
            theme_report=_resolve_research_theme(inp, theme_reports),
        )
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
    return rows, positions, qualities, roles


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
) -> None:
    cards = [
        build_thesis_card(
            row=r,
            position=positions[r.instrument_id],
            role=_role_for(r, roles),
            entry_reason=r.opportunity_reason.split(" | ")[0] if r.opportunity_reason else "",
        )
        for r in kept_rows
        if r.instrument_id in holdings or r.opportunity_state in ("core_dca", "small_watch")
    ]
    discipline_rows = [_discipline_row_from(r, positions[r.instrument_id]) for r in kept_rows]
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "opportunity_report.json",
        json.dumps(compose_opportunity_report(kept_rows, today), ensure_ascii=False, indent=2),
    )
    atomic_write_text(out_dir / "thesis_cards.yaml", compose_thesis_cards_yaml(cards))
    atomic_write_text(out_dir / "discipline_report.md", compose_discipline_markdown(discipline_rows, today))
    print(
        f"opportunity OK: {len(kept_rows)} rows, {len(cards)} cards, "
        f"{len(discipline_rows)} discipline entries -> {out_dir}"
    )


def run_opportunity(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="opportunity"):
        print("ERROR: opportunity stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    bundle = load_repo_configs(root)
    today = _today()
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
    try:
        rows, positions, qualities, roles = _build_rows(
            scores, instr_index, holdings, portfolio_total_cny,
            available_venues, theme_thesis, theme_reports, root,
            bundle.preferences.asset_class_targets,
            con,
        )
        if rows:
            _print_quality_warnings(rows)
        kept_rows = _apply_reduction(rows, qualities, set(holdings.keys()))
        _write_opportunity_outputs(kept_rows, positions, qualities, roles, holdings, root / "outputs" / today, today)
    finally:
        con.close()
    return 0
