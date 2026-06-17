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
from irc.monitor.fetch import NavFetchResult, nav_series_for
from irc.monitor.impacts import ImpactsResult, gather_impacts
from irc.monitor.narrative import gather_narrative
from irc.monitor.news_factor import ImpactRow
from irc.monitor.profiles import theme_query_seed
from irc.monitor.render_html import render_report
from irc.monitor.returns import window_returns
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.resolve import resolve_funds
from irc.monitor.signal import compute_signal
from irc.monitor.snapshot_targets import target_for_fund
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M1, published_state
from irc.monitor.eval.structural import monitor_signal_health
from irc.monitor.eval.staleness import STALE_AFTER_DAYS, resolve_health
from irc.monitor.eval.trace import build_eval_trace
from irc.monitor.trading_calendar import load_trading_days
from irc.monitor.eval.forward_log import append_ledger, ledger_row
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
from irc.monitor.types import MonitorFund, NarrativeDoc, SignalRecord
from irc.research.search.factory import build_providers
from irc.settings import Settings
from irc.spend.record_run import record_command_run
from irc.commands.spend_cmd import preflight_gate

_log = logging.getLogger(__name__)
_ENGINE_VERSION = "1"
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


def _search_theme(provider, query: str, fund_id: str) -> tuple:
    """Run one theme search; convert hits to EvidenceItems. Returns () on failure."""
    result = provider.search(query, max_results=5, freshness_days=7)
    if result.failure_reason:
        _log.warning(
            "monitor theme search failed for %s (%r): %s",
            fund_id, query, result.failure_reason,
        )
        return ()
    items = []
    for hit in result.hits:
        items.append(make_evidence_item(
            hit.source_domain or provider.name,
            hit.title, hit.published_iso or "", hit.url,
            owner_fund_id=fund_id,
        ))
    return tuple(items)


def build_evidence_pool(fund: MonitorFund, *, repo_root: Path) -> tuple:
    """EDGE: run theme searches via configured providers → owner-bound EvidenceItems.
    Returns () when no providers are configured or on any failure (factor gate surfaces gap).
    This is the ONLY place the monitor touches search providers."""
    try:
        settings = Settings()
        providers = build_providers(settings)
        if not providers:
            return ()
        provider = providers[0]   # use first available provider
        items: list = []
        for theme in fund.themes:
            query = theme_query_seed(theme)
            items.extend(_search_theme(provider, query, fund.id))
        return tuple(items)
    except Exception as exc:
        _log.warning("build_evidence_pool failed for %s: %s", fund.id, exc, exc_info=True)
        return ()


# ── Constituent pool (EDGE — snapshot I/O) ───────────────────────────────────

_TOP_N_HOLDINGS = 5


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
) -> FundView:
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


def _narrative_dump(views: list[FundView]) -> dict:
    return {
        v.fund_id: {
            "status": v.narrative.status,
            "price_action": [c.claim for c in v.narrative.price_action_commentary],
            "signal_rationale": [c.claim for c in v.narrative.signal_rationale_commentary],
            "risk": [c.claim for c in v.narrative.risk_commentary],
        }
        for v in views
    }


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
                   predictive_panel: PredictivePanelModel | None = None) -> None:
    prov = Provenance(_ENGINE_VERSION, "1", "1", "")
    gate_map = {g.fund_id: g for g in gates} if gates else None
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso(),
                         gates=gate_map, panel_rows=panel_rows,
                         predictive_panel=predictive_panel)
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
        json.dumps(_narrative_dump(views), indent=2, sort_keys=True),
    )
    atomic_write_text(
        out / "monitor.json",
        json.dumps(_machine_summary(views), indent=2, sort_keys=True),
    )


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
) -> tuple[tuple[GateDecision, ...], dict, dict]:
    """Build each fund's trace projection ONCE, derive its monitor_signal health AND
    its deterministic_scoring health from that single projection, append the two
    run-global LLM-suite healths (resolved once at the edge — identical for every
    fund, OQ-E), and apply the M1 gate. Returns
    (gates, signal_healths, deterministic_healths); deterministic_scoring is
    PANEL-ONLY and never gates (spec §4.3)."""
    gates: list[GateDecision] = []
    signal_healths: dict = {}
    deterministic_healths: dict = {}
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
        health = (signal_health, *suite_healths)
        gates.append(apply_eval_gate(view.signal, health=health,
                                     gating_stages=GATING_STAGES_M1))
    return tuple(gates), signal_healths, deterministic_healths


def _write_eval_artifacts(
    out: Path, root: Path, funds: list[MonitorFund], views: list[FundView],
    bundles: list[FundTraceBundle], gates: tuple[GateDecision, ...], *, run_date: str,
    trading_days: frozenset[date] | None,
) -> None:
    """EDGE: serialize eval_trace.json + append the forward ledger. Failures are
    logged and swallowed — the brief must still render."""
    try:
        trace = build_eval_trace(
            tuple(zip(funds, views, gates, bundles)),
            engine_version=_ENGINE_VERSION, run_date=run_date, trading_days=trading_days,
        )
        atomic_write_text(out / "eval_trace.json",
                          json.dumps(trace, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("eval_trace write failed", exc_info=True)
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
            )
            for fund, view, gate in zip(funds, views, gates)
        ]
        append_ledger(root / "data" / "monitor" / "forward_ledger.jsonl", rows)
    except Exception:  # noqa: BLE001 — append_ledger already swallows, this guards ledger_row
        _log.warning("forward ledger write failed", exc_info=True)
    _append_nav_history_for_views(root, views, run_date=run_date, written_at=written_at)


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
    fund: MonitorFund, cfg, root: Path, llm_config,
) -> tuple[FundView, list, FundTraceBundle]:
    """Process one fund: fetch → impacts → signal → narrative → view (+ eval bundle)."""
    from irc.monitor.profiles import PROFILES
    nav = nav_series_for(fund.id)
    pool = build_evidence_pool(fund, repo_root=root)
    impacts = gather_impacts(
        fund_id=fund.id, themes=fund.themes, pool=pool,
        route=llm_config, call=llm_call,
    )
    cost_history = list(impacts.cost_entries)
    macro_rows = _impact_rows_from(impacts, fund)

    constituent_rows: tuple = ()
    const_impacts_result = None
    const_pool: tuple = ()
    profile_spec = PROFILES.get(fund.analysis_profile)
    if profile_spec and profile_spec.lookthrough == "active_fund":
        const_pool = build_constituent_pool(fund.id, root=root)
        snap = load_latest_active_fund_cached(fund.id, root / "data")
        top_holdings: tuple = ()
        if snap is not None:
            top_holdings = tuple(
                sorted(snap.constituent_analyses, key=lambda c: c.weight_pct, reverse=True)
            )[:_TOP_N_HOLDINGS]
        if const_pool and top_holdings:
            holding_symbols = tuple(h.symbol for h in top_holdings)
            const_impacts_result = gather_impacts(
                fund_id=fund.id, themes=holding_symbols, pool=const_pool,
                route=llm_config, call=llm_call,
            )
            cost_history.extend(const_impacts_result.cost_entries)
            constituent_rows = _make_constituent_rows(const_impacts_result, top_holdings)

    inp = FactorInputs(
        acc_nav=nav.acc_series if nav else (),
        minimum_observations=cfg.history.minimum_observations,
        valuation_state=None,
        valuation_cached=False,
        restricted=None,
        aum_delta_pct=None,
        macro_rows=macro_rows,
        constituent_rows=constituent_rows,
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    signal = compute_signal(fund, scores)
    narr = gather_narrative(
        fund_id=fund.id, pool=pool, route=llm_config, call=llm_call,
    )
    cost_history.extend(narr.cost_entries)
    view = _make_view(fund, nav, signal, scores, narr.doc, pool, impacts.status)
    bundle = FundTraceBundle(
        fund_id=fund.id,
        macro_impacts=impacts.impacts,
        constituent_impacts=const_impacts_result.impacts if const_impacts_result else (),
        constituent_pool=const_pool,
    )
    return view, cost_history, bundle


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
    views: list[FundView] = []
    bundles: list[FundTraceBundle] = []
    all_costs: list = []
    for fund in funds:
        view, costs, bundle = _process_fund(fund, cfg, root, llm_config)
        views.append(view)
        bundles.append(bundle)
        all_costs.extend(costs)
    now_dt = datetime.now(timezone(timedelta(hours=8)))
    trading_days = load_trading_days(date.today(), root=root)
    suite_healths, suite_rows = _suite_eval(root, _today, now_dt)
    gates, signal_healths, deterministic_healths = _compute_gates(
        list(funds), views, bundles,
        min_obs=cfg.history.minimum_observations, suite_healths=suite_healths,
        trading_days=trading_days)
    panel_rows = build_panel_rows(signal_healths, deterministic_healths,
                                  now=_now_iso(), suite_rows=suite_rows)
    prior = _read_prior_signal(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates,
                          run_date=_today, trading_days=trading_days)
    predictive_panel = _predictive_panel_model(root, today=_today)
    _write_outputs(out, views, prior, gates, panel_rows, predictive_panel=predictive_panel)
    record_command_run(
        repo_root=root,
        history=all_costs,
        search_units={},
        today=datetime.fromisoformat(_today).date(),
    )
    return 0
