from __future__ import annotations
from unittest.mock import patch
import pytest
import respx
import httpx
from irc.research.ldr_client import (
    run_research,
    LDRResearchResult,
    _is_loopback_host,
    _extract_csrf_from_html,
    _sources_to_citations,
)
from irc.llm.http_client import SSRFError

_LOGIN_HTML = '<input name="csrf_token" value="login-csrf-123">'


def _mock_auth(base: str = "http://localhost:5000") -> None:
    respx.get(f"{base}/auth/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post(f"{base}/auth/login").mock(return_value=httpx.Response(200, text="OK"))
    respx.get(f"{base}/auth/csrf-token").mock(
        return_value=httpx.Response(200, json={"csrf_token": "api-csrf-456"})
    )


def _mock_research_flow(base: str = "http://localhost:5000", research_id: str = "r1", summary: str = "# Gold drivers\nFed minutes.", sources: list | None = None) -> None:
    """Mock the async start_research → status → report flow."""
    if sources is None:
        sources = ["https://x.com/fed"]
    respx.post(f"{base}/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": research_id})
    )
    respx.get(f"{base}/api/research/{research_id}/status").mock(
        return_value=httpx.Response(200, json={"status": "completed"})
    )
    respx.get(f"{base}/api/report/{research_id}").mock(
        return_value=httpx.Response(200, json={"summary": summary, "sources": sources})
    )


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_run_research_happy_path(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    _mock_research_flow()
    out = run_research(query="What drove gold last quarter?", time_budget_s=60)
    assert isinstance(out, LDRResearchResult)
    assert "Gold drivers" in out.report_md
    assert len(out.citations) == 1
    assert out.citations[0].url == "https://x.com/fed"


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_returns_empty_on_503(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(503)
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert out.failure_reason


@respx.mock
@patch(
    "irc.research.ldr_client._verify_host_resolves_publicly",
    side_effect=AssertionError("localhost should bypass public DNS guard"),
)
def test_ldr_allows_loopback_host_without_public_dns_guard(_mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    _mock_research_flow(research_id="r2", summary="# Local", sources=[])
    out = run_research(query="local ldr", time_budget_s=10)
    assert out.report_md == "# Local"


@patch(
    "irc.research.ldr_client._verify_host_resolves_publicly",
    side_effect=SSRFError("private network"),
)
def test_ldr_keeps_public_dns_guard_for_non_loopback_hosts(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://10.0.0.5:8080")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    out = run_research(query="private ldr", time_budget_s=10)
    assert out.report_md == ""
    assert out.failure_reason.startswith("SSRF blocked")
    mock_ssrf.assert_called_once_with("10.0.0.5")


def test_ldr_missing_credentials_returns_failure(monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.delenv("LDR_USERNAME", raising=False)
    monkeypatch.delenv("LDR_PASSWORD", raising=False)
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "LDR_USERNAME" in out.failure_reason


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_login_failure_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "wrong")
    # Return login page with no CSRF token → login returns None
    respx.get("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text="<html>no csrf here</html>")
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "login failed" in out.failure_reason


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_ldr_loopback_host_detection(host):
    assert _is_loopback_host(host) is True


def test_extract_csrf_name_before_value():
    html = '<input name="csrf_token" value="tok123" type="hidden">'
    assert _extract_csrf_from_html(html) == "tok123"


def test_extract_csrf_value_before_name():
    html = '<input value="tok456" name="csrf_token" type="hidden">'
    assert _extract_csrf_from_html(html) == "tok456"


def test_extract_csrf_missing_returns_empty():
    assert _extract_csrf_from_html("<html>no token</html>") == ""


def test_sources_to_citations_strings():
    cits = _sources_to_citations(["https://a.com", "https://b.com"])
    assert len(cits) == 2
    assert cits[0].index == 1
    assert cits[0].url == "https://a.com"


def test_sources_to_citations_dicts():
    cits = _sources_to_citations([{"title": "Fed", "url": "https://fed.gov"}])
    assert cits[0].title == "Fed"
    assert cits[0].url == "https://fed.gov"


def test_sources_to_citations_caps_at_10():
    sources = [f"https://s{i}.com" for i in range(20)]
    assert len(_sources_to_citations(sources)) == 10


# ---------------------------------------------------------------------------
# _is_loopback_host: non-loopback returns False
# ---------------------------------------------------------------------------

def test_ldr_non_loopback_host_detection():
    assert _is_loopback_host("8.8.8.8") is False
    assert _is_loopback_host("example.com") is False


# ---------------------------------------------------------------------------
# _login: error paths (login POST non-200, csrf-token non-200, empty csrf_token)
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_login_post_non200_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "wrong_pass")
    respx.get("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )
    respx.post("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(401)
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "login failed" in out.failure_reason


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_csrf_token_endpoint_non200_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    respx.get("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )
    respx.post("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text="OK")
    )
    respx.get("http://localhost:5000/auth/csrf-token").mock(
        return_value=httpx.Response(403)
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "login failed" in out.failure_reason


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_empty_csrf_token_in_response_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    respx.get("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )
    respx.post("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text="OK")
    )
    respx.get("http://localhost:5000/auth/csrf-token").mock(
        return_value=httpx.Response(200, json={"csrf_token": ""})
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "login failed" in out.failure_reason


# ---------------------------------------------------------------------------
# run_research: no research_id in start_research response
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_no_research_id_in_start_response(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"status": "queued"})
    )
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert "no research_id" in out.failure_reason


# ---------------------------------------------------------------------------
# run_research: status poll returns non-200
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_status_poll_non200_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": "r99"})
    )
    respx.get("http://localhost:5000/api/research/r99/status").mock(
        return_value=httpx.Response(500)
    )
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert "status http 500" in out.failure_reason


# ---------------------------------------------------------------------------
# run_research: status == "failed" returns failure with error field
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_status_failed_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": "r9"})
    )
    respx.get("http://localhost:5000/api/research/r9/status").mock(
        return_value=httpx.Response(200, json={"status": "failed", "error": "timeout in LDR worker"})
    )
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert "timeout in LDR worker" in out.failure_reason


# ---------------------------------------------------------------------------
# run_research: report fetch returns non-200
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_report_fetch_non200_returns_failure(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": "r10"})
    )
    respx.get("http://localhost:5000/api/research/r10/status").mock(
        return_value=httpx.Response(200, json={"status": "completed"})
    )
    respx.get("http://localhost:5000/api/report/r10").mock(
        return_value=httpx.Response(404)
    )
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert "report http 404" in out.failure_reason


# ---------------------------------------------------------------------------
# run_research: LDR_SEARCH_TOOL env is injected into payload
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_search_tool_injected_in_payload(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    monkeypatch.setenv("LDR_SEARCH_TOOL", "searxng")
    _mock_auth()
    _mock_research_flow(research_id="r_tool")

    captured: dict = {}

    def capture_start(request, *a, **kw):
        import json as _json
        captured["payload"] = _json.loads(request.content)
        return httpx.Response(200, json={"research_id": "r_tool"})

    respx.post("http://localhost:5000/api/start_research").mock(side_effect=capture_start)
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md != "" or "r_tool" in str(captured)
    assert captured.get("payload", {}).get("search_tool") == "searxng"



# ---------------------------------------------------------------------------
# _login: 429 retry-exhaustion — all attempts rate-limited (gap: ldr_client:76)
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
@patch("irc.research.ldr_client.time.sleep")
def test_ldr_login_429_retry_exhaustion_returns_failure(mock_sleep, mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    respx.get("http://localhost:5000/auth/login").mock(
        return_value=httpx.Response(200, text='<input name="csrf_token" value="tok">')
    )
    # All POST attempts return 429 → exhausts all LOGIN_MAX_RETRIES
    respx.post("http://localhost:5000/auth/login").mock(
        side_effect=lambda req: httpx.Response(429)
    )
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert "login failed" in out.failure_reason
    assert "3 retries" in out.failure_reason
    # sleep should have been called once per retry (3 times)
    assert mock_sleep.call_count == 3


# ---------------------------------------------------------------------------
# run_research: polling timeout — while...else fires when deadline exceeded
#               (gap: ldr_client:189)
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
@patch("irc.research.ldr_client.time.sleep")
@patch("irc.research.ldr_client.time.monotonic")
def test_ldr_polling_timeout_returns_failure(mock_monotonic, mock_sleep, mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": "r_tout"})
    )
    # deadline = 0.0 + 60 = 60; poll_start = 0.0; while check: 100.0 < 60 → False → else fires
    mock_monotonic.side_effect = [0.0, 0.0, 100.0]
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert out.failure_reason == "timed out"


# ---------------------------------------------------------------------------
# _start_research: research_id with path-traversal chars rejected (security fix)
# ---------------------------------------------------------------------------

@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_invalid_research_id_path_traversal_rejected(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:5000")
    monkeypatch.setenv("LDR_USERNAME", "user")
    monkeypatch.setenv("LDR_PASSWORD", "pass")
    _mock_auth()
    respx.post("http://localhost:5000/api/start_research").mock(
        return_value=httpx.Response(200, json={"research_id": "../../../etc/passwd"})
    )
    out = run_research(query="x", time_budget_s=60)
    assert out.report_md == ""
    assert "invalid research_id" in out.failure_reason
