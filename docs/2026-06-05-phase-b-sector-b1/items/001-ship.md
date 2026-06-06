PR: https://github.com/snowshine0216/investment-research-copilot/pull/114
Mode: A
Branch: claude/phase-b-sector-b1-001
Base: claude/relaxed-jemison-629597
Title: feat(opportunity): Phase B B1 sector-index PE onboarding (activation OFF) (001)

## Ship summary (/ship workflow)
- Platform: GitHub. Base overridden to the feature branch (autodev rule — never `main`).
- Step 3 merge-base: "Already up to date" (sub-branch cut from feature tip; no conflicts).
- Step 5 tests: 183 relevant tests pass (90 touched + 37 schema/trades/wiring + 56 opportunity_cmd/H3), 0 in-branch regressions. The whole-directory run hangs on a pre-existing/unrelated test (documented non-green baseline) — noted, non-blocking per /ship failure-triage. ruff clean on changed files.
- Steps 8+9 review: captured to [items/001-review.md](001-review.md) (Verdict: PASS-WITH-NITS). One latent silent-failure (config validation) fixed pre-push (commit 241ffee).
- Step 10 VERSION bump: SKIPPED (project convention — accumulate under CHANGELOG [Unreleased]; VERSION stays 0.9.3). PR title drops the version prefix accordingly.
- Step 11 CHANGELOG: [Unreleased] B1 entry present (impl) + validator note appended.
- Step 12 TODOS.md: not modified (B1 recorded in CHANGELOG + ROADMAP; avoided post-drift scope creep).
