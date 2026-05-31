# Item 001 — Consensus upside + pe/pb wiring

> Run: `funding-analysis` · Source: `docs/funding-analysis-review.md` → "## Recommended changes" #1
> Status: spec · Authored 2026-05-31 (autonomous run, no user — decisions made and recorded below)

## Goal

IRC already fetches data it then throws away (`BrokerReport.target_price` is hardcoded
`None`) and declares valuation fields it never populates (`OpportunityInput.pe_ttm`, `pb`,
`dividend_yield`). This item closes that gap **using only data the pipeline can actually
obtain**: it adds index-level PE/PB/dividend-yield population at the `OpportunityInput`
construction site for rows that track a recognised CN broad index, and it wires a pure,
end-to-end **consensus-upside** metric (`median(target_price) / latest_close − 1`) that
activates automatically the moment any data source supplies broker target prices. Because
the current AkShare EastMoney broker endpoint carries **no** target-price column (confirmed
below), the upside field is populated *where available, `None` otherwise* — no fabrication,
no dead code. The valuation axis the review asked for is added at the only instrument level
that makes sense for IRC (funds/ETFs/tracked indices, not single A-shares).

## Context grounding (verified, not assumed)

- **`OpportunityInput` is built per fund/ETF/tracked-index instrument**, never per single
  A-share. Sole construction site: `src/irc/commands/opportunity_cmd.py::_build_input`
  ~~(line ~559)~~ — corrected by grill: `_build_input` is defined at **opportunity_cmd.py:532**;
  the `OpportunityInput(...)` skeleton is built at :559 and `populate_inputs` is called at :579.
  → `src/irc/opportunity/inputs_loader.py::populate_inputs` (def at :93). `populate_inputs`
  fills evidence fields from DuckDB; `pe_ttm`/`pb`/`dividend_yield` are **not** populated
  anywhere today (grill-verified: no non-test reader of these three fields exists in `src/`).
- **`stock_research_report_em` returns NO target-price column.** Verified against installed
  AkShare source: the `indvAimPriceT`/`indvAimPriceL` (目标价) raw fields are renamed to
  `"-"` and dropped; the final frame exposes only rating, broker, forward-EPS, forward-PE,
  date, PDF link. The repo's own test `tests/fundamentals/test_akshare_fundamentals.py:372`
  already asserts `target_price is None` ("no target_price column in EastMoney feed").
- **The review's named pe/pb endpoints are wrong for IRC's instrument level.**
  `stock_a_indicator_lg` is absent from installed AkShare; `stock_individual_info_em`
  returns only market cap + latest price (no PE/PB). Both are per-A-share anyway. The
  correct installed **index-level** endpoints are `stock_index_pe_lg` / `stock_index_pb_lg`
  (乐咕乐股 — both PE and PB, ~12 named broad indices addressed by Chinese name) and
  `stock_zh_index_value_csindex` (CSI code — PE + dividend yield, no PB).
- The lookthrough layer already owns the broad-index key→Chinese-name map
  (`src/irc/opportunity/lookthrough.py::_BROAD_INDEX_DISPLAY`, e.g. `csi300→沪深300`),
  ~~which is exactly the symbol vocabulary `stock_index_pe_lg`/`stock_index_pb_lg` accept.~~
  — corrected by grill: `_BROAD_INDEX_DISPLAY` has **9** keys (`csi300`, `csi500`, `csi1000`,
  `csi_a500`, `sse50`, `star50`, `chinext`, `csi_dividend`, `csi_dividend_lc`), a **subset** of
  what the legulegu endpoint accepts — not "exactly" its vocabulary. The fetcher's name-map must
  only claim the keys it can resolve and return `None` for the rest. QDII/sector indices live in
  the **separate** `_QDII_US_DISPLAY` / `_QDII_HK_DISPLAY` / `_SECTOR_THEME_DISPLAY` maps and are
  correctly out of scope (they are not CN-broad indices addressable by `stock_index_pe_lg`).

## Acceptance criteria

Each is independently verifiable.

1. **New pure consensus-upside function.** `src/irc/fundamentals/consensus.py` exposes
   `consensus_upside_pct(reports: tuple[BrokerReport, ...], latest_close: float | None)
   -> float | None`. Pure, no I/O. Returns `median(non-None target_price) / latest_close − 1`
   when ≥1 report has a non-None `target_price` **and** `latest_close` is a positive float;
   returns `None` otherwise (no target prices, empty reports, or non-positive/`None` close).
   Median of an even count uses the standard two-middle mean. Unit-tested for: no targets →
   `None`; positive close + single target; even/odd target counts; `latest_close=None` →
   `None`; `latest_close<=0` → `None`.

2. **New `OpportunityInput.consensus_upside_pct` field.** Added to
   `src/irc/opportunity/types.py::OpportunityInput` as `consensus_upside_pct: float | None
   = None` (appended after existing valuation fields; default keeps every existing
   constructor call valid). A test asserts the field exists and defaults to `None`.

3. **New thin index-valuation fetcher.** `src/irc/fundamentals/akshare_index_valuation.py`
   exposes `fetch_cn_index_valuation(index_key: str) -> IndexValuation | None`, where
   `IndexValuation` is a new frozen dataclass `(index_key, pe_ttm, pb, dividend_yield,
   as_of_iso)` (`pe_ttm|pb|dividend_yield` each `float | None`). The fetcher maps
   `index_key` → Chinese index name via a module constant that reuses/derives from
   `_BROAD_INDEX_DISPLAY`, calls `stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) via
   the existing `_ak_call` indirection, extracts the latest-row PE and PB, and returns
   `None` for unknown keys or on any adapter failure/empty frame (degrade-to-None contract,
   matching `fetch_cn_filing_digest`). The frame-parse/extraction logic is a **separate pure
   helper** unit-tested against a fixture DataFrame with no network.

4. **`populate_inputs` wires pe/pb/dividend-yield + consensus upside.** `populate_inputs`
   (or a small extracted helper it calls) sets `pe_ttm`, `pb`, `dividend_yield`, and
   `consensus_upside_pct` on the returned `OpportunityInput` via `dataclasses.replace`.
   `pe_ttm`/`pb`/`dividend_yield` come from `fetch_cn_index_valuation(skeleton.tracked_index)`
   **only when** `tracked_index` is a recognised broad-index key; otherwise they stay `None`.
   `consensus_upside_pct` is computed from cached broker reports for the instrument (where
   available) and `series.iloc[-1]` (the latest close already loaded by `_price_series`);
   when no broker reports / no price are available it stays `None`. A test with a stubbed
   fetcher + in-memory DuckDB asserts: recognised index → pe/pb/div populated; unrecognised
   index/active-fund/gold/bond → all three `None`.
   - **Inertness lock (added by grill).** A regression test asserts that for a row whose
     `pe_ttm`/`pb`/`dividend_yield`/`consensus_upside_pct` are now populated, the
     `classify_valuation` output (state + reason) is **byte-identical** to the pre-item-001
     result — proving population is inert at the state level until item 002 wires these fields.
     `consensus_upside_pct` is **ratio units** (`median/close − 1`, e.g. `0.12` = +12%), matching
     the `qdii_premium_pct` ratio convention; it is NOT percent units. (Term + boundary recorded
     in CONTEXT.md "Valuation inputs".)

5. **`target_price` remains honestly `None` on the EastMoney path.** `fetch_cn_broker_reports`
   is **not** changed to invent a target price; the existing assertion in
   `tests/fundamentals/test_akshare_fundamentals.py` that `target_price is None` for the
   EastMoney feed stays green. A comment at the `target_price=None` site
   ~~(`akshare_filing.py:84`)~~ — corrected by grill: the `target_price=None` line is
   **`akshare_filing.py:83`** — records *why* (no target-price column upstream) and points at the
   consensus-upside consumer (and at [ADR 0009](../../adr/0009-consensus-upside-degrade-to-none.md)).

6. **No-network correctness of the whole stage.** `uv run pytest tests/fundamentals
   tests/opportunity` passes; `uv run ruff check src tests` is clean. The new files stay
   under the 200-line budget and new functions under the ~20-line ideal (helpers extracted).

7. **Live fetcher test is double-gated.** Any test that hits real AkShare for
   `fetch_cn_index_valuation` carries a `pytest.mark.live_akshare` marker **and** is skipped
   unless `IRC_RUN_LIVE_AKSHARE=1` (existing "Live test gate" pattern). All other tests run
   offline with stubbed `_ak_call`.

## Non-goals (explicit)

- **No `valuation_state` classifier change.** Making `valuation_state` consume the new
  fundamental inputs (pe/pb + upside) and gating `core_dca` on cheap-AND-intact is **item
  002**. This item only *populates* the inputs; it does not change how any state is derived.
- **No provider-pluggable / Tushare refactor.** Introducing a provider-agnostic CN
  fundamentals interface or wiring Tushare (which *does* carry target prices, and would
  light up criterion 1's upside metric for free) is **item 003**. This item stays on the
  existing AkShare adapters.
- **No new `ThesisEvidence` / citation emission.** pe/pb/upside are numeric `OpportunityInput`
  metrics, not cited evidence rows. No change to the dual-coverage gate, Policy B, H3/SAME-3,
  or `select_citations`. (See Constraints.)
- **No change to broker-rating consensus** (`_broker_consensus` in `thesis_evidence.py`)
  — that is the rating-sentiment information leg and is orthogonal to price upside.
- **No `key_ratios` / ROE / debt-equity** (that is item 004) and **no bull/bear debate**
  (item 005).

## Constraints

- **Purity / effects at edges.** `consensus_upside_pct`, `IndexValuation` extraction, and the
  index-name mapping are pure and unit-tested without mocks. Network I/O lives only in the new
  thin `fetch_cn_index_valuation` wrapper (via the existing `_ak_call` indirection) and in the
  already-impure `populate_inputs` (DuckDB) / `opportunity_cmd` edge.
- **Immutability.** All new types are `@dataclass(frozen=True)`. `populate_inputs` returns a
  new `OpportunityInput` via `dataclasses.replace` — no mutation (matches existing code).
- **No new citations.** This item emits zero `ThesisEvidence`; the 16-hex citation-id contract
  (ADR 0001), Policy B / `thesis_state` ownership (ADR 0003), and H3 / SAME-3 invariants
  (ADR 0004) are untouched. If a later item promotes upside to cited evidence it must respect
  the preimage contract — out of scope here.
- **Forbidden indicator.** `基金概况` is **not** used (we call index-valuation endpoints, never
  the fund static-profile indicator). The acceptance grep test stays green; no production code
  references the literal string.
- **Live-test gating.** New live fetcher tests are double-gated (`pytest.mark.live_akshare`
  + `IRC_RUN_LIVE_AKSHARE=1`).
- **Size budget.** New files < 200 lines; new functions < 20 lines ideal — extract helpers
  rather than nest. `inputs_loader.py` gains at most one small helper call; if it would exceed
  budget, the index-valuation population helper lives in the new module, not inlined.
- **Degrade-to-None.** Every new fetch path returns `None`/empty on failure and never raises,
  matching `fetch_cn_filing_digest` / `fetch_fund_nav_report`, so the orchestrator records a
  gap rather than crashing.

## Open questions resolved during brainstorming

1. **Does `stock_research_report_em` return target prices?** — **No (decided: do not
   fabricate).** Verified against installed AkShare source (target-price raw fields dropped to
   `"-"`) and the repo's own passing assertion. Rationale: inventing a value would corrupt the
   upside metric and break an existing test. `target_price` stays `None` on the EastMoney path;
   the upside metric is wired but evaluates to `None` today and activates automatically when a
   target-price-bearing source (item 003 Tushare) lands.

2. **What is "consensus upside" concretely, and where does the price come from?** — **Decided:**
   `consensus_upside_pct = median(non-None broker target_price) / latest_close − 1`, a pure
   function returning `None` when no targets exist. **Latest price needs no new fetch** —
   `populate_inputs` already loads a close/NAV series via `_price_series`; `series.iloc[-1]` is
   the latest close. Rationale: keeps the metric honest and zero-cost, and reuses existing I/O.

3. **Which AkShare indicator supplies pe/pb, for which instrument level?** — **Decided:**
   populate at the **instrument (fund/ETF/tracked-index)** level — the only level at which
   `OpportunityInput` is built — using **`stock_index_pe_lg` + `stock_index_pb_lg`** (both
   PE and PB; addressed by the Chinese index name IRC already maps in `_BROAD_INDEX_DISPLAY`).
   The review's `stock_a_indicator_lg` is absent from installed AkShare and `stock_individual_info_em`
   carries no PE/PB; both are per-A-share and wrong for this level. Scope: populate where
   `tracked_index` is a recognised broad index, `None` otherwise (sector themes, QDII, active
   funds, gold, bond). `dividend_yield` is taken from the index endpoints where present.
   Rationale: matches IRC's actual instrument granularity and reuses the existing index-key
   vocabulary; avoids per-constituent aggregation that belongs to a later effort.

4. **Could not fully resolve from code + MASTER-SPEC alone:** the exact column **names** and
   latest-row selection semantics of `stock_index_pe_lg` / `stock_index_pb_lg` (the legulegu
   endpoints) are not pinned without a live response. **Mitigation, not a blocker:** the
   extraction helper is written defensively (probe a small set of candidate PE/PB column
   labels — e.g. `市盈率`/`平均市盈率`/`pe` / `市净率`/`pb` — pick the latest-date row, coerce
   to float, return `None` on miss) and is the single point that a one-line gated live test
   pins during implementation. The pure helper + fixture remain fully testable offline.

## Resolved decisions

Q/A pairs from the grill-with-docs pass (2026-05-31, autonomous — recommended answers
auto-accepted; no user in the loop). Verdict: **PASS** (no spec ↔ ADR/code contradiction).

- **Q1 — Is `consensus_upside_pct` a new load-bearing term, and what units?**
  **A:** Yes — add to CONTEXT.md "Valuation inputs". Lock it as **ratio units** (`median/close − 1`,
  e.g. `0.12` = +12%), matching the closest sibling `qdii_premium_pct` (also a price-vs-reference
  ratio). The `_pct` suffix in this codebase is units-inconsistent, so the units are stated
  explicitly in CONTEXT.md to stop item 002 mis-reading it as percent units.
  **Doc impact:** CONTEXT.md term `consensus_upside_pct`.

- **Q2 — Does pe/pb/upside population interact with the dual-coverage gate, citation scope,
  H3/SAME-3, or Policy B?**
  **A:** No — grill-verified by grep: these are plain `float | None` scalars on `OpportunityInput`,
  not `ThesisEvidence`; they carry no `scope`/`citation_kind`/`citation_id`/`owner_instrument_id`,
  so ADR 0001's provenance contract, the dual-coverage gate, the citation selector, SAME-3, H3's
  `evidence_gaps` partition, and Policy B's quorum are all structurally untouched. Recorded so
  item 002 doesn't re-litigate it. **Doc impact:** CONTEXT.md term `consensus_upside_pct` (property
  noted) + "Valuation-input inertness" entry.

- **Q3 — Is the item 001 / 002 boundary crisp; does item 001 touch any classifier or `core_dca`?**
  **A:** Crisp and inert. No classifier reads pe/pb/dividend_yield/consensus_upside today
  (`classify_valuation` reads only `valuation_percentile_self` + `earnings_yield`/`real_yield_10y`);
  `OpportunityInput` is never serialised to disk. Item 001 only POPULATES inputs + adds the pure
  helper/fetcher — it must NOT change `classify_valuation`, `_decide_opportunity_state`, or the
  `core_dca` gate. Added an **inertness regression lock** to AC4 (classify_valuation output
  byte-unchanged for a populated row). **Doc impact:** CONTEXT.md "Valuation-input inertness"
  entry + AC4 clarification.

- **Q4 — Is a new ADR warranted under the three-of-three bar?**
  **A:** One ADR. *Adding scalar inputs + a pure helper* → 0/3 (reversible, unsurprising, no
  trade-off) → no ADR. *Populating at index level vs per-A-share* → ~2/3 (a consequence of the
  existing per-fund instrument granularity, not a new decision) → no ADR. *Wire consensus-upside
  end-to-end but degrade to `None` rather than fabricate a target price* → **3/3** (hard to
  reverse plumbing + honesty contract; surprising — "a metric that never fires"; real trade-off —
  fabricate / drop / wire-degrade). **Doc impact:** **ADR 0009** created.

- **Q5 — Any factual spec error vs. code requiring a strike-through correction?**
  **A:** Three minor, non-load-bearing line/count errors (struck through, never deleted):
  (a) `_build_input` is at `opportunity_cmd.py:532` (skeleton at :559, `populate_inputs` call at
  :579), not "~559"; (b) `target_price=None` is at `akshare_filing.py:83`, not `:84`;
  (c) `_BROAD_INDEX_DISPLAY` has **9** keys (a subset of the legulegu endpoint's coverage), not
  "exactly the symbol vocabulary" — and QDII/sector indices live in separate maps, correctly out
  of scope. None contradict a load-bearing ADR or break the design → Verdict stays PASS.
  **Doc impact:** none beyond the in-spec strike-throughs.

- **Q6 — Does `consensus_upside_pct` need disambiguation from the existing `_broker_consensus`?**
  **A:** Yes — one line. `_broker_consensus` (in `opportunity/thesis_evidence.py`) is broker
  *rating sentiment* (information-leg); `consensus_upside_pct` is a *price-target* valuation scalar.
  CONTEXT.md states the distinction so the two are not conflated. **Doc impact:** CONTEXT.md term
  `consensus_upside_pct` (distinction noted).
