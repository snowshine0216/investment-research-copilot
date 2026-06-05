import httpx
from irc.spend.probes.deepseek import DeepSeekProbe


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parses_balance_and_available_flag():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={
            "is_available": True,
            "balance_infos": [{"currency": "CNY", "total_balance": "42.50"}],
        })
    r = DeepSeekProbe().probe("sk-test", client=_client(handler))
    assert r.provider == "deepseek"
    assert r.amount == 42.50
    assert r.currency == "CNY"
    assert r.available is True
    assert r.source == "api"


def test_selects_cny_entry_regardless_of_order():
    # Real /user/balance returns BOTH a CNY and a USD balance_info, and the order
    # is not stable. Pricing is CNY, so the probe must read the CNY entry — not [0].
    def handler(request):
        return httpx.Response(200, json={
            "is_available": True,
            "balance_infos": [
                {"currency": "USD", "total_balance": "0.00"},
                {"currency": "CNY", "total_balance": "99.61"},
            ],
        })
    r = DeepSeekProbe().probe("sk-test", client=_client(handler))
    assert r.currency == "CNY"
    assert r.amount == 99.61
    assert r.available is True


def test_probe_failure_degrades_to_unreadable_reading():
    def handler(request):
        return httpx.Response(500, text="boom")
    r = DeepSeekProbe().probe("sk-test", client=_client(handler))
    assert r.amount is None
    assert r.available is False
    assert r.source == "probe_failed"
