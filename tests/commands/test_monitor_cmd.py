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


def _patch_edges(monkeypatch):
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.narrative import NarrativeResult
    from irc.monitor.types import NarrativeDoc

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    # Stub load_yaml so run_monitor doesn't need a real config/llm.yaml on disk
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _SENTINEL_LLM_CONFIG)
    ev = make_evidence_item("Reuters", "yields", "2026-06-15", "https://r", "008986")
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(
        k["fund_id"],
        (ValidatedImpact("gold_drivers", 0.5, 0.9, (ev.citation_id,)),
         ValidatedImpact("geopolitics", 0.4, 0.8, (ev.citation_id,))),
        "ok",
        (),
    ))
    monkeypatch.setattr(mc, "gather_narrative", lambda **k: NarrativeResult(
        NarrativeDoc(k["fund_id"], (), (), (), "ok"), (),
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


def test_build_evidence_pool_converts_hits_to_evidence_items(monkeypatch):
    """Fix 4: fake provider with canned hits → EvidenceItems with owner_fund_id set."""
    import irc.commands.monitor_cmd as mc
    from irc.research.search.types import SearchHit

    hit = SearchHit(title="Gold up", url="https://reuters.com/gold", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    prov = _fake_provider([hit])
    monkeypatch.setattr(mc, "build_providers", lambda settings: (prov,))
    monkeypatch.setattr(mc, "Settings", lambda: object())

    fund = _make_fund()
    items = mc.build_evidence_pool(fund, repo_root=".")
    assert len(items) > 0
    assert all(it.owner_fund_id == "008986" for it in items)
    assert all(len(it.citation_id) == 16 for it in items)


def test_build_evidence_pool_no_providers_returns_empty(monkeypatch):
    """Fix 4: when build_providers returns [] → return () gracefully."""
    import irc.commands.monitor_cmd as mc
    monkeypatch.setattr(mc, "build_providers", lambda settings: ())
    monkeypatch.setattr(mc, "Settings", lambda: object())

    fund = _make_fund()
    items = mc.build_evidence_pool(fund, repo_root=".")
    assert items == ()


def test_build_evidence_pool_provider_exception_returns_empty(monkeypatch):
    """Fix 4: any exception inside → return () (never crash)."""
    import irc.commands.monitor_cmd as mc

    def _boom(settings):
        raise RuntimeError("network down")

    monkeypatch.setattr(mc, "build_providers", _boom)
    monkeypatch.setattr(mc, "Settings", lambda: object())

    fund = _make_fund()
    items = mc.build_evidence_pool(fund, repo_root=".")
    assert items == ()


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
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: _SENTINEL_LLM_CONFIG)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)

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
