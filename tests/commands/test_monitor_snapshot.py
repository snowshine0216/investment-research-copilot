from __future__ import annotations

import textwrap
from pathlib import Path

from irc.commands.monitor_cmd import _persist_snapshot, run_monitor_snapshot
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    FundLevelSnapshot,
    FundNavReport,
)

_YAML = textwrap.dedent("""
schema_version: 1
defaults: { signal_bands: { buy: 0.40, sell: -0.40 } }
funds:
  - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
  - { id: "519069", name_cn: 价值, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary, geopolitics], constituent_news: true }
""")


def test_snapshot_builds_typed_targets(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    built = []

    def fake_build_snapshot(target, **kw):
        built.append(target)

        class _S:  # minimal snapshot stub
            failure_reasons = ()

        return _S()

    monkeypatch.setattr("irc.commands.monitor_cmd.build_snapshot", fake_build_snapshot)
    # monkeypatch the dispatch helper so the stub _S passes through
    monkeypatch.setattr(
        "irc.commands.monitor_cmd._persist_snapshot",
        lambda s, d: d / "x.json",
    )

    rc = run_monitor_snapshot(repo_root=str(tmp_path))
    assert rc == 0
    kinds = {t.kind for t in built}
    assert "active_fund" in kinds and "gold" in kinds
    assert all(t.provider_symbol for t in built)  # never broad_index w/o symbol
    assert "broad_index" not in kinds


# ── _persist_snapshot dispatch tests ─────────────────────────────────────────


def _make_fund_level_snapshot(fund_id: str, qdii_sentinel: bool = False) -> FundLevelSnapshot:
    """Build a minimal FundLevelSnapshot for testing."""
    if qdii_sentinel:
        return FundLevelSnapshot(
            fund_id=fund_id,
            nav_report=None,
            announcements=(),
            evidence=(),
            source_report_quarter="2026Q1",
            cache_probed_at="2026-06-15T08:00:00+08:00",
            fund_level_failure_reasons=(),
            evidence_gaps=("qdii_information_unavailable",),
        )
    nav = FundNavReport(
        fund_id=fund_id,
        fund_name="测试基金",
        latest_nav=1.234,
        latest_nav_date="2026-06-13",
        nav_history=(("2026-06-13", 1.234),),
        source_report_quarter="2026Q1",
    )
    return FundLevelSnapshot(
        fund_id=fund_id,
        nav_report=nav,
        announcements=(),
        evidence=(),
        source_report_quarter="2026Q1",
        cache_probed_at="2026-06-15T08:00:00+08:00",
        fund_level_failure_reasons=(),
        evidence_gaps=(),
    )


def _make_active_fund_snapshot(fund_id: str) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at="2026-06-15T08:00:00+08:00",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=(),
        fund_level_evidence=(),
    )


def test_persist_snapshot_fund_level_writes_nav_cache(tmp_path):
    """FundLevelSnapshot must route to write_nav_cache, not write_snapshot.

    This test would have caught the original bug: write_snapshot tries
    `snapshot.as_of_iso` which FundLevelSnapshot does not have, raising
    AttributeError.
    """
    snap = _make_fund_level_snapshot("008986")
    path = _persist_snapshot(snap, tmp_path)
    assert isinstance(path, Path)
    assert path.exists(), f"Expected cache file at {path}"
    assert "nav" in str(path)
    assert "008986" in path.name


def test_persist_snapshot_fund_level_qdii_sentinel_returns_placeholder(tmp_path):
    """QDII sentinel FundLevelSnapshot must return placeholder path (no crash)."""
    snap = _make_fund_level_snapshot("159920", qdii_sentinel=True)
    path = _persist_snapshot(snap, tmp_path)
    assert isinstance(path, Path)
    # sentinel skips actual write — placeholder path should NOT exist on disk
    assert not path.exists()
    assert "qdii_sentinel_skipped" in path.name


def test_persist_snapshot_active_fund_writes_active_cache(tmp_path):
    """ActiveFundSnapshot must route to write_active_fund_cache."""
    snap = _make_active_fund_snapshot("519069")
    path = _persist_snapshot(snap, tmp_path)
    assert isinstance(path, Path)
    assert path.exists(), f"Expected cache file at {path}"
    assert "active_fund" in str(path)
    assert "519069" in path.name


def test_run_monitor_snapshot_fund_level_no_attribute_error(tmp_path, monkeypatch):
    """run_monitor_snapshot must not raise AttributeError when build_snapshot
    returns a FundLevelSnapshot (the bug that was masked by the old monkeypatch)."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    snap = _make_fund_level_snapshot("008986")

    def fake_build_snapshot(target, **kw):
        return snap

    monkeypatch.setattr("irc.commands.monitor_cmd.build_snapshot", fake_build_snapshot)

    rc = run_monitor_snapshot(repo_root=str(tmp_path))
    assert rc == 0
    # Verify a real cache file was written to disk
    written = list((tmp_path / "data" / "fundamentals").rglob("*.json"))
    assert written, "Expected at least one cache file written to data/fundamentals/"
