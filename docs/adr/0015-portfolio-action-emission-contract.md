# ADR 0015 — `portfolio_action` emission contract (sell surfacing into the decision layer)

**Status:** Accepted (2026-06-10, actionable-ops item 001)
**Builds on:** [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md) (`thesis_state` setter rule), [ADR 0004 — renderer determinism + SAME-3](0004-renderer-determinism-and-alias-policy.md).
**Spec:** `docs/2026-06-10-actionable-ops/items/001-spec.md`

## Context

The discipline layer already derives sell-side signals per held position
(`risk_action ∈ {none, review_required, trim_review, exit_review}`, holding-aware
via `is_holding`), but they died inside `discipline_report.md` (markdown only).
`opportunity_report.json` rows omitted them and `decision/gates.py` hard-coded
`portfolio_action = "no_trade"` for every row (`PortfolioAction = Literal["no_trade"]`).
The operator's decision report told them what to BUY but never what to TRIM / EXIT /
REVIEW on instruments they actually hold.

Item 001 surfaces the existing signals through `opportunity_report.json` and maps
them in the decision layer into a real `portfolio_action`, with a current-vs-target
weight delta, plus machine-readable summary counts that item 002's notifier will
consume. Three contracts here are hard to reverse, surprising without context, and
the product of real trade-offs — so they are locked.

## Decision

### 1. Signal crosses opportunity → decision via `opportunity_report.json` (approach B)

The four discipline-derived fields (`risk_action`, `dca_action`, `portfolio_weight`,
`is_holding`) are added to each PUBLISHABLE `opportunity_report.json` row; the decision
command (which already reads that file via `_read_opportunity_state_by_id`) maps them.

- *Rejected A — re-run discipline inside decision.* Duplicates the opportunity
  stage's snapshot / Policy-B machinery and risks a divergent `risk_action`
  (single-source-of-truth violation).
- *Rejected C — new `discipline_report.json` artifact.* A parallel write path and
  artifact when the existing report already carries the publishable-row set the
  decision layer needs. Revisit only if a future item needs the full per-constituent
  discipline payload machine-readable.

`compose_opportunity_report` gains a keyword `discipline_by_id` map (default `None`
⇒ the four keys emit as `risk_action="none"`, `dca_action=None`, `portfolio_weight=None`,
`is_holding=False`, byte-identical to pre-change for legacy/test callers). The command
edge assembles the map from the `discipline_rows` and `positions[iid]` it already builds
at `_write_opportunity_outputs`; composition stays pure (effects at edges).

### 2. Five-value `PortfolioAction`, derived (never authored) by a pure mapper

`PortfolioAction = Literal["no_trade", "buy", "trim_review", "exit_review", "review"]`.
The single pure `map_portfolio_action(*, risk_action, score_action, allocation_selected,
is_holding, blocking_reasons)` (`src/irc/decision/portfolio_action.py`) decides it in
fixed precedence (corrected in P0-3 ship-blocked review, 2026-06-10):

1. `exit_review ∧ is_holding` ⇒ `exit_review`  **← sell-side first**
2. `trim_review ∧ is_holding` ⇒ `trim_review`
3. `review_required ∧ is_holding` ⇒ `review`
4. `blocking_reasons` non-empty ⇒ `no_trade`   **← blocks buy-side only**
5. buy-candidate ∧ allocation-selected ⇒ `buy`
6. else `no_trade`

The sell-side branches (1–3) precede the `blocking_reasons` short-circuit (4) because
buy-side blockers (`venue_blocked`, `opportunity_excluded`, `data_incomplete`, …) block
BUYING, not selling what you already hold.  A non-held row falls through (1–3) to (4),
so `not-held + blocked → no_trade` is unchanged.

Two non-obvious choices:

- **Three distinct sell actions, not a collapsed `sell`.** The operator acts
  differently on "scale out of an overheated winner" (`trim_review`) vs "thesis
  falsified — exit" (`exit_review`) vs "drawdown ≥20%, eyeball it" (`review`).
  Collapsing loses the distinction the discipline layer already paid to compute.
- **`review_required → review`, NEVER trim/exit.** `discipline.py` documents
  `review_required` as "NEVER auto-sell". A separate `review` action keeps the
  never-auto-sell semantics visible end-to-end; mapping it to a trim/exit would
  silently arm an auto-sell the discipline layer deliberately withheld.

The `is_holding` gate on the three sell branches is **load-bearing, not redundant**:
`derive_risk_action` can return `trim_review`/`exit_review` for a NON-holding (the
legacy `overweight` branch). The mapper — not the discipline derivation — enforces
"you cannot trim what you do not own", so an unheld overheated instrument stays
`no_trade`/`buy` and never appears in the 持仓行动 section.

This is a downstream projection: `portfolio_action` reads `risk_action`, it never
writes `thesis_state` (ADR 0003 setter rule) and does not touch Policy B
publishability. `current_weight` is **cost-basis** (`portfolio_weight`), not live
market value — `irc decision` is network-free off cached artifacts, so Δpp is a pure
subtraction of two cached scalars (deterministic per ADR 0004).

### 3. Summary-count key names are locked for the item-002 notifier

`decision_report.json` `summary` gains exactly `trim_count`, `exit_count`,
`review_count` (keyed off `portfolio_action`). **No `sell_count`** — "sell" is
ambiguous between exit-only and trim+exit, so the notifier composes its own rollup.
The existing `actionable_buy_count` / `watch_count` / `avoid_count` / `blocked_count`
keys are unchanged (additive-only). A held row carrying a sell/trim/exit/review action
that is not also blocked or an actionable buy gets `decision_status == "review_sell_later"`
(the `DecisionStatus` member that replaces the Phase-3 TODO; buy-side status precedence
is unchanged).

## Consequences

- Item 002 can be written against `trim_count` / `exit_count` / `review_count` and the
  five-value `portfolio_action` vocabulary without guessing; renaming after 002 ships
  would break the notifier, which is why the names are recorded here.
- H3 (publishable-only partition) and SAME-3 (citation-set equality) are structurally
  untouched: the four new keys are added to the SAME publishable-row dict; no new
  `[ref:...]` markers are emitted; `evidence_gaps == ()` remains the sole partition
  predicate.
- The five-value literal and the summary keys are additive — every existing
  `decision_report.json` consumer keeps working.
- `current_weight` being cost-basis is an acknowledged first-order approximation;
  live-NAV current weight is a future item, not a defect of this contract.

## Addendum — null-counts semantics (P0-2, ship-blocked review 2026-06-10)

`trim_count` / `exit_count` / `review_count` in `decision_report.json` `summary` are
**JSON `null`** (Python `None`) when `opportunity_report.json` is a pre-001 artifact —
i.e. not a single row carries a `risk_action` key.

**`null` ≠ `0`.** Semantics:

| Value | Meaning |
|---|---|
| `0` | Signals were derived; zero rows had that action. |
| `null` | Signals were never derived (stale artifact). Unknown, not zero. |

The `decision_report.md` 持仓行动 section renders a visible warning instead of the
empty-state line when null. The item-002 notifier **MUST** treat `null` as "signals
unavailable — re-run `irc opportunity` before acting"; it must NOT treat it as 0 or
suppress the warning silently.

Detection (implemented in `decision_cmd._is_stale_opportunity_artifact`): True when the
file has rows but not a single row carries a `risk_action` key.  Rows with
`risk_action="none"` (modern artifact, all no-risk) → not stale → counts are 0.
