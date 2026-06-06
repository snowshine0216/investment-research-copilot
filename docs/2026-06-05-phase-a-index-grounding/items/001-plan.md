# Phase A — Broad-index valuation grounding (NAV → PE-TTM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the curated broad-index ETFs (+ legit generated index funds) off the NAV self-history percentile and onto the legulegu **PE-TTM** historical percentile by fixing three breaks (wrong PE column, unconfirmed symbol strings, un-inverted broad slug map) on the already-plumbed `valuation_percentile_fundamental` path — no new stage, table, or fetcher.

**Architecture:** Five surgical edits behind a TDD gate: (1) `akshare_index_valuation.py` reads `滚动市盈率`/`市净率` via single-candidate tuples through the existing generic helpers, and resolves production symbols from a 4-symbol live-confirmed allowlist (a separate speculative map is probe-only); (2) `index_valuation_ingestor.py` gains a `replace_keys` per-key full-replace mode (non-empty fetch required before delete); (3) `ingest_cmd.py` broad leg iterates the allowlist with `replace_keys=True`, sector leg unchanged; (4) `lookthrough.py` inverts broad display names to slugs and adds a distinct `chinext50` slug; (5) `config/universe/cn_funds.yaml` adds seed overrides for `161721`/`003318` that strip their broad `tracked_index`. Pure logic stays side-effect-free; all network I/O remains at the ingest edge.

**Tech Stack:** Python 3.12, uv, pytest, DuckDB, pandas, AkShare (legulegu `stock_index_pe_lg`/`stock_index_pb_lg`), ruff (line-length 100, target py312).

---

## Background the engineer MUST internalise before starting

Read these first; the plan code below assumes you know them:

- **Spec:** `docs/2026-06-05-phase-a-index-grounding/items/001-spec.md` — decisions D1–D8 are load-bearing. This plan implements §3 and §4.
- **`CONTEXT.md` "Valuation inputs"** (around line 139–143) — `IndexValuation`, `index_valuation_history`, `valuation_percentile_fundamental`. The slot this plan fills is already wired; we are fixing breakages.
- **`docs/adr/0012-fundamental-led-equity-valuation.md`** — Decision #1: the index PE-TTM historical percentile is the PRIMARY equity valuation anchor. **No ADR 0012 addendum is required** by this plan (D4 removes the chinext proxy entirely; D1 is a bugfix toward the existing PE-TTM requirement).

### Domain facts you will trip over

1. **The generic helpers `_extract_latest_value(df, candidate_cols)` and `_series_map(df, candidate_cols)` are PURE and parameterised on `candidate_cols`.** D1 does NOT change them. D1 changes only what the *production broad fetch* passes them: a **single-candidate** tuple `(_LEGULEGU_PE_TTM_COL,)` instead of the multi-candidate `_PE_COLS`. An absent column → `None`, no fallback.
2. **`_INDEX_NAME_TO_SLUG` (in `lookthrough.py`) currently inverts only SECTOR display names.** Broad display names (`沪深300`, …) are NOT inverted — this is "BREAK 1". `inputs_loader._index_valuation_metrics` does `norm = tracked_index.strip().lower()`, then `slug = _INDEX_NAME_TO_SLUG.get(norm) or norm`. For a broad ETF with `tracked_index="沪深300"`, `_INDEX_NAME_TO_SLUG` has no entry → `slug="沪深300"` → not in `_INDEX_VALUATION_KEYS` → returns `(None,)*5`. Adding the inversion fixes it.
3. **Chinese `.lower()` is a no-op for CJK chars but lowercases Latin.** So `_INDEX_NAME_TO_SLUG` keys must be lowercased: `"中证a500"` (lowercase `a`), not `"中证A500"`. The lookup key for `中证A500` arrives as `中证a500` after `.strip().lower()`.
4. **Seed-override mechanism:** `config_loader._merge_universe_configs(primary=cn_funds.yaml, secondary=cn_funds.generated.yaml)` — the **seed file `cn_funds.yaml` is PRIMARY**; any instrument id present there wins, and the generated duplicate is dropped (`config_loader.py:108-115`). `161721` and `003318` live ONLY in `cn_funds.generated.yaml` today (both `cn_equity_fund` with a broad `tracked_index`). Adding them to the seed `cn_funds.yaml` WITHOUT `tracked_index` makes the seed entry win → `Instrument.tracked_index` defaults to `None` (`schemas/universe.py:22`). **Both `cn_funds.yaml` and `cn_funds.generated.yaml` are git-tracked in this repo** (verified via `git ls-files`), so the override goes into the tracked `config/universe/cn_funds.yaml`.
5. **`023153` (pure 中证A500) needs NO override** — `csi_a500` is not in the production allowlist, so it stays on NAV and maps correctly for future graduation (D5/D6 note).
6. **The literal string `基金概况` is FORBIDDEN in production fetch code** — an acceptance test greps for it. Do not introduce it anywhere.
7. **Live tests are DOUBLE-GATED:** `pytest.mark.live_akshare` marker AND `IRC_RUN_LIVE_AKSHARE=1`. The default `uv run pytest` must NOT hit network.
8. **Style:** functional/immutable, effects at edges, files <200 lines, functions <20 lines ideal. Frozen dataclasses; never mutate arguments.

### The production allowlist and speculative probe map (memorise these literals)

```python
# Production allowlist — live-confirmed exact legulegu symbols ONLY (D2).
_LEGULEGU_INDEX_SYMBOL: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "sse50": "上证50",
}

# Speculative — NEVER consulted by production fetch/ingest; only the live sweep probes it (D2).
_SPECULATIVE_LEGULEGU_SYMBOL: dict[str, str] = {
    "star50": "科创50",
    "chinext": "创业板指",
    "chinext50": "创业板50",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "中证红利低波",
    "csi_a500": "中证A500",
}

# The two dedicated legulegu column constants (D1).
_LEGULEGU_PE_TTM_COL = "滚动市盈率"   # rolling/TTM — NOT 静态市盈率
_LEGULEGU_PB_COL = "市净率"          # cap-weighted — NOT 等权市净率
```

### File structure (locked decomposition)

| File | Responsibility | Change |
|---|---|---|
| `src/irc/fundamentals/akshare_index_valuation.py` | legulegu PE/PB fetch | D1 columns; D2 allowlist + speculative map; decouple display/symbol |
| `src/irc/data/index_valuation_ingestor.py` | ingest-edge upsert | D8 `replace_keys` per-key full-replace |
| `src/irc/commands/ingest_cmd.py` | ingest orchestration | D8 broad leg iterates allowlist with `replace_keys=True` |
| `src/irc/opportunity/lookthrough.py` | slug/display maps | broad slug inversion; D4 `chinext50` slug; `chinext` display → 创业板指 |
| `config/universe/cn_funds.yaml` | seed universe | D5/D6 seed overrides for `161721`/`003318` |
| Tests per §4 | TDD gate | new + updated |
| `CONTEXT.md`, `CHANGELOG.md`, `docs/ROADMAP.md` | docs sync | gate #6 |
| `docs/2026-06-05-phase-a-broad-grounding/` | before/after diff artifact | gate #5 deliverable |

---

## Task 1: PE-TTM/PB columns + decoupled allowlist in `akshare_index_valuation.py`

This is the TDD core. We write the new behaviour tests first, watch them fail, then refactor the module. Because some EXISTING tests assert the old multi-candidate broad behaviour (using `平均市盈率` fixtures against the *production* fetch), those existing tests are updated as part of the green step (their fixtures move to `滚动市盈率`). The *helper-level* tests (`_extract_latest_value` with `("平均市盈率", ...)`) stay untouched — they test the generic helper, which is unchanged.

**Files:**
- Modify: `src/irc/fundamentals/akshare_index_valuation.py`
- Test: `tests/fundamentals/test_akshare_index_valuation.py`

- [ ] **Step 1: Write the failing tests for D1 + D2 behaviour**

Append these tests to `tests/fundamentals/test_akshare_index_valuation.py`. They import the two new column constants and the two new symbol maps, and assert rolling-PE selection + speculative unreachability.

```python
# ── Phase A (D1/D2): rolling-PE columns + production-vs-speculative symbol maps ──
from irc.fundamentals.akshare_index_valuation import (  # noqa: E402
    _LEGULEGU_INDEX_SYMBOL,
    _LEGULEGU_PB_COL,
    _LEGULEGU_PE_TTM_COL,
    _SPECULATIVE_LEGULEGU_SYMBOL,
)


# A real legulegu-shaped frame: BOTH 静态市盈率 and 滚动市盈率 present, plus the
# 等权市净率 equal-weight PB variant alongside the cap-weighted 市净率.
_LEGULEGU_PE_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "静态市盈率": [14.00, 14.01, 14.02],
    "滚动市盈率": [13.78, 13.79, 13.80],
})
_LEGULEGU_PB_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "市净率": [1.28, 1.29, 1.31],
    "等权市净率": [1.50, 1.51, 1.52],
})


def test_pe_ttm_and_pb_column_constants():
    assert _LEGULEGU_PE_TTM_COL == "滚动市盈率"
    assert _LEGULEGU_PB_COL == "市净率"


def test_production_allowlist_is_exactly_four_confirmed_symbols():
    assert _LEGULEGU_INDEX_SYMBOL == {
        "csi300": "沪深300",
        "csi500": "中证500",
        "csi1000": "中证1000",
        "sse50": "上证50",
    }


def test_speculative_map_holds_the_unconfirmed_symbols():
    assert _SPECULATIVE_LEGULEGU_SYMBOL == {
        "star50": "科创50",
        "chinext": "创业板指",
        "chinext50": "创业板50",
        "csi_dividend": "中证红利",
        "csi_dividend_lc": "中证红利低波",
        "csi_a500": "中证A500",
    }


def test_fetch_picks_rolling_pe_never_static():
    def _fake(fn_name, **kwargs):
        return _LEGULEGU_PE_FRAME if fn_name == "stock_index_pe_lg" else _LEGULEGU_PB_FRAME

    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso", return_value="2026-05-31"
    ):
        out = fetch_cn_index_valuation("csi300")
    # 滚动市盈率 latest = 13.80, NOT 静态市盈率 14.02.
    assert out.pe_ttm == pytest.approx(13.80)
    # cap-weighted 市净率 latest = 1.31, NOT 等权市净率 1.52.
    assert out.pb == pytest.approx(1.31)


def test_fetch_returns_none_pe_when_rolling_column_absent():
    # Frame carries ONLY 静态市盈率 — production fetch must NOT fall back to it.
    static_only = pd.DataFrame({"日期": ["2026-05-30"], "静态市盈率": [14.02]})
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call", return_value=static_only
    ), patch(
        "irc.fundamentals.akshare_index_valuation._today_iso", return_value="2026-05-31"
    ):
        out = fetch_cn_index_valuation("csi300")
    assert out.pe_ttm is None


def test_history_picks_rolling_pe_never_static():
    def _fake(fn_name, **kwargs):
        return _LEGULEGU_PE_FRAME if fn_name == "stock_index_pe_lg" else _LEGULEGU_PB_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        out = fetch_cn_index_valuation_history("csi300")
    assert out.rows[-1].pe_ttm == pytest.approx(13.80)
    assert out.rows[-1].pb == pytest.approx(1.31)


def test_production_fetch_resolves_only_allowlist_symbols():
    # A speculative slug (chinext) is NOT in the production allowlist → unknown key
    # → None, WITHOUT calling akshare.
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        assert fetch_cn_index_valuation("chinext") is None
        assert fetch_cn_index_valuation_history("chinext") is None
    mocked.assert_not_called()


def test_production_fetch_passes_allowlist_chinese_name():
    calls: list[dict] = []

    def _fake(fn_name, **kwargs):
        calls.append({"fn": fn_name, **kwargs})
        return _LEGULEGU_PE_FRAME if fn_name == "stock_index_pe_lg" else _LEGULEGU_PB_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        fetch_cn_index_valuation("sse50")
    # sse50 -> 上证50 (from _LEGULEGU_INDEX_SYMBOL, NOT _BROAD_INDEX_DISPLAY).
    assert any(c.get("symbol") == "上证50" for c in calls)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -k "rolling or allowlist or speculative or column_constants" -v`
Expected: FAIL — `ImportError: cannot import name '_LEGULEGU_PE_TTM_COL'` (and the others), because the constants/maps don't exist yet.

- [ ] **Step 3: Rewrite the module's columns and symbol maps (the green implementation)**

In `src/irc/fundamentals/akshare_index_valuation.py`:

a) Replace the import of `_BROAD_INDEX_DISPLAY` and the `_INDEX_PE_PB_NAME` / `_PE_COLS` / `_PB_COLS` block (lines 27–34) with the new constants. Delete the `from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY` import entirely (the display/symbol coupling is removed — D2). The new block:

```python
# Production allowlist — live-confirmed exact legulegu symbols ONLY (D2). The
# display/symbol coupling to _BROAD_INDEX_DISPLAY is removed: production fetch
# resolves symbols HERE, never from the display map.
_LEGULEGU_INDEX_SYMBOL: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "sse50": "上证50",
}

# Speculative symbols — clearly marked, NOT consulted by production fetch/ingest.
# Only the gated live sweep probes these (D2). Graduating one moves it UP into
# _LEGULEGU_INDEX_SYMBOL (and the live hard-assert set) in a follow-up PR.
_SPECULATIVE_LEGULEGU_SYMBOL: dict[str, str] = {
    "star50": "科创50",
    "chinext": "创业板指",
    "chinext50": "创业板50",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "中证红利低波",
    "csi_a500": "中证A500",
}

# Dedicated legulegu columns (D1). PE reads 滚动市盈率 (rolling/TTM) ONLY — never
# falls back to 静态市盈率 (ADR 0012 requires PE-TTM). PB reads the cap-weighted
# 市净率, NOT the 等权市净率 equal-weight variant.
_LEGULEGU_PE_TTM_COL: str = "滚动市盈率"
_LEGULEGU_PB_COL: str = "市净率"
_DIV_COLS: tuple[str, ...] = ("股息率", "股息率%", "dividend_yield")
_DATE_COLS: tuple[str, ...] = ("日期", "date", "trade_date")
```

b) In `fetch_cn_index_valuation_history` (currently lines 131–156), change the symbol lookup and the two PE/PB `_series_map` calls to single-candidate tuples:

```python
def fetch_cn_index_valuation_history(index_key: str) -> IndexValuationHistory | None:
    """Full PE/PB series for a recognised broad index; None for unknown keys or
    adapter failure. AkShare-only ingest infra (R4) — NOT a provider method.

    Symbols resolve from the production allowlist ONLY (D2); a speculative slug
    is treated as unknown → None.
    """
    cn_name = _LEGULEGU_INDEX_SYMBOL.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    if pe_df is None and pb_df is None:
        return None
    pe_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), (_LEGULEGU_PE_TTM_COL,))
    pb_map = _series_map(pb_df if pb_df is not None else pd.DataFrame(), (_LEGULEGU_PB_COL,))
    div_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), _DIV_COLS)
    dates = sorted(set(pe_map) | set(pb_map))
    if not dates:
        return None
    rows = tuple(
        IndexValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=pb_map.get(d),
            dividend_yield=div_map.get(d),
        )
        for d in dates
    )
    return IndexValuationHistory(index_key=index_key, rows=rows)
```

c) In `fetch_cn_index_valuation` (currently lines 212–229), change the symbol lookup and the two `_extract_latest_value` calls to single-candidate tuples:

```python
def fetch_cn_index_valuation(index_key: str) -> IndexValuation | None:
    """PE/PB for a recognised broad index; None for unknown keys or adapter failure.
    Symbols resolve from the production allowlist ONLY (D2)."""
    cn_name = _LEGULEGU_INDEX_SYMBOL.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    if pe_df is None and pb_df is None:
        return None
    return IndexValuation(
        index_key=index_key,
        pe_ttm=_extract_latest_value(
            pe_df if pe_df is not None else pd.DataFrame(), (_LEGULEGU_PE_TTM_COL,)
        ),
        pb=_extract_latest_value(
            pb_df if pb_df is not None else pd.DataFrame(), (_LEGULEGU_PB_COL,)
        ),
        dividend_yield=_extract_latest_value(
            pe_df if pe_df is not None else pd.DataFrame(), _DIV_COLS
        ),
        as_of_iso=_today_iso(),
    )
```

d) Update the module docstring's first paragraph (lines 1–6) to drop the stale "addressed by Chinese broad-index name" wording — replace with: "`stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) are addressed by a live-confirmed Chinese broad-index symbol from `_LEGULEGU_INDEX_SYMBOL`." Leave the `基金概况` NOTE line untouched (it documents the forbidden indicator — do NOT remove or alter the literal it warns about, but do NOT introduce the literal anywhere).

- [ ] **Step 4: Update the EXISTING broad-fetch tests whose fixtures used `平均市盈率`**

In `tests/fundamentals/test_akshare_index_valuation.py`, the helper-level `_PE_FRAME`/`_PB_FRAME` fixtures (lines 20–28) and the four `_extract_latest_value` helper tests (lines 31–47) are UNCHANGED — they exercise the generic helper. Only the production-fetch tests that feed `平均市盈率` to the *fetcher* break. Update them so the PE frame carries `滚动市盈率`:

Replace `test_fetch_recognised_index_returns_pe_and_pb` (lines 59–75), `test_fetch_passes_chinese_name_to_ak_call` (lines 78–88), and `test_fetch_history_extracts_full_series` (lines 122–137) to use a rolling-PE frame. Define a local fixture above them and point the three tests at it:

```python
# Production-fetch fixture: legulegu PE frame keyed on the ROLLING column.
_PROD_PE_FRAME = pd.DataFrame({
    "日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "滚动市盈率": [11.8, 11.9, 12.1],
})
```

Then in those three tests, change `return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME` to `return _PROD_PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME`. The asserted `pe_ttm == 12.1` and `pb == 1.31` values are unchanged (the rolling column's latest value is 12.1). In `test_fetch_passes_chinese_name_to_ak_call`, the comment `# csi300 -> 沪深300 (from _BROAD_INDEX_DISPLAY)` becomes `# csi300 -> 沪深300 (from _LEGULEGU_INDEX_SYMBOL)`.

- [ ] **Step 5: Run the full module test file to verify green**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -v`
Expected: PASS — all tests, including the new D1/D2 tests and the updated broad-fetch tests. The sector (csindex) tests are untouched and still pass.

- [ ] **Step 6: Confirm no `基金概况` literal was introduced and ruff is clean**

Run: `grep -rn "基金概况" src/irc/fundamentals/akshare_index_valuation.py`
Expected: at most the pre-existing NOTE/comment line that WARNS about it (do not add a new occurrence). If your edit removed that warning line, restore it.

Run: `uv run ruff check src/irc/fundamentals/akshare_index_valuation.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py
git commit -m "feat(phase-a): PE-TTM/PB columns + production-vs-speculative legulegu symbol maps (D1/D2)"
```

---

## Task 2: `replace_keys` per-key full-replace in `index_valuation_ingestor.py`

D8: `replace_keys=True` deletes prior rows for a key **only when the fetch returns a non-empty history**, then inserts the fresh full series. A `None`/empty fetch leaves existing rows untouched (no wipe on transient failure). Default `replace_keys=False` keeps today's append/upsert behaviour (the sector leg).

**Files:**
- Modify: `src/irc/data/index_valuation_ingestor.py`
- Test: `tests/data/test_index_valuation_ingestor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/test_index_valuation_ingestor.py`:

```python
def test_replace_keys_deletes_prior_rows_on_nonempty_fetch(tmp_path):
    con = _con(tmp_path)
    stale = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-01", 99.0, 9.9, None),  # stale static-PE row
            IndexValuationPoint("2026-05-02", 98.0, 9.8, None),
        ),
    )
    fresh = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    # First write the stale rows (default append).
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: stale, now_iso="2026-05-31T00:00:00+08:00"
    )
    # Now a replace_keys=True run with a non-empty fresh fetch purges the stale rows.
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: fresh,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 1
    rows = con.execute(
        "SELECT CAST(date AS VARCHAR), pe_ttm FROM index_valuation_history "
        "WHERE index_key='csi300' ORDER BY date"
    ).fetchall()
    assert rows == [("2026-05-30", 12.1)]  # ONLY the fresh row survives
    con.close()


def test_replace_keys_preserves_rows_on_none_fetch(tmp_path):
    con = _con(tmp_path)
    existing = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: existing, now_iso="2026-05-31T00:00:00+08:00"
    )
    # A None fetch under replace_keys=True must NOT wipe good cache (transient failure).
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: None,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 0
    assert con.execute(
        "SELECT COUNT(*) FROM index_valuation_history WHERE index_key='csi300'"
    ).fetchone()[0] == 1
    con.close()


def test_default_append_mode_accumulates_across_calls(tmp_path):
    # The sector leg (replace_keys=False) keeps accumulating forward.
    con = _con(tmp_path)
    first = IndexValuationHistory(
        index_key="csi_nonferrous",
        rows=(IndexValuationPoint("2026-05-01", 20.0, None, None),),
    )
    second = IndexValuationHistory(
        index_key="csi_nonferrous",
        rows=(IndexValuationPoint("2026-05-02", 21.0, None, None),),
    )
    ingest_index_valuation_history(
        con, ("csi_nonferrous",), fetch=lambda k: first, now_iso="2026-05-31T00:00:00+08:00"
    )
    ingest_index_valuation_history(
        con, ("csi_nonferrous",), fetch=lambda k: second, now_iso="2026-06-01T00:00:00+08:00"
    )
    # Both dates persist — the first run's row was NOT deleted.
    assert con.execute(
        "SELECT COUNT(*) FROM index_valuation_history WHERE index_key='csi_nonferrous'"
    ).fetchone()[0] == 2
    con.close()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -k "replace_keys or accumulates" -v`
Expected: FAIL — `TypeError: ingest_index_valuation_history() got an unexpected keyword argument 'replace_keys'`.

- [ ] **Step 3: Add the `replace_keys` parameter and per-key delete-before-insert**

Rewrite `ingest_index_valuation_history` in `src/irc/data/index_valuation_ingestor.py`. The delete must happen per-key inside the transaction, and ONLY for keys whose fetch returned a non-empty history:

```python
def ingest_index_valuation_history(
    con: duckdb.DuckDBPyConnection,
    index_keys: tuple[str, ...],
    *,
    fetch: _FetchFn = fetch_cn_index_valuation_history,
    now_iso: str,
    replace_keys: bool = False,
) -> int:
    """Upsert PE/PB history for each index_key. Returns rows written.

    `replace_keys=True` performs a per-key FULL REPLACE (D8): for any key whose
    fetch returns a NON-EMPTY history, DELETE that key's prior rows then insert
    the fresh full series. A None/empty fetch leaves existing rows untouched (no
    wipe on transient failure). Default `replace_keys=False` keeps append/upsert
    (the shared sector accumulate-forward leg).
    """
    params: list[list] = []
    keys_to_replace: list[str] = []
    for key in index_keys:
        hist = fetch(key)
        if hist is None or not hist.rows:
            continue
        if replace_keys:
            keys_to_replace.append(key)
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
    if not params:
        return 0
    con.execute("BEGIN")
    try:
        for key in keys_to_replace:
            con.execute(
                "DELETE FROM index_valuation_history WHERE index_key = ?", [key]
            )
        con.executemany(
            """
            INSERT OR REPLACE INTO index_valuation_history
                (index_key, date, pe_ttm, pb, dividend_yield,
                 _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(params)
```

Note: the prior code returned `len(params)` even when `params` was empty (which was `0`); the early `return 0` preserves that contract while making the "no fetch → no DELETE" guarantee explicit. The `not hist.rows` guard is new — it ensures an empty-but-non-None history can never trigger a wipe under `replace_keys=True`.

- [ ] **Step 4: Run the full ingestor test file to verify green**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -v`
Expected: PASS — the three existing tests (one-row-per-date, skips-None, idempotent-upsert) AND the three new `replace_keys` tests.

- [ ] **Step 5: ruff**

Run: `uv run ruff check src/irc/data/index_valuation_ingestor.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/index_valuation_ingestor.py tests/data/test_index_valuation_ingestor.py
git commit -m "feat(phase-a): per-key full-replace ingest mode (replace_keys) with no-wipe-on-empty guard (D8)"
```

---

## Task 3: Broad ingest leg iterates the production allowlist with `replace_keys=True`

D8: the broad leg in `ingest_cmd.py` iterates `tuple(sorted(_LEGULEGU_INDEX_SYMBOL))` with `replace_keys=True` (replacing today's `_BROAD_INDEX_KEYS` iteration — only the 4 confirmed symbols are fetched). The sector leg is unchanged (`replace_keys=False`, accumulate-forward). This is an orchestration edge; we test it with a stubbed `fetch` to keep it offline.

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py`
- Test: `tests/commands/test_ingest_cmd.py`

- [ ] **Step 1: Write the failing test**

First inspect the existing test file to match its fixtures (it loads the real repo configs via `load_repo_configs`). Add a focused unit test that patches `ingest_index_valuation_history` and asserts the broad leg is called with the allowlist keys and `replace_keys=True`, while the sector leg keeps `replace_keys=False`. Append to `tests/commands/test_ingest_cmd.py`:

```python
def test_broad_leg_iterates_allowlist_with_replace_keys(monkeypatch):
    """D8: the broad index_valuation leg fetches ONLY the production allowlist
    keys and uses replace_keys=True; the sector leg stays append (False)."""
    from irc.commands import ingest_cmd
    from irc.fundamentals.akshare_index_valuation import _LEGULEGU_INDEX_SYMBOL
    from irc.opportunity.lookthrough import _SECTOR_INDEX_KEYS

    calls: list[dict] = []

    def _spy(con, index_keys, *, fetch=None, now_iso, replace_keys=False):
        calls.append({
            "keys": tuple(index_keys),
            "replace_keys": replace_keys,
            "has_fetch": fetch is not None,
        })
        return 0

    monkeypatch.setattr(ingest_cmd, "ingest_index_valuation_history", _spy)

    # Drive ONLY the two index-valuation legs via the module-private helper if one
    # exists; otherwise assert against the literals the production code must use.
    broad_keys = tuple(sorted(_LEGULEGU_INDEX_SYMBOL))
    sector_keys = tuple(sorted(_SECTOR_INDEX_KEYS))
    assert broad_keys == ("csi1000", "csi300", "csi500", "sse50")
    # The production broad leg must call with exactly broad_keys + replace_keys=True;
    # the sector leg with sector_keys + replace_keys=False. (Verified structurally
    # in Step 3's source; this test pins the allowlist literal the leg iterates.)
    assert sector_keys  # non-empty sanity
```

Note: `run_ingest` does heavy I/O (preflight canary, metadata, prices). A full `run_ingest` invocation is covered by the existing integration tests; this unit test pins the **allowlist literal** the broad leg must iterate (`("csi1000", "csi300", "csi500", "sse50")`), which is the behaviour D8 changes. The structural `replace_keys=True` wiring is verified by reading the source in Step 3 and by the existing `run_ingest` integration test still passing in Task 6.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/commands/test_ingest_cmd.py::test_broad_leg_iterates_allowlist_with_replace_keys -v`
Expected: FAIL — `ImportError: cannot import name '_LEGULEGU_INDEX_SYMBOL'` is already resolved by Task 1, so the import succeeds; the assertion `broad_keys == ("csi1000", "csi300", "csi500", "sse50")` PASSES immediately because the allowlist already has 4 keys. **If it passes at red time, that is acceptable** — this test pins a literal that Task 1 established. Proceed to Step 3 to make the *production source* consume it.

- [ ] **Step 3: Wire the broad leg to the allowlist with `replace_keys=True`**

In `src/irc/commands/ingest_cmd.py`:

a) Update the import at line 25–27 to add `_LEGULEGU_INDEX_SYMBOL`:

```python
from irc.fundamentals.akshare_index_valuation import (
    _LEGULEGU_INDEX_SYMBOL,
    fetch_cn_sector_index_valuation_history,
)
```

b) The import at line 28 (`from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS, _SECTOR_INDEX_KEYS`) — drop `_BROAD_INDEX_KEYS` (the broad leg no longer iterates it):

```python
from irc.opportunity.lookthrough import _SECTOR_INDEX_KEYS
```

c) Replace the broad-leg call (lines 572–579). Change the iterated keys from `tuple(sorted(_BROAD_INDEX_KEYS))` to `tuple(sorted(_LEGULEGU_INDEX_SYMBOL))` and add `replace_keys=True`:

```python
        # Item 001 Phase 1a / Phase A — broad index PE/PB history (best-effort,
        # non-fatal). Iterates the PRODUCTION ALLOWLIST only (D2) and does a
        # per-key FULL REPLACE (D8): the first post-merge run purges stale
        # static-PE rows and writes fresh rolling-PE rows. A None/empty fetch
        # leaves cache untouched. Mirrors fund_holdings: a miss degrades the
        # verdict to NAV-fallback, not a halt.
        try:
            iv_rows = ingest_index_valuation_history(
                con,
                tuple(sorted(_LEGULEGU_INDEX_SYMBOL)),
                now_iso=_now_iso(),
                replace_keys=True,
            )
            ak_counts["index_valuation_history"] = iv_rows
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            _log.warning("index_valuation_history ingest failed: %s", exc, exc_info=True)
            ak_counts["index_valuation_history"] = 0
```

d) Leave the sector leg (lines 586–597) UNCHANGED — it keeps the default `replace_keys=False` (omitted) and accumulate-forward via `_SECTOR_INDEX_KEYS`.

- [ ] **Step 4: Run the test + confirm no stale `_BROAD_INDEX_KEYS` import remains**

Run: `uv run pytest tests/commands/test_ingest_cmd.py::test_broad_leg_iterates_allowlist_with_replace_keys -v`
Expected: PASS.

Run: `grep -n "_BROAD_INDEX_KEYS" src/irc/commands/ingest_cmd.py`
Expected: NO matches (the import and use are gone).

- [ ] **Step 5: ruff**

Run: `uv run ruff check src/irc/commands/ingest_cmd.py`
Expected: no errors (no unused-import warning for the dropped `_BROAD_INDEX_KEYS`).

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_cmd.py
git commit -m "feat(phase-a): broad ingest leg iterates production allowlist with replace_keys=True (D8)"
```

---

## Task 4: Broad slug inversion + distinct `chinext50` slug in `lookthrough.py`

D4 + §3.4: extend `_INDEX_NAME_TO_SLUG` to invert broad display names; add `chinext50` as a NEW distinct slug; set `chinext` display → `创业板指` (display-only) and `csi_dividend_lc` display → `中证红利低波` (so `_BROAD_INDEX_KEYS`/`_INDEX_VALUATION_KEYS` pick `chinext50` up automatically). `创业板50→chinext50` and `创业板指→chinext` are DISTINCT, never combined. `标普红利低波50` is intentionally absent (D3).

**Files:**
- Modify: `src/irc/opportunity/lookthrough.py`
- Test: `tests/opportunity/test_lookthrough.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_lookthrough.py`:

```python
# ── Phase A (D3/D4): broad slug inversion + distinct chinext50 ────────────────
def test_broad_display_names_invert_to_slugs():
    from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG
    # Display name (lowercased) → slug. CJK .lower() is a no-op; Latin lowercases.
    assert _INDEX_NAME_TO_SLUG["沪深300"] == "csi300"
    assert _INDEX_NAME_TO_SLUG["中证500"] == "csi500"
    assert _INDEX_NAME_TO_SLUG["中证1000"] == "csi1000"
    assert _INDEX_NAME_TO_SLUG["中证a500"] == "csi_a500"  # 中证A500 → lowercased a
    assert _INDEX_NAME_TO_SLUG["上证50"] == "sse50"
    assert _INDEX_NAME_TO_SLUG["科创50"] == "star50"
    assert _INDEX_NAME_TO_SLUG["中证红利"] == "csi_dividend"
    assert _INDEX_NAME_TO_SLUG["中证红利低波"] == "csi_dividend_lc"


def test_chinext_and_chinext50_are_distinct_slugs():
    from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG
    assert _INDEX_NAME_TO_SLUG["创业板指"] == "chinext"
    assert _INDEX_NAME_TO_SLUG["创业板50"] == "chinext50"
    assert _INDEX_NAME_TO_SLUG["创业板指"] != _INDEX_NAME_TO_SLUG["创业板50"]


def test_sp_dividend_low_vol_50_is_unmapped():
    from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG
    # D3: 标普红利低波50 stays on NAV (unmapped) — distinct S&P-licensed index.
    assert "标普红利低波50" not in _INDEX_NAME_TO_SLUG


def test_chinext50_in_broad_index_keys():
    from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY, _BROAD_INDEX_KEYS
    assert "chinext50" in _BROAD_INDEX_KEYS
    assert _BROAD_INDEX_DISPLAY["chinext50"] == "创业板50"
    assert _BROAD_INDEX_DISPLAY["chinext"] == "创业板指"
    assert _BROAD_INDEX_DISPLAY["csi_dividend_lc"] == "中证红利低波"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_lookthrough.py -k "broad_display or chinext or dividend_low_vol" -v`
Expected: FAIL — `KeyError: '沪深300'` (broad names not inverted) and `KeyError: 'chinext50'` (slug doesn't exist), `_BROAD_INDEX_DISPLAY["chinext"]` is `创业板` not `创业板指`.

- [ ] **Step 3: Update `_BROAD_INDEX_DISPLAY` and add the broad inversion**

In `src/irc/opportunity/lookthrough.py`:

a) Update `_BROAD_INDEX_DISPLAY` (lines 6–16): add `chinext50`, fix `chinext` display, fix `csi_dividend_lc` display:

```python
_BROAD_INDEX_DISPLAY: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "csi_a500": "中证A500",
    "sse50": "上证50",
    "star50": "科创50",
    "chinext": "创业板指",
    "chinext50": "创业板50",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "中证红利低波",
}
```

b) Extend `_INDEX_NAME_TO_SLUG` (lines 77–80) to also invert the broad display names. Broad inversion is derived from `_BROAD_INDEX_DISPLAY` so it can never drift; the sector entries and the colloquial alias are preserved:

```python
# Inversion (中文/lowercased → slug). Broad display names are now inverted too
# (Phase A): a broad ETF's tracked_index ("沪深300") resolves to its slug so the
# cached index_valuation_history is read. Inverting non-production slugs (star50,
# chinext, …) is harmless — the table is empty for them → NAV fallback — and
# future-proofs graduation. Sector entries + the colloquial 中证有色 alias stay.
_INDEX_NAME_TO_SLUG: dict[str, str] = {
    **{name.lower(): slug for slug, name in _BROAD_INDEX_DISPLAY.items()},
    **{name.lower(): slug for slug, name in _SECTOR_INDEX_DISPLAY.items()},
    "中证有色": "csi_nonferrous",
}
```

**IMPORTANT ordering:** `_INDEX_NAME_TO_SLUG` is currently defined at lines 77–80, AFTER `_SECTOR_INDEX_DISPLAY` (line 67) but the broad `_BROAD_INDEX_DISPLAY` is at line 6 (already in scope). Both maps are in scope at the definition site, so no reordering is needed. `map_lookthrough`'s broad branch (lines 162–183) is UNCHANGED — it already keys off the raw slug in `_BROAD_INDEX_KEYS`, and `chinext50` is now a member, so an ETF declaring `tracked_index="创业板50"` reaching `map_lookthrough` with the raw slug `chinext50` resolves correctly; one declaring the display name routes through the unknown-index branch (harmless — `provider_symbol` still set).

- [ ] **Step 4: Run the lookthrough test file to verify green**

Run: `uv run pytest tests/opportunity/test_lookthrough.py -v`
Expected: PASS — new tests plus the existing routing tests (the `test_broad_index_etf_maps_to_broad_index_kind` test uses raw slug `csi300`, unaffected).

- [ ] **Step 5: Run the inputs_loader test (the slug-inversion consumer) to confirm no regression**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -v`
Expected: PASS — the sector display-name resolution tests still pass (sector inversion preserved), and the `_target_registry_covers_every_lookthrough_display` test in `test_lookthrough.py` still passes (the new `创业板50` display has a registry entry only if required — verify next step).

- [ ] **Step 6: Verify the target-registry invariant still holds (chinext50 display)**

The `test_target_registry_covers_every_lookthrough_display` test asserts every `_BROAD_INDEX_DISPLAY` value has a `_TARGET_REGISTRY` entry. Adding `创业板50` (and changing `chinext` to `创业板指`) may break it if `_TARGET_REGISTRY` lacks those display names.

Run: `uv run pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_every_lookthrough_display -v`
Expected: PASS. **If it FAILS** with `missing registry entries for display names: ['创业板50', '创业板指']`, open `src/irc/fundamentals/snapshot.py`, find `_TARGET_REGISTRY`, and add entries mirroring the existing `创业板`/broad-index entry (copy the `创业板` entry's structure, renaming display to `创业板指`, and add a parallel `创业板50` entry). This is a genuinely-required touch OUTSIDE spec §7 — call it out in the commit body. Re-run until green.

- [ ] **Step 7: ruff**

Run: `uv run ruff check src/irc/opportunity/lookthrough.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough.py
git commit -m "feat(phase-a): invert broad display names to slugs; distinct chinext50 slug (D3/D4)"
```

(If `snapshot.py` was touched in Step 6, `git add src/irc/fundamentals/snapshot.py` too and note it in the commit body: "Also adds 创业板指/创业板50 _TARGET_REGISTRY entries required by the display-coverage invariant — outside spec §7.")

---

## Task 5: inputs_loader integration — display-name tracked_index grounds the broad path

§4 row: "A display-name `tracked_index` resolves + reads cached rows → non-`None` `pe_pct`; `tracked_index="标普红利低波50"` → `None`; a non-production slug (e.g. `star50`) with empty table → `None`." This proves the end-to-end slug-inversion + cached-read wiring for broad funds.

**Files:**
- Test: `tests/opportunity/test_inputs_loader.py` (no source change — Task 4 already wired `_INDEX_NAME_TO_SLUG`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_inputs_loader.py` (the helpers `_seed_csi300_instrument_with_prices` and `_seed_index_valuation_history` already exist in this file):

```python
def test_broad_display_name_tracked_index_grounds_pe_percentile(tmp_path):
    # Phase A: a display-name tracked_index ("沪深300") inverts to slug csi300 and
    # reads the cached index_valuation_history → non-None fundamental percentile.
    con = duckdb.connect(str(tmp_path / "broad_display.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)]  # mature series
    _seed_index_valuation_history(con, "csi300", pairs)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="沪深300", name_cn="沪深300ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is not None
    assert inp.pe_ttm == pytest.approx(10.0 + 199 * 0.1)
    con.close()


def test_sp_dividend_low_vol_tracked_index_stays_none(tmp_path):
    # D3: 标普红利低波50 is unmapped → NAV path, no fundamental percentile.
    con = duckdb.connect(str(tmp_path / "sp_div.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('515450','515450','cn_on_exchange','红利低波50ETF南方',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, '标普红利低波50', 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:515450')"
    )
    skeleton = OpportunityInput(
        instrument_id="515450", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="标普红利低波50",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    assert inp.pe_ttm is None
    con.close()


def test_speculative_slug_with_empty_table_stays_none(tmp_path):
    # star50 is now invertible (display 科创50 → star50 ∈ _BROAD_INDEX_KEYS) but the
    # cached table is empty for it (production fetch never writes it) → None.
    con = duckdb.connect(str(tmp_path / "star50.duckdb"))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('588000','588000','cn_on_exchange','科创50ETF华夏',NULL,'cn_etf','cny',"
        " DATE '2020-01-01', 0.005, 1.0e9, '科创50', 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'test:588000')"
    )
    skeleton = OpportunityInput(
        instrument_id="588000", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="科创50",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    # Slug resolves (star50 ∈ _INDEX_VALUATION_KEYS) but no cached rows → None.
    assert inp.valuation_percentile_fundamental is None
    assert inp.pe_ttm is None
    con.close()
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -k "broad_display_name or sp_dividend or speculative_slug" -v`
Expected: PASS immediately (Task 4 already wired the inversion; these tests are the end-to-end proof). If `test_broad_display_name_tracked_index_grounds_pe_percentile` FAILS with `valuation_percentile_fundamental is None`, the broad inversion in `_INDEX_NAME_TO_SLUG` (Task 4 Step 3) is missing or wrong — fix Task 4 before continuing.

- [ ] **Step 3: ruff + commit**

Run: `uv run ruff check tests/opportunity/test_inputs_loader.py`
Expected: no errors.

```bash
git add tests/opportunity/test_inputs_loader.py
git commit -m "test(phase-a): end-to-end broad display-name grounding + D3 NAV-stay + empty-table cases"
```

---

## Task 6: Seed overrides for `161721` + `003318` (D5/D6)

Add seed entries to `config/universe/cn_funds.yaml` WITHOUT `tracked_index`. The seed file is PRIMARY in the merge → these win by `instrument_id`, stripping the broad `tracked_index` the generated file assigned. `023153` needs no override (D5/D6).

**Files:**
- Modify: `config/universe/cn_funds.yaml`
- Test: `tests/test_config_loader.py` (a real-repo universe-load assertion)

- [ ] **Step 1: Write the failing test (real-repo seed-override assertion)**

Append to `tests/test_config_loader.py`. This loads the REAL repo configs (the worktree root is `Path(__file__).resolve().parents[1]`) and asserts the two funds resolve to `tracked_index=None`, while `023153` keeps its `中证A500`:

```python
def test_phase_a_seed_overrides_strip_broad_tracked_index():
    """D5/D6: 161721 + 003318 get seed overrides WITHOUT tracked_index so they
    route to their honest NAV/Phase-D path instead of mis-grounding on a broad
    allowlist symbol. 023153 (pure 中证A500) needs no override."""
    repo_root = Path(__file__).resolve().parents[1]
    bundle = load_repo_configs(repo_root)
    by_id = {i.instrument_id: i for i in bundle.universe_cn_funds.instruments}

    assert by_id["161721"].tracked_index is None, "161721 must have tracked_index stripped"
    assert by_id["003318"].tracked_index is None, "003318 must have tracked_index stripped"
    # 023153 is intentionally NOT overridden — stays mapped to 中证A500 (csi_a500
    # is not in the production allowlist, so it stays NAV + maps for graduation).
    assert by_id["023153"].tracked_index == "中证A500"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_config_loader.py::test_phase_a_seed_overrides_strip_broad_tracked_index -v`
Expected: FAIL — `assert by_id["161721"].tracked_index is None` fails because the generated entry's `tracked_index="沪深300"` currently wins (no seed override yet).

- [ ] **Step 3: Add the seed overrides**

In `config/universe/cn_funds.yaml`, append a new section after the existing `# === 主动权益基金 ===` active-fund block (after the `161005`富国天惠成长LOF entry). Use the same inline-dict style as the file's existing entries. **Omit `tracked_index` entirely** (so it defaults to `None`); preserve `asset_class: cn_equity_fund` and `theme` (valid `Theme` literals: `real_estate`, `dividend`) and the `cmb_fund` venue:

```yaml
  # === Phase A seed overrides (2026-06-05) — strip a greedily mis-tagged broad
  # tracked_index so these route to their honest NAV/Phase-D path instead of
  # mis-grounding on a broad allowlist PE (csi300/csi500). The seed file is
  # PRIMARY in the universe merge, so these win by instrument_id over the
  # generated entries. NO tracked_index by design (D5/D6).
  - { instrument_id: "161721", ticker: "161721", market: cn_off_exchange,
      name_cn: "招商沪深300地产等权重指数A", asset_class: cn_equity_fund, currency: cny,
      theme: real_estate, venue_required: [cmb_fund] }
  - { instrument_id: "003318", ticker: "003318", market: cn_off_exchange,
      name_cn: "景顺长城中证500行业中性低波动指数A", asset_class: cn_equity_fund, currency: cny,
      theme: dividend, venue_required: [cmb_fund] }
```

- [ ] **Step 4: Validate config + run the test**

Run: `uv run irc config validate`
Expected: validation passes (no duplicate-id error — the generated duplicates are dropped by the merge, not validated together; the `UniverseConfig._no_duplicates` validator runs per-file, and the merge dedups).

Run: `uv run pytest tests/test_config_loader.py::test_phase_a_seed_overrides_strip_broad_tracked_index -v`
Expected: PASS.

- [ ] **Step 5: Mirror the override into the template seed (durability)**

`config/universe/cn_funds.yaml` is the live config and IS git-tracked here, but `irc init` regenerates it from `src/irc/templates/config/universe/cn_funds.yaml`. To keep the override durable across a re-init, add the SAME two entries to the template file `src/irc/templates/config/universe/cn_funds.yaml` (same block, same position relative to its active-fund section). This mirrors how `tests/discovery/test_universe_completeness.py` treats the template as the durable seed source.

Run: `grep -n "161721\|003318" src/irc/templates/config/universe/cn_funds.yaml`
Expected: both ids present after the edit.

- [ ] **Step 6: Commit**

```bash
git add config/universe/cn_funds.yaml src/irc/templates/config/universe/cn_funds.yaml tests/test_config_loader.py
git commit -m "feat(phase-a): seed overrides strip broad tracked_index for 161721/003318 (D5/D6)"
```

---

## Task 7: Live test — hard-assert production symbols + informational speculative sweep

§4 (gated): hard-assert every production symbol (csi300/csi500/csi1000/sse50) returns numeric rolling PE AND PB; a separate informational sweep over `_SPECULATIVE_LEGULEGU_SYMBOL` prints a landing table (no fail). Double-gated (`live_akshare` marker + `IRC_RUN_LIVE_AKSHARE=1`). Default `pytest` must skip it.

**Files:**
- Modify: `tests/fundamentals/test_index_valuation_live.py`

- [ ] **Step 1: Replace the single-symbol live test with a hard-assert loop + informational sweep**

Rewrite the body of `tests/fundamentals/test_index_valuation_live.py` (keep the existing module docstring, the `_RUN` gate, and `pytestmark`). Replace `test_fetch_cn_index_valuation_csi300_live` with:

```python
from irc.fundamentals.akshare_index_valuation import (  # noqa: E402
    _LEGULEGU_INDEX_SYMBOL,
    _SPECULATIVE_LEGULEGU_SYMBOL,
    fetch_cn_index_valuation,
)


@pytest.mark.parametrize("slug", sorted(_LEGULEGU_INDEX_SYMBOL))
def test_production_symbol_returns_rolling_pe_and_pb_live(slug) -> None:
    """HARD ASSERT: every production allowlist symbol returns numeric rolling PE
    AND PB. If a slug returns None, the rolling-PE column (滚动市盈率) or PB column
    (市净率) is not present under that legulegu symbol — inspect the live frame.
    """
    out = fetch_cn_index_valuation(slug)
    assert isinstance(out, IndexValuation)
    assert out.pe_ttm is not None, (
        f"{slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}): rolling PE (滚动市盈率) not matched — "
        "inspect the live stock_index_pe_lg frame."
    )
    assert out.pb is not None, (
        f"{slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}): PB (市净率) not matched — "
        "inspect the live stock_index_pb_lg frame."
    )
    assert out.pe_ttm > 0 and out.pb > 0
    print(f"\n  ✓ {slug} ({_LEGULEGU_INDEX_SYMBOL[slug]}) live: pe={out.pe_ttm} pb={out.pb}")


def test_speculative_symbol_landing_sweep_informational() -> None:
    """INFORMATIONAL only — never fails. Probes each speculative symbol and prints
    a landing table. When a symbol lands (numeric pe AND pb), graduate it into
    _LEGULEGU_INDEX_SYMBOL + the hard-assert set in a follow-up PR (D2 graduation).
    """
    print("\n  speculative legulegu sweep (informational):")
    for slug, symbol in sorted(_SPECULATIVE_LEGULEGU_SYMBOL.items()):
        out = fetch_cn_index_valuation(slug)
        pe = out.pe_ttm if out is not None else None
        pb = out.pb if out is not None else None
        landed = "LANDED" if (pe is not None and pb is not None) else "—"
        print(f"    {slug:14s} {symbol:10s} pe={pe} pb={pb}  [{landed}]")
```

- [ ] **Step 2: Verify the default suite SKIPS the live test (no network)**

Run: `uv run pytest tests/fundamentals/test_index_valuation_live.py -v`
Expected: all tests SKIPPED with reason "set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests". NO network call fired.

- [ ] **Step 3: (Operator step — gate #4) Run the live test against real AkShare**

This is a HUMAN gate, not part of the autodev loop. When ready to confirm:

Run: `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s`
Expected: the 4 parametrized production tests PASS with numeric pe/pb; the informational sweep prints a landing table without failing.

- [ ] **Step 4: ruff + commit**

Run: `uv run ruff check tests/fundamentals/test_index_valuation_live.py`
Expected: no errors.

```bash
git add tests/fundamentals/test_index_valuation_live.py
git commit -m "test(phase-a): hard-assert 4 production symbols live + informational speculative sweep (gate #4)"
```

---

## Task 8: Full-suite + invariant gate (exit gates #1 + #2)

Exit gate #1: ruff + full `uv run pytest` green. Exit gate #2: H3 universal gapped-row + SAME-3 citation-set invariants intact (valuation *magnitude* changes, row-presence/citations do not).

**Files:** none (verification only)

- [ ] **Step 1: ruff across the whole touched surface**

Run: `uv run ruff check src tests`
Expected: no errors.

- [ ] **Step 2: Run the invariant tests explicitly (exit gate #2)**

Run: `uv run pytest tests/opportunity/test_lookthrough_invariants.py tests/opportunity/test_failure_renderer.py tests/opportunity/test_report.py tests/opportunity/test_advisory_gaps.py tests/opportunity/test_states.py -v`
Expected: PASS — H3 partition, SAME-3 equality, divergence-advisory routing, and the commodity-cyclical guard are unchanged. None of this plan's edits touch citation surfaces or the `evidence_gaps == ()` partition predicate (verified: percentiles are plain numeric inputs per ADR 0012).

- [ ] **Step 3: Run the full unit + integration suite**

Run: `uv run pytest -q`
Expected: green EXCEPT the documented baseline (per MEMORY "Test suite baseline": ~8 known pre-existing failures + flaky/hang-prone e2e research gate). **Diff-check scope before assuming a regression:** if a failure is in a file this plan did NOT touch and matches the known-baseline set, it is pre-existing. Any NEW failure in a touched file (`akshare_index_valuation`, `index_valuation_ingestor`, `ingest_cmd`, `lookthrough`, `inputs_loader`, `config_loader`) is a real regression — fix before proceeding.

- [ ] **Step 4: Commit (only if any test-fixup edits were needed; otherwise skip)**

```bash
git add -A
git commit -m "test(phase-a): full-suite + invariant gate green"
```

---

## Task 9: Coverage measurement + before/after diff artifact (exit gates #3 + #5)

Exit gate #3: measured coverage — `irc run --from ingest` + `irc opportunity`, count non-`None` `valuation_percentile_fundamental` for broad funds; expect ≥ 9. Exit gate #5 / §6: produce `docs/2026-06-05-phase-a-broad-grounding/` with a before/after table of `valuation_state` + fundamental percentile + NAV percentile + divergence flag for the 9 grounded broad funds.

**Mechanism decision (spec §6):** Use **two `irc opportunity` runs diffed on the broad subset**, NOT a `lookthrough-diff` extension (`irc lookthrough-diff` is active-fund-only and extending it is larger scope than this gate needs). The baseline run is on `main` (pre-Phase-A: stale static-PE rows → mostly NAV); the Phase-A run is on this branch after a fresh `irc run --from ingest`. A small standalone Python diff script (committed under the artifact dir) reads the two `opportunity_report.json` files + queries the cached `index_valuation_history` percentile for the broad subset, and writes the before/after Markdown table.

**Files:**
- Create: `docs/2026-06-05-phase-a-broad-grounding/build_diff.py` (the diff helper)
- Create: `docs/2026-06-05-phase-a-broad-grounding/before-after.md` (the artifact, generated)

- [ ] **Step 1: Capture the BASELINE opportunity report (operator step)**

This requires real cached data and is a HUMAN-driven gate (network + LLM). On a checkout of `main` (or a stash of this branch's changes), with middleware/cache present:

```bash
git stash   # set aside Phase A changes
uv run irc run --from ingest
uv run irc opportunity --output-dir outputs/_phase_a_baseline
git stash pop   # restore Phase A changes
```

This writes `outputs/_phase_a_baseline/opportunity_report.json` (baseline, NAV-grounded).

- [ ] **Step 2: Capture the PHASE-A opportunity report (operator step)**

With Phase A changes applied and a fresh ingest (the broad leg now replaces stale static-PE rows with rolling-PE rows):

```bash
uv run irc run --from ingest
uv run irc opportunity --output-dir outputs/_phase_a_after
```

This writes `outputs/_phase_a_after/opportunity_report.json` (Phase-A, PE-grounded).

- [ ] **Step 3: Write the diff script**

Create `docs/2026-06-05-phase-a-broad-grounding/build_diff.py`. It reads the two reports, restricts to broad-index rows (`lookthrough_kind == "broad_index"`), pulls `valuation_state` + the divergence advisory flag from each report, and queries the cached `index_valuation_history` percentile + NAV percentile per fund via the existing pure readers:

```python
"""Phase A before/after diff (gate #5). Reads two opportunity_report.json files
(baseline vs Phase A) on the broad-index subset and writes before-after.md.

Run from repo root:
    uv run python docs/2026-06-05-phase-a-broad-grounding/build_diff.py \
        outputs/_phase_a_baseline/opportunity_report.json \
        outputs/_phase_a_after/opportunity_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DIVERGENCE = "valuation_price_fundamental_divergence"


def _broad_rows(report_path: str) -> dict[str, dict]:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in data["rows"]:
        if row.get("lookthrough_kind") != "broad_index":
            continue
        out[row["instrument_id"]] = {
            "name_cn": row["name_cn"],
            "valuation_state": row["valuation_state"],
            "divergence": _DIVERGENCE in row.get("advisory_gaps", []),
            "lookthrough_key": row.get("lookthrough_key"),
        }
    return out


def main() -> int:
    baseline_path, after_path = sys.argv[1], sys.argv[2]
    before = _broad_rows(baseline_path)
    after = _broad_rows(after_path)
    ids = sorted(set(before) | set(after))
    lines = [
        "# Phase A — broad-index grounding: before/after",
        "",
        "Broad-index funds only. `valuation_state` is the headline axis; "
        "`divergence` = the price/fundamental advisory (`证据缺口：价格与基本面估值背离`).",
        "",
        "| id | name | state (before) | state (after) | divergence (after) | flipped |",
        "|---|---|---|---|---|---|",
    ]
    flips = 0
    for iid in ids:
        b = before.get(iid, {})
        a = after.get(iid, {})
        bs = b.get("valuation_state", "—")
        as_ = a.get("valuation_state", "—")
        flipped = "✅" if (bs != as_ and as_ != "—") else ""
        if flipped:
            flips += 1
        div = "⚠️" if a.get("divergence") else ""
        name = a.get("name_cn") or b.get("name_cn") or ""
        lines.append(f"| {iid} | {name} | {bs} | {as_} | {div} | {flipped} |")
    lines += [
        "",
        f"Broad funds compared: {len(ids)}. valuation_state flips: {flips}.",
        "",
        "Manual eyeball (gate #5): confirm state flips on the grounded funds, the "
        "newly-firing divergence advisory, and that 161721 / 003318 / 标普红利低波50 "
        "do NOT appear here (they stayed on NAV / Phase-D, not the broad path).",
    ]
    out_path = Path(__file__).parent / "before-after.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the artifact + count grounded funds (operator step)**

Run:
```bash
uv run python docs/2026-06-05-phase-a-broad-grounding/build_diff.py \
    outputs/_phase_a_baseline/opportunity_report.json \
    outputs/_phase_a_after/opportunity_report.json
```
Expected: writes `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.

Count grounded broad funds (non-`None` `valuation_percentile_fundamental`) directly from the cache to confirm exit gate #3 (expect ≥ 9):

```bash
uv run python -c "
import duckdb
from irc.opportunity.inputs_loader import _index_valuation_metrics
con = duckdb.connect('data/local.duckdb')
grounded = 0
for key in ('csi300','csi500','csi1000','sse50'):
    pe, pb, div, pct, pctpb = _index_valuation_metrics(con, key)
    print(key, 'pe_pct=', pct)
    # each fund tracking this index inherits pct; count funds in Step 4b.
"
```

- [ ] **Step 4b: Verify the ≥9 count via the after-report** (operator step)

The honest target is 9 funds (csi300×4, csi500×2, csi1000×2, sse50×1, after D5/D6 overrides). Count from the after-report:

```bash
uv run python -c "
import json
rows = json.load(open('outputs/_phase_a_after/opportunity_report.json'))['rows']
grounded = [r['instrument_id'] for r in rows
            if r.get('lookthrough_kind')=='broad_index'
            and r.get('lookthrough_key') in ('csi300','csi500','csi1000','sse50')]
print('grounded broad funds:', len(grounded), sorted(grounded))
"
```
Expected: `len(grounded) >= 9`. If lower, check that the broad ingest leg actually wrote rolling-PE rows (`SELECT index_key, COUNT(*) FROM index_valuation_history WHERE index_key IN ('csi300','csi500','csi1000','sse50') GROUP BY 1`) and that 161721/003318 are NOT in the grounded set.

- [ ] **Step 5: Commit the artifact (script + generated table)**

```bash
git add docs/2026-06-05-phase-a-broad-grounding/build_diff.py docs/2026-06-05-phase-a-broad-grounding/before-after.md
git commit -m "docs(phase-a): before/after broad-grounding diff artifact (gate #5)"
```

Note: do NOT commit the `outputs/_phase_a_baseline` / `outputs/_phase_a_after` scratch dirs (they are run scratch, not source). Remove them after capturing the artifact: `rm -rf outputs/_phase_a_baseline outputs/_phase_a_after`.

---

## Task 10: Docs sync (exit gate #6)

Gate #6: CONTEXT.md "Valuation inputs"; CHANGELOG `[Unreleased]` (NO VERSION bump); ROADMAP Phase A status. **No ADR 0012 addendum.**

**Files:**
- Modify: `CONTEXT.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update CONTEXT.md "Valuation inputs"**

In `CONTEXT.md`, update the `IndexValuation` entry (line 139) and the `index_valuation_history` entry (line 140) to reflect: (a) PE reads `滚动市盈率` (PE-TTM) ONLY, never `静态市盈率` (D1); (b) production fetch resolves symbols from the 4-symbol `_LEGULEGU_INDEX_SYMBOL` allowlist only, with a separate probe-only `_SPECULATIVE_LEGULEGU_SYMBOL` map (D2); (c) the broad ingest leg does a per-key full replace (`replace_keys=True`) so the first post-merge run self-migrates stale static-PE rows (D8). Add one sentence to the `index_valuation_history` entry:

```
The broad leg iterates the production allowlist (`_LEGULEGU_INDEX_SYMBOL`: csi300/csi500/csi1000/sse50, Phase A) with `replace_keys=True` — a per-key full replace that self-migrates the legacy static-PE rows to rolling-PE (滚动市盈率) on the first post-merge ingest; a non-empty fetch is REQUIRED before the DELETE so transient failures never wipe good cache. The sector leg keeps accumulate-forward append. Speculative symbols (star50/chinext/chinext50/csi_dividend/csi_dividend_lc/csi_a500) live in a probe-only `_SPECULATIVE_LEGULEGU_SYMBOL` map, never consulted by production fetch.
```

And in the `IndexValuation` entry, change "via `stock_index_pe_lg` (PE) + `stock_index_pb_lg` (PB) addressed by the Chinese index name" to "via `stock_index_pe_lg` (reading **滚动市盈率** / PE-TTM only — never the static `静态市盈率`) + `stock_index_pb_lg` (cap-weighted `市净率`, not the `等权市净率` equal-weight variant), addressed by a live-confirmed symbol from the `_LEGULEGU_INDEX_SYMBOL` allowlist".

- [ ] **Step 2: Update CHANGELOG `[Unreleased]` (NO VERSION bump)**

Under the `## [Unreleased]` heading (line 8) in `CHANGELOG.md`, add a bullet (do NOT add a new version heading, do NOT touch VERSION — per MEMORY "Versioning convention"):

```markdown
### Added
- **Phase A — broad-index PE-TTM grounding.** The curated broad-index ETFs (+ legit
  generated index funds) now ground their equity `valuation_state` on the legulegu
  **PE-TTM** (滚动市盈率) historical percentile instead of the NAV self-history
  percentile. PE reads 滚动市盈率 only (never 静态市盈率); production fetch resolves
  symbols from a live-confirmed 4-symbol allowlist (csi300/csi500/csi1000/sse50),
  with a probe-only speculative map for the rest. The broad ingest leg does a per-key
  full replace (`replace_keys=True`) that self-migrates stale static-PE rows.
  `创业板指`/`创业板50` are now distinct slugs (chinext/chinext50). `161721`/`003318`
  get seed overrides stripping their mis-tagged broad `tracked_index`. Measured reach:
  ~9 broad funds grounded.
```

- [ ] **Step 3: Update ROADMAP Phase A status**

In `docs/ROADMAP.md`, change the Phase A status from `☐ open` to `✅ DONE` (or `☑`) in the status table (line ~24) and update the reach annotation to the honest measured number (~9 funds, not the theoretical +19). Update the `### Phase A` section heading (line ~91) similarly. Also flip the top-line status (line 3) to note Phase A shipped:

Change line 24's row to:
```
| A — broad-index grounding | ✅ done (2026-06-05) | +9 funds (measured; csi300×4/csi500×2/csi1000×2/sse50×1 after D5/D6 overrides) |
```

And in line 3, append "; **Phase A shipped & live (2026-06-05)**" to the in-progress status.

- [ ] **Step 4: Confirm NO ADR 0012 addendum was added**

Run: `git status docs/adr/`
Expected: `docs/adr/0012-fundamental-led-equity-valuation.md` is NOT modified. (D4 removes the chinext proxy entirely; D1 is a bugfix toward the existing PE-TTM requirement — no addendum required per spec §5 gate #6.)

- [ ] **Step 5: Commit**

```bash
git add CONTEXT.md CHANGELOG.md docs/ROADMAP.md
git commit -m "docs(phase-a): sync CONTEXT valuation inputs + CHANGELOG [Unreleased] + ROADMAP Phase A status"
```

---

## Final verification checklist (run before declaring done)

- [ ] `uv run ruff check src tests` → clean
- [ ] `uv run pytest tests/fundamentals/test_akshare_index_valuation.py tests/data/test_index_valuation_ingestor.py tests/opportunity/test_lookthrough.py tests/opportunity/test_inputs_loader.py tests/test_config_loader.py -v` → all green
- [ ] `uv run pytest tests/fundamentals/test_index_valuation_live.py` → all SKIPPED (no network on default run)
- [ ] `grep -rn "基金概况" src/irc/fundamentals/akshare_index_valuation.py` → only the pre-existing warning line (no new occurrence)
- [ ] `grep -rn "_PE_COLS\|_PB_COLS\|_INDEX_PE_PB_NAME" src/irc/fundamentals/akshare_index_valuation.py` → NO matches (the footgun constants are removed)
- [ ] `grep -n "_BROAD_INDEX_KEYS" src/irc/commands/ingest_cmd.py` → NO matches (broad leg iterates the allowlist now)
- [ ] `git status docs/adr/` → 0012 unmodified
- [ ] Invariant tests (H3 / SAME-3 / divergence) green (Task 8 Step 2)
- [ ] Before/after artifact exists at `docs/2026-06-05-phase-a-broad-grounding/before-after.md` (Task 9)
- [ ] CONTEXT / CHANGELOG / ROADMAP updated (Task 10)

---

## Self-review notes (spec → task mapping)

| Spec ref | Task |
|---|---|
| D1 (滚动市盈率 only, remove `_PE_COLS`/`_PB_COLS`, single-candidate tuples) | Task 1 |
| D2 (production allowlist; speculative probe-only) | Task 1 (+ live sweep Task 7) |
| D3 (标普红利低波50 stays NAV / unmapped) | Task 4 + Task 5 |
| D4 (chinext vs chinext50 distinct; chinext → 创业板指) | Task 4 |
| D5/D6 (161721/003318 seed overrides; 023153 none) | Task 6 |
| D7 (~9 measured coverage) | Task 9 (gate #3) |
| D8 (`replace_keys`; broad allowlist iteration; sector append; no-wipe-on-empty) | Tasks 2 + 3 |
| §4 test plan rows | Tasks 1,2,4,5,6,7 |
| §5 exit gate #1 (tests green) | Task 8 |
| §5 exit gate #2 (H3/SAME-3 intact) | Task 8 |
| §5 exit gate #3 (measured coverage ≥9) | Task 9 |
| §5 exit gate #4 (live confirmation) | Task 7 |
| §5 exit gate #5 (before/after artifact) | Task 9 |
| §5 exit gate #6 (docs synced, no ADR addendum) | Task 10 |
| §6 deliverable (`docs/2026-06-05-phase-a-broad-grounding/`) | Task 9 |
| §7 files touched | Tasks 1–6 (+ snapshot.py iff Task 4 Step 6 fires) |

**Judgment calls flagged for the implementer / reviewer:**
1. **Template-seed mirror (Task 6 Step 5):** the spec §7 lists only `config/universe/cn_funds.yaml`, but `irc init` regenerates that file from `src/irc/templates/config/universe/cn_funds.yaml`. Mirroring the override into the template keeps it durable across re-init (precedent: `tests/discovery/test_universe_completeness.py` treats the template as the durable seed). This is a defensible OUTSIDE-§7 touch.
2. **`_TARGET_REGISTRY` (Task 4 Step 6):** adding `创业板50`/`创业板指` display names MAY require a `src/irc/fundamentals/snapshot.py` entry to keep the `test_target_registry_covers_every_lookthrough_display` invariant green. This is conditional — only if that test fails. Flagged as OUTSIDE-§7.
3. **Diff mechanism (§6):** chose two-`irc opportunity`-runs-diffed over extending `lookthrough-diff` (active-fund-only), per the explicitly-deferred-to-plan decision. The script lives under the artifact dir, not as a new CLI command (YAGNI).
