# TODOS

Known gaps and deferred work. Updated after Plan 3 ship (2026-05-08).

## Security

- [ ] **SSRF DNS-bypass** — `_validate_base_url()` checks IP literals only; a hostname that resolves to 169.254.169.254 at runtime bypasses the guard. Fix: DNS-resolve at call time in `http_client._post_request()` and verify the resolved IP. (adversarial-review finding 1)
- [ ] **Remaining plain-str secrets** — `anthropic_api_key`, `tushare_token`, `ldr_api_token`, `openbb_fmp_key`, `openbb_tiingo_key` are plain `str` in `Settings`. Upgrade to `SecretStr` when those providers are activated in Plan 2+. (adversarial-review finding 5)
- [ ] **Two-hop prompt injection** — raw refs pass through synthesizer and then into auditor prompt; a crafted ref could manipulate the audit result. Add a sanitization boundary before the auditor pass. (adversarial-review finding 11)
- [ ] **Unbounded question length in `ask_cmd`** — no max length on user question; a 100k-char question would be injected directly into the LLM prompt. Add `MAX_QUESTION_LEN = 2000` guard. (adversarial-review finding 13)

## Reliability

- [ ] **No aggregate timeout** — worst-case `retry_call_chat()` wall time is 3 min (5 × 30s + 2+4+8+16s waits). Add a `deadline_s` or `asyncio.timeout` guard for batch runs. (adversarial-review finding 7)
- [ ] **`sign==0` always "downtrend"** — `regime_detect.py` linear regression slope on short new-issue history gives sign=0 which defaults to "downtrend". Minor: only affects ETFs < 60 days old. (adversarial-review finding 2)
- [ ] **`compute_gold_score` KeyError on config drift** — hardcoded driver names like `"real_yield"` may diverge from config keys; a renamed config key would cause silent KeyError. Add explicit key validation. (adversarial-review finding 8)

## Coverage gaps

- [ ] `config_loader._resolve_schema` — `KeyError` path when schema is not registered (100% happy-path only)
- [ ] `settings.py` — `OPENROUTER_API_KEY` missing path
- [ ] `schemas/triggers.py` — invalid comparator branch (~50% coverage)
- [ ] `schemas/overrides.py` — populated override lists (~50% coverage)
- [ ] `schemas/gold.py` — direction enum variants beyond "up"
- [ ] `schemas/discovery.py` — quality filter edge cases

## Performance (Plan 3)

- [x] **Sequential LLM calls in scoring**: `score_macro_fit` called once per instrument in a for-loop (blocking HTTP). Parallelized with `ThreadPoolExecutor` in `run_scoring()` (ship 2026-05-08).
- [ ] **Sequential LLM calls in discovery**: `write_reason` called per role × instrument. Same fix as above. (ship review 2026-05-08)
- [ ] **`fetch_fund_metadata` / `fetch_etf_metadata` download full tables per call**: cache with `functools.lru_cache` or pass pre-fetched DataFrame from the caller. (ship review 2026-05-08)

## Reliability (Plan 2+)

- [x] **`ingest` aborts on single instrument failure**: one bad ticker killed the entire run — changed to skip-and-warn (`_log.warning + continue`) in `_fetch_metadata_by_id()` (ship 2026-05-08).
- [ ] **`write_reason` silent failure**: bare `except Exception: pass` swallows all LLM errors; `run_discover` returns 0 even when 0 candidates found. Add structured logging for retried/failed instruments. (adversarial-review 2026-05-08)
- [ ] **`fetch_fund_metadata` wrong record on miss**: falls back to `df.iloc[0]` when fund_code not found, returning metadata for a different fund. Raise `ValueError` or return `{}` instead. (adversarial-review 2026-05-08)
- [ ] **Mixed-date fallback** — `run_memo` silently reads scoring/gold/allocation from different calendar dates when outputs are stale; two dates appear in one memo. Add explicit staleness check or warn clearly. (adversarial-review finding 14)

## Design / Tech debt

- [ ] **`tracking_error` stub in `metrics.py`** — `derive_discovery_metrics` always emits `tracking_error=0.0`; quality filter's tracking-error branch never fires. Implement rolling-std-of-returns-minus-benchmark in Plan 4. (code-review 2026-05-08)
- [ ] **4/6 gold score drivers hardcoded** — `real_yield`, `dxy`, `cb_purchases`, `geopolitical_stress` are constants in `gold_score.py`; only `vol_ratio` and `adx` use live data. Activate remaining live drivers in Plan 4. (adversarial-review finding 3)
- [ ] **Correlation filter permanently disabled** — `allocation/pipeline.py` always skips correlation filter until correlation data is available in Plan 4. Weights are not renormalized after the filter runs (moot until activated). (adversarial-review findings 4+5)
- [ ] **`ChatResponse.raw` unbounded** — full LLM response body stored in frozen dataclass. Remove or make optional before any serialization path is added (Plan 4). (adversarial-review finding 11)
- [ ] **Portfolio target tolerance** — `PreferencesFile` uses ±2% sum tolerance vs 1e-6 for system configs. Tighten to 1e-4 when financial-accuracy requirements are confirmed.
- [ ] **`FailureKind.OK` dead code** — `classify_failure()` returns `OK` for 2xx but `HTTPStatusError` is never raised on 2xx. Remove or document.
- [ ] **Tenacity decorator rebuilt per call** — rebuild once at module level to reduce per-call allocation overhead in batch runs.


## Security

- [ ] **SSRF DNS-bypass** — `_validate_base_url()` checks IP literals only; a hostname that resolves to 169.254.169.254 at runtime bypasses the guard. Fix: DNS-resolve at call time in `http_client._post_request()` and verify the resolved IP. (adversarial-review finding 1)
- [ ] **Remaining plain-str secrets** — `anthropic_api_key`, `tushare_token`, `ldr_api_token`, `openbb_fmp_key`, `openbb_tiingo_key` are plain `str` in `Settings`. Upgrade to `SecretStr` when those providers are activated in Plan 2+. (adversarial-review finding 5)

## Reliability

- [ ] **No aggregate timeout** — worst-case `retry_call_chat()` wall time is 3 min (5 × 30s + 2+4+8+16s waits). Add a `deadline_s` or `asyncio.timeout` guard for batch runs. (adversarial-review finding 7)

## Coverage gaps

- [ ] `config_loader._resolve_schema` — `KeyError` path when schema is not registered (100% happy-path only)
- [ ] `settings.py` — `OPENROUTER_API_KEY` missing path
- [ ] `schemas/triggers.py` — invalid comparator branch (~50% coverage)
- [ ] `schemas/overrides.py` — populated override lists (~50% coverage)
- [ ] `schemas/gold.py` — direction enum variants beyond "up"
- [ ] `schemas/discovery.py` — quality filter edge cases

## Performance (Plan 3)

- [x] **Sequential LLM calls in scoring**: `score_macro_fit` called once per instrument in a for-loop (blocking HTTP). Parallelized with `ThreadPoolExecutor` in `run_scoring()` (ship 2026-05-08).
- [ ] **Sequential LLM calls in discovery**: `write_reason` called per role × instrument. Same fix as above. (ship review 2026-05-08)
- [ ] **`fetch_fund_metadata` / `fetch_etf_metadata` download full tables per call**: cache with `functools.lru_cache` or pass pre-fetched DataFrame from the caller. (ship review 2026-05-08)

## Reliability (Plan 2+)

- [x] **`ingest` aborts on single instrument failure**: one bad ticker killed the entire run — changed to skip-and-warn (`_log.warning + continue`) in `_fetch_metadata_by_id()` (ship 2026-05-08).
- [ ] **`write_reason` silent failure**: bare `except Exception: pass` swallows all LLM errors; `run_discover` returns 0 even when 0 candidates found. Add structured logging for retried/failed instruments. (adversarial-review 2026-05-08)
- [ ] **`fetch_fund_metadata` wrong record on miss**: falls back to `df.iloc[0]` when fund_code not found, returning metadata for a different fund. Raise `ValueError` or return `{}` instead. (adversarial-review 2026-05-08)

## Design / Tech debt

- [ ] **`tracking_error` stub in `metrics.py`** — `derive_discovery_metrics` always emits `tracking_error=0.0`; quality filter's tracking-error branch never fires. Implement rolling-std-of-returns-minus-benchmark in Plan 3 before connecting real `tracking_error_max` config. (code-review 2026-05-08)
- [ ] **`ChatResponse.raw` unbounded** — full LLM response body stored in frozen dataclass. Remove or make optional before any serialization path is added (Plan 2+). (adversarial-review finding 11)
- [ ] **Portfolio target tolerance** — `PreferencesFile` uses ±2% sum tolerance vs 1e-6 for system configs. Tighten to 1e-4 when financial-accuracy requirements are confirmed.
- [ ] **`FailureKind.OK` dead code** — `classify_failure()` returns `OK` for 2xx but `HTTPStatusError` is never raised on 2xx. Remove or document.
- [ ] **Tenacity decorator rebuilt per call** — rebuild once at module level to reduce per-call allocation overhead in batch runs.
