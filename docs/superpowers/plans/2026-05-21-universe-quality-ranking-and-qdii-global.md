# Universe Quality-Weighted Ranking + qdii_global Asset Class — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fund_code-ascending tiebreaker in `_candidate_rank` with a 1Y-return quality signal so the universe's per-bucket caps select the best performers instead of the oldest funds, and add a `qdii_global` asset_class so global-mandate QDII active funds compete in their own bucket instead of being drowned in 5,500+ broad-active equity candidates.

**Architecture:** Two surgical, backward-compatible changes to `src/irc/discovery/cn_fund_universe.py` and `src/irc/data/akshare_client.py`. Path A introduces an optional `returns` mapping that flows from `universe_cmd` → `build_cn_fund_universe` → `_apply_caps` → a new `_candidate_rank_with_returns` closure; when the mapping is missing or empty the old `(feeder_penalty, fund_code)` rank is preserved. Path C adds `qdii_global` to the `AssetClass` literal, splits the classifier path for QDII funds without US/HK markers, and gives the new bucket its own cap. Each change ships behind tests and a regeneration step.

**Tech Stack:** Python 3.13, pandas, pydantic (frozen models), akshare 1.18.60, pytest. Functional style — no class mutation, pure transforms, immutable dataclasses.

---

## Context the implementer needs

**Why this plan exists.** Today the discovery pipeline picks 40 broad-active CN equity funds out of ~5,545 candidates by sorting on `fund_code` ascending. The fund `270023 广发全球精选股票(QDII)人民币A` ranks 5087/5545 and is dropped despite strong returns. The same dumb sort silently drops every high-numbered fund regardless of quality. We need a signal correlated with what users care about. Path A fixes the ranking. Path C ensures global-mandate QDII active funds don't compete against domestic mixed/equity for the same 40 slots.

**Files in scope.**
- `src/irc/discovery/cn_fund_universe.py` — generator (read it end-to-end first; it's 325 lines and the whole pipeline lives there).
- `src/irc/data/akshare_client.py:188-231` — current catalog fetcher (`_raw_fund_table_call`, `fetch_open_fund_catalog`). New `fetch_open_fund_ranks` mirrors the lru_cache pattern.
- `src/irc/schemas/_types.py:5-9` — `AssetClass` Literal; add `qdii_global` there.
- `src/irc/commands/universe_cmd.py` — wiring layer; passes `returns` through.
- `tests/discovery/test_cn_fund_universe.py` — primary unit-test home.
- `tests/discovery/test_universe.py`, `tests/integration/test_generated_cn_fund_discovery.py` — may need additions for the qdii_global path.
- `config/universe/cn_funds.generated.yaml` — regenerated artifact; commit the new version.

**Key reading before starting.**
- `_candidate_rank` lives at `src/irc/discovery/cn_fund_universe.py:263-265`.
- `_apply_caps` at `src/irc/discovery/cn_fund_universe.py:268-276`.
- `_infer_asset_class` at `src/irc/discovery/cn_fund_universe.py:156-169` — note the QDII branches (`is_qdii and US_MARKERS → us_etf`; `is_qdii and HK_MARKERS → hk_etf`). QDII funds without those markers fall through to the cn_equity_fund / cn_bond_fund branches.
- `build_cn_fund_universe` at `src/irc/discovery/cn_fund_universe.py:306-315`.

**Akshare endpoint notes.** `akshare.fund_open_fund_rank_em(symbol=...)` returns a DataFrame with columns including `基金代码`, `基金简称`, `近1年`, `近3年`, `成立来`, etc. The `symbol` parameter takes one of: `"全部"`, `"股票型"`, `"混合型"`, `"债券型"`, `"指数型"`, `"QDII"`, `"LOF"`, `"FOF"`. The `"全部"` symbol is preferred — single call. If `"全部"` is unavailable in 1.18.60, fall back to iterating the type list and concatenating. **Task 1 verifies which symbol works.**

**Style guardrails (from CLAUDE.md).** Pure functions, no mutation, immutable dataclasses, return new objects via spread. Each function < 20 lines ideal. Tests before implementation. Frequent commits.

---

## File Structure

**New code:**
- `src/irc/data/akshare_client.py` — add `_raw_fund_rank_call()`, `_fetch_full_fund_rank_table()`, `fetch_open_fund_ranks()`. Mirror the catalog-fetcher trio.
- `src/irc/discovery/cn_fund_universe.py` — add `_candidate_rank_with_returns()` closure, extend `_apply_caps` signature, extend `build_cn_fund_universe` signature, add `qdii_global` branch in `_infer_asset_class`, add `qdii_global_cap` to `UniverseBuildOptions`, extend `_cap_for` and `_tracked_index_for`.

**Modified:**
- `src/irc/schemas/_types.py` — add `qdii_global` to `AssetClass` Literal.
- `src/irc/commands/universe_cmd.py` — fetch ranks, pass to builder.
- `config/universe/cn_funds.generated.yaml` — regenerated.

**Test files modified:**
- `tests/discovery/test_cn_fund_universe.py` — unit tests for new ranking, new asset class, builder integration.
- `tests/data/test_akshare_client.py` (locate or create alongside existing tests) — mock-based test for `fetch_open_fund_ranks`.

---

## Task 1: Probe akshare and lock the endpoint contract

**Files:**
- Probe-only: no files modified.

This task answers two questions before we commit code: (1) does `fund_open_fund_rank_em(symbol="全部")` work in 1.18.60? (2) what columns does it return? The answers gate Task 2's implementation choices.

- [ ] **Step 1: Run the probe**

```bash
.venv/bin/python -c "
import akshare as ak
for symbol in ('全部', '股票型', 'QDII'):
    try:
        df = ak.fund_open_fund_rank_em(symbol=symbol)
        print(f'symbol={symbol!r} rows={len(df)} cols={list(df.columns)}')
        hit = df[df.iloc[:, 0].astype(str) == '270023'] if len(df) else df.iloc[0:0]
        if len(hit):
            print('  270023 row:', dict(hit.iloc[0]))
    except Exception as e:
        print(f'symbol={symbol!r} FAILED: {e}')
"
```

Expected: at least one symbol succeeds and the row for `270023` includes a `近1年` (1-year return) column with a percent-formatted value like `'45.32%'` or numeric `45.32`. Record the working symbol and exact column names for Task 2.

- [ ] **Step 2: Record findings inline below**

After running, paste the working symbol(s) and column list into this file as a one-paragraph "Probe results" note. If `'全部'` works, the implementation is one call. If only per-type symbols work, the implementation iterates `("股票型", "混合型", "债券型", "指数型", "QDII", "LOF", "FOF")` and concatenates.

**Probe results (2026-05-21):** `fund_open_fund_rank_em(symbol="全部")` works in akshare 1.18.60, returning 19,584 rows with columns: `['序号', '基金代码', '基金简称', '日期', '单位净值', '累计净值', '日增长率', '近1周', '近1月', '近3月', '近6月', '近1年', '近2年', '近3年', '今年来', '成立来', '自定义', '手续费']`. The `近1年` column is already **numeric** (float, not percent-string) — `270023` row: `近1年=54.85` (54.85% 1-year return). The `基金代码` column is the fund code string. Implementation uses the single-call form with `symbol="全部"`. The `_parse_percent` helper must handle both numeric floats and `"--"` strings (the `自定义` column is NaN for most rows, so the pattern holds).

- [ ] **Step 3: Commit the probe note**

```bash
git add docs/superpowers/plans/2026-05-21-universe-quality-ranking-and-qdii-global.md
git commit -m "docs(plan): record akshare fund_open_fund_rank_em probe results"
```

---

## Task 2: Add `fetch_open_fund_ranks` to akshare_client (TDD)

**Files:**
- Modify: `src/irc/data/akshare_client.py` (add after line 231)
- Test: `tests/data/test_akshare_client.py` (locate existing file; if absent, create — `find tests -name "test_akshare*"`)

- [ ] **Step 1: Write the failing test**

Add to the test file. The test mocks `_ak_call` at the akshare_client module boundary — same pattern as existing tests in that file (search for `monkeypatch.setattr` against `_ak_call` to match the style).

```python
def test_fetch_open_fund_ranks_normalizes_columns_and_parses_percentages(monkeypatch):
    import pandas as pd
    from irc.data import akshare_client

    mock_df = pd.DataFrame([
        {"基金代码": "270023", "基金简称": "广发全球精选股票(QDII)人民币A",
         "近1年": "45.32%", "近3年": "12.10%", "成立来": "180.00%"},
        {"基金代码": "000001", "基金简称": "华夏成长混合",
         "近1年": "-3.50%", "近3年": "8.20%", "成立来": "120.00%"},
        {"基金代码": "999999", "基金简称": "无数据基金",
         "近1年": "--", "近3年": "", "成立来": "10.00%"},
    ])

    def fake_ak_call(name, **kwargs):
        assert name == "fund_open_fund_rank_em"
        return mock_df

    # Clear cache so the test sees the patched call.
    akshare_client._fetch_full_fund_rank_table.cache_clear()
    akshare_client.fetch_open_fund_ranks.cache_clear()
    monkeypatch.setattr(akshare_client, "_ak_call", fake_ak_call)

    out = akshare_client.fetch_open_fund_ranks()

    assert set(out.columns) >= {"fund_code", "return_1y"}
    assert out.loc[out["fund_code"] == "270023", "return_1y"].iloc[0] == 45.32
    assert out.loc[out["fund_code"] == "000001", "return_1y"].iloc[0] == -3.50
    # Missing returns become NaN (downstream treats NaN as "rank last").
    assert pd.isna(out.loc[out["fund_code"] == "999999", "return_1y"].iloc[0])
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/data/test_akshare_client.py::test_fetch_open_fund_ranks_normalizes_columns_and_parses_percentages -v
```

Expected: FAIL with `AttributeError: module 'irc.data.akshare_client' has no attribute 'fetch_open_fund_ranks'`.

- [ ] **Step 3: Implement minimal `fetch_open_fund_ranks`**

Add to `src/irc/data/akshare_client.py` immediately after the existing `fetch_open_fund_catalog` block (line 231). If Task 1 confirmed `"全部"` works, use the single-call form. Otherwise replace with the concat form (commented variant below).

```python
def _raw_fund_rank_call() -> pd.DataFrame:
    """Raw call to akshare's fund-rank table. Extracted for lru_cache wrapping."""
    return _ak_call("fund_open_fund_rank_em", symbol="全部")
    # Per-type fallback if "全部" is unavailable in 1.18.60:
    # frames = [
    #     _ak_call("fund_open_fund_rank_em", symbol=s)
    #     for s in ("股票型", "混合型", "债券型", "指数型", "QDII", "LOF", "FOF")
    # ]
    # return pd.concat(frames, ignore_index=True)


def _parse_percent(value: Any) -> float:
    """Convert '45.32%' / '-3.50%' / '--' / '' / NaN → float or NaN."""
    if value is None:
        return float("nan")
    text = str(value).strip().rstrip("%")
    if not text or text in {"--", "nan", "None"}:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


@lru_cache(maxsize=1)
def _fetch_full_fund_rank_table() -> pd.DataFrame:
    """Fetch the master fund-rank table with stable internal column names."""
    df = _raw_fund_rank_call()
    rename_map: dict[str, str] = {}
    if "基金代码" in df.columns:
        rename_map["基金代码"] = "fund_code"
    if "近1年" in df.columns:
        rename_map["近1年"] = "return_1y"
    df = df.rename(columns=rename_map)
    if "fund_code" in df.columns:
        df["fund_code"] = df["fund_code"].apply(_normalize_fund_code)
    if "return_1y" in df.columns:
        df["return_1y"] = df["return_1y"].apply(_parse_percent)
    return df


@lru_cache(maxsize=1)
def fetch_open_fund_ranks() -> pd.DataFrame:
    """Public accessor for the fund-rank table. Returns DataFrame with
    'fund_code' and 'return_1y' columns; return_1y is float (NaN for missing)."""
    df = _fetch_full_fund_rank_table()
    required = ["fund_code", "return_1y"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Akshare fund-rank table missing columns: {', '.join(missing)}")
    return df.loc[:, required].copy()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/data/test_akshare_client.py::test_fetch_open_fund_ranks_normalizes_columns_and_parses_percentages -v
```

Expected: PASS.

- [ ] **Step 5: Run the full akshare_client test file to confirm no regression**

```bash
.venv/bin/python -m pytest tests/data/test_akshare_client.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(akshare): add fetch_open_fund_ranks for 1Y-return quality signal"
```

---

## Task 3: Add `_candidate_rank_with_returns` closure (TDD)

**Files:**
- Modify: `src/irc/discovery/cn_fund_universe.py:263-265`
- Test: `tests/discovery/test_cn_fund_universe.py`

The closure preserves the original `_candidate_rank` for backward compatibility (empty/None returns → old behavior). New rank key: `(feeder_penalty, missing_return_penalty, -return_1y_or_0, fund_code)`. Funds with returns sort before funds without; among funds with returns, higher returns sort first; fund_code is the deterministic tiebreaker.

- [ ] **Step 1: Write the failing test**

Add to `tests/discovery/test_cn_fund_universe.py`:

```python
def test_candidate_rank_with_returns_prefers_higher_1y_return():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank_with_returns,
    )

    def make(code: str, name: str = "test fund") -> ClassifiedFund:
        return ClassifiedFund(
            catalog=CatalogFund(fund_code=code, fund_name=name, fund_type=""),
            asset_class="cn_equity_fund",
            market="cn_off_exchange",
            currency="cny",
            tracked_index=None,
            theme=None,
            venue_required=("cmb_fund",),
        )

    returns = {"270023": 45.3, "000001": -3.5, "100100": 12.0}
    items = [make("000001"), make("270023"), make("100100"), make("999999")]
    rank = _candidate_rank_with_returns(returns)
    ordered = sorted(items, key=rank)

    # 270023 (45.3%) first, then 100100 (12.0%), then 000001 (-3.5%),
    # then 999999 (no return — sorts last by fund_code among unranked).
    assert [it.catalog.fund_code for it in ordered] == ["270023", "100100", "000001", "999999"]


def test_candidate_rank_with_returns_falls_back_to_fund_code_when_empty():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank, _candidate_rank_with_returns,
    )

    def make(code: str) -> ClassifiedFund:
        return ClassifiedFund(
            catalog=CatalogFund(fund_code=code, fund_name="x", fund_type=""),
            asset_class="cn_equity_fund",
            market="cn_off_exchange",
            currency="cny",
            tracked_index=None,
            theme=None,
            venue_required=("cmb_fund",),
        )

    items = [make("270023"), make("000001"), make("100100")]
    legacy = sorted(items, key=_candidate_rank)
    via_empty_map = sorted(items, key=_candidate_rank_with_returns({}))

    assert [it.catalog.fund_code for it in legacy] == [it.catalog.fund_code for it in via_empty_map]


def test_candidate_rank_with_returns_preserves_feeder_penalty():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank_with_returns,
    )

    feeder = ClassifiedFund(
        catalog=CatalogFund(fund_code="000001", fund_name="某基金联接A", fund_type=""),
        asset_class="cn_equity_fund", market="cn_off_exchange", currency="cny",
        tracked_index=None, theme=None, venue_required=("cmb_fund",),
    )
    direct = ClassifiedFund(
        catalog=CatalogFund(fund_code="000002", fund_name="某基金A", fund_type=""),
        asset_class="cn_equity_fund", market="cn_off_exchange", currency="cny",
        tracked_index=None, theme=None, venue_required=("cmb_fund",),
    )

    # Feeder has a higher 1Y return but should still sort after direct because of penalty.
    returns = {"000001": 99.9, "000002": 1.0}
    ordered = sorted([feeder, direct], key=_candidate_rank_with_returns(returns))
    assert [it.catalog.fund_code for it in ordered] == ["000002", "000001"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -k candidate_rank_with_returns -v
```

Expected: FAIL with `ImportError: cannot import name '_candidate_rank_with_returns'`.

- [ ] **Step 3: Implement the closure**

Replace lines 263-265 of `src/irc/discovery/cn_fund_universe.py`:

```python
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
```

Add `Callable` to the typing imports at the top of the file (line 7: `from typing import Any, Callable`).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -k candidate_rank_with_returns -v
```

Expected: PASS for all three tests.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat(discovery): add _candidate_rank_with_returns for quality-weighted ranking"
```

---

## Task 4: Thread `returns` through `_apply_caps` and `build_cn_fund_universe` (TDD)

**Files:**
- Modify: `src/irc/discovery/cn_fund_universe.py:268-276` (`_apply_caps`) and `:306-315` (`build_cn_fund_universe`)
- Test: `tests/discovery/test_cn_fund_universe.py`

`returns` is an optional `Mapping[str, float]`. Default `None` → empty map → ranking equivalent to today.

- [ ] **Step 1: Write the failing test**

```python
def test_build_universe_uses_returns_to_select_high_performers_under_cap():
    from irc.discovery.cn_fund_universe import build_cn_fund_universe, UniverseBuildOptions

    rows = [
        {"fund_code": f"00010{i}", "fund_name": f"老基金{i}股票A", "fund_type": "股票型"}
        for i in range(5)
    ] + [
        {"fund_code": "270023", "fund_name": "广发新王者股票A", "fund_type": "股票型"},
    ]
    returns = {"270023": 50.0}  # everyone else has no return data
    options = UniverseBuildOptions(active_broad_cap=3)

    # Without returns: lowest 3 fund codes (000100, 000101, 000102) win.
    without = build_cn_fund_universe(rows, options=options)
    assert [it.instrument_id for it in without] == ["000100", "000101", "000102"]

    # With returns: 270023 jumps to position 1 because it has the only positive return.
    with_returns = build_cn_fund_universe(rows, options=options, returns=returns)
    ids = [it.instrument_id for it in with_returns]
    assert "270023" in ids
    assert len(ids) == 3
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py::test_build_universe_uses_returns_to_select_high_performers_under_cap -v
```

Expected: FAIL with `TypeError: build_cn_fund_universe() got an unexpected keyword argument 'returns'`.

- [ ] **Step 3: Update `_apply_caps` and `build_cn_fund_universe`**

Replace `_apply_caps` (lines 268-276):

```python
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
```

Replace `build_cn_fund_universe` (lines 306-315):

```python
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
```

- [ ] **Step 4: Run the new test plus the full discovery suite**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -v
```

Expected: all green (new test plus all existing tests — the default-`None`-returns path must not change behavior).

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat(discovery): thread optional returns map through cap selection"
```

---

## Task 5: Wire `fetch_open_fund_ranks` into `universe_cmd` (TDD)

**Files:**
- Modify: `src/irc/commands/universe_cmd.py`
- Test: `tests/commands/test_universe_cmd.py` (locate via `find tests -name "test_universe_cmd.py"`)

- [ ] **Step 1: Write the failing test**

Add to `tests/commands/test_universe_cmd.py`. The pattern should follow the existing test that mocks `fetch_open_fund_catalog` — read the file first and match the style.

```python
def test_run_build_cn_funds_passes_returns_to_builder(monkeypatch, tmp_path):
    import pandas as pd
    from irc.commands import universe_cmd

    captured: dict = {}

    def fake_catalog():
        return pd.DataFrame([
            {"fund_code": "270023", "fund_name": "广发全球精选股票(QDII)人民币A", "fund_type": ""},
            {"fund_code": "000001", "fund_name": "华夏成长混合", "fund_type": "混合型"},
        ])

    def fake_ranks():
        return pd.DataFrame([
            {"fund_code": "270023", "return_1y": 45.3},
            {"fund_code": "000001", "return_1y": -3.5},
        ])

    def fake_build(rows, options=None, returns=None):
        captured["returns"] = dict(returns or {})
        return ()

    monkeypatch.setattr(universe_cmd, "fetch_open_fund_catalog", fake_catalog)
    monkeypatch.setattr(universe_cmd, "fetch_open_fund_ranks", fake_ranks)
    monkeypatch.setattr(universe_cmd, "build_cn_fund_universe", fake_build)

    rc = universe_cmd.run_build_cn_funds(str(tmp_path))

    assert rc == 0
    assert captured["returns"] == {"270023": 45.3, "000001": -3.5}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/commands/test_universe_cmd.py::test_run_build_cn_funds_passes_returns_to_builder -v
```

Expected: FAIL — either `fetch_open_fund_ranks` not importable from `universe_cmd`, or `captured["returns"]` is `{}`.

- [ ] **Step 3: Update `universe_cmd`**

Replace the imports and `run_build_cn_funds` body in `src/irc/commands/universe_cmd.py`:

```python
from irc.data.akshare_client import fetch_open_fund_catalog, fetch_open_fund_ranks
from irc.discovery.cn_fund_universe import build_cn_fund_universe, serialize_universe
```

```python
def run_build_cn_funds(repo_root: str) -> int:
    root = Path(repo_root)
    generated_path = root / "config" / "universe" / "cn_funds.generated.yaml"
    try:
        catalog = fetch_open_fund_catalog()
        try:
            ranks_df = fetch_open_fund_ranks()
            returns = {
                row["fund_code"]: float(row["return_1y"])
                for row in ranks_df.to_dict("records")
                if row.get("return_1y") == row.get("return_1y")  # NaN filter
            }
        except Exception as rank_exc:  # noqa: BLE001 - rank table is optional quality signal
            print(f"WARN: fund-rank fetch failed ({rank_exc}); falling back to fund_code rank", file=sys.stderr)
            returns = {}
        instruments = build_cn_fund_universe(catalog.to_dict("records"), returns=returns)
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

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/commands/test_universe_cmd.py -v
```

Expected: all green including the new test.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/universe_cmd.py tests/commands/test_universe_cmd.py
git commit -m "feat(universe-cmd): fetch fund ranks and pass to builder"
```

---

## Task 6: Add `qdii_global` to the `AssetClass` literal (TDD)

**Files:**
- Modify: `src/irc/schemas/_types.py:5-9`
- Test: `tests/schemas/test_universe.py` (locate via `find tests -name "test_universe*"`)

- [ ] **Step 1: Write the failing test**

Add to `tests/schemas/test_universe.py`:

```python
def test_instrument_accepts_qdii_global_asset_class():
    from irc.schemas.universe import Instrument

    inst = Instrument.model_validate({
        "instrument_id": "270023",
        "ticker": "270023",
        "market": "cn_off_exchange",
        "name_cn": "广发全球精选股票(QDII)人民币A",
        "asset_class": "qdii_global",
        "currency": "cny",
        "venue_required": ["cmb_fund"],
    })

    assert inst.asset_class == "qdii_global"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/schemas/test_universe.py::test_instrument_accepts_qdii_global_asset_class -v
```

Expected: FAIL with pydantic validation error — `'qdii_global' is not a valid AssetClass`.

- [ ] **Step 3: Update `_types.py`**

```python
AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "qdii_global", "cash",
]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/schemas/test_universe.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/irc/schemas/_types.py tests/schemas/test_universe.py
git commit -m "feat(schema): add qdii_global asset class for global-mandate QDII funds"
```

---

## Task 7: Classify QDII funds without US/HK markers as `qdii_global` (TDD)

**Files:**
- Modify: `src/irc/discovery/cn_fund_universe.py:156-169` (`_infer_asset_class`) and `:107-153` (`_tracked_index_for`)
- Test: `tests/discovery/test_cn_fund_universe.py`

- [ ] **Step 1: Write the failing test**

```python
def test_qdii_global_classification_for_funds_without_us_or_hk_markers():
    from irc.discovery.cn_fund_universe import CatalogFund, classify_catalog_fund

    fund = CatalogFund(
        fund_code="270023",
        fund_name="广发全球精选股票(QDII)人民币A",
        fund_type="",
    )

    out = classify_catalog_fund(fund)

    assert out is not None
    assert out.asset_class == "qdii_global"
    assert out.tracked_index == "Global Equity"


def test_qdii_with_us_marker_still_classified_as_us_etf():
    from irc.discovery.cn_fund_universe import CatalogFund, classify_catalog_fund

    fund = CatalogFund(
        fund_code="000055",
        fund_name="广发纳斯达克100ETF联接美元(QDII)A",
        fund_type="",
    )

    out = classify_catalog_fund(fund)

    assert out is not None
    assert out.asset_class == "us_etf"


def test_qdii_with_hk_marker_still_classified_as_hk_etf():
    from irc.discovery.cn_fund_universe import CatalogFund, classify_catalog_fund

    fund = CatalogFund(
        fund_code="000071",
        fund_name="华夏恒生ETF联接(QDII)A",
        fund_type="",
    )

    out = classify_catalog_fund(fund)

    assert out is not None
    assert out.asset_class == "hk_etf"
```

- [ ] **Step 2: Run the tests to verify the first one fails**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -k qdii -v
```

Expected: the `qdii_global` test fails (asset_class is `cn_equity_fund`, not `qdii_global`). The US and HK tests pass already and act as a regression guard.

- [ ] **Step 3: Update `_infer_asset_class`**

Replace lines 156-169:

```python
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
```

- [ ] **Step 4: Update `_tracked_index_for` to emit `"Global Equity"` for `qdii_global`**

Insert into `_tracked_index_for` (after the `hk_etf` block, around line 128 of the original file):

```python
    if asset_class == "qdii_global":
        return "Global Equity"
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -v
```

Expected: all green. If the existing `test_excludes_money_market_short_cash_fof_and_abnormal_status` or similar tests break because their fixture names contained "QDII" and equity markers, update them or add a `_BOND_MARKERS` guard (the implementation already excludes bond-marked QDII via `not _has_any(text, _BOND_MARKERS)`).

- [ ] **Step 6: Commit**

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat(discovery): classify global-mandate QDII funds as qdii_global"
```

---

## Task 8: Add cap option and `_cap_for` branch for `qdii_global` (TDD)

**Files:**
- Modify: `src/irc/discovery/cn_fund_universe.py:30-37` (`UniverseBuildOptions`) and `:247-260` (`_cap_for`) and `:239-244` (`_cap_key`)
- Test: `tests/discovery/test_cn_fund_universe.py`

- [ ] **Step 1: Write the failing test**

```python
def test_qdii_global_has_its_own_cap_bucket():
    from irc.discovery.cn_fund_universe import build_cn_fund_universe, UniverseBuildOptions

    rows = [
        # Forty domestic broad-active equity funds (fill the cn_equity_fund cap).
        *[
            {"fund_code": f"00{i:04d}", "fund_name": f"老基金{i}股票A", "fund_type": "股票型"}
            for i in range(40)
        ],
        # One QDII global fund — must not be drowned by the 40 domestic competitors.
        {"fund_code": "270023", "fund_name": "广发全球精选股票(QDII)人民币A", "fund_type": ""},
    ]
    options = UniverseBuildOptions(active_broad_cap=40, qdii_global_cap=5)

    out = build_cn_fund_universe(rows, options=options)
    ids = [it.instrument_id for it in out]

    # 270023 lives in qdii_global bucket, not in the cn_equity_fund broad_active bucket.
    assert "270023" in ids
    classes = {it.instrument_id: it.asset_class for it in out}
    assert classes["270023"] == "qdii_global"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py::test_qdii_global_has_its_own_cap_bucket -v
```

Expected: FAIL with `TypeError: UniverseBuildOptions.__init__() got an unexpected keyword argument 'qdii_global_cap'`.

- [ ] **Step 3: Update `UniverseBuildOptions`, `_cap_key`, and `_cap_for`**

Replace lines 30-37 (`UniverseBuildOptions`):

```python
@dataclass(frozen=True)
class UniverseBuildOptions:
    active_broad_cap: int = 40
    theme_cap: int = 20
    bond_cap: int = 40
    cn_etf_cap: int = 80
    us_qdii_cap: int = 40
    hk_qdii_cap: int = 40
    qdii_global_cap: int = 30
```

Replace `_cap_for` (lines 247-260):

```python
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
```

`_cap_key` lines 239-244 already returns `(asset_class, "all")` for non-equity classes — that catches `qdii_global` automatically. No change needed.

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/discovery/test_cn_fund_universe.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat(discovery): add qdii_global_cap option and cap-routing branch"
```

---

## Task 9: Regenerate `cn_funds.generated.yaml` and verify 270023 is in

**Files:**
- Modify: `config/universe/cn_funds.generated.yaml`

- [ ] **Step 1: Locate the universe-build CLI entry point**

```bash
grep -rn "run_build_cn_funds\|universe build-cn-funds\|build-cn-funds" src/irc/cli.py src/irc/commands/ 2>/dev/null
```

Expected: an entry like `irc universe build-cn-funds` exposed through the CLI.

- [ ] **Step 2: Run the regeneration**

```bash
.venv/bin/python -m irc universe build-cn-funds
```

Expected: `universe build-cn-funds OK: N instruments -> config/universe/cn_funds.generated.yaml` plus a counts block that now includes a `qdii_global/NONE` line.

- [ ] **Step 3: Verify 270023 is present**

```bash
grep -A2 "270023" config/universe/cn_funds.generated.yaml | head -10
```

Expected: a block containing `instrument_id: '270023'`, `name_cn: 广发全球精选股票(QDII)人民币A`, `asset_class: qdii_global`.

- [ ] **Step 4: Sanity-check the deltas**

```bash
git diff --stat config/universe/cn_funds.generated.yaml
.venv/bin/python -c "
import yaml, collections
data = yaml.safe_load(open('config/universe/cn_funds.generated.yaml'))
counts = collections.Counter((it['asset_class'], it.get('theme') or 'NONE') for it in data['instruments'])
for k,v in sorted(counts.items()):
    print(f'  {k}: {v}')
"
```

Expected: a new `('qdii_global', 'NONE'): <N>` row in the count breakdown; total instrument count shifts by ~30 (the new qdii_global bucket) plus whatever shuffling the 1Y-return rank caused in other buckets.

- [ ] **Step 5: Commit the regenerated artifact**

```bash
git add config/universe/cn_funds.generated.yaml
git commit -m "chore(universe): regenerate cn_funds with quality ranking + qdii_global"
```

---

## Task 10: Add an integration test pinning 270023 into the regenerated universe

**Files:**
- Test: `tests/integration/test_generated_cn_fund_discovery.py` (extend the existing file)

This test runs against the committed YAML — it locks in the structural guarantee that high-return QDII-global funds make it into the universe.

- [ ] **Step 1: Add the assertion**

```python
def test_generated_universe_contains_270023_in_qdii_global_bucket():
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "config" / "universe" / "cn_funds.generated.yaml"
    data = yaml.safe_load(path.read_text())
    by_id = {it["instrument_id"]: it for it in data["instruments"]}

    assert "270023" in by_id, "270023 (广发全球精选股票 QDII) must be in the generated universe"
    assert by_id["270023"]["asset_class"] == "qdii_global"
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/integration/test_generated_cn_fund_discovery.py -v
```

Expected: all green including the new assertion.

- [ ] **Step 3: Run the full test suite as a final regression gate**

```bash
.venv/bin/python -m pytest -x
```

Expected: green. If anything red surfaces — most likely downstream consumers that pattern-match on `asset_class` and don't recognize `qdii_global` — fix it as a follow-up task. Likely suspects: opportunity scoring, role-bucket assignment, hard-filter, qa pipelines. Grep for `cn_equity_fund` and consider whether each call site should also handle `qdii_global` (often `qdii_global` should be treated like a sibling of `us_etf` for role/exposure purposes).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_generated_cn_fund_discovery.py
git commit -m "test(integration): lock 270023 qdii_global into generated universe"
```

---

## Task 11: Downstream consumer audit for `qdii_global`

**Files:**
- Audit-only: list and triage call sites that pattern-match `asset_class`.

This task surfaces every place in the codebase that branches on `asset_class` so the implementer can decide whether `qdii_global` needs explicit handling (e.g., role-bucket assignment, hard-filter, opportunity scoring).

- [ ] **Step 1: Find pattern-match sites**

```bash
grep -rn '"cn_equity_fund"\|"us_etf"\|"hk_etf"\|asset_class ==\|asset_class in' src/irc/ tests/ --include="*.py" | grep -v __pycache__
```

- [ ] **Step 2: For each site, decide one of:**
  - **No change:** the site is generic over asset_class (e.g., just reading the value).
  - **Add `qdii_global` to the branch:** the site treats us_etf/hk_etf as "foreign equity" — add qdii_global to the same group.
  - **New branch:** qdii_global has different semantics (e.g., a global fund is not pure US so it might not satisfy an "I want US exposure" role).

Record decisions in a short note under this task, then apply each change as a separate commit (one file per commit where practical). For each behavioral change, add a unit test.

- [ ] **Step 3: Commit per change**

```bash
git add <files>
git commit -m "fix(<area>): handle qdii_global asset class in <site>"
```

- [ ] **Step 4: Final regression run**

```bash
.venv/bin/python -m pytest -x
```

Expected: green.

---

## Acceptance Criteria

When all tasks are complete, the following statements are true:

1. `config/universe/cn_funds.generated.yaml` contains an instrument with `instrument_id: '270023'` and `asset_class: qdii_global`.
2. The counts block printed by `irc universe build-cn-funds` includes a `qdii_global/NONE: N` line.
3. `tests/integration/test_generated_cn_fund_discovery.py::test_generated_universe_contains_270023_in_qdii_global_bucket` passes.
4. Running `_apply_caps` with `returns={}` yields the same selection as today (backward-compatible — verified by existing tests still passing).
5. `fetch_open_fund_ranks()` is callable and lru-cached; failures inside `universe_cmd.run_build_cn_funds` are caught and degrade gracefully to `returns={}` with a stderr warning (the build still succeeds with legacy ranking).
6. No downstream test breaks; if any do, Task 11 fixes them with explicit `qdii_global` handling.

---

## Self-review notes

- **Coverage:** Tasks 1-5 cover Path A (quality ranking). Tasks 6-10 cover Path C (qdii_global asset class). Task 11 catches downstream blast radius.
- **TDD:** Every code-changing task starts with a failing test, then minimal implementation, then green test, then commit.
- **Backward compat:** `returns=None`/`{}` preserves today's behavior. The new asset class is additive in the Literal and behind its own cap key.
- **No placeholders:** All file paths exact, all test code complete, all expected outputs concrete.
- **Failure modes thought through:** akshare rank fetch failure → fall back to legacy rank with warning; tests still pass.
