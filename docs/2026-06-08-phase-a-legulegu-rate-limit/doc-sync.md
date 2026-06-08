Verdict: PASS

Subagent: orchestrator (in-prompt, spec-mode lightweight)
Items reviewed: 1 (001)

Doc changes verified:
- docs/adr/0014-legulegu-rate-limit-handling.md — the 6 ratified decisions + rejected alternatives (committed pre-handoff in the grill phase, `9692a2f`).
- CONTEXT.md — "Valuation inputs" carve-out names `LeguleguCooldownExhausted` (2 refs); "Failure-mode + audit policy" covers the `advisory_gaps` run-level-vs-row-level boundary (grill phase).
- CHANGELOG.md `[Unreleased]` — "Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)" entry references the new `src/irc/fundamentals/legulegu_fetch.py` primitive, pacing, dual-policy retry, sweep suspension, PB-wipe guard (impl `47fd986`).

New entities & their doc coverage:
- `legulegu_fetch.py` / `fetch_legulegu_frame` — covered by ADR 0014 + CHANGELOG.
- `LeguleguCooldownExhausted` — covered by CONTEXT.md + ADR 0014.
- both-axes PB-wipe guard + sweep suspension — covered by ADR 0014 (D4/D5) + CHANGELOG.

Missing coverage: none.
README.md: no change required — this is an internal ingest-robustness improvement (no new user-facing command/workflow/flag). The deferred follow-ups (PB carry-forward, run-level diagnostic artifact, HTTP-status adapter) are recorded in ADR 0014 → Consequences and the spec → "Known limitations".
