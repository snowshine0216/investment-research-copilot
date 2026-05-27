Verdict: FAIL

Source: /code-review on PR #80 (round 2 — after fix 45c715b)
Round 1: FAIL — see commit history; both findings fixed in 45c715b
Round 2 PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/80#issuecomment-4553837265
Findings: 3
  - src/irc/research/geopolitical_stress.py:93 — latent-bug — geopolitical_stress_from_theme_report reads report.report_md verbatim (same citation-contamination class as the round-1 blocker). Citation titles containing 'war', 'sanction', 'escalation', 'ceasefire' falsely shift the geo-stress score: confirmed live — neutral prose + stress citation titles yields geo_stress=0.70 vs correct 0.40. Flows into GoldDriverInputs.geopolitical_stress_0to1 → compute_gold_score. Fix: call extract_prose_from_report_md before _count_hits, same pattern as the two callers already fixed.
  - src/irc/research/persistence.py:32 — latent-bug — extract_prose_from_report_md stops at ANY '## ' heading, not only '## Citations'. LLM prompt in synthesize.py does not forbid ## subheadings; real LLM output commonly uses '## Key Risks', '## Outlook' etc. A prose block starting with '## Key Drivers\nDemand rising.\n## Key Risks\nEscalation.' returns '' (breaks at first ##), silently feeding score_thesis_news an empty string and producing the neutral-50 fallback the PR aimed to eliminate.
  - tests/research/test_persistence.py — nit — No dedicated unit tests for the new extract_prose_from_report_md helper. Unexercised edge cases include ##Citations-no-space (citation lines after it leak into prose), ## subheadings in prose body, and failure-report passthrough.
