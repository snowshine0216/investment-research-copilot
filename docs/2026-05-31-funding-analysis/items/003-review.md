Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial), orchestrator-inline
PR: https://github.com/snowshine0216/investment-research-copilot/pull/87
Supersedes: items/003-ship-blocked.md (pre-push findings; both fixed before push)

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 3× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 2× P0 (silent swallow + silent auth-fail), 1× P1, 1× note
- adversarial general-purpose (sonnet) → verdict RISKS (P1 failure-reason-key observability)

## Findings

### FIXED pre-push (commit c9edf3a)
1. **Silent exception swallowing** — `FallbackProvider._try` wrapped the entire primary call (incl. our AkShare mapping), and `TushareProvider`/`_tushare_call` swallowed auth/network errors, all returning None with no log (an expired TUSHARE_TOKEN would degrade invisibly). Fixed: WARNING logging on every swallow (method + symbol + exception class) before returning the sentinel — degrade-to-None preserved, silence removed. Tests added (caplog).
2. **Malformed `fiscal_period`** — `_map_fina_to_digest` produced a year-only period (`"2024"`) for a non-standard Tushare `mmdd`. Fixed: degrade to None on an unrecognized period. Tests added.

### Nits → TODOS (not blocking)
- `tushare` is a HARD dependency (~60MB forced on token-absent deployments) — move to an optional-dependency extra.
- Tushare column-level schema drift silently → None (call-level now warns; column-level within a good frame doesn't) — observability follow-up.
- Token-present path records `filing_empty`/`broker_empty` instead of `filing_fetch_failed`/`broker_fetch_failed` (FallbackProvider swallows before the outer except). No output-correctness impact (no consumer keys on the distinction); dormant until a token is set; mitigated by the new swallow-logging.

### Adversarial / code-reviewer — CONFIRMED CLEAN
- No-token AkShare-only path byte-identical (byte-equality lock 3/3).
- Budget/sentinel (`FetchPlan.total_calls`, `fetch_budget_exhausted`, `FetchBudgetExceeded`) zero-diff — Tushare not metered.
- Secrets: `tushare_token` SecretStr, never logged/repr'd/in error messages.
- `default_cn_provider()` resolved once at the command edge, threaded; no module-level mutable state; stage cores stay pure. Lazy `import tushare` (never at module load).

## Test notes
- tests/fundamentals + tests/opportunity: 771 passed / 15 skipped (post-fix).
- Full suite: 2601 passed / 34 skipped / 8 failed — the 8 are the documented pre-existing failures (identical to base per items/001-ship.md); 0 new.
- ruff: clean on all item-003 files. live_tushare test triple-gated, skips offline.
