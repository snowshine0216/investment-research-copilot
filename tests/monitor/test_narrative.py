import json
from irc.monitor.evidence import make_evidence_item
from irc.monitor.narrative import gather_narrative, _banned_verb_present


def _pool():
    return (make_evidence_item("Reuters", "real yields up", "2026-06-15", "https://r", "008986"),)


class _FakeResp:
    def __init__(self, text):
        self.text, self.prompt_tokens, self.completion_tokens, self.latency_ms = text, 9, 4, 1


def _payload(pool, strength="consistent_with", claim="实际利率上行与金价承压一致"):
    return json.dumps({
        "price_action_commentary": [
            {"claim": claim, "attribution_strength": strength,
             "citation_ids": [pool[0].citation_id]}],
        "signal_rationale_commentary": [],
        "risk_commentary": [],
    })


def test_banned_verb_detector():
    assert _banned_verb_present("实际利率上行导致金价下跌")    # 导致 banned
    assert not _banned_verb_present("与金价走弱一致")


def test_valid_narrative(monkeypatch):
    pool = _pool()
    res = gather_narrative(fund_id="008986", pool=pool, route=object(),
                           call=lambda *a, **k: _FakeResp(_payload(pool)))
    assert res.doc.status == "ok"
    assert res.doc.price_action_commentary[0].attribution_strength == "consistent_with"
    assert len(res.cost_entries) == 1


def test_banned_verb_without_support_rejected_then_degrades(monkeypatch):
    pool = _pool()
    bad = _payload(pool, strength="consistent_with", claim="实际利率上行导致金价下跌")

    res = gather_narrative(fund_id="008986", pool=pool, route=object(),
                           call=lambda *a, **k: _FakeResp(bad))
    assert res.doc.status.startswith("banned_verb")
    assert len(res.cost_entries) == 3          # 1 + 2 retries, all billed
    assert res.doc.price_action_commentary == ()


def test_banned_verb_allowed_with_supported_attribution(monkeypatch):
    pool = _pool()
    ok = _payload(pool, strength="supported_attribution", claim="路透：实际利率上行导致金价下跌")
    res = gather_narrative(fund_id="008986", pool=pool, route=object(),
                           call=lambda *a, **k: _FakeResp(ok))
    assert res.doc.status == "ok"


def test_unresolved_citation_rejected(monkeypatch):
    pool = _pool()
    bad = json.dumps({"price_action_commentary": [
        {"claim": "x", "attribution_strength": "unknown", "citation_ids": ["dead0000dead0000"]}],
        "signal_rationale_commentary": [], "risk_commentary": []})
    res = gather_narrative(fund_id="008986", pool=pool, route=object(),
                           call=lambda *a, **k: _FakeResp(bad))
    assert res.doc.status.startswith("unresolved_citation")


def test_empty_pool_early_return_no_call():
    """P0 fix: empty pool → degrade immediately with empty_pool, never call the LLM."""
    calls = {"n": 0}

    def fake_call(*a, **k):
        calls["n"] += 1
        return _FakeResp("{}")

    res = gather_narrative(fund_id="008986", pool=(), route=object(), call=fake_call)
    assert calls["n"] == 0
    assert res.doc.status == "empty_pool"
    assert res.doc.price_action_commentary == ()
    assert res.cost_entries == ()


def test_transport_error_degrades_gracefully():
    """P0 fix: transport exception → provider_error: reason, no crash."""
    pool = _pool()

    def bad_call(task, messages, route, **kw):
        raise OSError("timeout")

    res = gather_narrative(fund_id="008986", pool=pool, route=object(), call=bad_call)
    assert res.doc.status.startswith("provider_error:")
    assert res.cost_entries == ()


def test_none_call_degrades_gracefully():
    """P0 fix: call=None must not raise TypeError."""
    pool = _pool()
    res = gather_narrative(fund_id="008986", pool=pool, route=object(), call=None)
    assert res.doc.status.startswith("provider_error:")
