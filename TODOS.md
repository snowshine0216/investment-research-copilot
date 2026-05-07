# TODOS

Known gaps and deferred work from Plan 1 ship review (2026-05-07).

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

## Design / Tech debt

- [ ] **`ChatResponse.raw` unbounded** — full LLM response body stored in frozen dataclass. Remove or make optional before any serialization path is added (Plan 2+). (adversarial-review finding 11)
- [ ] **Portfolio target tolerance** — `PreferencesFile` uses ±2% sum tolerance vs 1e-6 for system configs. Tighten to 1e-4 when financial-accuracy requirements are confirmed.
- [ ] **`FailureKind.OK` dead code** — `classify_failure()` returns `OK` for 2xx but `HTTPStatusError` is never raised on 2xx. Remove or document.
- [ ] **Tenacity decorator rebuilt per call** — rebuild once at module level to reduce per-call allocation overhead in batch runs.
