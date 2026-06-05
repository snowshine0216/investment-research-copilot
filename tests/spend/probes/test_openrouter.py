import httpx
from irc.spend.probes.openrouter import OpenRouterProbe


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parses_remaining_credits():
    def handler(request):
        return httpx.Response(200, json={"data": {"total_credits": 20.0, "total_usage": 7.5}})
    r = OpenRouterProbe().probe("sk-or-test", client=_client(handler))
    assert r.provider == "openrouter"
    assert r.amount == 12.5
    assert r.currency == "USD"
    assert r.available is True
    assert r.source == "api"


def test_failure_is_unreadable():
    def handler(request):
        return httpx.Response(503, text="down")
    r = OpenRouterProbe().probe("sk-or-test", client=_client(handler))
    assert r.amount is None and r.source == "probe_failed"
