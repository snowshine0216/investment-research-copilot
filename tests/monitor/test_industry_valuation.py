from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from irc.monitor.industry_valuation import (
    parse_industry_pe,
    parse_stock_industry,
    fetch_industry_pe,
    fetch_stock_industry_map,
)


def test_parse_industry_pe_extracts_name_to_pe():
    df = pd.DataFrame({"板块名称": ["银行", "白酒"], "市盈率": ["6.5", "30.2"]})
    out = parse_industry_pe(df)
    assert out == {"银行": 6.5, "白酒": 30.2}


def test_parse_industry_pe_drops_nonpositive_and_nan():
    df = pd.DataFrame({"板块名称": ["亏损业", "正常业", "空值业"],
                       "市盈率": ["-12.0", "10.0", "nan"]})
    out = parse_industry_pe(df)
    assert out == {"正常业": 10.0}  # non-positive + NaN dropped


def test_parse_industry_pe_unexpected_shape_is_empty():
    assert parse_industry_pe(None) == {}
    assert parse_industry_pe(pd.DataFrame()) == {}
    assert parse_industry_pe(pd.DataFrame({"x": [1]})) == {}
