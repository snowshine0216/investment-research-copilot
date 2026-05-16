from __future__ import annotations

from irc.opportunity.sector_proxy import proxy_target_for_theme


def test_known_proxies_return_canonical_target():
    assert proxy_target_for_theme("dividend") == "中证红利"
    assert proxy_target_for_theme("broad") == "沪深300"


def test_unmapped_theme_returns_none():
    assert proxy_target_for_theme("semiconductor") is None
    assert proxy_target_for_theme("healthcare") is None
    assert proxy_target_for_theme("tech") is None
    assert proxy_target_for_theme(None) is None
    assert proxy_target_for_theme("") is None
