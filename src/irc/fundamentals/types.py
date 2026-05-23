from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal


__all__ = [
    "ActiveFundSnapshot",
    "BrokerReport",
    "CitationKind",
    "CitationScope",
    "Constituent",
    "ConstituentAnalysis",
    "ConstituentSnapshot",
    "FilingDigest",
    "FundHolding",
    "HoldingsResult",
    "LookthroughKind",
    "LookthroughTarget",
    "NewsItem",
    "ThesisEvidence",
    "ThesisEvidenceKind",
]


LookthroughKind = Literal[
    "broad_index", "sector_theme", "qdii_us", "qdii_hk", "bond", "gold", "active_fund", "qdii_global",
]


@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind
    key: str
    display_cn: str
    provider_symbol: str = ""


ThesisEvidenceKind = Literal["filing", "broker", "news", "policy", "snapshot"]
CitationKind = Literal["data", "information"]
CitationScope = Literal["instrument", "constituent", "asset_class_macro", "policy"]


@dataclass(frozen=True)
class ThesisEvidence:
    """Primary-source citation backing a `thesis_state`, with content-addressed
    provenance.

    `citation_id` is a 16-hex-char prefix of sha256 over the preimage
    (owner_instrument_id : scope : constituent_key : type : canonical_id : date)
    where canonical_id = url or f"{source}:{date}:{summary[:64]}". The id is
    computed in `__post_init__` and overrides any caller-supplied value.

    See `docs/adr/0001-citation-data-model.md` for the binding contract.
    """
    type: ThesisEvidenceKind
    source: str
    url: str
    date: str
    summary: str
    # Required provenance fields (no defaults; callers MUST supply).
    scope: CitationScope
    citation_kind: CitationKind
    owner_instrument_id: str
    parent_fund_id: str | None
    constituent_key: str | None
    # Computed in __post_init__; never accept caller-supplied value.
    citation_id: str = ""
    # Item 003: weight of holding in the parent fund (percent, 0.0–100.0).
    # Appended AFTER citation_id; NOT part of the hash preimage (ADR 0001 §2).
    holding_weight_pct: float | None = None

    def __post_init__(self) -> None:
        if not self.owner_instrument_id:
            raise ValueError("ThesisEvidence.owner_instrument_id must be non-empty")
        if self.citation_kind not in ("data", "information"):
            raise ValueError(f"invalid citation_kind: {self.citation_kind!r}")
        if self.scope not in ("instrument", "constituent",
                              "asset_class_macro", "policy"):
            raise ValueError(f"invalid scope: {self.scope!r}")
        if not self.type or not self.source or not self.date:
            raise ValueError(
                "ThesisEvidence.type/source/date must be non-empty"
            )
        canonical_id = self.url or f"{self.source}:{self.date}:{self.summary[:64]}"
        preimage = (
            f"{self.owner_instrument_id}:{self.scope}:"
            f"{self.constituent_key or ''}:{self.type}:"
            f"{canonical_id}:{self.date}"
        ).encode("utf-8")
        object.__setattr__(
            self, "citation_id", hashlib.sha256(preimage).hexdigest()[:16]
        )


@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str
    name_cn: str
    weight_pct: float
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("ConstituentAnalysis.symbol must be non-empty")
        if self.weight_pct < 0:
            raise ValueError(
                f"ConstituentAnalysis.weight_pct must be >= 0; got {self.weight_pct}"
            )


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
    constituent_analyses: tuple[ConstituentAnalysis, ...]
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    fund_level_failure_reasons: tuple[str, ...] = ()
