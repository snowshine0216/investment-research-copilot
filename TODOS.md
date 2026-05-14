# TODOS

Known gaps and deferred work. Updated after v0.5.0.0 ship (2026-05-11).

## Security

- [ ] **SSRF via feedparser redirect** — `rss_aggregator.py` DNS-guards the initial hostname but `feedparser.parse()` follows HTTP redirects internally, which could bypass the guard. Mitigation: pass a custom urllib handler with no-redirect policy or pre-resolve final destination. Low-priority since feed URLs are operator-supplied. (adversarial-review 2026-05-11)
- [ ] **Cross-class correlation check** — `correlation_filter.py` only drops intra-class correlated instruments; highly correlated equity + QDII pairs can survive. Add optional cross-class check. (adversarial-review 2026-05-11 INVESTIGATE)
- [ ] **Float tolerance edge case** — IEEE 754 sums for YAML-parsed floats like 0.3+0.4+0.3 can exceed 1e-4; `schemas/inputs.py` uses `_TARGETS_TOLERANCE = 1e-4`. Verified OK for current `preferences.yaml` (sum=1.0 exactly). Monitor if users add new targets. (adversarial-review 2026-05-11 INVESTIGATE)
- [ ] **Accurate per-fund manager tenure** — `ingest_cmd._ingest_active_fund_tenure` uses inception-date proxy; replace with a real per-fund manager-start-date field from EastMoney or a dedicated tenure API.

## Reliability

- [ ] **`evals/architecture/metrics.py` silent PASS on syntax errors** — files with syntax errors trigger `continue`, appearing to have no imports and hiding potential DAG cycles. Surface as WARN.
- [ ] **`evals/scoring/runner.py` false stability on 1-item corpus** — `len(scores)==1` produces empty split; `score_distribution_stability([], [x])` returns `0.0`, classified as PASS. Return WARN when split has <2 observations.

## Coverage gaps

- [ ] `config_loader._resolve_schema` — `KeyError` path when schema is not registered (100% happy-path only)
- [ ] `settings.py` — `OPENROUTER_API_KEY` missing path
- [ ] `schemas/triggers.py` — invalid comparator branch (~50% coverage)
- [ ] `schemas/overrides.py` — populated override lists (~50% coverage)
- [ ] `schemas/gold.py` — direction enum variants beyond "up"
- [ ] `schemas/discovery.py` — quality filter edge cases

## Design / Tech debt

- [ ] **`write_reason` silent failure**: bare `except Exception: pass` swallows all LLM errors; `run_discover` returns 0 even when 0 candidates found. Add structured logging for retried/failed instruments. (adversarial-review 2026-05-08)
- [ ] **`fetch_fund_metadata` wrong record on miss**: falls back to `df.iloc[0]` when fund_code not found, returning metadata for a different fund. Raise `ValueError` or return `{}` instead. (adversarial-review 2026-05-08)
- [ ] **Opportunity venue filtering not wired**: `OpportunityInput.venue_compatible` is always `True`; wire it from `bundle.account.venues` so venue-incompatible instruments are routed to `small_watch` instead of `core_dca`. (code-review 2026-05-14)
- [ ] **Opportunity valuation/heat/product fields not wired from ingest**: `_build_input` always sets `valuation_percentile_self`, `drawdown_since_entry`, `expense_ratio`, `aum_cny`, `manager_tenure_years`, and momentum/flow fields to `None`. Wire from ingest output when those feeds are available. Until then, virtually all states degrade to `evidence_insufficient`. (code-review 2026-05-14)
- [ ] **`reduce_same_index` per-index backup not in default pipeline**: `reduce_same_theme` Stage 1 keeps only one best representative per index key (no backup). `reduce_same_index` in `selection.py` is available for callers that need primary+backup, but is not wired into `run_opportunity`. Evaluate whether exposing a backup per-index improves display or fallback logic. (code-review 2026-05-14)
- [ ] **`_bucket_rows` silent fallback on unknown `dca_action`**: unknown values silently land in "今日可定投" via `.get(..., default)`. Add a log warning or raise `KeyError` to surface new `dca_action` values that are missing from `_DCA_BUCKET`. (code-review 2026-05-14)

## Completed

- [x] **SSRF DNS-bypass**: DNS-resolve at call time in `http_client._verify_host_resolves_publicly` + applied to `rss_aggregator`, `ldr_client`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Remaining plain-str secrets**: `SecretStr` for anthropic/tushare/ldr/fmp/tiingo tokens in `Settings`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Two-hop prompt injection**: raw refs sanitized before auditor prompt in memo pipeline. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Unbounded question length**: `MAX_QUESTION_LEN = 2000` guard in `ask_cmd`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **No aggregate timeout / deadline_s dead code**: outer loop now catches `httpx.HTTPError`; deadline_s is live. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`sign==0` always "downtrend"**: returns `'neutral'` on zero-slope. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`compute_gold_score` KeyError on config drift**: explicit key validation added. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Correlation filter permanently disabled**: activated with intra-class renormalization. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`ChatResponse.raw` unbounded**: bounded via opt-in env flag; default `None`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Portfolio target tolerance**: tightened from ±2% to 1e-4. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`FailureKind.OK` dead code**: removed. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Tenacity decorator rebuilt per call**: bound at module level. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Sequential LLM calls in discovery**: parallelized `write_reason` with `ThreadPoolExecutor`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`fetch_fund_metadata` / `fetch_etf_metadata` cache**: `lru_cache` on full-table fetches. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`tracking_error` stub**: rolling TE vs role benchmark now live in `discovery/metrics`. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **2/6 gold score drivers hardcoded**: `cb_purchases` + `etf_holdings_30d` wired from WGC CSV. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **`traceability.py` exact-copy lower bound**: replaced with token-based fuzzy coverage. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Mixed-date fallback in memo**: warn when scoring/gold/allocation inputs span mixed dates. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Sequential LLM calls in scoring**: parallelized with `ThreadPoolExecutor`. **Completed:** v0.3.0.0 (2026-05-08)
- [x] **`ingest` aborts on single instrument failure**: changed to skip-and-warn. **Completed:** v0.3.0.0 (2026-05-08)
- [x] **Bond ETF quality filter `_is_active_fund` heuristic**: consolidated into `instrument_kind.requires_manager_tenure`. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Resilient CN exchange price fetch**: EastMoney primary with automatic Sina finance fallback. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Role-aware allocation top-K**: two-phase greedy ensures role diversity. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Negative tenure from future inception date**: rejects ≤0 years. **Completed:** v0.4.0.0 (2026-05-10)
