# 003 — /ship steps 8+9 review findings (pre-push)

Captured before the PR opens (ship.md "review can demand fixes before push"). Routed through a fix subagent; superseded by `items/003-review.md` once the PR opens clean.

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 3× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 2× P0 (silent swallow + silent auth-fail), 1× P1, 1× note
- adversarial general-purpose (sonnet) — verdict RISKS (P1 failure-reason-key observability)

## Findings to fix pre-push

### FIX 1 — silent exception swallowing masks real errors + auth failures (observability)
`FallbackProvider._try` (`src/irc/fundamentals/provider.py`) is a bare `except Exception: return <sentinel>` wrapping the ENTIRE primary call — including AkShareProvider's own mapping/parsing. A KeyError/TypeError from a renamed column or our own code is swallowed as a "primary miss" → silently tries Tushare → None, with NO log. Likewise `TushareProvider`'s methods / `_tushare_call` (`tushare_provider.py`) swallow auth/network errors: an expired/invalid `TUSHARE_TOKEN` degrades every fetch to None silently, operator unaware (and it's only exercised when AkShare misses, so doubly invisible).
The degrade-to-None contract is intentional (ADR 0010 / 0009) — keep returning None — but the SILENT part must end. **Fix:** add WARNING-level logging on every swallow in `FallbackProvider._try` (with a context label: method + symbol/key) AND in the Tushare swallows (TushareProvider methods / `_tushare_call`), using the project's logging convention (see `src/irc/observability/`). Return values UNCHANGED (None/()), so the AkShare-only byte-equality lock still holds (logs only fire on the except branch; the lock's success path emits none). Add a test asserting a swallowed primary exception emits a warning and still returns the sentinel.

### FIX 2 — malformed `fiscal_period` for non-standard Tushare end_date (correctness)
`tushare_provider.py` `_map_fina_to_digest` / `_period_from_end_date`: `quarter_map.get(mmdd, "")` returns `""` for an unrecognized `mmdd` (e.g. a restatement row), yielding `fiscal_period = "2024"` (no quarter) — a silently malformed value reaching `FilingDigest.fiscal_period` that downstream `[ref:...]`/period regex parsers would misread. **Fix:** when the period can't be resolved (mmdd not in {1231,0331,0630,0930}), return None from the mapper (degrade cleanly) rather than emit a malformed period. Add a test (unrecognized mmdd → None; 0331 → `...Q1`; 1231 → `...FY`).

## Accepted / noted → TODOS (NOT fixed now)
- `tushare` added as a HARD dependency (pyproject `dependencies`) — forces a ~60MB install on token-absent deployments. Consider moving to `optional-dependencies` (`[tushare]` extra). Kept hard for V1 (import always resolves → no ModuleNotFoundError path). → TODOS.
- Tushare column drift (`pe`/`pb`/`dividend_yield` candidate-set misses) silently → None — same family as item-001/004 schema-drift TODOs. → TODOS (FIX 1's logging partially covers the call-level failures; column-level drift within a successful frame is separate).
- Failure-reason key on the TOKEN-PRESENT path changes `filing_fetch_failed:…`/`broker_fetch_failed:…` → `filing_empty`/`broker_empty` (FallbackProvider swallows the AkShare exception before the outer `_evidence_for_constituent` except fires). Adversarial confirmed NO output-correctness impact (no downstream code keys on the distinction; advisory_gaps only checks `broker_empty:*`); dormant until a token is set. → TODOS (observability).
- `_build_rows(provider: CnFundamentalsProvider)` has no default — intentional DI (always supplied at the command edge; adding a lazy default would move a Settings-read out of the edge). Left as-is.

## Confirmed CLEAN (adversarial + code-reviewer)
- No-token AkShare-only path byte-identical (byte-equality lock). Budget/sentinel (`FetchPlan.total_calls`, `fetch_budget_exhausted`, `FetchBudgetExceeded`) zero-diff. Secrets: `tushare_token` SecretStr, never logged/repr'd/in error messages. `default_cn_provider()` resolved once at the edge, threaded; no module-level mutable state. Stage cores stay pure.
