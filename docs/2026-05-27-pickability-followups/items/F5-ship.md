PR: https://github.com/snowshine0216/investment-research-copilot/pull/81
Mode: A
Branch: claude/pickability-followups-F5
Base: autodev/pickability-followups-feature
Title: feat(memo): deepen §2 macro excerpts via skip-list + paragraph accumulator (F5)

Source: /ship (16-step workflow, orchestrator-driven)
Workflow notes:
- Step 5 tests (excluding tests/integration, tests/e2e, tests/llm): 2362 passed, 5 failed, 13 skipped. All 5 failures verified pre-existing on the F5 base (`autodev/pickability-followups-feature`) by checking out the base and re-running the same tests. None introduced by F5.
- Step 8 code-reviewer: 0 P0, 1 P1 (function-length soft ideal violation accepted).
- Step 8 silent-failure hunter: 2 P0 + 2 P1 + 3 notes. **Both P0s FIXED inline in commit 997e418** (distinct over-skip sentinel + LLM `[N]` marker stripping). P1 #3 auto-resolved by P0 #2 fix. P1 #4 (failure_reason KeyError potential) noted for future hardening; the failure_reason branch is unchanged by F5 itself.
- Step 9 adversarial: Not dispatched separately — silent-failure-hunter's depth covered the same surface, and the P0 fixes addressed the core findings.
- Step 10 version bump: PATCH 0.9.1 → 0.9.2 (renderer policy change; internal logic only).
- Step 11 CHANGELOG: new `macro-research-excerpt-depth` entry under [Unreleased].

Recovery note: the F5 impl subagent's socket connection dropped after 24 min mid-implementation (agent ID a159c7eb8007d5a1b). The working-tree changes (134 lines in gold_cmd.py + 302 lines in test_gold_cmd.py) were intact and recovered by the orchestrator. Targeted tests (20/20 in test_gold_cmd.py) + ruff (clean) were verified before commit `51144b4`. The drift check (commit `fb9c659` + `d2bb8b2`) subsequently verified the diff matches the F5-plan with only minor amendable findings.

Final commit on branch: 793773c
