PR: https://github.com/snowshine0216/investment-research-copilot/pull/78
Mode: A
Branch: claude/instrument-pickability-003
Base: autodev/instrument-pickability-feature
Title: feat(memo): QDII premium-to-NAV surfacing across §5/§6/§7 + projection (003)

Source: tier-2 `gh pr create` (deliberate — `/ship`'s VERSION/CHANGELOG/release-orientation overkill for per-item sub-PRs); review captured via 3 parallel review subagents per autodev's ship.md fallback path.

## Ship workflow steps

| Step | Outcome |
|------|---------|
| 0 — detect platform + base | GitHub; base = `autodev/instrument-pickability-feature` (non-protected) |
| 1 — preflight | branch `claude/instrument-pickability-003`, ~1100 lines added, 6 impl commits + 1 drift amendment + 1 review-fix + 1 CHANGELOG |
| 2 — distribution pipeline | `SCOPE_NEW_BINARY=false` — skipped |
| 3 — merge base | already up to date |
| 4 — test framework bootstrap | pytest present — skipped |
| 5 — run tests | `uv run pytest tests/opportunity/ tests/memo/ tests/commands/test_opportunity_cmd.py tests/commands/test_memo_cmd.py` → **846 passed, 1 skipped** |
| 6 — coverage audit | 46 new tests at impl + 5 new tests at review-fix; covers all 18 ACs + boundary semantics + nan/inf guard |
| 7 — plan completion audit | drift verdict PASS (commit `f2c3cd8`) — 14 tasks present, 3 plan amendments, 1 recorded portability concern (fixed in commit `b509385`) |
| 8 — pre-landing parallel review | code-reviewer (0 P0, 2 P1) + silent-failure-hunter (0 P0, 2 P1, 4 P2/Notes) — see items/003-review.md |
| 9 — adversarial review | 1 P0 (hardcoded cwd CI break) + 2 P1 (nan passthrough, 5% boundary coverage) — Verdict: BREAKS, reversed by in-branch fix `b509385` |
| 10 — version bump | suppressed |
| 11 — CHANGELOG | added `qdii-premium-memo-surface` entry (commit `0f0a230`) |
| 12 — TODOS.md | n/a |
| 13 — commit | impl commits + drift `f2c3cd8` + review-fix `b509385` + CHANGELOG `0f0a230` |
| 14 — push | `claude/instrument-pickability-003` → origin |
| 15 — create PR | PR #78 opened against `autodev/instrument-pickability-feature` |
