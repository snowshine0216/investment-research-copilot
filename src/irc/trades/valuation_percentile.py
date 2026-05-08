from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.valuation import ValuationBucketsConfig


@dataclass(frozen=True)
class BucketChoice:
    buy_method: str
    granularity: str
    bucket_max_percentile: float


def method_for_percentile(percentile: float, cfg: ValuationBucketsConfig) -> BucketChoice:
    """Find the smallest bucket whose max_percentile >= percentile."""
    for b in cfg.buckets:
        if percentile <= b.max_percentile:
            return BucketChoice(
                buy_method=b.buy_method, granularity=b.granularity,
                bucket_max_percentile=b.max_percentile,
            )
    last = cfg.buckets[-1]
    return BucketChoice(
        buy_method=last.buy_method, granularity=last.granularity,
        bucket_max_percentile=last.max_percentile,
    )
