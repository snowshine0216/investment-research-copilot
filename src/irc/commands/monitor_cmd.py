"""EDGE: `irc monitor` command — thin orchestrator + snapshot subcommand.

All business logic lives in pure cores under src/irc/monitor/.
This module is the ONLY place I/O (filesystem, network, AkShare, LLM) is
allowed in the monitor vertical. It reads ONLY config/monitor.yaml via
load_monitor_config — never load_repo_configs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from irc.config_loader import load_monitor_config, load_yaml
from irc.fundamentals.snapshot import build_snapshot, write_snapshot
from irc.io_utils import atomic_write_text
from irc.llm.gateway import call as llm_call
from irc.monitor.evidence import make_evidence_item
from irc.monitor.factors import FactorInputs, build_factor_scores
from irc.monitor.fetch import NavFetchResult, nav_series_for
from irc.monitor.impacts import ImpactsResult, gather_impacts
from irc.monitor.narrative import gather_narrative
from irc.monitor.news_factor import ImpactRow
from irc.monitor.profiles import theme_query_seed
from irc.monitor.render_html import render_report
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.resolve import resolve_funds
from irc.monitor.signal import compute_signal
from irc.monitor.snapshot_targets import target_for_fund
from irc.monitor.types import MonitorFund, NarrativeDoc, SignalRecord
from irc.research.search.factory import build_providers
from irc.settings import Settings
from irc.spend.record_run import record_command_run
from irc.commands.spend_cmd import preflight_gate

_log = logging.getLogger(__name__)
_ENGINE_VERSION = "1"


# ── Snapshot subcommand ───────────────────────────────────────────────────────


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
        path = write_snapshot(snapshot, root / "data")
        reasons = getattr(snapshot, "failure_reasons", ())
        if reasons:
            print(f"WARNING: {fund.id} snapshot gaps: {'; '.join(reasons)}")
        print(f"monitor snapshot OK: {fund.id} -> {path}")
    return 0


# ── Evidence pool (EDGE) ──────────────────────────────────────────────────────


def _search_theme(provider, query: str, fund_id: str) -> tuple:
    """Run one theme search; convert hits to EvidenceItems. Returns () on failure."""
    result = provider.search(query, max_results=5, freshness_days=7)
    if result.failure_reason:
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
        return_table={},
        factor_freshness={c.name: "fresh" for c in signal.contributions},
        missing_factor_reasons=tuple(
            f"{s.name}: {s.reason}" for s in scores if not s.eligible
        ),
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


def _write_outputs(out: Path, views: list[FundView], prior: dict | None) -> None:
    prov = Provenance(_ENGINE_VERSION, "1", "1", "")
    html = render_report(tuple(views), prov, prior_signal=prior, now=_now_iso())
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


# ── Main orchestration ────────────────────────────────────────────────────────


def _process_fund(
    fund: MonitorFund, cfg, root: Path, llm_config,
) -> tuple[FundView, list]:
    """Process one fund: fetch → impacts → signal → narrative → view."""
    nav = nav_series_for(fund.id)
    pool = build_evidence_pool(fund, repo_root=root)
    impacts = gather_impacts(
        fund_id=fund.id, themes=fund.themes, pool=pool,
        route=llm_config, call=llm_call,
    )
    cost_history = list(impacts.cost_entries)
    macro_rows = _impact_rows_from(impacts, fund)
    inp = FactorInputs(
        acc_nav=nav.acc_series if nav else (),
        minimum_observations=cfg.history.minimum_observations,
        valuation_state=None,
        valuation_cached=False,
        restricted=None,
        aum_delta_pct=None,
        macro_rows=macro_rows,
        constituent_rows=(),
    )
    scores = build_factor_scores(fund.analysis_profile, inp)
    signal = compute_signal(fund, scores)
    narr = gather_narrative(
        fund_id=fund.id, pool=pool, route=llm_config, call=llm_call,
    )
    cost_history.extend(narr.cost_entries)
    view = _make_view(fund, nav, signal, scores, narr.doc, pool, impacts.status)
    return view, cost_history


def run_monitor(*, repo_root: str, today: str | None = None) -> int:
    """EDGE orchestrator for `irc monitor`."""
    root = Path(repo_root)
    _today = today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    gate = preflight_gate(repo_root, "monitor")
    if gate != 0:
        return gate
    cfg = load_monitor_config(root)
    funds = resolve_funds(cfg)
    llm_config = load_yaml(root / "config/llm.yaml", root)   # narrow LLMConfig (sole-source OK)
    views: list[FundView] = []
    all_costs: list = []
    for fund in funds:
        view, costs = _process_fund(fund, cfg, root, llm_config)
        views.append(view)
        all_costs.extend(costs)
    prior = _read_prior_signal(root, _today)
    out = root / "outputs" / _today / "monitor"
    out.mkdir(parents=True, exist_ok=True)
    _write_outputs(out, views, prior)
    record_command_run(
        repo_root=root,
        history=all_costs,
        search_units={},
        today=datetime.fromisoformat(_today).date(),
    )
    return 0
