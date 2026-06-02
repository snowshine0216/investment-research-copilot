PR: https://github.com/snowshine0216/investment-research-copilot/pull/91
Mode: A
Branch: claude/eval-funds-command-001
Base: feat/eval-funds-command
Title: feat(eval-funds): targeted per-fund opportunity_state / core_dca evaluation (001)

## Ship summary (/ship 16-step workflow)

- Step 0-1 preflight: GitHub; head `claude/eval-funds-command-001`; base `feat/eval-funds-command` (non-protected ✓).
- Step 2 distribution: SCOPE_NEW_BINARY=false (`irc` entry already exists) → skipped.
- Step 3 merge base: Already up to date.
- Step 5 tests: targeted+guard-rail 58→63 passed; full suite 2651 passed / 7 pre-existing failures (proven identical on base) → no in-branch failures, non-blocking.
- Step 6 coverage: new code covered (fund_eval.py→6 tests, fund_eval_cmd.py→7 tests, inputs_build.py→guard-rail). No required-but-missing tests.
- Step 7 plan completion: drift verdict already confirmed 33/33 steps DONE.
- Step 8+9 review: 3 reviewers (code-reviewer + silent-failure-hunter + adversarial). No P0; 4 latent edge bugs FIXED pre-push (commit `9ad77a2`). Verdict captured in items/001-review.md → PASS-WITH-NITS.
- Step 10 version: NO bump — project convention is `[Unreleased]` accumulation at static VERSION 0.9.3.
- Step 11 changelog: `[Unreleased] → Added — eval-funds` entry added (house style).
- Step 12 TODOS: 2 pre-existing reliability follow-ups recorded.
- Step 13-15: committed (feature 5 commits + fix `9ad77a2` + docs/review), pushed, PR #91 opened.

Review verdict file: items/001-review.md (Verdict: PASS-WITH-NITS)
