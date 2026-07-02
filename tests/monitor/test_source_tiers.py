from __future__ import annotations
from irc.monitor.source_tiers import SourceTiers, classify, tiers_from_config


def _tiers():
    return SourceTiers(
        blocked=("facebook.com", "x.com", "twitter.com", "reddit.com",
                  "letsdatascience.com", "mezha.net"),
        tier1=("reuters.com", "bloomberg.com", "xinhuanet.com", "gov.cn", "pbc.gov.cn"),
        tier2=("cnbc.com", "ft.com", "wsj.com", "kitco.com", "mining.com",
                "axios.com", "eastmoney.com"),
    )


def test_classify_blocked_domain():
    assert classify("facebook.com", _tiers()) == "blocked"


def test_classify_tier1_exact():
    assert classify("reuters.com", _tiers()) == 1


def test_classify_tier2_exact():
    assert classify("eastmoney.com", _tiers()) == 2


def test_classify_unknown_is_tier3():
    assert classify("some-new-blog.example", _tiers()) == 3


def test_classify_subdomain_inherits_tier1():
    assert classify("cn.reuters.com", _tiers()) == 1


def test_classify_subdomain_inherits_blocked():
    assert classify("m.facebook.com", _tiers()) == "blocked"


def test_classify_subdomain_does_not_match_substring():
    # "notreuters.com" must NOT match "reuters.com" (suffix match on labels,
    # not substring match)
    assert classify("notreuters.com", _tiers()) == 3


def test_classify_empty_domain_is_tier3():
    assert classify("", _tiers()) == 3
    assert classify("   ", _tiers()) == 3


def test_classify_case_insensitive():
    assert classify("REUTERS.COM", _tiers()) == 1


def test_tiers_from_config_malformed_none_is_all_tier3():
    tiers = tiers_from_config(None)
    assert classify("reuters.com", tiers) == 3
    assert classify("facebook.com", tiers) == 3


def test_tiers_from_config_malformed_empty_dict_is_all_tier3():
    tiers = tiers_from_config({})
    assert classify("anything.com", tiers) == 3


def test_tiers_from_config_well_formed():
    raw = {"blocked": ["facebook.com"], "tier1": ["reuters.com"], "tier2": ["ft.com"]}
    tiers = tiers_from_config(raw)
    assert classify("facebook.com", tiers) == "blocked"
    assert classify("reuters.com", tiers) == 1
    assert classify("ft.com", tiers) == 2
    assert classify("unknown.com", tiers) == 3


def test_tiers_from_config_partial_missing_keys_defaults_empty():
    raw = {"tier1": ["reuters.com"]}   # blocked/tier2 absent
    tiers = tiers_from_config(raw)
    assert classify("reuters.com", tiers) == 1
    assert classify("anything-else.com", tiers) == 3


def test_monitor_config_parses_source_tiers_section():
    from irc.schemas.monitor import MonitorConfig
    raw = {
        "schema_version": 1,
        "funds": [{"id": "008986", "name_cn": "x", "market": "cn_off_exchange",
                   "analysis_profile": "gold", "themes": ["gold_drivers"]}],
        "source_tiers": {
            "blocked": ["facebook.com"], "tier1": ["reuters.com"], "tier2": ["ft.com"],
        },
    }
    cfg = MonitorConfig(**raw)
    assert cfg.source_tiers.blocked == ("facebook.com",)
    assert cfg.source_tiers.tier1 == ("reuters.com",)
    assert cfg.source_tiers.tier2 == ("ft.com",)


def test_monitor_config_source_tiers_defaults_when_absent():
    from irc.schemas.monitor import MonitorConfig
    raw = {
        "schema_version": 1,
        "funds": [{"id": "008986", "name_cn": "x", "market": "cn_off_exchange",
                   "analysis_profile": "gold", "themes": ["gold_drivers"]}],
    }
    cfg = MonitorConfig(**raw)
    assert cfg.source_tiers.blocked == ()
    assert cfg.source_tiers.tier1 == ()
    assert cfg.source_tiers.tier2 == ()
