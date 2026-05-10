from __future__ import annotations
import respx
import httpx
from irc.research.ldr_client import run_research, LDRResearchResult


@respx.mock
def test_ldr_run_research_happy_path(monkeypatch):
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
def test_ldr_returns_empty_on_503(monkeypatch):
    monkeypatch.setenv("LDR_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("LDR_API_TOKEN", "tok")
    respx.post("http://localhost:8080/api/v1/research").mock(return_value=httpx.Response(503))
    out = run_research(query="x", time_budget_s=10)
    assert out.report_md == ""
    assert out.failure_reason
