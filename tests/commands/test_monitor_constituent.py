"""Tests for monitor constituent factor wiring (v2.0 snapshot-grounded).

Covers:
- load_latest_active_fund_cached (new snapshot_cache helper)
- build_constituent_pool (EDGE helper in monitor_cmd)
- _make_constituent_rows
- _process_fund wires constituent_rows for active_cn_equity profiles
- Empty/missing snapshot → constituent_rows=() without crash
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from irc.fundamentals.snapshot_cache import (
    load_latest_active_fund_cached,
    write_active_fund_cache,
)
from irc.fundamentals.types import (
    ActiveFundSnapshot,
    ConstituentAnalysis,
    ThesisEvidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_evidence(symbol: str, fund_id: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source=symbol, url=f"https://example.com/{symbol}",
        date="2026-03-31", summary=f"{symbol} Q1 summary",
        scope="constituent", citation_kind="data",
        owner_instrument_id=symbol, parent_fund_id=fund_id,
        constituent_key=symbol, holding_weight_pct=5.0,
    )


def _make_holding(symbol: str, name_cn: str, weight_pct: float,
                  fund_id: str, with_evidence: bool = True) -> ConstituentAnalysis:
    ev = (_make_evidence(symbol, fund_id),) if with_evidence else ()
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn, weight_pct=weight_pct,
        evidence=ev, failure_reasons=(),
        one_line_view=f"{symbol} view text",
    )


def _make_active_snapshot(fund_id: str, quarter: str = "2026Q1",
                           holdings: tuple = ()) -> ActiveFundSnapshot:
    if not holdings:
        holdings = (
            _make_holding("300750", "宁德时代", 6.8, fund_id),
            _make_holding("600519", "贵州茅台", 5.2, fund_id),
            _make_holding("000858", "五粮液", 4.1, fund_id),
        )
    return ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2026-03-31",
        source_report_quarter=quarter,
        cache_probed_at="2026-06-15T08:00:00+08:00",
        constituent_analyses=holdings,
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=(),
        fund_level_evidence=(),
    )


# ── load_latest_active_fund_cached ────────────────────────────────────────────


def test_load_latest_active_fund_cached_returns_newest_quarter(tmp_path: Path) -> None:
    """Two quarters exist; must return the later (2026Q1 > 2025Q4)."""
    snap_old = _make_active_snapshot("519069", "2025Q4")
    snap_new = _make_active_snapshot("519069", "2026Q1")
    write_active_fund_cache(snap_old, tmp_path)
    write_active_fund_cache(snap_new, tmp_path)

    loaded = load_latest_active_fund_cached("519069", tmp_path)
    assert loaded is not None
    assert loaded.source_report_quarter == "2026Q1"


def test_load_latest_active_fund_cached_returns_none_when_missing(tmp_path: Path) -> None:
    """No cache on disk → returns None (no crash)."""
    result = load_latest_active_fund_cached("519069", tmp_path)
    assert result is None


def test_load_latest_active_fund_cached_missing_root(tmp_path: Path) -> None:
    """Non-existent root directory → returns None gracefully."""
    result = load_latest_active_fund_cached("519069", tmp_path / "nonexistent")
    assert result is None


# ── build_constituent_pool ────────────────────────────────────────────────────


def test_build_constituent_pool_returns_evidence_items(tmp_path: Path) -> None:
    """Snapshot on disk → pool of EvidenceItems, owner_fund_id set."""
    import irc.commands.monitor_cmd as mc

    snap = _make_active_snapshot("519069")
    write_active_fund_cache(snap, tmp_path / "data")

    items = mc.build_constituent_pool("519069", root=tmp_path)
    assert len(items) > 0
    assert all(it.owner_fund_id == "519069" for it in items)
    assert all(len(it.citation_id) == 16 for it in items)


def test_build_constituent_pool_no_snapshot_returns_empty(tmp_path: Path) -> None:
    """No snapshot → () without crash."""
    import irc.commands.monitor_cmd as mc

    items = mc.build_constituent_pool("519069", root=tmp_path)
    assert items == ()


def test_build_constituent_pool_holding_no_evidence_uses_one_line_view(tmp_path: Path) -> None:
    """Holding with no evidence → synthesize one item from one_line_view."""
    import irc.commands.monitor_cmd as mc

    holding = _make_holding("600519", "贵州茅台", 5.0, "519069", with_evidence=False)
    snap = _make_active_snapshot("519069", holdings=(holding,))
    write_active_fund_cache(snap, tmp_path / "data")

    items = mc.build_constituent_pool("519069", root=tmp_path)
    assert len(items) == 1
    assert "贵州茅台" in items[0].title
    assert items[0].owner_fund_id == "519069"


def test_build_constituent_pool_top5_only(tmp_path: Path) -> None:
    """More than 5 holdings → only top 5 by weight_pct contribute to the pool."""
    import irc.commands.monitor_cmd as mc

    # 8 holdings with descending weights
    holdings = tuple(
        _make_holding(f"00{i:04d}", f"股票{i}", float(10 - i), "519069")
        for i in range(8)
    )
    snap = _make_active_snapshot("519069", holdings=holdings)
    write_active_fund_cache(snap, tmp_path / "data")

    items = mc.build_constituent_pool("519069", root=tmp_path)
    # each holding has 1 evidence item → top 5 → max 5 items
    assert 1 <= len(items) <= 5


def test_build_constituent_pool_exception_returns_empty(tmp_path: Path, monkeypatch) -> None:
    """Any exception inside → () without crash."""
    import irc.commands.monitor_cmd as mc

    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk error")))
    items = mc.build_constituent_pool("519069", root=tmp_path)
    assert items == ()


# ── _make_constituent_rows ────────────────────────────────────────────────────


def test_make_constituent_rows_maps_symbols_to_weights() -> None:
    """Impact rows keyed by symbol → ImpactRow with holding weight_pct."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact

    holdings = (
        _make_holding("300750", "宁德时代", 6.8, "519069"),
        _make_holding("600519", "贵州茅台", 5.2, "519069"),
    )
    impacts = ImpactsResult(
        fund_id="519069",
        impacts=(
            ValidatedImpact("300750", 0.5, 0.9, ()),
            ValidatedImpact("600519", -0.2, 0.7, ()),
        ),
        status="ok",
        cost_entries=(),
    )
    rows = mc._make_constituent_rows(impacts, holdings)
    assert len(rows) == 2
    by_key = {r.key: r for r in rows}
    assert by_key["300750"].weight == pytest.approx(6.8)
    assert by_key["600519"].weight == pytest.approx(5.2)
    assert by_key["300750"].impact == pytest.approx(0.5)


def test_make_constituent_rows_skips_unknown_symbols() -> None:
    """Impact for symbol not in top holdings → ignored."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact

    holdings = (_make_holding("300750", "宁德时代", 6.8, "519069"),)
    impacts = ImpactsResult(
        fund_id="519069",
        impacts=(
            ValidatedImpact("300750", 0.5, 0.9, ()),
            ValidatedImpact("999999", 0.8, 0.8, ()),   # not in holdings
        ),
        status="ok",
        cost_entries=(),
    )
    rows = mc._make_constituent_rows(impacts, holdings)
    assert len(rows) == 1
    assert rows[0].key == "300750"


# ── _process_fund constituent wiring ─────────────────────────────────────────


def _make_active_fund():
    from irc.monitor.types import MonitorFund
    return MonitorFund(
        id="519069", name_cn="汇添富价值精选", market="cn_off_exchange",
        analysis_profile="active_cn_equity",
        themes=("cn_monetary", "cn_equity_property_policy"),
        constituent_news=True,
        weights={"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                 "macro_tilt": 0.20, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40},
        minimum_confidence=0.50,
    )


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompt_tokens = self.completion_tokens = self.latency_ms = 1


def _fake_impacts_call(task, messages, config, **kw):
    """Return valid impacts JSON for any LLM task."""
    # Extract themes from the message user content and return one impact per theme
    user_msg = messages[1]["content"] if len(messages) > 1 else ""
    # Identify symbol-like keys from the themes line
    import re
    themes_match = re.search(r"Themes: ([^\n]+)", user_msg)
    themes = []
    if themes_match:
        themes = [t.strip() for t in themes_match.group(1).split(",")]
    impacts = [
        {"key": t, "impact": 0.4, "confidence": 0.8, "citation_ids": []}
        for t in themes[:2]
    ]
    if task == "monitor_narrative":
        payload = json.dumps({
            "price_action_commentary": [],
            "signal_rationale_commentary": [],
            "risk_commentary": [],
        })
    else:
        payload = json.dumps({"impacts": impacts})
    return _FakeResp(payload)


def _patch_process_fund_edges(monkeypatch, fund_id: str, series_len: int = 300):
    """Monkeypatch all I/O in _process_fund except build_constituent_pool."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.narrative import NarrativeResult
    from irc.monitor.types import NarrativeDoc

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(series_len))
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.0, "2026-06-15", series))
    ev = make_evidence_item("src", "title", "2026-06-15", "https://x", fund_id)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    # gather_impacts returns two macro theme impacts for the main pool;
    # build_constituent_pool runs real disk I/O, gather_impacts for const_pool is also real.
    monkeypatch.setattr(mc, "gather_narrative", lambda **k: NarrativeResult(
        NarrativeDoc(k["fund_id"], (), (), (), "ok"), (),
    ))


def _stub_gather_impacts_for_macro_only(monkeypatch, fund_id: str, themes: tuple):
    """Stub gather_impacts to return ok impacts for macro themes only (not symbols)."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact

    call_count = [0]

    def _fake_gather(**k):
        call_count[0] += 1
        impacts = tuple(
            ValidatedImpact(theme, 0.4, 0.8, ())
            for theme in k["themes"][:2]
        )
        return ImpactsResult(k["fund_id"], impacts, "ok", ())

    monkeypatch.setattr(mc, "gather_impacts", _fake_gather)
    return call_count


def test_process_fund_active_cn_equity_gets_constituent_rows(tmp_path, monkeypatch) -> None:
    """_process_fund for active_cn_equity wires constituent_rows from snapshot."""
    import irc.commands.monitor_cmd as mc

    # Write a real snapshot to disk
    snap = _make_active_snapshot("519069")
    write_active_fund_cache(snap, tmp_path / "data")

    _patch_process_fund_edges(monkeypatch, "519069")
    _stub_gather_impacts_for_macro_only(monkeypatch, "519069", ("cn_monetary", "cn_equity_property_policy"))

    captured_inputs = {}
    _real_build_factor_scores = mc.build_factor_scores

    def _spy(profile, inp):
        captured_inputs["inp"] = inp
        return _real_build_factor_scores(profile, inp)

    monkeypatch.setattr(mc, "build_factor_scores", _spy)

    class _MinCfg:
        class history:
            minimum_observations = 10

    fund = _make_active_fund()
    _sentinel_cfg = object()
    view, costs = mc._process_fund(fund, _MinCfg(), tmp_path, _sentinel_cfg)

    assert "inp" in captured_inputs, "_spy never fired"
    assert len(captured_inputs["inp"].constituent_rows) > 0, (
        "constituent_rows must be non-empty for active_cn_equity with snapshot on disk"
    )


def test_process_fund_gold_profile_leaves_constituent_rows_empty(tmp_path, monkeypatch) -> None:
    """Gold profile → constituent_rows=() (no active_fund lookthrough)."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.types import MonitorFund

    _patch_process_fund_edges(monkeypatch, "008986", series_len=60)
    _stub_gather_impacts_for_macro_only(monkeypatch, "008986", ("gold_drivers", "geopolitics"))

    captured_inputs = {}
    _real_build_factor_scores = mc.build_factor_scores

    def _spy(profile, inp):
        captured_inputs["inp"] = inp
        return _real_build_factor_scores(profile, inp)

    monkeypatch.setattr(mc, "build_factor_scores", _spy)

    gold_fund = MonitorFund(
        id="008986", name_cn="广发上海金ETF联接A", market="cn_off_exchange",
        analysis_profile="gold", themes=("gold_drivers", "geopolitics"),
        constituent_news=False,
        weights={"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50,
    )

    class _MinCfg:
        class history:
            minimum_observations = 10

    mc._process_fund(gold_fund, _MinCfg(), tmp_path, object())
    assert captured_inputs["inp"].constituent_rows == ()


def test_process_fund_active_no_snapshot_constituent_rows_empty(tmp_path, monkeypatch) -> None:
    """active_cn_equity but no snapshot on disk → constituent_rows=() gracefully."""
    import irc.commands.monitor_cmd as mc

    # No snapshot written to tmp_path

    _patch_process_fund_edges(monkeypatch, "519069", series_len=60)
    _stub_gather_impacts_for_macro_only(monkeypatch, "519069", ("cn_monetary", "cn_equity_property_policy"))

    captured_inputs = {}
    _real_build_factor_scores = mc.build_factor_scores

    def _spy(profile, inp):
        captured_inputs["inp"] = inp
        return _real_build_factor_scores(profile, inp)

    monkeypatch.setattr(mc, "build_factor_scores", _spy)

    class _MinCfg:
        class history:
            minimum_observations = 10

    fund = _make_active_fund()
    view, costs = mc._process_fund(fund, _MinCfg(), tmp_path, object())
    assert captured_inputs["inp"].constituent_rows == ()
