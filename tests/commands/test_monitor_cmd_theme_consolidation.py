from __future__ import annotations


def _fake_provider_counting(hits_by_query: dict):
    from irc.research.search.types import SearchResult, Locale

    calls: list[str] = []

    class _FakeProv:
        name = "fake"
        locale = Locale.EN

        def search(self, query, **kw):
            calls.append(query)
            hits = hits_by_query.get(query, [])
            return SearchResult(query=query, locale=Locale.EN, hits=tuple(hits), provider="fake")

    prov = _FakeProv()
    return prov, calls


def test_search_all_themes_calls_provider_once_per_unique_theme():
    import irc.commands.monitor_cmd as mc
    from irc.monitor.source_tiers import SourceTiers
    from irc.research.search.types import SearchHit
    from irc.monitor.profiles import theme_query_seed

    themes = ("gold_drivers", "geopolitics", "cn_monetary")
    queries = {theme_query_seed(t): [SearchHit(title=f"t-{t}", url=f"https://reuters.com/{t}",
                                                snippet="x", published_iso="2026-07-01",
                                                source_domain="reuters.com")]
               for t in themes}
    prov, calls = _fake_provider_counting(queries)
    tiers = SourceTiers(blocked=(), tier1=("reuters.com",), tier2=())

    result = mc._search_all_themes(prov, themes, tiers=tiers)

    assert len(calls) == 3   # exactly once per theme, not per fund
    assert set(result.keys()) == set(themes)
    assert len(result["gold_drivers"]) == 1


def test_search_all_themes_drops_blocked_hits():
    import irc.commands.monitor_cmd as mc
    from irc.monitor.source_tiers import SourceTiers
    from irc.research.search.types import SearchHit
    from irc.monitor.profiles import theme_query_seed

    theme = "geopolitics"
    query = theme_query_seed(theme)
    hits = [
        SearchHit(title="good", url="https://reuters.com/a", snippet="x",
                  published_iso="2026-07-01", source_domain="reuters.com"),
        SearchHit(title="junk", url="https://facebook.com/b", snippet="y",
                  published_iso="2026-07-01", source_domain="facebook.com"),
    ]
    prov, _ = _fake_provider_counting({query: hits})
    tiers = SourceTiers(blocked=("facebook.com",), tier1=("reuters.com",), tier2=())

    result = mc._search_all_themes(prov, (theme,), tiers=tiers)

    assert len(result[theme]) == 1
    assert result[theme][0].source_domain == "reuters.com"


def test_search_all_themes_failed_theme_maps_to_empty_tuple():
    import irc.commands.monitor_cmd as mc
    from irc.monitor.source_tiers import SourceTiers
    from irc.research.search.types import SearchResult, Locale

    class _FailProv:
        name = "fake"
        locale = Locale.EN

        def search(self, query, **kw):
            return SearchResult(query=query, locale=Locale.EN, hits=(), provider="fake",
                                failure_reason="timeout")

    result = mc._search_all_themes(_FailProv(), ("gold_drivers",),
                                   tiers=SourceTiers((), (), ()))
    assert result["gold_drivers"] == ()


def test_build_evidence_pool_from_shared_theme_results_owner_binds_per_fund():
    import irc.commands.monitor_cmd as mc
    from irc.research.search.types import SearchHit
    from irc.monitor.types import MonitorFund

    hit = SearchHit(title="Gold up", url="https://reuters.com/gold", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    theme_results = {"gold_drivers": (hit,), "geopolitics": ()}
    fund = MonitorFund(
        id="008986", name_cn="金", market="cn_off_exchange", analysis_profile="gold",
        themes=("gold_drivers", "geopolitics"), constituent_news=False,
        weights={"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50,
    )

    items = mc.build_evidence_pool(fund, theme_results=theme_results)

    assert len(items) == 1
    assert items[0].owner_fund_id == "008986"
    assert len(items[0].citation_id) == 16


def test_build_evidence_pool_two_funds_same_hit_share_url_but_differ_by_owner():
    """Same (url,date) hit shared by two funds' theme -> different cids (owner-bound)
    but identical (url,date) -> exact citation dedup possible downstream (Phase 4)."""
    import irc.commands.monitor_cmd as mc
    from irc.research.search.types import SearchHit
    from irc.monitor.types import MonitorFund

    hit = SearchHit(title="Fed holds rates", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    theme_results = {"us_monetary": (hit,)}
    fund_a = MonitorFund(
        id="270023", name_cn="A", market="cn_off_exchange", analysis_profile="qdii_global",
        themes=("us_monetary",), constituent_news=True,
        weights={"trend": 0.35, "macro_tilt": 0.35, "heat": 0.15, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50,
    )
    fund_b = MonitorFund(
        id="009225", name_cn="B", market="cn_off_exchange",
        analysis_profile="qdii_china_us_internet", themes=("us_monetary",),
        constituent_news=True,
        weights={"trend": 0.30, "valuation": 0.20, "heat": 0.15, "macro_tilt": 0.20,
                 "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50,
    )

    items_a = mc.build_evidence_pool(fund_a, theme_results=theme_results)
    items_b = mc.build_evidence_pool(fund_b, theme_results=theme_results)

    assert items_a[0].citation_id != items_b[0].citation_id   # owner-bound, ADR 0017
    assert items_a[0].url == items_b[0].url == "https://reuters.com/fed"
    assert items_a[0].date == items_b[0].date == "2026-06-15"


def test_run_monitor_searches_each_theme_exactly_once_across_whole_fund_set(
    tmp_path, monkeypatch,
):
    """End-to-end (Comp 2 flow-wiring trap): drive run_monitor with 3 funds sharing
    overlapping themes; assert the provider is called exactly once per UNIQUE theme,
    not once per fund. This is the wiring-assertion test — it goes through the real
    _build_theme_results/build_evidence_pool call chain, not a hand-built dict."""
    import textwrap
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.narrative import NarrativeResult
    from irc.monitor.types import NarrativeDoc
    from irc.research.search.types import SearchResult, Locale

    yaml_cfg = textwrap.dedent("""
    schema_version: 1
    history: { minimum_observations: 10, fetch_calendar_days: 550 }
    defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
    funds:
      - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
      - { id: "270023", name_cn: Q1, market: cn_off_exchange, analysis_profile: qdii_global, themes: [geopolitics, us_monetary], constituent_news: false }
      - { id: "009225", name_cn: Q2, market: cn_off_exchange, analysis_profile: qdii_china_us_internet, themes: [us_monetary], constituent_news: false }
    """)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(yaml_cfg, encoding="utf-8")

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(15))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    monkeypatch.setattr(mc, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(mc, "load_trading_days", lambda today, root: None)
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(k["fund_id"], (), "empty_pool", ()))
    # raising=False: Phase 3 REMOVES gather_narrative from monitor_cmd's namespace
    # (Step 3.23). With raising=False this monkeypatch stays valid both before the
    # removal (intercepts the real per-fund call) and after it (sets an inert,
    # teardown-removed attribute) — so this Phase-2 test survives Phase 3 unchanged.
    monkeypatch.setattr(mc, "gather_narrative", lambda **k: NarrativeResult(
        NarrativeDoc(k["fund_id"], (), (), (), "empty_pool"), ()), raising=False)
    monkeypatch.setattr(mc, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(mc, "record_command_run", lambda **k: None)

    calls: list[str] = []

    class _CountingProv:
        name = "fake"
        locale = Locale.EN

        def search(self, query, **kw):
            calls.append(query)
            return SearchResult(query=query, locale=Locale.EN, hits=(), provider="fake")

    monkeypatch.setattr(mc, "build_providers", lambda settings: (_CountingProv(),))
    monkeypatch.setattr(mc, "Settings", lambda: object())

    rc = mc.run_monitor(repo_root=str(tmp_path), today="2026-06-16")

    assert rc == 0
    # 3 unique themes across the 3 funds (gold_drivers, geopolitics, us_monetary)
    # despite geopolitics/us_monetary each being used by 2 funds -> 3 calls, not 4.
    assert len(calls) == 3
