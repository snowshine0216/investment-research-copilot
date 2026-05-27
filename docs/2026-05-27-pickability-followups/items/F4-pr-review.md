Verdict: FAIL

Source: /code-review on PR #80
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/80#pullrequestreview-4371707414
Findings: 2
  - src/irc/scoring/news_summaries.py:54 — latent-bug — _summary_for_theme returns full formatted markdown (header + citations section) rather than just LLM prose. load_theme_reports reads the .md file written by format_report_markdown, which has the shape "# theme\n\n{prose}\n\n## Citations\n[1] title — url". A report with neutral prose but citation title "Fed signals buy to support bonds" scores 85.0 instead of ~50.0 (confirmed by runtime test: catalyst_count=4, momentum=1.0 from citation keywords alone). gold_cmd._summary_from_theme_report already solves this by skipping lines starting with "#" but that logic is not reused.
  - src/irc/scoring/news_summaries.py:43 — latent-bug — _summary_for_theme duplicates prose-extraction logic already in gold_cmd._summary_from_theme_report but without the header-skipping guard that makes it correct. gold_cmd._summary_from_theme_report iterates splitlines(), skips "#" lines, and returns the first non-empty paragraph. _summary_for_theme does none of this.

Root cause: load_theme_reports reconstructs ThemeReport.report_md from the formatted .md file on disk (written by format_report_markdown), which wraps the original LLM prose in "# theme\n\n{prose}\n\n## Citations\n{cit_lines}\n". The unit tests for build_news_summaries use a _report() helper that constructs ThemeReport directly with bare prose, so they never exercise the disk round-trip and do not catch this.
