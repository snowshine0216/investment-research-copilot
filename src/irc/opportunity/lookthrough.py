from __future__ import annotations

from irc.opportunity.types import LookthroughTarget, OpportunityInput


_BROAD_INDEX_DISPLAY: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "csi_a500": "中证A500",
    "sse50": "上证50",
    "star50": "科创50",
    "chinext": "创业板",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "红利低波",
}

_SECTOR_THEME_DISPLAY: dict[str, str] = {
    "semiconductor": "半导体",
    "tech": "科技",
    "healthcare": "医药",
    "new_energy": "新能源",
    "consumer": "消费",
    "finance": "金融",
    "defense": "军工",
    "metals": "有色金属",
    "real_estate": "房地产",
    "soe": "国企改革",
    "dividend": "红利",
    "broad": "宽基",
}

_QDII_US_DISPLAY: dict[str, str] = {
    "nasdaq100": "纳斯达克100",
    "sp500": "标普500",
    "dow_jones": "道琼斯",
    "us50": "美国50",
    "us_equity": "美股大盘",
}

_QDII_HK_DISPLAY: dict[str, str] = {
    "hstech": "恒生科技",
    "hsi": "恒生指数",
    "hs_dividend": "港股红利",
    "china_internet": "中概互联",
}

_BROAD_INDEX_KEYS: frozenset[str] = frozenset(_BROAD_INDEX_DISPLAY.keys())
_QDII_US_KEYS: frozenset[str] = frozenset(_QDII_US_DISPLAY.keys())
_QDII_HK_KEYS: frozenset[str] = frozenset(_QDII_HK_DISPLAY.keys())


def _display_for(key: str, table: dict[str, str], fallback: str) -> str:
    return table.get(key, fallback)


def map_lookthrough(inp: OpportunityInput) -> LookthroughTarget:
    """Map an instrument to its underlying-exposure target.

    Order of precedence: tracked_index → theme → asset_class fallback.
    Missing or unknown values fall back deterministically; this function
    never raises on unrecognised input.
    """
    if inp.asset_class == "gold":
        return LookthroughTarget("gold", "gold", "黄金")

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget("bond", "cn_bond", "中国债券")

    tracked = (inp.tracked_index or "").strip().lower() or None
    theme = (inp.theme or "").strip().lower() or None

    if inp.asset_class == "us_etf":
        key = tracked or theme or "us_equity"
        return LookthroughTarget(
            "qdii_us", key, _display_for(key, _QDII_US_DISPLAY, key),
        )

    if inp.asset_class == "hk_etf":
        key = tracked or theme or "hsi"
        return LookthroughTarget(
            "qdii_hk", key, _display_for(key, _QDII_HK_DISPLAY, key),
        )

    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget("broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked])
        if tracked in _QDII_US_KEYS:
            return LookthroughTarget("qdii_us", tracked, _QDII_US_DISPLAY[tracked])
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget("qdii_hk", tracked, _QDII_HK_DISPLAY[tracked])
        # Unknown index: classify as broad_index but keep the raw key
        return LookthroughTarget("broad_index", tracked, tracked)

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget("sector_theme", theme, _SECTOR_THEME_DISPLAY[theme])

    if inp.asset_class == "cn_equity_fund":
        return LookthroughTarget("active_fund", "active_cn_equity", "主动权益")

    return LookthroughTarget("broad_index", "unknown", "未知底层")
