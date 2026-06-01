from __future__ import annotations
import json
from pathlib import Path



def _seed_minimal_repo(tmp_path: Path) -> None:
    """Create the minimum file layout needed by run_opportunity."""
    from datetime import datetime, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True)
    (tmp_path / "outputs" / "2026-05-14").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    # Write a fresh akshare manifest so the freshness gate passes by default.
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))

    # inputs/account.yaml
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund, cn_brokerage]\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )

    # inputs/preferences.yaml — minimal viable
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_etf: {center: 0.5, band: [0.4, 0.6]}\n"
        "  cn_bond_fund: {center: 0.2, band: [0.1, 0.3]}\n"
        "  us_etf: {center: 0.15, band: [0.1, 0.2]}\n"
        "  hk_etf: {center: 0.10, band: [0.05, 0.15]}\n"
        "  gold: {center: 0.05, band: [0.02, 0.1]}\n"
        "currency_tolerance:\n  cny: [0.5, 1.0]\n  usd: [0.0, 0.4]\n  hkd: [0.0, 0.3]\n"
        "constraints:\n  allow_short: false\n  allow_leverage: false\n  exclude_themes: []\n"
        "investment_plan:\n  monthly_new_capital_cny: 5000\n"
        "report_language: zh\n",
        encoding="utf-8",
    )

    # config files — copy from the project's templates directory at runtime; the
    # tested command does not need the full bundle for opportunity-only logic.
    repo = Path(__file__).resolve().parents[2]
    src_tpl = repo / "src" / "irc" / "templates"
    for fname in (
        "config/llm.yaml", "config/scoring.yaml", "config/gold_drivers.yaml",
        "config/discovery.yaml", "config/valuation_buckets.yaml",
        "config/triggers.yaml", "config/overrides.yaml", "config/macro_view.yaml",
        "config/universe/qdii_us.yaml", "config/universe/qdii_hk.yaml",
        "config/universe/cn_funds.yaml", "config/universe/gold.yaml",
    ):
        target = tmp_path / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((src_tpl / fname).read_text(encoding="utf-8"), encoding="utf-8")

    # outputs/2026-05-14/scoring.json — a single instrument
    (tmp_path / "outputs" / "2026-05-14" / "scoring.json").write_text(
        json.dumps({
            "scores": [{
                "instrument_id": "510300",
                "asset_class": "cn_etf",
                "role": "core_cn_equity",
                "composite_score": 75.0,
                "action": "buy_candidate",
                "data_completeness": 0.85,
                "factor_breakdown": {
                    "valuation_cost": {"score": 80, "raw_refs": []},
                    "risk": {"score": 70, "raw_refs": []},
                    "quality": {"score": 75, "raw_refs": []},
                    "macro_fit": {"score": 65, "raw_refs": []},
                    "thesis_news": {"score": 80, "raw_refs": []},
                },
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_opportunity_command_writes_three_outputs(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd._today", lambda: "2026-05-14"
    )
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    out = tmp_path / "outputs" / "2026-05-14"
    assert (out / "opportunity_report.json").exists()
    assert (out / "thesis_cards.yaml").exists()
    assert (out / "discipline_report.md").exists()


def test_opportunity_report_json_has_summary_and_rows(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    payload = json.loads((tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json").read_text())
    assert payload["date"] == "2026-05-14"
    assert "summary" in payload
    assert isinstance(payload["rows"], list)


def test_opportunity_markdown_starts_with_chinese_sections(tmp_path: Path, monkeypatch):
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    md = (tmp_path / "outputs" / "2026-05-14" / "discipline_report.md").read_text()
    assert "## 今日可定投" in md
    assert "## 关于回撤的说明" in md


def test_opportunity_does_not_read_external_worktree_path(tmp_path: Path, monkeypatch):
    """Acceptance criterion: never read the external worktree generated universe."""
    import irc.commands.opportunity_cmd as opp_mod
    src = Path(opp_mod.__file__).read_text(encoding="utf-8")
    assert "investment-research-copilot.worktrees" not in src


def test_opportunity_works_with_missing_scoring(tmp_path: Path, monkeypatch):
    """Falls back to latest outputs when today's scoring.json missing."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Move scoring under an older date
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0


def test_opportunity_returns_error_for_invalid_theme_thesis(tmp_path: Path, monkeypatch, capsys):
    """Issue 4 fix: invalid theme_thesis.yaml must return rc=2 with a clean error."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    (tmp_path / "config" / "opportunity").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "opportunity" / "theme_thesis.yaml").write_text(
        "themes:\n  semiconductor: TYPO_STATE\n", encoding="utf-8"
    )
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 2
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "theme_thesis.yaml" in captured.out


def test_opportunity_prints_warning_for_stale_scoring(tmp_path: Path, monkeypatch, capsys):
    """Issue 5 fix: stale scoring.json fallback must emit a WARNING."""
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    today_dir = tmp_path / "outputs" / "2026-05-14"
    older_dir = tmp_path / "outputs" / "2026-05-13"
    older_dir.mkdir(parents=True)
    (today_dir / "scoring.json").rename(older_dir / "scoring.json")
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    run_opportunity(repo_root=str(tmp_path))
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "2026-05-13" in captured.out


def test_empty_available_venues_treats_all_instruments_as_compatible(tmp_path: Path, monkeypatch, capsys):
    """Empty available_venues (no restriction configured) means venue_compatible=True for all.

    An account with no venues declared should not block every instrument;
    'no venue restriction configured' is treated as 'allow all'.
    """
    from irc.commands.opportunity_cmd import run_opportunity
    _seed_minimal_repo(tmp_path)
    # Override account.yaml to have no available_venues
    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: []\n"
        "    holdings:\n"
        "      - asset_class: cn_etf\n"
        "        instrument_id: '510300'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    # With empty venues, no instrument should be in exclude state due to venue.
    # Since scoring row has no venue_required in the minimal seed, all rows should be non-exclude.
    out_path = tmp_path / "outputs" / "2026-05-14" / "opportunity_report.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    excluded = [r for r in rows if r.get("opportunity_state") == "exclude"]
    assert not excluded, f"No rows should be venue-excluded when available_venues is empty: {excluded}"


def test_opportunity_refuses_to_run_when_ingest_is_stale(tmp_path: Path, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, opportunity exits with rc=1
    and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.data.manifest import ManifestEntry, write_manifest

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 1
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_opportunity_allow_stale_env_proceeds(tmp_path: Path, monkeypatch):
    """With IRC_ALLOW_STALE=1, opportunity proceeds despite stale ingest."""
    from datetime import datetime, timedelta, timezone
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.data.manifest import ManifestEntry, write_manifest

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0
    markers = list((tmp_path / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_build_input_empty_venues_treats_instrument_as_compatible():
    """Unit test: _build_input with empty set() treats venue_required instruments as compatible."""
    from irc.commands.opportunity_cmd import _build_input
    from irc.data.duckdb_helper import ensure_schema
    from unittest.mock import MagicMock
    import duckdb
    instr = MagicMock()
    instr.asset_class = "cn_etf"
    instr.market = "cn_brokerage"
    instr.theme = "broad"
    instr.tracked_index = "沪深300"
    instr.name_cn = "沪深300ETF"
    instr.venue_required = ["cn_brokerage"]
    con = duckdb.connect(":memory:")
    ensure_schema(con)
    try:
        from irc.fundamentals.provider import AkShareProvider
        inp = _build_input(
            {"instrument_id": "510300", "role": ""},
            instr, None, None, 0.0, set(),  # empty venues
            con,
            provider=AkShareProvider(),
        )
    finally:
        con.close()
    assert inp.venue_compatible is True


def test_opportunity_cmd_passes_snapshot_when_available(tmp_path: Path, monkeypatch) -> None:
    """When snapshot data is available, it is passed into build_opportunity_row."""
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.fundamentals.snapshot import write_snapshot
    from irc.fundamentals.types import ConstituentSnapshot

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")

    snap = ConstituentSnapshot(
        lookthrough_target="沪深300",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=(),
    )
    write_snapshot(snap, tmp_path / "data")

    captured_kwargs: list[dict] = []
    import irc.commands.opportunity_cmd as opp_mod
    original_build = opp_mod.build_opportunity_row

    def capturing_build(inp, theme_thesis, *, snapshot=None, theme_report=None):
        captured_kwargs.append({"snapshot": snapshot, "theme_report": theme_report})
        return original_build(inp, theme_thesis, snapshot=snapshot, theme_report=theme_report)

    monkeypatch.setattr(opp_mod, "build_opportunity_row", capturing_build)

    rc = run_opportunity(repo_root=str(tmp_path))

    assert rc == 0
    assert any(c["snapshot"] is not None for c in captured_kwargs)


def test_opportunity_cmd_passes_none_snapshot_when_no_cache(tmp_path: Path, monkeypatch) -> None:
    """When no snapshot exists and autobuild is off, snapshot=None is passed (degrade-not-halt).

    Item 005: autobuild=0 forces the legacy cache-only path, which returns None
    when no snapshot file is present on disk. This preserves the pre-005 contract.
    Fund-level autobuild behaviour when ON is covered in
    test_opportunity_cmd_fund_level.py.
    """
    from irc.commands.opportunity_cmd import run_opportunity

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")
    # Disable autobuild so the legacy cache-only path is exercised.
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "0")

    captured_kwargs: list[dict] = []
    import irc.commands.opportunity_cmd as opp_mod
    original_build = opp_mod.build_opportunity_row

    def capturing_build(inp, theme_thesis, *, snapshot=None, theme_report=None):
        captured_kwargs.append({"snapshot": snapshot, "theme_report": theme_report})
        return original_build(inp, theme_thesis, snapshot=snapshot, theme_report=theme_report)

    monkeypatch.setattr(opp_mod, "build_opportunity_row", capturing_build)

    rc = run_opportunity(repo_root=str(tmp_path))

    assert rc == 0
    assert all(c["snapshot"] is None for c in captured_kwargs)


def test_discipline_row_from_propagates_evidence_gaps_and_thesis_evidence():
    """_discipline_row_from must carry the row's thesis_evidence,
    evidence_gaps, fetch_types_attempted into the DisciplineRow so item 006
    (H3) can render the failure section and item 007 can render evidence
    bullets per row."""
    from irc.commands.opportunity_cmd import _discipline_row_from
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import (
        LookthroughTarget, OpportunityRow, ThesisEvidence,
    )

    ev = ThesisEvidence(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    row = OpportunityRow(
        instrument_id="510300", name_cn="x",
        asset_class="cn_etf", theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=("holdings_fetch_failed",),
        thesis_evidence=(ev,),
    )
    position = PositionContext(0.05, 0.0, 0.30, None, True)
    drow = _discipline_row_from(row, position)
    assert drow.thesis_evidence == (ev,)
    assert drow.evidence_gaps == ("holdings_fetch_failed",)
    # `fetch_types_attempted` is sourced from `getattr(row, "fetch_types_attempted", ())`
    # — OpportunityRow doesn't carry it today, so default is ().
    assert drow.fetch_types_attempted == ()


def test_discipline_row_from_propagates_advisory_gaps():
    """P0 fix: _discipline_row_from must propagate `advisory_gaps` so the
    discipline_report.md header suffix (AC9) renders.

    Without this, the §6 memo advisory and §5 demotion fire correctly but
    the discipline report — the document the user consults for ongoing
    position management — silently shows no warning. The user sees a
    cleaner risk picture than the data warrants.
    """
    from irc.commands.opportunity_cmd import _discipline_row_from
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import LookthroughTarget, OpportunityRow

    row = OpportunityRow(
        instrument_id="005827", name_cn="x",
        asset_class="cn_equity_fund", theme="growth",
        lookthrough_target=LookthroughTarget("active_fund", "005827", "x"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="small_watch", opportunity_reason="r",
        evidence_gaps=(),
        advisory_gaps=("top_holdings_broker_thin",),
    )
    drow = _discipline_row_from(row, PositionContext(0.05, 0.0, 0.30, None, True))
    assert drow.advisory_gaps == ("top_holdings_broker_thin",)


def test_reconstruct_opportunity_rows_round_trips_advisory_gaps():
    """P1 fix: memo's _reconstruct_opportunity_rows must round-trip
    advisory_gaps from the JSON dict so downstream consumers (current or
    future) see the field, not a silent default `()`.
    """
    from irc.commands.memo_cmd import _reconstruct_opportunity_rows

    rebuilt = [{
        "instrument_id": "005827", "name_cn": "x",
        "asset_class": "cn_equity_fund",
        "lookthrough_target": "x", "lookthrough_kind": "active_fund",
        "lookthrough_key": "005827",
        "valuation_state": "fair", "heat_state": "normal",
        "thesis_state": "intact", "product_quality_state": "acceptable",
        "opportunity_state": "small_watch", "opportunity_reason": "r",
        "evidence_gaps": [],
        "advisory_gaps": ["top_holdings_broker_thin"],
        "thesis_evidence": [],
        "constituent_analyses": [],
    }]
    rows = _reconstruct_opportunity_rows(rebuilt)
    assert len(rows) == 1
    assert rows[0].advisory_gaps == ("top_holdings_broker_thin",)


def test_discipline_row_from_passes_through_constituent_analyses():
    """Until item 003 lands, constituent_analyses is empty by default; the
    propagator still threads it (default → default) so the field exists on
    DisciplineRow for item 007's renderer."""
    from irc.commands.opportunity_cmd import _discipline_row_from
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.types import LookthroughTarget, OpportunityRow

    row = OpportunityRow(
        instrument_id="510300", name_cn="x",
        asset_class="cn_etf", theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="core_dca", opportunity_reason="r",
        evidence_gaps=(),
    )
    drow = _discipline_row_from(row, PositionContext(0.05, 0.0, 0.30, None, True))
    assert drow.constituent_analyses == ()


# ── Item 003: FetchPlan / FetchBudgetExceeded / compute_plan_hash ─────────────

def test_fetch_plan_total_calls_active_fund_only() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=5, active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=10,
    )
    # 5 × (1 + 10*3 + 4) = 5 × 35 = 175
    assert plan.total_calls() == 175


def test_fetch_plan_total_calls_with_stale_and_passive() -> None:
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=2, active_fund_stale=3,
        passive_misses=4, passive_stale=1, top_n=10,
    )
    # (2+3) × 35 + 4×2 + 1×2 = 175 + 8 + 2 = 185
    assert plan.total_calls() == 185


def test_fetch_budget_exceeded_carries_breakdown() -> None:
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan
    plan = FetchPlan(5, 0, 0, 0, 10)
    exc = FetchBudgetExceeded(plan=plan, total=155, budget=10)
    msg = str(exc)
    assert "active_fund_misses=5" in msg
    assert "cost=155" in msg
    assert "budget=10" in msg


def test_plan_hash_deterministic() -> None:
    from irc.commands.opportunity_cmd import compute_plan_hash
    h1 = compute_plan_hash("2026-05-22", ["005827", "501025"], 10)
    h2 = compute_plan_hash("2026-05-22", ["501025", "005827"], 10)
    assert h1 == h2  # sorted internally
    assert len(h1) == 12
    h3 = compute_plan_hash("2026-05-23", ["005827", "501025"], 10)
    assert h3 != h1


def test_plan_hash_includes_top_n() -> None:
    from irc.commands.opportunity_cmd import compute_plan_hash
    h1 = compute_plan_hash("2026-05-22", ["005827"], 10)
    h2 = compute_plan_hash("2026-05-22", ["005827"], 15)
    assert h1 != h2


# ── Item 003: resumable state I/O + lock ──────────────────────────────────────

def test_fetch_state_atomic_write_and_load(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state, write_fetch_state
    state = {
        "plan_hash": "abc123def456",
        "started_at": "2026-05-22T10:00:00",
        "items": [
            {"fund_id": "005827", "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-22T10:05:00"},
        ],
    }
    write_fetch_state(state, tmp_path / "data" / "fundamentals", "abc123def456")
    loaded = load_fetch_state(tmp_path / "data" / "fundamentals", "abc123def456")
    assert loaded == state


def test_fetch_state_load_returns_none_when_missing(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state
    assert load_fetch_state(tmp_path / "data" / "fundamentals", "x") is None


def test_fetch_state_load_returns_none_on_hash_mismatch(tmp_path) -> None:
    from irc.commands.opportunity_cmd import load_fetch_state, write_fetch_state
    state = {"plan_hash": "old123", "items": []}
    write_fetch_state(state, tmp_path / "data" / "fundamentals", "old123")
    # New run with different hash.
    assert load_fetch_state(tmp_path / "data" / "fundamentals", "new456") is None


def test_acquire_fetch_lock_second_call_raises(tmp_path, monkeypatch) -> None:
    import pytest
    from irc.commands.opportunity_cmd import acquire_fetch_lock, FetchLockBusy
    path = tmp_path / "lock.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd1 = acquire_fetch_lock(path)
    # Simulate a concurrent process by patching fcntl.flock to raise.
    import fcntl as fcntl_mod
    def raising(*a, **kw):
        raise BlockingIOError("locked")
    monkeypatch.setattr(fcntl_mod, "flock", raising)
    with pytest.raises(FetchLockBusy):
        acquire_fetch_lock(path)
    import os
    os.close(fd1)


# ── Item 003: autobuild env + freshness probe ──────────────────────────────────

def test_build_rows_autobuild_off_skips_active_fund_fetch(monkeypatch, tmp_path) -> None:
    """IRC_OPPORTUNITY_AUTOBUILD=0 → no AkShare calls; snapshot=None."""
    from irc.commands.opportunity_cmd import _is_active_fund_target_autobuild_on
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "0")
    assert _is_active_fund_target_autobuild_on() is False
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    assert _is_active_fund_target_autobuild_on() is True
    monkeypatch.delenv("IRC_OPPORTUNITY_AUTOBUILD", raising=False)
    assert _is_active_fund_target_autobuild_on() is True  # default on


def test_freshness_probe_same_quarter_reuses_cache(monkeypatch, tmp_path) -> None:
    """Probe returns same quarter → cache_probed_at advances, no full refetch."""
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot, HoldingsResult
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    write_active_fund_cache(cached, tmp_path)
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings",
        lambda sym, top_n=1: HoldingsResult((), "2024-03-31", "2024Q1"),
    )
    fresh, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is False
    assert fresh.cache_probed_at == "2026-05-22"


def test_freshness_probe_new_quarter_schedules_refetch(monkeypatch, tmp_path) -> None:
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.types import ActiveFundSnapshot, HoldingsResult
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings",
        lambda sym, top_n=1: HoldingsResult((), "2024-06-30", "2024Q2"),
    )
    _, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is True


def test_freshness_probe_failure_is_fail_closed(monkeypatch, tmp_path) -> None:
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.types import ActiveFundSnapshot
    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-01",
        constituent_analyses=(), failure_reasons_by_symbol={},
    )
    def boom(*a, **kw):
        raise ConnectionError("akshare 502")
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.fetch_cn_etf_holdings", boom,
    )
    _, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )
    assert refresh is True  # fail-closed


def test_freshness_probe_refetches_active_cache_with_missing_data_leg(tmp_path) -> None:
    """A fresh-by-date active-fund cache is not reusable when Policy B's
    required per-constituent data leg is missing."""
    from datetime import date
    from irc.commands.opportunity_cmd import _maybe_freshness_probe
    from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis

    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-22",
        constituent_analyses=(
            ConstituentAnalysis(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                evidence=(), failure_reasons=("filing_empty:600519",),
                one_line_view="证据获取失败",
            ),
        ),
        failure_reasons_by_symbol={},
    )

    fresh, refresh = _maybe_freshness_probe(
        cached, today=date(2026, 5, 22), root=tmp_path,
    )

    assert fresh == cached
    assert refresh is True


def test_classify_active_fund_scores_counts_missing_data_leg_cache_as_stale(tmp_path) -> None:
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_active_fund_scores
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis

    cached = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter="2024Q1", cache_probed_at="2026-05-22",
        constituent_analyses=(
            ConstituentAnalysis(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                evidence=(), failure_reasons=("filing_empty:600519",),
                one_line_view="证据获取失败",
            ),
        ),
        failure_reasons_by_symbol={},
    )
    write_active_fund_cache(cached, tmp_path)

    misses, stale = _classify_active_fund_scores(
        [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 5, 22),
        threshold_days=7,
        rebuild_fundamentals=False,
    )

    assert (misses, stale) == (0, 1)


# ── Item 003: validate_cli_args (--limit canonical rejection) ─────────────────

def test_validate_output_dir_canonical_rejects_limit(tmp_path) -> None:
    import pytest
    from irc.commands.opportunity_cmd import validate_cli_args
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=str(tmp_path / "outputs" / "2026-05-22"),
            limit=3, rebuild_fundamentals=False,
            today="2026-05-22",
        )
    assert exc.value.code == 2


def test_validate_output_dir_non_canonical_accepts_limit(tmp_path) -> None:
    from irc.commands.opportunity_cmd import validate_cli_args
    # Should not raise.
    validate_cli_args(
        output_dir="/tmp/scratch/", limit=3,
        rebuild_fundamentals=False, today="2026-05-22",
    )


def test_validate_output_dir_canonical_accepts_no_limit(tmp_path) -> None:
    from irc.commands.opportunity_cmd import validate_cli_args
    validate_cli_args(
        output_dir=str(tmp_path / "outputs" / "2026-05-22"),
        limit=None, rebuild_fundamentals=False, today="2026-05-22",
    )


# ── P0-4: validate_cli_args default (output_dir=None) covers canonical ─────────

def test_validate_none_output_dir_with_limit_rejects(tmp_path) -> None:
    """P0-4: output_dir=None + limit → treated as canonical path, exit 2."""
    import pytest
    from irc.commands.opportunity_cmd import validate_cli_args
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=None, limit=3,
            rebuild_fundamentals=False, today="2026-05-22",
        )
    assert exc.value.code == 2


def test_validate_none_output_dir_no_limit_passes() -> None:
    """P0-4: output_dir=None + no limit → fine."""
    from irc.commands.opportunity_cmd import validate_cli_args
    # Should not raise.
    validate_cli_args(
        output_dir=None, limit=None,
        rebuild_fundamentals=False, today="2026-05-22",
    )


# ── P1-a: double-append prevention ────────────────────────────────────────────

def test_evidence_routing_exception_no_double_append() -> None:
    """P1-a: when adapter raises, only *_fetch_failed appended, NOT *_fetch_failed + *_empty."""
    from unittest.mock import patch
    from irc.fundamentals.snapshot import _evidence_for_constituent
    from irc.fundamentals.types import FundHolding

    holding = FundHolding(
        symbol="600519", name_cn="贵州茅台",
        weight_pct=6.2, exchange="SH", provider_symbol="600519",
    )

    class _RaisingProvider:
        def fetch_filing_digest(self, s): raise ConnectionError("network down")
        def fetch_broker_reports(self, s, **_): raise ConnectionError("network down")
        def fetch_index_valuation(self, k): return None

    with patch("irc.fundamentals.snapshot.fetch_cn_stock_news", side_effect=ConnectionError("network down")):
        _, failures, _digest = _evidence_for_constituent(
            holding, fund_id="005827", provider=_RaisingProvider()
        )

    failure_codes = set(failures)
    # Must have fetch_failed codes.
    assert any("filing_fetch_failed" in f for f in failure_codes)
    assert any("broker_fetch_failed" in f for f in failure_codes)
    assert any("news_fetch_failed" in f for f in failure_codes)
    # Must NOT have _empty codes when exceptions fired.
    assert not any("filing_empty" in f for f in failure_codes), (
        f"double-append: filing_empty should not appear when exception fired: {failure_codes}"
    )
    assert not any("broker_empty" in f for f in failure_codes), (
        f"double-append: broker_empty should not appear when exception fired: {failure_codes}"
    )
    assert not any("news_empty" in f for f in failure_codes), (
        f"double-append: news_empty should not appear when exception fired: {failure_codes}"
    )


# ── P1-c: news adapter re-raise ───────────────────────────────────────────────

def test_cn_news_exception_propagates_to_caller() -> None:
    """P1-c: fetch_cn_stock_news re-raises; caller catches it as news_fetch_failed."""
    from unittest.mock import patch
    from irc.fundamentals.snapshot import _evidence_for_constituent
    from irc.fundamentals.types import FundHolding

    holding = FundHolding(
        symbol="600519", name_cn="贵州茅台",
        weight_pct=6.2, exchange="SH", provider_symbol="600519",
    )

    class _NullProvider:
        def fetch_filing_digest(self, s): return None
        def fetch_broker_reports(self, s, **_): return ()
        def fetch_index_valuation(self, k): return None

    with patch(
        "irc.fundamentals.snapshot.fetch_cn_stock_news",
        side_effect=ConnectionError("network"),
    ):
        _, failures, _digest = _evidence_for_constituent(
            holding, fund_id="005827", provider=_NullProvider()
        )

    assert any("news_fetch_failed:600519:ConnectionError" in f for f in failures), (
        f"expected news_fetch_failed:600519:ConnectionError in failures: {failures}"
    )
    assert not any("news_empty:600519" in f for f in failures), (
        f"news_empty should not appear when ConnectionError fired (P1-c regression): {failures}"
    )


# ── P1-h: clock-skew clamp in _is_stale ──────────────────────────────────────

def test_is_stale_future_cache_probed_at_treated_as_stale() -> None:
    """P1-h: if cache_probed_at is in the future (clock skew), treat as stale."""
    from datetime import date
    from irc.commands.opportunity_cmd import _is_stale
    from irc.fundamentals.types import ActiveFundSnapshot

    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="2099-01-01",  # far future
        constituent_analyses=(),
        failure_reasons_by_symbol={},
    )
    result = _is_stale(snap, today=date(2026, 5, 22), threshold_days=7)
    assert result is True, "future cache_probed_at (clock skew) should be treated as stale"


def test_build_rows_stamps_policy_b_gaps_for_active_fund_rows(tmp_path, monkeypatch):
    """Verify that _build_rows runs evaluate_policy_b on ActiveFundSnapshot rows
    and adds the verdict's gap_codes to the row's evidence_gaps.
    """
    from unittest.mock import patch

    import duckdb

    from irc.commands.opportunity_cmd import _build_rows
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.schemas.universe import Instrument

    # Build a single cn_equity_fund instrument.
    instr = Instrument(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
        ticker="005827", currency="cny",
        theme=None, tracked_index=None, venue_required=[],
    )
    instr_index = {"005827": instr}
    scores = [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}]

    # Snapshot with rule-1 trigger (empty constituent_analyses + fund_level failure).
    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=("holdings_fetch_failed:005827:Timeout",),
    )

    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "5000")

    con = duckdb.connect(":memory:")

    with patch(
        "irc.commands.opportunity_cmd.build_snapshot", return_value=snap,
    ), patch(
        "irc.commands.opportunity_cmd._load_latest_active_fund_cached",
        return_value=None,
    ), patch(
        "irc.commands.opportunity_cmd._classify_active_fund_scores",
        return_value=(0, 0),
    ), patch(
        "irc.commands.opportunity_cmd._classify_fund_level_scores",
        return_value=(0, 0),
    ), patch(
        "irc.commands.opportunity_cmd.write_active_fund_cache", return_value=None,
    ), patch(
        "irc.opportunity.inputs_build.populate_inputs", side_effect=lambda con, s, **kw: s,
    ):
        from irc.fundamentals.provider import AkShareProvider
        rows, _positions, _qualities, _roles, _pending_verdicts, _plan_hash, _snap_cache = _build_rows(
            scores, instr_index, {}, 0.0,
            available_venues=set(), theme_thesis=None, theme_reports={},
            root=tmp_path, asset_class_targets={}, con=con,
            output_date="2026-05-23",
            provider=AkShareProvider(),
        )
    assert len(rows) == 1
    assert "holdings_fetch_failed" in rows[0].evidence_gaps


def test_write_opportunity_outputs_accepts_pending_verdicts_kwarg(tmp_path):
    """Smoke check: _write_opportunity_outputs now accepts pending_verdicts kwarg."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs

    # Empty kept_rows; should write empty outputs without raising.
    _write_opportunity_outputs(
        kept_rows=[],
        positions={},
        qualities={},
        roles={},
        holdings={},
        out_dir=tmp_path,
        today="2026-05-23",
        pending_verdicts={},
    )


# ---------------------------------------------------------------------------
# P0-2 regression: run_opportunity must thread plan_hash + snapshot_cache_by_instrument
# ---------------------------------------------------------------------------

def _make_gapped_row(instrument_id: str, name_cn: str, evidence_gaps: tuple) -> "object":
    """Build a minimal gapped OpportunityRow."""
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    return OpportunityRow(
        instrument_id=instrument_id,
        name_cn=name_cn,
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            "active_fund", f"fund_{instrument_id}", name_cn, instrument_id,
        ),
        valuation_state="evidence_insufficient",
        heat_state="evidence_insufficient",
        thesis_state="evidence_insufficient",
        product_quality_state="evidence_insufficient",
        opportunity_state="exclude",
        opportunity_reason="",
        evidence_gaps=evidence_gaps,
    )


def test_run_opportunity_threads_plan_hash_and_snapshot_cache_to_rejections(
    tmp_path: Path, monkeypatch,
) -> None:
    """P0-2 regression: run_opportunity must pass plan_hash + snapshot_cache_by_instrument
    to _write_opportunity_outputs so that rejections.json carries a non-empty
    plan_hash and fund_level_failure_reasons for funds with known failures."""
    import json
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.discipline import PositionContext

    # Item 009 fix: citation gate now active; this test is about rejections
    # plan_hash threading, not citation coverage. Disable gate for isolation.
    import irc.commands.opportunity_cmd as _opp_mod_patch
    monkeypatch.setattr(_opp_mod_patch, "_is_canonical_out_dir", lambda _p: False)
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")

    _seed_minimal_repo(tmp_path)
    monkeypatch.setattr("irc.commands.opportunity_cmd._today", lambda: "2026-05-14")

    # Build a snapshot with a known fund-level failure reason.
    snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=("holdings_fetch_failed:005827:Timeout",),
    )
    gapped_row = _make_gapped_row("005827", "易方达蓝筹精选", ("holdings_fetch_failed",))
    publishable_row = _make_gapped_row("510300", "沪深300ETF", ())
    position = PositionContext(
        portfolio_weight=None, target_band_low=None, target_band_high=None,
        drawdown_since_entry=None, is_holding=False,
    )

    # Patch _build_rows to return a known plan_hash and snapshot_cache.
    import irc.commands.opportunity_cmd as opp_mod

    def fake_build_rows(*args, **kwargs):
        rows = [publishable_row, gapped_row]
        positions = {"005827": position, "510300": position}
        qualities = {}
        roles = {}
        pending_verdicts = {}
        plan_hash = "deadbeef1234"
        snapshot_cache_by_instrument = {"005827": snap}
        return rows, positions, qualities, roles, pending_verdicts, plan_hash, snapshot_cache_by_instrument

    monkeypatch.setattr(opp_mod, "_build_rows", fake_build_rows)

    rc = run_opportunity(repo_root=str(tmp_path))
    assert rc == 0

    rejections_path = tmp_path / "outputs" / "2026-05-14" / "rejections.json"
    assert rejections_path.exists(), "rejections.json must be written"
    body = json.loads(rejections_path.read_text(encoding="utf-8"))

    # plan_hash must be threaded through — not empty string.
    assert body["plan_hash"] == "deadbeef1234", (
        f"plan_hash was {body['plan_hash']!r} — run_opportunity did not pass it through"
    )

    # At least one rejection entry must carry fund_level_failure_reasons.
    gapped_entries = [e for e in body["entries"] if e["instrument_id"] == "005827"]
    assert gapped_entries, "005827 must appear in rejections"
    assert gapped_entries[0]["fund_level_failure_reasons"] == [
        "holdings_fetch_failed:005827:Timeout"
    ], (
        f"fund_level_failure_reasons was {gapped_entries[0]['fund_level_failure_reasons']!r} "
        "— run_opportunity did not pass snapshot_cache_by_instrument through"
    )


# ── Item 007 OQ2 — _stamp_audit_errors_from_verdict helper ───────────────────


def test_build_rows_stamps_audit_errors_from_publishable_verdict_coverage(monkeypatch) -> None:
    """OQ2 — when Policy B returns a publishable verdict (no gap_codes) whose
    constituent_coverage carries non-empty audit_errors on any entry, the
    audit_errors MUST be stamped onto OpportunityRow.constituent_analyses[*]
    via dataclasses.replace. Locked because item 007's renderer reads
    OpportunityRow.constituent_analyses[*].audit_errors directly."""
    import irc.commands.opportunity_cmd as oc
    from irc.fundamentals.types import ConstituentAnalysis
    from irc.opportunity.policy_b import (
        ConstituentCoverageEntry, PolicyBVerdict,
    )

    # Synthesise a publishable verdict whose coverage carries an audit_error
    # on one symbol (a future-state defence-in-depth case).
    fake_verdict = PolicyBVerdict(
        gap_codes=(),  # ← publishable
        audit_errors=(),
        decision_rule="synthetic publishable with audit-error",
        material_symbols=("600519",),
        constituent_coverage=(
            ConstituentCoverageEntry(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                weight_rank=1, in_material_top_half=True, exchange="SH",
                has_data_leg=True, has_info_leg=True,
                data_kind_count=1, information_kind_count=1,
                failure_reasons=(),
                audit_errors=("missing_constituent_record:600519",),  # ← stamp source
            ),
        ),
    )

    def fake_evaluate(snapshot, *, top_n):
        return fake_verdict

    monkeypatch.setattr(oc, "evaluate_policy_b", fake_evaluate)
    # The function-level test cannot run _build_rows end-to-end without all
    # config inputs. Instead, assert the post-Policy-B stamping helper
    # exists and behaves correctly on a constructed input.
    assert hasattr(oc, "_stamp_audit_errors_from_verdict"), \
        "_stamp_audit_errors_from_verdict helper must exist (OQ2 wiring)"

    # Build a row whose constituent_analyses includes 600519.
    from irc.opportunity.types import OpportunityRow
    from irc.fundamentals.types import LookthroughTarget
    c1 = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="x",
        audit_errors=(),  # initially empty
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(),
        constituent_analyses=(c1,),
    )
    patched = oc._stamp_audit_errors_from_verdict(row, fake_verdict)
    assert patched.constituent_analyses[0].audit_errors == \
        ("missing_constituent_record:600519",)
    # Other fields unchanged.
    assert patched.instrument_id == "005827"
    assert patched.constituent_analyses[0].symbol == "600519"


def test_stamp_audit_errors_no_op_when_coverage_empty() -> None:
    """No-op when verdict.constituent_coverage carries no audit_errors."""
    import irc.commands.opportunity_cmd as oc
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.policy_b import (
        ConstituentCoverageEntry, PolicyBVerdict,
    )
    from irc.opportunity.types import OpportunityRow

    fake_verdict = PolicyBVerdict(
        gap_codes=(), audit_errors=(),
        decision_rule="publishable, no errors",
        material_symbols=("600519",),
        constituent_coverage=(
            ConstituentCoverageEntry(
                symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
                weight_rank=1, in_material_top_half=True, exchange="SH",
                has_data_leg=True, has_info_leg=True,
                data_kind_count=1, information_kind_count=1,
                failure_reasons=(),
                audit_errors=(),  # ← empty
            ),
        ),
    )
    c1 = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="",
        audit_errors=(),
    )
    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827", display_cn="易方达",
            provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="strong", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(), thesis_evidence=(),
        constituent_analyses=(c1,),
    )
    patched = oc._stamp_audit_errors_from_verdict(row, fake_verdict)
    # Identical content (no audit_errors added).
    assert patched.constituent_analyses[0].audit_errors == ()


# ── Item 007 Q10 — _write_opportunity_outputs loads trade_plan for pick order ─


def test_write_opportunity_outputs_loads_trade_plan_for_pick_order(tmp_path, monkeypatch) -> None:
    """Q10 — _write_opportunity_outputs computes pick_order_iids from
    trade_plan.yaml so the appendix ordering matches the memo pick-table."""
    # Item 009 fix: rows lack thesis evidence; disable citation gate for isolation.
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    import yaml
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    # Write a minimal trade_plan.yaml in tmp_path.
    plan = {"trades": [
        {"target": "163417", "target_weight": 0.1},
        {"target": "005827", "target_weight": 0.05},
    ]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "trade_plan.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")

    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.2,
        evidence=(), failure_reasons=(), one_line_view="",
    )

    def _row(iid: str, name: str):
        from irc.fundamentals.types import ThesisEvidence
        evs = (
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/d",
                date="2024-04-15", summary="x", scope="instrument",
                citation_kind="data", owner_instrument_id=iid,
                parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/i",
                date="2024-04-16", summary="x", scope="instrument",
                citation_kind="information", owner_instrument_id=iid,
                parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
        )
        return OpportunityRow(
            instrument_id=iid, name_cn=name, asset_class="cn_equity_fund",
            theme=None,
            lookthrough_target=LookthroughTarget(
                kind="active_fund", key=iid, display_cn=name,
                provider_symbol="",
            ),
            valuation_state="fair", heat_state="normal", thesis_state="intact",
            product_quality_state="strong", opportunity_state="core_dca",
            opportunity_reason="", evidence_gaps=(), thesis_evidence=evs,
            constituent_analyses=(c,),
        )

    rows = [_row("005827", "A基金"), _row("163417", "B基金")]
    positions = {iid: type("P", (), {
        "portfolio_weight": None, "target_band_low": None,
        "target_band_high": None, "drawdown_since_entry": None,
        "is_holding": False,
    })() for iid in ("005827", "163417")}

    _write_opportunity_outputs(
        rows, positions, {}, {}, {}, tmp_path, "2026-05-23",
        pending_verdicts={}, plan_hash="",
        snapshot_cache_by_instrument={},
    )
    discipline = (tmp_path / "discipline_report.md").read_text(encoding="utf-8")
    # 163417 (first in trade_plan) appears before 005827 in the appendix.
    pos_b = discipline.index("### 163417")
    pos_a = discipline.index("### 005827")
    assert pos_b < pos_a, \
        f"appendix not ordered by pick-row; got:\n{discipline}"


def test_load_pick_order_iids_propagates_non_yaml_exceptions(tmp_path) -> None:
    """Regression — pre-merge silent-failure review surfaced that
    `except (OSError, Exception)` silently swallowed every error
    (including TypeErrors inside the comprehension over `doc.get("trades")`).
    The narrowed `except (OSError, yaml.YAMLError)` must propagate other
    exceptions. Lock by constructing a `trade_plan.yaml` whose `trades`
    contains a non-mapping entry — the generator's `.get` call raises
    AttributeError, which must NOT be swallowed."""
    import pytest
    from irc.commands.opportunity_cmd import _load_pick_order_iids
    # Valid YAML, but `trades` contains a string instead of a dict.
    plan_path = tmp_path / "trade_plan.yaml"
    plan_path.write_text("trades:\n  - just_a_string\n", encoding="utf-8")
    with pytest.raises(AttributeError):
        _load_pick_order_iids(tmp_path)


def test_load_pick_order_iids_tolerates_malformed_yaml(tmp_path) -> None:
    """Negative complement — a true YAML parse error returns `()` per Q10
    backward-compat (the appendix then renders in instrument_id-ascending
    order, no crash)."""
    from irc.commands.opportunity_cmd import _load_pick_order_iids
    plan_path = tmp_path / "trade_plan.yaml"
    plan_path.write_text(": ::: malformed ::: :\n", encoding="utf-8")
    assert _load_pick_order_iids(tmp_path) == ()
