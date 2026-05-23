"""Acceptance criteria 11, 12, 16, 18, 21, 22, 23."""
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
