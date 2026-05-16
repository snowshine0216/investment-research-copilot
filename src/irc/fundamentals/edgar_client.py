"""SEC EDGAR adapter.

Calls two JSON endpoints under data.sec.gov / www.sec.gov:
  - /files/company_tickers.json     — ticker → CIK
  - /api/xbrl/companyfacts/CIK*.json — XBRL facts (revenue, net income, cost)

SEC's fair-use policy requires a descriptive User-Agent. SSRF safety: hosts are
resolved with `verify_host_resolves_publicly` before any fetch.

Two public entry points:
  - fetch_us_filing_digest(symbol)             → FilingDigest | None  (legacy)
  - fetch_us_filing_digest_diag(symbol)        → (FilingDigest | None, error_code | None)

The diag variant lets callers (notably `snapshot._build_us_snapshot`) tag each
per-symbol failure with its cause. The legacy variant is a thin wrapper.
"""
from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

from irc.fundamentals.types import FilingDigest
from irc.llm.http_client import verify_host_resolves_publicly


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

EDGAR_ERROR_MISSING_EMAIL = "missing_email"
EDGAR_ERROR_HTTP_4XX = "http_4xx"
EDGAR_ERROR_HTTP_5XX = "http_5xx"
EDGAR_ERROR_NETWORK = "network"
EDGAR_ERROR_DECODE = "decode"
EDGAR_ERROR_CIK_MISS = "cik_not_found"

# SEC fair-use policy requires a valid contact email in the User-Agent.
_EDGAR_CONTACT = os.environ.get("EDGAR_CONTACT_EMAIL", "")
_USER_AGENT = (
    f"irc-research ({_EDGAR_CONTACT})"
    if _EDGAR_CONTACT
    else "irc-research (set EDGAR_CONTACT_EMAIL in .env)"
)

# Module-level sentinel: flip to True after the first warning so we don't
# spam stderr with one line per failed symbol. Mutation here is the only
# permitted module-level state in this file; see design doc.
_warned_missing_email: bool = False

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


def _maybe_warn_missing_email() -> None:
    global _warned_missing_email
    if _warned_missing_email:
        return
    _warned_missing_email = True
    print(
        "WARNING: EDGAR_CONTACT_EMAIL is empty — SEC may rate-limit or reject "
        "US filing fetches. Set it in .env.",
        file=sys.stderr,
    )


def _reset_warned_missing_email() -> None:
    """Reset the warn-once sentinel. For use in tests only."""
    global _warned_missing_email
    _warned_missing_email = False


def _fetch_json(url: str, *, timeout_s: float = 15.0) -> tuple[Any | None, str | None]:
    host = urlparse(url).hostname
    if not host:
        return None, EDGAR_ERROR_NETWORK
    try:
        verify_host_resolves_publicly(host)
    except Exception:
        return None, EDGAR_ERROR_NETWORK
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout_s)
    except httpx.HTTPError:
        return None, EDGAR_ERROR_NETWORK
    if resp.status_code >= 500:
        return None, EDGAR_ERROR_HTTP_5XX
    if resp.status_code >= 400:
        return None, EDGAR_ERROR_HTTP_4XX
    if resp.status_code != 200:
        return None, EDGAR_ERROR_NETWORK
    try:
        return resp.json(), None
    except ValueError:
        return None, EDGAR_ERROR_DECODE


def _lookup_cik(ticker: str) -> tuple[str | None, str | None]:
    body, err = _fetch_json(_TICKERS_URL)
    if err is not None:
        return None, err
    if not isinstance(body, dict):
        return None, EDGAR_ERROR_DECODE
    target = ticker.upper()
    for entry in body.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("ticker", "")).upper() == target:
            cik = entry.get("cik_str")
            if cik is None:
                return None, EDGAR_ERROR_CIK_MISS
            try:
                return str(int(cik)).zfill(10), None
            except (ValueError, TypeError):
                return None, EDGAR_ERROR_DECODE
    return None, EDGAR_ERROR_CIK_MISS


def fetch_us_filing_digest_diag(symbol: str) -> tuple[FilingDigest | None, str | None]:
    """Latest 10-K / 10-Q digest with a typed failure code on the None paths.

    Short-circuits with `EDGAR_ERROR_MISSING_EMAIL` (and a one-time stderr
    warning) when `EDGAR_CONTACT_EMAIL` is empty, so SEC's rate limiter never
    sees an unidentified request.
    """
    if not _EDGAR_CONTACT:
        _maybe_warn_missing_email()
        return None, EDGAR_ERROR_MISSING_EMAIL

    cik, err = _lookup_cik(symbol)
    if cik is None:
        return None, err
    facts, err = _fetch_json(_FACTS_URL.format(cik=cik))
    if facts is None:
        return None, err
    if not isinstance(facts, dict):
        return None, EDGAR_ERROR_DECODE
    revenue_rows = _units_usd(facts, _REVENUE_TAGS)
    if not revenue_rows:
        return None, EDGAR_ERROR_DECODE
    latest = _latest_periodic(revenue_rows)
    if latest is None:
        return None, EDGAR_ERROR_DECODE
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

    return (
        FilingDigest(
            symbol=symbol.upper(),
            fiscal_period=_fiscal_period(fy, fp),
            filed_at_iso=str(latest.get("filed", "")),
            revenue_yoy=revenue_yoy,
            net_income_yoy=net_income_yoy,
            gross_margin=gross_margin,
            source_url=_FACTS_URL.format(cik=cik),
        ),
        None,
    )


def fetch_us_filing_digest(symbol: str) -> FilingDigest | None:
    """Legacy single-return signature. Use `fetch_us_filing_digest_diag` for
    callers that need the typed error code."""
    digest, _err = fetch_us_filing_digest_diag(symbol)
    return digest


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
    candidates = [r for r in rows if r.get("form") in ("10-K", "10-Q")]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("filed", ""))


def _match_prior_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy - 1 and r.get("fp") == fp:
            return r
    return None


def _match_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy and r.get("fp") == fp and r.get("form") in ("10-K", "10-Q"):
            return r
    return None


def _fiscal_period(fy: int, fp: str) -> str:
    return f"{fy}FY" if fp == "FY" else f"{fy}{fp}"
