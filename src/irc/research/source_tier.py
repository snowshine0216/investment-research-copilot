"""Source-quality tiering for research citations.

Adversarial review §A5 (2026-05-19): a NYT/Reuters/ISW geopolitics
citation is currently weighted identically to ``我的钢铁网`` republishing
a PBOC press release. This module classifies a URL into a small set of
ordered tiers so downstream consumers (thesis evidence selection, memo
synthesizer, audit gate) can prefer primary/wire/paper sources over
republishers and unknown blogs.

Pure functions. No I/O. No regex on free text — just hostname matching.
"""
from __future__ import annotations

from enum import IntEnum
from urllib.parse import urlparse


class SourceTier(IntEnum):
    """Lower = more authoritative.

    PRIMARY      regulators, central banks, exchanges, official statistics
    WIRE         tier-1 wire services and primary-research desks
    PAPER        named tier-1 newspapers and financial periodicals
    REPUBLISHER  aggregators / portals that just republish wire feeds
    UNKNOWN      everything else (default for unfamiliar hosts)
    """

    PRIMARY = 1
    WIRE = 2
    PAPER = 3
    REPUBLISHER = 4
    UNKNOWN = 5


# Regulators, central banks, exchanges, official statistics offices.
_PRIMARY_HOSTS: frozenset[str] = frozenset({
    # CN regulators / official
    "pbc.gov.cn", "csrc.gov.cn", "mof.gov.cn", "stats.gov.cn",
    "ndrc.gov.cn", "cbirc.gov.cn", "safe.gov.cn",
    # US / global regulators and central banks
    "federalreserve.gov", "sec.gov", "treasury.gov",
    "ecb.europa.eu", "bankofengland.co.uk", "boj.or.jp",
    "imf.org", "bis.org", "worldbank.org", "oecd.org",
    # Exchanges
    "sse.com.cn", "szse.cn", "hkex.com.hk",
    "nyse.com", "nasdaq.com", "cboe.com", "cmegroup.com",
})

# Wire services and primary-research outlets (rated tier 2 because their
# editorial pipeline still adds interpretation on top of the source).
_WIRE_HOSTS: frozenset[str] = frozenset({
    "reuters.com", "bloomberg.com", "ap.org", "apnews.com",
    "xinhuanet.com", "news.xinhuanet.com", "people.com.cn",
    "kitco.com", "marketwatch.com", "investopedia.com",
    "isw.pub", "kyivindependent.com",
    "politico.com", "abfjournal.com",
})

# Named tier-1 newspapers / financial periodicals.
_PAPER_HOSTS: frozenset[str] = frozenset({
    "nytimes.com", "wsj.com", "ft.com", "economist.com",
    "theguardian.com", "washingtonpost.com",
    "21jingji.com", "jiemian.com", "caixin.com", "yicai.com",
    "stcn.com", "cs.com.cn", "cnstock.com",
    "newsweek.com", "forbes.com",
})

# Republishers / aggregators / data portals — content usually originates
# elsewhere; the URL adds no source diversity.
_REPUBLISHER_HOSTS: frozenset[str] = frozenset({
    "sina.com.cn", "cj.sina.com.cn", "finance.sina.com.cn",
    "163.com", "m.163.com",
    "mysteel.com", "news.mysteel.com", "tks.mysteel.com",
    "eastmoney.com", "data.eastmoney.com",
    "chinabgao.com", "m.chinabgao.com",
    "xyhndec.cn", "qiqiboke.com",
    "tradingview.com", "marketscreener.com",
    "bitget.com",
    "epaper.cs.com.cn", "epaper.stcn.com",
})


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _matches(host: str, table: frozenset[str]) -> bool:
    """A host matches the table when it is exactly listed OR a strict
    subdomain of a listed entry. ``news.mysteel.com`` matches
    ``mysteel.com`` AND ``news.mysteel.com``; ``mysteelxyz.com`` does
    NOT match ``mysteel.com``."""
    if host in table:
        return True
    return any(host.endswith("." + h) for h in table)


def classify(url: str) -> SourceTier:
    """Map a URL to a SourceTier. Pure.

    Order of precedence: PRIMARY → WIRE → PAPER → REPUBLISHER → UNKNOWN.
    Hosts unknown to the tables default to UNKNOWN — the caller decides
    whether to keep, demote, or drop UNKNOWN-tier evidence.
    """
    host = _normalize_host(url)
    if not host:
        return SourceTier.UNKNOWN
    if _matches(host, _PRIMARY_HOSTS):
        return SourceTier.PRIMARY
    if _matches(host, _WIRE_HOSTS):
        return SourceTier.WIRE
    if _matches(host, _PAPER_HOSTS):
        return SourceTier.PAPER
    if _matches(host, _REPUBLISHER_HOSTS):
        return SourceTier.REPUBLISHER
    return SourceTier.UNKNOWN


def is_trusted(tier: SourceTier) -> bool:
    """A citation is 'trusted' when its tier is PAPER-or-better.
    REPUBLISHER and UNKNOWN flow through as evidence but must NOT be
    sufficient on their own for state changes like thesis_state=intact.
    """
    return tier <= SourceTier.PAPER
