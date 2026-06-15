from irc.monitor.types import MonitorFund
from irc.monitor.snapshot_targets import target_for_fund


def _fund(profile, fid="000000"):
    return MonitorFund(
        id=fid,
        name_cn="x",
        market="cn_off_exchange",
        analysis_profile=profile,
        themes=(),
        constituent_news=False,
        weights={"trend": 1.0},
        bands={"buy": 0.4, "sell": -0.4},
        minimum_confidence=0.5,
    )


def test_active_cn_equity_maps_to_active_fund():
    t = target_for_fund(_fund("active_cn_equity", "519069"))
    assert t.kind == "active_fund" and t.provider_symbol == "519069"
    assert t.kind != "broad_index"


def test_gold_maps_to_gold_kind_fund_level():
    t = target_for_fund(_fund("gold", "008986"))
    assert t.kind == "gold" and t.provider_symbol == "008986"


def test_qdii_global_maps_to_qdii_global():
    t = target_for_fund(_fund("qdii_global", "270023"))
    assert t.kind == "qdii_global" and t.provider_symbol == "270023"


def test_qdii_china_us_internet_maps_to_fund_level_kind():
    t = target_for_fund(_fund("qdii_china_us_internet", "009225"))
    # index-tracking QDII registered as a CN fund: route to a fund-level kind with
    # provider_symbol so build_snapshot fetches NAV + announcements (not the us_etf alias).
    assert t.provider_symbol == "009225" and t.kind in (
        "qdii_us", "gold", "broad_index", "qdii_global"
    )
    assert t.kind != "active_fund"


def test_all_7_funds_map_to_typed_targets_never_broad_index():
    """All 7 monitor fund ids produce typed targets; none maps to broad_index."""
    fund_profiles = [
        ("008986", "gold"),
        ("270023", "qdii_global"),
        ("519069", "active_cn_equity"),
        ("260112", "active_cn_equity"),
        ("006533", "active_cn_equity"),
        ("009225", "qdii_china_us_internet"),
        ("000083", "active_cn_equity"),
    ]
    for fid, profile in fund_profiles:
        t = target_for_fund(_fund(profile, fid))
        assert t.provider_symbol == fid, f"{fid}: provider_symbol mismatch"
        assert t.kind != "broad_index", f"{fid}: must not map to broad_index"
        assert t.kind in (
            "active_fund", "gold", "qdii_global", "qdii_us", "qdii_hk",
        ), f"{fid}: unexpected kind {t.kind!r}"
