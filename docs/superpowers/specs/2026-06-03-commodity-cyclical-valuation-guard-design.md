# Commodity-Cyclical Valuation Guard + Sector PE Accumulate — Design

**Date:** 2026-06-03
**Status:** Approved (brainstorm) → revised after spec review → pending implementation plan
**Author:** pairing session (narrative metals valuation review)
**Follows:** [`2026-06-03-fundamental-valuation-grounding-design.md`](2026-06-03-fundamental-valuation-grounding-design.md) (#102, Phase 1) and [ADR 0012](../../adr/0012-fundamental-led-equity-valuation.md).

## Context

`irc narrative compute_metals --analyze` reports nearly every resource/metals fund as
`very_expensive`. Investigation found:

1. **Narrative already runs the identical valuation rule as the opportunity stage.** Both go
   `narrative/analyze.py:_build_input` → `opportunity/inputs_build.py:_build_input` →
   `inputs_loader.populate_inputs` → `states.build_opportunity_row` → `classify_valuation`.
   There is **no separate narrative classifier** to "align".

2. **The `very_expensive` verdict is a NAV price-momentum artifact, not a valuation.** For equity
   vehicles `classify_valuation` (`states.py:229`) uses the fundamental index PE-TTM percentile
   (`valuation_percentile_fundamental`) when present, otherwise **falls back to the NAV
   self-history percentile**. The metals funds fall back to NAV because they have **no PE-grounded
   index** wired.

3. **The data wall.** The long PE history csi300/csi1000 rely on comes from **legulegu**
   (`stock_index_pe_lg/pb_lg`), which serves **broad indices only**. Probed sources:

   | Source | Sector indices? | History | PE | PB | Speed |
   |---|---|---|---|---|---|
   | legulegu `stock_index_pe_lg/pb_lg` | ❌ broad only | ✅ years, daily | ✅ | ✅ | fast (anti-bot CSRF; intermittently flaky) |
   | csindex `stock_zh_index_value_csindex` | ✅ CSI sectors (中证有色 `930708`…) | ❌ ~20 trailing days | ✅ (市盈率1/市盈率2) | ❌ none | fast (plain `.xls`, no CSRF) |
   | Shenwan `index_analysis_daily_sw` | ✅ 申万 industries | ✅ (range) | ? | ? | ❌ ~70 min/backfill — unusable |

   No fast, free source of long sector-index PE *history*. csindex gives only *current* PE.

4. **Domain caveat.** For deep-cyclical sectors (nonferrous / 资源), PE percentile is a weak
   anchor (peak earnings depress PE at tops); NAV percentile is worse — pure momentum. The
   codebase already encodes this: bonds use a yield-curve anchor (`classify_bond_valuation`).

**Decision (user):** Hybrid — (A) a classifier **guard** now that stops NAV momentum producing a
valuation verdict for commodity-cyclical funds, and (B) **accumulate-forward** sector PE via
csindex so PE grounding switches on automatically once enough history accrues.

### Latent issue this review surfaced (P2-1)

The universe stores `tracked_index` as **display names** ("沪深300", "中证1000", …;
`cn_funds.yaml:5`, generator `discovery/cn_fund_universe.py:108` emits names like "S&P 500"), but
the valuation lookup `_index_valuation_metrics` (`inputs_loader.py:148`) lowercases the value and
tests membership in `_BROAD_INDEX_KEYS` — a set of **English slugs** (`csi300`…; `lookthrough.py:61`).
"沪深300" ≠ "csi300", so **no real fund's `tracked_index` ever resolves to a slug**. The #102
broad-index grounding is therefore **dormant in production today** (it only fires in unit tests that
pass slug values directly). Any sector mapping we add is equally unreachable unless we close this
gap. This spec adds a normalization layer (§2.1) and **scopes it to sector keys** — broad-index
re-activation is called out as a separate opt-in (Open items).

## Core invariant (must survive future edits)

> **Commodity-cyclical NAV-anchor exclusion.** For a commodity-cyclical theme, when **no
> fundamental anchor exists** (`valuation_percentile_fundamental is None`), the NAV self-history
> percentile is **not** a valuation anchor. The classifier withholds **every** directional verdict
> — `cheap` *and* `expensive`/`very_expensive` alike — and returns `evidence_insufficient`.

The exclusion is **symmetric on purpose**: a metals fund reading `cheap` off a post-crash NAV
trough is exactly as much a momentum artifact as one reading `very_expensive` at the peak — both
are "price relative to its own past", neither is valuation. A future change narrowing the guard to
"reject only the expensive end" re-admits the same momentum-as-valuation error on the cheap side
and is a **regression**, not a refinement. Locked by a test (§4) and recorded in `CONTEXT.md`.

## Design

### 1. Classifier guard (immediate)

In `classify_valuation` (`states.py`), equity branch, **only when**
`valuation_percentile_fundamental is None` (NAV fallback) **and** `inp.theme ∈
COMMODITY_CYCLICAL_THEMES`: return `("evidence_insufficient", <reason>)` **before** any band
assignment — withholding the verdict regardless of band (per the invariant).

```python
# NAV self-history percentile is price momentum, not valuation, for these themes.
# When no fundamental anchor exists the verdict is withheld SYMMETRICALLY — see
# CONTEXT.md "Commodity-cyclical NAV-anchor exclusion". Extensible without touching call sites.
COMMODITY_CYCLICAL_THEMES: frozenset[str] = frozenset({"metals"})
```

`inp.theme` is already populated on `OpportunityInput` (`inputs_build.py:47`). Reason (zh): NAV
价格百分位是动量而非估值；该周期性主题无基本面锚（PE 历史），方向性估值判断暂缺。

- **State reuse:** `evidence_insufficient` is an existing `ValuationState` — no new state.
- A metals fund that *later* gains a PE anchor (`fund_pct is not None`) skips the guard and uses
  the existing PE rule.

**Scope (corrected — P1-1, your note 2).** The guard is bound to `theme == "metals"`, **not** the
`compute_metals` narrative shortlist. `_EQUITY_ASSET_CLASSES` (`states.py:142`) includes
`qdii_global`, so the guard intentionally covers **all 21 metals-themed rows** in the current
merged universe: **20 `cn_equity_fund` + 1 `qdii_global`** (378546 摩根全球天然资源混合(QDII)A).
This breadth is intended and is locked by a `qdii_global`-metals test (§4). Non-metals equity funds
are untouched (no regression).

### 2. Make the PE anchor reachable + accumulate-forward (csindex)

#### 2.1 Slug resolution (P2-1 — mandatory)

Add a **normalization layer** so a display-name `tracked_index` resolves to a canonical slug:

- New `_SECTOR_INDEX_DISPLAY: dict[str, str]` (slug → 中文 name) and its inversion
  `_INDEX_NAME_TO_SLUG` (中文/lowercased → slug), **populated with sector indices only** for this
  PR (e.g. `csi_nonferrous → 中证有色金属`, `csi_resource → 中证资源`, …).
- `_index_valuation_metrics` resolves its key as: `slug = _INDEX_NAME_TO_SLUG.get(norm) or norm`
  (so an already-slug value still works), then tests membership in the **new** valuation key set
  (§2.2). Broad display names are **not** added to `_INDEX_NAME_TO_SLUG` here, so broad-fund
  behavior is unchanged (broad re-activation = separate opt-in, Open items).
- **Generator** `discovery/cn_fund_universe.py:_tracked_index_for`: add a sector branch that emits
  the 中文 index name for recognised **index** funds (keyword match on fund name, e.g. 有色/资源/
  矿业 → the matching sector display name). **Active** resource funds (no single index) emit
  `None` and stay guarded. This survives the monthly `irc universe build-cn-funds` regen (no
  hand-edits to the generated YAML that would be wiped).

#### 2.2 Valuation key set (P0-1)

Introduce a dedicated set rather than overloading "broad":

```python
_SECTOR_INDEX_KEYS: frozenset[str] = frozenset(_SECTOR_INDEX_DISPLAY.keys())
_INDEX_VALUATION_KEYS: frozenset[str] = _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
```

`_index_valuation_metrics` tests `slug in _INDEX_VALUATION_KEYS` (was `_BROAD_INDEX_KEYS`). This is
what lets accumulated sector rows actually become a PE anchor.

#### 2.3 csindex fetcher + ingest (P1-2 — canonical PE column)

- `_SECTOR_INDEX_CODE: dict[str, str]` — sector slug → CSI index code (e.g.
  `csi_nonferrous → "930708"`), verified live during implementation.
- `fetch_cn_sector_index_valuation_history(index_key)` in `akshare_index_valuation.py`: maps slug →
  CSI code, calls `stock_zh_index_value_csindex(symbol=code)`, returns an `IndexValuationHistory`
  with `pb=None`. **Canonical PE column = `市盈率1` (PE-TTM/trailing), not `市盈率2` (静态/LYR).**
  Rationale: CSI publishes 市盈率1 = total mkt-cap ÷ **TTM** attributable net profit; across the
  cyclical indices probed (有色 26.97/29.28, 能源 17.09/20.04, 钢铁 24.64/25.78) 市盈率1 ≤ 市盈率2,
  consistent with TTM PE sitting below static in an earnings upcycle. The legulegu column set
  (`_PE_COLS`) does **not** contain `市盈率1/市盈率2`, so this fetcher uses a **dedicated**
  csindex column constant (`_CSINDEX_PE_TTM_COL = "市盈率1"`) — it must **not** reuse
  `_series_map(..., _PE_COLS)`. Degrade-to-`None` contract preserved; `基金概况` never used.
- `ingest_cmd` calls `ingest_index_valuation_history` a **second time** with `_SECTOR_INDEX_KEYS`
  + this fetcher (ingestor already accepts a `fetch` param). `INSERT OR REPLACE` on
  `(index_key, date)` dedups overlapping weekly windows; the series grows over time. Both legs are
  best-effort/non-fatal (mirrors `ingest_cmd.py:569`).

Mapping wired by the generator (§2.1) for **CSI-index** metals funds only. **Not** mapped (stay
guarded): the 国证/CNI fund 160221 (csindex doesn't cover CNI); the **actively-managed** resource
funds (no single index — no proxy index assigned); the `qdii_global` fund 378546.

### 3. Min-history gate (P2-2 — prevents false precision)

In `_index_valuation_metrics`, return a non-`None` PE percentile **only** when the PE series is
mature, defined over **non-null PE observations** (matching `self_history_percentile`'s `_clean`):

- `n_valid = count of non-null pe_ttm in the series` (NOT raw row count — csindex rows carry
  `pb=None` but `pe_ttm` present; the count is on PE).
- Gate: `n_valid ≥ MIN_PE_POINTS (=120)` **and** span `≥ MIN_PE_DAYS (=180)`. Below → PE percentile
  `None` → classifier falls back → guard catches it. (`self_history_percentile` already requires
  ≥30 valid points; this is a stricter, explicit floor for thin accumulating series.)
- **Preserve the no-stale invariant:** keep the existing `if pe is not None` guard at
  `inputs_loader.py:160` (latest PE null ⇒ no percentile). csi300/csi1000 (thousands of points)
  are unaffected.

### 4. Downstream safety (P0-2) + testing

**Narrative risk handling (non-blocking — your note 1).** Do **not** add a structural evidence gap
or advisory-gap for the withheld valuation (so H3 publishability — `opportunity_cmd.py:1179`,
`publishable_rows = [r for r in kept_rows if not r.evidence_gaps]` — is unaffected and the row
publishes). Instead, `narrative/risk.py:_state_drivers` must **explicitly surface** a withheld
valuation: when `view.valuation_state == "evidence_insufficient"`, append a driver
`("valuation_state", "valuation withheld — no fundamental anchor", w)` so it appears in the risk
rationale/drivers rather than being silently dropped. Weight `w` is a tuning decision for the plan
(default 1 = mild caveat; not forced to `insufficient`).

**TDD** (red→green→refactor); unit tests, no live calls (live AkShare double-gated):

- `tests/opportunity/test_states.py` — **the invariant lock**: a `theme: metals` input with
  `valuation_percentile_fundamental=None` returns `evidence_insufficient` for **both** a low NAV
  percentile (would-be `cheap`) **and** a high NAV percentile (would-be `very_expensive`); a
  `qdii_global` + `theme: metals` input is guarded too (cross-asset-class lock); a metals input
  *with* a PE anchor uses the PE rule; a non-metals equity input keeps NAV banding (no regression).
- `tests/opportunity/test_inputs_loader.py` — (a) slug normalization: a sector **display-name**
  `tracked_index` resolves and (with mature rows) yields a PE percentile; (b) min-history gate:
  thin series → `None`, mature → percentile, latest-null → `None`; (c) csi300-scale unaffected.
- `tests/fundamentals/test_akshare_index_valuation.py` — sector fetcher reads **`市盈率1`**:
  a csindex-shaped frame (cols `市盈率1/市盈率2/股息率1/股息率2`) → PE from `市盈率1`, `pb=None`; a
  test that **fails if only legulegu PE names are recognised**; unknown key / failure → `None`.
- `tests/commands/test_ingest_index_valuation_wiring.py` — second ingest leg invoked with
  `_SECTOR_INDEX_KEYS` + sector fetcher; non-fatal on failure.
- `tests/narrative/test_risk.py` — `evidence_insufficient` valuation surfaces a driver (not silently benign).
- `CONTEXT.md` — add the "Commodity-cyclical NAV-anchor exclusion" invariant.

**Out of scope:** PB grounding (csindex has none); 国证/CNI indices; proxy-indexing active funds;
broad-index #102 re-activation (Open items); the opportunity-stage `FetchBudgetExceeded` halt
(separate issue #1). **Caveat carried forward:** once PE grounding switches on, PE percentile
remains a weak cyclical anchor; the existing earnings-yield/real-yield note annotates the reason.

## File-level change list

| File | Change |
|---|---|
| `src/irc/opportunity/states.py` | `COMMODITY_CYCLICAL_THEMES`; guard in `classify_valuation` equity branch |
| `src/irc/opportunity/lookthrough.py` | `_SECTOR_INDEX_DISPLAY`, `_INDEX_NAME_TO_SLUG`, `_SECTOR_INDEX_KEYS`, `_INDEX_VALUATION_KEYS` |
| `src/irc/opportunity/inputs_loader.py` | slug normalization + `_INDEX_VALUATION_KEYS` membership; min-history gate over non-null PE; keep latest-null guard |
| `src/irc/fundamentals/akshare_index_valuation.py` | `_SECTOR_INDEX_CODE`, `_CSINDEX_PE_TTM_COL = "市盈率1"`, `fetch_cn_sector_index_valuation_history` |
| `src/irc/commands/ingest_cmd.py` | second `ingest_index_valuation_history` call with sector keys + sector fetcher |
| `src/irc/discovery/cn_fund_universe.py` | `_tracked_index_for` sector branch (emit 中文 index name for recognised index funds; active → None) |
| `src/irc/narrative/risk.py` | `_state_drivers` surfaces `evidence_insufficient` valuation (non-blocking) |
| `CONTEXT.md` | invariant entry |
| `tests/...` | as listed in §4 |

## Open items to verify / decide during implementation

- **CSI codes + slugs** for: 165520 (中证800有色), 161217 (中证资源), 690008 (中证内地资源主题),
  018132 (中证有色金属矿业主题) — confirm each returns PE via `stock_zh_index_value_csindex`,
  pick canonical slug + 中文 display strings, and confirm `市盈率1` is TTM by cross-checking an
  overlapping index against an independent TTM source (test asserts within tolerance).
- **Broad-index re-activation (decision):** adding broad display names to `_INDEX_NAME_TO_SLUG`
  would also fix the dormant #102 grounding (broad funds NAV→PE). Default = **out of scope**
  (sector-only) to keep this PR's blast radius on commodity funds; flagged for the user.
- Final gate constants (`MIN_PE_POINTS=120`, `MIN_PE_DAYS=180`) and the risk-driver weight `w`.
