Verdict: PASS

Subagent: orchestrator (in-prompt; spec-mode N=1 light doc-sync)
Items reviewed: 1 (001)

## Doc changes verified (PR1 scope)
- `CHANGELOG.md` `[Unreleased]` — "Added — Phase D active-fund look-through valuation (PR1 shadow compute, 2026-06-04)" entry present (impl Task 20). No VERSION bump (project convention; VERSION stays 0.9.3).
- `README.md` — evidence-refresh-order note updated: `irc run` → `irc fundamentals stock-valuation` → `irc opportunity` (the new heavy refresh command's place in the cadence).

## Deliberately deferred to PR2 (per spec §10 — NOT a PR1 gap)
- **ADR 0012 addendum** ("active-fund look-through now populates the slot") — spec §10 assigns this to PR2 as the durable design-of-record for the flag flip.
- **CONTEXT.md "Valuation inputs"** update — spec §10 assigns this to PR2 (when active funds actually consume the PE anchor).
Rationale: PR1 is shadow-compute (flag OFF, prod byte-identical); the active-fund look-through does not yet change any output, so the design-of-record docs land with the flag flip. The diff report's current-basket caveat and the gate-#5 review note carry the interim documentation.

## Missing coverage: none (for PR1 scope)
