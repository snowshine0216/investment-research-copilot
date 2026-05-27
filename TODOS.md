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
- [ ] **Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried** — when `_fetch_active_fund_level_evidence` returns `()` (e.g. NAV fetch failed once), and the fund's CN constituents satisfy `_active_snapshot_has_required_data_leg_gap`, the snapshot is cached with empty evidence. Next run reuses the cached snapshot; rule 2.5 emits `foreign_heavy_fund_level_evidence_missing` for up to `IRC_CACHE_FRESHNESS_DAYS` (default 7) until a full refetch is triggered. Add a freshness probe: `if fund_level_evidence == () AND _compute_foreign_listed_share(...) >= FOREIGN_HEAVY_THRESHOLD: force refetch`. (item-001 ship adversarial review 2026-05-26)
- [ ] **`_ak_call` has no timeout enforcement** — AkShare's internal HTTP calls run unbounded. Item 001 adds +4 calls per active fund × ~50 funds ≈ 200 calls of additional exposure. On a network hang, the entire `_build_rows` loop blocks indefinitely. Wrap `_ak_call` (or add per-fetcher timeout) using `signal.alarm` or a `concurrent.futures.ThreadPoolExecutor` with a deadline. (item-001 ship adversarial review 2026-05-26)
- [ ] **`_EXCHANGE_FROM_SYMBOL_PREFIX` missing `"5": "SH"`** — Shanghai-listed ETFs starting with `5` (e.g. `510300`) are classified as `UNKNOWN` by `_infer_exchange`. Conservative under-count only (never causes incorrect publish), but cosmetic correctness. Mirror `_parse_exchange_from_ticker` in `akshare_fundamentals.py`. (item-001 ship adversarial review 2026-05-26)
- [ ] **Surface synthetic `qdii_premium_pct=0.0` for off-exchange feeders** — `qdii_premium_for_row` returns synthetic `0.0` for `market="cn_off_exchange"` (they transact at NAV); the decision-report's "QDII premium" display shows `0.00%` indistinguishably from a measured `0.0` for an on-exchange ETF trading exactly at NAV. Add a synthetic-vs-measured flag (or annotation) so the display can say e.g. `(NAV-priced, no fetch)`. (item-002 ship adversarial review 2026-05-26)
- [ ] **`lru_cache` test isolation pattern** — `_fetch_full_etf_spot_table` uses `lru_cache(maxsize=1)`; tests already follow the `cache_clear()` teardown pattern. When future contributors add tests touching the bulk fetcher, ensure the same `try/finally: _fetch_full_etf_spot_table.cache_clear()` pattern is followed. Document the requirement in a contributor note under `tests/data/`. (item-002 ship 2026-05-26)

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
- [x] **Opportunity valuation/heat/product fields not wired from ingest**: `_build_input` always sets `valuation_percentile_self`, `drawdown_since_entry`, `expense_ratio`, `aum_cny`, `manager_tenure_years`, and momentum/flow fields to `None`. Wire from ingest output when those feeds are available. Until then, virtually all states degrade to `evidence_insufficient`. (code-review 2026-05-14) **Completed: v0.8.2.0** — `inputs_loader.populate_inputs()` now reads rolling returns, drawdown, percentile, expense ratio, AUM, manager tenure, tracking error, premium/discount, and flow from DuckDB.
- [ ] **`reduce_same_index` per-index backup not in default pipeline**: `reduce_same_theme` Stage 1 keeps only one best representative per index key (no backup). `reduce_same_index` in `selection.py` is available for callers that need primary+backup, but is not wired into `run_opportunity`. Evaluate whether exposing a backup per-index improves display or fallback logic. (code-review 2026-05-14)
- [ ] **`_bucket_rows` silent fallback on unknown `dca_action`**: unknown values silently land in "今日可定投" via `.get(..., default)`. Add a log warning or raise `KeyError` to surface new `dca_action` values that are missing from `_DCA_BUCKET`. (code-review 2026-05-14)
- [ ] **`demote_unstable_active` treats `theme=None` as a shared bucket**: all instruments with `theme=None` share one passive-quality bucket; a single unrelated passive instrument can demote every active fund that also has `theme=None`. Guard with `if r.theme is None: continue` in the best-passive scan, or treat `None` as unmatched. (adversarial-review 2026-05-15)
- [ ] **Verbatim traceability check is LLM-whitespace-sensitive**: `ref in memo_text` requires exact substring match; LLM models (especially CN-routed) may insert soft line breaks or normalize whitespace, causing legitimate citations to score 0. Consider normalizing both sides before comparison, or treating this as a known false-negative. (adversarial-review 2026-05-17 INVESTIGATE)
- [ ] **`geopolitical_stress` token false-positives**: EN tokens use word-boundary regex (`\b`), so `"war"` does not match "backward"/"reward" and `"attack"` does not match "attacking"/"attackers". The remaining semantic false-positive is `"strike"` → "strike price" (matched as a whole word in financial texts). CJK tokens still use plain substring matching but are short enough to be unambiguous in practice. Low severity; acceptable given the intentionally-simple design. Revisit if score quality degrades. (adversarial-review 2026-05-17 INVESTIGATE)

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
- [x] **`traceability.py` misleading coverage_ratio**: token-overlap heuristic wrong for CN text; replaced with verbatim-count schema (`n_refs_provided`, `n_refs_quoted_verbatim`). **Completed:** v0.8.4.0 (2026-05-17) — PR #19.
- [x] **Decision gate: legacy schema and empty-pool block-all**: `compose_decision_report` now handles legacy `memo_traceability.json` (no `n_refs_quoted_verbatim` key) and empty evidence pool (`n_refs_provided=0`) without silently blocking all decisions. **Completed:** v0.8.5.0 (2026-05-17)
- [x] **`geopolitical_stress_0to1` hardcoded at 0.4**: wired from persisted `geopolitics` theme report via `geopolitical_stress_from_theme_report`. Degrades to 0.4 when report absent or failed. **Completed:** v0.8.5.0 (2026-05-17)
- [x] **Mixed-date fallback in memo**: warn when scoring/gold/allocation inputs span mixed dates. **Completed:** v0.5.0.0 (2026-05-11)
- [x] **Sequential LLM calls in scoring**: parallelized with `ThreadPoolExecutor`. **Completed:** v0.3.0.0 (2026-05-08)
- [x] **`ingest` aborts on single instrument failure**: changed to skip-and-warn. **Completed:** v0.3.0.0 (2026-05-08)
- [x] **Bond ETF quality filter `_is_active_fund` heuristic**: consolidated into `instrument_kind.requires_manager_tenure`. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Resilient CN exchange price fetch**: EastMoney primary with automatic Sina finance fallback. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Role-aware allocation top-K**: two-phase greedy ensures role diversity. **Completed:** v0.4.0.0 (2026-05-10)
- [x] **Negative tenure from future inception date**: rejects ≤0 years. **Completed:** v0.4.0.0 (2026-05-10)
