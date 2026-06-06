# MASTER-SPEC — Spend / Balance Gate Phase 2

**Mode:** plan (user-authored implementation plan with 12 numbered Tasks, explicit file paths, `Run:`/`Expected:` markers, named test files)

**Source plan:** [`docs/superpowers/plans/2026-06-05-spend-balance-gate-phase2.md`](../../superpowers/plans/2026-06-05-spend-balance-gate-phase2.md)

**Run date:** 2026-06-06

## Scope

| # | Item | Classification | Rationale |
|---|------|----------------|-----------|
| 001 | Spend/balance gate Phase 2 — usage-as-data recorder + EWMA convergence + ledger auto-decrement + estimate/actual artifacts | **IN** | User-authored, ready-to-execute plan (12 tasks). Builds on the merged Phase 1 spend module. |

No OUT-scope items (single-task plan-mode run).

## Goal (paraphrased from plan)

Make the spend gate *learn*: capture each gated run's actual paid-API usage (LLM tokens + search units), fold it into a rolling EWMA usage profile so the next estimate converges on reality, auto-decrement the local ledger, and emit estimated-vs-actual artifacts — hands-off on every gated run. Pure cores + I/O at the command edge, honouring ADR 0013 (usage rides home as data; no recorder param leaks into a pure core, no module-global accumulator).
