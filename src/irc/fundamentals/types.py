from __future__ import annotations

from dataclasses import dataclass


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
