"""SEC EDGAR adapter.

Calls two JSON endpoints under data.sec.gov / www.sec.gov:
  - /files/company_tickers.json     — ticker → CIK
  - /api/xbrl/companyfacts/CIK*.json — XBRL facts (revenue, net income, cost)

SEC's fair-use policy requires a descriptive User-Agent. SSRF safety: hosts are
resolved with `verify_host_resolves_publicly` before any fetch.

Returns None on any failure; the snapshot orchestrator records the diagnostic.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from irc.fundamentals.types import FilingDigest
from irc.llm.http_client import verify_host_resolves_publicly


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# SEC fair-use policy requires a valid contact email in the User-Agent.
# Set EDGAR_CONTACT_EMAIL in .env. Without it, requests use a placeholder
# that SEC may rate-limit or block.
_EDGAR_CONTACT = os.environ.get("EDGAR_CONTACT_EMAIL", "")
_USER_AGENT = (
    f"irc-research ({_EDGAR_CONTACT})"
    if _EDGAR_CONTACT
    else "irc-research (set EDGAR_CONTACT_EMAIL in .env)"
)

_REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
)
_NET_INCOME_TAGS = ("NetIncomeLoss",)
_COST_TAGS = (
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
)


def _fetch_json(url: str, *, timeout_s: float = 15.0) -> Any:
    """GET a JSON document. Returns None on any failure (network, HTTP, decode)."""
    host = urlparse(url).hostname
    if not host:
        return None
    try:
        verify_host_resolves_publicly(host)
    except Exception:
        return None
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout_s)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _lookup_cik(ticker: str) -> str | None:
    """Return the zero-padded 10-digit CIK for a ticker, or None if unknown."""
    body = _fetch_json(_TICKERS_URL)
    if not isinstance(body, dict):
        return None
    target = ticker.upper()
    for entry in body.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("ticker", "")).upper() == target:
            cik = entry.get("cik_str")
            if cik is None:
                return None
            return str(int(cik)).zfill(10)
    return None


def _units_usd(facts: dict, tag_candidates: tuple[str, ...]) -> list[dict]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tag_candidates:
        series = gaap.get(tag)
        if not isinstance(series, dict):
            continue
        units = series.get("units", {})
        usd = units.get("USD")
        if isinstance(usd, list) and usd:
            return usd
    return []


def _latest_periodic(rows: list[dict]) -> dict | None:
    """Return the row with the most recent `filed` date that is a 10-K or 10-Q."""
    candidates = [r for r in rows if r.get("form") in ("10-K", "10-Q")]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("filed", ""))


def _match_prior_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy - 1 and r.get("fp") == fp:
            return r
    return None


def _fiscal_period(fy: int, fp: str) -> str:
    return f"{fy}FY" if fp == "FY" else f"{fy}{fp}"


def fetch_us_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest 10-K / 10-Q digest for a US-listed company. Returns None on failure."""
    cik = _lookup_cik(symbol)
    if cik is None:
        return None
    facts = _fetch_json(_FACTS_URL.format(cik=cik))
    if not isinstance(facts, dict):
        return None
    revenue_rows = _units_usd(facts, _REVENUE_TAGS)
    if not revenue_rows:
        return None
    latest = _latest_periodic(revenue_rows)
    if latest is None:
        return None
    fy = int(latest["fy"])
    fp = str(latest["fp"])
    prior_revenue = _match_prior_year(revenue_rows, fy, fp)
    revenue_yoy = (
        (latest["val"] - prior_revenue["val"]) / prior_revenue["val"]
        if prior_revenue and prior_revenue.get("val")
        else None
    )

    net_rows = _units_usd(facts, _NET_INCOME_TAGS)
    net_cur = _match_year(net_rows, fy, fp)
    net_prior = _match_year(net_rows, fy - 1, fp)
    net_income_yoy = (
        (net_cur["val"] - net_prior["val"]) / net_prior["val"]
        if net_cur and net_prior and net_prior.get("val")
        else None
    )

    cost_rows = _units_usd(facts, _COST_TAGS)
    cost_cur = _match_year(cost_rows, fy, fp)
    gross_margin = (
        1 - cost_cur["val"] / latest["val"]
        if cost_cur and latest.get("val")
        else None
    )

    return FilingDigest(
        symbol=symbol.upper(),
        fiscal_period=_fiscal_period(fy, fp),
        filed_at_iso=str(latest.get("filed", "")),
        revenue_yoy=revenue_yoy,
        net_income_yoy=net_income_yoy,
        gross_margin=gross_margin,
        source_url=_FACTS_URL.format(cik=cik),
    )


def _match_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy and r.get("fp") == fp and r.get("form") in ("10-K", "10-Q"):
            return r
    return None
