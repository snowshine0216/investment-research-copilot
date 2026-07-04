"""004 run-level wiring: batch-first 行业 (store → batch → fallback) + board-PE
fetch-first. All network edges monkeypatched — offline only."""
from __future__ import annotations

import json
import logging
import textwrap
from datetime import date

import irc.commands.monitor_cmd as mc
from irc.monitor.board_pe_staleness import BoardPeFreshness
from irc.monitor.fetch import NavFetchResult
from irc.monitor.impacts import ImpactsResult
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.snapshot_cache import write_active_fund_cache
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis

_YAML_TWO_ACTIVE = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 10, fetch_calendar_days: 550 }
defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
funds:
  - { id: "110011", name_cn: 蓝筹A, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary], constituent_news: true }
  - { id: "519069", name_cn: 价值B, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary], constituent_news: true }
""")


class _FakeCon:
    def close(self):
        pass


def _snap(fid, holdings):
    return ActiveFundSnapshot(
        fund_id=fid, source_report_date="2026-03-31", source_report_quarter="2026Q1",
        cache_probed_at="2026-07-03T09:00:00",
        constituent_analyses=tuple(
            ConstituentAnalysis(symbol=s, name_cn=n, weight_pct=w,
                                evidence=(), failure_reasons=(), one_line_view="x")
            for s, n, w in holdings),
        failure_reasons_by_symbol={})


def _wire_two_fund_run(tmp_path, monkeypatch, *, batch_industry):
    """Offline two-active-fund run_monitor harness. A fake DuckDB con + empty
    per-code series map keep _build_full_basket_metrics on the REAL industry
    consume path (con=None would early-return before it)."""
    import irc.opportunity.inputs_loader as il
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML_TWO_ACTIVE, encoding="utf-8")
    write_active_fund_cache(_snap("110011", [("600519", "茅台", 60.0)]), tmp_path / "data")
    write_active_fund_cache(_snap("519069", [("000651", "格力", 55.0)]), tmp_path / "data")
    (tmp_path / "data" / "local.duckdb").write_bytes(b"")   # existence gates connect()
    series = tuple((f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}", 1.0 + 0.01 * i)
                   for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "connect", lambda p: _FakeCon())
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})
    monkeypatch.setattr(mc, "nav_series_for",
                        lambda fid, **k: NavFetchResult(fid, 2.13, "2026-07-03", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: frozenset({date(2026, 7, 2), date(2026, 7, 3)}))
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())
    monkeypatch.setattr(mc, "gather_impacts",
                        lambda **k: ImpactsResult(k["fund_id"], (), "ok", ()))
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(
                            None, False, "valuation_no_anchor", path="lookthrough"))
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    monkeypatch.setattr(mc, "_batch_flow_industry",
                        lambda root, symbols: (None, batch_industry))


# ---- AC-6 consume order (run level) ----


def test_batch_industry_fills_every_row_and_fallback_never_fires(tmp_path, monkeypatch):
    """AC-6 / source-spec §4 bullet 4: batch covers the full basket → 行业 is
    non-None for EVERY holdings row; the per-symbol fetch fake is NEVER invoked."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    fallback_calls = []
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: fallback_calls.append(tuple(symbols)) or {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert fallback_calls == []
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    rows = [r for fid in ("110011", "519069")
            for r in trace["funds"][fid]["holding_metrics"]["rows"]]
    assert rows and all(r["industry"] is not None for r in rows)


def test_symbol_absent_from_batch_falls_back_only_for_it(tmp_path, monkeypatch):
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业"})   # 000651 absent
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    fallback_calls = []
    monkeypatch.setattr(
        mc, "fetch_stock_industry_map",
        lambda symbols, **kw: fallback_calls.append(tuple(symbols))
        or {s: "家电行业" for s in symbols})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert fallback_calls == [("000651",)]      # ONLY the absent symbol reaches fallback


# ---- AC-5: 12:15 batch merge into the cross-day store ----


def test_batch_industry_merges_into_cross_day_store(tmp_path, monkeypatch):
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    store = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                       .read_text(encoding="utf-8"))
    assert store["600519"] == {"industry": "酿酒行业", "seen_at": "2026-07-03"}
    assert store["000651"]["seen_at"] == "2026-07-03"


def test_store_merge_failure_never_crashes_the_brief(tmp_path, monkeypatch, caplog):
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry={"600519": "酿酒行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})

    def _boom(path, today, industry_by_symbol):
        raise OSError("disk full")

    monkeypatch.setattr(mc, "record_seen", _boom)
    with caplog.at_level(logging.WARNING):
        rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert any("industry map store merge failed" in r.message for r in caplog.records)


# ---- AC-6 unit level: _industry_map_for ----


def test_fallback_none_result_writes_nothing_to_store(tmp_path, monkeypatch):
    """RD-4: a TRANSIENT/DEAD fallback ({sym: None}) never poisons the store."""
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: {s: None for s in symbols})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03", serving={})
    assert out == {"600519": None}
    assert not (tmp_path / "data" / "monitor" / "stock_industry_map.json").exists()


def test_fallback_parsed_result_merges_into_store(tmp_path, monkeypatch):
    """Q3: a fallback-served symbol accumulates cross-day (no daily re-fetch)."""
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: {"600519": "酿酒行业"})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03", serving={})
    assert out == {"600519": "酿酒行业"}
    store = json.loads((tmp_path / "data" / "monitor" / "stock_industry_map.json")
                       .read_text(encoding="utf-8"))
    assert store["600519"]["industry"] == "酿酒行业"


def test_serving_map_covers_all_no_fallback_call(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, **kw: called.append(symbols) or {})
    out = mc._industry_map_for(("600519",), root=tmp_path, today="2026-07-03",
                               serving={"600519": "酿酒行业"})
    assert out == {"600519": "酿酒行业"}
    assert called == []


# ---- AC-3: full-basket union helper ----


def test_full_basket_union_dedup_ordered_and_supersets_top5(tmp_path):
    holdings = [(f"60{i:04d}", f"n{i}", 20.0 - i) for i in range(7)]   # 7 > top-5
    write_active_fund_cache(_snap("110011", holdings), tmp_path / "data")

    class _F:
        id = "110011"
        analysis_profile = "active_cn_equity"

    full = mc._full_basket_union_symbols([_F()], tmp_path)
    top5 = mc._capture_union_symbols([_F()], tmp_path)
    assert len(full) == 7
    assert set(top5) <= set(full)                     # top-5 union ⊆ full-basket union
    assert full == tuple(dict.fromkeys(full))         # dedup-ordered


# ---- AC-8: fetch-first order + run-level threading ----


def test_board_pe_fetch_first_before_any_per_symbol_fallback(tmp_path, monkeypatch):
    """AC-8 call-order recorder: the board-PE fetch fires ONCE, at run level,
    BEFORE the first per-symbol fallback, across a 2-active-fund run."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry=None)   # nothing batched
    order = []
    monkeypatch.setattr(
        mc, "fetch_industry_pe",
        lambda **kw: order.append("board_pe")
        or ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(
        mc, "fetch_stock_industry_map",
        lambda symbols, **kw: order.append("fallback") or {s: None for s in symbols})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert order.count("board_pe") == 1              # ONE fetch per run, run-level
    assert order.count("fallback") == 2              # one per active fund
    assert order.index("board_pe") < order.index("fallback")


def test_board_pe_fetch_receives_hoisted_trading_days(tmp_path, monkeypatch):
    """Q10: the hoisted load_trading_days frozenset is threaded to the board-PE
    fetch (and load_trading_days is still called exactly once per run)."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry={"600519": "酿酒行业",
                                                              "000651": "家电行业"})
    tds = frozenset({date(2026, 7, 2), date(2026, 7, 3)})
    calendar_calls = []
    monkeypatch.setattr(mc, "load_trading_days",
                        lambda today, root: calendar_calls.append(1) or tds)
    seen = {}

    def _probe(**kw):
        seen["trading_days"] = kw.get("trading_days")
        return {}, BoardPeFreshness("DARK", None, None)

    monkeypatch.setattr(mc, "fetch_industry_pe", _probe)
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert seen["trading_days"] == tds
    assert len(calendar_calls) == 1                  # hoist is a pure move — one call


def test_trace_carries_run_level_board_pe_freshness(tmp_path, monkeypatch):
    """AC-11 wiring: run_monitor threads the freshness dict into eval_trace.json."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["schema_version"] == "7"            # AC-11: NO second bump
    assert trace["board_pe_freshness"] == {"state": "STALE", "as_of": "2026-07-02",
                                           "age_td": 1}


def test_report_and_drilldown_carry_stale_age_tag_end_to_end(tmp_path, monkeypatch):
    """AC-13 wiring: STALE freshness renders the exact age tag on BOTH surfaces."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-07-03" / "monitor"
    tag = "板块PE 引用 2026-07-02 · 1个交易日前"
    assert tag in (out / "report.html").read_text(encoding="utf-8")
    assert tag in (out / "drilldown.html").read_text(encoding="utf-8")


def test_panel_reason_carries_board_pe_state(tmp_path, monkeypatch):
    """AC-12 wiring: the valuation_coverage panel row surfaces the run-level state."""
    _wire_two_fund_run(tmp_path, monkeypatch,
                       batch_industry={"600519": "酿酒行业", "000651": "家电行业"})
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: ({"酿酒行业": 30.0},
                                      BoardPeFreshness("STALE", "2026-07-02", 1)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-07-03" / "monitor" / "report.html").read_text(
        encoding="utf-8")
    assert "board_pe STALE-1 (as_of 2026-07-02)" in html


def test_no_active_funds_or_no_con_skips_board_pe_fetch(tmp_path, monkeypatch):
    """_wants_board_pe: the run-level fetch is skipped when nothing will consume
    the table (con=None here — no data/local.duckdb) — keeps gold-only/offline
    runs network-free. Round-1 P1 fix: the trace key now names the intentional
    skip explicitly as NOT_REQUESTED rather than collapsing to the same None a
    caller-never-passed-the-field (pre-bump) trace would show."""
    _wire_two_fund_run(tmp_path, monkeypatch, batch_industry=None)
    (tmp_path / "data" / "local.duckdb").unlink()     # con stays None
    called = []
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda **kw: called.append(1)
                        or ({}, BoardPeFreshness("DARK", None, None)))
    monkeypatch.setattr(mc, "fetch_stock_industry_map", lambda symbols, **kw: {})
    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-07-03")
    assert rc == 0
    assert called == []
    trace = json.loads((tmp_path / "outputs" / "2026-07-03" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["board_pe_freshness"] == {
        "state": "NOT_REQUESTED", "as_of": None, "age_td": None}
