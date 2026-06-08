# MASTER-SPEC — Phase A legulegu broad-leg rate-limit hardening

**Mode:** spec (single feature). Spec + grill pre-completed `⏭️` (user-authored & grilled — 3 doc commits `7841f48`→`4714399`→`9692a2f`, incl. ADR 0014 + CONTEXT.md). Entry phase = Opus `superpowers:writing-plans`.

**Source spec (verbatim):** [`items/001-spec.md`](items/001-spec.md) — copied from `docs/superpowers/specs/2026-06-08-phase-a-legulegu-rate-limit-design.md`.
**ADR:** [`docs/adr/0014-legulegu-rate-limit-handling.md`](../adr/0014-legulegu-rate-limit-handling.md).
**Handoff:** `/tmp/HANDOFF-phase-a-rate-limit-impl.md`.

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Paced dual-policy retry + non-destructive sweep suspension + PB-wipe guard for the legulegu broad-index PE/PB ingest leg | **IN** | The deliverable. Fully designed, grilled, ADR-ratified; offline-TDD-able end to end. |

No OUT items (single feature). Deferred follow-ups (explicitly out of scope, recorded in the spec's "Known limitations" and ADR 0014 Consequences):

- Full PB date-aligned carry-forward (separate PR).
- Run-level ingest diagnostic artifact for throttle chronicity (NOT an `OpportunityRow.advisory_gap`).
- HTTP-status-preserving adapter for legulegu (durable throttle classifier).
- Pacing the csindex sector leg (verified unnecessary — static-Excel GET, no burst limiter).
- Exposing `valuation_percentile_fundamental` on the opportunity row.

## Live-network operator gates (NOT part of this autonomous run)

Live gates **#3 / #4 / #5** require real legulegu network calls. The limiter is in a **deep cooldown** from the 06-08 probing session; the spec and ADR 0014 are explicit: do offline TDD first, run each live gate **alone in its own recovered cold window**, never chained. These are **environmental stops** ([stop-conditions.md](../../.claude/skills/autodev/references/stop-conditions.md)) — this run delivers the fully offline-tested implementation and defers the live gates to the operator. They are listed verbatim in `items/001-spec.md` §"operator gates" and re-stated in PROGRESS.md. Nothing lands on `main` in this run; the feature-branch PR is left open for the operator to merge after the live gates pass.
