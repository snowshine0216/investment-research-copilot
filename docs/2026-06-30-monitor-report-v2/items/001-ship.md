PR: https://github.com/snowshine0216/investment-research-copilot/pull/186
Mode: A
Branch: claude/monitor-report-v2-001
Base: claude/wizardly-shamir-60a599
Title: feat(monitor): report v2 — market-composite anchor + news overlay, charts, citations, 限购 (001)

## /ship workflow notes
- Base overridden to the feature branch (autodev rule) — NOT the repo default `main`.
- VERSION NOT bumped (stays 0.9.3) — project convention: features accumulate under CHANGELOG
  `[Unreleased]` at static VERSION (commit `docs(changelog): … (no VERSION bump)`).
- Tests scoped to this change's suites (full pytest hangs ~61min/e2e-hours per documented baseline);
  1072 passed + 1 pre-existing unrelated arch failure.
- Steps 8+9 review captured inline → items/001-review.md (PASS-WITH-NITS; 1 blocker + 3 minors fixed
  pre-push, 3 P2 deferred).
