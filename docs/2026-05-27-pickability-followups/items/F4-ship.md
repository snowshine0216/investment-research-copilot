PR: https://github.com/snowshine0216/investment-research-copilot/pull/80
Mode: A
Branch: claude/pickability-followups-F4
Base: autodev/pickability-followups-feature
Title: feat(scoring): wire thesis_news real-content scoring via news_summaries (F4)

Source: /ship (16-step workflow)
Workflow notes:
- Step 5 tests: 2417 passed, 7 failed (all 7 pre-existing on the feature branch; documented in prior pickability run's `run-final-verify.md`; none introduced by F4)
- Step 8 review fired the silent-failure hunter, which surfaced a P1 observability gap (no signal when `build_news_summaries` returns all-empty tuples). Fixed inline in commit `43662e6` by adding a `news coverage: <k>/<N> instruments` print line at the score_cmd boundary. Test added: `test_score_cmd_run_score_logs_news_coverage`.
- Step 9 adversarial: RISKS (0 P0, 2 P1 — race condition + OOM-on-huge-reports). Both noted in PR body.
- Step 10 version bump: PATCH 0.9.0 → 0.9.1 (internal plumbing, no public API change).
- Step 11 CHANGELOG: new `thesis-news-scoring-plumbing` entry under [Unreleased].

Final commit on branch: aaec0b5
