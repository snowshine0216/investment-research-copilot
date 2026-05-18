from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.trades.venue_check import check_venue, VenueCheckResult


def _u(items: list[dict]) -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": items})


def test_compatible_when_user_has_required_venue():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["us_brokerage"],
                      universe=universe)
    assert isinstance(out, VenueCheckResult)
    assert out.compatible is True
    assert out.proxy_id is None


def test_incompatible_with_proxy_suggestion():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund", "cmb_gold"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "006075"


def test_no_proxy_available():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "Russell 2000", "venue_required": ["us_brokerage"]},
    ])
    out = check_venue(instrument_id="VTI", available_venues=["cmb_fund"],
                      universe=universe)
    assert out.compatible is False
    assert out.proxy_id is None


def test_cn_etf_proxied_by_cn_equity_fund_with_same_tracked_index():
    """A-share index ETFs can be proxied via off-exchange index funds tracking
    the same benchmark — this is the canonical CMB-bank-only setup."""
    universe = _u([
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "华泰柏瑞沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "嘉实沪深300指数研究增强A", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510300",
                      available_venues=["cmb_fund", "cmb_gold"], universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "OFF300"


def test_us_etf_proxied_by_cn_equity_fund_qdii_with_same_index():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "QDII500", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "cn_equity_fund", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="VTI",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id == "QDII500"


def test_bond_fund_does_not_get_cross_class_proxy():
    """Active bond funds are NOT substitutable across asset_classes —
    the cross-class relaxation only applies to index-tracked equity ETFs."""
    universe = _u([
        {"instrument_id": "111111", "ticker": "111111", "market": "cn_off_exchange",
         "name_cn": "纯债基金A", "asset_class": "cn_bond_fund", "currency": "cny",
         "venue_required": ["cn_brokerage"]},
        # A cn_equity_fund exists, but it's a different asset_class and has no
        # matching tracked_index, so it must NOT be offered as a proxy.
        {"instrument_id": "OTHEREQ", "ticker": "OTHEREQ", "market": "cn_off_exchange",
         "name_cn": "其他基金", "asset_class": "cn_equity_fund", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="111111",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None


def test_cross_class_proxy_requires_matching_tracked_index():
    """Even within the allow-list, the tracked_index MUST match — we don't
    silently substitute a CSI300 fund for an SSE50 ETF."""
    universe = _u([
        {"instrument_id": "510050", "ticker": "510050", "market": "cn_on_exchange",
         "name_cn": "上证50ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "上证50", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "沪深300指数基金", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510050",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None


def test_cross_class_proxy_requires_target_to_be_index_tracked():
    """An equity ETF with no tracked_index (rare, but possible) must NOT
    silently substitute a tracked fund — same-class match still applies."""
    universe = _u([
        {"instrument_id": "WEIRD", "ticker": "WEIRD", "market": "cn_on_exchange",
         "name_cn": "未定指数ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "沪深300指数基金", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="WEIRD",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None


def test_hk_etf_proxied_by_cn_equity_fund_qdii_with_same_index():
    """hk_etf is the third asset_class in the substitution dict — pin it."""
    universe = _u([
        {"instrument_id": "2800", "ticker": "2800", "market": "hk_on_exchange",
         "name_cn": "盈富基金", "asset_class": "hk_etf", "currency": "hkd",
         "tracked_index": "Hang Seng", "venue_required": ["hk_brokerage"]},
        {"instrument_id": "QDIIHK", "ticker": "QDIIHK", "market": "cn_off_exchange",
         "name_cn": "恒生指数QDII", "asset_class": "cn_equity_fund", "currency": "cny",
         "tracked_index": "Hang Seng", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="2800",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id == "QDIIHK"


def test_gold_etf_proxied_by_paper_gold_without_tracked_index_match():
    """Gold instruments don't share a tracked_index (paper gold has none,
    ETFs typically reference SHFE Au99.99). For gold targets the proxy
    rule drops the tracked_index equality check while keeping the
    same-asset_class constraint. See
    docs/2026-05-18-fix-memo-audit/items/010-spec.md.
    """
    universe = _u([
        {"instrument_id": "518880", "ticker": "518880", "market": "cn_on_exchange",
         "name_cn": "黄金ETF华安", "asset_class": "gold", "currency": "cny",
         "tracked_index": "SHFE Au99.99", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "cmb_paper_gold", "ticker": "CMB_AU", "market": "cmb_internal",
         "name_cn": "招商银行账户金", "asset_class": "gold", "currency": "cny",
         "venue_required": ["cmb_gold"]},  # no tracked_index
    ])
    out = check_venue(instrument_id="518880",
                      available_venues=["cmb_gold"], universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "cmb_paper_gold"
    assert "招商银行账户金" in out.note


def test_non_gold_relaxation_does_not_bleed_into_other_classes():
    """The gold-only tracked_index relaxation must NOT apply to cn_etf
    even when no tracked_index match exists. (Defensive regression — the
    earlier strict-equality check at this position remains required.)"""
    universe = _u([
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "华泰柏瑞沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
        # An off-exchange fund with NO tracked_index. Must NOT proxy.
        {"instrument_id": "OFFNOIDX", "ticker": "OFFNOIDX", "market": "cn_off_exchange",
         "name_cn": "无指数基金", "asset_class": "cn_etf", "currency": "cny",
         "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510300",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None  # gold relaxation didn't leak here


def test_proxy_note_includes_asset_class_when_cross_class():
    """The VenueCheckResult.note should expose the proxy's asset_class so a
    human reading decision_report.md can tell same-class from cross-class."""
    universe = _u([
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "华泰柏瑞沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "嘉实沪深300指数研究增强A", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510300",
                      available_venues=["cmb_fund", "cmb_gold"], universe=universe)
    assert out.proxy_id == "OFF300"
    assert "cn_equity_fund" in out.note
