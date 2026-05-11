# CN Fund Universe Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic generated CN fund universe path from Akshare's broad public-fund catalog, load it beside curated universe config, and emit discovery diagnostics that explain each funnel stage.

**Architecture:** Keep data-source I/O at command and client boundaries, with all fund classification and candidate shaping in pure functions under `src/irc/discovery/cn_fund_universe.py`. The generated YAML is a cache boundary: `irc universe build-cn-funds` writes `config/universe/cn_funds.generated.yaml`, `load_repo_configs()` merges curated plus generated instruments with curated rows winning, and discovery writes both `discovered_watchlist.csv` and `discovery_diagnostics.csv`.

**Tech Stack:** Python 3.12, Click, Pydantic v2, pandas, PyYAML, DuckDB, pytest, Akshare through `irc.data.akshare_client._ak_call`.

---

## Scope Check

This spec touches multiple files, but the pieces are one coupled product path rather than independent subsystems: catalog wrapper -> pure classification -> generated YAML -> config merge -> ingest/discover -> diagnostics. Keep this as one implementation plan so every task produces a working increment of the same feature.

## File Structure

- Create `src/irc/discovery/cn_fund_universe.py`: pure catalog normalization, exclusion, classification, share-class dedupe, cap application, and serialization helpers.
- Modify `src/irc/data/akshare_client.py`: expose `fetch_open_fund_catalog()` as a thin wrapper over the existing Akshare open-fund table path.
- Create `src/irc/commands/universe_cmd.py`: CLI command implementation for `irc universe build-cn-funds --repo-root .`.
- Modify `src/irc/cli.py`: add `@main.group(help="Universe generation.")` and register `build-cn-funds`.
- Modify `src/irc/config_loader.py`: support optional `config/universe/cn_funds.generated.yaml` loading and curated-wins merge without adding the generated file to `TEMPLATE_FILES`.
- Create `src/irc/discovery/diagnostics.py`: convert universe, hard-filter, quality-filter, and role-bucket results into a stable diagnostics dataframe.
- Modify `src/irc/discovery/pipeline.py`: add `run_discovery_with_diagnostics()` while keeping existing `run_discovery()` return type unchanged.
- Modify `src/irc/commands/discover_cmd.py`: write `discovery_diagnostics.csv` next to the watchlist.
- Modify `src/irc/schemas/discovery.py`, `src/irc/discovery/hard_filter.py`, `src/irc/discovery/quality_filter.py`, `config/discovery.yaml`, and `src/irc/templates/config/discovery.yaml`: add focused fee and drawdown calibration knobs while preserving old config compatibility through schema defaults.
- Add tests in `tests/discovery/test_cn_fund_universe.py`, `tests/data/test_akshare_client.py`, `tests/commands/test_universe_cmd.py`, `tests/test_config_loader.py`, `tests/discovery/test_diagnostics.py`, `tests/discovery/test_pipeline.py`, `tests/commands/test_discover_cmd.py`, and `tests/integration/test_generated_cn_fund_discovery.py`.

---

### Task 1: Pure CN Fund Universe Classifier

**Files:**
- Create: `src/irc/discovery/cn_fund_universe.py`
- Test: `tests/discovery/test_cn_fund_universe.py`

- [ ] **Step 1: Write the failing classifier tests**

Create `tests/discovery/test_cn_fund_universe.py` with this content:

```python
from __future__ import annotations

from irc.discovery.cn_fund_universe import (
    UniverseBuildOptions,
    build_cn_fund_universe,
    classify_catalog_fund,
    dedupe_share_classes,
    infer_theme,
    normalize_catalog_rows,
    serialize_universe,
)


def test_normalize_catalog_rows_uses_stable_column_names() -> None:
    rows = [
        {"fund_code": 110022, "fund_name": "易方达消费行业股票A", "fund_type": "股票型"},
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ]

    out = normalize_catalog_rows(rows)

    assert [fund.fund_code for fund in out] == ["110022", "003095"]
    assert out[0].fund_name == "易方达消费行业股票A"


def test_normalize_catalog_rows_skips_rows_without_required_fields() -> None:
    rows = [
        {"fund_code": "110022", "fund_name": "易方达消费行业股票A", "fund_type": "股票型"},
        {"fund_code": "", "fund_name": "无代码基金", "fund_type": "股票型"},
        {"fund_code": "000000", "fund_name": "", "fund_type": "股票型"},
    ]

    out = normalize_catalog_rows(rows)

    assert [fund.fund_code for fund in out] == ["110022"]


def test_excludes_money_market_short_cash_fof_and_abnormal_status() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "000001", "fund_name": "华夏现金增利货币A", "fund_type": "货币型"},
        {"fund_code": "000002", "fund_name": "招商短债债券A", "fund_type": "债券型"},
        {"fund_code": "000003", "fund_name": "南方养老FOF", "fund_type": "FOF"},
        {"fund_code": "000004", "fund_name": "某某基金清算", "fund_type": "混合型"},
        {"fund_code": "000005", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ])

    assert [instrument.instrument_id for instrument in instruments] == ["000005"]


def test_theme_inference_matches_supported_literals() -> None:
    assert infer_theme("华泰柏瑞沪深300ETF", "指数型") == "broad"
    assert infer_theme("中证红利低波ETF", "指数型") == "dividend"
    assert infer_theme("科技创新混合A", "混合型") == "tech"
    assert infer_theme("半导体芯片ETF", "指数型") == "semiconductor"
    assert infer_theme("军工龙头股票A", "股票型") == "defense"
    assert infer_theme("中欧医疗健康混合A", "混合型") == "healthcare"
    assert infer_theme("新能源车电池ETF", "指数型") == "new_energy"
    assert infer_theme("消费食品饮料股票A", "股票型") == "consumer"
    assert infer_theme("银行证券金融ETF", "指数型") == "finance"
    assert infer_theme("有色金属资源ETF", "指数型") == "metals"
    assert infer_theme("房地产ETF", "指数型") == "real_estate"
    assert infer_theme("央企国企改革ETF", "指数型") == "soe"
    assert infer_theme("朱少醒价值精选混合A", "混合型") is None


def test_classifies_active_equity_without_theme_as_cn_equity_fund() -> None:
    fund = normalize_catalog_rows([
        {"fund_code": "519035", "fund_name": "富国天博创新主题混合A", "fund_type": "混合型"}
    ])[0]

    classified = classify_catalog_fund(fund)

    assert classified is not None
    assert classified.asset_class == "cn_equity_fund"
    assert classified.market == "cn_off_exchange"
    assert classified.theme is None
    assert classified.venue_required == ("cmb_fund",)


def test_classifies_domestic_etf_only_with_exchange_traded_evidence() -> None:
    etf = normalize_catalog_rows([
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"}
    ])[0]
    index_fund = normalize_catalog_rows([
        {"fund_code": "110020", "fund_name": "易方达沪深300指数增强A", "fund_type": "指数型"}
    ])[0]

    classified_etf = classify_catalog_fund(etf)
    classified_index = classify_catalog_fund(index_fund)

    assert classified_etf is not None
    assert classified_etf.asset_class == "cn_etf"
    assert classified_etf.market == "cn_on_exchange"
    assert classified_etf.tracked_index == "沪深300"
    assert classified_index is not None
    assert classified_index.asset_class == "cn_equity_fund"
    assert classified_index.market == "cn_off_exchange"


def test_classifies_qdii_us_and_hk_exposure() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "006075", "fund_name": "易方达标普500人民币A", "fund_type": "QDII"},
        {"fund_code": "159920", "fund_name": "恒生ETF华夏", "fund_type": "QDII-ETF"},
    ])

    by_id = {instrument.instrument_id: instrument for instrument in instruments}
    assert by_id["006075"].asset_class == "us_etf"
    assert by_id["006075"].market == "cn_off_exchange"
    assert by_id["006075"].tracked_index == "S&P 500"
    assert by_id["159920"].asset_class == "hk_etf"
    assert by_id["159920"].market == "cn_on_exchange"
    assert by_id["159920"].tracked_index == "Hang Seng"


def test_dedupes_share_classes_preferring_a_over_c() -> None:
    funds = normalize_catalog_rows([
        {"fund_code": "003096", "fund_name": "中欧医疗健康混合C", "fund_type": "混合型"},
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ])

    out = dedupe_share_classes(funds)

    assert [fund.fund_code for fund in out] == ["003095"]


def test_caps_candidates_by_asset_class_and_theme() -> None:
    rows = [
        {"fund_code": f"10{i:04d}", "fund_name": f"消费行业股票{i}A", "fund_type": "股票型"}
        for i in range(5)
    ] + [
        {"fund_code": f"20{i:04d}", "fund_name": f"均衡成长混合{i}A", "fund_type": "混合型"}
        for i in range(5)
    ] + [
        {"fund_code": f"30{i:04d}", "fund_name": f"债券精选{i}A", "fund_type": "债券型"}
        for i in range(5)
    ]
    options = UniverseBuildOptions(active_broad_cap=2, theme_cap=3, bond_cap=2, cn_etf_cap=10, us_qdii_cap=10, hk_qdii_cap=10)

    out = build_cn_fund_universe(rows, options=options)

    consumer = [instrument for instrument in out if instrument.theme == "consumer"]
    growth = [instrument for instrument in out if instrument.asset_class == "cn_equity_fund" and instrument.theme is None]
    bonds = [instrument for instrument in out if instrument.asset_class == "cn_bond_fund"]
    assert len(consumer) == 3
    assert len(growth) == 2
    assert len(bonds) == 2


def test_serialized_universe_validates_as_yaml_compatible_shape() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"}
    ])

    out = serialize_universe(instruments)

    assert out == {
        "instruments": [
            {
                "instrument_id": "003095",
                "ticker": "003095",
                "market": "cn_off_exchange",
                "name_cn": "中欧医疗健康混合A",
                "asset_class": "cn_equity_fund",
                "currency": "cny",
                "theme": "healthcare",
                "venue_required": ["cmb_fund"],
            }
        ]
    }
```

- [ ] **Step 2: Run classifier tests to verify they fail**

Run:

```bash
uv run pytest tests/discovery/test_cn_fund_universe.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'irc.discovery.cn_fund_universe'`.

- [ ] **Step 3: Add the classifier implementation**

Create `src/irc/discovery/cn_fund_universe.py` with this content:

```python
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
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
        fund_type = _text(row.get("fund_type"))
        if not fund_code or not fund_name or not fund_type:
            continue
        normalized.append(CatalogFund(fund_code=fund_code.zfill(6), fund_name=fund_name, fund_type=fund_type))
    return tuple(sorted(normalized, key=lambda fund: fund.fund_code))


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
    return 2


def _share_base_name(name: str) -> str:
    normalized = name.strip().replace("（", "(").replace("）", ")")
    normalized = re.sub(r"(?:\([A-Z]\)|[A-Z]类?|[A-Z]份额?)$", "", normalized, flags=re.IGNORECASE)
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
    return 0


def _candidate_rank(classified: ClassifiedFund) -> tuple[int, str]:
    feeder_penalty = 1 if "联接" in classified.catalog.fund_name else 0
    return (feeder_penalty, classified.catalog.fund_code)


def _apply_caps(classified: Iterable[ClassifiedFund], options: UniverseBuildOptions) -> tuple[ClassifiedFund, ...]:
    grouped: dict[tuple[str, str], list[ClassifiedFund]] = defaultdict(list)
    for item in classified:
        grouped[_cap_key(item)].append(item)
    selected: list[ClassifiedFund] = []
    for key in sorted(grouped):
        items = sorted(grouped[key], key=_candidate_rank)
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


def build_cn_fund_universe(
    rows: Iterable[Mapping[str, Any]],
    options: UniverseBuildOptions | None = None,
) -> tuple[Instrument, ...]:
    build_options = options or UniverseBuildOptions()
    funds = dedupe_share_classes(normalize_catalog_rows(rows))
    classified = tuple(item for fund in funds if (item := classify_catalog_fund(fund)) is not None)
    capped = _apply_caps(classified, build_options)
    return tuple(_to_instrument(item) for item in capped)


def serialize_universe(instruments: Iterable[Instrument]) -> dict[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for instrument in instruments:
        row = instrument.model_dump(exclude_none=True)
        row["venue_required"] = list(instrument.venue_required)
        rows.append(row)
    return {"instruments": rows}
```

- [ ] **Step 4: Run classifier tests to verify they pass**

Run:

```bash
uv run pytest tests/discovery/test_cn_fund_universe.py -q
```

Expected: PASS, all tests in `test_cn_fund_universe.py` pass.

- [ ] **Step 5: Commit the classifier increment**

Run:

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat: add generated CN fund universe classifier"
```

Expected: commit succeeds.

---

### Task 2: Akshare Fund Catalog Wrapper

**Files:**
- Modify: `src/irc/data/akshare_client.py`
- Test: `tests/data/test_akshare_client.py`

- [ ] **Step 1: Add failing catalog wrapper tests**

Append these tests to `tests/data/test_akshare_client.py`:

```python
def test_fetch_open_fund_catalog_normalizes_chinese_columns() -> None:
    fake = pd.DataFrame({
        "基金代码": ["003095", "110022"],
        "基金名称": ["中欧医疗健康混合A", "易方达消费行业股票A"],
        "基金类型": ["混合型", "股票型"],
        "ignored": [1, 2],
    })
    with patch("irc.data.akshare_client._raw_fund_table_call", return_value=fake):
        from irc.data.akshare_client import fetch_open_fund_catalog

        fetch_open_fund_catalog.cache_clear()
        out = fetch_open_fund_catalog()

    assert list(out.columns) == ["fund_code", "fund_name", "fund_type"]
    assert out.to_dict("records") == [
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
        {"fund_code": "110022", "fund_name": "易方达消费行业股票A", "fund_type": "股票型"},
    ]


def test_fetch_open_fund_catalog_raises_when_required_columns_missing() -> None:
    fake = pd.DataFrame({"基金代码": ["003095"], "基金名称": ["中欧医疗健康混合A"]})
    with patch("irc.data.akshare_client._raw_fund_table_call", return_value=fake):
        from irc.data.akshare_client import fetch_open_fund_catalog

        fetch_open_fund_catalog.cache_clear()
        with pytest.raises(ValueError, match="fund_type"):
            fetch_open_fund_catalog()
```

- [ ] **Step 2: Run wrapper tests to verify they fail**

Run:

```bash
uv run pytest tests/data/test_akshare_client.py::test_fetch_open_fund_catalog_normalizes_chinese_columns tests/data/test_akshare_client.py::test_fetch_open_fund_catalog_raises_when_required_columns_missing -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `fetch_open_fund_catalog`.

- [ ] **Step 3: Add the catalog wrapper**

In `src/irc/data/akshare_client.py`, add this function immediately after `_fetch_full_fund_table()`:

```python
@lru_cache(maxsize=1)
def fetch_open_fund_catalog() -> pd.DataFrame:
    """Fetch Akshare's open-fund catalog with stable internal column names."""
    df = _raw_fund_table_call()
    rename_map = {
        "基金代码": "fund_code",
        "基金名称": "fund_name",
        "基金类型": "fund_type",
    }
    normalized = df.rename(columns=rename_map)
    required = ("fund_code", "fund_name", "fund_type")
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"Akshare open fund catalog missing columns: {', '.join(missing)}")
    out = normalized.loc[:, list(required)].copy()
    for column in required:
        out[column] = out[column].astype(str).str.strip()
    return out
```

- [ ] **Step 4: Run Akshare client tests**

Run:

```bash
uv run pytest tests/data/test_akshare_client.py -q
```

Expected: PASS, including existing Akshare client tests.

- [ ] **Step 5: Commit the catalog wrapper**

Run:

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat: expose Akshare open fund catalog"
```

Expected: commit succeeds.

---

### Task 3: Universe Build Command

**Files:**
- Create: `src/irc/commands/universe_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_universe_cmd.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write failing command tests**

Create `tests/commands/test_universe_cmd.py` with this content:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml
from click.testing import CliRunner

from irc.cli import main
from irc.commands.universe_cmd import run_build_cn_funds


def _catalog() -> pd.DataFrame:
    return pd.DataFrame([
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
        {"fund_code": "003096", "fund_name": "中欧医疗健康混合C", "fund_type": "混合型"},
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"},
        {"fund_code": "000001", "fund_name": "华夏现金增利货币A", "fund_type": "货币型"},
    ])


def test_build_cn_funds_writes_generated_yaml_atomically(tmp_path: Path) -> None:
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    assert rc == 0
    generated_path = tmp_path / "config" / "universe" / "cn_funds.generated.yaml"
    assert generated_path.exists()
    raw = yaml.safe_load(generated_path.read_text(encoding="utf-8"))
    ids = [row["instrument_id"] for row in raw["instruments"]]
    assert ids == ["003095", "510300"]
    assert raw["instruments"][0]["asset_class"] == "cn_equity_fund"
    assert raw["instruments"][0]["theme"] == "healthcare"


def test_build_cn_funds_prints_counts(tmp_path: Path, capsys) -> None:
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    captured = capsys.readouterr()
    assert rc == 0
    assert "cn_equity_fund/healthcare: 1" in captured.out
    assert "cn_etf/broad: 1" in captured.out


def test_build_cn_funds_leaves_existing_file_untouched_on_fetch_failure(tmp_path: Path) -> None:
    generated_path = tmp_path / "config" / "universe" / "cn_funds.generated.yaml"
    generated_path.parent.mkdir(parents=True)
    generated_path.write_text("sentinel: true\n", encoding="utf-8")

    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", side_effect=RuntimeError("network down")):
        rc = run_build_cn_funds(repo_root=str(tmp_path))

    assert rc == 1
    assert generated_path.read_text(encoding="utf-8") == "sentinel: true\n"


def test_cli_universe_build_cn_funds_command(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        result = runner.invoke(main, ["universe", "build-cn-funds", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "universe build-cn-funds OK" in result.output
    assert (tmp_path / "config" / "universe" / "cn_funds.generated.yaml").exists()
```

Append this assertion to `tests/test_cli_smoke.py::test_cli_help_lists_subcommands` by changing the command tuple:

```python
    for cmd in ("init", "config", "freshness", "universe"):
        assert cmd in result.output
```

- [ ] **Step 2: Run command tests to verify they fail**

Run:

```bash
uv run pytest tests/commands/test_universe_cmd.py tests/test_cli_smoke.py::test_cli_help_lists_subcommands -q
```

Expected: FAIL because `irc.commands.universe_cmd` and the `universe` CLI group do not exist.

- [ ] **Step 3: Add command implementation**

Create `src/irc/commands/universe_cmd.py` with this content:

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import yaml

from irc.data.akshare_client import fetch_open_fund_catalog
from irc.discovery.cn_fund_universe import build_cn_fund_universe, serialize_universe
from irc.io_utils import atomic_write_text
from irc.schemas.universe import UniverseConfig


def _theme_label(value: str | None) -> str:
    return value if value is not None else "none"


def _counts_text(config: UniverseConfig) -> str:
    counts = Counter(
        (instrument.asset_class, _theme_label(instrument.theme))
        for instrument in config.instruments
    )
    return "\n".join(
        f"  {asset_class}/{theme}: {count}"
        for (asset_class, theme), count in sorted(counts.items())
    )


def _yaml_text(config: UniverseConfig) -> str:
    raw = serialize_universe(config.instruments)
    return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def run_build_cn_funds(repo_root: str) -> int:
    root = Path(repo_root)
    generated_path = root / "config" / "universe" / "cn_funds.generated.yaml"
    try:
        catalog = fetch_open_fund_catalog()
        instruments = build_cn_fund_universe(catalog.to_dict("records"))
        config = UniverseConfig.model_validate(serialize_universe(instruments))
        text = _yaml_text(config)
    except Exception as exc:  # noqa: BLE001 - command must preserve previous generated file on any failure
        print(f"ERROR: failed to build generated CN fund universe: {exc}", file=sys.stderr)
        return 1

    atomic_write_text(generated_path, text)
    print(f"universe build-cn-funds OK: {len(config.instruments)} instruments -> {generated_path}")
    counts = _counts_text(config)
    if counts:
        print(counts)
    return 0
```

- [ ] **Step 4: Register the Click command**

In `src/irc/cli.py`, add this group after the existing `config()` group:

```python
@main.group(help="Universe generation.")
def universe() -> None:
    pass
```

Then add this command after `config_validate()`:

```python
@universe.command("build-cn-funds", help="Build generated CN fund universe from Akshare catalog.")
@click.option("--repo-root", type=click.Path(file_okay=False), default=".",
              help="Repo root (defaults to cwd).")
def universe_build_cn_funds(repo_root: str) -> None:
    from irc.commands.universe_cmd import run_build_cn_funds
    rc = run_build_cn_funds(repo_root=repo_root)
    raise SystemExit(rc)
```

- [ ] **Step 5: Run command and CLI tests**

Run:

```bash
uv run pytest tests/commands/test_universe_cmd.py tests/test_cli_smoke.py -q
```

Expected: PASS, command writes only `cn_funds.generated.yaml` and CLI help lists `universe`.

- [ ] **Step 6: Commit the command increment**

Run:

```bash
git add src/irc/commands/universe_cmd.py src/irc/cli.py tests/commands/test_universe_cmd.py tests/test_cli_smoke.py
git commit -m "feat: add CN fund universe build command"
```

Expected: commit succeeds.

---

### Task 4: Optional Generated Universe Loading

**Files:**
- Modify: `src/irc/config_loader.py`
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: Add failing config-loader tests**

Append these tests to `tests/test_config_loader.py`:

```python
def test_load_repo_configs_merges_optional_generated_cn_funds(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    write_yaml(tmp_repo / "config/universe/cn_funds.yaml", {
        "instruments": [
            {
                "instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
                "name_cn": "华泰柏瑞沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
                "tracked_index": "沪深300", "theme": "broad", "venue_required": ["cn_brokerage"],
            }
        ]
    })
    write_yaml(tmp_repo / "config/universe/cn_funds.generated.yaml", {
        "instruments": [
            {
                "instrument_id": "003095", "ticker": "003095", "market": "cn_off_exchange",
                "name_cn": "中欧医疗健康混合A", "asset_class": "cn_equity_fund", "currency": "cny",
                "theme": "healthcare", "venue_required": ["cmb_fund"],
            }
        ]
    })

    bundle = load_repo_configs(tmp_repo)

    assert [instrument.instrument_id for instrument in bundle.universe_cn_funds.instruments] == ["510300", "003095"]


def test_load_repo_configs_curated_cn_funds_win_over_generated_duplicates(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)
    write_yaml(tmp_repo / "config/universe/cn_funds.yaml", {
        "instruments": [
            {
                "instrument_id": "003095", "ticker": "003095", "market": "cn_off_exchange",
                "name_cn": "Curated Name", "asset_class": "cn_equity_fund", "currency": "cny",
                "theme": "healthcare", "venue_required": ["cmb_fund"],
            }
        ]
    })
    write_yaml(tmp_repo / "config/universe/cn_funds.generated.yaml", {
        "instruments": [
            {
                "instrument_id": "003095", "ticker": "003095", "market": "cn_off_exchange",
                "name_cn": "Generated Name", "asset_class": "cn_equity_fund", "currency": "cny",
                "theme": "healthcare", "venue_required": ["cmb_fund"],
            }
        ]
    })

    bundle = load_repo_configs(tmp_repo)

    assert len(bundle.universe_cn_funds.instruments) == 1
    assert bundle.universe_cn_funds.instruments[0].name_cn == "Curated Name"


def test_load_repo_configs_works_without_generated_cn_funds(tmp_repo: Path):
    _minimal_inputs(tmp_repo)
    _minimal_configs(tmp_repo)

    bundle = load_repo_configs(tmp_repo)

    assert bundle.universe_cn_funds.instruments == []


def test_load_yaml_accepts_generated_cn_funds_when_file_exists(tmp_repo: Path):
    write_yaml(tmp_repo / "config/universe/cn_funds.generated.yaml", {
        "instruments": [
            {
                "instrument_id": "003095", "ticker": "003095", "market": "cn_off_exchange",
                "name_cn": "中欧医疗健康混合A", "asset_class": "cn_equity_fund", "currency": "cny",
                "theme": "healthcare", "venue_required": ["cmb_fund"],
            }
        ]
    })

    cfg = load_yaml(tmp_repo / "config/universe/cn_funds.generated.yaml", tmp_repo)

    assert cfg.instruments[0].instrument_id == "003095"
```

- [ ] **Step 2: Run config-loader tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_loader.py -q
```

Expected: FAIL because generated universe files are not registered or merged.

- [ ] **Step 3: Add optional generated universe registration and merge helpers**

In `src/irc/config_loader.py`, replace the schema maps near the top with this code:

```python
_FILENAME_TO_SCHEMA: dict[str, type] = {
    "inputs/account.yaml": AccountFile,
    "inputs/preferences.yaml": PreferencesFile,
    "config/llm.yaml": LLMConfig,
    "config/scoring.yaml": ScoringConfig,
    "config/gold_drivers.yaml": GoldDriversConfig,
    "config/discovery.yaml": DiscoveryConfig,
    "config/valuation_buckets.yaml": ValuationBucketsConfig,
    "config/triggers.yaml": TriggersConfig,
    "config/overrides.yaml": OverridesConfig,
    "config/macro_view.yaml": MacroViewConfig,
    "config/universe/qdii_us.yaml": UniverseConfig,
    "config/universe/qdii_hk.yaml": UniverseConfig,
    "config/universe/cn_funds.yaml": UniverseConfig,
    "config/universe/gold.yaml": UniverseConfig,
}

_OPTIONAL_FILENAME_TO_SCHEMA: dict[str, type] = {
    "config/universe/cn_funds.generated.yaml": UniverseConfig,
}
```

Then replace `_resolve_schema()` with this version:

```python
def _resolve_schema(repo_root: Path, file_path: Path) -> type:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"could not determine relative path for {file_path}: {exc}. "
            "If this file is a symlink, ensure it points inside the repo root."
        ) from exc
    schema = _FILENAME_TO_SCHEMA.get(rel) or _OPTIONAL_FILENAME_TO_SCHEMA.get(rel)
    if schema is None:
        raise KeyError(f"no schema registered for {rel}")
    return schema
```

Add these helpers before `load_repo_configs()`:

```python
def _load_optional_universe(path: Path, repo_root: Path) -> UniverseConfig:
    if not path.exists():
        return UniverseConfig()
    return load_yaml(path, repo_root)


def _merge_universe_configs(primary: UniverseConfig, secondary: UniverseConfig) -> UniverseConfig:
    seen = {instrument.instrument_id for instrument in primary.instruments}
    instruments = [*primary.instruments]
    instruments.extend(
        instrument for instrument in secondary.instruments
        if instrument.instrument_id not in seen
    )
    return UniverseConfig(instruments=instruments)
```

Finally, replace the `universe_cn_funds=` argument inside `load_repo_configs()` with this expression:

```python
        universe_cn_funds=_merge_universe_configs(
            load_yaml(p / "config/universe/cn_funds.yaml", p),
            _load_optional_universe(p / "config/universe/cn_funds.generated.yaml", p),
        ),
```

- [ ] **Step 4: Run config-loader tests**

Run:

```bash
uv run pytest tests/test_config_loader.py -q
```

Expected: PASS, and `TEMPLATE_FILES` count remains unchanged because generated files are optional.

- [ ] **Step 5: Commit optional loading**

Run:

```bash
git add src/irc/config_loader.py tests/test_config_loader.py
git commit -m "feat: load optional generated CN fund universe"
```

Expected: commit succeeds.

---

### Task 5: Discovery Diagnostics Model

**Files:**
- Create: `src/irc/discovery/diagnostics.py`
- Modify: `src/irc/discovery/pipeline.py`
- Test: `tests/discovery/test_diagnostics.py`
- Test: `tests/discovery/test_pipeline.py`

- [ ] **Step 1: Write failing diagnostics unit tests**

Create `tests/discovery/test_diagnostics.py` with this content:

```python
from __future__ import annotations

import pandas as pd

from irc.discovery.diagnostics import build_discovery_diagnostics
from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


def _row(iid: str, asset_class: str, theme: str | None = None) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid,
        ticker=iid,
        market="cn_off_exchange",
        name_cn=iid,
        asset_class=asset_class,
        currency="cny",
        tracked_index=None,
        theme=theme,
        venue_required=(),
    )


def test_build_discovery_diagnostics_counts_universe_passes_rejections_and_roles() -> None:
    universe = (
        _row("003095", "cn_equity_fund", "healthcare"),
        _row("510300", "cn_etf", "broad"),
    )
    hard = HardFilterResult(
        passed=(universe[0],),
        rejected=(Rejection("510300", ("expense_ratio 0.01 > 0.005",)),),
    )
    quality = HardFilterResult(
        passed=(universe[0],),
        rejected=(),
    )
    bucketed = RoleBucketResult(
        buckets={"satellite_cn_healthcare": (universe[0],), "core_cn_equity": ()},
        relaxed_roles=("satellite_cn_healthcare",),
        failed_roles=("core_cn_equity",),
    )

    out = build_discovery_diagnostics(universe, hard, quality, bucketed)

    assert list(out.columns) == ["stage", "status", "asset_class", "theme", "role", "reason", "count"]
    records = out.to_dict("records")
    assert {
        "stage": "universe",
        "status": "input",
        "asset_class": "cn_equity_fund",
        "theme": "healthcare",
        "role": "",
        "reason": "",
        "count": 1,
    } in records
    assert {
        "stage": "hard_filter",
        "status": "rejected",
        "asset_class": "cn_etf",
        "theme": "broad",
        "role": "",
        "reason": "expense_ratio 0.01 > 0.005",
        "count": 1,
    } in records
    assert {
        "stage": "role_bucket",
        "status": "failed",
        "asset_class": "",
        "theme": "",
        "role": "core_cn_equity",
        "reason": "below fail_below",
        "count": 0,
    } in records


def test_empty_discovery_diagnostics_keeps_columns() -> None:
    empty_result = HardFilterResult(passed=(), rejected=())
    bucketed = RoleBucketResult(buckets={}, relaxed_roles=(), failed_roles=())

    out = build_discovery_diagnostics((), empty_result, empty_result, bucketed)

    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["stage", "status", "asset_class", "theme", "role", "reason", "count"]
    assert out.empty
```

Append this test to `tests/discovery/test_pipeline.py`:

```python
@patch("irc.discovery.pipeline.write_reason")
def test_pipeline_can_return_diagnostics(mock_writer) -> None:
    from irc.discovery.pipeline import run_discovery_with_diagnostics

    mock_writer.return_value = MagicMock(
        instrument_id="003095",
        reason_text="healthcare active fund",
        cited_refs=(),
        prompt_tokens=10,
        completion_tokens=5,
    )
    universe = (_row("003095", "cn_equity_fund", None, None),)
    metadata = pd.DataFrame([{
        "instrument_id": "003095", "inception_years": 5,
        "aum_cny": 1e9, "expense_ratio": 0.012, "daily_volume_cny": 0,
    }])
    metrics = pd.DataFrame([{
        "instrument_id": "003095", "drawdown_3y": 0.15,
        "tracking_error": None, "manager_tenure_years": 5,
    }])

    result = run_discovery_with_diagnostics(
        universe=universe,
        metadata=metadata,
        metrics=metrics,
        risk_band_max_dd_upper=0.20,
        cfg_overrides=None,
        cfg_discovery=None,
        route=MagicMock(),
        peer_summary="x",
        macro_snapshot="x",
        raw_ref_pool=(),
    )

    assert result.watchlist["instrument_id"].tolist() == ["003095"]
    assert {"universe", "hard_filter", "quality_filter", "role_bucket"}.issubset(
        set(result.diagnostics["stage"])
    )
```

- [ ] **Step 2: Run diagnostics tests to verify they fail**

Run:

```bash
uv run pytest tests/discovery/test_diagnostics.py tests/discovery/test_pipeline.py::test_pipeline_can_return_diagnostics -q
```

Expected: FAIL because `irc.discovery.diagnostics` and `run_discovery_with_diagnostics` do not exist.

- [ ] **Step 3: Add diagnostics model**

Create `src/irc/discovery/diagnostics.py` with this content:

```python
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


DIAGNOSTIC_COLUMNS = ("stage", "status", "asset_class", "theme", "role", "reason", "count")


@dataclass(frozen=True)
class DiagnosticRow:
    stage: str
    status: str
    asset_class: str
    theme: str
    role: str
    reason: str
    count: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "stage": self.stage,
            "status": self.status,
            "asset_class": self.asset_class,
            "theme": self.theme,
            "role": self.role,
            "reason": self.reason,
            "count": self.count,
        }


def _theme_label(value: str | None) -> str:
    return value if value is not None else "none"


def _index_universe(rows: tuple[UniverseRow, ...]) -> dict[str, UniverseRow]:
    return {row.instrument_id: row for row in rows}


def _count_rows(stage: str, status: str, rows: tuple[UniverseRow, ...]) -> list[DiagnosticRow]:
    counts = Counter((row.asset_class, _theme_label(row.theme)) for row in rows)
    return [
        DiagnosticRow(stage, status, asset_class, theme, "", "", count)
        for (asset_class, theme), count in sorted(counts.items())
    ]


def _count_rejections(
    stage: str,
    result: HardFilterResult,
    universe_by_id: dict[str, UniverseRow],
) -> list[DiagnosticRow]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for rejection in result.rejected:
        row = universe_by_id.get(rejection.instrument_id)
        asset_class = row.asset_class if row is not None else "unknown"
        theme = _theme_label(row.theme) if row is not None else "unknown"
        for reason in rejection.reasons:
            counts[(asset_class, theme, reason)] += 1
    return [
        DiagnosticRow(stage, "rejected", asset_class, theme, "", reason, count)
        for (asset_class, theme, reason), count in sorted(counts.items())
    ]


def _count_roles(bucketed: RoleBucketResult) -> list[DiagnosticRow]:
    rows = [
        DiagnosticRow("role_bucket", "bucketed", "", "", role, "", len(items))
        for role, items in sorted(bucketed.buckets.items())
    ]
    rows.extend(
        DiagnosticRow("role_bucket", "relaxed", "", "", role, "below min_candidates_per_role", len(bucketed.buckets.get(role, ())))
        for role in sorted(bucketed.relaxed_roles)
    )
    rows.extend(
        DiagnosticRow("role_bucket", "failed", "", "", role, "below fail_below", len(bucketed.buckets.get(role, ())))
        for role in sorted(bucketed.failed_roles)
    )
    return rows


def build_discovery_diagnostics(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame:
    universe_by_id = _index_universe(universe)
    rows: list[DiagnosticRow] = []
    rows.extend(_count_rows("universe", "input", universe))
    rows.extend(_count_rows("hard_filter", "passed", hard.passed))
    rows.extend(_count_rejections("hard_filter", hard, universe_by_id))
    rows.extend(_count_rows("quality_filter", "passed", quality.passed))
    rows.extend(_count_rejections("quality_filter", quality, universe_by_id))
    rows.extend(_count_roles(bucketed))
    return pd.DataFrame([row.as_dict() for row in rows], columns=list(DIAGNOSTIC_COLUMNS))
```

- [ ] **Step 4: Add diagnostics-aware pipeline entry point**

In `src/irc/discovery/pipeline.py`, add these imports near the top:

```python
from dataclasses import dataclass

from irc.discovery.diagnostics import build_discovery_diagnostics
```

Add this dataclass after `_MAX_REFS_PER_INSTRUMENT`:

```python
@dataclass(frozen=True)
class DiscoveryRunResult:
    watchlist: pd.DataFrame
    diagnostics: pd.DataFrame
```

Replace the body of `run_discovery()` with this compatibility wrapper:

```python
def run_discovery(
    universe: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    metrics: pd.DataFrame,
    risk_band_max_dd_upper: float,
    cfg_overrides: OverridesConfig | None,
    cfg_discovery: DiscoveryConfig | None,
    route: Any,
    peer_summary: str,
    macro_snapshot: str,
    raw_ref_pool: tuple[str, ...],
    excluded_themes: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Compose discovery 5 steps end-to-end. Returns watchlist DataFrame."""
    return run_discovery_with_diagnostics(
        universe=universe,
        metadata=metadata,
        metrics=metrics,
        risk_band_max_dd_upper=risk_band_max_dd_upper,
        cfg_overrides=cfg_overrides,
        cfg_discovery=cfg_discovery,
        route=route,
        peer_summary=peer_summary,
        macro_snapshot=macro_snapshot,
        raw_ref_pool=raw_ref_pool,
        excluded_themes=excluded_themes,
    ).watchlist
```

Then add `run_discovery_with_diagnostics()` immediately below `run_discovery()` using the old `run_discovery()` body plus diagnostics construction:

```python
def run_discovery_with_diagnostics(
    universe: tuple[UniverseRow, ...],
    metadata: pd.DataFrame,
    metrics: pd.DataFrame,
    risk_band_max_dd_upper: float,
    cfg_overrides: OverridesConfig | None,
    cfg_discovery: DiscoveryConfig | None,
    route: Any,
    peer_summary: str,
    macro_snapshot: str,
    raw_ref_pool: tuple[str, ...],
    excluded_themes: tuple[str, ...] = (),
) -> DiscoveryRunResult:
    cfg_d = cfg_discovery or _default_cfg()
    cfg_o = cfg_overrides or OverridesConfig()
    risk = RiskBand.model_validate({
        "max_drawdown": [0.05, risk_band_max_dd_upper],
        "horizon": "long_core_medium_rotation",
    })
    hard = apply_hard_filter(universe, metadata, cfg_d, cfg_o, excluded_themes=excluded_themes)
    quality = apply_quality_filter(hard.passed, metrics, cfg_d, risk)
    bucketed = bucket_by_role(
        quality.passed,
        cfg_d.role_bucket.min_candidates_per_role,
        cfg_d.role_bucket.fail_below,
    )
    refs_by_instrument = _index_refs_by_instrument(raw_ref_pool)
    rows: list[dict[str, Any]] = []
    for role, items in bucketed.buckets.items():
        for r in items:
            ctx = WriteReasonContext(
                role=role,
                peer_summary=peer_summary,
                macro_snapshot=macro_snapshot,
                raw_refs=refs_by_instrument.get(r.instrument_id, ()),
            )
            res = write_reason(r, ctx, route=route)
            if res is None:
                continue
            rows.append({
                "instrument_id": r.instrument_id,
                "ticker": r.ticker,
                "market": r.market,
                "name_cn": r.name_cn,
                "asset_class": r.asset_class,
                "currency": r.currency,
                "tracked_index": r.tracked_index or "",
                "venue_required": ",".join(r.venue_required),
                "role": role,
                "reason_text": res.reason_text,
                "cited_refs": ",".join(res.cited_refs),
                "relaxed": role in bucketed.relaxed_roles,
            })
    diagnostics = build_discovery_diagnostics(universe, hard, quality, bucketed)
    return DiscoveryRunResult(
        watchlist=pd.DataFrame(rows, columns=list(_WATCHLIST_COLUMNS)),
        diagnostics=diagnostics,
    )
```

- [ ] **Step 5: Run diagnostics and pipeline tests**

Run:

```bash
uv run pytest tests/discovery/test_diagnostics.py tests/discovery/test_pipeline.py -q
```

Expected: PASS, and existing `run_discovery()` tests still pass because the public return type remains `pd.DataFrame`.

- [ ] **Step 6: Commit diagnostics model**

Run:

```bash
git add src/irc/discovery/diagnostics.py src/irc/discovery/pipeline.py tests/discovery/test_diagnostics.py tests/discovery/test_pipeline.py
git commit -m "feat: collect discovery funnel diagnostics"
```

Expected: commit succeeds.

---

### Task 6: Write Diagnostics From Discover Command

**Files:**
- Modify: `src/irc/commands/discover_cmd.py`
- Test: `tests/commands/test_discover_cmd.py`

- [ ] **Step 1: Add failing discover command tests**

Append this test to `tests/commands/test_discover_cmd.py`:

```python
def test_discover_writes_diagnostics_csv(repo_with_db: Path) -> None:
    fake_resp_text = (
        "Reason: tracks SP500 (openbb:prices:006075:2026-05-06). Risk: USD strength."
    )
    with patch("irc.discovery.reason_writer.call_chat") as mock_chat:
        mock_chat.return_value.__class__ = type(
            "ChatResponse", (), {
                "text": fake_resp_text, "prompt_tokens": 10, "completion_tokens": 5,
            }
        )()
        mock_chat.return_value.text = fake_resp_text
        mock_chat.return_value.prompt_tokens = 10
        mock_chat.return_value.completion_tokens = 5
        rc = run_discover(repo_root=str(repo_with_db))

    assert rc == 0
    out_dir = next(p for p in (repo_with_db / "outputs").iterdir())
    diagnostics_path = out_dir / "discovery_diagnostics.csv"
    assert diagnostics_path.exists()
    df = pd.read_csv(diagnostics_path)
    assert {"stage", "status", "asset_class", "theme", "role", "reason", "count"}.issubset(df.columns)
    assert "universe" in set(df["stage"])
```

Update `test_discover_passes_excluded_themes_to_pipeline` so the mocked return value matches the new command call:

```python
def test_discover_passes_excluded_themes_to_pipeline(repo_with_db: Path) -> None:
    from irc.discovery.pipeline import DiscoveryRunResult

    preferences_path = repo_with_db / "inputs" / "preferences.yaml"
    preferences_path.write_text(
        preferences_path.read_text(encoding="utf-8").replace(
            "exclude_themes: []",
            "exclude_themes: [healthcare]",
        ),
        encoding="utf-8",
    )

    with patch("irc.commands.discover_cmd.run_discovery_with_diagnostics") as mock_run:
        mock_run.return_value = DiscoveryRunResult(
            watchlist=pd.DataFrame(columns=["instrument_id"]),
            diagnostics=pd.DataFrame(columns=["stage", "status", "asset_class", "theme", "role", "reason", "count"]),
        )
        rc = run_discover(repo_root=str(repo_with_db))

    assert rc == 0
    assert mock_run.call_args.kwargs["excluded_themes"] == ("healthcare",)
```

- [ ] **Step 2: Run discover command tests to verify they fail**

Run:

```bash
uv run pytest tests/commands/test_discover_cmd.py -q
```

Expected: FAIL because `run_discover()` still calls `run_discovery()` and writes no diagnostics CSV.

- [ ] **Step 3: Update discover command to write diagnostics**

In `src/irc/commands/discover_cmd.py`, replace this import:

```python
from irc.discovery.pipeline import run_discovery
```

with this import:

```python
from irc.discovery.pipeline import run_discovery_with_diagnostics
```

Then replace the `df = run_discovery(...)` block and output writes in `run_discover()` with this code:

```python
    result = run_discovery_with_diagnostics(
        universe=universe,
        metadata=metadata,
        metrics=metrics,
        risk_band_max_dd_upper=bundle.preferences.risk_band.max_drawdown[1],
        cfg_overrides=bundle.overrides,
        cfg_discovery=bundle.discovery,
        route=route,
        peer_summary="See universe peers in same role bucket.",
        macro_snapshot="See macro_series in DuckDB.",
        raw_ref_pool=ref_pool,
        excluded_themes=tuple(bundle.preferences.constraints.exclude_themes),
    )
    out_dir = root / "outputs" / _now_iso_date()
    out_dir.mkdir(parents=True, exist_ok=True)
    watchlist_path = out_dir / "discovered_watchlist.csv"
    diagnostics_path = out_dir / "discovery_diagnostics.csv"
    atomic_write_text(watchlist_path, result.watchlist.to_csv(index=False))
    atomic_write_text(diagnostics_path, result.diagnostics.to_csv(index=False))
    print(f"discover OK: {len(result.watchlist)} candidates -> {watchlist_path}")
    print(f"diagnostics OK: {len(result.diagnostics)} rows -> {diagnostics_path}")
    return 0
```

- [ ] **Step 4: Run discover command tests**

Run:

```bash
uv run pytest tests/commands/test_discover_cmd.py -q
```

Expected: PASS, and every discover run writes both CSV files.

- [ ] **Step 5: Commit discover diagnostics output**

Run:

```bash
git add src/irc/commands/discover_cmd.py tests/commands/test_discover_cmd.py
git commit -m "feat: write discovery diagnostics CSV"
```

Expected: commit succeeds.

---

### Task 7: Filter Calibration Knobs

**Files:**
- Modify: `src/irc/schemas/discovery.py`
- Modify: `src/irc/discovery/hard_filter.py`
- Modify: `src/irc/discovery/quality_filter.py`
- Modify: `config/discovery.yaml`
- Modify: `src/irc/templates/config/discovery.yaml`
- Test: `tests/discovery/test_hard_filter.py`
- Test: `tests/discovery/test_quality_filter.py`

- [ ] **Step 1: Add failing hard-filter calibration tests**

Append these tests to `tests/discovery/test_hard_filter.py`:

```python
def test_hard_filter_uses_qdii_feeder_expense_cap_for_off_exchange_us_or_hk_funds() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "006075", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.008, "daily_volume_cny": float("nan"),
    }])
    out = apply_hard_filter(
        rows=(_row("006075", "us_etf", market="cn_off_exchange"),),
        metadata=metadata,
        cfg=_cfg(),
        overrides=OverridesConfig(),
    )

    assert [row.instrument_id for row in out.passed] == ["006075"]


def test_hard_filter_keeps_tight_expense_cap_for_on_exchange_qdii_etf() -> None:
    metadata = pd.DataFrame([{
        "instrument_id": "513500", "inception_years": 5, "aum_cny": 6e8,
        "expense_ratio": 0.008, "daily_volume_cny": 2e7,
    }])
    out = apply_hard_filter(
        rows=(_row("513500", "us_etf", market="cn_on_exchange"),),
        metadata=metadata,
        cfg=_cfg(),
        overrides=OverridesConfig(),
    )

    assert out.passed == ()
    assert any("expense_ratio" in reason for reason in out.rejected[0].reasons)
```

Modify `_cfg()` in `tests/discovery/test_hard_filter.py` to include the new field:

```python
            "us_etf_expense_ratio_max": 0.003,
            "qdii_feeder_expense_ratio_max": 0.012,
```

- [ ] **Step 2: Add failing quality-filter calibration tests**

Append these tests to `tests/discovery/test_quality_filter.py`:

```python
def _asset_row(iid: str, asset_class: str, market: str = "cn_off_exchange") -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market=market,
        name_cn=iid, asset_class=asset_class, currency="cny",
        tracked_index=None, theme=None, venue_required=(),
    )


def test_quality_filter_uses_asset_class_drawdown_buffer_override() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "F", "drawdown_3y": 0.30,
        "tracking_error": None, "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_asset_row("F", "cn_equity_fund"),), metrics=metrics, cfg=_cfg(), risk_band=risk)

    assert [row.instrument_id for row in out.passed] == ["F"]


def test_quality_filter_uses_tighter_drawdown_buffer_for_cn_bond_fund() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "B", "drawdown_3y": 0.15,
        "tracking_error": None, "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_asset_row("B", "cn_bond_fund"),), metrics=metrics, cfg=_cfg(), risk_band=risk)

    assert out.passed == ()
    assert any("drawdown_3y" in reason for reason in out.rejected[0].reasons)
```

Modify `_cfg()` in `tests/discovery/test_quality_filter.py` so `quality_filters` contains:

```python
        "quality_filters": {
            "drawdown_3y_buffer": 1.2,
            "drawdown_3y_buffer_by_asset_class": {"cn_equity_fund": 1.6, "cn_bond_fund": 0.6},
            "tracking_error_max": 0.015,
            "manager_tenure_years_min": 2,
        },
```

- [ ] **Step 3: Run calibration tests to verify they fail**

Run:

```bash
uv run pytest tests/discovery/test_hard_filter.py::test_hard_filter_uses_qdii_feeder_expense_cap_for_off_exchange_us_or_hk_funds tests/discovery/test_hard_filter.py::test_hard_filter_keeps_tight_expense_cap_for_on_exchange_qdii_etf tests/discovery/test_quality_filter.py::test_quality_filter_uses_asset_class_drawdown_buffer_override tests/discovery/test_quality_filter.py::test_quality_filter_uses_tighter_drawdown_buffer_for_cn_bond_fund -q
```

Expected: FAIL because schema and filters do not yet support the new knobs.

- [ ] **Step 4: Extend discovery schema defaults**

In `src/irc/schemas/discovery.py`, change `HardFilters` and `QualityFilters` to this code:

```python
class HardFilters(FrozenModel):
    inception_years_min: int = Field(ge=0)
    cn_fund_aum_cny_min: float = Field(ge=0)
    us_etf_aum_usd_min: float = Field(ge=0)
    cn_active_expense_ratio_max: float = Field(ge=0, le=1)
    cn_passive_expense_ratio_max: float = Field(ge=0, le=1)
    us_etf_expense_ratio_max: float = Field(ge=0, le=1)
    qdii_feeder_expense_ratio_max: float = Field(default=0.012, ge=0, le=1)
    etf_daily_volume_cny_min: float = Field(ge=0)


class QualityFilters(FrozenModel):
    drawdown_3y_buffer: float = Field(gt=0)
    drawdown_3y_buffer_by_asset_class: dict[str, float] = Field(default_factory=dict)
    tracking_error_max: float = Field(ge=0, le=1)
    manager_tenure_years_min: float = Field(ge=0)
```

- [ ] **Step 5: Update hard-filter expense routing**

In `src/irc/discovery/hard_filter.py`, replace `_expense_max()` with this code:

```python
def _expense_max(row: UniverseRow, hf) -> float:
    if row.asset_class in ("us_etf", "hk_etf") and row.market == "cn_off_exchange":
        return hf.qdii_feeder_expense_ratio_max
    if row.asset_class in ("us_etf", "hk_etf"):
        return hf.us_etf_expense_ratio_max
    if "etf" in row.asset_class:
        return hf.cn_passive_expense_ratio_max
    return hf.cn_active_expense_ratio_max
```

Then replace this line inside `apply_hard_filter()`:

```python
            er_max = _expense_max(row.asset_class, hf)
```

with this line:

```python
            er_max = _expense_max(row, hf)
```

- [ ] **Step 6: Update quality-filter drawdown routing**

In `src/irc/discovery/quality_filter.py`, add this helper before `apply_quality_filter()`:

```python
def _drawdown_max(row: UniverseRow, cfg: DiscoveryConfig, risk_band: RiskBand) -> float:
    buffer = cfg.quality_filters.drawdown_3y_buffer_by_asset_class.get(
        row.asset_class,
        cfg.quality_filters.drawdown_3y_buffer,
    )
    return risk_band.max_drawdown[1] * buffer
```

Then remove the single `dd_max = risk_band.max_drawdown[1] * qf.drawdown_3y_buffer` assignment and insert this line inside the `else:` block before checking `drawdown`:

```python
            dd_max = _drawdown_max(row, cfg, risk_band)
```

- [ ] **Step 7: Update config defaults**

In both `config/discovery.yaml` and `src/irc/templates/config/discovery.yaml`, change the config to:

```yaml
hard_filters:
  inception_years_min: 3
  cn_fund_aum_cny_min: 500000000
  us_etf_aum_usd_min: 100000000
  cn_active_expense_ratio_max: 0.015
  cn_passive_expense_ratio_max: 0.005
  us_etf_expense_ratio_max: 0.003
  qdii_feeder_expense_ratio_max: 0.012
  etf_daily_volume_cny_min: 10000000

quality_filters:
  drawdown_3y_buffer: 1.2
  drawdown_3y_buffer_by_asset_class:
    gold: 1.35
    cn_equity_fund: 1.6
    cn_etf: 1.4
    cn_bond_fund: 0.6
    hk_etf: 1.4
    us_etf: 1.4
  tracking_error_max: 0.015
  manager_tenure_years_min: 2

role_bucket:
  min_candidates_per_role: 8
  fail_below: 5
```

- [ ] **Step 8: Run filter and config tests**

Run:

```bash
uv run pytest tests/discovery/test_hard_filter.py tests/discovery/test_quality_filter.py tests/test_config_loader.py -q
```

Expected: PASS, including existing old-config tests because the new schema fields have defaults.

- [ ] **Step 9: Commit calibration knobs**

Run:

```bash
git add src/irc/schemas/discovery.py src/irc/discovery/hard_filter.py src/irc/discovery/quality_filter.py config/discovery.yaml src/irc/templates/config/discovery.yaml tests/discovery/test_hard_filter.py tests/discovery/test_quality_filter.py
git commit -m "feat: calibrate discovery filters by fund class"
```

Expected: commit succeeds.

---

### Task 8: Mocked End-to-End Generated Universe Smoke

**Files:**
- Create: `tests/integration/test_generated_cn_fund_discovery.py`

- [ ] **Step 1: Write the failing mocked e2e smoke test**

Create `tests/integration/test_generated_cn_fund_discovery.py` with this content:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from irc.commands.discover_cmd import run_discover
from irc.commands.ingest_cmd import run_ingest
from irc.commands.init_cmd import run_init
from irc.commands.universe_cmd import run_build_cn_funds


def _catalog() -> pd.DataFrame:
    return pd.DataFrame([
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
        {"fund_code": "003096", "fund_name": "中欧医疗健康混合C", "fund_type": "混合型"},
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"},
        {"fund_code": "006075", "fund_name": "易方达标普500人民币A", "fund_type": "QDII"},
        {"fund_code": "000001", "fund_name": "华夏现金增利货币A", "fund_type": "货币型"},
    ])


def _metadata(fund_code: str) -> dict[str, object]:
    return {
        "fund_code": fund_code,
        "name_cn": fund_code,
        "fund_type": "mock",
        "aum_text": "20亿元",
        "inception_date": "2018-01-01",
        "expense_ratio": 0.012 if fund_code == "003095" else 0.002,
        "manager_tenure_years": 5,
    }


def _nav_history(_: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2024-01-01", "nav": 1.00, "nav_acc": 1.00},
        {"date": "2025-01-01", "nav": 1.10, "nav_acc": 1.10},
        {"date": "2026-01-01", "nav": 1.20, "nav_acc": 1.20},
    ])


def _price_history(**_: object) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2024-01-01", "open": 1.00, "high": 1.01, "low": 0.99, "close": 1.00, "volume": 20_000_000},
        {"date": "2025-01-01", "open": 1.05, "high": 1.06, "low": 1.04, "close": 1.05, "volume": 20_000_000},
        {"date": "2026-01-01", "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.10, "volume": 20_000_000},
    ])


def _macro_series(**_: object) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-01-01", "value": 1.0},
    ])


def test_generated_cn_fund_universe_flows_through_ingest_and_discover(tmp_path: Path) -> None:
    assert run_init(str(tmp_path), force=False) == 0
    discovery_path = tmp_path / "config" / "discovery.yaml"
    discovery_path.write_text(
        discovery_path.read_text(encoding="utf-8")
        .replace("min_candidates_per_role: 8", "min_candidates_per_role: 1")
        .replace("fail_below: 5", "fail_below: 0"),
        encoding="utf-8",
    )

    with patch("irc.commands.universe_cmd.fetch_open_fund_catalog", return_value=_catalog()):
        assert run_build_cn_funds(str(tmp_path)) == 0

    with patch("irc.commands.ingest_cmd.fetch_fund_metadata", side_effect=_metadata), \
         patch("irc.commands.ingest_cmd.fetch_etf_metadata_em", side_effect=_metadata), \
         patch("irc.commands.ingest_cmd.fetch_fund_nav_history", side_effect=_nav_history), \
         patch("irc.commands.ingest_cmd.fetch_etf_price_history", side_effect=_price_history), \
         patch("irc.commands.ingest_cmd.fetch_macro_series", side_effect=_macro_series):
        assert run_ingest(str(tmp_path)) == 0

    fake_resp_text = "Reason: active healthcare fund. Risk: sector concentration."
    with patch("irc.discovery.reason_writer.call_chat") as mock_chat:
        mock_chat.return_value.__class__ = type(
            "ChatResponse", (), {
                "text": fake_resp_text, "prompt_tokens": 10, "completion_tokens": 5,
            }
        )()
        mock_chat.return_value.text = fake_resp_text
        mock_chat.return_value.prompt_tokens = 10
        mock_chat.return_value.completion_tokens = 5
        assert run_discover(str(tmp_path)) == 0

    out_dir = next(path for path in (tmp_path / "outputs").iterdir())
    watchlist = pd.read_csv(out_dir / "discovered_watchlist.csv", dtype={"instrument_id": str})
    diagnostics = pd.read_csv(out_dir / "discovery_diagnostics.csv")

    assert "003095" in set(watchlist["instrument_id"])
    active = watchlist.loc[watchlist["instrument_id"] == "003095"].iloc[0]
    assert active["asset_class"] == "cn_equity_fund"
    assert active["role"] == "satellite_cn_healthcare"
    assert "cn_equity_fund" in set(diagnostics["asset_class"])
```

- [ ] **Step 2: Run the mocked e2e test to verify it fails if previous tasks are absent**

Run:

```bash
uv run pytest tests/integration/test_generated_cn_fund_discovery.py -q
```

Expected before Tasks 1-7: FAIL. Expected after Tasks 1-7: PASS.

- [ ] **Step 3: Run focused integration plus command tests**

Run:

```bash
uv run pytest tests/integration/test_generated_cn_fund_discovery.py tests/commands/test_universe_cmd.py tests/commands/test_discover_cmd.py -q
```

Expected: PASS, proving generated active funds can enter the real ingest/discover path with network mocked out.

- [ ] **Step 4: Commit e2e smoke**

Run:

```bash
git add tests/integration/test_generated_cn_fund_discovery.py
git commit -m "test: cover generated CN fund discovery flow"
```

Expected: commit succeeds.

---

### Task 9: Full Verification And Live Dry Run

**Files:**
- No source files created in this task.
- Verify: whole repo test suite and optional live commands.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
uv run pytest --tb=short -q
```

Expected: PASS, all tests pass.

- [ ] **Step 2: Run config validation**

Run:

```bash
uv run irc config validate --repo-root .
```

Expected: PASS with `OK: all` and a universe size count. The generated file is optional, so validation passes whether `config/universe/cn_funds.generated.yaml` exists or not.

- [ ] **Step 3: Run mocked-free generated universe build when network access is acceptable**

Run:

```bash
uv run irc universe build-cn-funds --repo-root .
```

Expected: exit code 0, `config/universe/cn_funds.generated.yaml` is written, and stdout includes counts such as `cn_equity_fund/none`, `cn_equity_fund/healthcare`, `cn_bond_fund/none`, or `cn_etf/broad` depending on live Akshare catalog contents.

- [ ] **Step 4: Validate generated YAML**

Run:

```bash
uv run irc config validate --repo-root .
```

Expected: PASS with a larger universe size than before the generated file existed.

- [ ] **Step 5: Run ingest and discover when live data sources are acceptable**

Run:

```bash
uv run irc ingest --repo-root .
uv run irc discover --repo-root .
```

Expected: both commands exit 0. `outputs/<today>/discovered_watchlist.csv` and `outputs/<today>/discovery_diagnostics.csv` exist. If the watchlist is still ETF-only, the diagnostics CSV has rejection counts that identify whether active funds were removed by metadata, hard filters, quality filters, or role bucketing.

- [ ] **Step 6: Inspect generated active-fund coverage**

Run:

```bash
python - <<'PY'
from pathlib import Path
import yaml

path = Path('config/universe/cn_funds.generated.yaml')
raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {'instruments': []}
active = [row for row in raw['instruments'] if row.get('asset_class') == 'cn_equity_fund']
print(f'generated active cn_equity_fund count: {len(active)}')
print(active[:5])
PY
```

Expected: active count is greater than 0 for a normal Akshare catalog response.

- [ ] **Step 7: Commit live-generated file only if the project wants it versioned**

If `config/universe/cn_funds.generated.yaml` is intended to be committed, run:

```bash
git add config/universe/cn_funds.generated.yaml
git commit -m "data: add generated CN fund universe snapshot"
```

Expected: commit succeeds. If the generated file should stay local, leave it uncommitted.

---

## Self-Review Notes

- Spec coverage: Tasks 1-3 cover Akshare catalog generation, deterministic classification, exclusions, share-class dedupe, caps, generated YAML, and counts. Task 4 covers optional loading and curated-wins dedupe. Tasks 5-6 cover diagnostics output. Task 7 covers fee, drawdown, and tenure-related calibration without changing the existing manager-tenure boundary. Task 8 covers mocked generated active funds flowing through ingest and discover. Task 9 covers full verification and live rollout.
- Placeholder scan: This plan contains concrete file paths, test code, implementation code, commands, and expected outcomes for every task. It does not leave undecided markers for future workers.
- Type consistency: The plan uses existing `Instrument`, `UniverseConfig`, `UniverseRow`, `HardFilterResult`, `RoleBucketResult`, `DiscoveryConfig`, and `RiskBand` names consistently. New public names are `CatalogFund`, `ClassifiedFund`, `UniverseBuildOptions`, `fetch_open_fund_catalog`, `run_build_cn_funds`, `DiagnosticRow`, `build_discovery_diagnostics`, `DiscoveryRunResult`, and `run_discovery_with_diagnostics`.