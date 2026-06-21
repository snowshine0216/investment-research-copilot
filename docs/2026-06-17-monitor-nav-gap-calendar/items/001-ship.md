PR: https://github.com/snowshine0216/investment-research-copilot/pull/162
Mode: A
Branch: claude/monitor-nav-gap-calendar-001
Base: main
Title: feat(monitor): calendar-grounded nav_quality NAV-gap check (supersedes #158 heuristic)

Note: per user instruction this turn ("rebase your pr against main"), the PR targets `main`
directly (not the autodev feature branch). The autodev run-dir bookkeeping was untracked from the
branch (`git rm --cached`, kept on disk) so the PR to main contains only deliverables: 15 files
(CHANGELOG, ADR 0018, 5 src, 8 tests). VERSION not bumped (project convention: accumulate under
CHANGELOG [Unreleased] at static VERSION).
