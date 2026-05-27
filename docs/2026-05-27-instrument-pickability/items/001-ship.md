PR: https://github.com/snowshine0216/investment-research-copilot/pull/76
Mode: A
Branch: claude/instrument-pickability-001
Base: autodev/instrument-pickability-feature
Title: feat(opportunity): emit advisory gap top_holdings_broker_thin (001)

Source: /ship (16-step workflow) — invoked via Skill(skill="ship") inside autodev's orchestrator
Tier: 1 (primary)

## Ship workflow steps

| Step | Outcome |
|------|---------|
| 0 — detect platform + base | GitHub; base = `autodev/instrument-pickability-feature` (overridden via --base, valid non-protected) |
| 1 — preflight | branch `claude/instrument-pickability-001`, 17 files / 719+15 lines, 12 impl commits + 4 review-fix commits |
| 2 — distribution pipeline | `SCOPE_NEW_BINARY=false` — skipped |
| 3 — merge base | already up to date |
| 4 — test framework bootstrap | pytest present — skipped |
| 5 — run tests | `uv run pytest tests/opportunity/ tests/memo/ tests/commands/` → **758 passed, 1 skipped** (post review fixes) |
| 6 — coverage audit | 30 new tests at impl + 9 new tests at review-fix; covers boundary, JSON roundtrip, demotion, propagation; ruff clean on touched files |
| 7 — plan completion audit | drift verdict PASS (commit `8856ab0`) — all 11 plan tasks present in diff |
| 8 — pre-landing parallel review | code-reviewer (0 P0, 4 P1) + silent-failure-hunter (0 P0, 1 P1) — see items/001-review.md |
| 9 — adversarial review | 1 P0 found (advisory_gaps not propagated to discipline_report) + 1 P1 (reconstruct drops field) + 1 P1 (dup sort, deferred) — see items/001-review.md |
| 10 — version bump | suppressed via --no-version-bump (per-item sub-PR; rollup PR will bump) |
| 11 — CHANGELOG | added `top-holdings-broker-thin-advisory` entry under [Unreleased] (commit `8f251df`) |
| 12 — TODOS.md | n/a (no TODOS.md present) |
| 13 — commit | impl commits (Phase 2 step 5) + review-fix commits (`2d3a1a3` review fixes, `f8b19e3` iid fix, `8f251df` CHANGELOG) |
| 14 — push | `claude/instrument-pickability-001` → origin, force-disabled |
| 15 — create PR | PR #76 opened against `autodev/instrument-pickability-feature` |

## Pre-existing failures unchanged (in PR body)

- `test_qdii_appears_in_rejections_with_qdii_reason`
- `test_memo_cites_only_publishable_citation_ids`
- `test_build_rows_qdii_row_carries_sentinel_gap`

All three are in the QDII path that item 003 (QDII premium snapshot) will address.
