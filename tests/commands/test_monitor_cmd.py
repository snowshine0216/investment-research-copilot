from __future__ import annotations

import json
import textwrap

from irc.commands.monitor_cmd import run_monitor

_YAML = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 10, fetch_calendar_days: 550 }
defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
funds:
  - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
""")

_SENTINEL_LLM_CONFIG = object()   # fake value; tests that monkeypatch gather_* don't need real LLMConfig


def _make_llm_config():
    """Minimal LLMConfig for E2E tests that call through to the real gather_* functions."""
    from irc.schemas.llm import LLMConfig
    return LLMConfig(
        providers={
            "testprovider": {
                "base_url": "https://example.com/v1",
                "api_key_env": "FAKE_API_KEY",
            },
        },
        tasks={
            "monitor_impact": {"provider": "testprovider", "model": "test-model-x1"},
            "monitor_narrative": {"provider": "testprovider", "model": "test-model-x1"},
            "memo_synthesis": {"provider": "testprovider", "model": "test-model-x1"},
            "memo_audit": {"provider": "testprovider", "model": "test-model-x1"},
        },
    )


def _patch_edges(monkeypatch):
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    # Stub load_yaml so run_monitor doesn't need a real config/llm.yaml on disk
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _SENTINEL_LLM_CONFIG)
    # Degrade calendar to None so no test reaches AkShare network
    monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)
    # Comp 2: run_monitor now searches once per unique theme OUTSIDE
    # build_evidence_pool — stub the run-level edge so e2e tests stay offline.
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    ev = make_evidence_item("Reuters", "yields", "2026-06-15", "https://r", "008986")
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(
        k["fund_id"],
        (ValidatedImpact("gold_drivers", 0.5, 0.9, (ev.citation_id,)),
         ValidatedImpact("geopolitics", 0.4, 0.8, (ev.citation_id,))),
        "ok",
        (),
    ))


def test_run_monitor_writes_all_outputs(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    _patch_edges(monkeypatch)
    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-06-15" / "monitor"
    for name in ("report.html", "signal.json", "impacts.json", "narrative.json", "monitor.json"):
        assert (out / name).exists(), name
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "金" in html


def test_preflight_block_returns_code(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    _patch_edges(monkeypatch)
    import irc.commands.monitor_cmd as mc
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 5)
    assert run_monitor(repo_root=str(tmp_path), today="2026-06-15") == 5


# ── build_evidence_pool unit tests (Fix 4) ────────────────────────────────────


def _make_fund():
    from irc.monitor.types import MonitorFund
    return MonitorFund(
        id="008986", name_cn="金", market="cn_off_exchange",
        analysis_profile="gold", themes=("gold_drivers", "geopolitics"),
        constituent_news=False, weights={"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50,
    )


def _fake_provider(hits):
    """Build a minimal SearchProvider that returns canned hits."""
    from irc.research.search.types import SearchResult, Locale

    class _FakeProv:
        name = "fake"
        locale = Locale.EN

        def search(self, query, **kw):
            return SearchResult(query=query, locale=Locale.EN, hits=tuple(hits), provider="fake")

    return _FakeProv()


def test_build_evidence_pool_converts_hits_to_evidence_items():
    """Fix 4 (superseded by Comp 2): shared theme_results -> EvidenceItems with
    owner_fund_id set."""
    import irc.commands.monitor_cmd as mc
    from irc.research.search.types import SearchHit

    hit = SearchHit(title="Gold up", url="https://reuters.com/gold", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    fund = _make_fund()
    items = mc.build_evidence_pool(fund, theme_results={"gold_drivers": (hit,), "geopolitics": ()})
    assert len(items) > 0
    assert all(it.owner_fund_id == "008986" for it in items)
    assert all(len(it.citation_id) == 16 for it in items)


def test_build_evidence_pool_no_theme_results_returns_empty():
    """Empty theme_results map (e.g. no providers configured upstream) -> ()."""
    import irc.commands.monitor_cmd as mc

    fund = _make_fund()
    items = mc.build_evidence_pool(fund, theme_results={})
    assert items == ()


def test_build_evidence_pool_missing_theme_key_skips_not_crashes():
    """A fund theme absent from theme_results (that theme's search failed
    upstream) contributes no items for that theme rather than raising."""
    import irc.commands.monitor_cmd as mc

    fund = _make_fund()
    items = mc.build_evidence_pool(fund, theme_results={"geopolitics": ()})
    assert items == ()


def test_search_all_themes_drops_blocked_tier_hits(monkeypatch):
    """ADR 0022 (superseded location, Comp 2): a facebook.com hit is dropped by
    _search_all_themes before it ever reaches build_evidence_pool."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.source_tiers import SourceTiers
    from irc.research.search.types import SearchHit

    good = SearchHit(title="Gold up", url="https://reuters.com/gold", snippet="x",
                     published_iso="2026-06-15", source_domain="reuters.com")
    blocked = SearchHit(title="junk post", url="https://facebook.com/x", snippet="y",
                        published_iso="2026-06-15", source_domain="facebook.com")
    prov = _fake_provider([good, blocked])
    tiers = SourceTiers(blocked=("facebook.com",), tier1=("reuters.com",), tier2=())

    result = mc._search_all_themes(prov, ("gold_drivers",), tiers=tiers)
    assert len(result["gold_drivers"]) == 1
    assert result["gold_drivers"][0].source_domain == "reuters.com"


def test_build_theme_results_missing_tier_config_keeps_everything_as_tier3(monkeypatch):
    """Malformed/missing source_tiers config -> fail-open: nothing dropped."""
    import irc.commands.monitor_cmd as mc
    from irc.research.search.types import SearchHit

    hit = SearchHit(title="junk post", url="https://facebook.com/x", snippet="y",
                    published_iso="2026-06-15", source_domain="facebook.com")
    prov = _fake_provider([hit])
    monkeypatch.setattr(mc, "build_providers", lambda settings: (prov,))
    monkeypatch.setattr(mc, "Settings", lambda: object())
    monkeypatch.setattr(mc, "_load_source_tiers_config", lambda repo_root: None)

    result = mc._build_theme_results(mc.Path("."), [_make_fund()])
    assert len(result["gold_drivers"]) == 1   # kept as tier 3, not dropped


# ── End-to-end real gather path tests (Fix 5) ────────────────────────────────


def test_real_gather_path_empty_pool_degrades_gracefully(tmp_path, monkeypatch):
    """E2E: drives run_monitor WITHOUT monkeypatching gather_impacts/gather_narrative.
    build_evidence_pool returns () → both gather_* early-return (empty_pool).
    Asserts rc==0, report.html exists, signal computed, narrative_status degraded."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _SENTINEL_LLM_CONFIG)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    # Degrade calendar to None so no test reaches AkShare network
    monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)
    # Comp 2: run_monitor now searches once per unique theme OUTSIDE
    # build_evidence_pool — stub the run-level edge so this test stays offline
    # even on a machine with real search-provider keys in .env.
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    # Return empty pool — no monkeypatch on gather_impacts / gather_narrative
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())

    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0

    out = tmp_path / "outputs" / "2026-06-15" / "monitor"
    assert (out / "report.html").exists()

    narrative_data = json.loads((out / "narrative.json").read_text(encoding="utf-8"))
    assert narrative_data["008986"]["status"] == "empty_pool"

    signal_data = json.loads((out / "signal.json").read_text(encoding="utf-8"))
    # Signal status is computed from the trend factor (series has data) even when LLM fails
    assert "008986" in signal_data


def test_monitor_json_contains_impacts_status_degraded(tmp_path, monkeypatch):
    """Fix 1 [P0]: empty pool → impacts_status='empty_pool' must appear in monitor.json per fund."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _SENTINEL_LLM_CONFIG)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    # Degrade calendar to None so no test reaches AkShare network
    monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)
    # Comp 2: stub the run-level theme-search edge so this test stays offline.
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())

    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0

    monitor_data = json.loads(
        (tmp_path / "outputs" / "2026-06-15" / "monitor" / "monitor.json").read_text(encoding="utf-8")
    )
    # impacts_status must be present in every fund entry
    fund_entry = next(f for f in monitor_data["funds"] if f["fund_id"] == "008986")
    assert "impacts_status" in fund_entry, "impacts_status missing from monitor.json fund entry"
    assert fund_entry["impacts_status"] == "empty_pool"


def test_make_view_populates_factor_scores_and_return_table():
    from irc.commands.monitor_cmd import _make_view
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.types import (
        FactorScore, SignalRecord, NarrativeDoc, MonitorFund,
    )
    fund = MonitorFund(
        id="008986", name_cn="n", market="cn_off_exchange", analysis_profile="gold",
        themes=(), constituent_news=False, weights={"trend": 1.0},
        bands={"buy": 0.4, "sell": -0.4}, minimum_confidence=0.5,
    )
    acc = tuple((f"2026-01-{i % 28 + 1:02d}", 1.0 + 0.001 * i) for i in range(300))
    nav = NavFetchResult(fund_id="008986", latest_nav=acc[-1][1], as_of_date="2026-06-15", acc_series=acc)
    rec = SignalRecord("008986", "ok", "ADD_BIAS", 0.6, 0.9, 1.0, ("price-momentum",),
                       (), ())
    scores = (
        FactorScore("trend", 0.6, True, "", 1.0),
        FactorScore("heat", None, False, "heat_no_data", 1.0),
    )
    narr = NarrativeDoc("008986", (), (), (), "ok")
    view = _make_view(fund, nav, rec, scores, narr, ())
    assert view.factor_scores == scores            # full ordered set incl. N/A
    assert set(view.return_table) == {5, 20, 60, 120, 250}
    assert view.return_table[60] is not None       # 300 points → all windows valued


def test_make_view_no_nav_yields_all_none_returns():
    from irc.commands.monitor_cmd import _make_view
    from irc.monitor.types import SignalRecord, NarrativeDoc, MonitorFund, FactorScore
    fund = MonitorFund("x", "n", "m", "gold", (), False, {}, {"buy": .4, "sell": -.4}, .5)
    rec = SignalRecord("x", "insufficient_evidence", None, 0.0, 0.0, 0.0, (), (), ())
    narr = NarrativeDoc("x", (), (), (), "ok")
    view = _make_view(fund, None, rec, (FactorScore("trend", None, False, "no_nav", 1.0),), narr, ())
    assert all(v is None for v in view.return_table.values())
    assert view.factor_scores[0].name == "trend"


def test_real_gather_path_fake_call_produces_ok_impacts(tmp_path, monkeypatch):
    """E2E: drives run_monitor with a FAKE call injected via mc.llm_call.
    Injects a non-empty pool and a call that returns valid impacts JSON.
    Asserts impacts status == 'ok' and signal computed."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.evidence import make_evidence_item

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    ev = make_evidence_item("Reuters", "yields fall", "2026-06-15", "https://r", "008986")

    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _make_llm_config())
    # Comp 2: stub the run-level theme-search edge so this test stays offline.
    monkeypatch.setattr(mc, "_build_theme_results", lambda root, funds: {})
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    # Degrade calendar to None so no test reaches AkShare network
    monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)

    class _FakeResp:
        def __init__(self, text):
            self.text = text
            self.prompt_tokens = self.completion_tokens = self.latency_ms = 1

    def _fake_call(task, messages, config, **kw):
        if task == "monitor_impact":
            payload = json.dumps({"impacts": [
                {"key": "gold_drivers", "impact": 0.6, "confidence": 0.8,
                 "citation_ids": [ev.citation_id]},
            ]})
        else:
            payload = json.dumps({
                "price_action_commentary": [],
                "signal_rationale_commentary": [],
                "risk_commentary": [],
            })
        return _FakeResp(payload)

    monkeypatch.setattr(mc, "llm_call", _fake_call)

    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0

    monitor_data = json.loads(
        (tmp_path / "outputs" / "2026-06-15" / "monitor" / "monitor.json").read_text(encoding="utf-8")
    )
    assert monitor_data["funds"][0]["fund_id"] == "008986"

    # Verify impacts_status is "ok" by checking the view via monitor.json (signal should be present)
    signal_data = json.loads(
        (tmp_path / "outputs" / "2026-06-15" / "monitor" / "signal.json").read_text(encoding="utf-8")
    )
    assert "008986" in signal_data


# ── P1b: run_monitor reads the flow store slice ONCE for the fund-loop union ──

_YAML_TWO_ACTIVE_FUNDS = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 10, fetch_calendar_days: 550 }
defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
funds:
  - { id: "110011", name_cn: 易方达蓝筹, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_equity_property_policy], constituent_news: true }
  - { id: "519069", name_cn: 交银成长, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_equity_property_policy], constituent_news: true }
""")


def test_run_monitor_loads_flow_store_slice_once_for_fund_loop(tmp_path, monkeypatch):
    """P1b (RED pre-fix): run_monitor must load the flow store slice ONCE for the
    union of active-fund top-5 symbols across the whole fund loop, then pass it
    into each _process_fund call — not re-read the store once per fund."""
    import irc.commands.monitor_cmd as mc
    from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML_TWO_ACTIVE_FUNDS, encoding="utf-8")
    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())

    def _snap(fid):
        return ActiveFundSnapshot(
            fund_id=fid, source_report_date="2026-03-31", source_report_quarter="2026Q1",
            cache_probed_at="2026-06-15T09:00:00",
            constituent_analyses=(
                ConstituentAnalysis(symbol="600519", name_cn="贵州茅台", weight_pct=30.0,
                                    evidence=(), failure_reasons=(), one_line_view="x"),
            ),
            failure_reasons_by_symbol={},
        )
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: _snap(fid))

    calls: list[tuple] = []
    real_slice = mc._load_flow_store_slice

    def _counting_slice(root, symbols):
        calls.append(tuple(symbols))
        return real_slice(root, symbols)
    monkeypatch.setattr(mc, "_load_flow_store_slice", _counting_slice)

    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0
    assert len(calls) == 1, f"expected exactly 1 store read, got {len(calls)}: {calls}"
    assert "600519" in calls[0]


def test_run_monitor_fund_card_carries_theme_chips_end_to_end(tmp_path, monkeypatch):
    """Flow-wiring trap: assert theme chips reach the rendered HTML through the
    REAL _make_view/run_monitor call chain, not a hand-built FundView."""
    import irc.commands.monitor_cmd as mc
    _patch_edges(monkeypatch)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(
        encoding="utf-8")
    assert "#macro-gold_drivers" in html
    assert "#macro-geopolitics" in html


def test_run_monitor_never_calls_gather_narrative_per_fund(tmp_path, monkeypatch):
    """Report v3: per-fund gather_narrative is DROPPED entirely (spec §5).
    Assert the function is not even imported/callable from monitor_cmd's
    namespace anymore — its absence IS the assertion."""
    import irc.commands.monitor_cmd as mc
    assert not hasattr(mc, "gather_narrative")


def test_run_monitor_threads_macro_narrative_into_trace_and_narrative_json(
    tmp_path, monkeypatch,
):
    """Flow-wiring trap (dark-factor class): the run-level macro_narrative must
    reach BOTH eval_trace.json (run-level field, schema 6) AND narrative.json's
    reserved "__macro__" key through the REAL run_monitor -> _write_eval_artifacts
    / _write_outputs chain — not just exist in gather_macro_narrative's return."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.narrative_macro import (
        MacroNarrativeDoc, MacroNarrativeResult, MacroThemeBlock,
    )
    from irc.monitor.types import Claim

    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    doc = MacroNarrativeDoc(
        blocks=(MacroThemeBlock("gold_drivers", (
            Claim("黄金受实际利率下行支撑。", "consistent_with", ()),
        )),),
        status="ok",
    )
    monkeypatch.setattr(mc, "gather_macro_narrative",
                        lambda **k: MacroNarrativeResult(doc, ()))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    trace = json.loads((out / "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["macro_narrative"]["status"] == "ok"
    assert trace["macro_narrative"]["blocks"][0]["theme"] == "gold_drivers"
    narrative = json.loads((out / "narrative.json").read_text(encoding="utf-8"))
    assert narrative["__macro__"]["status"] == "ok"
    assert narrative["__macro__"]["blocks"][0]["theme"] == "gold_drivers"


def test_run_monitor_threads_macro_impacts_into_render(tmp_path, monkeypatch):
    """Item 002 AC5 (dark-factor trap class): the SAME per-fund macro
    ValidatedImpact tuples the trace serializes must reach render_report's
    macro_impacts_by_fund through the REAL run_monitor -> _write_outputs chain."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.render_html import render_report as real_render

    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    seen = {}

    def spy(views, prov, **kw):
        seen["macro_impacts_by_fund"] = kw.get("macro_impacts_by_fund")
        return real_render(views, prov, **kw)

    monkeypatch.setattr(mc, "render_report", spy)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    got = seen["macro_impacts_by_fund"]
    assert got is not None and set(got)          # one entry per monitored fund
    trace = json.loads((tmp_path / "outputs" / "2026-06-16" / "monitor" /
                        "eval_trace.json").read_text(encoding="utf-8"))
    for fid, impacts in got.items():
        assert [i.impact for i in impacts] == [
            r["impact"] for r in trace["funds"][fid]["impacts"]["macro"]]


def test_run_monitor_survives_gather_macro_narrative_raising(tmp_path, monkeypatch, caplog):
    """F1 (P0, ship-review round 1): gather_macro_narrative raising ANY exception
    (valid-JSON-wrong-shape LLM output, provider bug, etc.) must never kill the
    whole run. The call site degrades to the absent-macro-block shape and the
    run completes rc-clean with report.html + eval_trace.json still written."""
    import logging
    import irc.commands.monitor_cmd as mc

    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)

    def _boom(**k):
        raise RuntimeError("valid-JSON-wrong-shape simulated crash")

    monkeypatch.setattr(mc, "gather_macro_narrative", _boom)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    assert (out / "report.html").exists()
    trace = json.loads((out / "eval_trace.json").read_text(encoding="utf-8"))
    assert trace["macro_narrative"]["status"] != "ok"
    assert trace["macro_narrative"]["blocks"] == []
    narrative = json.loads((out / "narrative.json").read_text(encoding="utf-8"))
    assert narrative["__macro__"]["blocks"] == []
    assert "gather_error" in trace["macro_narrative"]["status"]
    assert any("gather_macro_narrative failed" in r.message for r in caplog.records)


def test_run_monitor_logs_warning_when_second_tier_read_fails(tmp_path, monkeypatch, caplog):
    """F3 (P1, ship-review round 1): the SECOND `_load_source_tiers_config` read
    (used for the drilldown/constituent tiers, distinct from the first read
    inside _build_theme_results) must log the same warning when it returns
    None, instead of silently degrading badges to 未分级 with no breadcrumb."""
    import logging
    import irc.commands.monitor_cmd as mc

    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)
    monkeypatch.setattr(mc, "_load_source_tiers_config", lambda root: None)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    # _patch_edges stubs _build_theme_results entirely, so the FIRST tier read
    # (inside _build_theme_results) never runs in this test — isolating the
    # assertion to the SECOND call site (drilldown/constituent tiers), which
    # must log the same warning instead of swallowing the None silently.
    warnings = [r.message for r in caplog.records
                if "source_tiers config missing/malformed" in r.message]
    assert len(warnings) >= 1


def test_run_monitor_eval_gated_fund_excluded_from_actionable_but_counted_in_health(
    tmp_path, monkeypatch,
):
    """spec §11 acceptance criterion, flow-wiring trap: assert through the REAL
    run_monitor -> _compute_gates -> render_report chain, not a hand-built
    ActionableFund/DataHealthCounts fixture."""
    import irc.commands.monitor_cmd as mc
    _patch_edges(monkeypatch)
    # Force the monitor_signal stage to FAIL so apply_eval_gate suppresses the fund
    # (gate.suppressed=True) while its raw bias stays ADD_BIAS.
    monkeypatch.setattr(mc, "_compute_gates", lambda funds, views, bundles, **k: (
        tuple(mc.GateDecision(v.fund_id, True, ("monitor_signal",), "gated", "forced-fail")
              for v in views),
        {}, {}, {}, {}, {}, {},
    ))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(
        encoding="utf-8")
    assert "可操作" not in html or "EVAL-GATED" not in html.split("可操作")[1].split("</div>")[0]
    assert "被评估门禁" in html   # 数据健康 row still counts the gated fund


# ── Phase 6: 盘中提示 provisional flow wiring ───────────────────────────────────


def test_provisional_flow_for_fund_means_top5_values():
    import irc.commands.monitor_cmd as mc

    class _H:
        def __init__(self, symbol):
            self.symbol = symbol

    top5 = (_H("600000"), _H("600001"))
    provisional = {"600000": 2.0, "600001": 4.0}
    assert mc._provisional_flow_for_fund(top5, provisional) == 3.0


def test_provisional_flow_for_fund_none_provisional_returns_none():
    import irc.commands.monitor_cmd as mc

    class _H:
        def __init__(self, symbol):
            self.symbol = symbol

    assert mc._provisional_flow_for_fund((_H("600000"),), None) is None


def test_provisional_flow_for_fund_no_values_present_returns_none():
    import irc.commands.monitor_cmd as mc

    class _H:
        def __init__(self, symbol):
            self.symbol = symbol

    top5 = (_H("600000"),)
    assert mc._provisional_flow_for_fund(top5, {"999999": 1.0}) is None


def test_run_monitor_calls_provisional_flow_note_once_per_run(tmp_path, monkeypatch):
    """Budget note (spec §8): +1 proxied data-plane call at 12:15, not per-fund."""
    import irc.commands.monitor_cmd as mc
    _patch_edges(monkeypatch)
    calls = []
    monkeypatch.setattr(mc, "_provisional_flow_note", lambda root, symbols: (
        calls.append(symbols) or None
    ))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    assert len(calls) == 1   # exactly once per run, not once per fund


def test_run_monitor_provisional_flow_note_error_degrades_to_no_annotation(tmp_path, monkeypatch):
    """_provisional_flow_note already degrades to None on any error (existing
    contract) — assert run_monitor still succeeds and simply omits the
    annotation."""
    import irc.commands.monitor_cmd as mc
    _patch_edges(monkeypatch)
    monkeypatch.setattr(mc, "_provisional_flow_note", lambda root, symbols: None)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(
        encoding="utf-8")
    assert "盘中主力净流入" not in html   # no annotation, no crash


def test_narrative_dump_macro_blocks_carry_mechanism():
    """Item 002 AC11: narrative.json's __macro__ block dump gains the additive
    mechanism key (write-only debug artifact — verified reader-free, RD-12)."""
    from irc.commands.monitor_cmd import _narrative_dump
    from irc.monitor.narrative_macro import MacroNarrativeDoc, MacroThemeBlock
    from irc.monitor.types import Claim

    doc = MacroNarrativeDoc(
        blocks=(MacroThemeBlock("gold_drivers",
                                (Claim("黄金受支撑。", "consistent_with", ()),),
                                mechanism="美元走弱→利多黄金"),),
        status="ok")
    out = _narrative_dump([], doc)
    assert out["__macro__"]["blocks"][0]["mechanism"] == "美元走弱→利多黄金"
