PR: https://github.com/snowshine0216/investment-research-copilot/pull/105
Mode: A
Branch: claude/cyclical-valuation-guard-001
Base: autodev/cyclical-valuation-guard-feature
Title: feat(opportunity): commodity-cyclical valuation guard + sector-PE accumulate (001)

## Ship summary
- Tool: `/ship` (orchestrator-driven, 16-step workflow).
- Step 3 merge feature base: already up to date.
- Step 5 test gate: 216 passed (scoped to touched files; full suite ~18min + not green on main, deliberately not run).
- Steps 8+9 review: captured inline → items/001-review.md (Verdict: PASS-WITH-NITS; no P0/blockers/latent bugs).
- Step 10 version bump: SKIPPED by override — VERSION stays 0.9.3; feature accumulated under CHANGELOG [Unreleased] (project convention).
- Step 11 CHANGELOG: [Unreleased] "### Added — commodity-cyclical valuation guard + sector-PE accumulate-forward".
- Base override applied: PR opened against the feature branch, NOT the protected default `main`.
