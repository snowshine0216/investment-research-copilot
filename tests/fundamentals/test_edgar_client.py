"""TDD tests for edgar_client. Mocks SEC's two JSON endpoints with respx."""
from __future__ import annotations

import httpx
import pytest
import respx

from irc.fundamentals.edgar_client import fetch_us_filing_digest
from irc.fundamentals.types import FilingDigest


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _tickers_payload() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }


def _facts_url(cik_padded: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"


def _facts_payload() -> dict:
    """Shape mirrors data.sec.gov's companyfacts response: facts > us-gaap > <tag> > units > USD list."""
    revenues = [
        {"fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2025-05-01",
         "end": "2025-03-29", "val": 90_000_000_000, "accn": "0000320193-25-000050"},
        {"fy": 2026, "fp": "Q2", "form": "10-Q", "filed": "2026-05-02",
         "end": "2026-03-28", "val": 95_400_000_000, "accn": "0000320193-26-000050"},
    ]
    net_income = [
        {"fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2025-05-01",
         "end": "2025-03-29", "val": 23_000_000_000, "accn": "x"},
        {"fy": 2026, "fp": "Q2", "form": "10-Q", "filed": "2026-05-02",
         "end": "2026-03-28", "val": 25_000_000_000, "accn": "x"},
    ]
    cost = [
        {"fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2025-05-01",
         "end": "2025-03-29", "val": 50_000_000_000, "accn": "x"},
        {"fy": 2026, "fp": "Q2", "form": "10-Q", "filed": "2026-05-02",
         "end": "2026-03-28", "val": 52_000_000_000, "accn": "x"},
    ]
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": revenues}},
                "NetIncomeLoss": {"units": {"USD": net_income}},
                "CostOfRevenue": {"units": {"USD": cost}},
            }
        },
    }


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """Bypass DNS-based SSRF check so respx mocks aren't shadowed by network resolution."""
    monkeypatch.setattr(
        "irc.fundamentals.edgar_client.verify_host_resolves_publicly", lambda host: None,
    )


@respx.mock
def test_fetch_us_filing_digest_happy_path_computes_yoy_and_margin() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(
        return_value=httpx.Response(200, json=_facts_payload())
    )
    digest = fetch_us_filing_digest("AAPL")
    assert isinstance(digest, FilingDigest)
    assert digest.symbol == "AAPL"
    assert digest.fiscal_period == "2026Q2"
    assert digest.filed_at_iso == "2026-05-02"
    assert digest.revenue_yoy == pytest.approx((95_400 - 90_000) / 90_000, rel=1e-3)
    assert digest.net_income_yoy == pytest.approx((25_000 - 23_000) / 23_000, rel=1e-3)
    assert digest.gross_margin == pytest.approx(
        1 - 52_000_000_000 / 95_400_000_000, rel=1e-3
    )
    assert "0000320193" in digest.source_url
    assert "sec.gov" in digest.source_url


@respx.mock
def test_fetch_us_filing_digest_handles_annual_10k() -> None:
    facts = _facts_payload()
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(
        {"fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-11-01",
         "end": "2026-09-26", "val": 410_000_000_000, "accn": "x"}
    )
    facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].extend([
        {"fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-11-01",
         "end": "2025-09-27", "val": 96_000_000_000, "accn": "x"},
        {"fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-11-01",
         "end": "2026-09-26", "val": 104_000_000_000, "accn": "x"},
    ])
    facts["facts"]["us-gaap"]["CostOfRevenue"]["units"]["USD"].extend([
        {"fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-11-01",
         "end": "2025-09-27", "val": 220_000_000_000, "accn": "x"},
        {"fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-11-01",
         "end": "2026-09-26", "val": 230_000_000_000, "accn": "x"},
    ])
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].insert(0,
        {"fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-11-01",
         "end": "2025-09-27", "val": 385_000_000_000, "accn": "x"})
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(
        return_value=httpx.Response(200, json=facts)
    )
    digest = fetch_us_filing_digest("AAPL")
    assert digest is not None
    assert digest.fiscal_period == "2026FY"  # 10-K with later filed date wins
    assert digest.filed_at_iso == "2026-11-01"
    assert digest.revenue_yoy == pytest.approx((410 - 385) / 385, rel=1e-3)


@respx.mock
def test_fetch_us_filing_digest_uses_alternate_revenue_tag() -> None:
    facts = _facts_payload()
    gaap = facts["facts"]["us-gaap"]
    gaap["RevenueFromContractWithCustomerExcludingAssessedTax"] = gaap.pop("Revenues")
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(
        return_value=httpx.Response(200, json=facts)
    )
    digest = fetch_us_filing_digest("AAPL")
    assert digest is not None
    assert digest.fiscal_period == "2026Q2"


@respx.mock
def test_fetch_us_filing_digest_returns_none_when_ticker_unknown() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    assert fetch_us_filing_digest("ZZZZ") is None


@respx.mock
def test_fetch_us_filing_digest_returns_none_on_tickers_http_error() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(503))
    assert fetch_us_filing_digest("AAPL") is None


@respx.mock
def test_fetch_us_filing_digest_returns_none_on_facts_http_error() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(return_value=httpx.Response(500))
    assert fetch_us_filing_digest("AAPL") is None


@respx.mock
def test_fetch_us_filing_digest_returns_none_on_network_failure() -> None:
    respx.get(_TICKERS_URL).mock(side_effect=httpx.ConnectError("dns"))
    assert fetch_us_filing_digest("AAPL") is None


@respx.mock
def test_fetch_us_filing_digest_returns_none_when_revenue_facts_missing() -> None:
    facts = _facts_payload()
    facts["facts"]["us-gaap"].pop("Revenues")
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(return_value=httpx.Response(200, json=facts))
    assert fetch_us_filing_digest("AAPL") is None


@respx.mock
def test_fetch_us_filing_digest_sends_user_agent_header() -> None:
    route = respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(return_value=httpx.Response(200, json=_facts_payload()))
    fetch_us_filing_digest("AAPL")
    # SEC's fair-use policy requires a descriptive User-Agent
    ua = route.calls[0].request.headers.get("user-agent", "")
    assert ua and "irc" in ua.lower()
