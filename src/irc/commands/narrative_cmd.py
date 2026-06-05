from __future__ import annotations

import logging
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from irc.commands.fund_eval_cmd import _instr_by_id, _latest_quarter
from irc.config_loader import load_repo_configs
from irc.fundamentals.provider import default_cn_provider
from irc.io_utils import atomic_write_text
from irc.commands.narrative_autobuild import autobuild_narrative
from irc.commands.opportunity_cmd import FetchBudgetExceeded
from irc.narrative.analyze import analyze_fund, error_report
from irc.narrative.config import available_narratives, load_narrative_basket
from irc.narrative.holdings_fetch import fetch_top_holdings
from irc.narrative.report import (
    render_diagnostics_json,
    render_report_json,
    render_report_md,
    render_shortlist_json,
    render_shortlist_md,
)
from irc.narrative.schemas import (
    NarrativeBasket,
    NarrativeFundReport,
    ShortlistRow,
)
from irc.narrative.screen import rank_shortlist, score_overlap

_log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _enumerate_cn_funds(root: Path) -> tuple[tuple[str, str, str], ...]:
    """(instrument_id, name_cn, asset_class) for the curated CN-fund universe."""
    bundle = load_repo_configs(root)
    uni = getattr(bundle, "universe_cn_funds", None)
    if uni is None:
        return ()
    return tuple((i.instrument_id, i.name_cn, i.asset_class) for i in uni.instruments)


def _screen(
    basket: NarrativeBasket,
    universe: tuple[tuple[str, str, str], ...],
    cache_dir: Path,
) -> tuple[tuple[ShortlistRow, ...], tuple[tuple[str, str, str], ...]]:
    candidates: list[ShortlistRow] = []
    excluded: list[tuple[str, str, str]] = []
    for iid, name, asset_class in universe:
        holdings = fetch_top_holdings(iid, cache_dir=cache_dir)
        if not holdings:
            excluded.append((iid, name, "no_published_holdings"))
            continue
        candidates.append(ShortlistRow(
            instrument_id=iid, name_cn=name, asset_class=asset_class,
            overlap=score_overlap(holdings, basket), holdings=holdings,
        ))
    shortlist = rank_shortlist(
        tuple(candidates), min_basket_weight_pct=basket.min_basket_weight_pct,
        min_overlap_count=basket.min_overlap_count, top_n=basket.top_n,
    )
    return shortlist, tuple(excluded)


def _open_analyze_context(root: Path, db_path: str | None, quarter: str | None):
    """Open DuckDB read-only + resolve provider/quarter/instr-index. Returns
    (con, provider, quarter, instr_index) or None when prerequisites are absent."""
    db = Path(db_path) if db_path else (root / "data" / "local.duckdb")
    resolved_quarter = quarter or _latest_quarter(root)
    if not db.exists() or resolved_quarter is None:
        return None
    try:
        con = duckdb.connect(str(db), read_only=True)
    except Exception as exc:
        _log.warning("_open_analyze_context: cannot connect to %s — %s", db, exc)
        return None
    return (con, default_cn_provider(), resolved_quarter, _instr_by_id(root))


def _run_analyze(
    root: Path, shortlist: tuple[ShortlistRow, ...], *,
    db_path: str | None, quarter: str | None, role: str,
) -> tuple[NarrativeFundReport, ...] | None:
    ctx = _open_analyze_context(root, db_path, quarter)
    if ctx is None:
        return None
    con, provider, resolved_quarter, instr_index = ctx
    reports: list[NarrativeFundReport] = []
    try:
        autobuild_narrative(
            shortlist, provider=provider, instr_index=instr_index, con=con,
            quarter=resolved_quarter, data_dir=root / "data", today_iso=_today(),
        )
        for row in shortlist:
            try:
                reports.append(
                    analyze_fund(
                        row, instr=instr_index.get(row.instrument_id), con=con,
                        provider=provider, quarter=resolved_quarter,
                        data_dir=root / "data", role=role,
                    )
                )
            except FetchBudgetExceeded:
                raise
            except Exception as exc:
                _log.warning(
                    "_run_analyze: analyze_fund failed for %s — %s",
                    row.instrument_id, exc,
                )
                reports.append(error_report(row, str(exc)))
    finally:
        try:
            con.close()
        except Exception:
            _log.debug("con.close failed", exc_info=True)
    return tuple(reports)


def _write_screen(
    out: Path, name: str, label: str,
    shortlist: tuple[ShortlistRow, ...],
    excluded: tuple[tuple[str, str, str], ...],
) -> None:
    atomic_write_text(out / f"{name}_shortlist.md", render_shortlist_md(label, shortlist))
    atomic_write_text(out / f"{name}_shortlist.json", render_shortlist_json(label, shortlist))
    atomic_write_text(out / f"{name}_screen_diagnostics.json",
                      render_diagnostics_json(excluded))


def run_narrative(
    repo_root: str, name: str, *, analyze: bool = False,
    out_dir: str | None = None, quarter: str | None = None,
    db_path: str | None = None, role: str = "satellite_cn_metals",
    min_overlap: float | None = None,
) -> int:
    root = Path(repo_root)
    try:
        basket = load_narrative_basket(name, root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Available narratives: {', '.join(available_narratives(root)) or '(none)'}",
              file=sys.stderr)
        return 2
    # spec §3.1: --min-overlap overrides the config's min_basket_weight_pct (immutably).
    if min_overlap is not None:
        basket = replace(basket, min_basket_weight_pct=min_overlap)
    # Gate unconditionally (after arg parsing): the scope is the eval tasks, a safe
    # upper bound even on a --screen-only run. Spec §8.2 / Phase 1 plan Task 13.
    from irc.commands.spend_cmd import preflight_gate
    gate_rc = preflight_gate(repo_root, "narrative")
    if gate_rc != 0:
        return gate_rc
    out = Path(out_dir) if out_dir else (root / "outputs" / _today() / "narrative")
    out.mkdir(parents=True, exist_ok=True)
    label = basket.display_name_cn or basket.narrative_id
    shortlist, excluded = _screen(
        basket, _enumerate_cn_funds(root), root / "data" / "narrative_holdings",
    )
    _write_screen(out, name, label, shortlist, excluded)
    if analyze:
        try:
            reports = _run_analyze(root, shortlist, db_path=db_path, quarter=quarter, role=role)
        except FetchBudgetExceeded as exc:
            print(
                f"ERROR: fetch budget exceeded ({exc}). "
                f"Raise IRC_FETCH_BUDGET or set IRC_NARRATIVE_AUTOBUILD=0 to skip the "
                f"snapshot autobuild (active + passive funds). Shortlist written to {out}.",
                file=sys.stderr,
            )
            return 3
        if reports is None:
            print(
                f"ERROR: --analyze needs data/local.duckdb (run `irc ingest`) and a "
                f"snapshot quarter under data/fundamentals/. Active-fund snapshots are "
                f"auto-built during a successful --analyze (set IRC_NARRATIVE_AUTOBUILD=0 "
                f"to disable); if none exist yet, run `irc opportunity` once or re-run "
                f"--analyze online. Shortlist written to {out}.",
                file=sys.stderr,
            )
            return 2
        atomic_write_text(out / f"{name}_report.md", render_report_md(label, reports, name=name))
        atomic_write_text(out / f"{name}_report.json", render_report_json(label, reports))
    print(f"narrative {name} OK: {len(shortlist)} shortlisted, "
          f"{len(excluded)} excluded -> {out}")
    return 0
