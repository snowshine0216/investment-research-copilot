# Item 004 — Deterministic `compute_ratios` key-ratios surface

> Run: `funding-analysis` · Source: `docs/funding-analysis-review.md` → "## Recommended changes" #4
> Status: spec · Authored 2026-05-31 (autonomous run, no user — decisions made and recorded below)
> Depends on: nothing hard. Independent of items 002 (merged) / 003 (Tushare). Touches only the
> fundamentals layer + a reason-only annotation; does NOT depend on Tushare landing.

## Goal

The review's TL;DR: IRC's fundamental layer is a *thesis-direction* engine, not a *quality/valuation*
engine — it reads revenue/NI YoY + gross margin + broker sentiment but has no balance-sheet quality
(debt/equity, ROE) and no earnings-quality (FCF) read. Recommendation #4 closes that gap with a
**deterministic, pure `compute_ratios(financials)`** that returns a small frozen `KeyRatios` record
`{roe, debt_equity, gross_margin, fcf_yield}` (all ratio units, all `float | None`) — **no LLM, no
I/O**. The headline constraint is determinism: same `financials` in → same `KeyRatios` out. Following
the item 001 (`consensus_upside_pct`) + item 002 (`_pe_pb_fragment`) precedent exactly, the ratios
**surface reason-only** — a Chinese caveat fragment appended to the constituent's `one_line_view` /
opportunity reason — and **never** drive any state, gate, or classifier. `compute_ratios` operates
over the line items IRC *already fetches* (via `FilingDigest`); `roe` is sourced from the
`净资产收益率` figure already present in the `stock_financial_abstract` frame (one new FilingDigest
field), `gross_margin` is passed through verbatim, and `debt_equity` / `fcf_yield` honestly degrade
to `None` today because their input line items are not yet fetched — wired-but-degrade-to-`None`,
mirroring ADR 0009. The metric self-activates the moment a richer source (item 003 Tushare) supplies
the missing line items, with zero further wiring.

## Context grounding (verified, not assumed)

- **`FilingDigest` already carries the earnings-quality inputs we surface today**
  (`src/irc/fundamentals/types.py:165-175`): `revenue_yoy`, `net_income_yoy`, `gross_margin`
  (ratio units, computed as `1 - cost/revenue` in `akshare_filing.py:145`), `guidance_text`,
  `source_url`. It does **not** carry `roe`, total debt, shareholders' equity, free cash flow, or
  market cap.
- **ROE is *already in the fetched dataframe* but dropped on the floor.** `stock_financial_abstract`
  exposes `净资产收益率` under the `盈利能力` (profitability) section — present in the live test
  fixture `_ABSTRACT_FRAME` (`tests/fundamentals/test_akshare_fundamentals.py:411-419`, value `0.18`
  for the latest quarter). It is extractable via the existing `_common_metric(df, name, col)` helper
  with a one-line section change (`选项 == "盈利能力"` instead of `"常用指标"`). No new AkShare call.
- **`consensus.py` is the exact template** (`src/irc/fundamentals/consensus.py`): a pure helper,
  ratio units, explicit NaN + zero/non-positive-denominator screening, `float | None` return,
  ADR-documented degrade-to-`None`. `compute_ratios` follows this shape.
- **`_pe_pb_fragment` is the exact reason-only-surface template**
  (`src/irc/opportunity/valuation_fundamental.py:46-53`): an optional Chinese fragment built from
  `float | None` inputs, appended to a reason string, never feeding a state. pe/pb stay reason-only
  *precisely because they lack peer/history normalisation* (item 002 Open Q3) — the same logic
  applies to absolute ratios here.
- **The constituent surface point is `_one_line_view`** (`src/irc/fundamentals/snapshot.py:426`):
  a ≤60-char deterministic per-holding label assembled from filing/broker/news evidence fragments,
  human-consumption only (CONTEXT.md "ConstituentAnalysis"). It is the natural carrier for a ratios
  fragment, parallel to how the filing fragment already lands there.
- **Filing-evidence-semantics addendum** (ADR 0001 §5, 2026-05-28): a `type="filing"` citation is a
  *disclosure-existence anchor*, NOT an endorsed performance figure; producers emit the locked phrase
  `{symbol} {fiscal_period} 财报已披露（口径未核实）` and MUST NOT inline a raw scalar
  (`revenue_yoy=`) in a citation summary. Ratios surfaced as *reason text* are not citation summaries,
  but they inherit the same posture: shown with a `口径未核实` caveat, never asserted as verified.
- **No existing `roe` / `debt_equity` / `fcf_yield` / `compute_ratios` / `KeyRatios` symbol exists**
  anywhere in `src/` or `tests/` (grep clean) — this is a clean addition.

## Decisions (auto-resolved; brainstorming, no user in loop)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| D1 | What is the input `financials`? New fetchers or existing container? | **Existing `FilingDigest`.** `compute_ratios(financials: FilingDigest) -> KeyRatios`. Add exactly **one** new field, `roe`, to `FilingDigest`, populated from the `净资产收益率` figure already in the fetched frame. Defer all new fetchers (debt/equity/FCF/market-cap). | Keeps 004 small & pure (review's "few hours"; CLAUDE.md size budget). ROE is free (already fetched, just dropped). New balance-sheet/cash-flow fetchers are scope-creep best handled when item 003's Tushare point-in-time feed lands. Wire-but-degrade-to-None (ADR 0009) lets the two unfetched ratios self-activate later. |
| D2 | `roe` source — recompute (NI/equity) or surface the provider figure? | **Surface the provider `净资产收益率` figure directly** (no equity line item, no recompute). | AkShare's `净资产收益率` *is* an already-computed ROE in ratio units; fetching a separate equity line item to recompute would (a) add a fetcher 004 is avoiding and (b) risk a different period/caliber mismatch. Honesty: surface what the disclosure states, caveated. |
| D3 | Units of each ratio | **All ratio units** (`0.18` = 18%), `float | None`. `roe` ratio; `debt_equity` ratio; `gross_margin` ratio (pass-through, already ratio); `fcf_yield` ratio. | Consistent with `gross_margin` (ratio), `consensus_upside_pct` (ratio, ADR 0009), `qdii_premium_pct` (ratio). One unit convention across the valuation/quality surface. |
| D4 | None / degrade behaviour | Each ratio is `None` when its input line item is absent, NaN, or the denominator is zero/non-positive. `debt_equity` and `fcf_yield` are **always `None` in production today** (inputs unfetched). `gross_margin`/`roe` are `None` whenever `FilingDigest` carries `None` for them. | Mirrors `consensus_upside_pct`'s explicit NaN + `<=0` screening and ADR 0009 degrade-to-None philosophy. No fabrication. |
| D5 | Where do ratios surface — reason or state? | **Reason-only** (Chinese annotation fragment, like `_pe_pb_fragment`). NOT a new state, NOT a gate. No change to `valuation_state`, `thesis_state`, Policy B, `core_dca`, or any classifier. | The review frames #4 as closing an *evidence/quality-read* gap, not adding a signal. Absolute ratios lack peer/history normalisation (same reason pe/pb stayed reason-only in item 002). Scope boundary: do NOT bolt a trading signal onto IRC. |
| D6 | Citation model — do ratios need `[ref:...]`? | **No.** Ratios are plain numerics (like `consensus_upside_pct`), NOT `ThesisEvidence`. They carry no `citation_id`. The underlying `FilingDigest` already produces the `type="filing"` disclosure-anchor citation. | ADR 0009 precedent: a numeric valuation input "touches none of the ADR 0001 citation invariants." SAME-3 / dual-coverage / H3 / Policy B are untouched. |
| D7 | Filing-evidence-semantics compliance | Ratio reason fragment carries a `口径未核实` caveat and is NOT injected into any `ThesisEvidence.summary`. The forbidden `revenue_yoy=`-style raw-scalar-in-citation rule is respected because ratios never enter a citation summary. | ADR 0001 §5: filing numbers are disclosure anchors, not endorsed performance; the reason fragment matches that posture. |
| D8 | Module placement | New pure module `src/irc/fundamentals/ratios.py` (parallel to `consensus.py`); the reason-fragment helper lives there too (or beside `_one_line_view`). New ADR `0010-key-ratios-degrade-to-none.md` recording the wire-but-degrade decision. | Mirrors `consensus.py` placement and the ADR 0009 precedent; keeps files <200 lines. |
| D9 | `KeyRatios` shape | Frozen dataclass `KeyRatios(roe, debt_equity, gross_margin, fcf_yield)`, all `float | None`, in `fundamentals/types.py` or `ratios.py`. `compute_ratios` returns it. | Immutability (CLAUDE.md). A typed record (vs a dict) makes the four-field contract explicit and is the project convention (`FilingDigest`, `KeyRatios` reads cleanly). NOTE: the master-spec row writes the return as `-> {roe, ...}` (dict notation) — interpreted as "these four keys", a frozen dataclass is the idiomatic realisation; flag as grill target G1 if the caller specifically wants a dict. |

## Acceptance criteria

1. **AC1 — `KeyRatios` type exists.** A frozen dataclass `KeyRatios` with exactly the fields
   `roe: float | None`, `debt_equity: float | None`, `gross_margin: float | None`,
   `fcf_yield: float | None` (all defaulting to `None`) is defined and immutable
   (`dataclasses.replace`-style updates only; mutation raises).
2. **AC2 — `compute_ratios` is pure and deterministic.** `compute_ratios(financials: FilingDigest)
   -> KeyRatios` performs no I/O, no LLM call, no logging, and no network access; the same
   `FilingDigest` input always yields an equal `KeyRatios`. A test calling it twice on the same input
   asserts equality; a test asserts the function body imports no `akshare` / `duckdb` / `llm` symbol.
3. **AC3 — `gross_margin` pass-through.** When `financials.gross_margin` is a finite float,
   `compute_ratios(...).gross_margin == financials.gross_margin` (ratio units, no transformation).
   When it is `None`, the result is `None`.
4. **AC4 — `roe` surfaced from disclosure.** `FilingDigest` gains a `roe: float | None` field;
   `fetch_cn_filing_digest` populates it from the `净资产收益率` row of the `盈利能力` section of
   `stock_financial_abstract` (via the existing `_common_metric` mechanism, latest period column),
   in ratio units; `compute_ratios(...).roe == financials.roe`. When the section/row is absent or the
   value is NaN, `roe` is `None` and the digest is still produced (ROE absence does NOT fail the
   digest — only revenue/NI/cost absence does, unchanged).
5. **AC5 — `debt_equity` and `fcf_yield` degrade to `None` today.** With no debt/equity/FCF/market-cap
   line items on `FilingDigest`, `compute_ratios(...).debt_equity is None` and
   `...fcf_yield is None` for every production input. A test documents this as the
   wired-but-degrade-to-None contract (not a bug).
6. **AC6 — zero / NaN denominator safety.** Any ratio whose computation would divide by zero or a
   NaN, or whose numerator/denominator is NaN, returns `None` (explicit NaN + non-positive-denominator
   screening, mirroring `consensus_upside_pct`). Verified by a parametrised test over
   `{0, NaN, None}` inputs.
7. **AC7 — reason-only surface.** A pure helper renders an optional Chinese ratios fragment
   (e.g. `（ROE 18% / 毛利率 69%，口径未核实）`) from a `KeyRatios`, emitting only the sub-fields
   that are non-`None`, and returns the empty string when all four are `None`. The fragment is
   appended to the constituent surface (`_one_line_view` or the opportunity reason) the same way
   `_pe_pb_fragment` is appended in `valuation_fundamental.py`.
8. **AC8 — no state / gate / classifier change.** No edit to `opportunity/states.py` classifiers,
   `valuation_fundamental.py` signal logic, Policy B (`policy_b.py`), `derive_thesis_from_evidence`,
   or `compose_opportunity_state`. A regression test asserts that for a fixture run, every
   `OpportunityRow`'s `valuation_state` / `thesis_state` / `opportunity_state` / `evidence_gaps` /
   `advisory_gaps` is byte-identical with vs without the ratios fragment present (the fragment is
   cosmetic reason text only).
9. **AC9 — no new citation / no citation-invariant change.** `KeyRatios` produces no `ThesisEvidence`
   and no `[ref:...]` marker. A test greps that the ratios reason fragment contains no
   `\[ref:[0-9a-f]{16}\]` token, and that `compute_ratios` returns no `ThesisEvidence`.
   SAME-3 / dual-coverage / H3 partition tests remain green.
10. **AC10 — filing-evidence-semantics respected.** The acceptance grep that forbids `revenue_yoy=`
    in production summaries stays green; the ratios fragment is not inserted into any
    `ThesisEvidence.summary`; the fragment carries the `口径未核实` caveat. The `基金概况`
    forbidden-indicator grep stays green (no new fund-profile fetch introduced).
11. **AC11 — determinism / byte-stability of the constituent surface.** Two runs over the same cached
    `FilingDigest` snapshot produce byte-identical `one_line_view` strings (the publishable-set
    lockdown / two-run byte-equality coverage stays green).
12. **AC12 — ADR recorded.** A new `docs/adr/0010-*.md` records the wire-but-degrade-to-`None`
    decision for `debt_equity` / `fcf_yield` (peer of ADR 0009) and the reason-only surface choice,
    and CONTEXT.md gains a `KeyRatios` glossary entry.
13. **AC13 — size + TDD budget.** New code lives in files <200 lines, functions <20 lines (ideal);
    every behaviour landed red-first (test precedes implementation); ratios tests mirror source
    (`ratios.py` → `tests/fundamentals/test_ratios.py`).

## Non-goals (explicit)

- **No LLM.** `compute_ratios` and the reason helper are deterministic pure functions; no task is
  added to `config/llm.yaml`.
- **No trading signal.** No factor, score weight, backtest, ranking, or buy/sell input. (Scope
  boundary — A-share quant lives in `ashare-quant`.)
- **No new state classifier and no change to existing states.** `valuation_state`, `thesis_state`,
  `product_quality_state`, `heat_state`, `opportunity_state` are untouched. `valuation_state` does
  NOT gain a ratios input (it took its fundamental anchor in item 002 via `consensus_upside_pct`).
- **No change to Policy B publishability or `thesis_state` derivation** (ADR 0003 invariant).
- **No `core_dca` / `cheap-AND-intact` gate change.**
- **No scope-creep fetchers.** Item 004 adds only the `roe` extraction from the *already-fetched*
  `stock_financial_abstract` frame. It does NOT add balance-sheet (total debt, equity), cash-flow
  (operating CF, capex, FCF), or market-cap fetchers. Those are deferred to a future item (likely
  alongside item 003's Tushare point-in-time feed), at which point `debt_equity` / `fcf_yield`
  self-activate with no further wiring.
- **No HK / US ratio path in V1.** `compute_ratios` is defined over the CN `FilingDigest` shape;
  `hkex_client` / `edgar_client` digests are out of scope (they do not carry `净资产收益率`). If a
  HK/US digest is passed, ratios degrade to `None` gracefully (no crash).
- **No new opportunity-row field.** Ratios surface only through the existing `one_line_view` /
  reason text; no new `OpportunityRow` / `ThesisCard` field is added.

## Constraints (enforced)

- **TDD** red→green→refactor; test file mirrors source.
- **Functional / immutable.** `compute_ratios` and the reason helper are pure; `KeyRatios` and
  `FilingDigest` are frozen dataclasses (the `roe` addition keeps `FilingDigest` frozen and is a
  defaulted field so existing call sites/cache files re-hydrate without churn).
- **Effects at edges.** The only new effect is the `净资产收益率` extraction inside
  `fetch_cn_filing_digest` (already an I/O wrapper); `compute_ratios` itself is pure.
- **Size budget.** Files <200 lines, functions <20 lines (ideal).
- **Citation ID** 16 hex unchanged; `compute_ratios` introduces no citation. `\[ref:[0-9a-f]{16}\]`
  contract untouched.
- **`基金概况` forbidden** — no new fund-profile fetch; the grep acceptance test stays green.
- **Filing-evidence-semantics addendum** (ADR 0001 §5) — ratios are caveated reason text
  (`口径未核实`), never endorsed performance, never inlined as a raw scalar in a citation summary.
- **Secrets in `.env` only** — N/A (no new I/O / credentials).

## Open questions resolved during brainstorming

All recorded in the **Decisions** table above (D1–D9). Summary of the load-bearing ones:

- **Input = existing `FilingDigest`** (not new fetchers); add one `roe` field from already-fetched
  data; `debt_equity` / `fcf_yield` degrade to `None` today (D1, D2, D4).
- **All ratio units, `float | None`** (D3).
- **Reason-only surface, no state/gate** (D5).
- **No citation, no `ThesisEvidence`** (D6); filing-evidence posture preserved (D7).
- **New `ratios.py` + ADR 0010 + CONTEXT.md entry** (D8).
- **`KeyRatios` frozen dataclass** realises the `{roe, ...}` return (D9).

## Could-not-fully-resolve (grill targets)

- **G1 — return shape: frozen dataclass vs literal `dict`.** The master-spec row writes
  `compute_ratios(financials) -> {roe, debt_equity, gross_margin, fcf_yield}`. I chose a frozen
  `KeyRatios` dataclass (immutability + explicit contract; project convention). If the planner wants
  the literal `dict[str, float | None]` form, that is a one-line change — grill to confirm.
- **G2 — exact surface attachment point.** Reason-only is decided (D5), but *which* string: the
  per-constituent `_one_line_view` (≤60-char, human-only) vs the `OpportunityInput` /
  `valuation_fundamental` reason path (fund-level, like pe/pb). I lean `_one_line_view` because the
  ratios are per-constituent (a fund has N constituents, each with its own ROE), whereas pe/pb were
  index-level. Confirm in the plan/grill that the ≤60-char budget can absorb a ratios fragment (may
  require raising the cap or truncating the broker/news fragment) — flagged as an implementation
  detail, not a design risk.
- **G3 — `roe` period alignment.** `净资产收益率` for a Q1 column is a quarterly (not annualised)
  ROE; surfacing it next to an annual gross margin could mislead. Mitigation: the `口径未核实` caveat
  + showing the `fiscal_period` already present in `one_line_view`'s filing fragment. Confirm whether
  the caveat is sufficient or whether ROE should be suppressed for non-FY periods (grill).
- **G4 — should `debt_equity` / `fcf_yield` appear in the fragment at all today?** They are always
  `None` now, so AC7's "emit only non-None sub-fields" means they never render — effectively the
  fragment shows ROE + gross margin only until item 003. Confirmed acceptable (honest, self-activating)
  but worth a one-line grill check that an all-`None`-pair fragment reading "ROE / 毛利率 only" is the
  intended V1 surface.
