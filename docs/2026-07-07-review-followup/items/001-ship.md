PR: https://github.com/snowshine0216/investment-research-copilot/pull/212
Mode: A
Branch: claude/review-followup-001
Base: autodev/review-followup-feature
Title: feat(notify): data-health digest in irc notify-status (001)

Ship flow: /ship steps 0-15 completed 2026-07-07; step 16 closeout skipped via Gate 0 (.autodev-current present).
Tests at ship: 167 green across the per-file sweep (test_health 21, test_classify 35, test_notify_cmd 39, launchd flow-capture 4 + ops); bash -n + wrapper AC test; ruff clean. VERSION 0.9.3 unchanged; CHANGELOG [Unreleased] + ADR 0016 amendment + 3 READMEs synced (Task 6); TODOS deferred entries carry pickup triggers.
Review verdict: PASS-WITH-NITS (items/001-review.md; adversarial BREAKS → fixed → CLEAN). Branch head at ship: 690eb0ea.
