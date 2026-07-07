# MASTER-SPEC — review-followup run (2026-07-07)

Mode: **backlog** (5 items in `BACKLOG.md`, user-locked order + scope).
Input: `docs/2026-07-07-review-followup/BACKLOG.md` (status LOCKED 2026-07-07; Q-A/Q-B/Q-C resolved by the user).
Ground truth for defects/drift: `docs/2026-07-07-workflow-review.md`.

## IN-scope items

| id | Title | Effort | Kind | Authoring pre-completed by user? |
|----|-------|--------|------|----------------------------------|
| 004 | Rotation candidates join fix (review R-1, P0) | S | code | Approach LOCKED in backlog; spec+grill+plan still run (real engineering decisions remain: map construction site, fixture shape, replay harness) |
| 005 | Rotation seed skip-set freshness (review R-4) | S | code | Fix is one-line + tests, fully specified; spec+grill+plan still run (cheap; freshness semantics touch documented contracts) |
| 001 | Data-health notification (feature) | S–M | code | **Spec + grill pre-completed** — `docs/superpowers/specs/2026-07-07-data-health-notify-design.md` is GRILLED + LOCKED 2026-07-07 (§9 decisions, §10 constraints). Only plan+impl phases run. |
| 002 | Docs-sync + TODOS reconciliation (D1–D15 + 002-b/c/d) | S | docs + 1 test | **Spec + grill pre-completed** — backlog says "No design needed; the review's §0/§1 tables ARE the work order" (user override). Plan phase runs to sequence ~15 edits + the TDD version-grep test (002-d). |
| 003 | Opus-enablement pass (review §4 repo-encodable subset) | S | docs/process | Content fully enumerated in backlog (3 CLAUDE.md bullets + FACTS.md header rule). Spec = verbatim copy; grill ⏭️ (docs-only, content user-locked); plan runs. Depends on 002. |

**Item order (user-locked in BACKLOG.md, with rationale): 004 → 005 → 001 → 002 → 003.**

## OUT-of-scope (user-locked in BACKLOG.md — see SKIPPED.md)

- CN proxy purchase / efinance source switch (future decision).
- Review Tier-2 engine fixes M-1 (flow freshness gate), M-2 (real factor_freshness), M-4 (evidence pinning) — each needs its own spec+grill session.
- Monitor code fixes M-3/M-4/M-7 — stay TODOS-registered (Q-C); registration itself IS in scope via 002-c.
- Full README restructure (Q-B rejected; only the light 002-b enhance).
- `overall-workflow.html` full regeneration (002-b defers it; only the relabel is in scope).

## Cross-item constraints (from BACKLOG.md handoff block — apply to every item)

- Every worker dispatch carries the literal line: **"Calling the Agent tool is FORBIDDEN"**.
- Per-file pytest only — never whole `tests/commands/` (documented hang, FACTS.md).
- Production-shaped fixtures (the `"BK1"` hand-crafted fixture masked R-1).
- Runtime proof before "done".
- No VERSION bump; CHANGELOG `[Unreleased]` accumulation.
- ⚠️ Known autodev two-worker concurrent-build race on the rotation vertical: verify agentId + git state before judging notifications; recover via reset-to-reviewed-base.
