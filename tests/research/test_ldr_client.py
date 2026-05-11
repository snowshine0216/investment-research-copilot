from __future__ import annotations
from unittest.mock import patch
import pytest
import respx
import httpx
from irc.research.ldr_client import run_research, LDRResearchResult, _is_loopback_host
from irc.llm.http_client import SSRFError


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_run_research_happy_path(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("LDR_API_TOKEN", "tok")
    respx.post("http://localhost:8080/api/v1/research").mock(
        return_value=httpx.Response(200, json={
            "report_md": "# Gold drivers\n[1] Fed minutes.",
            "citations": [{"index": 1, "title": "Fed minutes", "url": "https://x.com/fed"}],
        })
    )
    out = run_research(query="What drove gold last quarter?", time_budget_s=60)
    assert isinstance(out, LDRResearchResult)
    assert "Gold drivers" in out.report_md
    assert len(out.citations) == 1


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly")
def test_ldr_returns_empty_on_503(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("LDR_API_TOKEN", "tok")
    respx.post("http://localhost:8080/api/v1/research").mock(return_value=httpx.Response(503))
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert out.failure_reason


@respx.mock
@patch("irc.research.ldr_client._verify_host_resolves_publicly", side_effect=AssertionError("localhost should bypass public DNS guard"))
def test_ldr_allows_loopback_host_without_public_dns_guard(_mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    respx.post("http://localhost:8080/api/v1/research").mock(
        return_value=httpx.Response(200, json={"report_md": "# Local", "citations": []})
    )

    out = run_research(query="local ldr", time_budget_s=10)

    assert out.report_md == "# Local"


@patch("irc.research.ldr_client._verify_host_resolves_publicly", side_effect=SSRFError("private network"))
def test_ldr_keeps_public_dns_guard_for_non_loopback_hosts(mock_ssrf, monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://10.0.0.5:8080")

    out = run_research(query="private ldr", time_budget_s=10)

    assert out.report_md == ""
    assert out.failure_reason.startswith("SSRF blocked")
    mock_ssrf.assert_called_once_with("10.0.0.5")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_ldr_loopback_host_detection(host):
    assert _is_loopback_host(host) is True
