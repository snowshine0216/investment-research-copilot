from __future__ import annotations
from dataclasses import dataclass, field
import ipaddress
import os
import re
import time
from urllib.parse import urlparse
import httpx
from irc.llm.http_client import verify_host_resolves_publicly, SSRFError


_POLL_INTERVAL_S = 5
_HEARTBEAT_INTERVAL_S = 30
_HTTP_REQUEST_TIMEOUT_S = 30
_LOGIN_MAX_RETRIES = 3
_LOGIN_BACKOFF_S = 10
_MAX_CITATIONS = 10
_ERROR_PREVIEW_LEN = 200


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


def _extract_csrf_from_html(html: str) -> str:
    """Extract csrf_token value from a Flask-WTF login form."""
    for pattern in (
        r'<input[^>]+name=["\']csrf_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']csrf_token["\']',
    ):
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return ""


def _login(client: httpx.Client, base: str, username: str, password: str) -> tuple[str, str]:
    """Authenticate and return (api_csrf_token, error_message).

    LDR uses session-based auth:
      1. GET /auth/login  → parse CSRF token from HTML form
      2. POST /auth/login → establish session cookie
      3. GET /auth/csrf-token → obtain CSRF token for API calls
    """
    try:
        login_page = client.get(f"{base}/auth/login")
        csrf = _extract_csrf_from_html(login_page.text)
        if not csrf:
            return "", "could not extract CSRF token from login page"

        for attempt in range(_LOGIN_MAX_RETRIES):
            resp = client.post(
                f"{base}/auth/login",
                data={"username": username, "password": password, "csrf_token": csrf},
                follow_redirects=True,
            )
            if resp.status_code == 429:
                time.sleep(_LOGIN_BACKOFF_S)
                continue
            if resp.status_code not in (200,):
                return "", f"login POST returned {resp.status_code}"
            break
        else:
            return "", f"login rate-limited (429) after {_LOGIN_MAX_RETRIES} retries"

        token_resp = client.get(f"{base}/auth/csrf-token")
        if token_resp.status_code != 200:
            return "", f"csrf-token endpoint returned {token_resp.status_code}"
        token = token_resp.json().get("csrf_token", "")
        if not token:
            return "", "empty csrf_token in response"
        return token, ""
    except Exception as exc:
        return "", str(exc)


def _sources_to_citations(sources: list) -> list[LDRCitation]:
    cits = []
    for i, s in enumerate(sources[:_MAX_CITATIONS], start=1):
        if isinstance(s, str):
            cits.append(LDRCitation(index=i, title=s, url=s))
        elif isinstance(s, dict):
            cits.append(LDRCitation(
                index=i,
                title=s.get("title", s.get("url", str(s))),
                url=s.get("url", ""),
            ))
    return cits


_RESEARCH_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def run_research(query: str, time_budget_s: int = 120) -> LDRResearchResult:
    base = os.environ.get("LDR_BASE_URL", "http://localhost:5000").rstrip("/")
    host = urlparse(base).hostname or ""
    try:
        if not _is_loopback_host(host):
            verify_host_resolves_publicly(host)
    except SSRFError as e:
        return LDRResearchResult(report_md="", failure_reason=f"SSRF blocked: {e}")

    username = os.environ.get("LDR_USERNAME", "")
    password = os.environ.get("LDR_PASSWORD", "")
    if not username or not password:
        return LDRResearchResult(
            report_md="",
            failure_reason="LDR_USERNAME and LDR_PASSWORD must be set",
        )

    try:
        with httpx.Client(timeout=_HTTP_REQUEST_TIMEOUT_S) as client:
            api_csrf, login_err = _login(client, base, username, password)
            if login_err:
                return LDRResearchResult(
                    report_md="",
                    failure_reason=f"LDR login failed: {login_err}",
                )
            headers = {"Content-Type": "application/json", "X-CSRF-Token": api_csrf}

            research_id, err = _start_research(client, base, headers, query)
            if err:
                return LDRResearchResult(report_md="", failure_reason=err)
            print(f"        job: {research_id}  (budget {time_budget_s}s)", flush=True)

            poll_err = _poll_until_complete(client, base, research_id, headers, time_budget_s)
            if poll_err:
                return LDRResearchResult(report_md="", failure_reason=poll_err)

            return _fetch_report(client, base, research_id, headers)
    except Exception as e:
        return LDRResearchResult(report_md="", failure_reason=str(e))


def _start_research(
    client: httpx.Client,
    base: str,
    headers: dict,
    query: str,
) -> tuple[str, str]:
    """POST to start_research; return (research_id, error). Empty error means success."""
    search_tool = os.environ.get("LDR_SEARCH_TOOL", "")
    payload: dict = {"query": query, "iterations": 1}
    if search_tool:
        payload["search_tool"] = search_tool
    resp = client.post(f"{base}/api/start_research", headers=headers, json=payload)
    if resp.status_code != 200:
        return "", f"start_research http {resp.status_code}: {resp.text[:_ERROR_PREVIEW_LEN]}"
    research_id = resp.json().get("research_id", "")
    if not research_id:
        return "", f"no research_id in response: {resp.text[:_ERROR_PREVIEW_LEN]}"
    if not _RESEARCH_ID_RE.match(research_id):
        return "", f"invalid research_id format: {research_id!r}"
    return research_id, ""


def _poll_until_complete(
    client: httpx.Client,
    base: str,
    research_id: str,
    headers: dict,
    time_budget_s: int,
) -> str:
    """Poll status until completed; return empty string on success or an error message."""
    deadline = time.monotonic() + time_budget_s
    poll_start = time.monotonic()
    last_heartbeat = poll_start
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
        status_resp = client.get(
            f"{base}/api/research/{research_id}/status",
            headers=headers,
        )
        if status_resp.status_code != 200:
            return f"status http {status_resp.status_code}"
        status = status_resp.json().get("status", "")
        now = time.monotonic()
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
            print(f"        … {int(now - poll_start)}s elapsed, status={status}", flush=True)
            last_heartbeat = now
        if status == "completed":
            return ""
        if status == "failed":
            return f"LDR research failed: {status_resp.json().get('error', '')}"
    return "timed out"


def _fetch_report(
    client: httpx.Client,
    base: str,
    research_id: str,
    headers: dict,
) -> LDRResearchResult:
    """Fetch the completed report and return a LDRResearchResult."""
    resp = client.get(f"{base}/api/report/{research_id}", headers=headers)
    if resp.status_code != 200:
        return LDRResearchResult(report_md="", failure_reason=f"report http {resp.status_code}")
    body = resp.json()
    return LDRResearchResult(
        report_md=body.get("summary", body.get("report", "")),
        citations=_sources_to_citations(body.get("sources", [])),
    )
