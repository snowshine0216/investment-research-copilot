PR: https://github.com/snowshine0216/investment-research-copilot/pull/132
Mode: A
Branch: claude/monitor-eval-m0-m1-001
Base: monitor-eval
Title: feat(monitor): M0 eval spine — trace/gate/ledger + monitor_signal eval (001)

## /ship workflow notes
- Base overridden to the feature branch `monitor-eval` (non-protected) — not the default `main`.
- Merge base: already up to date.
- Tests (step 5): in-branch focused suite green (135 passed); broader ~61min suite has 24 known
  pre-existing failures (project baseline), none in-branch.
- Steps 8+9 review found a blocker + 5 real bugs in new code → all fixed pre-push (fix round 1,
  c095f74..e8750b2); review verdict captured in items/001-review.md (PASS).
- Version: no bump (static VERSION 0.9.3; CHANGELOG [Unreleased] entry added) per project convention.
- Review verdict: items/001-review.md (PASS).
