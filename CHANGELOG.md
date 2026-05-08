# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
