import httpx
import pytest
from irc.spend.probes.base import get_json_with_retry, ProbeError


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_json_returns_parsed_body_on_200():
    def handler(request):
        return httpx.Response(200, json={"ok": True})
    body = get_json_with_retry("https://api.example.com/x", headers={}, client=_client(handler))
    assert body == {"ok": True}


def test_get_json_raises_probeerror_after_retries_on_500():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")
    with pytest.raises(ProbeError):
        get_json_with_retry("https://api.example.com/x", headers={},
                            client=_client(handler), attempts=2, wait_seconds=0)
    assert calls["n"] == 2


def test_get_json_does_not_retry_on_401():
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, text="nope")
    with pytest.raises(ProbeError):
        get_json_with_retry("https://api.example.com/x", headers={},
                            client=_client(handler), attempts=3, wait_seconds=0)
    assert calls["n"] == 1   # auth failure is not retried
