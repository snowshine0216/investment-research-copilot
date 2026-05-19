# 004 — Source quality tiering

## Why

The adversarial review (§A5) notes a NYT/Reuters/ISW citation is
currently weighted identically to `我的钢铁网` republishing a PBOC press
release. Real frameworks tier sources: primary regulator/exchange →
tier-1 wire → tier-1 paper → republisher/blog/forum.

## What changes

1. New module `src/irc/research/source_tier.py`:

```python
from __future__ import annotations
from enum import IntEnum
from urllib.parse import urlparse


class SourceTier(IntEnum):
    PRIMARY = 1      # regulator, central bank, exchange, gov
    WIRE = 2         # Reuters, Bloomberg, Xinhua, AP, ISW
    PAPER = 3        # NYT, FT, WSJ, 21jingji, jiemian, caixin
    REPUBLISHER = 4  # aggregators that just republish (sina cj, 163 dy, mysteel)
    UNKNOWN = 5      # everything else


_PRIMARY_HOSTS: frozenset[str] = frozenset({
    "pbc.gov.cn", "csrc.gov.cn", "mof.gov.cn", "stats.gov.cn",
    "federalreserve.gov", "sec.gov", "treasury.gov", "ecb.europa.eu",
    "imf.org", "bis.org",
    "sse.com.cn", "szse.cn", "hkex.com.hk", "nyse.com", "nasdaq.com",
})

_WIRE_HOSTS: frozenset[str] = frozenset({
    "reuters.com", "bloomberg.com", "ap.org", "apnews.com",
    "xinhuanet.com", "news.xinhuanet.com",
    "kitco.com", "marketwatch.com",
    "isw.pub", "kyivindependent.com",
})

_PAPER_HOSTS: frozenset[str] = frozenset({
    "nytimes.com", "wsj.com", "ft.com", "economist.com",
    "21jingji.com", "jiemian.com", "caixin.com", "yicai.com",
    "stcn.com", "cs.com.cn", "cnstock.com",
})

_REPUBLISHER_HOSTS: frozenset[str] = frozenset({
    "sina.com.cn", "cj.sina.com.cn", "163.com", "m.163.com",
    "mysteel.com", "news.mysteel.com", "tks.mysteel.com",
    "eastmoney.com", "data.eastmoney.com",
    "chinabgao.com", "m.chinabgao.com",
    "xyhndec.cn", "qiqiboke.com",
})


def classify(url: str) -> SourceTier:
    """Pure: map a URL to a SourceTier."""
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # match longest known suffix
    for table, tier in (
        (_PRIMARY_HOSTS, SourceTier.PRIMARY),
        (_WIRE_HOSTS, SourceTier.WIRE),
        (_PAPER_HOSTS, SourceTier.PAPER),
        (_REPUBLISHER_HOSTS, SourceTier.REPUBLISHER),
    ):
        if any(host == h or host.endswith("." + h) for h in table):
            return tier
    return SourceTier.UNKNOWN
```

2. In `src/irc/research/theme_research.py`, attach the tier to each
   `Citation` (extend the dataclass with `tier: SourceTier`).
3. In `src/irc/opportunity/thesis_evidence.py`, when building
   `thesis_evidence` from news sources, prefer lower-tier (better) URLs;
   demote `REPUBLISHER` and `UNKNOWN` to evidence-only-with-warning.

## Acceptance criteria

- `classify("https://www.reuters.com/...")` → `WIRE`.
- `classify("https://news.mysteel.com/...")` → `REPUBLISHER`.
- `classify("https://www.pbc.gov.cn/...")` → `PRIMARY`.
- `Citation` carries a `tier` field; thesis_evidence selection prefers
  lower-tier numbers.

## Tests to add

- `tests/research/test_source_tier.py`: 6+ host classifications covering
  each tier and the UNKNOWN fallback.
