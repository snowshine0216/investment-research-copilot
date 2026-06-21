PR: https://github.com/snowshine0216/investment-research-copilot/pull/172
Mode: A
Branch: claude/monitor-dual-track-valuation-001
Base: autodev/monitor-dual-track-valuation-feature
Title: feat(monitor): dual-track per-stock valuation + False-Cheap clamp (001)

## Ship workflow notes (project adaptations)
- **Base = the synthesized feature branch** (NOT `main` — no "merge to main" opt-in this turn). Verified via `gh pr view 172`.
- **No VERSION bump** — project convention (memory: accumulate under CHANGELOG `[Unreleased]` at static VERSION; don't bump per feature PR). CHANGELOG `[Unreleased]` updated instead.
- **Tests scoped** to the touched monitor/commands surface (full suite is ~61 min, known-red with e2e hangs per project baseline). `tests/monitor/` 688 pass, `tests/monitor/eval/` 258 pass, `tests/commands/test_monitor_cmd*` per-file green, ruff clean.
- **Steps 8+9 review** captured inline → [`items/001-review.md`](001-review.md) (Verdict: PASS-WITH-NITS — 2 blockers found + fixed before push, re-review CLEAN).
