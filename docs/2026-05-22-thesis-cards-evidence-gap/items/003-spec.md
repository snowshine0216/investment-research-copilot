# Item 003 spec — active-fund constituent layer + per-stock analysis (Slices A + G + HK news adapter)

## Goal

Build the runtime fetch engine that produces **per-fund top-N constituent evidence** for CN active equity funds, with first-class HK constituent support. This slice unblocks the "ANALYZE ONE by ONE" mandate from the source diagnosis (`docs/diagnosis-thesis-cards-evidence-gap.md` §1.2): every `cn_equity_fund` row gets a `ConstituentAnalysis` list of structured per-stock evidence (filings + broker + news) routed by the holding's market (CN / HK / US). The slice extends `LookthroughTarget` to carry `provider_symbol`, changes `build_snapshot` to accept the typed target (dispatching to a new `_build_active_fund_snapshot`), introduces an `ActiveFundSnapshot` carrying disclosure-quarter-keyed cache metadata, wires auto-build-on-cache-miss into `_build_rows`, and ships the new `fetch_hk_stock_news` adapter (Q2 resolution — committed). Item 005 (Slice F) covers fund-level NAV + announcement adapters for gold / bond / passive ETF / tracked CN indices; item 006 (Slice H) layers the Policy B weight-aware quorum and the structured `rejections.json` log on top of the data this item produces; item 007 (D1/D3) renders the data in memo + discipline; item 009 (D2) enables the canonical-path citation gate. Item 003 ONLY produces the data — it does NOT enforce coverage gates, does NOT render evidence pool entries, and does NOT write `rejections.json`. Acceptance is: cold run produces non-empty `constituent_analyses` on every `cn_equity_fund` row whose holdings adapter returned data; second run on the same day costs zero AkShare calls.

## In scope

**Slice A sub-rows (data path):**

1. **A1** — Remove `"cn_equity_fund"` from `NON_INDEXABLE_ASSET_CLASSES` (`src/irc/opportunity/thesis_evidence.py:276-278`). Keep `gold`, `cn_bond_fund`, and `qdii_global` (the latter is excluded for a different reason — info-leg unavailable, see item 005).
2. **A2** — Reorder `map_lookthrough` so the `cn_equity_fund` branch fires **BEFORE** the `tracked_index` branch (currently L114) and the `theme` branch (currently L124). Extend `LookthroughTarget` from 3 fields to 4 by adding `provider_symbol: str = ""`. Themed AND unthemed CN equity funds return `LookthroughTarget(kind="active_fund", key=f"fund_{inp.instrument_id}", display_cn=inp.name_cn, provider_symbol=inp.instrument_id)`. Update the `LookthroughKind` `Literal` to keep `"active_fund"` (already present).
3. **A3a (holdings contract)** — Change `fetch_cn_etf_holdings(symbol, *, as_of="", top_n=10) -> tuple[Constituent, ...]` to `fetch_cn_etf_holdings(provider_symbol: str, *, as_of: str = "", top_n: int = 10) -> HoldingsResult` where `HoldingsResult = (constituents: tuple[FundHolding, ...], source_report_date: str, source_report_quarter: str)`. Introduce `FundHolding(symbol, name_cn, weight_pct, exchange, provider_symbol)`. Exchange parser (see §"Exchange parser specification" below).
4. **A3b (snapshot dispatch)** — Change `build_snapshot(lookthrough_target: str, *, top_n=10, as_of_iso="") -> ConstituentSnapshot` to `build_snapshot(target: LookthroughTarget, *, top_n=10, as_of_iso="")`. Dispatch on `target.kind == "active_fund"` → new `_build_active_fund_snapshot(target, top_n, as_of_iso) -> ActiveFundSnapshot`. All non-active-fund kinds (`broad_index`, `sector_theme`, `qdii_us`, `qdii_hk`, `bond`, `gold`, `qdii_global`) continue to dispatch to the existing `_TARGET_REGISTRY`-driven path keyed by `target.display_cn` — **this legacy path is preserved untouched** and still returns `ConstituentSnapshot`. The return type of `build_snapshot` becomes a union `ActiveFundSnapshot | ConstituentSnapshot`; callers narrow via `isinstance`.
5. **A3c (HK news adapter)** — Introduce `fetch_hk_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]`. Lives in `src/irc/fundamentals/hkex_client.py` (companion to `fetch_hk_filing_digest`). Implementation prefers `ak.stock_hk_news_em(symbol=stock)`; falls back to a thin HKEX news scraper inside `hkex_client.py` if the AkShare function is unavailable. Returns same `NewsItem` shape as the new CN news adapter (`title`, `url`, `published_iso`, `summary`).
6. **A3d (per-stock evidence routing)** — `_build_active_fund_snapshot` fetches holdings via `fetch_cn_etf_holdings(target.provider_symbol)` then, per holding, dispatches by `FundHolding.exchange`:
   - `"SH" | "SZ" | "BJ"` (CN A-share) → `fetch_cn_filing_digest(symbol)` + `fetch_cn_broker_reports(symbol)` + `fetch_cn_stock_news(symbol, top_k=3)` (new — see A3e).
   - `"HK"` → `fetch_hk_filing_digest(symbol)` + `fetch_hk_stock_news(symbol, top_k=3)`. **NEVER `fetch_cn_broker_reports`.**
   - `"US"` → no adapter call; record `"us_evidence_unsupported:{symbol}"` in failure reasons.
   - `"UNKNOWN"` → no adapter call; record `"exchange_unknown:{symbol}"`.
7. **A3e (CN news adapter)** — Introduce `fetch_cn_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]` in `src/irc/fundamentals/akshare_fundamentals.py`, wrapping `ak.stock_news_em(symbol=stock)`. Returns top-K most recent. The diagnosis Q7 already commits to top-3.
8. **A3f (ConstituentAnalysis construction)** — Per holding, the snapshot builder constructs a `ConstituentAnalysis(symbol, name_cn, weight_pct, evidence, failure_reasons, one_line_view)` where `evidence: tuple[ThesisEvidence, ...]` carries every successful adapter response as a full `ThesisEvidence` (with the provenance contract from item 002: `scope="constituent"`, `owner_instrument_id=fund_id`, `parent_fund_id=fund_id`, `constituent_key=symbol`, `citation_kind` per adapter classification). Empty adapter responses or exceptions append a string reason to `failure_reasons`.
9. **A3g (one_line_view)** — Each `ConstituentAnalysis.one_line_view` is a deterministic ≤60-char human label assembled from the same evidence, useful for memo inline rendering and discipline reports (see §"one_line_view format").
10. **A4** — Cache layout: `data/fundamentals/{source_report_quarter}/active_fund/fund_{iid}.json` for active funds. **`source_report_quarter` comes from the provider response**, NOT the calendar quarter (the parser converts `"2024年1季度股票投资明细"` → `"2024Q1"`). `ActiveFundSnapshot.cache_probed_at` records the most-recent freshness probe (ISO date). Freshness rule: on canonical runs, if `cache_probed_at` > `IRC_CACHE_FRESHNESS_DAYS` (default 7), probe via `fetch_cn_etf_holdings(provider_symbol, top_n=1)` reading just the latest quarter. Probe failure (exception or empty) → **fail-closed**: treat cache as stale, schedule full re-fetch. Successful probe with unchanged quarter → update `cache_probed_at`, reuse cached body. The legacy non-active-fund cache layout (`data/fundamentals/<quarter>/<target_display>.json`) is untouched.
11. **A5a (preflight ledger)** — `_build_rows` computes a `FetchPlan` BEFORE any adapter call: count active-fund cache misses + stale active-fund caches × `(1 + top_N × 3)` calls. Add the legacy passive cost only as a placeholder (`stub=0` — item 005 fills it). Abort with a per-category breakdown if total > `IRC_FETCH_BUDGET` (default **2000**).
12. **A5b (resumable state)** — Per-item fetch state persisted to `data/fundamentals/.fetch_state_{plan_hash}.json` where `plan_hash = sha256(f"{output_date}:{','.join(sorted(instrument_ids))}:{top_N}".encode()).hexdigest()[:12]`. Atomic write via `.tmp → os.replace`. Cross-process advisory locking via stdlib `fcntl.flock(LOCK_EX | LOCK_NB)` — no new third-party dependency (see §"Open questions" Q-A and decision).
13. **A5c (dev limit)** — `--limit N` flag on `irc opportunity`/`irc run --from opportunity` caps the number of `cn_equity_fund` rows that auto-build via the new path. **Rejected on canonical `outputs/<date>/` paths** (exit code 2). `--rebuild-fundamentals` forces full re-fetch (ignores cache).
14. **A5d (autobuild env var)** — `IRC_OPPORTUNITY_AUTOBUILD=1` (default on). When set to `0`, `_build_rows` skips the active-fund build on cache miss (preserves the current "load-only" behaviour for offline / debugging runs).
15. **A6** — `_build_rows` threads the constructed `ActiveFundSnapshot` into `build_opportunity_row` so `derive_thesis_from_evidence` can read `snapshot.constituent_analyses` and produce per-constituent `OpportunityRow.constituent_analyses` AND a flattened `OpportunityRow.thesis_evidence`.

**Slice G sub-rows (per-stock structured field):**

16. **G1** — Introduce `ConstituentAnalysis` dataclass in `src/irc/opportunity/types.py`. **Add** `constituent_analyses: tuple[ConstituentAnalysis, ...] = ()` to `OpportunityRow` — item 002 did NOT add this field (verified: `src/irc/opportunity/types.py:180-198` has no such field; only `DisciplineRow` carries the `tuple[object, ...] = ()` placeholder). `src/irc/opportunity/report.py:35-37` already accesses it defensively via `getattr(row, "constituent_analyses", ())`, so adding the field is the missing wiring. Add `constituent_analyses: tuple[ConstituentAnalysis, ...] = ()` to `ThesisCard` (the field does not exist yet on `ThesisCard`). Narrow `DisciplineRow.constituent_analyses` from `tuple[object, ...] = ()` to `tuple[ConstituentAnalysis, ...] = ()`.
17. **G2** — `derive_thesis_from_evidence` accepts the new `ActiveFundSnapshot` type. For active-fund inputs, it returns the per-constituent analyses straight through to `OpportunityRow.constituent_analyses` AND flattens all per-constituent `evidence` lists into `OpportunityRow.thesis_evidence` (so the audit gate in item 009 can iterate a single tuple). The signature changes to:
    ```python
    derive_thesis_from_evidence(
        snapshot: ConstituentSnapshot | ActiveFundSnapshot | None,
        theme_report: ThemeReport | None,
        *, asset_class: str | None = None,
        owner_instrument_id: str,
    ) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...], tuple[ConstituentAnalysis, ...]]
    ```
    The trailing `tuple[ConstituentAnalysis, ...]` is the new return slot. All non-active-fund call paths return `()` for that slot.
18. **G3** — `_row_to_dict` already serializes `constituent_analyses` via `asdict()` (item 002 wired the `getattr(...)` line). Verify it correctly serializes `ConstituentAnalysis` — including the nested `evidence: tuple[ThesisEvidence, ...]` and `failure_reasons: tuple[str, ...]`. `_card_to_dict` already uses `asdict(card)`; add a defensive `citation_id` check for nested constituent evidence equivalent to the existing top-level check at `report.py:69-73`.
19. **G6** — Three tests (see §"Acceptance criteria" + diagnosis G6).

**HK news adapter (Q2 resolution — committed):**

20. New `fetch_hk_stock_news(stock, top_k=3)` in `hkex_client.py`. Tagged `citation_kind="information"`. Empty response → record `"hk_news_empty:{stock}"`. Exception → `"hk_news_fetch_failed:{stock}:{reason}"`. Both flow into the constituent's `failure_reasons`, NOT into the fund-level snapshot's `failure_reasons_by_symbol` (those are reserved for adapter-level catastrophic failures like the holdings call itself).

## Out of scope

- **F1 (passive fund-level evidence — gold, cn_bond_fund, cn_etf, tracked CN indices)** → item 005.
- **F2 `fetch_fund_nav_report` + `fund_announcement_em` adapters** → item 005 (live-verified in item 004 first).
- **F1 QDII exclusion logic** (`evidence_gaps=["qdii_information_unavailable"]`) → item 005.
- **H1 / H2 Policy B weight-aware quorum gate** (per-holding data-leg, top-half info-leg quorum, gap stamping) → item 006. **Item 003 only populates the data — it never stamps `evidence_gaps`.**
- **H2 structured `rejections.json`** → item 006.
- **H3 universal gapped-row invariant** (skip thesis_card emission for gapped rows) → item 006.
- **D1 memo evidence_pool rendering** with `[ref:{citation_id}]` markers and per-constituent inline lines → item 007.
- **D1c memo alias-builder** (`build_alias_maps`) → item 007.
- **D3 discipline report nesting** (`## 持仓明细` appendix, per-fund constituent bullets) → item 007.
- **D2 / D2a / D2b / D2c audit gates** (`find_uncited_opportunity_rows`, `find_missing_pick_citations`, `find_uncited_conclusions`, `find_uncited_discipline_rows`) → item 009.
- **B1 / B2 DuckDB `fund_holdings` ingestor** → item 010.
- **C1 / C2 sector-themed news routing** → V2 (skipped, see `SKIPPED.md`).
- **Sector-routing of theme reports** (`_resolve_research_theme` unchanged — every `cn_equity_fund` still resolves to `holdings_sector` for the supplemental macro citation slot).

## Detailed schema specifications

All new dataclasses live in `src/irc/opportunity/types.py` or `src/irc/fundamentals/types.py`; choice noted per dataclass.

### `LookthroughTarget` (extended — `src/irc/opportunity/types.py`)

```python
@dataclass(frozen=True)
class LookthroughTarget:
    kind: LookthroughKind     # unchanged Literal
    key: str                  # unchanged
    display_cn: str           # unchanged
    provider_symbol: str = ""  # NEW — defaults to "" for backward compat
```

`provider_symbol` is non-empty ONLY for `kind == "active_fund"`. For all other kinds it stays `""`. Test sites in §"Files touched" list every call site that must be updated.

### `NewsItem` (new — `src/irc/fundamentals/types.py`)

```python
@dataclass(frozen=True)
class NewsItem:
    symbol: str             # holding ticker the news is about
    title: str
    url: str
    published_iso: str      # YYYY-MM-DD
    summary: str            # may be ""
    source: str             # "stock_news_em" | "stock_hk_news_em" | "hkex_scraper"
```

### `FundHolding` (new — `src/irc/fundamentals/types.py`)

```python
@dataclass(frozen=True)
class FundHolding:
    symbol: str             # normalized ticker for adapter routing (e.g. "600519", "00700")
    name_cn: str
    weight_pct: float       # 0.0–100.0 (percent, NOT fraction)
    exchange: Literal["SH", "SZ", "BJ", "HK", "US", "UNKNOWN"]
    provider_symbol: str    # raw value from provider, retained for debugging
```

`weight_pct` is in percent units (e.g. `3.46`), matching the provider's `占净值比例` column directly (current code divides by 100, but we keep percent here so the renderer can show "权重 3.5%" naturally; the existing `Constituent.weight` fraction semantics remain for the legacy non-active-fund path).

### `HoldingsResult` (new — `src/irc/fundamentals/types.py`)

```python
@dataclass(frozen=True)
class HoldingsResult:
    constituents: tuple[FundHolding, ...]
    source_report_date: str       # e.g. "2024-03-31" (best-effort parse from 季度 column)
    source_report_quarter: str    # e.g. "2024Q1" (canonical YYYY[Q1-4] format)
```

`source_report_date` is the last day of the inferred fiscal quarter (e.g. `2024-03-31` for Q1). If the provider response doesn't include enough info to determine a date, set to `""` (but `source_report_quarter` must always be non-empty when constituents are non-empty).

### `ActiveFundSnapshot` (new — `src/irc/fundamentals/types.py`)

```python
@dataclass(frozen=True)
class ActiveFundSnapshot:
    fund_id: str
    source_report_date: str
    source_report_quarter: str
    cache_probed_at: str                       # ISO date YYYY-MM-DD; "" if never probed
    constituent_analyses: tuple[ConstituentAnalysis, ...]
    failure_reasons_by_symbol: dict[str, tuple[str, ...]]
    # Fund-level catastrophic failures (e.g. holdings adapter returned empty):
    fund_level_failure_reasons: tuple[str, ...] = ()
```

`failure_reasons_by_symbol` carries per-constituent diagnostics keyed by symbol. `fund_level_failure_reasons` exists for `holdings_fetch_failed:{fund_id}:{reason}` so item 006 (H2) can distinguish "no constituents at all" from "10 constituents with partial coverage".

### `ThesisEvidence.holding_weight_pct` (NEW OPTIONAL FIELD — see note below)

`src/irc/memo/citation_selector.py:28` reads `getattr(e, "holding_weight_pct", 0.0)` defensively, anticipating item 003 attaches the field. Item 003 MUST add it:

```python
@dataclass(frozen=True)
class ThesisEvidence:
    # ...existing fields...
    holding_weight_pct: float | None = None   # NEW — set for scope="constituent" entries; None otherwise
```

For every `ThesisEvidence` emitted inside `ConstituentAnalysis.evidence`, `holding_weight_pct = FundHolding.weight_pct` (percent units, 0.0–100.0). For all other scopes (`instrument`, `asset_class_macro`, `policy`), leave as `None`. The selector treats `None` as `0.0` (already coded). Field is appended at the END of `ThesisEvidence` AFTER `citation_id` to preserve the `__post_init__` hash invariant (it is NOT part of the citation_id preimage — item 003 does not change the hash contract from ADR 0001).

### `ConstituentAnalysis` (new — `src/irc/opportunity/types.py`)

```python
@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str             # normalized ticker
    name_cn: str
    weight_pct: float       # 0.0–100.0 percent
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str      # ≤60 chars, see §one_line_view format
```

All `ThesisEvidence` entries inside `.evidence` carry `scope="constituent"`, `owner_instrument_id=fund_id`, `parent_fund_id=fund_id`, `constituent_key=symbol`. The item 002 provenance contract enforces these at `ThesisEvidence.__post_init__`.

### `OpportunityRow.constituent_analyses` (NEW FIELD — not narrowing)

```python
# Item 002 status: field NOT present on OpportunityRow (only on DisciplineRow).
# Item 003: add the field.
constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

Field added AFTER `fetch_types_attempted` (current last field of `OpportunityRow`) to keep constructor positional ordering stable for the many existing call sites. `report.py:35-37` already reads via `getattr(...)` defensively, so existing callers continue to work; new callers in `build_opportunity_row` start populating the field.

### `ThesisCard.constituent_analyses` (new field)

```python
constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

Field added at the END of the dataclass (after `expected_omissions`) to preserve constructor ordering for unrelated callers.

### `DisciplineRow.constituent_analyses` (narrowed)

```python
# Before (item 002):
constituent_analyses: tuple[object, ...] = ()

# After (item 003):
constituent_analyses: tuple[ConstituentAnalysis, ...] = ()
```

## Exchange parser specification

`_parse_exchange(row: pd.Series) -> str` derived from each row of the `fund_portfolio_hold_em` DataFrame.

**Strategy 1 — prefer `股票市场` column if present:**

Match by `substring containment` (NOT exact match) — the AkShare column is free-text and varies by version (`沪市A`, `深市主板`, `创业板`, `科创板`). Match priority is HK/US first so values like `"港股主板"` don't accidentally hit `主板`.

| `股票市场` contains | Mapped exchange |
|---|---|
| `港` (covers `港交所`, `港股`, `港股主板`) | `"HK"` |
| `纽` / `纳斯达克` / `美` (excluding `美的` collision — column never carries stock names) | `"US"` |
| `沪` / `上交所` / `上证` | `"SH"` |
| `深` / `深交所` / `深证` / `创业板` / `中小板` | `"SZ"` |
| `北` / `北交所` / `京` (covers `北京证券交易所`) | `"BJ"` |
| `科创板` | `"SH"` (科创板 trades on Shanghai) |
| anything else | fall through to Strategy 2 |

**Conservative fallthrough:** if Strategy 1 finds a column value but no substring matches, treat as a Strategy-1 miss and fall through to Strategy 2 (do NOT stamp `UNKNOWN` prematurely — the column may carry a new value AkShare added).

**Strategy 2 — ticker-prefix routing (used when `股票市场` is absent OR Strategy 1 fell through):**

Let `raw = str(row["股票代码"]).strip()`. Strip any existing exchange suffix (`".SH"`, `".SZ"`, `".HK"`, `".US"`). The remaining ticker is `code`.

| Condition | Exchange | Notes |
|---|---|---|
| `code` ends with `.HK` (before suffix-strip) OR `len(code) in (4, 5)` AND `code.isdigit()` | `"HK"` | HK codes are 4–5 digits with optional leading zeros (`0700`, `00700`, `09988`). The 4-digit branch is critical — without it `"0700"` falls through to `"SZ"` via the next rule. |
| `len(code) == 6` AND `code[0] == "6"` | `"SH"` | A-share Shanghai (e.g. `600519`). |
| `len(code) == 6` AND `code[0] in {"0", "3"}` | `"SZ"` | A-share Shenzhen (e.g. `000333`, `300750`). |
| `len(code) == 6` AND `code[0] in {"4", "8"}` | `"BJ"` | Beijing Stock Exchange (e.g. `430139`, `831010`). |
| US ticker (alphabetic, e.g. `AAPL`) | `"US"` | Letters-only code. |
| anything else | `"UNKNOWN"` | Records `exchange_unknown:{symbol}` in the constituent's `failure_reasons`. |

**Regression test (mandatory):** `00700` (5-digit HK code) in a fixture WITHOUT `股票市场` column → `exchange == "HK"`, NOT `"UNKNOWN"` or `"SZ"`. Same for `0700` (4-digit) and `09988`.

**Edge case — current `_to_qualified_symbol` mis-routes `00700` to `00700.SZ`.** The new `_parse_exchange` must run BEFORE the existing `_to_qualified_symbol` for the active-fund path; the legacy path (CN index constituents) keeps using `_to_qualified_symbol` unchanged.

**Quarter column parsing:** `season_text = row["季度"]` is text like `"2024年1季度股票投资明细"`. The parser extracts year + quarter via regex `r"(\d{4})年(\d)季度"`. Result `"2024年1季度..."` → `source_report_quarter="2024Q1"`, `source_report_date="2024-03-31"`. If the regex fails to match, both fields default to `""` and the builder records a fund-level failure reason `"holdings_quarter_parse_failed:{provider_symbol}"`.

Accept both `季度` and `报告期` column names (some AkShare versions use the latter); the parser tries each in order.

## Market-routed evidence fetch specification

Per holding, the snapshot builder picks an adapter set based on `FundHolding.exchange`:

| Exchange | Filing (data) | Broker (info) | News (info) | Forbidden |
|---|---|---|---|---|
| `SH`, `SZ`, `BJ` | `fetch_cn_filing_digest(symbol)` | `fetch_cn_broker_reports(symbol)` | `fetch_cn_stock_news(symbol, top_k=3)` | — |
| `HK` | `fetch_hk_filing_digest(symbol)` | — (no HK broker adapter ships in V1) | `fetch_hk_stock_news(symbol, top_k=3)` | `fetch_cn_broker_reports`, `fetch_cn_filing_digest`, `fetch_cn_stock_news` |
| `US` | none in V1 | none | none | All CN/HK adapters |
| `UNKNOWN` | none | none | none | All adapters |

**Failure reason codes (canonical, sorted):**

| Code (placeholders filled at call site) | When emitted |
|---|---|
| `"holdings_fetch_failed:{fund_id}:{reason}"` | `fetch_cn_etf_holdings` raised or returned empty. Emitted into `ActiveFundSnapshot.fund_level_failure_reasons`. |
| `"holdings_quarter_parse_failed:{fund_id}"` | `季度` / `报告期` column missing or unparseable. |
| `"exchange_unknown:{symbol}"` | Both Strategy 1 and Strategy 2 failed to assign an exchange. |
| `"us_evidence_unsupported:{symbol}"` | Constituent has `exchange == "US"`. V1 ships no US adapters. |
| `"filing_fetch_failed:{symbol}:{reason}"` | `fetch_cn_filing_digest` / `fetch_hk_filing_digest` raised. |
| `"filing_empty:{symbol}"` | Filing adapter returned None / empty digest. |
| `"broker_fetch_failed:{symbol}:{reason}"` | `fetch_cn_broker_reports` raised. (CN only — HK never calls this.) |
| `"broker_empty:{symbol}"` | Broker adapter returned `()`. |
| `"news_fetch_failed:{symbol}:{reason}"` | `fetch_cn_stock_news` raised. |
| `"news_empty:{symbol}"` | `fetch_cn_stock_news` returned `()`. |
| `"hk_news_fetch_failed:{symbol}:{reason}"` | `fetch_hk_stock_news` raised. |
| `"hk_news_empty:{symbol}"` | `fetch_hk_stock_news` returned `()` because `ak.stock_hk_news_em` returned an empty DataFrame. |
| `"hk_news_unsupported_adapter:{symbol}"` | `ak.stock_hk_news_em` not available in installed AkShare (ImportError / AttributeError detection at lazy-import). Distinguishes "AkShare doesn't ship the adapter" from "adapter ran and returned empty". |

`{reason}` is `type(exc).__name__` (e.g. `"ConnectionError"`); the full traceback is not encoded.

**Budget:** per-fund call count = `1` (holdings) + `top_N × num_adapters_for_each_exchange`. Worst case: top_N=10 CN-only fund = 1 + 10 × 3 = 31. Worst-case 52 cn_equity_fund rows (verified from `outputs/2026-05-21/scoring.json`) = 52 × 31 = 1612 active-fund calls. Plus item 005's passive overhead (≤ 200) and freshness probes — total fits under `IRC_FETCH_BUDGET=2000`.

## fetch_hk_stock_news adapter specification

**Function signature:** `def fetch_hk_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]`

**Location:** `src/irc/fundamentals/hkex_client.py` (companion to `fetch_hk_filing_digest`).

**Primary path:** `ak.stock_hk_news_em(symbol=normalized_hk_code)` where `normalized_hk_code` uses the existing `_normalize_hk_code` helper (strips `.HK`, zero-pads to 5 digits — e.g. `"00700"`).

**Fallback path (only if AkShare doesn't expose `stock_hk_news_em` at import time):** a thin HKEX news scraper. **For V1, the fallback may be a stub that returns `()` and records the gap** — this is acceptable because the budget regression in item 008 / item 009 already classifies `hk_news_empty` as a quorum failure and the user accepts that some HK constituents may be info-gapped. **Implementation choice:** the planner picks scraper vs. stub-empty based on time budget; if a working scraper exists in `hkex_client.py` after item 003 ships, the empty-stub path is replaced.

**Detection:** at module import time, set `_HAS_AK_HK_NEWS = hasattr(ak, "stock_hk_news_em")` (lazy-imported inside `_ak_call`, NOT module-level — see existing `_ak_call` pattern).

**Return shape:** `tuple[NewsItem, ...]` length ≤ `top_k`, sorted by `published_iso` descending.

**Tagging in evidence:** each `NewsItem` is wrapped in a `ThesisEvidence` carrying `type="news"`, `source=item.source`, `url=item.url`, `date=item.published_iso`, `summary=item.title or item.summary[:120]`, `scope="constituent"`, `citation_kind="information"`, `owner_instrument_id=fund_id`, `parent_fund_id=fund_id`, `constituent_key=symbol`.

**Empty / failure handling:** see §"Failure reason codes" above (`hk_news_empty:{stock}` and `hk_news_fetch_failed:{stock}:{reason}`).

**Required test (fixture-based):** mock `_ak_call("stock_hk_news_em", symbol="00700")` returning a 5-row DataFrame with columns `["发布时间", "标题", "内容摘要", "新闻链接"]` (verified shape — may need adjustment from live response; capture once during impl). Assert top-3 ordering by date and `citation_kind="information"`.

## Cache layout + freshness contract

- **Active-fund cache path:** `data/fundamentals/{source_report_quarter}/active_fund/fund_{iid}.json` (e.g. `data/fundamentals/2024Q1/active_fund/fund_005827.json`).
- **Legacy path (untouched):** `data/fundamentals/{quarter}/{display_cn}.json` for CN ETFs / tracked indices / QDII (existing `ConstituentSnapshot` callers).
- **Cache key invariant:** `source_report_quarter` is **provider-declared** (from the `季度` column), NOT calendar quarter. Tests assert the cache directory matches the snapshot's `source_report_quarter`, not `date.today()`.
- **`cache_probed_at`:** ISO date stamp updated on every successful freshness probe (even if no refresh occurred). Empty string on first write.
- **Freshness rule (`IRC_CACHE_FRESHNESS_DAYS`, default 7):** if (`today - cache_probed_at`).days > threshold AND output path is canonical (`outputs/<YYYY-MM-DD>/`), trigger a freshness probe. Probe = `fetch_cn_etf_holdings(provider_symbol, top_n=1)` reading only the latest quarter. If the probe's `source_report_quarter` > cached `source_report_quarter` → full re-fetch. If equal → update `cache_probed_at`, reuse cache body.
- **Fail-closed semantics:** any probe exception OR empty probe result → treat cache as stale, schedule full re-fetch (consume the full budget reservation).
- **`--rebuild-fundamentals`:** forces full re-fetch regardless of cache state; skips probe.
- **Quarter advancement on probe:** when probe reveals a newer quarter, the OLD cache file at the previous quarter directory is left in place (never deleted by item 003 — disk hygiene is item 010's concern if anyone's). The NEW snapshot writes to the new quarter directory.

## Preflight budget ledger

`FetchPlan` is computed at the start of `_build_rows` (before any adapter call other than cache reads):

```
plan = FetchPlan(
    active_fund_misses=N1,          # no cache file
    active_fund_stale=N2,            # cache exists but cache_probed_at expired
    passive_misses=0,                # placeholder — item 005 fills in
    passive_stale=0,                 # placeholder — item 005
    top_n=TOP_N_DEFAULT,              # = 10
)

total_calls = (N1 + N2) * (1 + TOP_N_DEFAULT * 3) + passive_misses * 2 + passive_stale * 2
if total_calls > IRC_FETCH_BUDGET:
    raise FetchBudgetExceeded(plan, total_calls, IRC_FETCH_BUDGET)
```

`IRC_FETCH_BUDGET` env var, default `2000`. Abort exits with code 3 and prints the per-category breakdown to stderr.

**Resumable state file:** `data/fundamentals/.fetch_state_{plan_hash}.json` where:

```python
plan_hash = sha256(f"{output_date}:{','.join(sorted(instrument_ids))}:{TOP_N_DEFAULT}".encode()).hexdigest()[:12]
```

State shape:

```json
{
  "plan_hash": "abc123def456",
  "started_at": "2026-05-22T10:00:00",
  "items": [
    {"fund_id": "005827", "status": "complete",
     "source_report_quarter": "2024Q1", "fetched_at": "2026-05-22T10:05:32"},
    {"fund_id": "501025", "status": "in_progress", "fetched_at": "2026-05-22T10:07:00"}
  ]
}
```

**Atomic write:** `tmp_path = path.with_suffix(".json.tmp"); tmp_path.write_text(...); tmp_path.replace(path)`.

**Locking (resolved — see Open Q-A):** acquire `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on the state file before write. If lock contention raises `BlockingIOError`, retry once after 100 ms; on second failure, exit with code 4 ("concurrent run detected — set `IRC_OPPORTUNITY_AUTOBUILD=0` or wait for the other run"). **No new dependency** — `fcntl` is stdlib (Unix-only — Windows users get a no-op lock and a stderr warning; the codebase already targets `>=3.12` and the run environment is macOS/Linux per `CLAUDE.md`).

**Resume contract:** on entry to `_build_rows`, if `.fetch_state_{plan_hash}.json` exists AND its `plan_hash` matches: pick up only the items NOT marked `complete`. If `plan_hash` mismatches the on-disk file (different run shape): IGNORE the stale state, start fresh, overwrite the file. `--force-resume` is rejected on canonical paths.

## Auto-build wiring

- `IRC_OPPORTUNITY_AUTOBUILD` env var; default `"1"` (on). Setting `"0"` disables the new active-fund autobuild and falls back to the legacy "load cached snapshot only" behaviour (matches item 002's status quo).
- In `_build_rows`, after computing `target = map_lookthrough(inp)`, the dispatch becomes:
  ```python
  if target.kind == "active_fund" and AUTOBUILD_ON:
      snap_obj = snapshot_cache.get(target.key)
      if snap_obj is None:
          snap_obj = _load_active_fund_cached(target, root / "data")
          if snap_obj is None or _is_stale(snap_obj):
              snap_obj = build_snapshot(target, top_n=TOP_N_DEFAULT)
              _write_active_fund_cache(snap_obj, root / "data")
          snapshot_cache[target.key] = snap_obj
  else:
      target_name = target.display_cn  # legacy path — unchanged
      if target_name not in snapshot_cache:
          snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
  ```
- Result is passed into `build_opportunity_row(..., snapshot=snap_obj, ...)`. `build_opportunity_row` forwards into `derive_thesis_from_evidence` which now accepts `ActiveFundSnapshot | ConstituentSnapshot | None`.

## one_line_view format

`one_line_view` is a deterministic ≤60-char compact label per constituent, derived from the most-significant evidence entries. Format template:

```
{filing_fragment} · {broker_fragment} · {news_fragment}
```

Where (each fragment is dropped if not available):

| Fragment | Source | Example |
|---|---|---|
| `filing_fragment` | latest filing | `"24Q1 营收+18%"` (CN A-share); `"24FY 营收+12%"` (HK); `"-"` if no filing |
| `broker_fragment` | most recent broker rating | `"买入(中金)"`; omitted if no broker (HK case) |
| `news_fragment` | most recent news title, truncated to 24 chars | `"新品发布"`; omitted if no news |

**No evidence at all** → `one_line_view = "证据获取失败"` (always non-empty so memo rendering has something to show).

This is purely for human readability; the audit gate (item 009) reads structured `.evidence`, not `one_line_view`.

## Acceptance criteria

1. **Themed CN active fund routing.** `OpportunityInput(asset_class="cn_equity_fund", instrument_id="005827", name_cn="易方达蓝筹精选", theme="consumer")` → `map_lookthrough(inp) == LookthroughTarget(kind="active_fund", key="fund_005827", display_cn="易方达蓝筹精选", provider_symbol="005827")`. The `theme="consumer"` branch is NOT taken.
2. **Unthemed CN active fund routing.** `OpportunityInput(asset_class="cn_equity_fund", instrument_id="005827", name_cn="易方达蓝筹精选")` (no theme, no tracked_index) → same result as (1). No more `"主动权益"` generic display.
3. **Legacy lookthrough untouched.** `asset_class="us_etf", tracked_index="nasdaq100"` → `LookthroughTarget("qdii_us", "nasdaq100", "纳斯达克100", provider_symbol="")`. `asset_class="gold"` → `LookthroughTarget("gold", "gold", "黄金", provider_symbol="")`.
4. **Holdings contract.** `fetch_cn_etf_holdings("005827", top_n=10)` returns `HoldingsResult(constituents, source_report_date, source_report_quarter)`. `constituents` is `tuple[FundHolding, ...]` (NOT legacy `tuple[Constituent, ...]`). All five existing tests in `tests/fundamentals/test_akshare_fundamentals.py` are updated to assert on `HoldingsResult.constituents` and on the new quarter fields.
5. **Snapshot dispatch.** `build_snapshot(LookthroughTarget("active_fund", "fund_005827", "...", "005827"))` returns `ActiveFundSnapshot`. `build_snapshot(LookthroughTarget("broad_index", "csi300", "沪深300"))` returns `ConstituentSnapshot` (legacy path).
6. **Per-stock evidence — CN fund.** Stubbed 10-stock CN fund with all three adapters returning data → `ActiveFundSnapshot.constituent_analyses` has 10 entries; each has `evidence` containing ≥1 filing (`citation_kind="data"`) + ≥1 broker (`citation_kind="information"`) + ≥1 news (`citation_kind="information"`). All `evidence` entries carry `scope="constituent"`, `parent_fund_id="005827"`, `constituent_key=<symbol>`.
7. **Per-stock evidence — HK constituents.** Mixed-market fund with 3 SH + 3 HK + 4 SZ holdings. Assert HK holdings use `fetch_hk_filing_digest` + `fetch_hk_stock_news` ONLY; assert `fetch_cn_broker_reports` is NEVER called for HK symbols.
8. **Exchange parser — HK regression.** Fixture without `股票市场` column containing rows `["00700", "0700", "09988", "600519", "AAPL", "830839"]` → exchanges `["HK", "HK", "HK", "SH", "US", "BJ"]`.
9. **Exchange parser — `股票市场` priority.** Same ticker `"00700"` with `股票市场="深交所"` → `exchange="SZ"` (column takes precedence). Same with `股票市场="港交所"` → `exchange="HK"`.
10. **Failure routing — empty holdings.** `fetch_cn_etf_holdings` returns `HoldingsResult((), "", "")` → `ActiveFundSnapshot.constituent_analyses == ()`, `fund_level_failure_reasons` contains `"holdings_fetch_failed:005827:<reason>"`. **Item 003 does NOT stamp `OpportunityRow.evidence_gaps`** — item 006 reads `fund_level_failure_reasons` and stamps gaps.
11. **Cache write.** First run on `005827` with provider quarter `2024Q1` → file written at `data/fundamentals/2024Q1/active_fund/fund_005827.json` (NOT `2026Q1` calendar quarter, NOT `2026-05-22/`).
12. **Cache reuse — second run.** Same-day second run reads from cache; AkShare call counter is `0` for `fund_portfolio_hold_em`, `stock_financial_abstract`, `stock_research_report_em`, `stock_news_em`, `stock_hk_news_em`. (Test patches `_ak_call` with a counter mock.)
13. **Freshness probe — stale cache, same quarter.** Cache `cache_probed_at = "2026-05-08"` (today=`2026-05-22`, threshold=7 days) → probe fires, returns same `2024Q1` → no full re-fetch, `cache_probed_at` advances to `2026-05-22`. 1 AkShare call total.
14. **Freshness probe — stale cache, new quarter.** Same as (13) but probe returns `2024Q2` → full re-fetch fires; new cache at `data/fundamentals/2024Q2/active_fund/fund_005827.json`.
15. **Freshness probe — fail-closed.** Probe raises `ConnectionError` → full re-fetch fires (same as new quarter). The original cache is left in place at the old quarter dir until the rebuild succeeds.
16. **Preflight budget abort.** `IRC_FETCH_BUDGET=10` + 5 cold cn_equity_fund rows (cost 5 × 31 = 155) → run aborts with exit code 3 and a stderr line `"FetchBudgetExceeded: active_fund_misses=5 cost=155 budget=10"`. No `.tmp` files created in `outputs/<date>/`.
17. **`--limit` accepted (non-canonical path).** `irc run --from opportunity --limit 3 --output-dir /tmp/scratch/` succeeds, only processes 3 active-fund rows (deterministic order: sorted by `instrument_id`).
18. **`--limit` rejected (canonical path).** `irc run --from opportunity --limit 3 --output-dir outputs/2026-05-22/` exits with code 2 and stderr `"--limit is rejected on canonical output paths"`.
19. **Resumable state.** Mid-run interrupt (raise after item 3 of 5) → state file `.fetch_state_<hash>.json` exists with 3 items marked `complete`. Re-run picks up items 4 and 5 only; AkShare call counter for the first 3 stays at 0.
20. **Resumable state — stale hash discarded.** State file with plan_hash `"abc123"` exists; new run has plan_hash `"def456"` (different output_date) → stale state silently ignored, file overwritten on first successful fetch.
21. **Resumable state — concurrent lock.** Two processes start with the same plan_hash → second exits with code 4 and `"concurrent run detected"`.
22. **`IRC_OPPORTUNITY_AUTOBUILD=0` honoured.** With env var unset to `0` and no cache, the active-fund row gets `snapshot=None`, `constituent_analyses=()`, and `evidence_gaps` retains its item 002 behaviour. No AkShare calls.
23. **`--rebuild-fundamentals` forces refresh.** Cache exists for `005827` → `--rebuild-fundamentals` triggers a full re-fetch; AkShare counter > 0.
24. **`thesis_cards.yaml` carries the new fields.** `005827` card has `lookthrough_kind: "active_fund"`, `lookthrough_key: "fund_005827"`, non-empty `constituent_analyses` (≥5 entries on a real-shaped fixture), and `thesis_evidence` containing ≥1 filing + ≥1 broker + ≥1 news entry whose `constituent_key` matches a concrete stock symbol.
25. **`evidence_gaps` no longer contains `missing_constituent_snapshot` for `cn_equity_fund`** (provided the fund's holdings adapter returned data; gapless funds vs. gapped funds is item 006's concern).
26. **`ConstituentAnalysis` schema invariants.** Constructing `ConstituentAnalysis(symbol="600519", name_cn="贵州茅台", weight_pct=6.2, evidence=(), failure_reasons=("filing_empty:600519",), one_line_view="证据获取失败")` succeeds. Constructing with negative `weight_pct` or empty `symbol` raises (via dataclass post-init validation — add lightweight checks).
27. **`OpportunityRow.constituent_analyses` is typed `tuple[ConstituentAnalysis, ...]`** — mypy / typing check passes; passing `tuple[dict, ...]` fails type-check.
28. **`_row_to_dict` serialization round-trip.** `OpportunityRow(constituent_analyses=(ConstituentAnalysis(...),))` → JSON → parse → all fields including nested `evidence[0].citation_id` are non-empty.
29. **G6 (a) — full success.** 10-stock fund, all adapters succeed → `constituent_analyses` has 10 entries; sum of `len(c.evidence) for c in analyses` ≥ 30 (10 filings + 10 broker + 10 news).
30. **G6 (b) — partial success.** 10-stock fund where holdings 6–10 all have `filing_empty` + `broker_empty` + `news_empty` → those entries appear with empty `evidence` and `failure_reasons` containing all three reason codes. `ActiveFundSnapshot.constituent_analyses` has 10 entries (NOT 5).
31. **G6 (c) — production-path smoke.** Real-shaped AkShare fixtures (captured under `tests/fixtures/akshare/`) for `fund_portfolio_hold_em`, `stock_financial_abstract`, `stock_research_report_em`, `stock_news_em`. Assert: constituent news entries carry `scope="constituent"`, `citation_kind="information"`, `type="news"`; the fund-level `ActiveFundSnapshot.fund_level_failure_reasons` is empty.

## Edge cases

- **All 10 holdings fail to fetch any adapter** (each constituent has only `failure_reasons`, no `evidence`). Item 003 still produces 10 `ConstituentAnalysis` entries (with empty `evidence`). Item 006 (H2) reads this and stamps `evidence_gaps=["holdings_fetch_failed"]` — out of scope here.
- **US-only fund** (e.g. a niche QDII active fund, unlikely but possible). All 10 holdings get `exchange="US"` → all `failure_reasons=("us_evidence_unsupported:<symbol>",)`. Item 003 records this; item 006 handles the row-level disposition.
- **Mixed CN + HK fund** (e.g. `501025` 鹏华中证香港银行指数(LOF)A). 8 HK + 2 CN holdings; verify the test in (7) — CN adapters never called for HK constituents.
- **Provider returns `季度` AND `报告期` columns** simultaneously → parser prefers `季度`; both column-presence flags are tested.
- **Probe returns same quarter** → cache reused, `cache_probed_at` advances. No full re-fetch.
- **Probe network error** → fail-closed (full re-fetch). 1 wasted probe call counted against budget.
- **Concurrent runs trying to write same `.fetch_state_*.json`** → `fcntl.flock` rejects the second process. Test patches `fcntl.flock` to raise `BlockingIOError`.
- **`股票代码` column contains `"sz000333"` prefix form** → parser strips `"sz"` / `"sh"` prefix before applying length-based routing.
- **Quarter parse failure** (e.g. provider returns `"2024年中报"` instead of `"2024年2季度..."`) → fund-level `holdings_quarter_parse_failed:{fund_id}` recorded; no constituents emitted (treated like empty holdings).
- **Weight 0.0** (provider reports 0% for a holding — happens when 占净值比例 column is blank) → still emitted as `FundHolding` with `weight_pct=0.0`. Item 006's quorum logic handles weight=0 (sorts to bottom).
- **First-time write — no `cache_probed_at`.** New cache has `cache_probed_at=""` (empty string). The staleness check treats `""` as "older than threshold" iff today > `IRC_CACHE_FRESHNESS_DAYS` ago — i.e., the first write itself sets `cache_probed_at` to today's date.

## Dependencies on other items

**Hard requires (must merge before item 003):**

- Item 001 — `OpportunityRow.contributing_dimensions` + `OpportunityRow.fetch_types_attempted` (already merged per the run context).
- Item 002 — `ThesisEvidence.citation_id` + provenance fields (`scope`, `citation_kind`, `owner_instrument_id`, `parent_fund_id`, `constituent_key`); `CitationMeta`; `CitedMap` type aliases; `select_citations`; `DisciplineRow.constituent_analyses` placeholder field; `_row_to_dict` already serializes `constituent_analyses` via `asdict()` and `getattr`.

**Required-by (items that read item 003's outputs):**

- Item 005 (F) — passive fund-level evidence consumes the same cache layout and `IRC_FETCH_BUDGET`. Also: `LookthroughTarget.provider_symbol` is reused for fund-level NAV adapter dispatch.
- Item 006 (H) — Policy B reads `ActiveFundSnapshot.constituent_analyses` and `failure_reasons_by_symbol`; stamps `OpportunityRow.evidence_gaps`; writes `rejections.json`.
- Item 007 (D1) — memo evidence_pool reads `OpportunityRow.constituent_analyses` to render per-constituent lines.
- Item 007 (D3) — discipline `## 持仓明细` appendix reads `DisciplineRow.constituent_analyses`.
- Item 009 (D2) — audit gate iterates `OpportunityRow.constituent_analyses` and `OpportunityRow.thesis_evidence` for per-driver citation enforcement.

## Files touched (preview for planner)

| File | Action |
|---|---|
| `src/irc/opportunity/types.py` | Add `provider_symbol` to `LookthroughTarget`. Add `ConstituentAnalysis` dataclass. Narrow `OpportunityRow.constituent_analyses` and `DisciplineRow.constituent_analyses` to `tuple[ConstituentAnalysis, ...]`. Add `ThesisCard.constituent_analyses` field. |
| `src/irc/opportunity/lookthrough.py` | Reorder branches: `cn_equity_fund` first. Update return value to include `provider_symbol`. |
| `src/irc/opportunity/thesis_evidence.py` | Remove `cn_equity_fund` from `NON_INDEXABLE_ASSET_CLASSES`. Update `derive_thesis_from_evidence` signature to accept `ActiveFundSnapshot \| ConstituentSnapshot \| None` and return a trailing `tuple[ConstituentAnalysis, ...]` slot. Flatten per-constituent evidence into the row-level `thesis_evidence`. |
| `src/irc/opportunity/cards.py` | Update `build_thesis_card` to thread `row.constituent_analyses` into `ThesisCard.constituent_analyses`. |
| `src/irc/opportunity/report.py` | Add defensive `citation_id` check for nested constituent evidence in `_card_to_dict`. (No `_row_to_dict` change — already covered by item 002.) |
| `src/irc/fundamentals/types.py` | Add `NewsItem`, `FundHolding`, `HoldingsResult`, `ActiveFundSnapshot`. |
| `src/irc/fundamentals/akshare_fundamentals.py` | Change `fetch_cn_etf_holdings` signature + return type. Add `fetch_cn_stock_news`. Add `_parse_exchange`, `_parse_quarter_column` helpers. |
| `src/irc/fundamentals/hkex_client.py` | Add `fetch_hk_stock_news`. Detection of `ak.stock_hk_news_em`. Optional scraper fallback or stub-empty. |
| `src/irc/fundamentals/snapshot.py` | Change `build_snapshot` signature to accept `LookthroughTarget`. Add `_build_active_fund_snapshot`. Keep legacy `_build_cn_snapshot` / `_build_us_snapshot` / `_build_hk_snapshot` / `_build_hk_index_snapshot` untouched; dispatch by `target.kind`. |
| `src/irc/fundamentals/snapshot_cache.py` | Add `active_fund_cache_path`, `load_active_fund_cache`, `write_active_fund_cache`, `_active_fund_snapshot_to_dict`, `_active_fund_snapshot_from_dict`. Keep legacy `cache_path` / `load_cached_snapshot` / `load_latest_cached_snapshot` / `write_snapshot` untouched. |
| `src/irc/commands/opportunity_cmd.py` | Update `_build_rows`: typed-target dispatch, autobuild, preflight ledger, resumable state, `--limit`, `--rebuild-fundamentals` flags. |
| `src/irc/commands/fundamentals_cmd.py` | Update call site of `build_snapshot` to construct `LookthroughTarget` from CLI input (currently passes string). |
| `src/irc/commands/cli_args.py` (or wherever `irc opportunity` arg parsing lives) | Add `--limit`, `--rebuild-fundamentals` flags; canonical-path rejection logic. |
| `tests/opportunity/test_types.py` | Update 4 `LookthroughTarget(...)` constructors to use the 4-field form (default `provider_symbol=""` so old call sites compile). Add `ConstituentAnalysis` tests. |
| `tests/opportunity/test_lookthrough.py` | Add tests for the new branch ordering. |
| `tests/opportunity/test_thesis_evidence.py` | Update tests for the new return tuple shape; add active-fund path tests. |
| `tests/opportunity/test_report.py` | Update `LookthroughTarget(...)` calls; add `constituent_analyses` round-trip test. |
| `tests/opportunity/test_selection.py` | Update existing `LookthroughTarget(...)` calls. |
| `tests/opportunity/test_cards.py` | Update existing `LookthroughTarget(...)` calls; add `ThesisCard.constituent_analyses` test. |
| `tests/opportunity/test_discipline.py` | Update `LookthroughTarget(...)` calls. |
| `tests/opportunity/test_citation_map.py` | Update `LookthroughTarget(...)` calls. |
| `tests/opportunity/test_trim_triggers.py` | Update `LookthroughTarget(kind="index", ...)` — this is INVALID per item 002's `LookthroughKind` Literal; replace with `kind="broad_index"`. |
| `tests/commands/test_opportunity_cmd.py` | Update `LookthroughTarget(...)` calls; add `_build_rows` autobuild test + `--limit` test + preflight abort test. |
| `tests/commands/test_fundamentals_cmd.py` | Update `build_snapshot` mock to expect `LookthroughTarget`. |
| `tests/fundamentals/test_akshare_fundamentals.py` | Update 5 `fetch_cn_etf_holdings` tests to assert `HoldingsResult`. Add `fetch_cn_stock_news` tests + `_parse_exchange` regression tests. |
| `tests/fundamentals/test_snapshot.py` | Update 10+ `build_snapshot("string")` calls to construct `LookthroughTarget`. Add `_build_active_fund_snapshot` tests including the empty-holdings failure path. |
| `tests/fundamentals/test_hkex_client.py` (new or existing) | Add `fetch_hk_stock_news` tests. |
| `tests/fundamentals/test_snapshot_cache.py` (new) | Active-fund cache path + freshness probe + atomic write + lock contention tests. |
| `tests/fixtures/akshare/` | New fixture files for `fund_portfolio_hold_em` with `股票市场` column, without `股票市场` column, with HK constituents, with mixed CN/HK; `stock_hk_news_em` sample; `stock_news_em` sample. |
| `docs/adr/0002-active-fund-constituent-layer.md` (new optional ADR) | Document the typed-target dispatch + cache layout decision. Planner decides if this needs an ADR or just inline comments. |

## Open questions for the planner

**Q-A (resolved):** **Locking mechanism — `filelock` vs. `fcntl`.** No third-party `filelock` / `portalocker` is currently in `pyproject.toml`. Adding a dependency for this single use case is overkill. **Decision: use stdlib `fcntl.flock(fd, LOCK_EX | LOCK_NB)`** — works on macOS / Linux (the codebase's actual deployment surface per `CLAUDE.md`); Windows fallback is a no-op lock with a stderr warning (acceptable — Windows is not a supported runtime). If the planner discovers a use case in another item that needs cross-platform file locking, they may revisit and add `filelock` then.

**Q-B (resolved):** **`fetch_cn_etf_holdings` call-site count — only 1 production usage + 5 test sites.** Confirmed via grep: production call site is currently NONE (the function exists but isn't called anywhere outside tests). Item 003 introduces the first real call from `_build_active_fund_snapshot`. The 5 test sites must be updated to assert `HoldingsResult`. **No additional planner work needed** — the contract change is invasive but cheap.

**Q-C (resolved):** **`股票市场` column presence in existing fixture.** Confirmed missing — current fixture columns are `["序号","股票代码","股票名称","占净值比例","持股数","持仓市值","季度"]`. The ticker-prefix fallback (Strategy 2) is the dominant path. Both column-present and column-absent fixtures must be tested.

**Q-D (resolved):** **Legacy `_TARGET_REGISTRY` interaction.** For `kind in {"broad_index", "sector_theme", "qdii_us", "qdii_hk", "bond", "gold", "qdii_global"}`, dispatch to the existing legacy path via `target.display_cn`. **Legacy build path is preserved untouched** — item 005 (Slice F) later layers fund-level NAV adapters on top, but item 003 must not modify the existing CN-index / US-symbols / HK-symbols / HK-index builders.

**Q-E (resolved):** **`one_line_view` format.** Locked above in §"one_line_view format". Template `{filing_fragment} · {broker_fragment} · {news_fragment}` with deterministic empty-fallback `"证据获取失败"`.

**Q-F (resolved):** **`failure_reasons` canonical enumeration.** Locked above in §"Failure reason codes".

**Q-G (resolved):** **Budget calculation timing.** Computed at `_build_rows` entry, BEFORE the per-instrument loop. Abort raises `FetchBudgetExceeded` (exit code 3) — no `.tmp` artifacts ever created.

**Q-H (resolved):** **HK news fallback — stub-empty only, NO scraper in V1.** Implementation: at module load time inside `_ak_call`'s lazy-import wrapper, detect `hasattr(ak, "stock_hk_news_em")`. On import-error or AttributeError, `fetch_hk_stock_news` returns `()` and the caller stamps `"hk_news_unsupported_adapter:{stock}"` into the constituent's `failure_reasons` (NEW reason code — add to §"Failure reason codes" table). The HK info-leg empty case is handled downstream by item 006 (H2) Policy B's weight-aware quorum. A scraper-based fallback is rejected for V1: HKEX HTML changes break scrapers silently and the maintenance burden compounds against item 008's regression budget. Re-evaluate in V2 only if `stock_hk_news_em` proves unreliable in production traces.

**Q-I (resolved):** **`ThesisCard.constituent_analyses` field order — safe via existing keyword-only construction.** Verified: `src/irc/opportunity/cards.py:41-63` constructs `ThesisCard` with all keyword arguments. Adding `constituent_analyses` as the trailing default-`()` field in the dataclass requires only adding `constituent_analyses=row.constituent_analyses,` to the `build_thesis_card` return expression. No positional-arg call sites elsewhere.

**Q-J (resolved):** **`OpportunityRow.thesis_evidence` flattening order.** Locked: when `derive_thesis_from_evidence` flattens per-constituent evidence into the row's top-level `thesis_evidence`, order by `(weight_pct desc, type_rank asc, citation_id asc)` where `type_rank: filing=0, broker=1, news=2`. Filings sort first within a holding (matches the data/info-leg priority the citation selector imposes downstream). Note: `select_citations` already picks deterministically via `_slot_key` regardless of input order (item 002 ADR 0001 §3 invariant); this flatten order is only for renderer determinism (memo D1 evidence_pool reads the tuple sequentially). Locks into a test in `test_thesis_evidence.py` named `test_active_fund_thesis_evidence_flatten_ordering`.
