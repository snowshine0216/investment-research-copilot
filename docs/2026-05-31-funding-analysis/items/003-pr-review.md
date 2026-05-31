Verdict: PASS-WITH-NITS
Source: /code-review on PR #87 (round 3, final)
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/87#issuecomment-4586597951
Round-1 (_to_ts_code BJ): RESOLVED (3ddbb3c)
Round-2 (DEEPSEEK coupling): RESOLVED (e75b29a)
Findings (round 3): 1
  - src/irc/opportunity/valuation_fundamental.py:61 — nit — `assert inp.consensus_upside_pct is not None` in production code; assert is silently stripped under `python -O`, making the precondition invisible at runtime. The caller guard in states.py already ensures the invariant; drop the assert or replace with an explicit early-return guard.
