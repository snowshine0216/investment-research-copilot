from __future__ import annotations
from irc.news.topic_classifier import classify_topic, TOPICS


def test_topics_set():
    assert set(TOPICS) == {
        "us_monetary", "us_fiscal_politics",
        "cn_monetary", "cn_equity_property_policy",
        "geopolitics", "gold_specific", "holdings_sector",
    }


def test_keyword_routing():
    assert classify_topic("FOMC minutes show ...", url="federalreserve.gov") == "us_monetary"
    assert classify_topic("PBoC reverse repo of ...", url="pbc.gov.cn") == "cn_monetary"
    assert classify_topic("World Gold Council Q1 ...", url="gold.org") == "gold_specific"
    assert classify_topic("Russia-Ukraine ...", url="reuters.com") == "geopolitics"


def test_default_falls_back_to_none():
    assert classify_topic("ABC announces ...", url="generic.com") is None
