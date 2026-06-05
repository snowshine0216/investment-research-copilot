from __future__ import annotations

from irc.opportunity.sector_indices import (
    SECTOR_INDEX_DISPLAY,
    SECTOR_INDEX_KEYS,
    SECTOR_NAME_TO_SLUG,
)
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

_QDII_US_ALIASES: dict[str, str] = {
    "s&p500": "sp500", "s&p 500": "sp500", "sp500": "sp500", "spx": "sp500", "标普500": "sp500",
    "nasdaq100": "nasdaq100", "nasdaq 100": "nasdaq100", "ndx": "nasdaq100", "纳斯达克100": "nasdaq100",
    "dow jones": "dow_jones", "dow": "dow_jones", "道琼斯": "dow_jones",
}

_QDII_HK_ALIASES: dict[str, str] = {
    "hstech": "hstech", "恒生科技": "hstech", "hs tech": "hstech",
    "hsi": "hsi", "恒生指数": "hsi", "hang seng": "hsi",
    "hs_dividend": "hs_dividend", "港股红利": "hs_dividend",
    "china_internet": "china_internet", "中概互联": "china_internet",
}

_BROAD_INDEX_KEYS: frozenset[str] = frozenset(_BROAD_INDEX_DISPLAY.keys())

# Sector-index maps come from the single source-of-truth catalog
# (opportunity/sector_indices.py) — 17 slugs (14 new + 3 folded-in metals).
# Re-bound here under the legacy private names so existing importers
# (inputs_loader, akshare_index_valuation, ingest_cmd, tests) stay valid.
_SECTOR_INDEX_DISPLAY: dict[str, str] = SECTOR_INDEX_DISPLAY
_SECTOR_INDEX_KEYS: frozenset[str] = SECTOR_INDEX_KEYS

# Inversion (中文/lowercased name or alias -> slug). Broad display names are
# deliberately NOT inverted here (broad re-activation is a separate opt-in).
_INDEX_NAME_TO_SLUG: dict[str, str] = dict(SECTOR_NAME_TO_SLUG)

# The full valuation key-set the inputs loader tests membership against — the
# union of broad (#102) and sector. Overloading "broad" is avoided.
_INDEX_VALUATION_KEYS: frozenset[str] = _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS

_QDII_US_KEYS: frozenset[str] = frozenset(_QDII_US_DISPLAY.keys())
_QDII_HK_KEYS: frozenset[str] = frozenset(_QDII_HK_DISPLAY.keys())

# Canonical set of QDII lookthrough kinds (used by narrative autobuild + analyze).
QDII_KINDS: tuple[str, ...] = ("qdii_us", "qdii_hk", "qdii_global")


def _normalize_qdii_key(raw: str, aliases: dict[str, str]) -> str | None:
    """Try to match raw (already lowercased) against known aliases."""
    if raw in aliases:
        return aliases[raw]
    no_spaces = raw.replace(" ", "")
    if no_spaces in aliases:
        return aliases[no_spaces]
    return None


def _display_for(key: str, table: dict[str, str], fallback: str) -> str:
    return table.get(key, fallback)


def map_lookthrough(inp: OpportunityInput) -> LookthroughTarget:
    """Map an instrument to its underlying-exposure target.

    Active funds always route to `active_fund` regardless of theme/tracked_index.
    Other asset classes preserve the legacy ordering.
    """
    # Item 003: cn_equity_fund always routes to active_fund FIRST — before
    # tracked_index or theme checks so themed active funds don't mis-route.
    if inp.asset_class == "cn_equity_fund":
        return LookthroughTarget(
            kind="active_fund",
            key=f"fund_{inp.instrument_id}",
            display_cn=inp.name_cn,
            provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "gold":
        return LookthroughTarget(
            "gold", "gold", "黄金", provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "cn_bond_fund":
        return LookthroughTarget(
            "bond", "cn_bond", "中国债券", provider_symbol=inp.instrument_id,
        )

    tracked = (inp.tracked_index or "").strip().lower() or None
    theme = (inp.theme or "").strip().lower() or None

    if inp.asset_class == "us_etf":
        raw = tracked or theme or "us_equity"
        key = _normalize_qdii_key(raw, _QDII_US_ALIASES) or raw
        # Item 016 — populate provider_symbol so the snapshot dispatch can
        # route to `_build_fund_level_snapshot` (NAV + announcements via
        # the CN AkShare endpoints these QDII funds are registered under).
        return LookthroughTarget(
            "qdii_us", key, _display_for(key, _QDII_US_DISPLAY, key),
            provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "hk_etf":
        raw = tracked or theme or "hsi"
        key = _normalize_qdii_key(raw, _QDII_HK_ALIASES) or raw
        return LookthroughTarget(
            "qdii_hk", key, _display_for(key, _QDII_HK_DISPLAY, key),
            provider_symbol=inp.instrument_id,
        )

    if inp.asset_class == "qdii_global":
        raw = tracked or theme or "global_equity"
        return LookthroughTarget(
            "qdii_global", raw, raw,
            provider_symbol=inp.instrument_id,
        )

    if tracked is not None:
        if tracked in _BROAD_INDEX_KEYS:
            return LookthroughTarget(
                "broad_index", tracked, _BROAD_INDEX_DISPLAY[tracked],
                provider_symbol=inp.instrument_id,
            )
        if tracked in _QDII_US_KEYS:
            # Item 016 — QDII rows now dispatch to fund-level snapshot
            # (was: hard-coded sentinel skip).
            return LookthroughTarget(
                "qdii_us", tracked, _QDII_US_DISPLAY[tracked],
                provider_symbol=inp.instrument_id,
            )
        if tracked in _QDII_HK_KEYS:
            return LookthroughTarget(
                "qdii_hk", tracked, _QDII_HK_DISPLAY[tracked],
                provider_symbol=inp.instrument_id,
            )
        # Unknown index: classify as broad_index but keep the raw key + provider_symbol.
        return LookthroughTarget(
            "broad_index", tracked, tracked, provider_symbol=inp.instrument_id,
        )

    if theme is not None and theme in _SECTOR_THEME_DISPLAY and theme not in ("broad",):
        return LookthroughTarget(
            "sector_theme", theme, _SECTOR_THEME_DISPLAY[theme],
            provider_symbol=inp.instrument_id,
        )

    return LookthroughTarget("broad_index", "unknown", "未知底层")
