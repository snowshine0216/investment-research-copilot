from __future__ import annotations

from pathlib import Path

import pytest

from irc.fundamentals.snapshot_cache import (
    active_fund_cache_path,
    load_active_fund_cache,
    nav_cache_path,
    load_nav_cache,
    write_active_fund_cache,
    write_nav_cache,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    FundAnnouncement,
    FundLevelSnapshot,
    FundNavReport,
    ThesisEvidence,
)
from irc.opportunity.types import ConstituentAnalysis


def _make_snapshot(quarter: str = "2024Q1") -> ActiveFundSnapshot:
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2024-04-15", summary="贵州茅台 24Q1",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=(ev,), failure_reasons=(), one_line_view="x",
    )
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="2024-03-31",
        source_report_quarter=quarter, cache_probed_at="",
        constituent_analyses=(c,),
        failure_reasons_by_symbol={"600519": ()},
    )


def test_active_fund_cache_path_uses_quarter(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    assert path == tmp_path / "fundamentals" / "2024Q1" / "active_fund" / "fund_005827.json"


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    snap = _make_snapshot()
    written = write_active_fund_cache(snap, tmp_path)
    assert written.exists()
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded is not None
    assert loaded.fund_id == "005827"
    assert loaded.source_report_quarter == "2024Q1"
    assert loaded.constituent_analyses[0].symbol == "600519"
    assert loaded.constituent_analyses[0].evidence[0].citation_id != ""


def test_load_active_fund_cache_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_load_active_fund_cache_returns_none_on_malformed(tmp_path: Path) -> None:
    path = active_fund_cache_path("005827", "2024Q1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json}", encoding="utf-8")
    assert load_active_fund_cache("005827", "2024Q1", tmp_path) is None


def test_write_then_reload_preserves_holding_weight_pct(tmp_path: Path) -> None:
    snap = _make_snapshot()
    write_active_fund_cache(snap, tmp_path)
    loaded = load_active_fund_cache("005827", "2024Q1", tmp_path)
    assert loaded.constituent_analyses[0].evidence[0].holding_weight_pct == 6.2


# ── Task 7: NAV cache I/O tests ───────────────────────────────────────────────


def _make_snap(tmp_id: str = "518880") -> FundLevelSnapshot:
    nav = FundNavReport(
        fund_id=tmp_id,
        fund_name=tmp_id,
        latest_nav=4.5678,
        latest_nav_date="2026-03-15",
        nav_history=(
            ("2026-03-14", 4.5500),
            ("2026-03-15", 4.5678),
        ),
        source_report_quarter="2026Q1",
    )
    ann = FundAnnouncement(
        fund_id=tmp_id,
        title="x",
        topic="dividend",
        date="2024-01-01",
        report_id="AN1",
    )
    ev = ThesisEvidence(
        type="snapshot", source=tmp_id, url="",
        date="2026-03-15",
        summary="NAV=4.5678 @ 2026-03-15",
        scope="instrument", citation_kind="data",
        owner_instrument_id=tmp_id,
        parent_fund_id=None, constituent_key=None,
    )
    return FundLevelSnapshot(
        fund_id=tmp_id,
        nav_report=nav,
        announcements=(ann,),
        evidence=(ev,),
        source_report_quarter="2026Q1",
        cache_probed_at="2026-05-23",
    )


def test_nav_cache_path_layout(tmp_path: Path) -> None:
    p = nav_cache_path("518880", "2026Q1", tmp_path)
    assert p == tmp_path / "fundamentals" / "2026Q1" / "nav" / "fund_518880.json"


def test_write_and_load_nav_cache_roundtrip(tmp_path: Path) -> None:
    snap = _make_snap()
    written = write_nav_cache(snap, tmp_path)
    assert written.exists()
    loaded = load_nav_cache("518880", "2026Q1", tmp_path)
    assert loaded is not None
    assert loaded.fund_id == "518880"
    assert loaded.nav_report is not None
    assert loaded.nav_report.latest_nav == 4.5678
    assert loaded.announcements[0].report_id == "AN1"
    assert loaded.evidence[0].citation_kind == "data"
    # citation_id is content-addressed → recomputed on load — assert equality.
    assert loaded.evidence[0].citation_id == snap.evidence[0].citation_id


def test_load_nav_cache_missing_returns_none(tmp_path: Path) -> None:
    assert load_nav_cache("518880", "2026Q1", tmp_path) is None


def test_load_nav_cache_malformed_json_returns_none(tmp_path: Path) -> None:
    p = nav_cache_path("518880", "2026Q1", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json{", encoding="utf-8")
    assert load_nav_cache("518880", "2026Q1", tmp_path) is None


def test_write_nav_cache_atomic_tmp_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The .tmp.{pid} → os.replace pattern leaves no .tmp file behind."""
    snap = _make_snap()
    written = write_nav_cache(snap, tmp_path)
    leftover = list(written.parent.glob("*.tmp.*"))
    assert leftover == []
    assert written.exists()


def test_write_nav_cache_skips_qdii_sentinel(tmp_path: Path) -> None:
    """Per grill Q5: QDII sentinel (evidence_gaps == qdii_information_unavailable)
    is NOT serialized to disk."""
    sentinel = FundLevelSnapshot(
        fund_id="513500",
        nav_report=None,
        announcements=(),
        evidence=(),
        source_report_quarter="",
        cache_probed_at="",
        evidence_gaps=("qdii_information_unavailable",),
    )
    write_nav_cache(sentinel, tmp_path)
    # Sentinel writers return a sentinel path (or None) — the file MUST NOT exist.
    assert not (tmp_path / "fundamentals").exists() or not any(
        (tmp_path / "fundamentals").rglob("fund_513500.json")
    )
