# SKIPPED — TODOS.md critical fixes

## 003 — Opportunity venue filtering not wired (RECLASSIFIED OUT 2026-07-03)

**Blocker:** none — the item is a stale TODO, already resolved on main. The venue wiring
exists (`opportunity/inputs_build.py` sets `venue_compatible` from
`instr.venue_required` ∩ `available_venues`, fed from `bundle.account.accounts[*].available_venues`
at `opportunity_cmd.py:1497`), and the "route venue-incompatible to small_watch" behavior the
TODO asked for was deliberately REMOVED by PR #25 (`ae5a7d88`, "remove venue_compatible
downgrade gate") — venue incompatibility is execution-note-only by design, locked by
`test_venue_incompatible_does_not_block_core_dca`.

**Unblock path:** n/a. Action taken instead: TODOS.md line annotated `[x]` resolved-as-built
with the evidence above (doc-only commit on the feature branch). If the user *wants* the
downgrade behavior back, that is a product decision reversing PR #25 — raise it explicitly.

For the record, the selection deliberately did NOT pick up (not part of this run's input,
documented here so nobody reads absence as oversight):

- **memo "exited 0, wrote nothing" ghost halt** (TODOS.md Reliability #1) — marked UNSOLVED
  and diagnosis-blocked: mitigations landed 2026-07-03; next step requires a live occurrence
  with captured terminal stdout. Not actionable by code change today.
- All other open TODOS.md entries — polish / observability / test-strengthening / doc-only,
  not critical.
