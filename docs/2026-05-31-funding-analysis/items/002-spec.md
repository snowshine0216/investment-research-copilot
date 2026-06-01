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
   core_dca is refused when a **fundamental valuation contradiction** is present (the fundamental
   signal is `"rich"` while the percentile path says cheap).
   ~~i.e. the new pure predicate `fundamental_blocks_core_dca(inp)` returns `True`~~ — corrected by
   grill (Q-T2): no standalone `fundamental_blocks_core_dca` predicate is added; the block is the
   `valuation_fundamental == "rich" AND cheap_or_low` test INSIDE `compose_opportunity_state` (see
   below).
   ~~Because `compose_opportunity_state` currently takes only the four sub-states + `venue_compatible`, the fundamental-block signal is threaded in **without widening the citation/partition surface** — either by passing a `valuation_fundamental: Literal[...]|None` parameter (default `None`, so all existing callers/tests stay green) or by computing the block inside `classify_valuation` and refusing the cheap notch (so the composer needs no new parameter). The chosen mechanism is recorded in Open Q4.~~
   — **corrected by grill (Q-T2): the two proposed mechanisms are NOT interchangeable; the
   `classify_valuation`-notch-refusal mechanism CANNOT implement this AC and the explicit-parameter
   mechanism is the SINGLE chosen mechanism.** Rationale: AC3 forbids `classify_valuation` from ever
   moving a state toward more-expensive, so when the percentile path is genuinely `cheap`/`reasonable_low`
   a `"rich"` fundamental signal *cannot* be expressed by demoting the percentile state — that would
   violate AC3 and corrupt the `valuation_state` axis (a deeply cheap percentile is a true fact). The
   only correct place for the contradiction-block is therefore an **explicit gate in
   `compose_opportunity_state`**: add a `valuation_fundamental: Literal["cheap","rich","neutral"]|None
   = None` parameter (default `None` keeps every existing caller/test byte-identical); when it is
   `"rich"` AND `cheap_or_low` is `True`, the composer skips the `core_dca` branch and falls through to
   `small_watch`/`pause_wait`. `derive_contributing_dimensions` is updated **only** to keep its
   `core_dca`-branch in lock-step (it still returns all four dims for `core_dca`; the fundamental block
   only suppresses entry into that branch, so when `core_dca` is NOT reached the existing
   `small_watch`/`pause_wait` dimension logic already applies — no change needed there). `build_opportunity_row`
   computes `valuation_fundamental_signal(inp)` once and passes it to `compose_opportunity_state`.
   Tested: cheap+cold+intact+strong with `consensus_upside_pct=None` → `core_dca` (unchanged);
   same row with `consensus_upside_pct=-0.30` (`"rich"`) → NOT `core_dca` (falls to `small_watch`),
   `valuation_state` STAYS `cheap` (AC3-preserving), reason annotates the contradiction. Adds no
   `ThesisEvidence`/`scope`/`citation_id`/`evidence_gaps` — H3/SAME-3/Policy B structurally untouched.

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
   (`tests/opportunity/test_inputs_loader.py::test_population_is_inert_classify_valuation_byte_identical`,
   which asserts `classify_valuation(populated) == classify_valuation(bare)` for a *populated* row)
   becomes **false by design** in item 002. Item 002 **must update that test** to assert the new,
   intentional behaviour rather than deleting coverage — and must leave a comment pointing at this
   spec + ADR 0009. No silent deletion; the diff must show the lock evolving from "inert" to
   "consumes `consensus_upside_pct` as specified."
   ~~(a populated `consensus_upside_pct` may now annotate the reason / adjust the notch)~~
   — **corrected by grill (Q-T4): for THAT SPECIFIC test row the break is via the REASON ANNOTATION
   ONLY, not the notch.** The row's price series is flat (300 × 100.0), and `self_history_percentile`
   uses inclusive ranking (`count_le / len`), so its `valuation_percentile_self` is **1.0** →
   `classify_valuation` returns **`very_expensive`**, not cheap. Its `consensus_upside_pct` is
   `120/100 − 1 = 0.20` → `valuation_fundamental_signal == "cheap"`. AC3's one-notch adjustment fires
   ONLY when the percentile path is `cheap`/`reasonable_low`, so for a `very_expensive` row the notch
   NEVER fires; the lock breaks solely because AC2 appends the equity fundamental caveat to `reason`.
   Therefore the updated test must (i) assert the populated row's `reason` now contains the fundamental
   caveat while its `state` is unchanged at `very_expensive` (annotation-only), AND (ii) add a SECOND
   row with a genuinely cheap percentile (e.g. `valuation_percentile_self=0.10` + `consensus_upside_pct
   ≥ 0.20`) to exercise the AC3 one-notch corroboration and confirm `reasonable_low → cheap` /
   `cheap → cheap`. Provenance is preserved: the test stays in `test_inputs_loader.py`, keeps the
   guard `assert populated.pe_ttm is not None`, and the docstring + comment cite this spec + ADR 0009.

8. **No citation / partition / Policy-B / thesis_state change.** Grep-level invariants hold:
   `valuation_state` remains a plain `Literal` with no `scope`/`citation_id`/`citation_kind`; the H3
   partition predicate stays `evidence_gaps == ()`; SAME-3 citation-set equality is untouched (no new
   `ThesisEvidence` emitted); `derive_thesis_from_evidence` remains the sole writer of `thesis_state`;
   Policy B (`evaluate_policy_b`) is not read or written by any item-002 code path. A test or
   structural assertion confirms no new `ThesisEvidence` row is produced by the valuation path.

9. **No-network correctness + budgets.** `uv run pytest tests/opportunity` passes; `uv run ruff check
   src tests` is clean. `states.py` stays under the 200-line budget (extract helpers if the anchor
   pushes it over — `valuation_fundamental_signal` ~~and `fundamental_blocks_core_dca`~~ — corrected by
   grill (Q-T2): the block is an inline test inside `compose_opportunity_state`, not a separate
   predicate — plus the small reason-annotation helper are pure functions); new functions stay under
   the ~20-line ideal. If `states.py` would exceed budget, `valuation_fundamental_signal` + the
   reason-annotation helper may move to a small new `src/irc/opportunity/valuation_fundamental.py`.

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
- **Purity / effects at edges.** `valuation_fundamental_signal`, ~~`fundamental_blocks_core_dca`~~ (replaced by the inline composer test per Q-T2), the
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
   ~~**Decided: refuse the cheap notch inside `classify_valuation` AND add a defensive explicit guard in `compose_opportunity_state` via an optional defaulted parameter.** … This is belt-and-suspenders: the state itself already encodes the block …~~
   — **corrected by grill (Q-T2): the belt-and-suspenders framing is wrong. The two mechanisms are
   NOT both valid, and the `classify_valuation`-notch path CANNOT implement the block by itself.**
   When the percentile path is genuinely `cheap`/`reasonable_low`, AC3 forbids `classify_valuation`
   from moving the state toward more-expensive — so the `"rich"` signal cannot demote `cheap`→`fair`
   to break `cheap_or_low`. The notch mechanism can only ever ADD a cheap notch (or refuse to add
   one); it can never remove an existing cheap percentile state. Therefore the **explicit
   `compose_opportunity_state` parameter is the SINGLE chosen mechanism (not optional, not
   belt-and-suspenders).** `compose_opportunity_state` gains
   `valuation_fundamental: Literal["cheap","rich","neutral"] | None = None`; when `"rich"` AND
   `cheap_or_low`, it skips the `core_dca` branch → `small_watch`. The default `None` keeps all
   existing callers/tests byte-identical. `build_opportunity_row` computes the signal once and passes
   it. `derive_contributing_dimensions` is unchanged (the block only suppresses ENTRY into the
   `core_dca` branch; the resulting `small_watch`/`pause_wait` already has correct dimension logic).
   No `ThesisEvidence`/`scope`/`citation_id`/`evidence_gaps` added — H3/SAME-3/dual-coverage/Policy B
   structurally untouched (AC8).

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
   into `classify_valuation`/`core_dca` per this spec, and that pe/pb remain reason-only. ~~If the grill judges the core_dca-gating to be load-bearing enough for its own ADR, that is the single open escalation.~~
   — **confirmed by grill (Q-T3): no new ADR. The core_dca-gating scores ~1–2/3 (reversible; its only
   surprise — "a metric that never fires until data lands" — is already owned by ADR 0009; the design
   choices are bounded within ADR 0009's frame).** CONTEXT.md updated with `valuation_fundamental_signal`
   + `Fundamental-aware core_dca gate` terms and the amended `Valuation-input inertness` entry.

## Could-not-fully-resolve (grill targets)

- **Exact threshold values** (`0.20` / `-0.10`) are best-judgment, not validated against a labelled
  dataset (none exists in-repo). They are isolated as named constants so the grill can challenge/move
  them without touching logic. Not a blocker — any value preserves the all-None dormancy lock (AC6).
- ~~**Whether the explicit `compose_opportunity_state` parameter (Open Q4 belt-and-suspenders) is worth the signature change** vs relying solely on the `classify_valuation` notch-refusal. Both satisfy the ACs …~~ — **RESOLVED by grill (Q-T2): they do NOT both satisfy the ACs. The notch-refusal mechanism is incapable of blocking core_dca when the percentile is already cheap (AC3 forbids the demotion). The explicit composer parameter is the single, non-optional, load-bearing mechanism.** See revised AC4 and Open Q4 above.

## Resolved decisions

Q/A pairs from the grill-with-docs pass (2026-05-31, autonomous run — no user; each recommended
answer auto-accepted, grounded in code + CONTEXT.md + ADRs). Verdict: **PASS** (no spec ↔
load-bearing-ADR/code contradiction that doc updates cannot resolve). All facts below were verified
against `src/irc/opportunity/states.py`, `…/types.py`, `…/inputs_loader.py`, `…/returns.py`, and the
item-001 lock test, NOT taken from the spec's own claims.

- **Q-T1 — Are `CHEAP_UPSIDE_THRESHOLD=0.20` / `RICH_UPSIDE_THRESHOLD=-0.10` defensible defaults?**
  **A: Yes — pin as proposed.** +20% is a conventional "material upside vs analyst consensus" bar for
  treating a price as cheap; −10% is deliberately asymmetric/tighter so the DCA gate errs conservative
  (slow to call cheap, quick to withhold the cheap label). No labelled dataset exists in-repo, so they
  are best-judgment, isolated as module-level named constants so future tuning is a one-line change.
  Units are ratio (CONTEXT.md `consensus_upside_pct`), never percent. **Rationale:** matches the lone
  honestly-obtainable, already-relative fundamental valuation scalar; needs no peer/history
  normalisation (unlike absolute pe/pb). **Doc impact:** CONTEXT.md `valuation_fundamental_signal`.

- **Q-T2 — Threading mechanism: explicit composer parameter vs `classify_valuation` notch-refusal —
  pick exactly one.** **A: the explicit `compose_opportunity_state` parameter is the SINGLE,
  non-optional, load-bearing mechanism; it is NOT belt-and-suspenders.** **Rationale:** AC3 forbids
  `classify_valuation` from moving any state toward more-expensive. When the percentile path is
  genuinely `cheap`/`reasonable_low`, a `"rich"` fundamental signal therefore CANNOT be expressed by
  demoting the percentile state to break `cheap_or_low` — the notch mechanism can only add (or refuse
  to add) a cheap notch, never remove an existing cheap state. So the notch path is structurally
  incapable of blocking `core_dca` in exactly the case AC4 targets. The block must live in
  `compose_opportunity_state(valuation_fundamental: Literal[...] | None = None)`; default `None` keeps
  every existing caller byte-identical; `valuation_state` itself stays `cheap` (the percentile fact is
  true), only `opportunity_state` falls through to `small_watch`. **Doc impact:** CONTEXT.md
  `Fundamental-aware core_dca gate`; spec AC4 + Open Q4 + Could-not-fully-resolve corrected in place.

- **Q-T3 — ADR escalation: does the core_dca-gating clear the three-of-three bar?**
  **A: No new ADR. CONTEXT.md update suffices.** Scored: (1) hard-to-reverse — NO (pure helper +
  one-notch adjustment + an optional defaulted composer param; revert the helper to undo, no cache or
  artifact migration); (2) surprising-without-context — the "metric that never fires until data lands"
  surprise is ALREADY owned by ADR 0009; activation is its documented, expected consequence, not a new
  surprise; (3) real-trade-off — the augment-vs-replace and threading choices are bounded design calls
  *within* ADR 0009's frame, not a new architectural-shape decision. Net ~1–2/3, below the 3/3 bar.
  **Rationale:** ADR 0009 already records the honesty/degrade-to-None decision item 002 *consumes*; a
  sibling ADR would duplicate it. **Doc impact:** CONTEXT.md `valuation_fundamental_signal` +
  `Fundamental-aware core_dca gate` + amended `Valuation-input inertness` (no ADR 0010).

- **Q-T4 — Does the item-001 AC4 inertness lock break "by design" via the NOTCH, as the spec claimed?**
  **A: No — for that specific test row it breaks via the REASON ANNOTATION only; AC7 must be corrected
  and a second cheap-percentile row added.** **Rationale:** the lock row (`510300`/csi300) seeds a flat
  300×100.0 price series; `self_history_percentile` uses inclusive ranking (`count_le/len`), giving
  percentile **1.0** → `classify_valuation` returns **`very_expensive`**, never cheap. Its
  `consensus_upside_pct` is `120/100−1 = 0.20` → signal `"cheap"`, but AC3's notch fires only on a
  `cheap`/`reasonable_low` percentile, so the notch NEVER fires here — the byte-difference is purely
  AC2's appended equity caveat. The updated test must assert annotation-only on this row AND add a
  genuinely-cheap-percentile row to exercise the AC3 corroboration notch. Provenance preserved (stays
  in `test_inputs_loader.py`, keeps the population guard, cites spec + ADR 0009). **Doc impact:** spec
  AC7 corrected in place.

- **Q-T5 — Do the load-bearing invariants (H3/SAME-3, Policy B vs thesis_state, all-None degrade)
  hold?** **A: Yes — verified against code; spec respects all four.** (a) H3 partitions on
  `evidence_gaps == ()` ONLY; item 002 emits no gap code → partition unchanged. (b) SAME-3 is set
  equality over `select_citations(row.thesis_evidence)`; item 002 emits no `ThesisEvidence` → equality
  untouched. (c) `thesis_state` is set EXCLUSIVELY by `derive_thesis_from_evidence`; `valuation_state`
  is a separate `Literal` axis and `compose_opportunity_state` never writes `thesis_state`; Policy B
  (`evaluate_policy_b`) is neither read nor written by any item-002 path — `valuation_state` cannot
  leak into thesis_state or publishability. (d) All-None degrade: with `consensus_upside_pct is None`,
  `valuation_fundamental_signal` returns `None`, no annotation/notch fires, and the composer parameter
  defaults `None` → `classify_valuation`/`build_opportunity_row` are byte-identical to pre-002 (AC6
  dormancy lock holds; `valuation_state` becomes `evidence_insufficient` only for the EXISTING reason,
  a missing percentile — never because fundamentals are absent). **Doc impact:** none beyond AC8's
  existing assertions (confirmation only).

- **Q-T6 — Augment vs replace; do pe/pb participate in the state?** **A: augment-only anchor, never
  replace; pe/pb are reason-only and never change the state — confirmed.** **Rationale:** the
  percentile band is the always-available load-bearing signal; `consensus_upside_pct` is `None` in
  production, so a replacement design would collapse every equity `valuation_state` to
  `evidence_insufficient` today (a regression). The `earnings_yield` anchor is the exact precedent
  (annotate, never change state). pe/pb are populated at index level with no self-history/peer
  percentile context (item 001), so absolute thresholding across the mixed CN/HK/US-QDII universe
  would be unsound — they enrich the reason only. **Doc impact:** CONTEXT.md `valuation_fundamental_signal`.
