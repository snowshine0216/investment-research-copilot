PR: https://github.com/snowshine0216/investment-research-copilot/pull/137
Mode: A
Branch: claude/monitor-eval-m2-001
Base: claude/xenodochial-cohen-339150
Title: feat(monitor-eval): M2 deterministic rigor — property/oracle suite + deterministic_scoring panel (001)

Ship tool: /ship (orchestrator-driven, autodev overrides)
- Base overridden to the feature branch (not main).
- VERSION NOT bumped (project convention: accumulate features under CHANGELOG [Unreleased]).
- CHANGELOG [Unreleased] entry added.
- Steps 8+9 review captured inline → items/001-review.md (Verdict: PASS after pre-push fix b2e093f).
- Pre-push fix round 1 (b2e093f): 3 latent/robustness findings; see items/001-ship-blocked.md + items/001-review.md.

Tests at ship: tests/monitor + tests/spend = 399 passed, 8 skipped; ruff clean on touched paths.
tests/commands 80 failures are pre-existing (missing src/irc/templates/config/monitor.yaml; identical on feature base).
