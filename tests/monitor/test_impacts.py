import json
from irc.monitor.evidence import make_evidence_item
from irc.monitor.impacts import gather_impacts, ImpactsResult


def _pool():
    return (make_evidence_item("Reuters", "real yields up", "2026-06-15", "https://r", "008986"),)


def _good_payload(pool):
    return json.dumps({"impacts": [
        {"key": "gold_drivers", "impact": -0.5, "confidence": 0.8,
         "citation_ids": [pool[0].citation_id]},
    ]})


class _FakeResp:
    def __init__(self, text):
        self.text, self.prompt_tokens, self.completion_tokens, self.latency_ms = text, 10, 5, 1


def test_gather_impacts_first_call_valid(monkeypatch):
    pool = _pool()
    calls = {"n": 0}

    def fake_call(task, messages, route, **kw):
        calls["n"] += 1
        return _FakeResp(_good_payload(pool))

    res = gather_impacts(
        fund_id="008986", themes=("gold_drivers",), pool=pool,
        route=object(), call=fake_call,
    )
    assert isinstance(res, ImpactsResult)
    assert res.impacts[0].impact == -0.5
    assert len(res.cost_entries) == 1          # one billed call
    assert calls["n"] == 1


def test_invalid_then_valid_bills_both(monkeypatch):
    pool = _pool()
    seq = iter([_FakeResp("not json"), _FakeResp(_good_payload(pool))])

    def fake_call(task, messages, route, **kw):
        return next(seq)

    res = gather_impacts(fund_id="008986", themes=("gold_drivers",), pool=pool,
                         route=object(), call=fake_call)
    assert len(res.cost_entries) == 2          # invalid call still billed (§6.4)
    assert res.impacts[0].impact == -0.5


def test_exhausted_retries_degrades(monkeypatch):
    pool = _pool()

    def fake_call(task, messages, route, **kw):
        return _FakeResp("never valid")

    res = gather_impacts(fund_id="008986", themes=("gold_drivers",), pool=pool,
                         route=object(), call=fake_call)
    assert res.status.startswith("schema_invalid")
    assert len(res.cost_entries) == 3          # 1 + 2 schema-retries, all billed
    assert res.impacts == ()


def test_empty_pool_early_return_no_call():
    """P1/P0 fix: empty pool → degrade immediately, never call the LLM."""
    calls = {"n": 0}

    def fake_call(*a, **k):
        calls["n"] += 1
        return _FakeResp("{}")

    res = gather_impacts(fund_id="008986", themes=("gold_drivers",), pool=(),
                         route=object(), call=fake_call)
    assert calls["n"] == 0                     # call must NOT be invoked
    assert res.status == "empty_pool"
    assert res.impacts == ()
    assert res.cost_entries == ()


def test_transport_error_degrades_gracefully():
    """P0 fix: transport exception (not JSONDecodeError) → provider_error: reason, no crash."""
    pool = _pool()

    def bad_call(task, messages, route, **kw):
        raise ValueError("connection refused")

    res = gather_impacts(fund_id="008986", themes=("gold_drivers",), pool=pool,
                         route=object(), call=bad_call)
    assert res.status.startswith("provider_error:")
    assert res.impacts == ()
    assert res.cost_entries == ()              # no response obtained, so no billing


def test_none_call_degrades_gracefully():
    """P0 fix: call=None must not raise TypeError; degrades to provider_error."""
    pool = _pool()
    res = gather_impacts(fund_id="008986", themes=("gold_drivers",), pool=pool,
                         route=object(), call=None)
    assert res.status.startswith("provider_error:")
    assert res.impacts == ()
