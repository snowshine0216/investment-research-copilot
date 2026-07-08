# Item 003 spec — Opus-enablement pass (user-authored, verbatim from BACKLOG.md)

*(autodev run note: content fully enumerated by the user; spec+grill ⏭️ pre-completed — see MASTER-PLAN. Depends on 002 (merged #213) and 002-d (version-grep guard, merged). The 002 dependency rationale: "fixing CLAUDE.md's wrong content first — accuracy is the biggest Opus lever"; both prerequisites now hold.)*

## Item 003 — Opus-enablement pass (review §4; process/docs, S)

What of §4 is repo-encodable (the rest is session routing discipline — lives in the user's
global PLAYBOOK, out of repo scope):

- **CLAUDE.md Conventions additions** (3 bullets):
  1. *Production-shaped fixtures*: integration fixtures for store/cache/join code must be
     copied from real artifact shapes, never hand-crafted (R-1 was masked by a hand-crafted
     `"BK1"` fixture — review §2.1).
  2. *Assembly assertion per feature*: every factor/pipeline feature needs one end-to-end
     test proving the new leg moves the final output from the command layer
     (`_process_fund`-style), not only pure-function tests.
  3. *Contract sentences name their test*: any "contract"/"invariant" sentence added to
     CONTEXT.md or an ADR names the enforcing test; prose-only contracts are the M-1 root
     cause.
- **FACTS.md header rule**: entries describing a live incident carry a date and a
  verification command, and must be re-verified before being acted on (the F8 entry went
  stale in 2 days).
- Depends on: 002-a (fixing CLAUDE.md's wrong content first — accuracy is the biggest
  Opus lever), 002-d (version-grep removes a drift class from model responsibility).

---

