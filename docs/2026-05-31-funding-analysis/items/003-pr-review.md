Verdict: PASS-WITH-NITS
Source: /code-review on PR #87
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/87#pullrequestreview-4396792503
Findings: 3
  - src/irc/fundamentals/tushare_provider.py:57 — latent-bug — `_to_ts_code` maps Beijing-exchange (BJ) stock codes (head digit '4' or '8') to `.SZ` suffix instead of `.BJ`; Tushare's `fina_indicator` / `report_rc` receives wrong ts_code (e.g. `430047.SZ` instead of `430047.BJ`), returning empty frame or mismatched data. Tushare-only path, token-gated, degrades to None gracefully. Fix: add `head in ('4', '8') → '.BJ'` to match `akshare_fundamentals._parse_exchange_from_ticker:118-119`.
  - src/irc/fundamentals/tushare_provider.py:167 — nit — `dividend_yield` unit convention is undocumented; Tushare `dv_ratio` is stored as raw percentage points (e.g. 2.5 = 2.5%) via `_coerce_float`, same as AkShare's path — both are consistent today, but no comment states the expected unit. Add a comment to `IndexValuation` or the mapping function.
  - src/irc/fundamentals/tushare_provider.py:173 — nit — `_INDEX_TS_CODE` covers only 4 of the 9 `_BROAD_INDEX_KEYS` (missing `csi1000`, `csi_a500`, `star50`, `csi_dividend`, `csi_dividend_lc`); Tushare fallback is inert for those 5 indices even with a valid token. No crash; degrade-to-None by design, but the fallback adds no value for the majority of broad indices.
