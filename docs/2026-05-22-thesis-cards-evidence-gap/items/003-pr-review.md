Verdict: PASS-WITH-NITS

Source: /code-review on PR #57 (round 2 after fix commit e1017a2)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/57#issuecomment-4524038922
Round 1 findings (resolved):
  - src/irc/fundamentals/akshare_fundamentals.py:316 — `sample = latest.iloc[0]` raised IndexError on all-NaN quarter column — resolved in e1017a2: `non_null = df[quarter_col].dropna()` guard added; all-NaN branch now emits holdings with `("", "")` metadata; 2 regression tests added
  - src/irc/fundamentals/akshare_fundamentals.py:91 — single-char `'京'` in `_BJ_TOKENS` falsely matched `'南京'` — resolved in e1017a2: tokens replaced with `("北交所", "北证", "京交所")`; 3 regression tests added
  - src/irc/fundamentals/akshare_fundamentals.py:112 — `_parse_exchange_from_ticker` routed 5xxx codes to UNKNOWN instead of SH — resolved in e1017a2: `head in ("5", "6")` check; regression tests for 512000/510300/588000 added
Round 2 findings: 3
  - src/irc/opportunity/thesis_evidence.py:277 — latent-bug — removing cn_equity_fund from NON_INDEXABLE_ASSET_CLASSES causes wrong gap label ('constituent_missing' instead of 'constituent_not_applicable') when IRC_OPPORTUNITY_AUTOBUILD=0 or cache is absent; _classify_constituent_gap falls through to snapshot=None path and returns the wrong label
  - src/irc/fundamentals/akshare_fundamentals.py:7 — nit — module-level docstring guarantees "all public functions never raise" but fetch_cn_stock_news and fetch_hk_stock_news intentionally propagate exceptions per P1-c; misleads future callers who skip try/except based on the module contract
  - src/irc/commands/opportunity_cmd.py:900 — nit — con.close() called twice when FetchBudgetExceeded or FetchLockBusy is raised (once in the except block, once in the outer finally); benign with DuckDB but redundant

Reviewer: independent second-pass (Sonnet 4.6)
Effort: high · Angles: 3 (line-by-line, removed-behavior, cross-file) · Candidates before dedup: 8 · Survivors: 3
Prior bugs: all 3 confirmed resolved with regression tests passing.
