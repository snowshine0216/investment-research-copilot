from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from irc.schemas.universe import Instrument


@dataclass(frozen=True)
class CatalogFund:
    fund_code: str
    fund_name: str
    fund_type: str


@dataclass(frozen=True)
class ClassifiedFund:
    catalog: CatalogFund
    asset_class: str
    market: str
    currency: str
    tracked_index: str | None
    theme: str | None
    venue_required: tuple[str, ...]


@dataclass(frozen=True)
class UniverseBuildOptions:
    active_broad_cap: int = 40
    theme_cap: int = 20
    bond_cap: int = 40
    cn_etf_cap: int = 80
    us_qdii_cap: int = 40
    hk_qdii_cap: int = 40
    qdii_global_cap: int = 30


THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("semiconductor", ("半导体", "芯片", "集成电路")),
    ("new_energy", ("新能源", "光伏", "电池", "储能", "电动车")),
    ("healthcare", ("医疗", "医药", "创新药", "中药", "生物")),
    ("consumer", ("消费", "食品饮料", "食品", "饮料", "白酒", "酒", "家电")),
    ("defense", ("军工", "国防", "航天")),
    ("finance", ("银行", "券商", "证券", "金融")),
    ("metals", ("有色", "金属", "化工", "资源")),
    ("real_estate", ("地产", "房地产")),
    ("soe", ("央企", "国企", "国资")),
    ("dividend", ("红利", "股息", "低波")),
    ("tech", ("科技", "信息技术", "互联网", "软件", "通信", "AI", "人工智能")),
    ("broad", ("沪深300", "中证500", "中证1000", "上证50", "A500", "创业板", "科创50", "宽基")),
)

_EXCLUDED_TERMS = (
    "货币", "现金", "短债", "超短债", "现金管理", "FOF", "基金中基金",
    "清算", "终止", "退市", "异常", "暂停运作",
)
_ETF_MARKERS = ("ETF", "交易型开放式", "交易开放式", "场内")
_US_MARKERS = ("标普", "S&P", "纳斯达克", "纳指", "NASDAQ", "道琼斯", "DOW", "美国")
_HK_MARKERS = ("恒生", "港股", "香港", "H股", "中概互联", "中概互联网")
_EQUITY_TYPE_MARKERS = ("股票", "混合", "指数", "QDII")
_BOND_MARKERS = ("债券", "纯债", "信用债", "国债", "政金债", "可转债", "债")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_catalog_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[CatalogFund, ...]:
    normalized: list[CatalogFund] = []
    for row in rows:
        fund_code = _text(row.get("fund_code"))
        fund_name = _text(row.get("fund_name"))
        fund_type = _text(row.get("fund_type")) or ""
        if not fund_code or not fund_name:
            continue
        normalized.append(CatalogFund(fund_code=fund_code.zfill(6), fund_name=fund_name, fund_type=fund_type))
    return tuple(normalized)


def infer_theme(fund_name: str, fund_type: str) -> str | None:
    text = f"{fund_name} {fund_type}"
    text_upper = text.upper()
    for theme, keywords in THEME_KEYWORDS:
        if any(keyword.upper() in text_upper for keyword in keywords):
            return theme
    return None


def _is_excluded(fund: CatalogFund) -> bool:
    text = f"{fund.fund_name} {fund.fund_type}".upper()
    return any(term.upper() in text for term in _EXCLUDED_TERMS)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    text_upper = text.upper()
    return any(marker.upper() in text_upper for marker in markers)


def _is_exchange_traded(fund: CatalogFund) -> bool:
    if "联接" in fund.fund_name:
        return False
    return _has_any(f"{fund.fund_name} {fund.fund_type}", _ETF_MARKERS)


def _tracked_index_for(fund_name: str, asset_class: str, theme: str | None) -> str | None:
    text = fund_name.upper()
    if asset_class == "us_etf":
        if "标普500" in fund_name or "S&P" in text:
            return "S&P 500"
        if "纳斯达克" in fund_name or "纳指" in fund_name or "NASDAQ" in text:
            return "Nasdaq 100"
        if "道琼斯" in fund_name or "DOW" in text:
            return "Dow Jones"
        if "美国50" in fund_name:
            return "FTSE US 50"
        return "US Equity"
    if asset_class == "hk_etf":
        if "恒生科技" in fund_name:
            return "Hang Seng Tech"
        if "恒生" in fund_name:
            return "Hang Seng"
        if "红利" in fund_name:
            return "HK Dividend"
        if "中概" in fund_name or "互联网" in fund_name:
            return "China Internet"
        return "HK Equity"
    if asset_class == "qdii_global":
        return "Global Equity"
    for keyword, tracked in (
        ("沪深300", "沪深300"),
        ("中证A500", "中证A500"),
        ("A500", "中证A500"),
        ("中证500", "中证500"),
        ("中证1000", "中证1000"),
        ("上证50", "上证50"),
        ("创业板50", "创业板50"),
        ("创业板", "创业板指"),
        ("科创50", "科创50"),
    ):
        if keyword in fund_name:
            return tracked
    if asset_class == "cn_bond_fund":
        if "国债" in fund_name:
            return "国债"
        if "政金债" in fund_name:
            return "政金债"
        if "信用债" in fund_name:
            return "信用债"
        if "可转债" in fund_name:
            return "中证可转债"
    if asset_class == "cn_etf":
        # §2.1 — recognised CSI sector-index ETFs emit a canonical 中文 index
        # name (matching _SECTOR_INDEX_DISPLAY) so _INDEX_NAME_TO_SLUG resolves
        # them and the accumulate-forward PE anchor becomes reachable. Most
        # specific keyword first (矿业 before 有色).
        if "矿业" in fund_name and "有色" in fund_name:
            return "中证有色金属矿业主题"
        if "有色" in fund_name:
            return "中证有色金属"
        if "资源" in fund_name:
            return "中证资源"
    if asset_class == "cn_etf" and theme is not None:
        return fund_name
    return None


def _infer_asset_class(fund: CatalogFund) -> str | None:
    text = f"{fund.fund_name} {fund.fund_type}"
    is_qdii = "QDII" in text.upper()
    if is_qdii and _has_any(text, _US_MARKERS):
        return "us_etf"
    if is_qdii and _has_any(text, _HK_MARKERS):
        return "hk_etf"
    if is_qdii and _has_any(text, _EQUITY_TYPE_MARKERS) and not _has_any(text, _BOND_MARKERS):
        return "qdii_global"
    if _is_exchange_traded(fund):
        return "cn_etf"
    if _has_any(text, _BOND_MARKERS):
        return "cn_bond_fund"
    if _has_any(text, _EQUITY_TYPE_MARKERS):
        return "cn_equity_fund"
    return None


def _market_for(fund: CatalogFund) -> str:
    return "cn_on_exchange" if _is_exchange_traded(fund) else "cn_off_exchange"


def _venue_for(market: str) -> tuple[str, ...]:
    if market == "cn_on_exchange":
        return ("cn_brokerage",)
    return ("cmb_fund",)


def classify_catalog_fund(fund: CatalogFund) -> ClassifiedFund | None:
    if _is_excluded(fund):
        return None
    asset_class = _infer_asset_class(fund)
    if asset_class is None:
        return None
    theme = None if asset_class == "cn_bond_fund" else infer_theme(fund.fund_name, fund.fund_type)
    market = _market_for(fund)
    return ClassifiedFund(
        catalog=fund,
        asset_class=asset_class,
        market=market,
        currency="cny",
        tracked_index=_tracked_index_for(fund.fund_name, asset_class, theme),
        theme=theme,
        venue_required=_venue_for(market),
    )


def _share_class_rank(name: str) -> int:
    normalized = name.upper().replace("（", "(").replace("）", ")")
    for rank, share_class in enumerate(("A", "B", "D", "E", "I", "C")):
        if re.search(rf"(?:\({share_class}\)|{share_class}类?|{share_class}份额?)$", normalized):
            return rank
    return len(("A", "B", "D", "E", "I", "C"))


def _share_base_name(name: str) -> str:
    normalized = name.strip().replace("（", "(").replace("）", ")")
    normalized = re.sub(
        r"(?:\([ABCDIE]\)|[ABCDIE]类?|[ABCDIE]份额?)$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"人民币$", "", normalized)
    return normalized


def dedupe_share_classes(funds: Iterable[CatalogFund]) -> tuple[CatalogFund, ...]:
    chosen: dict[str, CatalogFund] = {}
    ranked = sorted(
        funds,
        key=lambda fund: (
            _share_base_name(fund.fund_name),
            _share_class_rank(fund.fund_name),
            1 if "联接" in fund.fund_name else 0,
            fund.fund_code,
        ),
    )
    for fund in ranked:
        base_name = _share_base_name(fund.fund_name)
        if base_name not in chosen:
            chosen[base_name] = fund
    return tuple(sorted(chosen.values(), key=lambda fund: fund.fund_code))


def _cap_key(classified: ClassifiedFund) -> tuple[str, str]:
    if classified.asset_class == "cn_equity_fund" and classified.theme not in (None, "broad"):
        return (classified.asset_class, classified.theme)
    if classified.asset_class == "cn_equity_fund":
        return (classified.asset_class, "broad_active")
    return (classified.asset_class, "all")


def _cap_for(classified: ClassifiedFund, options: UniverseBuildOptions) -> int:
    if classified.asset_class == "cn_equity_fund" and classified.theme not in (None, "broad"):
        return options.theme_cap
    if classified.asset_class == "cn_equity_fund":
        return options.active_broad_cap
    if classified.asset_class == "cn_bond_fund":
        return options.bond_cap
    if classified.asset_class == "cn_etf":
        return options.cn_etf_cap
    if classified.asset_class == "us_etf":
        return options.us_qdii_cap
    if classified.asset_class == "hk_etf":
        return options.hk_qdii_cap
    if classified.asset_class == "qdii_global":
        return options.qdii_global_cap
    return 0


def _candidate_rank(classified: ClassifiedFund) -> tuple[int, str]:
    feeder_penalty = 1 if "联接" in classified.catalog.fund_name else 0
    return (feeder_penalty, classified.catalog.fund_code)


def _candidate_rank_with_returns(
    returns: Mapping[str, float],
) -> Callable[[ClassifiedFund], tuple[int, int, float, str]]:
    """Build a sort-key function that ranks by (feeder_penalty,
    missing_return_penalty, -return_1y, fund_code). When `returns` is empty
    the result is order-equivalent to `_candidate_rank` (ascending fund_code,
    feeders last)."""
    def key(classified: ClassifiedFund) -> tuple[int, int, float, str]:
        feeder_penalty = 1 if "联接" in classified.catalog.fund_name else 0
        raw = returns.get(classified.catalog.fund_code)
        if raw is None or (isinstance(raw, float) and raw != raw):  # NaN check
            missing = 1
            neg_return = 0.0
        else:
            missing = 0
            neg_return = -float(raw)
        return (feeder_penalty, missing, neg_return, classified.catalog.fund_code)
    return key


def _apply_caps(
    classified: Iterable[ClassifiedFund],
    options: UniverseBuildOptions,
    returns: Mapping[str, float] | None = None,
) -> tuple[ClassifiedFund, ...]:
    grouped: dict[tuple[str, str], list[ClassifiedFund]] = defaultdict(list)
    for item in classified:
        grouped[_cap_key(item)].append(item)
    rank_key = _candidate_rank_with_returns(returns or {})
    selected: list[ClassifiedFund] = []
    for key in sorted(grouped):
        items = sorted(grouped[key], key=rank_key)
        selected.extend(items[: _cap_for(items[0], options)])
    return tuple(sorted(selected, key=lambda item: item.catalog.fund_code))


def _to_instrument(classified: ClassifiedFund) -> Instrument:
    payload: dict[str, Any] = {
        "instrument_id": classified.catalog.fund_code,
        "ticker": classified.catalog.fund_code,
        "market": classified.market,
        "name_cn": classified.catalog.fund_name,
        "asset_class": classified.asset_class,
        "currency": classified.currency,
        "tracked_index": classified.tracked_index,
        "theme": classified.theme,
        "venue_required": list(classified.venue_required),
    }
    return Instrument.model_validate(payload)


def _exclude_feeder_funds(classified: tuple[ClassifiedFund, ...]) -> tuple[ClassifiedFund, ...]:
    """Remove OTC feeder funds (联接) whose parent ETF is already in the classified set."""
    etf_names = {item.catalog.fund_name for item in classified if item.asset_class == "cn_etf"}
    return tuple(
        item for item in classified
        if not (
            "联接" in item.catalog.fund_name
            and any(item.catalog.fund_name.startswith(etf_name) for etf_name in etf_names)
        )
    )


def build_cn_fund_universe(
    rows: Iterable[Mapping[str, Any]],
    options: UniverseBuildOptions | None = None,
    returns: Mapping[str, float] | None = None,
) -> tuple[Instrument, ...]:
    build_options = options or UniverseBuildOptions()
    funds = dedupe_share_classes(normalize_catalog_rows(rows))
    classified = tuple(item for fund in funds if (item := classify_catalog_fund(fund)) is not None)
    classified = _exclude_feeder_funds(classified)
    capped = _apply_caps(classified, build_options, returns)
    return tuple(_to_instrument(item) for item in capped)


def serialize_universe(instruments: Iterable[Instrument]) -> dict[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for instrument in instruments:
        row = instrument.model_dump(exclude_none=True)
        row["venue_required"] = list(instrument.venue_required)
        rows.append(row)
    return {"instruments": rows}
