# SKIPPED — review-followup run (2026-07-07)

All entries below are **user-locked out of scope** in BACKLOG.md ("Out of scope for this backlog" + Backlog decisions section). None are orchestrator skips; do not re-try without explicit user instruction.

- **CN proxy purchase / efinance source switch** — blocker: a spend/infrastructure decision only the user can make (F8 egress is an environment problem, not code). Unblock path: user decides on a paid CN egress or an efinance data-source migration; then a dedicated spec.
- **M-1 flow-freshness gate (Tier-2)** — blocker: touches locked factor-math surfaces; user requires its own spec+grill session. Unblock path: dedicated session; the interim honesty gap is documented in CONTEXT.md (data-health digest "may be more honest than the report").
- **M-2 real `factor_freshness` (Tier-2)** — same as M-1: needs own spec+grill.
- **M-4 evidence pinning (Tier-2)** — same as M-1: needs own spec+grill.
- **M-3 / M-4-stopgap / M-7 monitor code fixes** — user decision Q-C: stay TODOS-registered (registration happens in item 002-c); they touch the locked report/ledger surfaces and get their own spec+review session.
- **Full README restructure** — user decision Q-B: rejected; only the light doc-map enhance (002-b) is in scope. Revisit after the doc-map beds in.
- **`overall-workflow.html` full regeneration** — deferred in 002-b (M effort, low urgency); only the CLAUDE.md-link relabel is in scope. Pickup: when the diagram next drifts materially or a diagram session is scheduled.
