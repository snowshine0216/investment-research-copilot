"""EDGE: `irc monitor` command — thin orchestrator + snapshot subcommand.

All business logic lives in pure cores under src/irc/monitor/.
This module is the ONLY place I/O (filesystem, network, AkShare, LLM) is
allowed in the monitor vertical. It reads ONLY config/monitor.yaml via
load_monitor_config — never load_repo_configs.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from irc.config_loader import load_monitor_config, load_yaml
from irc.data.duckdb_helper import connect
from irc.monitor.heat_fetch import fetch_purchase_table, heat_inputs_for, purchase_tag_for
from irc.monitor.market_composite import market_composite_view
from irc.monitor.valuation import resolve_valuation_state
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.snapshot_cache import (
    load_latest_active_fund_cached,
    write_active_fund_cache,
    write_nav_cache,
    write_snapshot,
)
from irc.fundamentals.types import ActiveFundSnapshot, FundLevelSnapshot
from irc.io_utils import atomic_write_text
from irc.llm.gateway import call as llm_call
from irc.monitor.constituent_match import select_impacts_by_holding
from irc.monitor.evidence import make_evidence_item
from irc.monitor.factors import FactorInputs, build_factor_scores
from irc.monitor.source_tiers import SourceTiers, classify, tiers_from_config
from irc.monitor.flow_batch_fetch import fetch_flow_today_batch
from irc.monitor.flow_series_store import append_today, load_store, series_slice
from irc.monitor.holding_metrics import build_holding_metrics, aggregate_flow, aggregate_valuation
from irc.monitor.industry_valuation import fetch_industry_pe, fetch_stock_industry_map
from irc.monitor.render_drilldown import drilldown_page_html
from irc.monitor.fetch import NavFetchResult, nav_series_for
from irc.monitor.impacts import ImpactsResult, gather_impacts
from irc.monitor.macro_direction import unmatched_impact_keys
from irc.monitor.narrative_macro import (
    PROMPT_VERSION, build_macro_pool, gather_macro_narrative,
    MacroNarrativeDoc, MacroNarrativeResult,
)
from irc.monitor.news_factor import ImpactRow
from irc.monitor.profiles import theme_query_seed
from irc.monitor.render_html import render_report
from irc.monitor.returns import window_returns
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.resolve import resolve_funds
from irc.monitor.signal import compute_signal
from irc.monitor.snapshot_targets import target_for_fund
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M1, published_state
from irc.monitor.eval.structural import (
    monitor_signal_health, flow_reconciliation, flow_coverage_health,
    valuation_reconciliation, valuation_coverage_health,
)
from irc.monitor.eval.staleness import STALE_AFTER_DAYS, resolve_health
from irc.monitor.eval.trace import SCHEMA_VERSION, build_eval_trace
from irc.monitor.trading_calendar import load_trading_days
from irc.monitor.eval.forward_log import append_ledger, ledger_row, latest_per_key
from irc.monitor.render_timeline import BiasTimeline
from irc.monitor.eval.nav_history import nav_history_append_rows, append_nav_history
from irc.monitor.eval.constants import NAV_APPEND_DAYS, REVIEW_TRIGGER_K, STALE_EVAL_DAYS
from irc.monitor.eval.types import (
    FundTraceBundle, GateDecision, StageHealth, ValidationPanelRow,
    PredictiveMetricView, PredictivePanelModel,
)
from irc.monitor.eval.determinism import deterministic_health, build_panel_rows
from irc.monitor.eval.review import dedup_iso_weeks, review_trigger
from evals._shared.latest_report import (
    latest_stage_report, latest_stage_report_entry, list_stage_reports,
)
from evals.monitor_forward.runner import run as _forward_eval_run
from irc.monitor.types import MonitorFund, NarrativeDoc, SignalRecord
from irc.research.search.factory import build_providers
from irc.settings import Settings
from irc.spend.record_run import record_command_run
from irc.commands.spend_cmd import preflight_gate

_log = logging.getLogger(__name__)
_ENGINE_VERSION = "4"
_NAV_STALE_DAYS = 7


# ── Snapshot subcommand ───────────────────────────────────────────────────────


def _persist_snapshot(snapshot, data_root: Path) -> Path:
    """Dispatch snapshot write to the correct writer by runtime type.

    - ActiveFundSnapshot  → write_active_fund_cache (keyed by fund_id + quarter)
    - FundLevelSnapshot   → write_nav_cache         (NAV + announcements cache)
    - ConstituentSnapshot → write_snapshot           (broad-index constituent cache)
    """
    if isinstance(snapshot, ActiveFundSnapshot):
        return write_active_fund_cache(snapshot, data_root)
    if isinstance(snapshot, FundLevelSnapshot):
        return write_nav_cache(snapshot, data_root)
    return write_snapshot(snapshot, data_root)


def run_monitor_snapshot(*, repo_root: str, top_n: int = 10) -> int:
    """EDGE: refresh per-fund snapshot caches for the Monitor set using TYPED
    targets (active_fund / fund-level kinds keyed by provider_symbol=fund_id).
    Never the broad-index path (§9)."""
    root = Path(repo_root)
    cfg = load_monitor_config(root)
    funds = resolve_funds(cfg)
    for fund in funds:
        target = target_for_fund(fund)
        snapshot = build_snapshot(target, top_n=top_n)
        path = _persist_snapshot(snapshot, root / "data")
        reasons = (
            getattr(snapshot, "failure_reasons", None)
            or getattr(snapshot, "fund_level_failure_reasons", ())
        )
        if reasons:
            print(f"WARNING: {fund.id} snapshot gaps: {'; '.join(reasons)}")
        print(f"monitor snapshot OK: {fund.id} -> {path}")
    return 0


# ── Evidence pool (EDGE) ──────────────────────────────────────────────────────


def _unique_themes(funds: list[MonitorFund]) -> tuple[str, ...]:
    """Stable-sorted union of themes across the monitor set (Comp 2)."""
    return tuple(sorted({t for fund in funds for t in fund.themes}))


def _search_all_themes(
    provider, themes: tuple[str, ...], *, tiers: SourceTiers,
) -> dict[str, tuple]:
    """EDGE: search once per unique theme (Comp 2 — 28->8 provider calls). Tier
    gate (ADR 0022) applied here, once per theme, not per fund. Returns
    {theme: tuple[SearchHit, ...]} with blocked hits dropped; a theme whose
    search failed maps to () (logged, never raises)."""
    out: dict[str, tuple] = {}
    for theme in themes:
        query = theme_query_seed(theme)
        result = provider.search(query, max_results=5, freshness_days=7)
        if result.failure_reason:
            _log.warning("monitor theme search failed for theme %r: %s",
                         theme, result.failure_reason)
            out[theme] = ()
            continue
        kept = []
        dropped = 0
        for hit in result.hits:
            domain = hit.source_domain or provider.name
            if classify(domain, tiers) == "blocked":
                dropped += 1
                continue
            kept.append(hit)
        if dropped:
            _log.warning("monitor theme search: dropped %d blocked-tier hit(s) for theme %r",
                         dropped, theme)
        out[theme] = tuple(kept)
    return out


def _load_source_tiers_config(repo_root: Path) -> dict | None:
    """EDGE-read: `source_tiers:` section of config/monitor.yaml as a raw dict
    (already pydantic-validated by load_monitor_config elsewhere; this is a
    second narrow read local to the evidence edge to avoid threading cfg through
    every build_evidence_pool call site — matches the existing load_monitor_config
    pattern of a narrow, single-purpose read). None on any read/parse failure."""
    try:
        cfg = load_monitor_config(repo_root)
        st = cfg.source_tiers
        return {"blocked": list(st.blocked), "tier1": list(st.tier1), "tier2": list(st.tier2)}
    except Exception:  # noqa: BLE001 — degrade to tier-3-everything, never crash
        return None


def build_evidence_pool(fund: MonitorFund, *, theme_results: dict[str, tuple]) -> tuple:
    """PURE assembly (Comp 2): each fund's pool from the SHARED theme_results map
    built once by _search_all_themes. Owner-binds per fund exactly as before (cid
    preimage includes owner_fund_id, ADR 0017) — same hits -> same cids as the
    status quo. Missing/failed theme key -> no hits for that theme (not KeyError)."""
    items: list = []
    for theme in fund.themes:
        for hit in theme_results.get(theme, ()):
            items.append(make_evidence_item(
                hit.source_domain or "unknown", hit.title, hit.published_iso or "",
                hit.url, owner_fund_id=fund.id,
            ))
    return tuple(items)


# ── Constituent pool (EDGE — snapshot I/O) ───────────────────────────────────

_TOP_N_HOLDINGS = 5
_FLOW_STORE_REL = ("data", "monitor", "fund_flow_series.json")


def _load_flow_store_slice(root: Path, symbols) -> dict:
    """EDGE-read: the persisted completed-day flow store, sliced to `symbols`.
    The 12:15 brief consumes the store (whose newest row is a COMPLETED day); it
    NEVER writes a provisional intraday value (D6/trap §8). Degrades to {} on any
    error — the flow factor then reads all-None (honest N/A)."""
    try:
        store = load_store(root.joinpath(*_FLOW_STORE_REL))
        return series_slice(store, symbols)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("_load_flow_store_slice failed", exc_info=True)
        return {}


def _provisional_flow_note(root: Path, symbols) -> dict | None:
    """EDGE-read only: today's intraday f184 as a 盘中提示 annotation for the 12:15
    brief. NEVER persisted (no append_today here) — the store's newest row stays a
    COMPLETED day (D6/trap §8). Degrades to None on any error (no annotation)."""
    if not symbols:
        return None
    try:
        flow, _industry = fetch_flow_today_batch(tuple(symbols))
        return flow
    except Exception:  # noqa: BLE001 — annotation is best-effort
        _log.warning("_provisional_flow_note failed", exc_info=True)
        return None


def _evidence_items_for_holding(holding, fund_id: str) -> tuple:
    """Convert one ConstituentAnalysis → owner-bound EvidenceItems.

    If the holding has ThesisEvidence rows, convert each via make_evidence_item.
    If none, synthesize one no-url item from one_line_view (stable fallback).
    v2.0 NOTE: uses snapshot-cached research, NOT fresh daily news. Fresh daily
    news per top holding is a documented v2.1 follow-up (avoids ~12 extra web
    searches/run while still wiring the constituent factor).
    """
    items = []
    for ev in holding.evidence:
        items.append(make_evidence_item(
            ev.source, ev.summary or ev.source,
            ev.date, ev.url, owner_fund_id=fund_id,
        ))
    if not items and holding.one_line_view:
        title = f"{holding.name_cn} ({holding.symbol}): {holding.one_line_view}"
        # Stable fallback source so citation_id is deterministic across runs.
        items.append(make_evidence_item(
            f"snapshot:{holding.symbol}", title,
            "", "", owner_fund_id=fund_id,
        ))
    return tuple(items)


def build_constituent_pool(fund_id: str, *, root: Path) -> tuple:
    """EDGE: load latest cached ActiveFundSnapshot → top-N holdings → EvidenceItems.

    Returns () when no snapshot exists (constituent factor stays N/A naturally).
    v2.0: snapshot-grounded (cheaper than fresh daily news). See _evidence_items_for_holding.
    """
    try:
        snap = load_latest_active_fund_cached(fund_id, root / "data")
        if snap is None:
            _log.debug("build_constituent_pool: no cached snapshot for %s", fund_id)
            return ()
        top = sorted(
            snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True
        )[:_TOP_N_HOLDINGS]
        items: list = []
        for holding in top:
            items.extend(_evidence_items_for_holding(holding, fund_id))
        return tuple(items)
    except Exception as exc:
        _log.warning(
            "build_constituent_pool failed for %s: %s", fund_id, exc, exc_info=True,
        )
        return ()


def _make_constituent_rows(
    impacts: ImpactsResult, top_holdings: tuple,
) -> tuple:
    """Map gather_impacts result back to ImpactRows keyed by holding symbol.

    Robust to LLM symbol-keying drift (exchange suffix / whitespace / case /
    leading zeros / name_cn) via match_impact_to_holding. Unmatched keys are
    logged at WARNING (no silent drop) so future keying drift stays visible."""
    symbol_to_weight = {h.symbol: h.weight_pct for h in top_holdings}
    best, unmatched = select_impacts_by_holding(impacts.impacts, top_holdings)
    if unmatched:
        _log.warning(
            "monitor constituent: dropped %d unmatched impact key(s) for %s: %s "
            "(holdings: %s)",
            len(unmatched), impacts.fund_id, list(unmatched),
            [h.symbol for h in top_holdings],
        )
    return tuple(
        ImpactRow(symbol, weight=symbol_to_weight[symbol],
                  impact=imp.impact, confidence=imp.confidence)
        for symbol, imp in best.items()
    )


# ── Orchestration helpers ─────────────────────────────────────────────────────


def _provisional_flow_for_fund(top5: tuple, provisional_flow: dict | None) -> float | None:
    """PURE: simple mean of the top-5 symbols' intraday f184 values (render-only
    annotation, NOT a factor — no weighting sophistication needed). None when
    provisional_flow is None/empty or no top5 symbol has a value."""
    if not provisional_flow or not top5:
        return None
    values = [provisional_flow.get(h.symbol) for h in top5]
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _build_full_basket_metrics(full_holdings, top5, fund_id, *, root, today, con, flow_slice):
    """EDGE: consume flow (top-5, from the run-level store slice) + fetch industry
    (full basket) → full-basket HoldingMetrics. Flow is read ONCE per run: run_monitor
    loads the store slice for the union of all active-fund symbols and passes it
    through to every _process_fund call (see `run_monitor`); a caller invoking
    _process_fund directly (e.g. tests) without a slice still falls back to
    _load_flow_store_slice for library robustness."""
    from irc.opportunity.inputs_loader import _stock_series_by_code
    flow_symbols = tuple(h.symbol for h in top5)
    flow_series = {s: flow_slice.get(s) for s in flow_symbols}
    full_symbols = tuple(h.symbol for h in full_holdings)
    if con is None:
        return build_holding_metrics(full_holdings, {}, flow_series)
    series_by_code = _stock_series_by_code(con, full_symbols)
    industry_pe = fetch_industry_pe(
        cache_dir=root / "data" / "monitor" / "industry_pe", today=today)
    industry_map = fetch_stock_industry_map(
        full_symbols, cache_dir=root / "data" / "monitor" / "stock_industry", today=today)
    return build_holding_metrics(
        full_holdings, series_by_code, flow_series,
        industry_by_symbol=industry_map, industry_pe_by_industry=industry_pe)


def _impact_rows_from(impacts: ImpactsResult, fund: MonitorFund) -> tuple[ImpactRow, ...]:
    return tuple(
        ImpactRow(i.key, weight=1.0, impact=i.impact, confidence=i.confidence)
        for i in impacts.impacts
        if i.key in fund.themes
    )


def _make_view(
    fund: MonitorFund,
    nav: NavFetchResult | None,
    signal: SignalRecord,
    scores: tuple,
    narr_doc: NarrativeDoc,
    pool: tuple,
    impacts_status: str = "ok",
    *,
    holding_metrics: tuple = (),
    purchase_table=None,
    provisional_flow_pct: float | None = None,
    provisional_flow_as_of: str | None = None,
) -> FundView:
    mv = market_composite_view(signal, bands=fund.bands)
    return FundView(
        fund_id=fund.id,
        name_cn=fund.name_cn,
        latest_nav=nav.latest_nav if nav else 0.0,
        as_of_date=nav.as_of_date if nav else "N/A",
        nav_series=nav.acc_series if nav else (),
        signal=signal,
        narrative=narr_doc,
        evidence_pool=pool,
        return_table=window_returns(nav.acc_series if nav else ()),
        factor_freshness={c.name: "fresh" for c in signal.contributions},
        missing_factor_reasons=tuple(
            f"{s.name}: {s.reason}" for s in scores if not s.eligible
        ),
        factor_scores=tuple(scores),
        impacts_status=impacts_status,
        holding_metrics=holding_metrics,
        market_view=mv,
        purchase_tag=purchase_tag_for(fund.id, purchase_table=purchase_table),
        themes=fund.themes,
        provisional_flow_pct=provisional_flow_pct,
        provisional_flow_as_of=provisional_flow_as_of,
    )


def _read_prior_signal(root: Path, today: str) -> dict | None:
    import glob
    pattern = str(root / "outputs" / "*" / "monitor" / "signal.json")
    files = sorted(p for p in glob.glob(pattern) if today not in p)
    if not files:
        return None
    try:
        return json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_prior_signal_with_date(root: Path, today: str) -> tuple[dict | None, str | None]:
    """Comp 5: like _read_prior_signal but also returns the prior run's date
    label (for the 偏向变化 row's '(vs 2026-06-15)' annotation — on Monday
    that's Friday, not a calendar 'yesterday', since it's the latest run
    strictly before today)."""
    import glob
    pattern = str(root / "outputs" / "*" / "monitor" / "signal.json")
    files = sorted(p for p in glob.glob(pattern) if today not in p)
    if not files:
        return None, None
    latest = Path(files[-1])
    prior_date = latest.parent.parent.name   # outputs/<date>/monitor/signal.json
    try:
        return json.loads(latest.read_text(encoding="utf-8")), prior_date
    except Exception:
        return None, None


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _signal_dump(views: list[FundView]) -> dict:
    return {
        v.fund_id: {"status": v.signal.status, "bias": v.signal.bias}
        for v in views
    }


def _impacts_dump(views: list[FundView]) -> dict:
    return {
        v.fund_id: [
            {"key": c.name, "contribution": c.contribution}
            for c in v.signal.contributions
        ]
        for v in views
    }


def _narrative_dump(views: list[FundView], macro_doc: MacroNarrativeDoc | None) -> dict:
    out = {
        v.fund_id: {
            "status": v.narrative.status,
            "price_action": [c.claim for c in v.narrative.price_action_commentary],
            "signal_rationale": [c.claim for c in v.narrative.signal_rationale_commentary],
            "risk": [c.claim for c in v.narrative.risk_commentary],
        }
        for v in views
    }
    out["__macro__"] = (
        {
            "status": macro_doc.status,
            "blocks": [
                {"theme": b.theme, "mechanism": b.mechanism,
                 # 002 ship-review round 1, Finding 2 (P1): additive debug
                 # key — present-but-dropped vs. LLM-omitted, both None otherwise.
                 "mechanism_dropped": b.mechanism_dropped,
                 "claims": [c.claim for c in b.claims]}
                for b in macro_doc.blocks
            ],
        }
        if macro_doc is not None else {"status": "empty_pool", "blocks": []}
    )
    return out


def _machine_summary(views: list[FundView]) -> dict:
    return {
        "funds": [
            {
                "fund_id": v.fund_id,
                "name_cn": v.name_cn,
                "latest_nav": v.latest_nav,
                "as_of_date": v.as_of_date,
                "signal": {"status": v.signal.status, "bias": v.signal.bias},
                "impacts_status": v.impacts_status,
            }
            for v in views
        ]
    }


def _write_outputs(out: Path, views: list[FundView], prior: dict | None,
                   gates: tuple[GateDecision, ...] = (),
                   panel_rows: tuple[ValidationPanelRow, ...] = (),
                   predictive_panel: PredictivePanelModel | None = None,
                   timeline: BiasTimeline | None = None,
                   macro_doc: MacroNarrativeDoc | None = None,
                   macro_pool_items: tuple = (),
                   tiers: SourceTiers | None = None,
                   constituent_pool_items: tuple = (),
                   prior_run_date: str | None = None,
                   purchase_tags: dict | None = None,
                   macro_impacts_by_fund: dict | None = None,
                   *, now_dt: datetime) -> None:
    prov = Provenance(_ENGINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION, "")
    gate_map = {g.fund_id: g for g in gates} if gates else None
    html = render_report(tuple(views), prov, prior_signal=prior,
                         now=now_dt.isoformat(timespec="seconds"), now_dt=now_dt,
                         gates=gate_map, panel_rows=panel_rows,
                         predictive_panel=predictive_panel, timeline=timeline,
                         macro_narrative=macro_doc, macro_pool_items=macro_pool_items,
                         tiers=tiers, constituent_pool_items=constituent_pool_items,
                         prior_run_date=prior_run_date, purchase_tags=purchase_tags,
                         stale_eval_days=STALE_EVAL_DAYS,
                         macro_impacts_by_fund=macro_impacts_by_fund)
    atomic_write_text(out / "report.html", html)
    atomic_write_text(
        out / "signal.json",
        json.dumps(_signal_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "impacts.json",
        json.dumps(_impacts_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "narrative.json",
        json.dumps(_narrative_dump(views, macro_doc), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "monitor.json",
        json.dumps(_machine_summary(views), indent=2, sort_keys=True),
    )


def _write_drilldown(out: Path, views: tuple) -> None:
    """EDGE: write drilldown.html when any fund has holding_metrics (atomic write)."""
    dd_views = tuple(
        (
            v.fund_id, v.name_cn, v.holding_metrics,
            aggregate_flow(v.holding_metrics), v.signal,
            aggregate_valuation(v.holding_metrics),
        )
        for v in views if v.holding_metrics
    )
    if not dd_views:
        return
    try:
        atomic_write_text(out / "drilldown.html", drilldown_page_html(dd_views))
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("drilldown.html write failed", exc_info=True)


# ── Eval wiring helpers ───────────────────────────────────────────────────────


def _suite_eval(root: Path, today: str, now: datetime) -> tuple[tuple, tuple]:
    """EDGE-read: resolve the two LLM-suite StageHealths ONCE per run (run-global,
    OQ-E) AND build their display panel rows from the SAME report read. The suite
    stages gate (GATING_STAGES_M1) but were previously invisible in the panel, so a
    gate they caused looked mis-attributed to monitor_signal. Missing/SKIPPED/stale →
    UNKNOWN → caveated (fail-open). Returns (healths, panel_rows)."""
    healths: list[StageHealth] = []
    rows: list[ValidationPanelRow] = []
    for stage in ("monitor_impact", "monitor_narrative"):
        report = latest_stage_report(root, stage, today_iso=today)
        health = resolve_health(report, now=now, stale_after_days=STALE_AFTER_DAYS,
                                stage=stage)
        healths.append(health)
        rows.append(ValidationPanelRow(
            stage=stage, status=health.status,
            ran_at=report.ran_at if report is not None else "—",
            reasons=health.reasons,
        ))
    return tuple(healths), tuple(rows)


def _compute_gates(
    funds: list[MonitorFund], views: list[FundView], bundles: list[FundTraceBundle],
    *, min_obs: int, suite_healths: tuple[StageHealth, ...],
    trading_days: frozenset[date] | None,
) -> tuple[tuple[GateDecision, ...], dict, dict, dict, dict, dict, dict]:
    """Build each fund's trace projection ONCE, derive its monitor_signal health AND
    its deterministic_scoring health from that single projection, append the two
    run-global LLM-suite healths (resolved once at the edge — identical for every
    fund, OQ-E), and apply the M1 gate. Also computes flow_reconciliation,
    flow_coverage, valuation_reconciliation, and valuation_coverage healths (all
    panel-only, §5.E — never gate). Returns
    (gates, signal_h, det_h, flow_recon_h, flow_cov_h, val_recon_h, val_cov_h);
    all four health dicts are PANEL-ONLY and never passed to apply_eval_gate."""
    gates: list[GateDecision] = []
    signal_healths: dict = {}
    deterministic_healths: dict = {}
    flow_recon_healths: dict = {}
    flow_cov_healths: dict = {}
    val_recon_healths: dict = {}
    val_cov_healths: dict = {}
    for fund, view, bundle in zip(funds, views, bundles):
        stub = GateDecision(fund.id, False, (), "validated", "")
        projection = build_eval_trace(
            ((fund, view, stub, bundle),), engine_version=_ENGINE_VERSION,
            run_date="", trading_days=trading_days,
        )["funds"][fund.id]
        signal_health = monitor_signal_health(
            projection, minimum_observations=min_obs,
            stale_days=_NAV_STALE_DAYS, today=date.today(),
        )
        signal_healths[fund.id] = signal_health
        try:
            deterministic_healths[fund.id] = deterministic_health(fund.id, projection)
        except Exception as exc:  # noqa: BLE001 — panel-only; must not crash the run
            _log.warning(
                "deterministic_health failed for %s: %r", fund.id, exc, exc_info=True,
            )
            deterministic_healths[fund.id] = StageHealth(
                stage="deterministic_scoring",
                status="FAIL",
                reasons=(f"{fund.id}: recompute_error: {exc!r}",),
            )
        try:
            flow_recon_healths[fund.id] = flow_reconciliation(projection)
        except Exception as exc:  # noqa: BLE001 — panel-only; must not crash the run
            _log.warning(
                "flow_reconciliation failed for %s: %r", fund.id, exc, exc_info=True,
            )
            flow_recon_healths[fund.id] = StageHealth(
                stage="flow_reconciliation", status="WARN",
                reasons=(f"{fund.id}: reconciliation_error: {exc!r}",),
            )
        try:
            flow_cov_healths[fund.id] = flow_coverage_health(projection)
        except Exception as exc:  # noqa: BLE001 — panel-only; must not crash the run
            _log.warning(
                "flow_coverage_health failed for %s: %r", fund.id, exc, exc_info=True,
            )
            flow_cov_healths[fund.id] = StageHealth(
                stage="flow_coverage", status="WARN",
                reasons=(f"{fund.id}: coverage_error: {exc!r}",),
            )
        try:
            val_recon_healths[fund.id] = valuation_reconciliation(projection)
        except Exception as exc:  # noqa: BLE001 — panel-only; must not crash the run
            _log.warning(
                "valuation_reconciliation failed for %s: %r", fund.id, exc, exc_info=True,
            )
            val_recon_healths[fund.id] = StageHealth(
                stage="valuation_reconciliation", status="WARN",
                reasons=(f"{fund.id}: reconciliation_error: {exc!r}",),
            )
        try:
            val_cov_healths[fund.id] = valuation_coverage_health(projection)
        except Exception as exc:  # noqa: BLE001 — panel-only; must not crash the run
            _log.warning(
                "valuation_coverage_health failed for %s: %r", fund.id, exc, exc_info=True,
            )
            val_cov_healths[fund.id] = StageHealth(
                stage="valuation_coverage", status="WARN",
                reasons=(f"{fund.id}: coverage_error: {exc!r}",),
            )
        health = (signal_health, *suite_healths)
        gates.append(apply_eval_gate(view.signal, health=health,
                                     gating_stages=GATING_STAGES_M1))
    return (
        tuple(gates), signal_healths, deterministic_healths,
        flow_recon_healths, flow_cov_healths, val_recon_healths, val_cov_healths,
    )


def _write_eval_artifacts(
    out: Path, root: Path, funds: list[MonitorFund], views: list[FundView],
    bundles: list[FundTraceBundle], gates: tuple[GateDecision, ...], *, run_date: str,
    trading_days: frozenset[date] | None, macro_narrative=None,
    unmatched_keys: tuple[str, ...] = (),
) -> None:
    """EDGE: serialize eval_trace.json (now carrying the run-level macro_narrative
    field, schema 5->6) + append the forward ledger. Failures are logged and
    swallowed — the brief must still render."""
    try:
        trace = build_eval_trace(
            tuple(zip(funds, views, gates, bundles)),
            engine_version=_ENGINE_VERSION, run_date=run_date, trading_days=trading_days,
            macro_narrative=macro_narrative,
            unmatched_impact_keys=unmatched_keys,
        )
        atomic_write_text(out / "eval_trace.json",
                          json.dumps(trace, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("eval_trace write failed", exc_info=True)
    written_at = ""  # always bound: a _now_iso() failure must not unbind the trailing append
    try:
        written_at = _now_iso()
        rows = [
            ledger_row(
                run_date=run_date, fund_id=fund.id, written_at=written_at,
                signal=view.signal,
                nav_acc=(view.nav_series[-1][1] if view.nav_series else None),
                nav_unit=view.latest_nav, as_of_date=view.as_of_date,
                published_state=published_state(view.signal, gate), gate=gate,
                manifest_versions={"engine": _ENGINE_VERSION},
                market_composite=(view.market_view.composite if view.market_view else None),
                market_bias=(view.market_view.bias if view.market_view else None),
            )
            for fund, view, gate in zip(funds, views, gates)
        ]
        append_ledger(root / "data" / "monitor" / "forward_ledger.jsonl", rows)
    except Exception:  # noqa: BLE001 — append_ledger already swallows, this guards ledger_row
        _log.warning("forward ledger write failed", exc_info=True)
    _append_nav_history_for_views(root, views, run_date=run_date, written_at=written_at)


def _run_forward_eval(root: Path, today: str) -> int | None:
    """EDGE (Comp 0): run the monitor_forward scorer inline so its artifact is
    same-day fresh. `today` is unused by the runner (it computes its own) but kept
    for symmetry with the spec + the staleness contract. Contained: a non-zero rc
    or any exception MUST NOT change `irc monitor`'s exit code — degrade to the
    pre-existing 'read latest artifact' path. Returns the scorer rc, or None on
    exception."""
    try:
        return _forward_eval_run(root)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("inline monitor_forward eval failed", exc_info=True)
        return None


_TIMELINE_MAX_DATES = 20


def _read_ledger_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    dropped = 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                dropped += 1
    if dropped:
        _log.warning("_read_ledger_rows: skipped %d malformed line(s) in %s", dropped, path)
    return rows


def _build_bias_timeline(root: Path) -> BiasTimeline:
    """EDGE-read Comp 3b: forward_ledger → deduped one row per (fund, run_date)
    (latest written_at wins), bounded to the most recent _TIMELINE_MAX_DATES run
    dates. Engine tag from manifest_versions.engine (default '0').

    Absent (fund, date) cells carry (None, '0') — a distinct no-data sentinel
    that renders differently from a real NEUTRAL signal (Finding B).
    Any exception degrades to an empty BiasTimeline — never crash the brief."""
    try:
        all_rows = _read_ledger_rows(root / "data" / "monitor" / "forward_ledger.jsonl")
        # Filter: keep only rows with BOTH run_date and fund_id (Finding A)
        well_formed = [r for r in all_rows if "run_date" in r and "fund_id" in r]
        rows = latest_per_key(well_formed)
        dates = sorted({r["run_date"] for r in rows})[-_TIMELINE_MAX_DATES:]
        by_fund: dict[str, dict[str, tuple[str | None, str]]] = {}
        for r in rows:
            if r["run_date"] not in dates:
                continue
            eng = str((r.get("manifest_versions") or {}).get("engine", "0"))
            by_fund.setdefault(r["fund_id"], {})[r["run_date"]] = (
                r.get("raw_bias") or "NEUTRAL", eng)
        # Absent cells use (None, "0") sentinel — NOT "NEUTRAL" (Finding B)
        out_rows = tuple(
            (fid, tuple(by_fund[fid].get(d, (None, "0")) for d in dates))
            for fid in sorted(by_fund)
        )
        return BiasTimeline(run_dates=tuple(dates), rows=out_rows)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("_build_bias_timeline failed; returning empty timeline", exc_info=True)
        return BiasTimeline(run_dates=(), rows=())


def _is_stale(artifact_date: str, today: str) -> bool:
    return date.fromisoformat(artifact_date) < date.fromisoformat(today) - timedelta(
        days=STALE_EVAL_DAYS)


def _load_details(root: Path, ref: str | None) -> dict:
    if not ref:
        return {}
    try:
        return json.loads((root / ref).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("could not load monitor_forward details %s", ref, exc_info=True)
        return {}


def _metric_view(m, details: dict) -> PredictiveMetricView:
    md = details.get(m.name, {})
    bd = md.get("baseline_deltas", {})

    def _d(key):
        e = bd.get(key)
        return e.get("delta") if isinstance(e, dict) and "delta" in e else None

    return PredictiveMetricView(
        name=m.name, value=m.value, status=m.status, state=md.get("state", "ok"),
        ci_low=md.get("ci_low", m.value), ci_high=md.get("ci_high", m.value),
        random_delta=_d("random"), momentum_delta=_d("momentum"),
        buy_hold_delta=_d("buy_hold"), n_observations=m.n_observations,
    )


def _headline_random_delta(root: Path, entry) -> float | None:
    """Per-week headline scalar for the review trigger: the publishable_bias_directional
    random delta. None when the headline row's state is insufficient_data/undefined,
    details.json missing, or the random baseline is itself insufficient_data."""
    rep = entry.report
    hdr = next((m for m in rep.metrics if m.name == "publishable_bias_directional"), None)
    if hdr is None:
        return None
    details = _load_details(root, hdr.details_ref)
    md = details.get("publishable_bias_directional", {})
    if md.get("state") in ("insufficient_data", "undefined"):
        return None
    rnd = md.get("baseline_deltas", {}).get("random", {})
    return rnd.get("delta") if "delta" in rnd else None


def _predictive_panel_model(root: Path, *, today: str) -> PredictivePanelModel:
    entry = latest_stage_report_entry(root, "monitor_forward", today_iso=today)
    if entry is None:
        return PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                    metrics=(), review_flag=False)
    details = _load_details(
        root, next((m.details_ref for m in entry.report.metrics if m.details_ref), None))
    metrics = tuple(_metric_view(m, details) for m in entry.report.metrics)
    weeks = dedup_iso_weeks(
        list_stage_reports(root, "monitor_forward", limit=REVIEW_TRIGGER_K * 4,
                           today_iso=today),
        k=REVIEW_TRIGGER_K)
    weekly = [_headline_random_delta(root, e) for e in reversed(weeks)]  # chronological
    return PredictivePanelModel(
        present=True, stale=_is_stale(entry.artifact_date, today),
        artifact_date=entry.artifact_date, metrics=metrics,
        review_flag=review_trigger(weekly),
    )


def _append_nav_history_for_views(
    root: Path, views: list[FundView], *, run_date: str, written_at: str,
) -> None:
    """EDGE: append each fund's bounded NAV tail to nav_history.jsonl. Bounded to
    nav_date >= run_date - NAV_APPEND_DAYS. Swallows failures — never crash the brief."""
    try:
        rows: list = []
        for v in views:
            rows.extend(nav_history_append_rows(
                fund_id=v.fund_id, acc_series=v.nav_series, run_date=run_date,
                written_at=written_at, nav_append_days=NAV_APPEND_DAYS,
            ))
        append_nav_history(root / "data" / "monitor" / "nav_history.jsonl", rows)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("nav_history append failed", exc_info=True)


# ── Main orchestration ────────────────────────────────────────────────────────


def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config, *, con=None, purchase_table=None,
    today: str | None = None, flow_slice: dict | None = None,
    theme_results: dict[str, tuple] | None = None,
    provisional_flow: dict | None = None,
    provisional_flow_as_of: str | None = None,
) -> tuple[FundView, list, FundTraceBundle]:
    """Process one fund: fetch → impacts → signal → view (+ eval bundle).

    Report v3: the per-fund LLM narrative call is GONE — every view carries the
    empty degraded NarrativeDoc; the run-level 宏观面 macro block (built once in
    run_monitor via gather_macro_narrative) replaces it (spec §5).

    `flow_slice` is the run-level flow-store slice (see prior docstring, unchanged).
    `theme_results` is the run-level shared theme-search results map (Comp 2,
    built ONCE by run_monitor for the union of all funds' themes) — when None
    (e.g. a caller/test invoking this function directly), falls back to an
    empty dict so build_evidence_pool degrades to an empty pool, mirroring the
    prior "no providers configured" empty-pool behavior for library robustness."""
    from irc.monitor.profiles import PROFILES
    from irc.monitor.valuation import ValuationResolution
    nav = nav_series_for(fund.id)
    pool = build_evidence_pool(fund, theme_results=theme_results or {})
    impacts = gather_impacts(
        fund_id=fund.id, themes=fund.themes, pool=pool,
        route=llm_config, call=llm_call,
    )
    cost_history = list(impacts.cost_entries)
    macro_rows = _impact_rows_from(impacts, fund)

    constituent_rows: tuple = ()
    const_impacts_result = None
    const_pool: tuple = ()
    holding_metrics: tuple = ()
    provisional_pct: float | None = None
    profile_spec = PROFILES.get(fund.analysis_profile)
    if profile_spec and profile_spec.lookthrough == "active_fund":
        const_pool = build_constituent_pool(fund.id, root=root)
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        full_holdings: tuple = ()
        if snap is not None:
            full_holdings = tuple(sorted(
                snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True))
        top5 = full_holdings[:_TOP_N_HOLDINGS]
        if const_pool and top5:
            holding_symbols = tuple(h.symbol for h in top5)
            const_impacts_result = gather_impacts(
                fund_id=fund.id, themes=holding_symbols, pool=const_pool,
                route=llm_config, call=llm_call,
            )
            cost_history.extend(const_impacts_result.cost_entries)
            constituent_rows = _make_constituent_rows(const_impacts_result, top5)
        if full_holdings and today is not None:
            holding_metrics = _build_full_basket_metrics(
                full_holdings, top5, fund.id, root=root, today=today, con=con,
                flow_slice=(flow_slice if flow_slice is not None
                            else _load_flow_store_slice(
                                root, tuple(h.symbol for h in top5))))
        provisional_pct = _provisional_flow_for_fund(top5, provisional_flow)

    if con is not None:
        val = resolve_valuation_state(fund, con=con, root=root)
    else:
        val = ValuationResolution(None, False, "valuation_no_anchor", path="lookthrough")

    restricted, aum_delta_pct = heat_inputs_for(fund.id, purchase_table=purchase_table)

    inp = FactorInputs(
        acc_nav=nav.acc_series if nav else (),
        minimum_observations=cfg.history.minimum_observations,
        valuation_state=val.state,
        valuation_cached=val.cached,
        restricted=restricted,
        aum_delta_pct=aum_delta_pct,
        macro_rows=macro_rows,
        constituent_rows=constituent_rows,
        flow=aggregate_flow(holding_metrics) if holding_metrics else None,
        valuation_aggregate=(
            aggregate_valuation(holding_metrics)
            if val.path == "lookthrough" and holding_metrics else None
        ),
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    signal = compute_signal(fund, scores)
    empty_narr = NarrativeDoc(fund.id, (), (), (), "empty_pool")
    view = _make_view(fund, nav, signal, scores, empty_narr, pool, impacts.status,
                      holding_metrics=holding_metrics, purchase_table=purchase_table,
                      provisional_flow_pct=provisional_pct,
                      provisional_flow_as_of=provisional_flow_as_of)
    bundle = FundTraceBundle(
        fund_id=fund.id,
        macro_impacts=impacts.impacts,
        constituent_impacts=const_impacts_result.impacts if const_impacts_result else (),
        constituent_pool=const_pool,
    )
    return view, cost_history, bundle


def _build_theme_results(root: Path, funds: list[MonitorFund]) -> dict[str, tuple]:
    """EDGE: resolve the search provider + source tiers ONCE per run, search once
    per unique theme across the whole monitor set (Comp 2). Empty dict when no
    providers configured or on any failure — every fund's build_evidence_pool then
    degrades to an empty pool exactly as the old per-fund failure path did."""
    try:
        settings = Settings()
        providers = build_providers(settings)
        if not providers:
            return {}
        provider = providers[0]
        raw_tiers = _load_source_tiers_config(root)
        if raw_tiers is None:
            _log.warning("monitor: source_tiers config missing/malformed -> all tier 3")
        tiers = tiers_from_config(raw_tiers)
        themes = _unique_themes(funds)
        return _search_all_themes(provider, themes, tiers=tiers)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("_build_theme_results failed: %s", exc, exc_info=True)
        return {}


def run_monitor(*, repo_root: str, today: str | None = None) -> int:
    """EDGE orchestrator for `irc monitor`."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    gate = preflight_gate(repo_root, "monitor")
    if gate != 0:
        return gate
    cfg = load_monitor_config(root)
    funds = resolve_funds(cfg)
    llm_config = load_yaml(root / "config/llm.yaml", root)
    con = None
    db_path = root / "data" / "local.duckdb"
    if db_path.exists():
        try:
            con = connect(db_path)
        except Exception:  # noqa: BLE001 — degrade, never crash the brief
            _log.warning("valuation DB open failed; valuation → N/A", exc_info=True)
            con = None
    purchase_table = fetch_purchase_table()  # ONE akshare call/run; None on failure → heat_no_data
    if purchase_table is None:
        _log.warning("monitor heat: purchase table unavailable → heat_no_data for all funds")
    flow_slice = _load_flow_store_slice(root, _capture_union_symbols(funds, root))
    provisional_flow = _provisional_flow_note(root, _capture_union_symbols(funds, root))
    # EDGE clock read (allowed HERE, never in render_*): stamp the ACTUAL fetch
    # time for the 盘中提示 annotation (spec §8 截至HH:MM — the 15:45 capture
    # rerun renders its own time, never a hardcoded 12:15).
    provisional_flow_as_of = (
        datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M")
        if provisional_flow else None
    )
    theme_results = _build_theme_results(root, list(funds))
    views: list[FundView] = []
    bundles: list[FundTraceBundle] = []
    all_costs: list = []
    try:
        for fund in funds:
            view, costs, bundle = _process_fund(
                fund, cfg, root, llm_config, con=con, purchase_table=purchase_table,
                today=_today, flow_slice=flow_slice, theme_results=theme_results,
                provisional_flow=provisional_flow,
                provisional_flow_as_of=provisional_flow_as_of,
            )
            views.append(view)
            bundles.append(bundle)
            all_costs.extend(costs)
    finally:
        if con is not None:
            con.close()
    macro_pool = build_macro_pool(theme_results)
    try:
        macro_result = gather_macro_narrative(
            theme_pool=macro_pool, route=llm_config, call=llm_call)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("gather_macro_narrative failed: %s", exc, exc_info=True)
        macro_result = MacroNarrativeResult(MacroNarrativeDoc((), f"gather_error: {exc}"), ())
    all_costs.extend(macro_result.cost_entries)
    macro_pool_items = tuple(ev for items in macro_pool.values() for ev in items)
    now_dt = datetime.now(timezone(timedelta(hours=8)))
    trading_days = load_trading_days(date.today(), root=root)
    suite_healths, suite_rows = _suite_eval(root, _today, now_dt)
    (gates, signal_healths, deterministic_healths,
     flow_recon_healths, flow_cov_healths, val_recon_healths, val_cov_healths) = (
        _compute_gates(
            list(funds), views, bundles,
            min_obs=cfg.history.minimum_observations, suite_healths=suite_healths,
            trading_days=trading_days)
    )
    panel_rows = build_panel_rows(
        signal_healths, deterministic_healths, now=_now_iso(), suite_rows=suite_rows,
        flow_reconciliation_healths=flow_recon_healths,
        flow_coverage_healths=flow_cov_healths,
        valuation_reconciliation_healths=val_recon_healths,
        valuation_coverage_healths=val_cov_healths,
    )
    prior, prior_run_date = _read_prior_signal_with_date(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    # 002 ship-review round 1, Finding 1 (P0): known themes = the same
    # config-derived theme set the renderer's fund-chip lookup uses
    # (mirrors render_html._invert_fund_themes' source, FundView.themes) —
    # NOT a new config surface. A macro impact key absent from it is a
    # typo'd/stale/renamed LLM echo that would otherwise render as silent
    # "no record" forever (impact_validate.py:37 never validates the key).
    known_themes = {theme for v in views for theme in v.themes}
    macro_impacts_by_fund = {b.fund_id: b.macro_impacts for b in bundles}
    unmatched_keys = unmatched_impact_keys(known_themes, macro_impacts_by_fund)
    if unmatched_keys:
        _log.warning(
            "monitor: macro impact key(s) unmatched by any rendered theme "
            "(typo'd/stale/renamed LLM echo, invisible on the report): %s",
            ", ".join(unmatched_keys),
        )
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates,
                          run_date=_today, trading_days=trading_days,
                          macro_narrative=macro_result.doc,
                          unmatched_keys=unmatched_keys)
    _run_forward_eval(root, _today)  # Comp 0: same-day-fresh artifact; contained
    timeline = _build_bias_timeline(root)
    predictive_panel = _predictive_panel_model(root, today=_today)
    raw_tiers_for_drilldown = _load_source_tiers_config(root)
    if raw_tiers_for_drilldown is None:
        _log.warning("monitor: source_tiers config missing/malformed -> all tier 3")
    tiers = tiers_from_config(raw_tiers_for_drilldown)
    constituent_pool_items = tuple(
        ev for b in bundles for ev in b.constituent_pool
    )
    purchase_tags = {v.fund_id: v.purchase_tag for v in views}
    _write_outputs(out, views, prior, gates, panel_rows, predictive_panel=predictive_panel,
                   timeline=timeline, macro_doc=macro_result.doc,
                   macro_pool_items=macro_pool_items, tiers=tiers,
                   constituent_pool_items=constituent_pool_items,
                   prior_run_date=prior_run_date,
                   purchase_tags=purchase_tags,
                   macro_impacts_by_fund=macro_impacts_by_fund,
                   now_dt=now_dt)
    _write_drilldown(out, tuple(views))
    record_command_run(
        repo_root=root,
        history=all_costs,
        search_units={},
        today=datetime.fromisoformat(_today).date(),
    )
    return 0


_FLOW_KEEP_TD = 25


def _capture_union_symbols(funds, root: Path) -> tuple:
    """The union of the monitor set's active-fund top-5 look-through symbols."""
    from irc.monitor.profiles import PROFILES
    syms: list[str] = []
    for fund in funds:
        spec = PROFILES.get(fund.analysis_profile)
        if not (spec and spec.lookthrough == "active_fund"):
            continue
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        if snap is None:
            continue
        top = sorted(snap.constituent_analyses, key=lambda c: c.weight_pct,
                     reverse=True)[:_TOP_N_HOLDINGS]
        syms.extend(h.symbol for h in top)
    return tuple(dict.fromkeys(syms))


def run_flow_capture(*, repo_root: str, today: str | None = None) -> int:
    """EDGE (15:45 job, D6): ONE ulist.np batch → append the now-final f184 to the
    completed-day store. No LLM, no report, no ledger. `today` MUST be a completed
    CN trading day (the wrapper runs it after the 15:00 close)."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    funds = resolve_funds(load_monitor_config(root))
    symbols = _capture_union_symbols(funds, root)
    if not symbols:
        _log.warning("flow-capture: no active-fund symbols; nothing to capture")
        return 0
    try:
        by_symbol, _industry = fetch_flow_today_batch(symbols)
    except Exception:  # noqa: BLE001 — degrade, never crash (breaker/abort posture)
        _log.warning("flow-capture: ulist.np batch failed", exc_info=True)
        return 0
    trading_days = load_trading_days(date.today(), root=root)
    tds = tuple(d.isoformat() for d in (trading_days or ()))
    append_today(root / "data" / "monitor" / "fund_flow_series.json", _today,
                 by_symbol, keep_td=_FLOW_KEEP_TD, trading_days=tds)
    print(f"flow-capture OK: {_today} appended {sum(v is not None for v in by_symbol.values())}"
          f"/{len(symbols)} symbols")
    return 0
