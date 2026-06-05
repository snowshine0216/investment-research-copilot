# Phase A — Broad-index valuation grounding (NAV → PE-TTM)

**Date:** 2026-06-05
**Status:** Design approved (with live-review revisions); ready for implementation plan.
**ROADMAP item:** [`docs/ROADMAP.md`](../../ROADMAP.md) Phase A.
**Builds on:** ADR 0012 (fundamental-led equity valuation), valuation-grounding item 001 (the index PE/PB
fetch + `index_valuation_history` table + the `valuation_percentile_fundamental` slot already exist).

## 1. Goal

Move the **18 curated broad-index ETFs** (+ legit generated index funds) off the NAV self-history
percentile (price momentum) and onto the **legulegu PE-TTM historical percentile**, by populating the
already-wired `valuation_percentile_fundamental` slot. No new stage, table, or fetcher — Phase A fixes
breakages on a path that is already plumbed end to end:

```
fund.tracked_index ("沪深300")
  → _INDEX_NAME_TO_SLUG        [BREAK 1: broad display names not inverted] → slug "csi300"
  → index_valuation_history WHERE index_key="csi300"
        ← ingest leg fetches via _LEGULEGU_INDEX_SYMBOL
          [BREAK 2: PE column = 静态市盈率, not 滚动市盈率 — ADR 0012 violation]
          [BREAK 3: 7/9 symbol strings unconfirmed / unsupported by legulegu]
  → self_history_percentile (legulegu multi-year history clears the 120pt/180d maturity gate at once)
  → valuation_percentile_fundamental → classify_valuation
```

The price/fundamental **divergence advisory auto-activates** for grounded funds (both percentiles present);
no code change — it just starts firing on real output.

## 2. Decisions of record

| # | Decision | Rationale |
|---|---|---|
| D1 | **PE leg reads `滚动市盈率` (rolling/TTM) ONLY; return `None` if absent — never fall back to `静态市盈率`.** | Live gate proved the current code returns static PE (csi300: static 14.02 vs rolling 13.80). ADR 0012 requires PE-TTM. |
| D2 | **Production symbol map = a verified-exact allowlist of `{csi300, csi500, csi1000, sse50}` only.** Speculative symbols live in a separate, clearly-marked probe map. | Gate #4 requires every newly activated symbol to be live-confirmed. The live sweep confirmed exactly these four; the rest returned `None`. |
| D3 | **`标普红利低波50` stays on NAV (unmapped).** | Distinct S&P-licensed index, not an alias for 中证红利低波; no legulegu coverage. *Approved in review.* |
| D4 | **`chinext` and `chinext50` are DISTINCT exact slugs — never combined.** `创业板指 → chinext` (symbol `创业板指`), `创业板50 → chinext50` (symbol `创业板50`). Both speculative until live-confirmed. | The original `创业板50 → chinext` proxy was reversed and would silently combine two indices. Distinct exact mappings remove the proxy entirely — so **no ADR 0012 addendum is required**. |
| D5 | **`161721` (招商沪深300地产等权重) gets a seed override stripping its `沪深300` tag.** | Real-estate equal-weight sector slice the generator greedily mis-tagged; `csi300` is in the production allowlist, so without the override it would mis-ground on broad 沪深300 PE. Seed wins by id. |
| D6 | **`003318` (景顺长城中证500行业中性低波动, csindex 930782) gets a seed override stripping its `中证500` tag → NAV/Phase D.** | Distinct smart-beta index, not ordinary 中证500; `csi500` is in the allowlist so it would otherwise mis-ground. Its Phase D look-through coverage is 0.12 (< 0.50 floor) → correctly stays NAV. The exact 930782 csindex path is a Phase B follow-up. |
| D7 | **Honest coverage target = ~9 funds, measured (not ~20).** | After D5/D6 overrides, only the four confirmed symbols ground: csi300×4, csi500×2, csi1000×2, sse50×1. |
| D8 | **Broad ingest leg does a per-key full *replace*; the shared sector leg keeps *append*.** | The ingestor is shared. Broad legulegu returns full history → replace purges the stale static-PE rows (self-migrating) and trimmed-history orphans. Sector csindex is accumulate-forward → must keep appending. A non-empty fetch is required before delete, so transient provider failures never wipe good cache. |

## 3. Design

### 3.1 PE-TTM correctness + dedicated columns (`fundamentals/akshare_index_valuation.py`)

- Add `_LEGULEGU_PE_TTM_COL = "滚动市盈率"` and `_LEGULEGU_PB_COL = "市净率"` (cap-weighted; *not* the
  `等权市净率` equal-weight variant).
- Remove `_PE_COLS` / `_PB_COLS` (they front-load static / ambiguous columns — the footgun). Drive the
  broad PE/PB legs through the existing generic helpers with a **single-candidate** tuple, so an absent
  column yields `None` with no fallback:
  - `fetch_cn_index_valuation_history`: `_series_map(pe_df, (_LEGULEGU_PE_TTM_COL,))`,
    `_series_map(pb_df, (_LEGULEGU_PB_COL,))`.
  - `fetch_cn_index_valuation`: `_extract_latest_value(pe_df, (_LEGULEGU_PE_TTM_COL,))`, etc.
- `_DIV_COLS` / dividend behaviour unchanged (`None` in practice).

### 3.2 Production allowlist vs speculative probe (`fundamentals/akshare_index_valuation.py`)

- `_LEGULEGU_INDEX_SYMBOL: dict[str, str]` — **production allowlist, live-confirmed exact symbols only:**
  ```
  csi300 → "沪深300"   csi500 → "中证500"   csi1000 → "中证1000"   sse50 → "上证50"
  ```
- `_SPECULATIVE_LEGULEGU_SYMBOL: dict[str, str]` — clearly marked, **NOT** consulted by production
  fetch/ingest; only the live sweep probes it:
  ```
  star50 → "科创50"   chinext → "创业板指"   chinext50 → "创业板50"
  csi_dividend → "中证红利"   csi_dividend_lc → "中证红利低波"   csi_a500 → "中证A500"
  ```
- `fetch_cn_index_valuation*` resolve the symbol from `_LEGULEGU_INDEX_SYMBOL` **only**. This replaces
  `_INDEX_PE_PB_NAME = dict(_BROAD_INDEX_DISPLAY)` — the display/symbol coupling is removed.
- **Graduation:** when a speculative symbol lands live, move it into `_LEGULEGU_INDEX_SYMBOL` and add it
  to the hard-assert set (a follow-up PR), expanding coverage incrementally.

### 3.3 Cache migration via per-key replace (`data/index_valuation_ingestor.py`)

- Add a parameter `replace_keys: bool = False`.
  - `replace_keys=True` **and** the key's fetch returns a non-empty history →
    `DELETE FROM index_valuation_history WHERE index_key = ?` then insert the fresh full series.
  - Fetch returns `None`/empty → leave existing rows untouched (no wipe on transient failure).
- `ingest_cmd.py`: broad leg iterates `tuple(sorted(_LEGULEGU_INDEX_SYMBOL))` with `replace_keys=True`
  (replaces today's `_BROAD_INDEX_KEYS` iteration — only confirmed symbols are fetched). Sector leg
  unchanged (`replace_keys=False`, accumulate-forward preserved).
- Net effect: the first post-merge broad ingest purges the static-PE rows and writes rolling-PE rows — no
  standalone migration script.

### 3.4 Slug map + new `chinext50` slug (`opportunity/lookthrough.py`)

- Extend `_INDEX_NAME_TO_SLUG` (display, lowercased → slug). Inverting non-production slugs is harmless:
  the table is empty for them → `_index_valuation_metrics` returns `None` → NAV. It also future-proofs
  graduation.
  ```
  沪深300→csi300   中证500→csi500   中证1000→csi1000   中证a500→csi_a500   上证50→sse50
  科创50→star50    创业板指→chinext  创业板50→chinext50  中证红利→csi_dividend  中证红利低波→csi_dividend_lc
  ```
  `标普红利低波50` is intentionally absent (D3).
- Add `chinext50` as a new slug: `_BROAD_INDEX_DISPLAY["chinext50"] = "创业板50"` and set
  `_BROAD_INDEX_DISPLAY["chinext"] = "创业板指"` (display-only now). `_BROAD_INDEX_KEYS` /
  `_INDEX_VALUATION_KEYS` pick `chinext50` up automatically.

### 3.5 Universe overrides (`config/universe/cn_funds.yaml`)

- Add seed entries (seed overrides generated by `instrument_id`) for **`161721`** and **`003318`**, each
  **without `tracked_index`**, so they route to their honest NAV/Phase D path instead of mis-grounding on
  a broad allowlist symbol. `023153` (pure 中证A500) needs no override — `csi_a500` is not in the
  production allowlist, so it stays NAV and maps correctly for future graduation.

## 4. Test plan (TDD — gate #1)

| Test file | Asserts |
|---|---|
| `tests/fundamentals/test_akshare_index_valuation.py` | Rolling-PE extraction on a **real legulegu frame shape** (cols incl. `日期`, `静态市盈率`, `滚动市盈率`, `等权…`) picks `滚动市盈率`, never `静态市盈率`; returns `None` when `滚动市盈率` absent; PB picks `市净率` not `等权市净率`; production fetch resolves only `_LEGULEGU_INDEX_SYMBOL`; speculative slugs are unreachable via production fetch. |
| `tests/data/test_index_valuation_ingestor.py` | `replace_keys=True` deletes prior rows for a key on non-empty fetch; preserves rows on `None` fetch; default (`False`, sector) keeps accumulating across calls. |
| `tests/opportunity/test_lookthrough.py` | Each broad display name inverts to its slug; `创业板50→chinext50` and `创业板指→chinext` are distinct; `标普红利低波50` is unmapped; `chinext50` ∈ `_BROAD_INDEX_KEYS`. |
| `tests/opportunity/test_inputs_loader.py` | A display-name `tracked_index` resolves + reads cached rows → non-`None` `pe_pct`; `tracked_index="标普红利低波50"` → `None`; a non-production slug (e.g. `star50`) with empty table → `None`. |
| universe-load test | `161721` + `003318` resolve to `tracked_index=None` (seed override wins). |
| `tests/fundamentals/test_index_valuation_live.py` (gated) | **Hard-assert every production symbol** (csi300/csi500/csi1000/sse50) returns numeric rolling PE **and** PB. Separate **informational** sweep over `_SPECULATIVE_LEGULEGU_SYMBOL` prints a landing table (no fail). |

## 5. Exit gates (ROADMAP §4)

1. **Tests green** — ruff + full `uv run pytest`; new behaviour TDD-first (table above).
2. **Invariants intact** — re-run H3 universal gapped-row + SAME-3 citation-set tests. Valuation
   *magnitude* changes; row-presence/citations do not → partition unaffected (verify, don't assume).
3. **Coverage (measured)** — `irc run --from ingest` + `irc opportunity`: count non-`None`
   `valuation_percentile_fundamental` for the broad funds. **Expect ≥ 9** (csi300×4, csi500×2, csi1000×2,
   sse50×1, after D5/D6 overrides). Honest number; lower than the ROADMAP's theoretical +19.
4. **Live confirmation** — production allowlist hard-asserted under `IRC_RUN_LIVE_AKSHARE=1`
   (already passing for the four; re-run after the rolling-PE fix).
5. **Human diff review (hard stop)** — Phase A produces and commits its **own** before/after artifact
   (the existing `irc lookthrough-diff` is active-fund-only). Eyeball: state flips on the 9 grounded
   funds, the newly-firing divergence advisory, and that `161721`/`003318`/`标普红利低波50` stayed on NAV.
6. **Docs synced** — CONTEXT.md "Valuation inputs"; CHANGELOG `[Unreleased]` (no VERSION bump); ROADMAP
   Phase A status. **No ADR 0012 addendum** (no proxy enters the slot; the static→TTM change is a bugfix
   toward ADR 0012's existing PE-TTM requirement). An addendum becomes required only if a disclosed proxy
   is later approved.

## 6. Deliverable: before/after diff artifact

Produce `docs/2026-06-05-phase-a-broad-grounding/` with a before/after table of `valuation_state` +
`valuation_percentile_fundamental` (+ NAV percentile + divergence flag) for the 9 grounded broad funds.
Mechanism (decided in plan): two `irc opportunity` runs (baseline vs Phase A) diffed on the broad subset,
or a small extension of `lookthrough-diff` to include broad-index funds. The artifact is the gate-#5
sign-off evidence.

## 7. Files touched

- `src/irc/fundamentals/akshare_index_valuation.py` — rolling-PE/PB columns; production vs speculative symbol maps; display/symbol decoupling.
- `src/irc/data/index_valuation_ingestor.py` — `replace_keys` per-key full-replace mode.
- `src/irc/commands/ingest_cmd.py` — broad leg iterates the production allowlist with `replace_keys=True`.
- `src/irc/opportunity/lookthrough.py` — broad slug inversion; new `chinext50` slug; `chinext` display → `创业板指`.
- `config/universe/cn_funds.yaml` — `161721` + `003318` seed overrides.
- Tests per §4; docs per gate #6; diff artifact per §6.

## 8. Out of scope (follow-ups)

- Graduating speculative symbols (star50, chinext, chinext50, csi_dividend, csi_dividend_lc, csi_a500) as
  each is live-confirmed.
- The exact csindex `930782` valuation path for `003318` (Phase B territory).
- A disclosed-proxy policy + ADR 0012 addendum, *if* ever desired for `创业板指`/`003318`.
- Phases B (sector) / C (foreign) / 0 (gold + bond-misclass), per the ROADMAP.
