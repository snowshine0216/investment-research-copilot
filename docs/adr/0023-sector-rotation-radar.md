# ADR 0023 — Sector rotation radar: EM-board taxonomy, advisory isolation, cross-vertical edge reuse

**Status:** Accepted (built 2026-07-05).

**Builds on:** [ADR 0019 — monitor capital-flow factor](0019-monitor-capital-flow-factor.md)
(EastMoney data-plane posture, breaker semantics, batch `ulist.np` findings),
[ADR 0017 — monitor evidence isolation](0017-monitor-evidence-isolation.md) (what "isolation"
does and does not mean here).

**Relates to:** [ADR 0015 — portfolio_action emission contract](0015-portfolio-action-emission-contract.md)
and [ADR 0011 — adversarial debate advisory-only](0011-adversarial-debate-advisory-only.md)
(the advisory line the radar must not cross), [ADR 0007 — thesis-news scoring](0007-thesis-news-scoring.md)
(the static theme mapping the deferred L3 hook would touch), [ADR 0014 — legulegu rate-limit
handling](0014-legulegu-rate-limit-handling.md) (why 申万-granularity data was rejected).
**Spec:** [`docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md`](../superpowers/specs/2026-07-05-sector-rotation-radar-design.md).

## Context

Screening today finds sector-driven candidates only through `irc narrative` — a hand-curated,
frozen basket the user must think to write. Nothing in the system detects 板块轮动; a tech fund
scores identically whether its sector is hot or cold, and weekly research themes are macro, not
sector. The monitor vertical has already built (and battle-tested) every needed data edge:
batch board/stock fetch with 3-outcome caching, a stock→industry map, board PE, a trading
calendar, and a CN egress path. The gap is aggregation and a join to funds. Three decisions in
closing it are hard to reverse, surprising without context, and real trade-offs.

## Decision

### D1 — The canonical sector unit is the **EastMoney industry board** (~86, keyed by board code)

All momentum/flow measurement, the series store, states, and the fund join operate on EM boards.

- *Rejected — 申万 industries*: the vocabulary of narrative configs and holdings snapshots, but
  the repo has no live SW-level flow/momentum feed, and the one SW-adjacent provider (legulegu)
  is rate-limit-fragile (ADR 0014). Choosing SW would mean new fetch infrastructure on the least
  reliable provider.
- *Rejected — 17 CSIndex sector indices*: clean momentum but tech+metals coverage only; the radar
  would be structurally blind to rotation into healthcare/consumer/defense/etc.
- *Rejected — 11 universe themes*: coarse enough to smear the signal (8 boards averaging into
  "tech" detects heat weeks late) and only 238/~500 funds carry a tag.

Consequence: the series store's history is keyed by EM board codes — switching taxonomy later
restarts the accumulation clock. That is the hard-to-reverse part and why it is recorded here.

### D2 — Advisory only, one-way isolated

The radar emits `rotation_state` per board and *rotation candidates* per fund. It never emits or
influences `portfolio_action` (ADR 0015), `DirectionalBias`, `opportunity_state`, discovery
filtering, or scoring weights. Dependency direction is enforced one-way: nothing in
`monitor/discovery/scoring/memo/opportunity` imports from `irc.rotation`. Candidates are research
leads that *start* the existing evidence workflow (`irc narrative --analyze`, `irc eval-funds`),
never shortcut it — deliberately the same posture as ADR 0011's debate layer. Fund friction
(T+1/T+2, 申购费) makes fast-rotation *trading* a losing game; the radar's value is earlier
research starts, and tactical trading stays out of IRC by standing decision.

### D3 — Reuse monitor edges by import; do not extract a shared package yet

`irc.rotation` imports `cached_fetch`, the `em_raw` parsers, and `trading_calendar` from
`irc.monitor`, and extends `industry_map_store` in place. ADR 0017's isolation is about the
monitor brief's **evidence pool**, not code; importing a parser mixes no evidence. Extracting a
shared `emdata` package now would churn a production vertical inside a feature item (refactor +
feature coupled) for exactly two consumers — extraction waits for a third (rule of three).

### D4 — Close-anchored capture: the radar chains at 15:45, never 12:15

The daily snapshot appends to a series backfilled from daily closes; a 12:15 capture would mix
half-day rows into that series and silently corrupt every momentum window. So the radar rides the
flow-capture wrapper (post-close, holiday-guarded, protective-only), not the monitor wrapper.

## Consequences

- A new `data/rotation/` store accumulates from day 1; forward validation (`rotation_forward`)
  becomes possible after ~4–6 weeks and segments by `radar_version`.
- The composite's weights/windows are recorded priors (ADR 0018 spirit): tunable only with
  forward-eval evidence, never silently.
- The 262 theme-untagged universe funds become discoverable through holdings exposure — the
  first surface that covers the whole CN universe by what funds actually hold.
- Deferred hooks (dynamic hot_sector research query, auto-narrative baskets, memo/monitor
  surfacing) each need their own decision pass; F3 in particular interacts with ADR 0007's
  static theme mapping and must not be built as a side effect.
- **F6 — daily in-run bounded top-up (§8/D11)**: the daily `irc rotation` run is cache-only in
  v1; the ≤50 in-run `IRC_ROTATION_TOPUP_BUDGET` top-up for incremental holdings/board-map cache
  misses between seeds is deferred (the budget currently bounds seed's stock-board chunking).
  Cold cache renders L1 + the seed-pointer line (spec §7).
