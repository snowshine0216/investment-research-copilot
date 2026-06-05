# Valuation-anchor coverage roadmap — NAV → PE/PB

**Status:** In progress — **Phase D shipped & live (2026-06-05)**; Phases A/B/C + Phase 0 open.
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
| B — sector ETFs | ☐ open | +21 funds (3%) — PE-only (csindex) |
| C — foreign (US/HK) | ☐ open (needs source decision) | +141 funds (21%) |
| Phase 0 — correctness (gold, bond-misclass) | ☐ open | independent |

**What "live" changed:** active CN equity funds with no `tracked_index` now value off their
holdings' PE/PB (a current-basket harmonic series) instead of NAV momentum; the divergence advisory
fires when NAV and PE disagree; on the real before/after, 3 funds changed `valuation_state` and 1
(`110022 易方达消费`) moved `small_watch → core_dca`, with H3/SAME-3 invariants intact. Note: Phase D's
40 grounded ≠ the theoretical +383 below — the 120/180 maturity gate (not just coverage) binds, so the
honest reach is far smaller. See §3 Phase D and `docs/2026-06-04-phase-d-lookthrough-pr1/gate5-review-note.md`.

**Move forward from here:** the remaining index-path phases are A → B → C (each additive into the same
slot), plus the independent Phase 0 correctness fixes, plus one Phase-D follow-up (add `tracked_index`
mappings for index products currently routed through the look-through). See §7 for the now-narrowed
open decisions.

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

### Phase B — Sector expansion
- **Scope:** the 21 CN sector ETFs (机器人, 通信设备, 半导体, 算力, …).
- **Work:** map ~18 more CSI index codes into `_SECTOR_INDEX_CODE`
  (`src/irc/fundamentals/akshare_index_valuation.py:47`) + corresponding slugs in
  `_SECTOR_INDEX_DISPLAY`/`_INDEX_NAME_TO_SLUG`. Investigate whether
  `stock_zh_index_value_csindex` returns **full history in one call** — if yes, backfill and
  skip the `MIN_PE_DAYS=180` accumulate-forward wait; if no, accept the ~6-month ramp.
- **Data source:** csindex (`市盈率1`) — **PE-TTM only, no PB**. (So sector funds are
  "PE-only" unless a PB source is added — flag against the user's "PE/PB" wording.)
- **Coverage delta:** +21 funds (3%).
- **Risk:** ~18 CSI codes are empirical — each needs a live confirmation (degrade-to-None on miss).

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
Now that Phase D validated the look-through and the slot is exercised end-to-end on real output, the
cheapest wins are **Phase A** (broad-index grounding, +19, data+fetcher already exist — just needs the
live-symbol fix + slug map) and **Phase 0** (gold/bond correctness, independent). Both are single-spec
`autodev`-able with the live-symbol + output-review steps as hard human gates (§6). Phase A also
absorbs the Phase-D follow-up (the index products miscoded as active). Phases B (sector) and C
(foreign) follow, with C still needing the source-selection decision (#3) before it can be planned.
