Verdict: PASS

Subagent: opus / Questions resolved: 7
Docs touched (commit 8999770e):
  - CONTEXT.md — "Stock-industry map (cross-day store)" term: seed-writer skip-set clause
  - docs/2026-07-07-review-followup/items/005-spec.md — Failure-clock strike-through +
    `## Resolved decisions`
Spec refined (commit 8999770e): items/005-spec.md `## Resolved decisions` + strike-through

No ADR created (Q7: three-of-three fails — a one-line skip-set swap reusing the existing pure
`fresh_slice`, no schema/`radar_version`/store-shape change, trivially reversible; consistent
with item 004's no-ADR L2 fix). No spec-vs-CONTEXT / spec-vs-ADR contradiction (no FAIL): the
spec consumes (never forks) the store's ≤30-calendar-day serve-while-stale window and upholds
ADR 0023 (advisory posture, no version bump).

## Resolved decisions

- Q1: Does re-fetching ~640 stale symbols blow the seed budget (IRC_ROTATION_TOPUP_BUDGET) on
     the ~2026-08-05 cliff and starve never-seen symbols?
  A: No starvation — the "budget" is `chunk_size` (per-call symbol count, default 50), NOT a
     per-run call cap; every pending symbol is always fetched, just in more chunks.
  Rationale: rotation_cmd.py:204-211,242-245 wire IRC_ROTATION_TOPUP_BUDGET → chunk_size (the
     R-11 finding). Consequence (accepted): the cliff becomes a periodic ~640-symbol unpaced
     burst (+ the ~331 always-refetched HK symbols, R-11) — the R-5 self-DoS shape, out of
     scope, no new crash risk (per-chunk try/except → failed → retried next seed).
  Doc impact: Resolved-decisions Q1 + CONTEXT store clause.

- Q2: Is `summary["skipped"]` still truthful post-fix?
  A: Yes; keep the locked `len(fresh)`. Every newly-stale key moves to done/failed, never
     silently dropped.
  Rationale: the store-scoped `skipped` vs symbol-scoped `done`/`failed` mismatch is
     PRE-EXISTING (also true when skipped=len(existing.keys())), so not a regression; the
     locked "no richer summary" (Q6) forbids an intersection/tally.
  Doc impact: Resolved-decisions Q2.

- Q3: Does the daily `irc rotation` run change the staleness-clock assumptions?
  A: No — the daily run is READ-ONLY on the store (resolve_candidates only reads via
     fresh_slice; never record_seen; F6 in-run top-up deferred).
  Rationale: seen_at is written only by `irc monitor` (daily, ~60 syms) and `irc rotation
     seed` (on demand) — confirming the spec's failure clock exactly.
  Doc impact: CONTEXT store clause (writer/reader split made explicit).

- Q4: Does the fix auto-heal coverage, or only on re-seed?
  A: Only on re-seed — sharpened the spec's "restores self-healing" → "…on re-seed".
  Rationale: no scheduled seed (ops/launchd chains the daily radar, not `rotation seed`);
     without a periodic re-seed or the deferred F6 top-up, coverage still crosses the ~08-05
     cliff. Fix is necessary-but-not-sufficient for continuous coverage; cadence/F6 is a
     separate out-of-scope decision.
  Doc impact: spec Failure-clock strike-through + CONTEXT store clause.

- Q5: AC3 test mechanics — batch_fetch contract + which symbols in `symbols`?
  A: Sharpened: the fake batch_fetch returns a 2-tuple ({}, {stale_sym: "<行业 name>"}) (not a
     bare dict); AC3 passes BOTH stale and fresh symbols in `symbols` and asserts stale
     seen_at==today, fresh seen_at unchanged, fresh absent from recorded chunks.
  Rationale: seed unpacks `_flow, industry_by_symbol = batch_fetch(...)`; a fresh symbol
     absent from `symbols` would be trivially untouched — passing it in makes the skip
     assertion load-bearing.
  Doc impact: Resolved-decisions Q5 (plan input).

- Q6: Alignment with the item-004-corrected CONTEXT store entry.
  A: One clause added — the seed WRITER's skip-set honors the same fresh_slice ≤30-day window
     as the two READER joins (lockstep; a seed-local window would re-open the heal gap).
  Rationale: the post-004 entry documented the readers but was silent on the seed writer.
  Doc impact: CONTEXT.md "Stock-industry map (cross-day store)" term.

- Q7: Is a new ADR warranted?
  A: No.
  Rationale: three-of-three fails — one-line pure-fn reuse, trivially reversible, no
     version/store-shape change; mild surprise captured by the AC4 docstring rewrite + CONTEXT
     clause; the lone trade-off is settled by the store's serve-while-stale contract.
  Doc impact: none.
