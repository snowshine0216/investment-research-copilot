# MASTER-PLAN — Monitor CN-egress data-plane light-up

Mode: spec
Project type: non-web   # Python CLI/data tool → post-ship verifier is /verify (never /qa)
PR shape: A             # per-item PRs (no --rollup in the invocation)
Feature branch: autodev/monitor-cn-egress-lightup-feature  (synthesized off main; no protected-branch opt-in this turn — roll-up PR opened at Phase 3, NOT merged)
Sub-branch: claude/monitor-cn-egress-lightup-001
Item order: 001 (N=1)

## Skill skips (spec mode)

- `superpowers:brainstorming` — ⏭️ skipped (user authored the spec)
- `grill-with-docs` — ⏭️ pre-completed (spec header: "grilled 2026-07-02"; orchestrator must not auto-invoke)
- `superpowers:writing-plans` — RUNS (Opus subagent → `items/001-plan.md`)
- `superpowers:subagent-driven-development` — RUNS (Sonnet impl)
- drift → `/ship` → (`/verify` ‖ `/code-review`) → fix → merge — all run unchanged

## Workflow rules pinned for this run

- Every subagent dispatch declares `model=` explicitly: plan=opus; impl/drift/verify/pr-review/fix=sonnet.
- Merge gate requires: `001-plan.md` + `001-drift.md` (PASS) + `001-ship.md` (PR URL) + `001-verify.md` (PASS) + `001-review.md` (PASS|PASS-WITH-NITS, inline from /ship) + `001-pr-review.md` (PASS|PASS-WITH-NITS). Grill verdict absent-OK (⏭️ user-grilled).
- Item PR base = the feature branch (never main). `gh pr merge --squash --delete-branch` after the gate.
- Repo-specific: NO VERSION bump (accumulate under CHANGELOG [Unreleased] — project versioning convention); `pytest tests/commands/` whole-dir HANGS — run per-file; live EastMoney probes only via python requests, never curl; never retry EastMoney while it is blocking.
- Spec §5 Slice 0 (live spike re-run) is an ops-gated step: it gates slices 3–5 per the spec but requires live market-hours probes (15:45 CST across ≥3 days). Handling decided at plan time — the plan must not silently drop the gate.
