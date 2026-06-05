PR: https://github.com/snowshine0216/investment-research-copilot/pull/116
Mode: A
Branch: claude/phase-a-index-grounding-001
Base: claude/stupefied-banach-f1f037
Title: feat(phase-a): broad-index PE-TTM valuation grounding (001)

## Ship provenance
- Tool: `/ship` (orchestrator-driven), with autodev overrides:
  - **VERSION bump SKIPPED** (step 10) — spec gate #6 + project convention (accumulate under CHANGELOG `[Unreleased]`, no per-feature bump). VERSION stays `0.9.3`.
  - **CHANGELOG SKIPPED** (step 11) — already written by impl Task 10 under `[Unreleased]`.
  - Base overridden to the non-protected feature branch `claude/stupefied-banach-f1f037` (not `main`).
- Steps 8+9 review: captured inline → [`001-review.md`](001-review.md) (`PASS-WITH-NITS`; latent bug found & fixed pre-push in `39dbf7f`).
- Feature branch fast-forwarded on origin before opening the PR so the per-item diff is clean.
