"""Acceptance criteria 11, 12, 16, 18, 19, 20, 21, 22, 23 + round-2/3 hardening."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.commands.opportunity_cmd import (
    FetchBudgetExceeded, FetchLockBusy, FetchPlan,
    acquire_fetch_lock, validate_cli_args,
)


# ── Shared seed helpers ───────────────────────────────────────────────────────

def _seed_repo_with_active_funds(tmp_path: Path, fund_ids: list[str], date: str = "2026-05-14") -> None:
    """Seed a minimal repo with N cn_equity_fund rows in scoring.json."""
    from datetime import datetime, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    (tmp_path / "inputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "universe").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "opportunity").mkdir(parents=True, exist_ok=True)
    (tmp_path / "outputs" / date).mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))

    (tmp_path / "inputs" / "account.yaml").write_text(
        "accounts:\n"
        "  - broker: cmb\n"
        "    currency: cny\n"
        "    available_venues: [cmb_fund]\n"
        "    holdings:\n"
        "      - asset_class: cn_equity_fund\n"
        "        instrument_id: '005827'\n"
        "        cost_basis_cny: 10000\n",
        encoding="utf-8",
    )
    (tmp_path / "inputs" / "preferences.yaml").write_text(
        "risk_band:\n  max_drawdown: [0.05, 0.20]\n  horizon: long_core_medium_rotation\n"
        "universe:\n  cn_funds: true\n  cn_etfs: true\n  hk_etfs: true\n  us_etfs: true\n"
        "asset_class_targets:\n"
        "  cn_equity_fund: {center: 0.3, band: [0.2, 0.4]}\n"
        "  cn_etf: {center: 0.2, band: [0.1, 0.3]}\n"
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

    scores = [
        {
            "instrument_id": fid,
            "asset_class": "cn_equity_fund",
            "role": "active_cn",
            "composite_score": 70.0,
            "action": "buy_candidate",
            "data_completeness": 0.85,
            "factor_breakdown": {
                "valuation_cost": {"score": 70, "raw_refs": []},
                "risk": {"score": 70, "raw_refs": []},
                "quality": {"score": 70, "raw_refs": []},
                "macro_fit": {"score": 70, "raw_refs": []},
                "thesis_news": {"score": 70, "raw_refs": []},
            },
        }
        for fid in fund_ids
    ]
    (tmp_path / "outputs" / date / "scoring.json").write_text(
        json.dumps({"scores": scores}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_preflight_budget_exceeded_carries_breakdown_to_stderr(capsys) -> None:
    """Spec §16: budget abort prints active_fund_misses=N cost=N budget=N."""
    plan = FetchPlan(5, 0, 0, 0, 10)
    exc = FetchBudgetExceeded(plan, 155, 10)
    msg = str(exc)
    assert "active_fund_misses=5" in msg
    assert "cost=155" in msg
    assert "budget=10" in msg


def test_limit_rejected_on_canonical_path(tmp_path) -> None:
    """Spec §18."""
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=str(tmp_path / "outputs" / "2026-05-22"),
            limit=3, rebuild_fundamentals=False, today="2026-05-22",
        )
    assert exc.value.code == 2


def test_concurrent_lock_second_call_raises(tmp_path, monkeypatch) -> None:
    """Spec §21."""
    import os
    fd1 = acquire_fetch_lock(tmp_path / "lock.lock")
    import fcntl
    monkeypatch.setattr(
        fcntl, "flock",
        lambda *a, **kw: (_ for _ in ()).throw(BlockingIOError("locked")),
    )
    with pytest.raises(FetchLockBusy):
        acquire_fetch_lock(tmp_path / "lock.lock")
    os.close(fd1)


# ── End-to-end wiring tests (item 003 drift fix) ─────────────────────────────

def test_limit_caps_active_fund_autobuild_rows(tmp_path: Path, monkeypatch) -> None:
    """Spec §17/19: --limit 3 on a scratch dir → only 3 cn_equity_fund rows built.

    Deterministic order = sorted by instrument_id; mock build_snapshot to count
    calls per fund_id.
    """
    import irc.commands.opportunity_cmd as opp_mod

    fund_ids = ["005827", "100032", "110022", "161725"]  # 4 funds, sorted order
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")

    called_fund_ids: list[str] = []

    from irc.fundamentals.types import ActiveFundSnapshot

    def mock_build_snapshot(target, top_n=10):
        called_fund_ids.append(target.provider_symbol)
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        limit=3,
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, f"run_opportunity returned {rc}"
    # Exactly 3 build_snapshot calls, for the 3 lowest sorted fund_ids.
    assert len(called_fund_ids) == 3, f"expected 3 calls, got {called_fund_ids}"
    assert called_fund_ids == sorted(called_fund_ids[:3]), "build order is not sorted"
    assert "161725" not in called_fund_ids, "4th fund should be excluded by --limit"


def test_limit_rejected_on_canonical_output_path_via_run_opportunity(tmp_path: Path, monkeypatch) -> None:
    """Spec §18: --limit on outputs/<today>/ path must exit with code 2."""
    import irc.commands.opportunity_cmd as opp_mod

    _seed_repo_with_active_funds(tmp_path, ["005827", "100032", "110022"], date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")

    canonical_out = str(tmp_path / "outputs" / "2026-05-14")
    with pytest.raises(SystemExit) as exc_info:
        opp_mod.run_opportunity(
            repo_root=str(tmp_path),
            limit=3,
            output_dir=canonical_out,
        )
    assert exc_info.value.code == 2


def test_rebuild_fundamentals_bypasses_cache(tmp_path: Path, monkeypatch) -> None:
    """Spec §23: --rebuild-fundamentals forces build_snapshot even when cache present."""
    import irc.commands.opportunity_cmd as opp_mod
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot

    fund_ids = ["005827"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")

    # Write a fresh cache so the normal path would reuse it.
    cached_snap = ActiveFundSnapshot(
        fund_id="005827",
        source_report_date="2024-03-31",
        source_report_quarter="2024Q1",
        cache_probed_at="2026-05-14",  # fresh — normal path would NOT rebuild
        constituent_analyses=(),
        failure_reasons_by_symbol={},
    )
    write_active_fund_cache(cached_snap, tmp_path / "data")

    build_called: list[str] = []

    def mock_build_snapshot(target, top_n=10):
        build_called.append(target.provider_symbol)
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        rebuild_fundamentals=True,
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, f"run_opportunity returned {rc}"
    assert "005827" in build_called, (
        "--rebuild-fundamentals should have bypassed cache and called build_snapshot"
    )


# ── P0-1: budget gate wired into _build_rows ──────────────────────────────────

def test_budget_exceeded_exits_code_3_before_any_fetch(tmp_path: Path, monkeypatch) -> None:
    """Spec §16: IRC_FETCH_BUDGET=10 + 5 cold rows → exit 3, no .tmp files written."""
    import irc.commands.opportunity_cmd as opp_mod

    fund_ids = ["005827", "100032", "110022", "161725", "519674"]  # 5 cold funds
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "10")  # 5 × 31 = 155 > 10

    # Track any build_snapshot call (should NEVER happen before budget check).
    fetched: list[str] = []

    def mock_build_snapshot(target, top_n=10):
        fetched.append(target.provider_symbol)
        from irc.fundamentals.types import ActiveFundSnapshot
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    with pytest.raises(SystemExit) as exc_info:
        opp_mod.run_opportunity(
            repo_root=str(tmp_path),
            output_dir=str(scratch),
        )
    assert exc_info.value.code == 3, f"expected exit 3, got {exc_info.value.code}"
    # No build_snapshot calls fired before the gate raised.
    assert fetched == [], f"build_snapshot called before budget gate: {fetched}"
    # No .tmp files under scratch.
    tmps = list(scratch.rglob("*.tmp*"))
    assert tmps == [], f"tmp files found under scratch: {tmps}"


# ── P0-2: lock wired into _build_rows ─────────────────────────────────────────

def test_concurrent_run_exits_code_4(tmp_path: Path, monkeypatch) -> None:
    """Spec §21: concurrent run → exit 4 with 'concurrent run detected'."""
    import irc.commands.opportunity_cmd as opp_mod

    fund_ids = ["005827"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    # Large budget so it doesn't trigger budget gate.
    monkeypatch.setenv("IRC_FETCH_BUDGET", "9999")

    # Simulate lock already held by another process: ALL flock calls raise BlockingIOError.
    import fcntl as fcntl_mod

    def fake_flock(fd, flags, *args, **kwargs):
        raise BlockingIOError("locked by concurrent process")

    monkeypatch.setattr(fcntl_mod, "flock", fake_flock)

    with pytest.raises(SystemExit) as exc_info:
        opp_mod.run_opportunity(
            repo_root=str(tmp_path),
            output_dir=str(tmp_path / "scratch"),
        )
    assert exc_info.value.code == 4, f"expected exit 4, got {exc_info.value.code}"


# ── P0-3: fetch state wired (resume + stale-hash discard) ─────────────────────

def test_resumable_state_skips_completed_funds(tmp_path: Path, monkeypatch) -> None:
    """Spec §19: state file with 1 complete fund → second run skips that fund."""
    import irc.commands.opportunity_cmd as opp_mod
    from irc.commands.opportunity_cmd import compute_plan_hash, write_fetch_state
    from irc.fundamentals.types import ActiveFundSnapshot

    fund_ids = ["005827", "100032"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "9999")

    # Pre-write a state file marking 005827 as complete.
    plan_hash = compute_plan_hash("2026-05-14", fund_ids, 10)
    state = {
        "plan_hash": plan_hash,
        "started_at": "2026-05-14T09:00:00",
        "items": [
            {"fund_id": "005827", "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-14T09:05:00"},
        ],
    }
    fundamentals_dir = tmp_path / "data" / "fundamentals"
    fundamentals_dir.mkdir(parents=True, exist_ok=True)
    write_fetch_state(state, fundamentals_dir, plan_hash)

    fetched: list[str] = []

    def mock_build_snapshot(target, top_n=10):
        fetched.append(target.provider_symbol)
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, f"run_opportunity returned {rc}"
    # Only 100032 should be fetched (005827 was marked complete).
    assert fetched == ["100032"], f"expected only 100032 fetched, got {fetched}"


def test_stale_plan_hash_discarded(tmp_path: Path, monkeypatch) -> None:
    """Spec §20: stale plan_hash in state file → silently ignored, fresh fetch."""
    import irc.commands.opportunity_cmd as opp_mod
    from irc.commands.opportunity_cmd import write_fetch_state
    from irc.fundamentals.types import ActiveFundSnapshot

    fund_ids = ["005827"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "9999")

    # Write a state file with a DIFFERENT plan_hash (different date).
    old_hash = "deadbeef0000"
    state = {
        "plan_hash": old_hash,
        "started_at": "2026-05-13T09:00:00",
        "items": [
            {"fund_id": "005827", "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-13T09:05:00"},
        ],
    }
    fundamentals_dir = tmp_path / "data" / "fundamentals"
    fundamentals_dir.mkdir(parents=True, exist_ok=True)
    write_fetch_state(state, fundamentals_dir, old_hash)

    fetched: list[str] = []

    def mock_build_snapshot(target, top_n=10):
        fetched.append(target.provider_symbol)
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, f"run_opportunity returned {rc}"
    # 005827 must be fetched — stale state should have been discarded.
    assert "005827" in fetched, f"expected 005827 fetched despite stale state, got {fetched}"


def test_stale_plan_hash_discard_is_silent(tmp_path: Path, monkeypatch, capsys) -> None:
    """Round-3 item 1: stale plan_hash discard must NOT write to stderr (AC 20)."""
    import irc.commands.opportunity_cmd as opp_mod
    from irc.commands.opportunity_cmd import write_fetch_state
    from irc.fundamentals.types import ActiveFundSnapshot

    fund_ids = ["005827"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "9999")

    old_hash = "deadbeef1111"
    state = {
        "plan_hash": old_hash,
        "started_at": "2026-05-13T09:00:00",
        "items": [
            {"fund_id": "005827", "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-13T09:05:00"},
        ],
    }
    fundamentals_dir = tmp_path / "data" / "fundamentals"
    fundamentals_dir.mkdir(parents=True, exist_ok=True)
    write_fetch_state(state, fundamentals_dir, old_hash)

    def mock_build_snapshot(target, top_n=10):
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "discarded stale" not in captured.err, (
        f"stale-hash discard must be silent, but stderr contained: {captured.err!r}"
    )
    assert "plan_hash changed" not in captured.err, (
        f"stale-hash discard must be silent, but stderr contained: {captured.err!r}"
    )


# ── P0-4: validate_cli_args default-path + symlink ────────────────────────────

def test_limit_rejected_on_default_canonical_path(tmp_path: Path, monkeypatch) -> None:
    """Spec §18: --limit on default (output_dir=None) canonical path exits code 2."""
    import irc.commands.opportunity_cmd as opp_mod

    _seed_repo_with_active_funds(tmp_path, ["005827"], date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")

    with pytest.raises(SystemExit) as exc_info:
        opp_mod.run_opportunity(
            repo_root=str(tmp_path),
            limit=3,
            # No output_dir → defaults to outputs/2026-05-14/ (canonical)
        )
    assert exc_info.value.code == 2, (
        f"expected exit 2 for --limit on default canonical path, got {exc_info.value.code}"
    )


def test_limit_rejected_via_symlink_to_canonical(tmp_path: Path, monkeypatch) -> None:
    """P0-4 symlink bypass: symlink pointing to outputs/<today>/ must also be rejected."""
    import irc.commands.opportunity_cmd as opp_mod

    _seed_repo_with_active_funds(tmp_path, ["005827"], date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")

    canonical = tmp_path / "outputs" / "2026-05-14"
    canonical.mkdir(parents=True, exist_ok=True)
    symlink_dir = tmp_path / "sym_out"
    symlink_dir.symlink_to(canonical)

    with pytest.raises(SystemExit) as exc_info:
        validate_cli_args(
            output_dir=str(symlink_dir),
            limit=3, rebuild_fundamentals=False, today="2026-05-14",
        )
    assert exc_info.value.code == 2, (
        f"symlink to canonical should exit 2, got {exc_info.value.code}"
    )


# ── P0-5: empty-quarter cache safety ──────────────────────────────────────────

def test_empty_source_report_quarter_no_cache_written_stamps_failure_reason(tmp_path: Path) -> None:
    """Spec §5: semi-annual quarter parse → no cache file, fund_level_failure_reasons stamped."""
    from unittest.mock import patch
    from irc.fundamentals.snapshot import _build_active_fund_snapshot
    from irc.fundamentals.types import FundHolding, HoldingsResult, LookthroughTarget

    target = LookthroughTarget(
        kind="active_fund", key="fund_005827",
        display_cn="易方达蓝筹精选", provider_symbol="005827",
    )

    # Holdings with empty source_report_quarter (simulates "2024年半年度" parse failure).
    holdings_with_bad_quarter = HoldingsResult(
        constituents=(
            FundHolding(
                symbol="600519", name_cn="贵州茅台",
                weight_pct=6.2, exchange="SH", provider_symbol="600519",
            ),
        ),
        source_report_date="",
        source_report_quarter="",   # <-- key: quarter parse failed
    )

    from irc.fundamentals.provider import AkShareProvider
    with patch(
        "irc.fundamentals.snapshot.fetch_cn_etf_holdings",
        return_value=holdings_with_bad_quarter,
    ), patch("irc.fundamentals.akshare_filing._ak_call", return_value=__import__("pandas").DataFrame()):
        snap = _build_active_fund_snapshot(target, top_n=10, provider=AkShareProvider())

    # Must stamp holdings_quarter_parse_failed.
    assert any(
        "holdings_quarter_parse_failed:005827" in r
        for r in snap.fund_level_failure_reasons
    ), f"expected holdings_quarter_parse_failed:005827 in {snap.fund_level_failure_reasons}"

    # No cache file must exist under data/fundamentals/.
    cache_files = list((tmp_path / "data").rglob("fund_005827.json")) if (tmp_path / "data").exists() else []
    assert cache_files == [], f"cache file should NOT be written for empty quarter: {cache_files}"


# ── Round-3 hardening: item 3 — cache_write_failed in fund_level_failure_reasons

def test_cache_write_failed_stamped_in_fund_level_failure_reasons(tmp_path: Path, monkeypatch) -> None:
    """Round-3 item 3: when write_active_fund_cache raises, the reason
    cache_write_failed:{fund_id}:{ExcType} must appear in
    ActiveFundSnapshot.fund_level_failure_reasons (not only on stderr).
    """
    import irc.commands.opportunity_cmd as opp_mod
    from irc.fundamentals.types import ActiveFundSnapshot

    fund_ids = ["005827"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    monkeypatch.setenv("IRC_FETCH_BUDGET", "9999")

    built_snaps: list[ActiveFundSnapshot] = []

    def mock_build_snapshot(target, top_n=10):
        snap = ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )
        built_snaps.append(snap)
        return snap

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    def failing_write(snap, root):
        raise OSError("disk full")

    monkeypatch.setattr(opp_mod, "write_active_fund_cache", failing_write)

    # Capture produced rows so we can inspect fund_level_failure_reasons.
    produced_rows: list = []
    _orig_build_opp = opp_mod.build_opportunity_row

    def capturing_build_opportunity_row(inp, thesis, *, snapshot=None, theme_report=None):
        row = _orig_build_opp(inp, thesis, snapshot=snapshot, theme_report=theme_report)
        produced_rows.append(snapshot)
        return row

    monkeypatch.setattr(opp_mod, "build_opportunity_row", capturing_build_opportunity_row)

    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, f"run_opportunity returned {rc}"

    active_snaps = [s for s in produced_rows if isinstance(s, ActiveFundSnapshot)]
    assert active_snaps, "no ActiveFundSnapshot passed to build_opportunity_row"
    snap = active_snaps[0]
    assert any(
        "cache_write_failed:005827" in r for r in snap.fund_level_failure_reasons
    ), f"expected cache_write_failed:005827 in {snap.fund_level_failure_reasons}"


# ── Round-3 hardening: item 4 — budget gate credits completed_ids ─────────────

def test_budget_gate_credits_completed_ids(tmp_path: Path, monkeypatch) -> None:
    """Round-3 item 4: state file marks 3 funds complete; 5 cold + 0 stale funds
    in the score list → budget cost should be (5-3) * (1 + TOP_N*3) = 2*31 = 62,
    NOT 5 * 31 = 155.

    Set IRC_FETCH_BUDGET=100 → without credit it would exceed (155 > 100),
    with credit it should pass (62 <= 100).
    """
    import irc.commands.opportunity_cmd as opp_mod
    from irc.commands.opportunity_cmd import compute_plan_hash, write_fetch_state
    from irc.fundamentals.types import ActiveFundSnapshot

    # 5 funds, all cold (no cache).
    fund_ids = ["005827", "100032", "110022", "161725", "519674"]
    _seed_repo_with_active_funds(tmp_path, fund_ids, date="2026-05-14")
    monkeypatch.setattr(opp_mod, "_today", lambda: "2026-05-14")
    monkeypatch.setenv("IRC_OPPORTUNITY_AUTOBUILD", "1")
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    # Budget between crediting (62 ≤ 100) and non-crediting (155 > 100).
    monkeypatch.setenv("IRC_FETCH_BUDGET", "100")

    # Mark 3 of the 5 funds as complete in the state file.
    plan_hash = compute_plan_hash("2026-05-14", fund_ids, 10)
    state = {
        "plan_hash": plan_hash,
        "started_at": "2026-05-14T08:00:00",
        "items": [
            {"fund_id": fid, "status": "complete",
             "source_report_quarter": "2024Q1", "fetched_at": "2026-05-14T08:05:00"}
            for fid in ["005827", "100032", "110022"]  # 3 completed
        ],
    }
    fundamentals_dir = tmp_path / "data" / "fundamentals"
    fundamentals_dir.mkdir(parents=True, exist_ok=True)
    write_fetch_state(state, fundamentals_dir, plan_hash)

    # Also write cache files so the completed funds return something from disk.
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    for fid in ["005827", "100032", "110022"]:
        cached_snap = ActiveFundSnapshot(
            fund_id=fid,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )
        write_active_fund_cache(cached_snap, tmp_path / "data")

    fetched: list[str] = []

    def mock_build_snapshot(target, top_n=10):
        fetched.append(target.provider_symbol)
        return ActiveFundSnapshot(
            fund_id=target.provider_symbol,
            source_report_date="2024-03-31",
            source_report_quarter="2024Q1",
            cache_probed_at="2026-05-14",
            constituent_analyses=(),
            failure_reasons_by_symbol={},
        )

    monkeypatch.setattr(opp_mod, "build_snapshot", mock_build_snapshot)

    # Should NOT raise FetchBudgetExceeded (62 ≤ 100).
    rc = opp_mod.run_opportunity(
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "scratch"),
    )
    assert rc == 0, (
        f"run_opportunity returned {rc} — budget gate did not credit completed_ids. "
        f"fetched={fetched}"
    )
    # Only the 2 incomplete funds should have been fetched.
    assert set(fetched) == {"161725", "519674"}, (
        f"expected only incomplete funds fetched, got {fetched}"
    )
