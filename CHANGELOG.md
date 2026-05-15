# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Eval discipline:** Every stage eval now returns `FAIL` (exit code 2) when its
  input file is missing or unreadable, instead of the previous silent `PASS`.
  Affects 12 runners: allocation, architecture, discovery, gold_score, memo,
  news, opportunity, queries, research, scoring, trade_plan, triggers.
- **Research pipeline halt:** The pipeline now stops at the research stage when
  the quality gate fails (an entire locale dead, or success rate < 50%). Halt
  reason and remediation are written to `outputs/<date>/PIPELINE_HALTED.md`.
- **Search-provider visibility:** Every Tavily/Brave/Bocha/Jina failure is now
  logged at `WARNING` (visible without `DEBUG=true`), and the research stage
  prints a per-theme pass/fail summary at the end.
- **Time-filtered search:** Theme queries now pass `freshness_days` per theme
  (7-30 days) so providers return dated news articles instead of homepages.
- **`eval --all` summary:** Prints per-stage and overall PASS/WARN/FAIL.

## [0.8.0.0] — 2026-05-15

### Changed
- Completed the web research stack operational wiring: targeted `irc research --theme` runs, machine-readable `data/research/research_status.json`, research evals based on the new status file, fundamentals snapshot rebuild command, and README setup/output/error instructions.

## [0.7.0.0] — 2026-05-15

### Added
- **`src/irc/observability/` package** with four modules: `console.py` (shared `rich.Console` writing to stderr + `setup_logging`), `progress.py` (`progress_iter` wraps any iterable in a Rich progress bar; `stage_banner` context manager prints rule/done/FAILED with elapsed time), `errors.py` (pure `classify_exception` maps exceptions to 8 categories; stateful `ErrorTally` collects skips per loop and renders a tree summary), and `__init__.py` re-exporting the public API.
- **`DEBUG` setting** in `Settings` and `.env.example`: set `DEBUG=true` to enable verbose Rich logging (full tracebacks, DEBUG-level third-party records). Default is `WARNING`-only from third parties with one-line repr for errors.
- **Pipeline stage banners** in `irc run`: each stage is now wrapped in `stage_banner`, printing `[N/T] stage — starting` / `done in Xs` / `FAILED after Xs` to stderr.
- **Progress bars + error tallies** in `irc ingest`: `progress_iter` over metadata, prices, and NAV loops; `ErrorTally` collects skipped instruments per loop and renders a categorized tree (ssl / proxy / timeout / data-key / schema / not-found / empty / other) after each loop completes.
- **Progress bar in `irc research`**: `progress_iter` over the themes loop replaces manual `[N/T]` print statements.
- **`demote_unstable_active`** in `src/irc/opportunity/selection.py`: downgrades active-fund rows to `small_watch` when a passive alternative in the same theme has equal or better `SelectionQuality`.
- **33 new observability tests** across 5 test files covering all public API paths, edge cases, and the non-TTY rendering path.
- **4 new selection tests** for `demote_unstable_active` covering no-passive, no-quality, already-exclude, and demotion scenarios.

### Changed
- `_fetch_metadata_by_id` now returns `(metadata_by_id, ErrorTally)` instead of `metadata_by_id` alone; callers updated accordingly.
- Per-theme `print` statements in `theme_research.py` replaced with `progress_iter` progress bar.

## [0.6.2.0] — 2026-05-14

### Added
- **Opportunity/thesis/discipline sidecar layer** (`src/irc/opportunity/`): pure-function modules for lookthrough mapping, valuation/heat/thesis/product-quality state classification, same-index and same-theme reduction (max 2 per theme), DCA + risk action derivation, thesis card generation, and JSON/YAML/Markdown report composition.
- **`irc opportunity` CLI command**: reads today's scoring output, account holdings, and universe config; runs the full pure pipeline; writes three outputs — `opportunity_report.json`, `thesis_cards.yaml`, and `discipline_report.md`.
- **Theme thesis config** (`config/opportunity/theme_thesis.yaml`): per-theme thesis state table (`intact` / `falsified` / `evidence_insufficient`); missing file defaults to all-insufficient.
- **Discipline report** with 6 sections in Chinese: 今日可定投, 暂停加仓, 风险复核, 调仓复核, 退出复核, 关于回撤的说明. Drawdown ≥ 20% never auto-triggers exit — only falsified thesis or poor product quality triggers `exit_review`.
- **Opportunity eval stage** (`evals/opportunity/`): 7 metric functions (thesis card completeness, evidence gap visibility, same-theme distinct-index limit, drawdown not auto-sell, hot-chase prevention, valid action enums, no external worktree path) + runner registered in `irc eval --all`.
- **112 new tests**: 4 types, 8 lookthrough, 33 states, 4 selection, 11 discipline, 6 cards, 4 report, 3 theme_thesis, 5 command, 15 eval metrics, 3 eval runner, 2 integration pipeline, 1 integration decision-without-opportunity.

## [0.6.1.0] — 2026-05-11

### Added
- **Decision-readiness layer** (`irc.decision`): pure `completeness`, `models`, `gates`, and `report` modules that compose scoring, allocation, trade-plan, traceability, and pipeline-health artifacts into a daily `decision_report.json` + `decision_report.md`.
- **`irc decision` CLI command**: reads today's outputs; writes `decision_report.json` and `decision_report.md`; exit 0 on success, 2 when required artifacts are missing.
- **6 hard gates** (Phase 1): pipeline-halted, data-completeness < 0.80, target-weights invalid, venue blocked without proxy, memo narrative-only, score-avoid signal. `portfolio_action` is always `no_trade` (Phase 3 ordering excluded).
- **Scoring `missing_data` field**: every score row now lists the specific financial metric fields that were absent or NaN.
- **Local scoring metrics loader** (`src/irc/scoring/metrics_loader.py`): derives `expense_ratio`, `drawdown_3y`, `vol_1y`, `downside_capture`, `manager_tenure_years`, and `holdings_concentration_top10` from local DuckDB tables; `aum_stability_pct` stays NaN (honest missing) until AUM-history ingestion lands.
- **Scoring eval completeness gates** (Phase 2): `scoring_data_completeness_avg` (FAIL < 0.75, WARN < 0.90) and `buy_candidate_min_completeness` (FAIL < 0.80) metrics added to scoring eval runner; runner now reads `outputs/<date>/scoring.json` and handles `{"scores": [...]}` format.

### Changed
- `run_research()` in `ldr_client.py` refactored into `_start_research`, `_poll_until_complete`, and `_fetch_report` helpers; `research_id` from LDR server now validated against `[A-Za-z0-9_-]+` before URL interpolation to prevent path-traversal from a malicious server.
- Magic numbers extracted as module-level constants across `ldr_client.py` (`_LOGIN_MAX_RETRIES`, `_LOGIN_BACKOFF_S`, `_HTTP_REQUEST_TIMEOUT_S`, etc.) and `metrics_loader.py` (`_TRADING_DAYS_PER_YEAR`); `DecisionStatus` Literal cleaned of unused `review_sell_later` variant.

### Fixed
- **`_write()` date decoupling** in `evals/scoring/runner.py`: eval report was written to today's date folder regardless of which historical scoring artifact was loaded; now derives the folder from the source file's parent date.
- **Zero-denominator Inf in `derive_risk_metrics`**: zero-priced or negative-value price series caused `Inf` drawdown values (invalid JSON); safe-max guard replaces zero denominators with NaN before division.
- Scoring eval runner previously read stale `outputs/scoring/scores.json` path and treated the file as a raw list; now reads dated output path and unwraps the dict wrapper — completeness gate now fires correctly on real artifacts.
- **Falsy-list masking** in `gates.py`: `missing_data or REQUIRED_METRIC_FIELDS` incorrectly fell back to all-required-fields when the score had zero missing fields (empty list is falsy); fixed to explicit `is not None` check.
- **Markdown injection** in decision report table: raw field values could contain `|` or `\n`, breaking Markdown table structure; `_md()` helper now escapes both characters.
- **Null-safety** in `gates.py` / `report.py`: explicit `None` checks and `try/except` guards for `data_completeness`, `coverage_ratio`, and `target_weight` fields that may arrive as `None` from older output files.
- **Pipeline-incomplete gate**: `_scores_missing_action()` detects when >50% of score rows lack an `action` field (scoring stage did not run) and auto-elevates `pipeline_halted`, preventing the decision layer from issuing advice on incomplete pipeline output.
- **`MIN_BUY_COMPLETENESS` constant**: hardcoded `0.80` deduplicated into `completeness.py`; `gates.py` and `evals/scoring/runner.py` now import the single constant.
- **Null-safety in `decision_cmd.py`**: `_resolve_output_dir` no longer raises when the `outputs/` directory does not exist.

## [0.6.0.0] — 2026-05-11

### Added
- **News layer** (`news/`): feedparser-based RSS aggregator with SSRF DNS guard, 7-topic keyword classifier, URL + similarity-signature dedup, static FOMC/PBoC/WGC events calendar, pipeline that aggregates all feeds and returns per-topic counts.
- **Research stage** (`cli/research`, `research/ldr_client`): calls optional LDR API (HTTP wrapper with token + graceful failure) to produce per-theme markdown research documents written to `data/research/<theme>.md`; included in `irc run` only when `LDR_ENABLED=true`.
- **Eval framework** (`evals/`): 12-stage evaluation harness (data, discovery, scoring, gold_score, allocation, research, news, queries, memo, trade_plan, triggers, architecture). Each stage has typed `MetricReport`/`StageReport` schemas (`evals/_shared`), a metrics module, and a runner. `irc eval` CLI dispatches a single stage or `--all`; exit code reflects worst status.
- **Spot-check eval** (`evals/spot_check`): weekly auto-sample + CSV queue for manual review.
- **Architecture eval** (`evals/architecture`): DAG acyclicity check, max LOC, and output completeness metrics.
- **WGC gold drivers** (`gold/drivers`): wires `cb_purchases` + `etf_holdings_30d` from WGC CSV ingestion; removes hardcoded constants.
- **Discovery rolling tracking-error** (`discovery/metrics`): replaces the 0.0 stub with actual rolling TE vs role benchmark.
- **`PIPELINE_HALTED.md`** on stage failure + optional research stage support in main run.
- **Thesis-news score** (`scoring/factors/thesis_news`): replaces stub with real news-signals scoring factor.
- **Correlation filter activation** (`allocation`): intra-class weight renormalization live; module-level Lock for OBB credential (TOCTOU fix).
- **Feature-flagged active-fund tenure proxy** and resilient CN exchange price fetch carried forward from 0.4.0.0.
- **Generated CN fund universe path**: `irc universe build-cn-funds` command, akshare open-fund catalog wrapper, deterministic CN fund classifier (`src/irc/discovery/cn_fund_universe.py`), optional generated universe merge in config loading, and discovery diagnostics CSV output (`discovery_diagnostics.csv`).

### Fixed
- **Security — SSRF (CRITICAL)**: `ldr_client.py` now calls `_verify_host_resolves_publicly` on non-loopback `LDR_BASE_URL` hosts before any HTTP request while still allowing local self-hosted LDR; `rss_aggregator.py` applies DNS guard before feedparser; `discovery/reason_writer.py` sanitizes `instrument_id` in simplified mode before constructing LLM prompt.
- **Security — SQL injection**: `evals/data/metrics.py` double-quotes column names from `information_schema` and escapes embedded quotes; table name already allowlisted.
- **Security — secrets**: `SecretStr` for anthropic/tushare/ldr/fmp/tiingo tokens; user question capped at `MAX_QUESTION_LEN=2000`.
- **Security — two-hop prompt injection**: raw refs sanitized before auditor prompt in memo pipeline.
- **Reliability — retry deadline**: `deadline_s` now converts retryable HTTPX failures into `AggregateTimeoutError` when the wall-clock deadline is exceeded.
- **Reliability — akshare fund lookup**: fund codes are normalized before catalog pre-checks so numeric/mixed-type upstream codes do not falsely raise `FundNotFound`.
- **Reliability — parallel write_reason**: `ThreadPoolExecutor` mirrors Plan-3 scoring parallelism.
- **Reliability — gold_score KeyError**: explicit validation surfaces renamed-driver mismatches.
- **Reliability — regime zero-slope**: returns `'neutral'` not `'downtrend'`.
- **Reliability — memo mixed-date warning**: warns when scoring/gold/allocation inputs span mixed dates.
- **Reliability — FundNotFound**: akshare raises typed exception instead of returning wrong fund's metadata.
- **Reliability — falsification length**: conditions list capped at 10, each truncated to 300 chars to prevent memo corruption.
- **Correctness — topic classifier**: returns `None` (not `'holdings_sector'`) when no keyword matches, preserving the feed-supplied topic in the pipeline `or` fallback.
- **Correctness — dedup blank URL**: items with empty `source_url` no longer collide in the seen-URL set.
- **Correctness — preference tolerance**: target sum tolerance tightened from 2% → 1e-4.
- **Performance — retry binding**: tenacity decorator bound at import time, not per-call.
- **Performance — akshare cache**: `lru_cache` for full-table fetches; cleared in init.
- **Schema — ChatResponse.raw**: bounded via opt-in env flag; default `None`.
- **Schema — FailureKind.OK removed**: `classify_failure` returns only real failures.
- **Pipeline correctness — research stage**: `run_research_pipeline` now returns non-zero when any theme research fails; `irc run` includes that fail-fast stage only when `LDR_ENABLED=true` so default setup remains operable.
- **Concurrency hardening — akshare proxy path**: DXY macro fetch now wraps proxy-env mutation in a module-level lock to avoid cross-thread proxy-env contamination.

### Changed
- Macro slot rename: `DTWEXBGS` → `DXY` across `_MACRO_SERIES` (`ingest_cmd.py`), `_macro_value` lookup (`gold_cmd.py`), `_AKSHARE_MACRO_HANDLERS` (`akshare_client.py`), and corresponding tests. The slot was always populated by the akshare DXY index (~95–115 range) which matches the DXY-calibrated thresholds in `gold_score._dxy_score` (95/105/115) and `gold_scenarios` (dxy<100, dxy>110); the FRED `DTWEXBGS` ID was a misnomer (real DTWEXBGS sits ~120). No data-quality change — purely a rename for clarity.
- `openbb_client.fetch_macro_series` now routes akshare-only IDs (`DXY`) directly to akshare, skipping the always-failing OpenBB+FRED call.

## [0.4.0.0] — 2026-05-10

### Added
- **Theme-aware CN fund taxonomy**: `theme` field added to `UniverseInstrument` schema (`sector`, `broad`, `dividend`, `growth`, or `None`). Theme drives role bucketing in discovery, quality filtering in `discovery/quality_filter.py`, and exclusion via `preferences.constraints.exclude_themes`.
- **Sector role buckets** (`discovery/role_bucket.py`): 7 new `satellite_cn_*` roles (`sector_cn_tech`, `sector_cn_consumer`, `sector_cn_healthcare`, `sector_cn_energy`, `sector_cn_finance`, `sector_cn_manufacturing`, `sector_cn_materials`) mapping sector ETFs to typed allocation slots. Core CN role now also gated on `theme=broad` or `None` with broad index.
- **Role-aware top-K allocation** (`allocation/pipeline.py`): two-phase greedy selection ensures every represented role gets a slot before score-based backfill. Prevents 4 high-scored 沪深300 clones from crowding out lower-scored 红利/创新 picks.
- **Expanded CN funds universe template** (`cn_funds.yaml`): 10 sector ETFs across tech/consumer/healthcare/energy/finance/manufacturing/materials added with correct theme tags; active off-exchange funds skeleton; fund template now covers broad, sector, dividend, and bond categories.
- **LLM skip logging** in `discovery/pipeline.py`: instruments excluded by `excluded_themes` are now logged as skipped before reason-writing, preventing spurious "no raw refs" warnings.
- **`_IngestFeatureFlags` feature-flag system** (`ingest_cmd.py`): `ACTIVE_FUND_TENURE_PROXY_ENABLED` env var (default `true`) controls whether fund age is used as a manager-tenure proxy for active funds without explicit tenure data.
- **Active fund tenure proxy fallback** (`ingest_cmd.py`): for off-exchange active funds missing `manager_tenure_years`, the fund's inception date is used as a proxy. Guards in place: proxy disabled for passive ETFs, for funds with real tenure, and when inception date is future-dated or unparseable.
- **Resilient CN exchange price fetch** (`data/akshare_client.py`): EastMoney primary with automatic Sina finance fallback; `skip_eastmoney` flag routes straight to Sina; `on_eastmoney_exhausted` callback fires after last EM retry, enabling the ingest loop to skip EM for remaining instruments in the same run.
- **Per-source ingest counters**: CN exchange prices now tracked under `ak_counts["prices"]` (not `ob_counts["prices"]`), so manifest record counts correctly reflect which provider fetched each price series.

### Fixed
- **Negative tenure from future-dated inception** (`ingest_cmd.py`): `_apply_active_fund_tenure_fallback` now rejects zero-or-negative years (e.g. from a provider returning a future inception date), preventing a semantically invalid negative from flowing into scoring.
- **Invalid `.env` bool crashes ingest** (`ingest_cmd.py`): `_IngestFeatureFlags` validation errors now produce a human-readable `Config error: …` message and `return 1` instead of a raw pydantic traceback.
- **`_to_sina_symbol` IndexError on empty ticker** (`data/akshare_client.py`): added explicit guard — raises `ValueError` on non-digit or empty input rather than `IndexError`.
- **Refs pre-indexed per instrument** in `discovery/pipeline.py`: `_index_refs_by_instrument` groups, sorts descending by date, and caps at 30 refs before reason-writing — prevents oversized prompts on large universes.
- **Quality filter `exclude_themes`** plumbed through from preferences to `run_discover` call: themes in `preferences.constraints.exclude_themes` are now excluded before LLM reason-writing, not just before scoring.
- **`requires_manager_tenure` consolidated** (`instrument_kind.py`): single authoritative function replaces the duplicated `_is_active_fund` heuristic that was causing bond ETFs to incorrectly require tenure data.

## [0.3.0.0] — 2026-05-08

### Added
- **Gold scoring pipeline** (`src/irc/scoring/`): vol-ratio + ADX market regime classifier (`regime_detect.py`), rolling 6-month H/L/Q1/Q3 band with 6-zone classifier (`gold_band.py`), 3-scenario classifier driven by real yield, DXY, CB purchases, and geopolitical stress (`gold_scenarios.py`), 6-driver composite gold score (0–100) mapping to `GoldTilt` label (`gold_score.py`)
- **`irc gold` command**: orchestrates regime + band + scenario + score → `gold_regime.json` (includes zone) + `gold_band.yaml`
- **Allocation pipeline** (`src/irc/allocation/`): AUM-based mode selector (`mode_selector.py`), per-asset-class target weights with gold tilt delta ±5pp and softmax distribution (`target_weights.py`), high-correlation pair filter (`correlation_filter.py`), top-K per class + correlation filter pipeline (`pipeline.py`)
- **`irc allocate` command**: reads scoring output + gold tilt → `proposed_allocation.yaml`
- **Trade planning pipeline** (`src/irc/trades/`): default buy method by asset class + mode (`buy_method.py`), bucket-based buy method from valuation percentile (`valuation_percentile.py`), venue compatibility check + same-index proxy suggestion (`venue_check.py`), VIX/real-yield/weekly-drawdown trigger emitter (`triggers.py`), full `TradePlanRow` composition (`pipeline.py`)
- **`irc plan` command**: reads `proposed_allocation.yaml` → `trade_plan.yaml`
- **Memo synthesis pipeline** (`src/irc/memo/`): frozen `MemoInputs` dataclass + 7-section Markdown skeleton renderer (`template.py`), LLM synthesis with raw-ref context injection (`synthesizer.py`), compliance audit LLM pass (`auditor.py`), citation coverage ratio check (`traceability.py`), full orchestrated pipeline (`pipeline.py`)
- **`irc memo` command**: reads scoring + gold + allocation + plan → `memo.md` + `memo_audit.txt` + `memo_traceability.json`
- **Interactive query engine** (`src/irc/queries/`): instrument extraction + intent classification (`parser.py`), LLM response with memo + scores context injection (`responder.py`)
- **`irc ask <question>` command**: interactive Q&A grounded in today's outputs
- **`irc run` orchestrator**: full 7-stage pipeline (ingest → discover → score → gold → allocate → plan → memo) with `--from <stage>` and `--only <stage>` resume flags

### Fixed
- `regime_detect.py` NaN guard was dead code: `np.nan or 0.0` evaluates to `nan` (NaN is truthy); replaced with `math.isfinite()` check — prevents `json.dumps` crash on sparse price history
- `target_weights.py` ZeroDivisionError: added guard for all-zero non-gold asset class weights
- `venue_check.py` proxy logic inverted: instruments with empty `venue_required` (unrestricted) were never returned as proxies — fixed with `not i.venue_required or set(...) &` condition
- `memo/pipeline.py` traceability metric: now checks only refs in `raw_ref_pool[:40]` (matching what synthesizer actually receives) — eliminates always-missing refs that were never shown to the LLM
- `gold_cmd.py` gold zone: `classify_zone(current_price, band)` is now called and written to `gold_regime.json` — `gold_zone` in generated memos was previously always "unknown"
- `memo/synthesizer.py` prompt injection: raw refs from external APIs (OpenBB/AKShare) are now sanitized (newlines stripped, truncated to 200 chars) before LLM injection
- `run_cmd.py` dead code: removed unused `_RUNNERS` dict (shadowed by `_runners_map()`)
- `run_cmd.py` uncaught ValueError: `--from` and `--only` with invalid stage names now return exit code 1 with a clear error message instead of crashing with `ValueError`

## [0.2.0.0] — 2026-05-08

### Added
- **Data ingestion pipeline** (`src/irc/data/`): atomic file writer with fsync, DuckDB connection and idempotent 7-table schema with provenance triples, per-source manifest writer, `RawRef` dataclass with DuckDB-backed reachability index
- **Market data clients**: OpenBB wrapper for ETF price history and FRED macro series; AKShare wrapper for CN fund NAV history and fund/ETF metadata
- **`irc ingest` command**: pulls 3-year price history for all universe instruments, two FRED macro series, and CN fund NAV into DuckDB; now populates the `instruments` table so discovery has real metadata; all writes use `executemany` for performance
- **Discovery pipeline** (`src/irc/discovery/`): five-step funnel — universe enumeration, hard filters (inception, AUM, expense ratio, volume), quality filters (drawdown, tracking error, manager tenure), role-bucket assignment (8 portfolio roles), and LLM-written rationale with raw-ref citation
- **`irc discover` command**: runs the full discovery funnel and writes `discovered_watchlist.csv`
- **Scoring pipeline** (`src/irc/scoring/`): five factor modules (valuation/cost, risk, quality, macro-fit via LLM, thesis-news stub), weighted composite scorer with action/conviction mapping and low-conviction demotion, Spearman sanity check; macro-fit LLM calls fanned out via `ThreadPoolExecutor` (up to 8 parallel)
- **`irc score` command**: scores the latest watchlist and writes `scoring.json`

### Fixed
- `cited_refs` NaN crash: guard now uses `isinstance(..., str)` so float NaN from empty CSV cells no longer crashes `score`
- Falsy-zero masking in scoring pipeline: replaced `m.get(key) or default` with `is not None` checks so instruments with 0.0 drawdown or 0% expense ratio score correctly
- `spearmanr` returns NaN for constant scores (all placeholder data); sanity check now treats NaN as HARD_FAIL
- `fetch_etf_metadata` used regex-mode string match by default; fixed with `regex=False`
- `macro_fit.py` NaN bypass: `min(100.0, nan)` returned 100.0 — added `math.isfinite()` guard
- `raw_ref.py` N+1 DuckDB queries: consolidated up to 8 per-table queries into a single UNION ALL
- `discover_cmd.py` unbounded scans: prices + nav_history now bounded to 3-year date window
- `discover_cmd.py` volume NULL: `COALESCE(volume, 0.0)` understated daily_volume — replaced with `FILTER (WHERE volume IS NOT NULL)`
- `ingest_cmd.py` timezone: `datetime.now().date()` replaced with `datetime.now(timezone(timedelta(hours=8))).date()` in both `_date_window()` and `_upsert_instruments()` for UTC+8 consistency
- `ingest_cmd.py` fail-fast on missing metadata: changed `raise ValueError` to `_log.warning + continue` so one bad ticker no longer aborts the full ingestion run
- `reason_writer.py` prompt injection: `name_cn` and `tracked_index` are now sanitized (control chars stripped, truncated to 200 chars) before LLM interpolation

## [0.1.0] — 2026-05-07

### Summary
Plan 1 foundation: Python CLI scaffolding, pydantic v2 schemas, LLM gateway, and full test suite.

### Added
- **Repo scaffolding**: `pyproject.toml`, `.gitignore`, `src/irc/` package skeleton with `uv` toolchain
- **Schemas** (`src/irc/schemas/`): 12 pydantic v2 `FrozenModel` configs covering inputs (account, preferences), LLM routing, scoring, gold drivers, discovery, valuation buckets, triggers, overrides, macro view, and universe; all with strict validation and sum-to-one cross-checks
- **Settings** (`src/irc/settings.py`): `pydantic-settings` class loading `deepseek_api_key` and `openrouter_api_key` as `SecretStr` from `.env`
- **Config loader** (`src/irc/config_loader.py`): YAML → schema dispatch for all 14 config files, returns `ConfigBundle`; repo root auto-discovery via `pyproject.toml`
- **LLM gateway** (`src/irc/llm/`): pure task→`ResolvedRoute` resolver, `httpx` chat completions client with injected-client support, `tenacity` retry with stepped backoff (2/4/8/16s), cost tracker with secret redaction
- **CLI** (`src/irc/cli.py`): `click`-based `irc` entry point with `init`, `config validate`, and `freshness` sub-commands
- **Templates** (`src/irc/templates/`): packaged default configs (14 YAML files) and input templates (account, preferences); `irc init` copies them into the user's repo
- **Tests**: 82 tests covering all modules; env-gated live smoke tests for DeepSeek and OpenRouter
- **CLAUDE.md**: gstack skill routing rules for this repo

### Security
- **SSRF guard**: `ProviderConfig.base_url` validated at parse time; private/link-local IP ranges blocked (10.x, 172.16.x, 192.168.x, 169.254.x, 100.64.x, IPv6 ULA/link-local); localhost allowed for dev mock servers; guard scope documented (IP literals only)
- **SecretStr API keys**: `deepseek_api_key` and `openrouter_api_key` stored as `pydantic.SecretStr`; raw values masked in `repr()` and logs
- **Header injection guard**: `_resolve_key()` strips whitespace from env var values before use as Bearer token
- **Sentinel exception class**: SSRF guard uses `_PrivateIPError` instead of message-string matching to distinguish validation rejections from parse failures
- **Null content raise**: `_parse_response()` raises `ValueError` on `null` LLM content instead of silently returning `""`
- **Valuation coverage check**: `ValuationBucketsConfig` now requires the last bucket `max_percentile == 1.0`

### Fixed
- Column width constants extracted from magic numbers in `freshness_cmd.py`
- `_MAX_ROOT_SEARCH_DEPTH` named constant extracted in `config_loader.py`
- Symlinked config path produces actionable error message instead of bare `relative_to()` traceback

[0.1.0]: https://github.com/snowballons/investment-research-copilot/releases/tag/v0.1.0
