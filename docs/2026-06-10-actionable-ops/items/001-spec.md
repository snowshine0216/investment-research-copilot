# Item 001 — Sell surfacing + holdings-aware deltas

Run: `actionable-ops` (backlog). Branch: `autodev/actionable-ops-feature`.
Status: spec. MASTER-SPEC row 001 ("IN").

## Goal

The daily/weekly decision report (`decision_report.md` + `decision_report.json`)
must tell the operator not only what to **BUY** but what to **TRIM / EXIT /
REVIEW** on instruments they actually hold, with a concrete current-vs-target
weight delta so each action is actionable. Today the discipline layer already
derives sell-side signals (`risk_action ∈ {none, review_required, trim_review,
exit_review}`, holding-aware via `is_holding`), but they die inside
`discipline_report.md` (markdown only) and never reach the decision layer:
`opportunity_report.json` rows omit `risk_action`/`dca_action`/`portfolio_weight`,
and `src/irc/decision/gates.py:191` hard-codes `portfolio_action="no_trade"` for
every row (`PortfolioAction = Literal["no_trade"]`, `models.py:14`). This item
threads holdings → current weight → target-weight delta → a real
`portfolio_action` into the decision row, adds a Sell/Trim/Review section to the
report, and emits machine-readable summary counts that item 002's notifier will
consume.

## Approach (chosen)

**Surface existing signals through `opportunity_report.json`, map them in the
decision layer.** Three candidate approaches were weighed (see Open Questions
OQ1):

- **A — re-run discipline inside decision.** Rejected: duplicates the
  opportunity stage's snapshot/Policy-B machinery and risks divergent
  `risk_action`, violating single-source-of-truth.
- **B (chosen) — extend `opportunity_report.json` rows with the
  already-derived `risk_action` / `dca_action` / `portfolio_weight` /
  `is_holding`, then have the decision layer read and map them.** The discipline
  data exists at `_write_opportunity_outputs` time (`positions[iid]` +
  `_discipline_row_from`). The decision command already reads
  `opportunity_report.json` (`_read_opportunity_state_by_id`). No new I/O wiring.
- **C — new `discipline_report.json` artifact.** Rejected as gold-plating: adds
  a parallel artifact + write path when the existing report already carries the
  publishable-row set the decision layer needs. (May be revisited if a future
  item needs the full per-constituent discipline payload machine-readable.)

Vertical slice (the coherent unit this item delivers):
`holdings → current weight → target delta → portfolio_action emission → report
section + JSON summary counts`.

### Data flow

```
inputs/account.yaml holdings ──(existing)──▶ OpportunityInput.is_holding/portfolio_weight
                                                   │
                              PositionContext ──▶ derive_risk_action ──▶ risk_action
                                                   │
opportunity_report.json row  ◀── NEW: risk_action, dca_action, portfolio_weight, is_holding
                                                   │
proposed_allocation.yaml target_weight ──┐         │
                                          ▼         ▼
                            decision layer: map_portfolio_action(risk_action, score_action,
                                              allocation_selected) + weight_delta(current, target)
                                                   │
                            DecisionRow.portfolio_action / current_weight / target_weight / weight_delta
                                                   │
                            ┌──────────────────────┼─────────────────────────────┐
                            ▼                       ▼                             ▼
              decision_report.md                decision_report.json        decision_report.json
              "## 持仓行动 / Sell·Trim·Review"   rows[*].portfolio_action     summary.{trim,exit,review}_count
```

### Component changes (each unit single-purpose, files < 200 lines)

1. **`src/irc/opportunity/report.py` — `_row_to_dict` + `compose_opportunity_report`**: add four keys to the
   emitted row dict: `risk_action`, `dca_action`, `portfolio_weight`,
   `is_holding`. No
   change to thesis_cards / discipline markdown / SAME-3 citation set.
   ~~Pure; the derived discipline values are passed in (see #2).~~ **CORRECTED
   (R1):** `OpportunityRow` does NOT carry `risk_action`/`dca_action`
   (those live on `DisciplineRow`/`ThesisCard`, `types.py:194/215`) nor
   `portfolio_weight`/`is_holding` (those are on `OpportunityInput`/`PositionContext`,
   `types.py:79-80` / `discipline.py:11-17`), so `_row_to_dict(row)` cannot reach
   them as written. `compose_opportunity_report` therefore gains a keyword param
   `discipline_by_id: dict[str, …] | None = None` (default `None` ⇒ keys emit as
   `risk_action="none"`, `dca_action=None`, `portfolio_weight=None`,
   `is_holding=False`, byte-identical to today for every legacy/test caller —
   satisfies the public-API-stability constraint), and `_row_to_dict` looks the
   row's values up by `instrument_id`.

2. **`src/irc/commands/opportunity_cmd._write_opportunity_outputs`**: build the
   `discipline_by_id` map from the per-row `risk_action`/`dca_action` (from the
   discipline rows already built at lines 1254/1280) and `portfolio_weight`/`is_holding`
   (from `positions[iid]`), keyed by `instrument_id`, and pass it into
   `compose_opportunity_report(publishable_rows, today, discipline_by_id=…)`
   (call site `opportunity_cmd.py:1373`). Effects-at-edges: command layer only
   threads data; the composition function stays pure.

3. **`src/irc/decision/models.py`**: widen `PortfolioAction` to
   `Literal["no_trade", "buy", "trim_review", "exit_review", "review"]`; widen
   `DecisionStatus` to add `"review_sell_later"` (removing the Phase-3 TODO at
   `models.py:12`). Add three optional `DecisionRow` fields:
   `current_weight: float = 0.0`, `weight_delta: float = 0.0`, and reuse the
   existing `target_weight`. (`asdict` already serializes them.)

4. **`src/irc/decision/portfolio_action.py` (new, pure, < 60 lines)**: a single
   pure function `map_portfolio_action(*, risk_action, score_action,
   allocation_selected, is_holding, blocking_reasons) -> PortfolioAction` plus
   `weight_delta(current, target) -> float`. Mapping rules — see Acceptance.
   Tested without mocks.

5. **`src/irc/decision/gates.py`**: `decide_row` gains `risk_action`,
   `dca_action`, `portfolio_weight`, `is_holding` params (threaded from the
   opportunity-state map the decision command already loads). `_build_decision_row`
   replaces the `portfolio_action="no_trade"` literal with the
   `map_portfolio_action(...)` result and stamps `current_weight` /
   `weight_delta`. `decision_status` becomes `"review_sell_later"` when a hold
   carries a sell/trim/exit/review action but is not an actionable buy.

6. **`src/irc/decision/report.py`**: new `_holdings_action_section(rows)` ⇒
   `## 持仓行动 / Sell · Trim · Review` rendered above "Blocked". One table:
   Instrument · Name · Action · Current % · Target % · Δ pp · Why. Only rows with
   `portfolio_action ∈ {trim_review, exit_review, review}` AND `is_holding`.
   Empty-state line when none. `_summary(rows)` gains
   `trim_count`/`exit_count`/`review_count` (see Acceptance AC5 / OQ4 for the
   exact definitions item 002 consumes).

7. **`src/irc/commands/decision_cmd.py`**: read the four new fields out of
   `_read_opportunity_state_by_id` row dicts (already loaded) and pass them
   through `compose_decision_report` → `_build_rows` → `decide_row`. Where
   `opportunity_report.json` lacks a row for an id (legacy / unpublished),
   default `risk_action="none"`, `portfolio_weight=None`, `is_holding=False` so
   behavior is identical to today (`portfolio_action="no_trade"`).

## Acceptance criteria

Each criterion is independently verifiable by a test or by inspecting outputs.

1. `opportunity_report.json` rows each carry the keys `risk_action`,
   `dca_action`, `portfolio_weight`, and `is_holding`, with values byte-equal to
   the corresponding discipline row's `risk_action`/`dca_action` and the row's
   `PositionContext.portfolio_weight`/`is_holding`. (A regression test feeds an
   `OpportunityRow` set through `compose_opportunity_report` and asserts the four
   keys.)

2. `PortfolioAction` literal includes `no_trade`, `buy`, `trim_review`,
   `exit_review`, `review`; `DecisionStatus` includes `review_sell_later`; the
   Phase-3 TODO comment in `models.py` is removed. (Type/lint + a test asserting
   the literal members.)

3. `map_portfolio_action` is a pure function obeying, in fixed precedence:
   (a) `blocking_reasons` non-empty ⇒ `no_trade` (a blocked row is never an
   action); (b) `risk_action == "exit_review"` AND `is_holding` ⇒ `exit_review`;
   (c) `risk_action == "trim_review"` AND `is_holding` ⇒ `trim_review`;
   (d) `risk_action == "review_required"` AND `is_holding` ⇒ `review`;
   (e) `score_action ∈ {buy_candidate, strong_buy_candidate}` AND
   `allocation_selected` ⇒ `buy`; (f) otherwise `no_trade`. Sell-side branches
   require `is_holding` (you cannot trim what you do not own). Unit-tested on a
   truth table covering every branch + the not-a-holding short-circuit.

4. `weight_delta(current, target)` returns `current - target` in weight-fraction
   units (e.g. `0.02` for +2pp); rendered as percentage-points in the report.
   `None`/missing current weight is treated as `0.0`. Unit-tested.

5. `decision_report.json` `summary` gains exactly these three additive integer
   counts (canonical names — see OQ4): `trim_count`
   (= rows where `portfolio_action == "trim_review"`), `exit_count`
   (= `portfolio_action == "exit_review"`), `review_count`
   (= `portfolio_action == "review"`). No `sell_count` key is emitted (item 002
   composes its own `trim_count + exit_count` rollup if it wants one). The
   existing `actionable_buy_count` / `watch_count` / `avoid_count` /
   `blocked_count` keys are unchanged. (Test asserts counts on a fixed row set.)

6. `decision_report.md` contains a `## 持仓行动 / Sell · Trim · Review` section
   rendered above the Blocked section, with one row per held instrument carrying
   a trim/exit/review action, columns: Instrument, Name, Action, Current %,
   Target %, Δ (pp), Why. When no such rows exist the section renders a stable
   empty-state line (greppable, e.g. `（无持仓调整建议）`). (Renderer test on
   both populated and empty inputs.)

7. A non-held instrument that scores `expensive`/`overheated` does **NOT** appear
   in the holdings-action section and does **NOT** receive `trim_review`/
   `exit_review`/`review` as its `portfolio_action` (it stays `no_trade` or
   `buy`). This preserves the holding-aware contract end-to-end. (Test.)

8. When `opportunity_report.json` is absent or missing a row for an id (legacy
   path), every `DecisionRow.portfolio_action` is `no_trade` or `buy` and the
   holdings-action section renders empty — output is identical to pre-change for
   the buy-side rows. (Back-compat test.)

9. A held instrument with `risk_action == "exit_review"` gets
   `decision_status == "review_sell_later"` (unless it is simultaneously a
   blocked or actionable_buy row, in which case the existing status precedence
   wins). (Test on the status-precedence boundary.)

10. End-to-end: `uv run irc decision` against the current `outputs/<latest>/`
    artifacts produces a `decision_report.json` whose `summary` carries the four
    new counts and whose rows carry the new fields, exiting 0. (Manual run +
    `irc decision` smoke; no network.)

11. `uv run ruff check src tests` passes on all touched/new files; every new or
    modified source file remains < 200 lines and every new function < 20 lines
    ideal (helpers extracted otherwise).

## Non-goals

- **Order sizing in units / lots / shares.** The report states a target weight
  delta (pp); it does not compute how many units to sell. (Footnote in the
  decision sheet — "this plan does not size trades" — stays true.)
- **Broker / execution integration.** No order placement, no venue order routing.
- **Historical performance attribution** (realized P&L, since-entry return
  beyond the existing `drawdown_since_entry`).
- **Changing the discipline `risk_action` logic** in `discipline.py`. This item
  *surfaces* the existing signals; it does not retune the trim/exit/review
  thresholds.
- **Market-value current weight.** Current weight stays cost-basis-derived
  (`cost_basis_cny / portfolio_total_cny`), the value already computed as
  `inp.portfolio_weight`. Re-pricing holdings to live NAV is out of scope (see
  OQ3).
- **A standalone `discipline_report.json` artifact** (approach C above).
- **Notifier wiring** — item 002 consumes the JSON counts; this item only emits
  them.

## Constraints

- **TDD mandatory.** Red → green → refactor. Every behavior above lands as a
  failing test first. `tests/` mirrors `src/irc/` one-for-one
  (`portfolio_action.py` → `tests/decision/test_portfolio_action.py`, etc.).
- **No VERSION bump.** Accumulate under `CHANGELOG [Unreleased]` at the static
  `VERSION` per the project versioning convention; do not bump per feature PR.
- **Functional / immutable.** Pure stage cores; no argument mutation; frozen
  dataclasses extended via field additions (defaults preserve back-compat).
  `map_portfolio_action` / `weight_delta` are pure (no I/O, deterministic).
- **Effects at edges.** All filesystem reads (`opportunity_report.json`,
  `proposed_allocation.yaml`, `inputs/account.yaml`) stay in `decision_cmd.py` /
  `opportunity_cmd.py`; `report.py`, `gates.py`, `portfolio_action.py`,
  `models.py` stay pure.
- **File / function size budget.** Files < 200 lines, functions < 20 lines
  ideal; extract helpers rather than nest > 3 levels. New
  `portfolio_action.py` is the home for the mapping so `gates.py` does not grow
  past budget.
- **No shared mutable module state.** Counts and mappings are computed from
  passed-in row lists; no globals.
- **Public-API stability.** `compose_opportunity_report`, `decide_row`,
  `compose_decision_report` keep their existing signatures *extended only by
  keyword params with defaults*, so legacy / test callers compile unchanged.
  Existing `decision_report.json` keys (`actionable_buy_count`, etc.) are
  preserved; only additive keys are introduced.
- **Locked invariants — all UNAFFECTED (assert in review):**
  - **`thesis_state` setter rule** — `thesis_state` is set ONLY by
    `derive_thesis_from_evidence`. This item reads `risk_action`, never writes
    `thesis_state`; Policy B path untouched.
  - **Policy B** — publishability of active funds is unchanged; this item does
    not touch `evaluate_policy_b`, `evidence_gaps`, or the gapped/publishable
    partition.
  - **H3 universal gapped-row invariant** — only **publishable** rows
    (`evidence_gaps == ()`) reach `opportunity_report.json`; the four new keys
    are added to the *same* publishable-row dict, so the partition predicate and
    the failure-section field set are untouched.
  - **SAME-3 invariant** — the citation set rendered in picks-table / evidence-
    pool / discipline bullets is unchanged; no new `[ref:...]` markers are
    emitted by this item.
  - **Citation ID format** (16 hex) — untouched.
- **Deps / security.** No new dependencies. No secrets. No network in any unit
  test; the e2e check (AC10) reads existing on-disk outputs only.

## Open questions resolved during brainstorming

*(Autonomy override in effect — no user in loop; each answer is the
recommended resolution with rationale, recorded here.)*

- **OQ1 — Where does the signal cross from opportunity → decision?**
  **Resolved: Approach B** (extend `opportunity_report.json`, map in decision).
  Rationale: single source of truth for `risk_action` (computed once in the
  opportunity stage by `derive_risk_action`); the decision command already reads
  `opportunity_report.json`; no new artifact or write path. Approaches A
  (re-derive) and C (new JSON) add duplication/surface for no gain at this scope.

- **OQ2 — Should `portfolio_action` distinguish trim vs exit vs review, or
  collapse to a single `sell`?** **Resolved: keep three distinct actions**
  (`trim_review`, `exit_review`, `review`) mirroring the discipline
  `risk_action` vocabulary, plus `buy` and `no_trade`. Rationale: the operator
  acts differently on "scale out of an overheated winner" vs "thesis falsified —
  exit" vs "drawdown ≥20%, eyeball it." Collapsing loses the distinction the
  discipline layer already paid to compute. Item 002's notifier gets separate
  counts so it can phrase alerts precisely.

- **OQ3 — Current weight from cost-basis or live market value?**
  **Resolved: cost-basis** (`cost_basis_cny / portfolio_total_cny`), the value
  already computed as `inp.portfolio_weight`. Rationale: market-value re-pricing
  needs a live NAV fetch per holding, which `irc decision` deliberately does NOT
  do (it reads cached outputs, exit-code-clean, no network). Cost-basis weight is
  an honest first-order delta; live-NAV current weight is a future item. The
  report column is labelled so the operator knows it is cost-basis.

- **OQ4 — Exact JSON summary key names for item 002's notifier?**
  **Resolved: `trim_count`, `exit_count`, `review_count`** (and the existing
  `actionable_buy_count` for buys). MASTER-SPEC item 002 says the notifier
  consumes "sell/review counts." To avoid ambiguity between "sell" meaning
  exit-only vs trim+exit, the canonical keys are `trim_count`
  (`portfolio_action == "trim_review"`), `exit_count`
  (`portfolio_action == "exit_review"`), `review_count`
  (`portfolio_action == "review"`). AC5 is corrected to these names — `sell_count`
  is NOT emitted (it was an ambiguous draft term); item 002 sums `trim_count +
  exit_count` if it wants a combined "sell" total. Rationale: explicit,
  non-overlapping, greppable; the notifier composes its own rollup.

- **OQ5 — Does the holdings-action section list rows that are flagged but not
  held (e.g. an overheated non-holding the discipline layer would trim *if*
  held)?** **Resolved: no.** Only `is_holding` rows appear, and the sell-side
  `portfolio_action` branches are gated on `is_holding` (AC3, AC7). Rationale:
  the user's stated goal is "TRIM/EXIT/REVIEW on holdings they actually own."
  A non-held overheated instrument is already covered by buy-side gating
  (it simply isn't bought); surfacing it as a "trim" would be nonsensical.

- **OQ6 — `review_required` (drawdown ≥20% / thesis under_pressure) → which
  `portfolio_action`?** **Resolved: `review`** (a distinct, softer action than
  trim/exit), still gated on `is_holding`. Rationale: `review_required` is
  explicitly "NEVER auto-sell" per `discipline.py` — it must not render as a
  trim/exit. A separate `review` action + `review_count` keeps the
  never-auto-sell semantics visible end-to-end.

### No unresolved questions

All open questions were resolvable from MASTER-SPEC + code + CONTEXT.md. The one
that required a judgement call (OQ4 key naming) is recorded with the rationale
and the corrected AC; the implementer should treat `trim_count`/`exit_count`/
`review_count` as canonical.

## Resolved decisions

*(Grill pass, 2026-06-10, subagent opus, autonomy override — auto-accepted
recommendations. CONTEXT.md + ADR 0015 synced inline. Strike-throughs above mark
corrections; nothing deleted.)*

- **R1 — `compose_opportunity_report` signature must change (the spec implied it
  could stay).** The four new fields are NOT on `OpportunityRow` — `risk_action`/
  `dca_action` live on `DisciplineRow`/`ThesisCard`; `portfolio_weight`/`is_holding`
  on `OpportunityInput`/`PositionContext`. `compose_opportunity_report(rows, date)`
  receives only rows, so `_row_to_dict(row)` cannot reach them. **Resolution:** add a
  keyword `discipline_by_id: dict[str, …] | None = None` (default `None` ⇒ today's
  bytes). Built at the command edge from the already-existing `discipline_rows` +
  `positions[iid]`. Rationale: keeps composition pure, preserves public-API
  stability via a defaulted keyword, no new I/O. Doc impact: components #1/#2
  corrected in place; CONTEXT.md `portfolio_action` entry.

- **R2 — H3 / SAME-3 are structurally untouched (confirmed, not just asserted).**
  The four keys are added to the SAME publishable-row dict that already passes the
  `evidence_gaps == ()` partition; the partition predicate, the failure-section
  4-field renderer signature, and the `select_citations(cap=3)` SAME-3 surfaces are
  all unchanged. No new `[ref:...]` marker is emitted (the new fields are plain
  scalars, never cited). `opportunity_report.json` IS one of the five canonical
  byte-equality artifacts (ADR 0004), so the new keys must be deterministic — they
  are (derived from cached scalars + a deterministic `discipline_by_id` map).
  Doc impact: ADR 0015 §Consequences; AC retained.

- **R3 — `portfolio_action` is a projection of `risk_action`, never a writer of
  `thesis_state`.** The decision layer reads `risk_action` and maps it; it never
  calls `derive_thesis_from_evidence` and never mutates `thesis_state` (ADR 0003
  setter rule) or Policy B publishability. The `map_portfolio_action` precedence
  is closed and pure. Doc impact: CONTEXT.md `map_portfolio_action`; ADR 0015 §2.

- **R4 — the `is_holding` gate on the sell branches is load-bearing, NOT
  belt-and-suspenders.** `derive_risk_action` (`discipline.py`) can return
  `trim_review`/`exit_review` for a non-holding via its legacy `overweight` branch.
  Without the `is_holding` gate in `map_portfolio_action`, an unheld overheated
  instrument would render as a trim — violating AC7. The mapper, not the discipline
  derivation, is the enforcement locus for the holdings-only contract. Doc impact:
  CONTEXT.md `map_portfolio_action`; ADR 0015 §2.

- **R5 — Δpp determinism holds (cost-basis, two cached scalars).** `current_weight`
  (cost-basis `portfolio_weight`) and `target_weight` (`proposed_allocation.yaml`)
  are both read network-free from cached artifacts; `weight_delta = current − target`
  is a single subtraction, no float accumulation, stable across re-runs (ADR 0004).
  Doc impact: CONTEXT.md `current_weight` / `weight_delta`; ADR 0015 §2.

- **R6 — `review_sell_later` is the locked `DecisionStatus` name.** The
  `models.py:12` Phase-3 TODO already named it `review_sell_later`; the spec adopts
  it verbatim — no rename. Buy-side status precedence (`avoid > blocked >
  actionable_buy`) is unchanged; the new status only fills the slot a held-with-sell-
  signal row would otherwise occupy as `watch_only`. Doc impact: CONTEXT.md
  `review_sell_later`.

- **R7 — summary-count names locked for item 002: `trim_count` / `exit_count` /
  `review_count`, NO `sell_count`.** Keyed off `portfolio_action`. The existing
  four counts are preserved (additive-only). Item 002's notifier consumes these and
  composes its own `trim_count + exit_count` rollup if it wants a combined "sell"
  total. Doc impact: CONTEXT.md "Decision summary sell/review counts"; ADR 0015 §3.

- **R8 — an ADR clears the three-of-three bar; recorded as ADR 0015.** The
  `portfolio_action` emission contract is hard to reverse (machine-read
  `decision_report.json` consumed by item 002), surprising without context (why
  `review_required → review` not trim/exit; why the `is_holding` gate; why no
  `sell_count`), and the product of a real trade-off (approaches A/B/C; the
  sell-collapse vs three-action choice; the count-naming ambiguity). Doc impact:
  ADR 0015 created.

**Verdict: PASS.** No spec claim contradicts a load-bearing ADR (0003 setter rule,
0004 determinism/SAME-3) or current code that the doc updates cannot resolve. The
one code-vs-spec contradiction (R1, the `compose_opportunity_report` signature) is
a refinable under-specification, corrected in place — not a blocking contradiction.
