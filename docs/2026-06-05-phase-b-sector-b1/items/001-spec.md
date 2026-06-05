# Phase B — Sector expansion (design spec)

**Status:** Draft for review (2026-06-05)
**Roadmap:** [`docs/ROADMAP.md`](../../ROADMAP.md) §Phase B.
**Builds on:** [ADR 0012 — fundamental-led equity valuation](../../adr/0012-fundamental-led-equity-valuation.md) (the `valuation_percentile_fundamental` seam, `self_history_percentile`, the 120/180 maturity gate, the divergence advisory), the index-valuation seam (item 001), and **Phase D's shadow-then-flip rollout pattern** ([`2026-06-04-phase-d-active-lookthrough-design.md`](2026-06-04-phase-d-active-lookthrough-design.md) §3.8) — Phase B reuses Phase D's *separate-accumulation-from-activation* discipline and its `lookthrough_cfg` config threading.
**Goal:** Populate `valuation_percentile_fundamental` (PE-TTM only) for the curated CN sector ETFs by wiring their tracked CSI indices into the already-proven csindex valuation seam — **gated so the valuation-basis change is reviewed by a human (gate #5) before it reaches any recommendation**, not after.

---

## 1. What it does (one sentence)

For each curated CN sector ETF, resolve its `tracked_index` to a CSI index code, **accumulate** that index's PE-TTM history into the existing `index_valuation_history` table, and — **only for sector slugs explicitly placed on a reviewed allowlist** — let the existing `_index_valuation_metrics` → `self_history_percentile` → `valuation_percentile_fundamental` path ground the fund's valuation off PE instead of NAV momentum.

## 2. Why this shape (and why two PRs)

The index-valuation seam already proves the mechanism end-to-end for the 3 existing metals codes: `fetch (csindex 市盈率1) → ingest to index_valuation_history → inputs_loader reads cached → 120/180 maturity gate → self_history_percentile → valuation_percentile_fundamental → classify_valuation`. Phase B adds **no new pipeline modules** — it is a **data/config expansion** of that seam (one source-of-truth catalog module + config-gated activation + tests).

Two hard facts force a **two-PR shape**, mirroring Phase D:

1. **csindex serves only a ~20-trading-day trailing window per call** (verified live 2026-06-05: every code — existing and new — returns exactly 20 rows, 2026-05-08→06-04). There is **no full-history backfill** via `stock_zh_index_value_csindex`. So a newly-wired index **accumulates forward** and takes ~6 months to clear the `MIN_PE_POINTS=120` ∧ `MIN_PE_DAYS=180` gate. (`index_csindex_all` is catalog-only; `stock_zh_index_hist_csindex` is price, not valuation. No valuation-history endpoint exists.)
2. **The maturity gate auto-activates grounding.** Once a series crosses 120/180, `_index_valuation_metrics` emits the PE percentile and `classify_valuation` (`states.py:264`) immediately prefers it over NAV — silently, months after merge. **An empty merge-time diff therefore does NOT satisfy gate #5** (roadmap line 146: human review *before* a valuation-basis change reaches recommendations). Accumulation must be separated from activation.

> **B1 — data onboarding (activation OFF).** Wire the catalog; history accumulates; **no sector slug grounds anything** (allowlist empty) → output byte-identical *through* maturation. B1 explicitly **does not pass gate #3** (grounded count = 0 by design).
>
> **B2 — activation (after gate #5).** Once series mature, produce the **real** NAV-vs-PE recommendation diff, obtain human sign-off (gate #5), then add the reviewed slugs to the allowlist. **B2 passes gate #3** (grounded count measured > 0).

## 3. Decisions (locked)

### 3.1 Source & coverage — csindex PE-TTM only, accumulate-forward
- Source: AkShare `stock_zh_index_value_csindex(symbol=<code>)`, column `市盈率1` (= total mkt-cap ÷ TTM attributable net profit; PE-TTM/trailing). **PE only — csindex carries no PB** (verified: sector PB column absent). Sector `valuation_percentile_fundamental_pb` stays `None`. This is an **intentional, documented gap**: PB is corroborate-only (ADR 0012 §5), and adding a sector PB source is a separate source spike (out of scope, §10). Resolves roadmap §7 decision 2 for the sector path: **accept PE-only**.
- Degrade-to-None: unknown slug / adapter failure / no usable PE rows → `None` (existing `fetch_cn_sector_index_valuation_history` contract; unchanged).
- The maturity gate (`120/180`) and `self_history_percentile` (`<30 → None`) are **unchanged** — Phase B introduces no new gate logic.

### 3.2 Separate accumulation from activation (the P0 fix)
- **Accumulation (ingest)** runs for **all** sector slugs (the ingest leg already iterates `_SECTOR_INDEX_KEYS`; new slugs are picked up automatically — no ingest code change).
- **Activation (read → slot)** is gated by a new config allowlist `sector_index_grounding.activated_slugs` (`config/valuation_buckets.yaml`, schema `ValuationBucketsConfig`):
  ```yaml
  sector_index_grounding:
    activated_slugs: []   # B1: empty (accumulate only). B2: reviewed mature slugs.
  ```
- In `_index_valuation_metrics`: **if the resolved slug is a sector slug (`slug in SECTOR_INDEX_KEYS`) and not in `activated_slugs`, short-circuit to the all-`None` tuple** `(None, None, None, None, None)` — i.e. behave exactly as the pre-Phase-B "slug not resolvable" path. This withholds **both** the raw `pe_ttm/pb/dividend_yield` **and** the percentile, guaranteeing byte-identical output (not merely a withheld percentile — the raw metrics also feed `OpportunityInput`).
- **Broad-index slugs are unaffected** (Phase A's concern); only sector slugs pass through the allowlist. The existing 3 metals slugs are now **also** governed by the allowlist — this is a deliberate correctness fix: without it, `csi_nonferrous`/`csi_resource` would auto-activate (unreviewed) when they mature (~Nov 2026, having started 2026-05-08).

### 3.3 Config threading — explicit, no global reads (per Phase D review P1)
Phase D already threads `bundle.valuation_buckets.active_fund_lookthrough` down `run_opportunity → _build_rows → _build_input → populate_inputs(..., lookthrough_cfg=...)`. Phase B threads the sector allowlist down the **same** chain:
1. `run_opportunity` passes `bundle.valuation_buckets.sector_index_grounding.activated_slugs` (a `frozenset[str]`) alongside the existing lookthrough cfg.
2. `_build_rows → _build_input → populate_inputs` forward it.
3. `populate_inputs → _index_valuation_metrics(con, tracked_index, *, activated_sector_slugs)` as a keyword-only param (default `frozenset()` so existing call sites/tests stay valid and default-inert).
A focused test asserts the allowlist reaches `_index_valuation_metrics` (no module-level lookup — FP rule).

### 3.4 Single source-of-truth catalog (the chosen structure)
New module **`src/irc/opportunity/sector_indices.py`** (keeps `lookthrough.py` under its 200-line budget; pure, no I/O):
```python
@dataclass(frozen=True)
class SectorIndex:
    slug: str
    code: str            # csindex symbol for stock_zh_index_value_csindex
    display_cn: str      # canonical universe tracked_index string (resolution key)
    official_cn: str     # 指数全称 from index_csindex_all (identity-guard target)
    aliases: tuple[str, ...] = ()

SECTOR_INDICES: tuple[SectorIndex, ...] = ( ... 17 rows, see §4 ... )

SECTOR_INDEX_CODE    = {r.slug: r.code for r in SECTOR_INDICES}        # consumed by the fetcher
SECTOR_INDEX_DISPLAY = {r.slug: r.display_cn for r in SECTOR_INDICES}
SECTOR_INDEX_KEYS    = frozenset(SECTOR_INDEX_DISPLAY)
SECTOR_NAME_TO_SLUG  = {                                               # name + alias → slug
    **{r.display_cn.strip().lower(): r.slug for r in SECTOR_INDICES},
    **{a.strip().lower(): r.slug for r in SECTOR_INDICES for a in r.aliases},
}
```
- `lookthrough.py` imports the derived maps (replacing its inline 3-entry `_SECTOR_INDEX_DISPLAY` / sector portion of `_INDEX_NAME_TO_SLUG`); composes `_INDEX_VALUATION_KEYS = _BROAD_INDEX_KEYS | SECTOR_INDEX_KEYS` and `_INDEX_NAME_TO_SLUG = {broad…, **SECTOR_NAME_TO_SLUG}`.
- `akshare_index_valuation.py` imports `SECTOR_INDEX_CODE` (it already imports `_BROAD_INDEX_DISPLAY` from `lookthrough` — same dependency direction).
- The existing 3 metals entries are **folded into** `SECTOR_INDICES` (no behavior change — same slugs/codes).

### 3.5 No universe edits in B1 (the byte-identity fix)
Changing a fund's raw `tracked_index` (e.g. `中证机床ZZ` → `中证机床`) alters `map_lookthrough` keys (`lookthrough.py:162`), report/selection grouping, and allocation dedup **before** any valuation alias map is consulted — so it is **not** byte-identical. Therefore:
- **B1 edits no `config/universe/*.yaml` values.** The malformed `中证机床ZZ` is resolved purely via an alias (`"中证机床zz" → csi_machine_tool`) in `SECTOR_INDICES`.
- The universe rename (`中证机床ZZ` → `中证机床`) is a **separate, separately-reviewed change** (its own small PR), out of scope here.

## 4. The committed catalog matrix

Verified live 2026-06-05 (`stock_zh_index_value_csindex` returns `市盈率1`; `指数全称` from `index_csindex_all`). **17 sector slugs** = 14 new + 3 existing metals.

| # | ETF(s) | universe `tracked_index` | slug | CSI code | official `指数全称` | identity |
|---:|---|---|---|---|---|---|
| 1 | 562500 / 159770 / 159551 / 560630 | 中证机器人 | `csi_robotics` | `H30590` | 中证机器人指数 | csindex ✓ |
| 2 | 562360 | 中证智能制造 | `csi_smart_mfg` | `930850` | 中证智能制造主题指数 | csindex ✓ |
| 3 | 159667 | 中证机床ZZ *(alias→中证机床)* | `csi_machine_tool` | `931866` | 中证机床指数 | csindex ✓ |
| 4 | 159995 | 中证芯片产业 | `csi_chip` | `H30007` | 中证芯片产业指数 | csindex ✓ |
| 5 | 512480 | 中证全指半导体 | `csi_semiconductor` | `H30184` | 中证全指半导体产品与设备指数 | csindex ✓ *(locked vs 932139)* |
| 6 | 516350 | 中证半导体材料设备 | `csi_semi_equip` | `931743` | 中证半导体材料设备主题指数 | csindex ✓ |
| 7 | 588200 | 上证科创板芯片 | `sse_star_chip` | `000685` | 上证科创板芯片指数 | ⚠ **SSE — not in `index_csindex_all`** |
| 8 | 515070 | 中证人工智能主题 | `csi_ai_theme` | `930713` | 中证人工智能主题指数 | csindex ✓ |
| 9 | 515980 | 中证人工智能产业 | `csi_ai_industry` | `931071` | 中证人工智能产业指数 | csindex ✓ |
| 10 | 515880 | 中证全指通信设备 | `csi_telecom_equip` | `931160` | 中证全指通信设备指数 | csindex ✓ |
| 11 | 560660 | 中证数字经济主题 | `csi_digital_econ` | `931582` | 中证数字经济主题指数 | csindex ✓ |
| 12 | 516630 | 中证云计算与大数据 | `csi_cloud` | `930851` | 中证云计算与大数据主题指数 | csindex ✓ |
| 13 | 159338 | 中证算力基础设施 | `csi_compute_infra` | `931688` | 中证算力基础设施主题指数 | csindex ✓ |
| 14 | 512960 | 中证国新央企科技引领 *(theme: soe)* | `csi_soe_tech` | `932038` | 中证国新央企科技引领指数 | csindex ✓ |
| 15 | *(metals narrative)* | 中证有色金属 *(alias 中证有色)* | `csi_nonferrous` | `930708` | 中证有色金属指数 | csindex ✓ |
| 16 | *(metals narrative)* | 中证资源 | `csi_resource` | `000819` | 中证申万有色金属指数 | ⚠ **display≠official — confirm** |
| 17 | *(metals narrative)* | 中证有色金属矿业主题 | `csi_nonferrous_mining` | `931892` | 中证有色金属矿业主题指数 | csindex ✓ |

**Two flags requiring human confirmation at gate #4 (block their *activation*, not B1 onboarding):**
- **#7 `sse_star_chip` (000685):** absent from `index_csindex_all`; the value endpoint returns PE but the CSI-catalog identity cross-check cannot validate it. Confirm via the SSE series source (`index_stock_info` / EastMoney) or a recorded manual source before B2 activates it.
- **#16 `csi_resource` (000819):** official name `中证申万有色金属指数` ≠ display `中证资源`. Pre-existing; the identity guard caught it. Confirm whether any curated fund actually tracks this and whether `000819` is the intended index before B2 activates it.

**Count reconciliation (P2 honesty):** the curated universe has **17 sector/thematic ETFs tracking 14 distinct index names**; with the 3 existing metals codes that is **17 sector slugs**. The roadmap's "21 funds / ~18 codes" is an estimate that also counts generated-catalog sector ETFs (which carry *fund-name-as-index* and are **out of scope** — they never resolve) and the metals ETFs. The committed figure here (17 slugs / 14 new) is the honest curated scope.

## 5. Architecture

| Layer | Existing | Phase B change |
|---|---|---|
| Catalog (SoT) | inline 3-entry dicts across 2 files | **new `opportunity/sector_indices.py`** — `SECTOR_INDICES` table + derived maps |
| Fetch | `fundamentals/akshare_index_valuation.py` (`fetch_cn_sector_index_valuation_history`) | import `SECTOR_INDEX_CODE` from SoT (drop inline `_SECTOR_INDEX_CODE`) |
| Ingest | `data/index_valuation_ingestor.py` + `ingest_cmd.py` sector leg | **none** (auto-iterates `_SECTOR_INDEX_KEYS`) |
| Table | `index_valuation_history` | **none** |
| Read → slot | `inputs_loader._index_valuation_metrics` | **add `activated_sector_slugs` gate** (§3.2/§3.3) |
| Config | `ValuationBucketsConfig` (has `active_fund_lookthrough`) | **add `sector_index_grounding.activated_slugs`** |

Effects stay at the edges (the fetcher + ingest + DuckDB). `sector_indices.py` is pure. Every new/edited file < 200 lines, functions < 20.

## 6. Data flow

```
irc run (ingest leg)                         # accumulation — ALWAYS on
  ingest_index_valuation_history(con, sorted(_SECTOR_INDEX_KEYS),
                                 fetch=fetch_cn_sector_index_valuation_history)
    -> for each slug: csindex 市盈率1 (trailing ~20d) -> upsert index_valuation_history

irc opportunity (read — cached only, R3)     # activation — allowlist-gated
  populate_inputs(..., activated_sector_slugs=cfg.sector_index_grounding.activated_slugs)
    _index_valuation_metrics(con, tracked_index, *, activated_sector_slugs):
      slug = _INDEX_NAME_TO_SLUG.get(norm) or norm
      if slug in SECTOR_INDEX_KEYS and slug not in activated_sector_slugs:
          return (None, None, None, None, None)        # B1: byte-identical
      ... existing path: read DuckDB, 120/180 gate, self_history_percentile ...
      -> valuation_percentile_fundamental (PE); _pb stays None for sectors
```

## 7. Testing (TDD, test mirrors source)

**Structural (no network):**
- **Alias-collision rejection:** building `SECTOR_NAME_TO_SLUG` from all `(display_cn + aliases)` normalized yields **no key mapped to two distinct slugs** (assert no silent overwrite). Non-tautological.
- **Curated-config coverage:** load the real `config/universe/cn_funds.yaml`; every sector-ETF `tracked_index` resolves via `SECTOR_NAME_TO_SLUG` to a matrix slug (proves config ↔ matrix sync — no curated sector ETF silently unmapped). Non-tautological. *(Derived-map keyset equality is noted as tautological and not relied upon.)*
- **Resolution:** each universe `tracked_index` (incl. the `中证机床ZZ` alias) → expected slug → expected code.
- **SoT internal contract:** every `SectorIndex` has non-empty `code`/`official_cn`; slugs unique.

**Identity guard — live-gated (`IRC_RUN_LIVE_AKSHARE=1` + marker; gate #4):** the load-bearing correctness test. For each `SectorIndex`, assert its `code` resolves in `index_csindex_all` to the committed `official_cn` (catches *valid-but-wrong* codes — a code that returns PE but is the wrong index). 16 CSI codes covered here; `sse_star_chip` (000685) is **not** in `index_csindex_all` → cross-check via the SSE source (`index_stock_info`/EastMoney) or treat as an explicit, documented gate-#4 manual confirmation.

**Activation gate (no network):**
- Flag-OFF (empty allowlist): a **mature** synthetic sector series (seeded in `index_valuation_history`) yields `valuation_percentile_fundamental is None` **and** raw `pe_ttm/pb/dividend_yield` None (full short-circuit, byte-identical).
- Flag-ON (slug in allowlist): same mature series → percentile populated; PB stays None (csindex).
- Threading test: the allowlist reaches `_index_valuation_metrics` (no global read).
- Broad-index path unchanged with the allowlist empty and non-empty.

**Live-gated (gate #4):** `test_sector_index_valuation_live.py` already parametrizes over `sorted(_SECTOR_INDEX_CODE)` → **auto-covers all 17 codes**; strengthen it to also assert the returned frame has a numeric `市盈率1` **and** pair with the identity guard above (code↔official-name), so "a code returns PE" alone is no longer sufficient.

**Per-slug ingest audit (gate #3 artifact, B1):** after a real `irc run --only ingest` (or the sector ingest), a helper `audit_sector_ingest(con) -> rows` reports **per slug**: row count, has-numeric-PE, latest date, freshness (days), and maturity (points/span vs 120/180). Replaces the ingestor's aggregate count (`index_valuation_ingestor.py:31` silently skips `None` histories). The B1 PR records this table; expected state = all 17 present & accumulating, **0 mature → 0 grounded**.

**Invariants:** H3 universal gapped-row + SAME-3 citation-set equality unaffected with the allowlist empty (B1) and non-empty (B2). Lint: `uv run ruff check src tests` clean.

## 8. Rollout & exit gates (roadmap §4)

**B1 — data onboarding (allowlist empty).** SoT module + fetcher import + config + activation gate + tests + per-slug ingest audit + docs.
- Gate #1 tests/ruff green. Gate #2 invariants intact (byte-identical, allowlist empty). **Gate #3 NOT claimed** — B1 reports grounded = 0 by design (the ingest audit shows all 17 accumulating). Gate #4 live identity+PE confirmation (this spec's matrix; #7/#16 flagged). Gate #5 **N/A at B1** (no activation → no recommendation change; the empty diff is *expected*, not a pass). Gate #6 docs synced (CONTEXT.md "Valuation inputs", CHANGELOG `[Unreleased]`, ROADMAP Phase B → B1 done).

**Maturation wait (~6 months).** Series accumulate via routine weekly `irc run`. No code change.

**B2 — activation (after gate #5).** When series mature (per the ingest audit):
- Produce the **real** before/after diff (`memo.md` / `opportunity` / `narrative` valuation buckets, NAV-vs-PE band flips, Δpercentile) for funds whose slug matured — the genuine gate-#5 artifact (roadmap line 146).
- Human sign-off; resolve flags #7 (`sse_star_chip`) and #16 (`csi_resource`) before adding them.
- Add the reviewed mature slugs to `sector_index_grounding.activated_slugs`. **Gate #3 now measured & passed** (grounded count > 0). ADR 0012 addendum + CHANGELOG + CONTEXT.md record the real diff.
- **Phase A dependency (roadmap §5, line 167):** B2 activation assumes the slot + divergence-advisory machinery is validated on real index-path output. Phase D validated the slot for the active path; the **index-path divergence advisory** is Phase A's validation. B2 is therefore gated on *either* Phase A being validated *or* B2 independently verifying the advisory on the first matured sector slug. B1 carries no such dependency (inert).

**Sequencing (roadmap §6):** `brainstorming (this) → spec → writing-plans → autodev` for **B1 only** (code+tests autodev-able; gate #4 live confirmation is a hard stop). B2 is **not** planned now — it is a small, post-maturation, post-gate-#5 change (a config edit + recorded diff + docs), governed by §8; it gets its own short plan once the maturation/review outcome is known. The roadmap notes A/Phase 0 as the cheaper near-term wins; Phase B B1 proceeds in parallel safely because it is inert.

## 9. Error handling / degradation

- Unknown slug / adapter failure / empty frame / immature series → `None` → NAV fallback (existing contract).
- Non-activated sector slug → full all-`None` short-circuit → byte-identical (§3.2).
- `valuation_percentile_fundamental[_pb]` are plain numeric inputs (no `ThesisEvidence`, no `[ref:...]`) → dual-coverage gate, citation selector, SAME-3, H3 partition, 16-hex citation id (ADR 0001), Policy B / `thesis_state` ownership (ADR 0003) all structurally unaffected — `valuation_state` is a separate axis and never leaks into Policy B.

## 10. Out of scope

- **PB for sectors** (PE-only; documented gap; a PB source is a separate spike).
- **Any backfill source** for sector PE history (the ramp is accepted; no full-history endpoint exists via csindex).
- **Generated-catalog sector ETFs** (fund-name-as-index; never resolve) — curation of those is separate.
- **The `中证机床ZZ` universe rename** — separate, separately-reviewed config change.
- **Phase A (broad-index) activation**, Phase C (foreign), Phase 0 (gold/bond) — independent, additive.
- **Classifier / advisory logic changes** — none; Phase B only feeds the existing slot.
