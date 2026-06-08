PR: https://github.com/snowshine0216/investment-research-copilot/pull/121
Mode: A
Branch: phase-a/legulegu-rate-limit-impl
Base: phase-a/legulegu-rate-limit
Title: feat(phase-a): legulegu broad-leg rate-limit hardening + PB-wipe guard (001)

## Ship workflow notes
- Ship tool: `/ship` (16-step), driven inline by the orchestrator.
- **Base override:** PR targets the feature branch `phase-a/legulegu-rate-limit` (non-protected), NOT `main`. `main` PR is opened separately in Phase 3 and left for the operator.
- **Step 5 (tests):** targeted offline suites (88 pass / 5 skip), not the full ~18-min not-green suite (project practice). Zero in-branch failures.
- **Step 10 (VERSION bump): SKIPPED** by project convention — VERSION stays `0.9.3`, changes accumulate under CHANGELOG `[Unreleased]` (memory `project_versioning_convention`). base VERSION == current == 0.9.3.
- **Step 11 (CHANGELOG):** already added in impl Task 7 (`47fd986`) — idempotent skip.
- **Steps 8+9 (review):** captured into `items/001-review.md`.
