PR: https://github.com/snowshine0216/investment-research-copilot/pull/128
Mode: A
Branch: claude/monitor-daily-report-001
Base: autodev/monitor-daily-report-feature
Title: feat(monitor): irc monitor daily brief + configurable LLM routing + schedule rework (001)

## Ship summary
- Primary tool: `/ship` workflow driven by orchestrator with two project adaptations: base overridden to the
  feature branch (not `main`); VERSION NOT bumped (project convention — features accumulate under CHANGELOG
  [Unreleased] at static VERSION 0.9.3); tests run feature-scoped (the bare 61-min suite has ~24 documented
  pre-existing failures unrelated to this branch).
- Steps 8+9 review captured inline → items/001-review.md (PASS-WITH-NITS). The review surfaced a P0 (command
  crashed on real run) + P1s; all fixed over 3 fix rounds BEFORE the PR was opened (ship.md "review can demand
  fixes before push" path; provenance in items/001-ship-blocked.md).
- Docs already updated by impl Phase K (README, ops/launchd/README, CLAUDE.md, CHANGELOG [Unreleased]).
- Final feature-scoped suite at push: 353 passed / 11 skipped.
