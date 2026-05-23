# Item 008 Drift Log

Production fixes surfaced by `tests/integration/test_publishable_set_lockdown.py` per Q6 inline-fix policy.

Each entry: `- <date> <commit-sha> fix(<scope>): <one-line description>`

- 2026-05-23 TBD fix(opportunity): register fund_announcements_unavailable in RejectionReasonCode + _GAP_TO_REASON (gap code emitted by snapshot.py:223 but missing from rejection_log.py dict — latent RuntimeError crash)
