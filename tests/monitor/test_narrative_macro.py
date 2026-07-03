from __future__ import annotations
import pytest
from irc.monitor.narrative_macro import theme_display_name, THEME_DISPLAY_NAME


def test_theme_display_name_known_theme():
    assert theme_display_name("cn_monetary") == "中国货币政策"
    assert theme_display_name("geopolitics") == "地缘政治"
    assert theme_display_name("gold_drivers") == "黄金驱动"


def test_theme_display_name_unknown_theme_returns_raw_key():
    assert theme_display_name("some_future_theme") == "some_future_theme"


def test_all_config_themes_have_a_display_name():
    """The 8 themes seeded in config/monitor.yaml (see profiles.py THEME_SEEDS)
    must all resolve to a real Chinese label, not a raw-key fallback."""
    from irc.monitor.profiles import THEME_SEEDS
    for theme in THEME_SEEDS:
        assert theme in THEME_DISPLAY_NAME, f"{theme} missing from THEME_DISPLAY_NAME"


def test_build_macro_pool_owner_binds_to_theme_synthetic_owner():
    from irc.monitor.narrative_macro import build_macro_pool
    from irc.research.search.types import SearchHit

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    assert "us_monetary" in pool
    assert len(pool["us_monetary"]) == 1
    item = pool["us_monetary"][0]
    assert item.owner_fund_id == "theme:us_monetary"
    assert len(item.citation_id) == 16


def test_build_macro_pool_omits_empty_evidence_themes():
    from irc.monitor.narrative_macro import build_macro_pool

    pool = build_macro_pool({"us_monetary": (), "geopolitics": ()})
    assert pool == {}


def test_build_macro_pool_caps_items_per_theme():
    from irc.monitor.narrative_macro import build_macro_pool, _MAX_ITEMS_PER_THEME
    from irc.research.search.types import SearchHit

    hits = tuple(
        SearchHit(title=f"item{i}", url=f"https://reuters.com/{i}", snippet="x",
                  published_iso=f"2026-06-{i+1:02d}", source_domain="reuters.com")
        for i in range(15)
    )
    pool = build_macro_pool({"geopolitics": hits})
    assert len(pool["geopolitics"]) == _MAX_ITEMS_PER_THEME


def test_build_macro_pool_two_themes_independent_synthetic_owners():
    from irc.monitor.narrative_macro import build_macro_pool
    from irc.research.search.types import SearchHit

    hit_a = SearchHit(title="a", url="https://reuters.com/a", snippet="x",
                      published_iso="2026-06-15", source_domain="reuters.com")
    hit_b = SearchHit(title="b", url="https://reuters.com/b", snippet="x",
                      published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit_a,), "geopolitics": (hit_b,)})
    assert pool["us_monetary"][0].owner_fund_id == "theme:us_monetary"
    assert pool["geopolitics"][0].owner_fund_id == "theme:geopolitics"


def test_cjk_ratio_pure_chinese_passes():
    from irc.monitor.narrative_macro import _passes_language_guard
    assert _passes_language_guard("央行本周维持利率不变，符合市场预期。") is True


def test_cjk_ratio_pure_english_fails():
    from irc.monitor.narrative_macro import _passes_language_guard
    assert _passes_language_guard("The Fed held rates steady this week as expected.") is False


def test_cjk_ratio_tolerates_tickers_and_numbers():
    from irc.monitor.narrative_macro import _passes_language_guard
    # mostly Chinese with an embedded ticker/number/latin brand name
    assert _passes_language_guard("受Fed议息影响，SPX500下跌1.2%，市场情绪偏谨慎。") is True


def test_cjk_ratio_boundary_at_30_percent():
    from irc.monitor.narrative_macro import _cjk_ratio
    # 3 CJK chars out of 10 non-whitespace chars = 0.30 exactly -> boundary
    text = "中文中abcdefg"   # 3 CJK + 7 latin = 10 non-whitespace chars
    assert abs(_cjk_ratio(text) - 0.30) < 1e-9


def test_cjk_ratio_empty_text_is_zero():
    from irc.monitor.narrative_macro import _cjk_ratio
    assert _cjk_ratio("") == 0.0
    assert _cjk_ratio("   ") == 0.0


def _fake_resp(text: str, prompt_tokens=10, completion_tokens=10):
    class _R:
        pass
    r = _R()
    r.text = text
    r.prompt_tokens = prompt_tokens
    r.completion_tokens = completion_tokens
    r.latency_ms = 5
    return r


def test_gather_macro_narrative_empty_pool_no_llm_call():
    from irc.monitor.narrative_macro import gather_macro_narrative

    def _call(*a, **k):
        raise AssertionError("must not be called on empty pool")

    result = gather_macro_narrative(theme_pool={}, route=object(), call=_call)
    assert result.doc.status == "empty_pool"
    assert result.doc.blocks == ()
    assert result.cost_entries == ()


def test_gather_macro_narrative_parses_claims_per_theme(monkeypatch):
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    body = {
        "us_monetary": [
            {"claim": "美联储本周维持利率不变。", "attribution_strength": "consistent_with",
             "citation_ids": [cid]},
        ],
    }

    def _call(task, messages, route, **kw):
        import json as _json
        return _fake_resp(_json.dumps(body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.status == "ok"
    assert len(result.doc.blocks) == 1
    assert result.doc.blocks[0].theme == "us_monetary"
    assert len(result.doc.blocks[0].claims) == 1
    assert len(result.cost_entries) == 1


def test_gather_macro_narrative_caps_at_3_claims_per_theme(monkeypatch):
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    body = {"us_monetary": [
        {"claim": f"中文声明第{i}条，关于美联储政策的评论。",
         "attribution_strength": "consistent_with", "citation_ids": [cid]}
        for i in range(5)   # 5 claims offered, must cap at 3
    ]}

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps(body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert len(result.doc.blocks[0].claims) == 3


def test_gather_macro_narrative_banned_verb_without_supported_attribution_rejected(monkeypatch):
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    bad_body = {"us_monetary": [
        {"claim": "加息导致市场下跌是主因。", "attribution_strength": "possible_driver",
         "citation_ids": [cid]},
    ]}
    good_body = {"us_monetary": []}

    calls = {"n": 0}

    def _call(task, messages, route, **kw):
        calls["n"] += 1
        body = bad_body if calls["n"] == 1 else good_body
        return _fake_resp(_json.dumps(body))

    gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    # banned verb without supported_attribution -> schema-retry, eventually degrades
    # for that call attempt; after MAX_SCHEMA_RETRIES the last successful parse (empty) wins
    assert calls["n"] >= 2


def test_gather_macro_narrative_persistent_english_drops_theme(monkeypatch):
    """CJK guard: a theme whose claims persistently fail the language guard is
    DROPPED from the doc (absent > English) rather than rendered in English."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    english_body = {"us_monetary": [
        {"claim": "The Fed held rates steady this week.",
         "attribution_strength": "consistent_with", "citation_ids": [cid]},
    ]}

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps(english_body))   # persistently English

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.blocks == ()   # theme dropped, not rendered in English


# ── F1: shape-validate decoded payload before claim parsing (ship-review round 1) ──


def test_parse_theme_claims_rejects_string_rows_not_a_list():
    """Exact repro from the ship-blocked finding: theme value is a bare string
    (not a list of row dicts). Must raise _MacroNarrErr, never AttributeError
    from char-iterating the string as if it were a list of row dicts."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    with pytest.raises(_MacroNarrErr):
        _parse_theme_claims("brief note", (), hardened=False)


def test_parse_theme_claims_rejects_non_dict_row():
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    with pytest.raises(_MacroNarrErr):
        _parse_theme_claims(["not a dict"], (), hardened=False)


def test_gather_macro_narrative_top_level_not_dict_degrades_not_crashes(monkeypatch):
    """Top-level decoded payload is not a dict (e.g. a JSON list) -> must
    degrade via the existing retry/drop path, never raise out of
    gather_macro_narrative."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps(["not", "a", "dict"]))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.blocks == ()
    assert result.doc.status != "ok"


def test_gather_macro_narrative_theme_value_string_degrades_not_crashes(monkeypatch):
    """Exact repro shape from the ship-blocked finding threaded through the
    full gather_macro_narrative call, not just the pure parse helper."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"cn_monetary": (hit,)})

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps({"cn_monetary": "brief note"}))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.blocks == ()
    assert result.doc.status != "ok"


# ── F2: citation_ids typing (ship-review round 1) ──────────────────────────────


def test_parse_theme_claims_rejects_bare_string_citation_ids():
    """citation_ids as a bare string must be type-rejected with a distinct
    reason BEFORE any char-iteration reaches resolve_in_pool — never produce
    1-char garbage cids."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行维持利率不变，符合预期。", "attribution_strength": "consistent_with",
             "citation_ids": "abcd1234abcd1234"}]
    with pytest.raises(_MacroNarrErr, match="citation_ids not a list"):
        _parse_theme_claims(rows, (), hardened=False)


# ── F3: non-str attribution_strength hardening (todos-critical-fixes 001) ──────


def test_parse_theme_claims_rejects_list_valued_attribution_strength():
    """AC1: an unhashable list strength (real LLM output shape) must raise
    _MacroNarrErr like every other schema violation — never TypeError from
    the _VALID_STRENGTH set-membership hash test."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": ["consistent_with"], "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_rejects_dict_valued_attribution_strength():
    """AC2: a dict-wrapped strength is also unhashable — same _MacroNarrErr path."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": {"value": "consistent_with"}, "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_rejects_hashable_non_str_attribution_strength():
    """AC3 regression pin: hashable non-strs (None, int) already reach
    _MacroNarrErr today via failed set membership; the new isinstance guard
    must not change that."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    for bad in (None, 3):
        rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
                 "attribution_strength": bad, "citation_ids": []}]
        with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
            _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_list_strength_raises_even_when_hardened():
    """AC6: the hardened attempt raises like any schema violation — only the
    CJK language guard has hardened-drop semantics."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": ["consistent_with"], "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=True)


def test_gather_macro_narrative_list_strength_consumes_retry_then_ok(monkeypatch):
    """AC4 (+AC7 exact-str pin): a list-valued strength on attempt 1 consumes
    ONE schema retry; the valid attempt-2 payload then parses normally. No
    exception escapes gather_macro_narrative."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    bad_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": ["consistent_with"], "citation_ids": [cid]},
    ]}
    good_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": "consistent_with", "citation_ids": [cid]},
    ]}

    calls = {"n": 0}

    def _call(task, messages, route, **kw):
        calls["n"] += 1
        return _fake_resp(_json.dumps(bad_body if calls["n"] == 1 else good_body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.status == "ok"
    assert len(result.doc.blocks) == 1
    assert result.doc.blocks[0].theme == "us_monetary"
    assert result.doc.blocks[0].claims[0].attribution_strength == "consistent_with"
    assert calls["n"] == 2
    assert len(result.cost_entries) == 2


def test_gather_macro_narrative_persistent_list_strength_degrades_after_full_budget(
    monkeypatch,
):
    """AC5: a persistently bad strength exhausts the WHOLE retry budget
    (_MAX_SCHEMA_RETRIES + 1 = 3 calls, 3 cost entries) then degrades via the
    normal (blocks=(), status=last_err) path — it never raises out of
    gather_macro_narrative, so the monitor_cmd gather_error guard is never
    the mechanism for this shape."""
    from irc.monitor.narrative_macro import (
        _MAX_SCHEMA_RETRIES, build_macro_pool, gather_macro_narrative,
    )
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    bad_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": ["consistent_with"], "citation_ids": [cid]},
    ]}

    calls = {"n": 0}

    def _call(task, messages, route, **kw):
        calls["n"] += 1
        return _fake_resp(_json.dumps(bad_body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.blocks == ()
    assert "bad attribution_strength" in result.doc.status
    assert calls["n"] == _MAX_SCHEMA_RETRIES + 1   # 3 today; pinned to the constant
    assert len(result.cost_entries) == _MAX_SCHEMA_RETRIES + 1


def test_gather_macro_narrative_does_not_launder_parse_type_errors(monkeypatch):
    """AC8 pin: the gather except tuple stays (json.JSONDecodeError,
    _MacroNarrErr). A coding-bug TypeError raised inside the parse block must
    propagate, NOT be consumed as a silent schema retry."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    def _boom(*a, **k):
        raise TypeError("coding bug")

    monkeypatch.setattr(nm, "_parse_theme_claims", _boom)

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变。", "attribution_strength": "consistent_with",
         "citation_ids": [cid]},
    ]}

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps(body))

    with pytest.raises(TypeError, match="coding bug"):
        gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
