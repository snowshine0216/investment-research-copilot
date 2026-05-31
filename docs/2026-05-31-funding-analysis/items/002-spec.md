# Item 002 — Fundamental `valuation_state` + `core_dca` cheap-AND-intact gate

> Run: `funding-analysis` · Source: `docs/funding-analysis-review.md` → "## Recommended changes" #2
> Status: spec · Authored 2026-05-31 (autonomous run, no user — decisions made and recorded below)
> Depends on: item 001 (MERGED, PR #84). 002 is the FIRST CONSUMER of the inputs 001 wired.

## Goal

Item 001 populated `OpportunityInput.pe_ttm` / `pb` / `dividend_yield` / `consensus_upside_pct`
but proved (via an inertness regression lock) that **no state classifier reads them** — they
are live data on a dead wire. Item 002 makes the **valuation axis** consume a *fundamental*
signal in addition to the existing price/percentile band, and tightens the `core_dca` gate so a
position is only nominated for core dollar-cost-averaging when it is **cheap AND its thesis is
intact** — never on a cheap percentile alone when a fundamental signal contradicts it. Concretely:
(a) `classify_valuation` gains a pure equity **valuation-fundamental anchor** that, mirroring the
existing `earnings_yield`/`real_yield_10y` anchor, layers `consensus_upside_pct` (and, where a
defensible peer-relative reading exists, pe/pb) onto the percentile-derived state as a
*reason annotation* and a *one-notch state adjustment in the cheap direction only when corroborated*;
and (b) `compose_opportunity_state` gains an explicit cheap-AND-intact precondition for `core_dca`
that additionally refuses core_dca when the fundamental valuation signal says the instrument is
*not* genuinely cheap (a strongly negative consensus upside). Because every new input degrades to
`None` in production until item 003 wires Tushare (ADR 0009), the **default behaviour with all
fundamental inputs `None` must be byte-identical to today** — the change is dormant until data
arrives, exactly like the `earnings_yield` anchor was dormant before its inputs were populated.

## Context grounding (verified, not assumed)

- **`classify_valuation` is the sole valuation classifier** (`opportunity/states.py:188`). It reads
  `valuation_percentile_self` → `valuation_percentile_vs_benchmark` (via `_percentile`), branches
  bonds to `classify_bond_valuation`, and for equities appends an `earnings_yield - real_yield_10y`
  **reason-only** caveat when the state is `expensive`/`very_expensive` (`states.py:218-232`). The
  caveat *never* changes `state` — verified by `tests/opportunity/test_earnings_yield_anchor.py`
  (`test_classify_valuation_appends_*`). This is the exact precedent item 002 follows.
- **`pe_ttm`/`pb`/`dividend_yield`/`consensus_upside_pct` have no non-test reader** today
  (CONTEXT.md "Valuation-input inertness"; 001 grill Q3 + AC4 inertness lock). Item 002 is the
  change that removes the inertness lock's premise — so item 002 **must update / retire** that
  lock, not leave it asserting a now-false invariant (see AC7).
- **`core_dca` is composed, not classified.** `compose_opportunity_state` (`states.py:388`) already
  requires `cheap_or_low AND quiet_heat AND intact_thesis AND decent_product` for `core_dca`
  (`states.py:410-411`). "cheap-AND-intact" is therefore *partly present already*; item 002 makes
  the cheap precondition **fundamental-aware** (a contradicting fundamental signal blocks core_dca)
  and locks the gate with explicit tests. `derive_contributing_dimensions` (`states.py:423`) mirrors
  `compose_opportunity_state`'s branches and MUST stay in lock-step (the core_dca branch returns all
  four dims — unchanged).
- **`valuation_state` is NOT a citation and NOT thesis_state.** It is a plain `Literal` field on
  `OpportunityRow` (`types.py:155`), threaded into `ThesisCard`/picks-table/discipline for display
  and DCA-rhythm derivation. It carries no `citation_id`/`scope`/`citation_kind`. `thesis_state` is
  set **exclusively** by `derive_thesis_from_evidence` (CONTEXT.md Policy B entry; ADR 0003).
- **`consensus_upside_pct` is ratio units** (`0.12` = +12%; CONTEXT.md "Valuation inputs"), matching
  `qdii_premium_pct`. Item 002 must read it as a ratio, never as percent.
- **`_broker_consensus`** (rating sentiment, information-leg) is a *different* axis from
  `consensus_upside_pct` (price-target valuation scalar). Item 002 touches only the latter.

## Acceptance criteria

Each is independently verifiable.

1. **New pure fundamental-valuation anchor.** A pure helper in `src/irc/opportunity/states.py`
   — `valuation_fundamental_signal(inp: OpportunityInput) -> Literal["cheap","rich","neutral",None]`
   (or an equivalently-typed `Enum`/`str|None`) — returns:
   - `"cheap"` when `consensus_upside_pct is not None and consensus_upside_pct >= CHEAP_UPSIDE_THRESHOLD`;
   - `"rich"` when `consensus_upside_pct is not None and consensus_upside_pct <= RICH_UPSIDE_THRESHOLD`;
   - `"neutral"` when `consensus_upside_pct` is present but between the thresholds;
   - `None` when `consensus_upside_pct is None` (the production-today case).
   Thresholds are module-level named constants (`CHEAP_UPSIDE_THRESHOLD = 0.20`,
   `RICH_UPSIDE_THRESHOLD = -0.10`; rationale recorded in Open Questions). The helper is **pure, no
   I/O**, unit-tested for each of the four branches plus the `None` (no-data) branch. pe/pb are
   **NOT** thresholded absolutely (see Open Q3); the helper consumes only `consensus_upside_pct` for
   the state-affecting decision, and pe/pb participate only in the reason annotation (AC3).

2. **`classify_valuation` reason annotation for equities.** For equity asset classes
   (`_EQUITY_ASSET_CLASSES`) only, when `valuation_fundamental_signal(inp)` is not `None`,
   `classify_valuation` **appends** a Chinese caveat phrase to `reason` describing the fundamental
   read (e.g. consensus upside / pe / pb), analogous to the existing earnings-yield phrase. Bonds
   (`_BOND_ASSET_CLASSES`) and any non-equity class are unaffected. A test asserts: equity with
   `consensus_upside_pct=0.25` gets a "便宜/上行空间" phrase appended; bond class with the same field
   set gets **no** phrase (mirrors `test_classify_valuation_does_not_append_phrase_for_bond_class`).

3. **State adjustment is one-notch, cheap-direction, corroboration-only.** `classify_valuation` may
   move the percentile-derived `state` **at most one notch toward cheaper** (e.g. `reasonable_low →
   cheap`) and **only** when `valuation_fundamental_signal(inp) == "cheap"` AND the percentile path
   already says `cheap`/`reasonable_low` (corroboration, never override). It must **never** move a
   state toward more-expensive, never promote `fair`/`expensive`/`very_expensive` to cheap, and never
   change state when the fundamental signal is `None`. Tested: (a) percentile `reasonable_low` +
   `"cheap"` signal → `cheap`; (b) percentile `fair` + `"cheap"` signal → `fair` (no jump); (c)
   percentile `expensive` + `"rich"` signal → `expensive` (no further move, reason annotated only);
   (d) any state + `None` signal → identical to today. pe/pb are never load-bearing for the notch.

4. **`core_dca` gated on cheap-AND-intact, fundamental-aware.** `compose_opportunity_state` keeps its
   existing `cheap_or_low AND quiet_heat AND intact_thesis AND decent_product` precondition AND adds:
   core_dca is refused when a **fundamental valuation contradiction** is present — i.e. the new pure
   predicate `fundamental_blocks_core_dca(inp)` returns `True` (the fundamental signal is `"rich"`
   while the percentile path says cheap). Because `compose_opportunity_state` currently takes only the
   four sub-states + `venue_compatible`, the fundamental-block signal is threaded in **without
   widening the citation/partition surface** — either by passing a `valuation_fundamental:
   Literal[...]|None` parameter (default `None`, so all existing callers/tests stay green) or by
   computing the block inside `classify_valuation` and refusing the cheap notch (so the composer needs
   no new parameter). The chosen mechanism is recorded in Open Q4. Tested: cheap+cold+intact+strong
   with `consensus_upside_pct=None` → `core_dca` (unchanged); same row with `consensus_upside_pct=-0.30`
   (`"rich"`) → NOT `core_dca` (falls to `small_watch`/`pause_wait` per existing fallthrough), with a
   reason naming the valuation contradiction.

5. **Bonds, gold, QDII, active funds untouched.** The fundamental anchor and core_dca block apply to
   `_EQUITY_ASSET_CLASSES` only. A test sets `consensus_upside_pct` on a `cn_bond_fund` /
   `gold` row and asserts `classify_valuation` and `compose_opportunity_state` outputs are
   byte-identical to today (bond path is yield-percentile-anchored; gold/QDII have no equity
   fundamentals). This protects the bond-valuation invariant (`classify_bond_valuation`).

6. **Degrade-to-None / dormant-by-default lock.** A regression test asserts that for a representative
   set of rows where **all** fundamental inputs (`pe_ttm`/`pb`/`dividend_yield`/`consensus_upside_pct`)
   are `None` — the production-today case — `classify_valuation(inp)` and `build_opportunity_row(inp,…)`
   produce **byte-identical** `valuation_state`, `opportunity_state`, `opportunity_reason`, and
   `contributing_dimensions` to the pre-item-002 outputs. This is the ADR-0009 honesty contract made
   testable at the state layer: item 002 is inert until item 003 supplies data.

7. **Retire/replace the item-001 inertness lock.** The item-001 AC4 "inertness regression lock"
   (which asserts `classify_valuation` output is byte-identical for a *populated* row) becomes **false
   by design** in item 002 (a populated `consensus_upside_pct` may now annotate the reason / adjust the
   notch). Item 002 **must update that test** to assert the new, intentional behaviour (populated
   inputs now flow into the reason/state per AC2/AC3) rather than deleting coverage — and must leave a
   comment pointing at this spec + ADR 0009. No silent deletion; the diff must show the lock evolving
   from "inert" to "consumes fundamentals as specified."

8. **No citation / partition / Policy-B / thesis_state change.** Grep-level invariants hold:
   `valuation_state` remains a plain `Literal` with no `scope`/`citation_id`/`citation_kind`; the H3
   partition predicate stays `evidence_gaps == ()`; SAME-3 citation-set equality is untouched (no new
   `ThesisEvidence` emitted); `derive_thesis_from_evidence` remains the sole writer of `thesis_state`;
   Policy B (`evaluate_policy_b`) is not read or written by any item-002 code path. A test or
   structural assertion confirms no new `ThesisEvidence` row is produced by the valuation path.

9. **No-network correctness + budgets.** `uv run pytest tests/opportunity` passes; `uv run ruff check
   src tests` is clean. `states.py` stays under the 200-line budget (extract helpers if the anchor
   pushes it over — `valuation_fundamental_signal` and `fundamental_blocks_core_dca` are small pure
   functions); new functions stay under the ~20-line ideal.

## Non-goals (explicit)

- **NO trading signals.** No buy/sell/backtest/factor/transaction-cost logic. The fundamental anchor
  feeds the existing *DCA-discipline* `valuation_state`/`core_dca` axis only (that belongs to IRC; the
  trading line lives in `ashare-quant` — MASTER-SPEC "Out of scope").
- **NO new fetchers / no Tushare.** Item 002 does not change `populate_inputs`, any AkShare adapter,
  or `settings.py`. Supplying target-price data so `consensus_upside_pct` becomes non-`None` in
  production is **item 003**. Item 002 consumes whatever 001 populated and degrades to today's
  behaviour when it is `None`.
- **NO change to Policy B or `thesis_state` derivation.** `valuation_state` is a separate axis; it
  must not leak into `thesis_state` (owned by `derive_thesis_from_evidence`) or into Policy B
  publishability (ADR 0003). The "intact" half of the core_dca gate reads the **existing**
  `thesis_state == "intact"`; item 002 does not redefine intactness.
- **NO new `ThesisEvidence` / citation emission.** pe/pb/upside stay plain numeric inputs; the 16-hex
  citation contract (ADR 0001), dual-coverage gate, SAME-3, H3, and `select_citations` are untouched.
- **NO `key_ratios` / ROE / debt-equity** (item 004) and **no bull/bear debate** (item 005).
- **NO absolute pe/pb cheapness threshold.** Absolute pe/pb is not comparable across the equity/ETF/
  QDII universe without a peer or self-history percentile context that IRC does not yet compute; pe/pb
  inform only the *reason* string, never the state (Open Q3).

## Constraints

- **TDD red→green→refactor.** Each AC is driven by a failing test first; test files mirror source
  (`tests/opportunity/test_states.py` and a new focused test module for the fundamental anchor, e.g.
  `tests/opportunity/test_valuation_fundamental_anchor.py`).
- **Purity / effects at edges.** `valuation_fundamental_signal`, `fundamental_blocks_core_dca`, the
  reason-annotation helper, and `classify_valuation`/`compose_opportunity_state` stay **pure** —
  no I/O, no mutation. They are unit-tested without mocks.
- **Immutability.** No argument mutation; any derived `OpportunityRow`/state is built fresh (frozen
  dataclasses, `dataclasses.replace` where a new instance is needed). `compose_opportunity_state`
  continues to return a new `(state, reason)` tuple.
- **Size budget.** `states.py` < 200 lines; new functions < 20 lines ideal — extract helpers rather
  than nest > 3 levels. If `states.py` would exceed budget, the anchor helpers may live in a small new
  `src/irc/opportunity/valuation_fundamental.py` module imported by `states.py`.
- **Citation 16-hex untouched.** No `ThesisEvidence` emitted; the `\[ref:[0-9a-f]{16}\]` contract
  (ADR 0001) is not exercised by this item.
- **Forbidden indicator.** `基金概况` is not referenced (no fetch code touched); the acceptance grep
  test stays green.
- **Degrade-to-None.** Every new code path treats `None` fundamental inputs as "no opinion" and
  reproduces today's behaviour exactly (ADR 0009 honesty contract — the metric is dormant, not broken).
- **No live tests added.** Item 002 is pure logic over already-populated inputs; it adds no AkShare/
  network call, so no `pytest.mark.live_*` gating is needed.

## Open questions resolved during brainstorming

Autonomous run (no user). Each recommendation auto-accepted; rationale grounded in code + CONTEXT.md +
ADRs. These are the grill-phase re-check targets.

1. **Should the fundamental signal REPLACE the percentile band or AUGMENT it?**
   **Decided: augment (anchor), never replace.** Rationale: the percentile band is the load-bearing,
   always-available valuation signal; `consensus_upside_pct` is `None` in production until item 003,
   so a replacement design would make `valuation_state` collapse to `evidence_insufficient` for every
   equity today — a regression. The codebase already has the exact precedent: the `earnings_yield`
   anchor *annotates* without changing state. Item 002 follows it, adding a strictly-bounded one-notch
   cheap-direction adjustment only under corroboration (AC3). This keeps the change dormant-by-default
   and preserves the degrade-to-None contract (ADR 0009).

2. **What does "cheap" mean fundamentally, and at what thresholds?**
   **Decided: cheap = consensus upside ≥ +20% (`CHEAP_UPSIDE_THRESHOLD = 0.20`); rich = consensus
   upside ≤ −10% (`RICH_UPSIDE_THRESHOLD = -0.10`).** Rationale: `consensus_upside_pct` is the one
   fundamental valuation scalar IRC can obtain honestly (once item 003 lands) and it is *already
   relative* (price vs analyst target), so it needs no peer/history normalisation — unlike absolute
   pe/pb. +20% is a conventional "material upside" bar for treating a price as cheap vs consensus;
   −10% (asymmetric, tighter) flags meaningful *downside* to target so the gate errs conservative
   (a DCA system should be slow to call something cheap and quick to withhold the cheap label). Both
   are named module constants so the grill / future tuning can move them in one place. Units are ratio
   (CONTEXT.md), not percent.

3. **Do pe_ttm / pb participate in the STATE decision, or only the reason?**
   **Decided: reason only; pe/pb never change the state.** Rationale: 001 populates pe/pb at the
   **index level** (`stock_index_pe_lg`/`pb_lg`) with no self-history or peer percentile attached — an
   absolute pe of, say, 12 is "cheap" for a bank index and "expensive" for a growth index. Threshold-
   ing absolute pe/pb across IRC's mixed CN/HK/US-QDII universe would be unsound and is exactly the
   kind of per-instrument-percentile work the 001 spec deferred. So pe/pb enrich the human-readable
   reason ("指数 PE x.x / PB x.x") but are kept out of the state machine until a percentile context
   exists. This keeps item 002 honest and avoids smuggling in a half-baked cross-asset comparator.

4. **How is the fundamental block threaded into `compose_opportunity_state` without widening the
   partition/citation surface?**
   **Decided: refuse the cheap notch inside `classify_valuation` AND add a defensive explicit guard
   in `compose_opportunity_state` via an optional defaulted parameter.** Rationale: the cleanest,
   lowest-blast-radius path is to let the fundamental contradiction (`"rich"` signal) prevent
   `classify_valuation` from ever *reporting* cheap/reasonable_low for that equity — which
   automatically removes core_dca eligibility through the existing `cheap_or_low` precondition, with no
   composer signature change. To make the gate explicit and grill-defensible we ALSO add an optional
   `valuation_fundamental: Literal[...] | None = None` parameter to `compose_opportunity_state` whose
   default keeps every existing call/test byte-identical; `build_opportunity_row` passes the computed
   signal. This is belt-and-suspenders: the state itself already encodes the block, and the explicit
   parameter documents it and lets `derive_contributing_dimensions` stay correct. Neither path adds any
   `ThesisEvidence`, `scope`, `citation_id`, or `evidence_gaps` — so H3 partition, SAME-3 equality,
   dual-coverage, and Policy B are structurally untouched (re-confirmed in AC8).

5. **Does adding a fundamental `valuation_state` input affect H3 / SAME-3 / the opportunity partition
   or citation-set equality?**
   **Decided: NO — structurally untouched.** Rationale: `valuation_state` is a plain `Literal` on
   `OpportunityRow` with no citation provenance; H3 partitions on `evidence_gaps == ()` ONLY (CONTEXT.md
   H3 entry) and item 002 emits no new gap code; SAME-3 is set-equality over `select_citations`
   output and item 002 emits no new `ThesisEvidence`. A different `valuation_state` value changes the
   *reason text* and possibly `opportunity_state`/`dca_action` (display + rhythm), none of which are
   citation IDs. Locked by AC8. (This mirrors 001 grill Q2, which already established the scalars carry
   no citation surface.)

6. **What does `valuation_state` classify to when pe_ttm/pb AND consensus_upside_pct are all None
   (the common case until item 003)?**
   **Decided: exactly today's percentile-derived state — the fundamental anchor is `None`/no-opinion
   and contributes nothing.** Rationale: ADR 0009 — the metric is wired but evaluates to `None` in
   production; AC6 makes "all-None ⇒ byte-identical to pre-002" a hard regression lock. `valuation_state`
   only becomes `evidence_insufficient` for the *existing* reason (no percentile at all), never because
   the new fundamental inputs are missing. Missing fundamentals must NEVER push a row toward
   `evidence_insufficient` or emit a gap — that would change publishability for the common case and
   violate the degrade-to-None contract.

7. **Must the item-001 inertness regression lock be touched?**
   **Decided: yes — update it, do not delete it (AC7).** Rationale: 001's AC4 lock asserts a *populated*
   row's `classify_valuation` output is byte-identical to pre-001. Item 002 *intentionally* makes a
   populated `consensus_upside_pct` flow into the reason/state, so that assertion is now false **by
   design**. Leaving it would either fail CI or force item 002 to no-op. The correct move is to evolve
   the test to assert the new specified behaviour (populated → annotated/adjusted per AC2/AC3) and the
   all-None dormancy (AC6), with a comment pointing at this spec + ADR 0009. Silent deletion would lose
   the boundary coverage the 001 grill deliberately added.

8. **Is a new ADR warranted (three-of-three bar)?**
   **Decided: no new ADR; extend the record in this spec + a one-line CONTEXT.md update to the
   "Valuation-input inertness" entry noting item 002 lifted the inertness.** Rationale, scored:
   *adding a pure anchor + reason annotation* → 0/3 (reversible, unsurprising, no real trade-off).
   *one-notch corroboration-only state adjustment + fundamental core_dca block* → ~2/3 at most (it is a
   direct, bounded consequence of ADR 0009's "metric activates automatically when data lands" — not a
   new architectural decision; reversible by reverting the helper; the alternative designs were
   considered here in Open Q1–Q4). It does not clear the 3/3 bar that warranted ADR 0009 (that ADR
   already owns the honesty/degrade-to-None decision this item *consumes*). So: no ADR 0010; instead
   update CONTEXT.md "Valuation-input inertness" to state that item 002 wired `consensus_upside_pct`
   into `classify_valuation`/`core_dca` per this spec, and that pe/pb remain reason-only. If the grill
   judges the core_dca-gating to be load-bearing enough for its own ADR, that is the single open
   escalation.

## Could-not-fully-resolve (grill targets)

- **Exact threshold values** (`0.20` / `-0.10`) are best-judgment, not validated against a labelled
  dataset (none exists in-repo). They are isolated as named constants so the grill can challenge/move
  them without touching logic. Not a blocker — any value preserves the all-None dormancy lock (AC6).
- **Whether the explicit `compose_opportunity_state` parameter (Open Q4 belt-and-suspenders) is worth
  the signature change** vs relying solely on the `classify_valuation` notch-refusal. Both satisfy the
  ACs; the grill should confirm the preferred mechanism so the plan picks exactly one and
  `derive_contributing_dimensions` is kept consistent.
