from __future__ import annotations
from dataclasses import dataclass, field
import ipaddress
import os
from urllib.parse import urlparse
import httpx
from irc.llm.http_client import _verify_host_resolves_publicly, SSRFError


@dataclass(frozen=True)
class LDRCitation:
    index: int
    title: str
    url: str


@dataclass(frozen=True)
class LDRResearchResult:
    report_md: str
    citations: list[LDRCitation] = field(default_factory=list)
    failure_reason: str = ""


def _is_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def run_research(query: str, time_budget_s: int = 120) -> LDRResearchResult:
    base = os.environ.get("LDR_BASE_URL", "http://localhost:8080").rstrip("/")
    host = urlparse(base).hostname or ""
    try:
        if not _is_loopback_host(host):
            _verify_host_resolves_publicly(host)
    except SSRFError as e:
        return LDRResearchResult(report_md="", failure_reason=f"SSRF blocked: {e}")
    token = os.environ.get("LDR_API_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=time_budget_s) as client:
            resp = client.post(
                f"{base}/api/v1/research",
                headers=headers,
                json={"query": query, "time_budget_s": time_budget_s},
            )
        if resp.status_code != 200:
            return LDRResearchResult(report_md="", failure_reason=f"http {resp.status_code}")
        body = resp.json()
        cits = [LDRCitation(**c) for c in body.get("citations", [])]
        return LDRResearchResult(report_md=body.get("report_md", ""), citations=cits)
    except Exception as e:
        return LDRResearchResult(report_md="", failure_reason=str(e))
