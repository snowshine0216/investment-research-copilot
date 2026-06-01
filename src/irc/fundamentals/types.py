from __future__ import annotations

import hashlib
import re as _re
from dataclasses import dataclass
from typing import Literal


_ISO_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUARTER_RE_FNR = _re.compile(r"^\d{4}Q[1-4]$")


__all__ = [
    "ActiveFundSnapshot",
    "BrokerReport",
    "CitationKind",
    "CitationScope",
    "Constituent",
    "ConstituentAnalysis",
    "ConstituentSnapshot",
    "FilingDigest",
    "FundAnnouncement",
    "FundHolding",
    "FundLevelSnapshot",
    "FundNavReport",
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

    @classmethod
    def from_dict(cls, d: dict) -> "ThesisEvidence":
        """Rebuild a `ThesisEvidence` from its JSON dict form.

        Recomputes `citation_id` via `__post_init__`. If the JSON dict carries
        a `citation_id` that doesn't match the recomputed value, raise — detects
        drift/tampering of `opportunity_report.json` between stages.

        Single source of truth for the dict→dataclass rebuild across
        snapshot_cache.py, memo_cmd.py, and the renderer pipeline.
        """
        expected_id = d.get("citation_id")
        ev = cls(
            type=d["type"],
            source=d["source"],
            url=d.get("url") or "",
            date=d["date"],
            summary=d.get("summary") or "",
            scope=d["scope"],
            citation_kind=d["citation_kind"],
            owner_instrument_id=d["owner_instrument_id"],
            parent_fund_id=d.get("parent_fund_id"),
            constituent_key=d.get("constituent_key"),
            holding_weight_pct=d.get("holding_weight_pct"),
        )
        if expected_id is not None and expected_id != ev.citation_id:
            raise ValueError(
                f"citation_id mismatch: JSON has {expected_id!r} "
                f"but recomputed to {ev.citation_id!r} "
                f"(possible tampering of opportunity_report.json)"
            )
        return ev


@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str
    name_cn: str
    weight_pct: float
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str
    audit_errors: tuple[str, ...] = ()

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
    # Item 004: provider-computed 净资产收益率 (ROE), ratio units (0.18 = 18%),
    # sourced from the 盈利能力 section of stock_financial_abstract. Defaulted so
    # existing call sites + cached snapshots re-hydrate without churn. None when
    # the row is absent/NaN (ROE absence never fails the digest). Reason-only.
    roe: float | None = None


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
    # Item 001 (decision-confidence-followup): row-level evidence (NAV + announcements)
    # consumed by Policy B rule 2.5 (foreign-heavy short-circuit). Same shape as
    # FundLevelSnapshot.evidence: scope="instrument", owner_instrument_id=fund_id,
    # parent_fund_id=None, constituent_key=None. See ADR 0003 §7.
    fund_level_evidence: tuple[ThesisEvidence, ...] = ()


# ── Item 005: Fund-level types ────────────────────────────────────────────────

@dataclass(frozen=True)
class FundNavReport:
    """Fund-level NAV snapshot. `latest_nav_date` is ISO 8601 `str` — adapter
    converts AkShare's `datetime.date` via `.isoformat()`."""
    fund_id: str
    fund_name: str
    latest_nav: float
    latest_nav_date: str
    nav_history: tuple[tuple[str, float], ...]
    source_report_quarter: str

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundNavReport.fund_id must be non-empty")
        if self.latest_nav <= 0:
            raise ValueError(
                f"FundNavReport.latest_nav must be > 0; got {self.latest_nav}"
            )
        if not _ISO_DATE_RE.match(self.latest_nav_date):
            raise ValueError(
                f"FundNavReport.latest_nav_date must be ISO YYYY-MM-DD; "
                f"got {self.latest_nav_date!r}"
            )
        if not self.nav_history:
            raise ValueError("FundNavReport.nav_history must be non-empty")
        last_date, last_nav = self.nav_history[-1]
        if last_date != self.latest_nav_date:
            raise ValueError(
                f"FundNavReport.nav_history[-1][0]={last_date!r} must equal "
                f"latest_nav_date={self.latest_nav_date!r}"
            )
        if round(last_nav, 6) != round(self.latest_nav, 6):
            raise ValueError(
                f"FundNavReport.nav_history[-1][1]={last_nav} must equal "
                f"latest_nav={self.latest_nav} (to 6dp)"
            )
        if not _QUARTER_RE_FNR.match(self.source_report_quarter):
            raise ValueError(
                f"FundNavReport.source_report_quarter must match YYYYQ[1-4]; "
                f"got {self.source_report_quarter!r}"
            )


@dataclass(frozen=True)
class FundAnnouncement:
    """One fund-specific announcement. `date` is ISO 8601 `str` — adapter
    normalises AkShare's `datetime.date` via `.isoformat()`. `report_id` is
    the opaque `报告ID` provider reference (no URL column in AkShare 1.18.63's
    topic-specific announcement endpoints)."""
    fund_id: str
    title: str
    topic: Literal["dividend", "report", "personnel"]
    date: str
    report_id: str

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundAnnouncement.fund_id must be non-empty")
        if not self.title:
            raise ValueError("FundAnnouncement.title must be non-empty")
        if not self.report_id:
            raise ValueError("FundAnnouncement.report_id must be non-empty")
        if not _ISO_DATE_RE.match(self.date):
            raise ValueError(
                f"FundAnnouncement.date must be ISO YYYY-MM-DD; got {self.date!r}"
            )


@dataclass(frozen=True)
class FundLevelSnapshot:
    """Full per-fund result for non-active V1 asset classes (gold, cn_bond_fund,
    cn_etf, tracked CN ETFs). Distinct from `ActiveFundSnapshot` (per-constituent
    analyses) and `ConstituentSnapshot` (legacy display-only). The QDII sentinel
    case sets `nav_report=None, announcements=(), evidence=(), evidence_gaps=
    ("qdii_information_unavailable",)` and is NOT cached on disk (grill Q5).

    See ADR 0002 §5 (Fund-level engine).
    """
    fund_id: str
    nav_report: FundNavReport | None
    announcements: tuple[FundAnnouncement, ...]
    evidence: tuple[ThesisEvidence, ...]
    source_report_quarter: str
    cache_probed_at: str
    fund_level_failure_reasons: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.fund_id:
            raise ValueError("FundLevelSnapshot.fund_id must be non-empty")
