# Valuation-anchor coverage roadmap — NAV → PE/PB

**Status:** In progress — **Phase D shipped & live (2026-06-05)**; **Phase B B1 onboarded (activation OFF, 2026-06-05)**; Phases A/C + Phase 0 open, **Phase B B2 deferred** (pending ~6-month maturation + gate #5).
**Goal:** Move fund `valuation_state` off the NAV self-history percentile (a price-momentum
proxy) and onto a **fundamental anchor (PE/PB historical percentile)** for as many funds as
the data honestly allows.
**Builds on:** [ADR 0012 — fundamental-led equity valuation](../adr/0012-fundamental-led-equity-valuation.md)
(+ its 2026-06-05 Phase D addendum), valuation-grounding item 001 (`docs/2026-06-03-valuation-grounding/`),
cyclical-valuation-guard (`docs/2026-06-04-cyclical-valuation-guard/`),
**Phase D (`docs/2026-06-04-phase-d-lookthrough-pr1/` + spec `docs/superpowers/specs/2026-06-04-phase-d-active-lookthrough-design.md`)**.

---

## 0. Progress snapshot (2026-06-05)

**Phase D (active-fund holdings look-through) is DONE and LIVE in production** — built and shipped
*first*, ahead of the A→D sequence below. This was safe because Phase D's per-stock look-through is
its **own** fetch/ingest path (independent of the index-path phases A/B/C), and the shared
`valuation_percentile_fundamental` slot it writes into was already proven by ADR 0012 / item 001.

| Phase | Status | Reach (measured) |
|---|---|---|
| **D — active-fund look-through** | ✅ **live** (PR #109/#110/#111, flag `enabled: true`, floor `0.50`) | **40 funds grounded** at floor 0.50 (sensitivity 0.40→71 · 0.60→17). Gate #4 (live columns) PASS; gate #5 (human floor decision) signed off. |
| A — broad-index grounding | ☐ open | +19 funds (3%) — data+fetcher exist; needs the live-symbol fix + slug map |
| B — sector ETFs | ◑ B1 done (onboarding; activation OFF) | +17 sector slugs onboarded, PE-only (csindex); B2 activation pending maturation + gate #5 |
| C — foreign (US/HK) | ☐ open (needs source decision) | +141 funds (21%) |
| Phase 0 — correctness (gold, bond-misclass) | ☐ open | independent |

**What "live" changed:** active CN equity funds with no `tracked_index` now value off their
holdings' PE/PB (a current-basket harmonic series) instead of NAV momentum; the divergence advisory
fires when NAV and PE disagree; on the real before/after, 3 funds changed `valuation_state` and 1
(`110022 易方达消费`) moved `small_watch → core_dca`, with H3/SAME-3 invariants intact. Note: Phase D's
40 grounded ≠ the theoretical +383 below — the 120/180 maturity gate (not just coverage) binds, so the
honest reach is far smaller. See §3 Phase D and `docs/2026-06-04-phase-d-lookthrough-pr1/gate5-review-note.md`.

**Move forward from here:** the remaining index-path work is **A**, **B2** (B1 is onboarded; activation
is deferred pending maturation + gate #5 — see §3 Phase B), and **C** (each additive into the same
slot), plus the independent Phase 0 correctness fixes, plus one Phase-D follow-up (add `tracked_index`
mappings for index products currently routed through the look-through). The cheapest near-term wins are
**Phase A** and **Phase 0** (§7 → "Recommended next move"). See §7 for the now-narrowed open decisions.

---

## 1. Why

`classify_valuation` (`src/irc/opportunity/states.py:236`) already prefers
`valuation_percentile_fundamental` (PE-TTM percentile) over the NAV self-history percentile
when present — but the slot is **empty for every real fund today**. The 2026-06-04 production
run grounded **0 of 662** instruments on PE/PB. Causes, all verified:

- `index_valuation_history` holds only `csi300` + `csi1000`.
- `_INDEX_NAME_TO_SLUG` (`src/irc/opportunity/lookthrough.py:77`) inverts only the 3 sector
  display names; broad display names ("沪深300"…) are deliberately not inverted, so a fund's
  `tracked_index` never resolves to a slug. The #102 broad grounding is dormant in prod.
- No US/HK index-valuation source exists (legulegu/csindex are A-share only).
- Active funds carry no `tracked_index` at all.

Consequence: thematic ETFs and gold currently receive directional `expensive` /
`very_expensive` verdicts from what the code itself labels "price momentum, not valuation"
(`states.py:145-150`).

## 2. The hard constraint (read this before promising "most funds")

PE/PB is meaningful **only where earnings exist**. The universe splits:

| Segment | Count | % | PE/PB verdict |
|---|---:|---:|---|
| Active CN equity funds (no index) | 383 | 58% | only via **holdings look-through** (Phase D) |
| Bond funds | 88 | 13% | **never** — yield-curve anchor is correct |
| US / global equity ETFs | 87 | 13% | needs a non-CN source (Phase C) |
| HK equity ETFs | 54 | 8% | needs a non-CN source (Phase C) |
| CN sector ETFs | 21 | 3% | csindex code map (Phase B) |
| CN broad-index ETFs | 15 | 2% | **data + fetcher already exist** (Phase A) |
| Gold | 6 | 1% | **never** — no earnings |
| Index funds miscoded as active (broad) | 4 | 1% | Phase A |
| US "ETFs" that are bond funds | 3 | 0% | should use yield (correctness fix) |
| CN ETF, no index assigned | 1 | 0% | assign index |

**~15% of the universe (bonds + gold) must never use PE/PB — and already doesn't.**
Of the equity-applicable ~85%, the **58% active-fund block has no index**, so:

- Phases A–C (index-tracking funds) reach a ceiling of **~27% of the universe**.
- **Crossing "most funds" (>50%) is impossible without Phase D (active-fund look-through).**

There is no shortcut: the bulk *and* the hardest piece are the same block.

## 3. Phases

Each phase populates the **same** `valuation_percentile_fundamental` slot — the seam is already
there, so phases are additive and independently shippable.

### Phase A — Activate broad grounding (near-free)
- **Scope:** the 19 broad-index CN funds (15 ETFs + 4 miscoded index funds).
- **Work:**
  1. Add broad display names → slugs in `_INDEX_NAME_TO_SLUG`, with an alias map for the
     mismatches (`创业板50`/`创业板指` → `chinext`, `中证红利低波` → `csi_dividend_lc`; decide
     `标普红利低波50` — S&P-licensed, may be out of scope).
  2. Fix the broad ingest: 9 keys are requested but only 2 land — verify the legulegu `symbol`
     strings for `中证500/上证50/科创50/创业板/中证红利/红利低波/中证A500` and correct the
     mismatches (**requires a live AkShare check — `IRC_RUN_LIVE_AKSHARE=1`**).
- **Data source:** legulegu (`stock_index_pe_lg` / `stock_index_pb_lg`) — **PE + PB**.
- **Coverage delta:** +19 funds (3%). Also starts firing the price/fundamental divergence
  advisory on real output.
- **Risk:** changes real recommendations (NAV→PE on broad ETFs).

### Phase B — Sector expansion  (B1 ✅ done · B2 ◑ deferred)

- **B1 — data onboarding (activation OFF) ✅ DONE (2026-06-05).** Run record
  `docs/2026-06-05-phase-b-sector-b1/`; PRs [#114](https://github.com/snowshine0216/investment-research-copilot/pull/114)
  (merged) → [#115](https://github.com/snowshine0216/investment-research-copilot/pull/115) (roll-up, open).
  New single-source-of-truth catalog `src/irc/opportunity/sector_indices.py` (`SectorIndex` +
  `SECTOR_INDICES`, **17 slugs = 14 new + 3 folded-in metals**) **replaces** the old inline
  `_SECTOR_INDEX_CODE` / `_SECTOR_INDEX_DISPLAY` dicts (`lookthrough.py` /
  `akshare_index_valuation.py` import the derived maps). Config-gated activation
  (`sector_index_grounding.activated_slugs`, default empty, with a fail-loud validator that rejects
  unknown slugs), threaded explicitly `run_opportunity → _build_rows → _build_input →
  populate_inputs → _index_valuation_metrics` (keyword-only, no global read). Per-slug
  `audit_sector_ingest` (replaces the silent aggregate count); strengthened double-gated live
  identity guard. **Output byte-identical** with the allowlist empty; **grounded = 0 by design**
  (Gate #3 not claimed). Accumulation runs on every weekly `irc run` (the ingest leg auto-iterates
  `_SECTOR_INDEX_KEYS`; no further code change needed).
- **Data source:** csindex `stock_zh_index_value_csindex` (`市盈率1`) — **PE-TTM only, no PB**
  (sector `valuation_percentile_fundamental_pb` stays `None`; see §7 decision 2). Confirmed live
  2026-06-05: every code returns ~20 trailing rows/call; **no full-history backfill endpoint exists**.
- **Scope (honest):** 17 sector/thematic ETFs tracking **14 distinct CSI index names** + the 3 metals
  codes = **17 slugs / 14 new**. The earlier "21 funds / ~18 codes" estimate also counted
  generated-catalog sector ETFs (fund-name-as-index) that never resolve — out of scope.
- **B2 — activation ◑ DEFERRED (post-maturation + gate #5).** Because csindex accumulates forward
  ~20 days/call, a newly-wired index takes **~6 months** to clear `MIN_PE_POINTS=120 ∧
  MIN_PE_DAYS=180`. When series mature (track via `audit_sector_ingest`): produce the real NAV-vs-PE
  before/after diff, obtain gate-#5 human sign-off, then add the reviewed mature slugs to
  `activated_slugs`. **Not planned now** — a small config-edit + recorded-diff + docs change governed
  by B1 spec §8 (gets its own short plan once the maturation/review outcome is known). Coverage delta
  on activation: up to +17 sector slugs (3%), floor-bound by the maturity gate (same caveat as Phase D).

#### Phase B blockers / follow-ups — with disposition

| Item | Detail | Suggestion | Disposition |
|---|---|---|---|
| **Flag #7 — `sse_star_chip` (000685)** | SSE-listed; **absent from `index_csindex_all`**, so the CSI-catalog identity guard cannot validate it (the value endpoint still returns PE — i.e. "PE present" ≠ "right index"). | Confirm the code↔index identity via the SSE source (`index_stock_info` / EastMoney) or a recorded manual source **before** adding it to `activated_slugs`. | **Defer to B2** (gate #4). Inert in B1 (never grounded; live test skipped). |
| **Flag #16 — `csi_resource` (000819)** | Committed `official_cn` `中证申万有色金属指数` ≠ display `中证资源`; the strengthened live identity guard surfaces this mismatch. The /code-review flagged that `000819` may actually be `中证资源指数`. | Resolve **live** (`IRC_RUN_LIVE_AKSHARE=1`): confirm whether any curated fund tracks this and which index `000819` truly is, then correct the catalog `official_cn` once verified. Do **not** guess offline. | **Defer to B2** (gate #4). Inert in B1. |
| **Sector PB gap** | csindex carries no PB for sectors → sector PB percentile stays `None`. | Accept PE-only (PB is corroborate-only, ADR 0012 §5), **or** run a separate sector-PB source spike. | **Defer** — separate spike; user decision in §7 decision 2. |
| **`中证机床ZZ` universe value** | The malformed `tracked_index` `中证机床ZZ`; B1 resolves it via an **alias** in `SECTOR_INDICES` (no universe edit — a rename re-keys `map_lookthrough` / report grouping / allocation dedup → **not** byte-identical). | Optionally clean `中证机床ZZ → 中证机床` in `config/universe/*.yaml` in a separate, separately-reviewed PR (re-baselining the affected grouping outputs). | **Defer / optional** — the alias works indefinitely; rename only if desired. |
| **B2 maturation wait** | ~6 months of forward accumulation before any series matures (metals codes started 2026-05-08 → mature ~Nov 2026; the 14 new codes start from B1 merge). | No code change — let weekly `irc run` accumulate; watch `audit_sector_ingest` for `mature=True`. (Already investigated: no full-history csindex/alt endpoint to skip the wait, 2026-06-05.) | **Defer** — inherent wait, not a bug. |

- **Risk (on B2 activation):** changes real recommendations (NAV→PE) for matured sector funds — gated by
  the mandatory human output-diff review (gate #5). B1 carries **no** recommendation risk (allowlist empty).

### Phase C — Foreign index valuation source (US/HK)
- **Scope:** 87 US/global + 54 HK equity ETFs.
- **Work:** select and wire a non-CN index PE/PB feed (candidate: Tushare `index_global`;
  HK source TBD). New fetcher + ingest leg + slug map, same slot.
- **Data source:** TBD — **requires a source-selection decision (token, coverage, quality).**
- **Coverage delta:** +141 funds (21%).
- **Risk:** new external dependency; exploratory — needs a spike before a plan exists.

### Phase D — Active-fund holdings look-through ✅ DONE & LIVE (2026-06-05)
- **Scope:** active CN equity funds with no `tracked_index` (≤383; 58% of the universe is the ceiling).
- **Spec:** `docs/superpowers/specs/2026-06-04-phase-d-active-lookthrough-design.md`; run record `docs/2026-06-04-phase-d-lookthrough-pr1/`; design-of-record = ADR 0012 addendum (2026-06-05). Shipped as PR1 (shadow, #109/#110) → gate #4 → gate #5 → PR2 (flag flip, #111).
- **Solution as built:** per-stock PE/PB history from **EastMoney `stock_value_em`** (primary) + **Tushare `daily_basic`** (fallback) → DuckDB **`stock_valuation_history`** table (not a per-quarter JSON dir) via the dedicated heavy **`irc fundamentals stock-valuation`** command → pure **`opportunity/lookthrough_valuation.py`** rolls the fund's current top-N A-share basket into a **current-basket harmonic earnings-yield PE series** (PB in parallel), percentiled by `self_history_percentile` into the same slot. `irc opportunity` reads the cache only.
- **Open design decisions — RESOLVED:**
  - *Constructed weighted-PE history vs percentile-of-percentiles* → **constructed current-basket harmonic series** (earnings-yield aggregation; percentile-of-percentiles rejected — a mean of percentiles is not a percentile).
  - *Top-N truncation* → current disclosed top-N A-shares, **per-date renormalized** over holdings present at each date (bounds the current-weights × past-PE anachronism; a mega-cap alone can't masquerade as the basket).
  - *HK/US holdings with no A-share coverage* → **excluded from the covered set**; coverage ratio = `Σ covered weight_pct / 100` of NAV; below the configurable **`coverage_floor` (0.50, the gate-#5 choice)** → `None` → NAV fallback.
  - *Endpoint correction:* `stock_a_indicator_lg` is **absent in AkShare 1.18.60** — `stock_value_em` is used instead.
  - *PE vs PB:* PE clears the index path's `120/180` maturity gate; **PB delivered too** (corroborate-only, on the bare `<30` floor) — so Phase D is PE **and** PB, resolving §7 decision 2 for the active block.
- **Coverage delta (measured, not theoretical):** **40 funds grounded at floor 0.50** (71 @ 0.40, 17 @ 0.60). The +383 ceiling is an upper bound; the 120/180 maturity gate is the real binding constraint. "Most funds" in the strict >50% sense is **not** reached on current data — the honest reach is modest and floor-tunable.
- **Risk realized & contained:** biggest blast radius, shipped shadow-first (flag OFF, prod byte-identical) then flipped after a human diff review; H3/SAME-3 invariants verified intact in both flag states.
- **Follow-up (open):** several index/`指数增强`/`LOF` products lack a `tracked_index` mapping and currently route through the look-through. Add their mappings in `config/universe/cn_funds.generated.yaml` (`irc universe build-cn-funds`) so they ride the cleaner index path — this also overlaps Phase A.

### Phase 0 (parallel correctness fixes — independent of coverage)
- **Gold:** stop emitting a NAV-percentile `expensive`/`very_expensive`; either extend the
  symmetric withhold (currently `theme=metals` only) to gold, or give gold a real-rate/regime
  anchor.
- **USD-bond "us_etf":** the 3 bond funds miscoded as `us_etf` (e.g. 161716) run the equity
  price-percentile path; route them to the yield anchor (or fix their `asset_class`).

## 4. Exit gates (every phase must pass ALL before merge)

A phase is **done** only when:

1. **Tests green:** `uv run ruff check src tests` clean; `uv run pytest` (unit + integration)
   green; new behaviour covered TDD-first (test mirrors source).
2. **Invariants intact:** H3 universal gapped-row + SAME-3 citation-set equality unaffected
   (the valuation change must not alter publishability partitioning).
3. **Coverage metric met:** a real `irc run --from ingest` + `irc opportunity` shows the
   expected count of funds with non-`None` `valuation_percentile_fundamental`
   (A: ≥19 · B: ≥ A+sector-with-mature-series · C: ≥ A+B+foreign · D: ≥ A+B+C+active).
   *Measured, not asserted.*
4. **Live-data confirmation:** every new index symbol/code returns real rows under
   `IRC_RUN_LIVE_AKSHARE=1` (or the chosen provider's live gate). No silently-guessed strings.
5. **Output-diff review (HUMAN gate):** a side-by-side of `memo.md` / `opportunity` /
   `narrative` valuation buckets before vs after, signed off by the user. Changing the
   valuation basis changes recommendations — this gate is non-negotiable and cannot be
   auto-passed.
6. **Docs synced:** CONTEXT.md "Valuation inputs", CHANGELOG `[Unreleased]`, and an ADR
   addendum if the anchor semantics change.

## 5. Sequencing & dependencies

```
Phase 0 (correctness)  ──┐  (independent, do anytime)
Phase A (broad)  ────────┼──> B (sector) ──> C (foreign) ──> D (active look-through)
                          validates the slot + divergence advisory on real output;
                          B/C/D all reuse the slot A proves out.
```
B/C/D each *assume A is validated*, not merely merged — later phases build on a verified anchor.

## 6. Execution strategy — split into 4, do NOT chain in one autodev loop

**Is it OK to implement all of them?** Yes — the direction is sound and the seam is clean —
**but in order, gated, and not all autonomously.**

**One autodev loop or four?** **Four separate efforts.** Reasons an unattended single loop is unsafe here:

- **Human design decisions block autonomy.** Phase C needs a data-source choice; Phase D needs
  the look-through methodology decided. autodev *executes* decided plans; it does not *make
  architectural calls*. C and D are not "ready-to-execute plans" yet.
- **Empirical/live verification can't run offline.** A and B hinge on which legulegu symbols
  and CSI codes actually return data — that's a live AkShare step (double-gated), not something
  a sandboxed loop can deduce. Guessed strings silently degrade to None and look "green."
- **Per-phase human output review is required (gate #5).** Each phase changes real
  recommendations. autodev only completes-or-skips an item; it has no "pause for human sign-off"
  state. Chaining all 4 would merge A's recommendation changes and build B/C/D on top before
  anyone looked.
- **Real dependencies.** Backlog autodev treats items as ~independent; here later phases assume
  earlier ones are *validated*.

**Recommended mapping to tooling:**

| Phase | Tooling | Why |
|---|---|---|
| Phase 0 | `autodev` (single spec) or direct TDD | Self-contained, low risk; still stop at gate #5 |
| Phase A | `autodev` (single spec) | Code+tests autodev-able; **stop at the live-symbol + output gates** |
| Phase B | `autodev` (single spec) after codes confirmed | Confirm CSI codes live *first*, then let autodev wire+test |
| Phase C | `brainstorming` → spec → plan → *then* autodev the plan | Source selection is a human decision |
| Phase D | `brainstorming` → full spec (its own doc) → plan → autodev | Methodology is a human decision; biggest blast radius |

Net: A and B can each be a single autodev item **with the live-verify and output-review steps
treated as hard human gates**; C and D must be designed first, then optionally autodev'd. Do
not run all four in one loop.

**Validated by Phase D:** Phase D ran exactly this path — `brainstorming → spec → plan → autodev`
for PR1, with **gate #4** (live `stock_value_em` column confirmation) and **gate #5** (human diff
review + floor choice) as hard stops the autodev loop did not cross, followed by a small **PR2** flag
flip. The loop stopped cleanly at both human gates and shadow-shipped (flag OFF) before the flip — the
recommended pattern works; apply it to A/B/C.

## 7. Open decisions for the user

1. ~~**Scope of "most funds":** commit to Phase D or stop at index-tracking funds?~~ **RESOLVED —
   Phase D is shipped & live.** Note the honest outcome: "most funds (>50%)" is **not** reached on
   current data (40 grounded at floor 0.50), because the maturity gate binds harder than coverage. The
   live floor is config-tunable (`active_fund_lookthrough.coverage_floor`) if you want more reach at
   lower per-fund precision (0.40 → 71 grounded).
2. **PB requirement (narrowed):** Phase D delivers **PE and PB** for active funds. The remaining
   PE-only gap is the **sector path (Phase B, csindex `市盈率1`)** — accept PE-only there, or invest in
   a PB source for sectors?
3. **Phase C source:** Tushare (needs token) vs. another feed — or defer foreign (US/HK, +21%) entirely?
4. **Gold & bond-misclass fixes (Phase 0):** bundle now, or track separately? (Independent of the
   coverage phases — can be done anytime.)

### Recommended next move
Now that Phase D validated the look-through and **Phase B B1 onboarded the sector data layer**, the
cheapest remaining wins are **Phase A** (broad-index grounding, +19, data+fetcher already exist — just
needs the live-symbol fix + slug map) and **Phase 0** (gold/bond correctness, independent). Both are
single-spec `autodev`-able with the live-symbol + output-review steps as hard human gates (§6). Phase A
also absorbs the Phase-D follow-up (the index products miscoded as active). **Phase B B2 (activation)**
needs no work now — it unlocks itself after ~6 months of forward accumulation, then a small config-edit
+ gate-#5 diff review (track `audit_sector_ingest` for maturity; resolve flags #7/#16 first — see §3
Phase B blockers). **Phase C (foreign)** still needs the source-selection decision (#3) before it can be
planned.
