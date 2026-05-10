from __future__ import annotations
from typing import Final


TOPICS: Final[tuple[str, ...]] = (
    "us_monetary", "us_fiscal_politics",
    "cn_monetary", "cn_equity_property_policy",
    "geopolitics", "gold_specific", "holdings_sector",
)


_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("us_monetary", ("federalreserve.gov", "fomc", "powell", "fred", "fedwatch")),
    ("us_fiscal_politics", ("treasury.gov", "congress", "debt ceiling", "election")),
    ("cn_monetary", ("pbc.gov.cn", "pboc", "央行", "公开市场", "mlf")),
    ("cn_equity_property_policy", ("csrc", "证监会", "银保监", "财政部", "房地产")),
    ("geopolitics", ("isw", "cfr.org", "russia-ukraine", "中东", "台海", "geopolit")),
    ("gold_specific", ("gold.org", "world gold council", "wgc", "lbma", "kitco", "shfe")),
)


def classify_topic(text: str, url: str = "") -> str | None:
    blob = (text + " " + url).lower()
    for topic, kws in _RULES:
        if any(k in blob for k in kws):
            return topic
    return None
