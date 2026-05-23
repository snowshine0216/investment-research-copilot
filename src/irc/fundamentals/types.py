from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Constituent:
    symbol: str
    name: str
    weight: float
    market: str


@dataclass(frozen=True)
class FilingDigest:
    symbol: str
    fiscal_period: str
    filed_at_iso: str
    revenue_yoy: float | None
    net_income_yoy: float | None
    gross_margin: float | None
    guidance_text: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class BrokerReport:
    symbol: str
    broker: str
    rating: str
    target_price: float | None
    published_iso: str
    title: str
    source_url: str = ""


@dataclass(frozen=True)
class ConstituentSnapshot:
    lookthrough_target: str
    as_of_iso: str
    constituents: tuple[Constituent, ...]
    filings: tuple[FilingDigest, ...]
    broker_reports: tuple[BrokerReport, ...]
    failure_reasons: tuple[str, ...] = ()


# ── Item 003: new types for active-fund constituent layer ─────────────────────

@dataclass(frozen=True)
class NewsItem:
    symbol: str
    title: str
    url: str
    published_iso: str
    summary: str
    source: str


@dataclass(frozen=True)
class FundHolding:
    symbol: str
    name_cn: str
    weight_pct: float
    exchange: Literal["SH", "SZ", "BJ", "HK", "US", "UNKNOWN"]
    provider_symbol: str


@dataclass(frozen=True)
class HoldingsResult:
    constituents: tuple[FundHolding, ...]
    source_report_date: str
    source_report_quarter: str


@dataclass(frozen=True)
class ActiveFundSnapshot:
    fund_id: str
    source_report_date: str
    source_report_quarter: str
    cache_probed_at: str
    constituent_analyses: tuple[object, ...]  # narrowed in Task 3 to tuple[ConstituentAnalysis, ...]
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    fund_level_failure_reasons: tuple[str, ...] = ()
