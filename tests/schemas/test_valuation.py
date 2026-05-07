from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.valuation import ValuationBucketsConfig


def test_buckets_must_be_ordered():
    raw = {
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly", "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow", "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold", "granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
        ]
    }
    cfg = ValuationBucketsConfig.model_validate(raw)
    assert cfg.buckets[0].max_percentile == 0.30


def test_buckets_disordered_fails():
    raw = {
        "buckets": [
            {"max_percentile": 0.60, "buy_method": "lump_sum", "granularity": "x"},
            {"max_percentile": 0.30, "buy_method": "dca_weekly", "granularity": "x"},
        ]
    }
    with pytest.raises(ValidationError, match="ascending"):
        ValuationBucketsConfig.model_validate(raw)
