# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — monitor eval predictive-validity backtest (M3) (2026-06-16)

- New offline eval stage `monitor_forward` (`irc eval monitor_forward`) measuring whether the Monitor
  signal predicts forward NAV, surfaced in the daily brief's validation panel and **never gating any
  fund's published state** (informational; `active, in_all_suite=False` — excluded from the green
  `--all` suite; no LLM/web/spend gate). Two halves under one stage: a **retro backtest** that replays
  the evidence-free sub-composite (`compute_signal` with evidence legs N/A) over persisted NAV history
  on a look-ahead-free replay clock (truncated input window `series[:as_of_idx+1]`, strict-`>` entry,
  grid floor sourced from `minimum_observations`), and a **forward scorer** over the matured
  `forward_ledger.jsonl` rows. Metrics: directional hit-rate (raw-composite + publishable-bias modes),
  cross-sectional Rank-IC, with clustered block-bootstrap CIs and three baselines (within-`run_date`
  permutation null, momentum from the `<= as_of_date` slice, buy-and-hold). WARN-max for statistical
  weakness; FAIL reserved for input-contract / scorer-invariant breaches (`bad_nav` is a row exclusion).
- New authoritative NAV series `data/monitor/nav_history.jsonl` — producer-maintained bounded-tail
  append in `irc monitor` (dedup-on-read, total-order tiebreak), with a one-time backfill migration
  (`scripts/backfill_nav_history.py`) seeding pre-window history from `eval_trace.json`.
- Daily-brief predictive-validity panel (pure, no-JS, byte-stable) with a staleness caveat and an
  ISO-week-deduped human-review trigger (fires when the headline publishable-bias random delta sits
  below baseline for K consecutive weeks). `evals/_shared/latest_report.py` gains a `StageReportEntry`
  wrapper + report-history API (`list_stage_reports`, `latest_stage_report_entry`); the existing
  `latest_stage_report` is unchanged (M0/M1 back-compat).

### Fixed — eval-suite crash logging (2026-06-16)

- `irc eval --all` now logs a per-stage runner crash via the module logger with a full traceback
  (`_log.exception` in `_run_active_suite`) instead of a bare `print` to stdout. In non-interactive
  runs (launchd schedule, CI) a runner crash (e.g. malformed-trace `KeyError`, `ImportError`) is now
  distinguishable from a normal stage FAIL and its stack trace is preserved via the
  `src/irc/observability` structured-logging setup. Swallow-and-continue and the per-stage `rc=2` are
  unchanged.

### Added — monitor eval LLM suites (M1) (2026-06-16)

- Offline LLM-quality eval suites for the two MiniMax-routed monitor tasks. Synthetic/adversarial
  corpora under `src/irc/monitor/eval/cases/{impact,narrative}/*.json` (directional-strong/neutral,
  contradiction, injection, citation-discipline; citation-resolve, entailment-ablation,
  attribution-honesty, no-numbers, injection) and pure deterministic scorers
  (`metrics_impact.py`: sign-accuracy, magnitude-band, injection-resistance, citation-validity;
  `metrics_narrative.py`: citation-resolution, entailment-ablation, attribution-honesty,
  hallucination-rate, injection-resistance) — unit-testable on canned outputs with no network.
- `live_gated` runners `evals/monitor_impact/` + `evals/monitor_narrative/` (shared
  `evals/monitor_suite/driver.py`): load the corpora, drive the real MiniMax route, score, write a
  `StageReport`. Gated by `IRC_RUN_LIVE_LLM_EVAL=1` + the M0 `eval-live` budget gate; the runner
  ledgers spend via `record_command_run`. This is the only paid M1 surface; the green suite never
  hits the API.
- Live run now gates on the LLM suites: `GATING_STAGES_M1` resolves the latest
  `monitor_impact`/`monitor_narrative` reports (run-global) → a fresh `FAIL` marks affected funds
  `EVAL_GATED`; `SKIPPED`/stale/missing fail open (`caveated`).

### Added — monitor eval spine (M0) (2026-06-16)

- New `src/irc/monitor/eval/` package: an in-run validation + forward-evaluation spine for the
  `irc monitor` daily brief. Each run now also emits `outputs/<date>/monitor/eval_trace.json`
  (per-fund signal/factor/citation projection with a unified macro+constituent evidence pool) and
  appends a row per fund to `data/monitor/forward_ledger.jsonl` (real append-mode JSONL; reruns
  collapsed at read time by `latest_per_key`, last-write-wins). The four legacy monitor dumps are
  unchanged.
- Pure cores: `structural` (in-run signal-consistency / citation-integrity / NAV-quality health,
  worst-wins), `staleness` (resolve suite `StageReport` → `StageHealth`), `gate`
  (`apply_eval_gate` / `published_state`), `forward_log`, `trace`, `panel`. NAV is
  degradation-safe — a fund with no NAV observations is gated (`EVAL_GATED`) rather than crashing,
  and still gets a ledger row.
- New `evals/monitor_signal/` artifact eval (oracle signal-recompute, citation-resolution,
  NAV-completeness) wired into `irc eval --all`. Shared-infra: `SKIPPED` status + `EVAL_RC_SKIPPED`,
  a `live_gated` lifecycle, `latest_stage_report` (China-date lookup), an `eval-live` spend scope,
  and an `irc eval` SKIPPED/budget-gate path for live LLM suites (runners land in M1).
- Report card render: an `EVAL-GATED 🛡` badge, per-bias validation chips (✓ validated / ⚠
  caveated), and a Validation panel section.

### Changed — monitor report verdict justification (2026-06-15)

- Each per-fund card in `outputs/<date>/monitor/report.html` now explains *why* it earned
  its bias, surfacing data the signal engine already computed but the renderer discarded:
  a **verdict block** (deterministic `C` vs bands clause + concise lead MiniMax rationale),
  an **all-factors contribution table** (canonical order; present factors show value `sᵢ` /
  renorm weight `w'ᵢ` / contribution `w'ᵢ·sᵢ` / confidence; N/A factors show a dimmed row
  with their eligibility reason; footer carries `C` / confidence / available weight /
  families), a real **`[5,20,60,120,250]d` returns table** (was always empty), a labeled
  **risk & divergence block** (`divergence_codes` → plain caveats + MiniMax `risk_commentary`),
  and a **price-action-only narrative** section (no longer merged with rationale + risk).
  `NO_CALL` funds are self-explaining. Renderer stays pure, byte-stable, self-contained
  (no JS / remote refs); XSS-escaping, H3 universal-rows, and citation-closure invariants
  preserved. New pure modules `returns.py`, `render_factors.py`, `render_cards.py`.

### Added — `irc monitor` daily brief + configurable LLM routing + schedule rework (2026-06-15)

- `irc monitor` daily brief for the fixed 7-fund Monitor set (`config/monitor.yaml`):
  current price · acc-NAV trend chart · directional bias (`ADD_BIAS` / `NEUTRAL` /
  `REDUCE_BIAS` | `NO_CALL`) · causal MiniMax narrative. Self-contained HTML report at
  `outputs/<date>/monitor/report.html`. Evidence is isolated from the dual-coverage gate
  (ADR 0017 — monitor evidence never pollutes the main opportunity/memo pipeline).
- `irc monitor snapshot` — typed per-fund constituent snapshot refresh (active_fund or
  fund_level targets keyed by `provider_symbol = fund_id`, from each fund's
  `analysis_profile`). Quarterly job; called by `com.irc.fundamentals-quarterly`.
- Configurable LLM provider routing (env-driven `base_url` + `api_key` + `default_model`):
  MiniMax added as a provider, DeepSeek retained; per-task routing via `config/llm.yaml`.
  Monitor tasks (`monitor_impact`, `monitor_narrative`) route to MiniMax; legacy tasks
  (`memo_synthesis`, `memo_audit`, scoring rationales, thesis checks, Q&A) stay on
  DeepSeek/OpenRouter. Adding a third provider is a `config/llm.yaml` edit, no code change.
  SSRF guard re-applied on env-resolved base URLs.

### Changed — schedule rework + call-edge key validation (2026-06-15)

- Schedule reworked: removed `com.irc.daily` (Mon–Fri 17:30/20:00/22:30) and
  `com.irc.weekly-full` (Sat 09:00); added `com.irc.monitor` (Mon–Fri 09:00 primary +
  13:00 retry, Asia/Shanghai, idempotency on `report.html`) and
  `com.irc.fundamentals-quarterly` (1st of Jan/Apr/Jul/Oct, calls `irc monitor snapshot`).
  Morning brief reads prior trading day's *complete* published NAV; 13:00 fires only if
  09:00 failed. `notify-status` gains a new `monitor` run-kind whose success detection
  looks for `outputs/<date>/monitor/report.html`.
- `DEEPSEEK_API_KEY` no longer hard-required at `Settings()` construction. Both
  `deepseek_api_key` and `minimax_api_key` are Optional; validated at the LLM call edge.
  `irc monitor` (MiniMax tasks only) needs `MINIMAX_*`; `irc run` (DeepSeek tasks) needs
  `DEEPSEEK_API_KEY`. `irc config validate` remains secret-free.

### Changed — monitor NAV chart: labelled axes, hover detail, capped size (2026-06-15)

- The monitor report's acc-NAV trend chart (`render_nav_chart`) now renders with
  **labelled axes** (y-axis NAV at low/mid/high with gridlines; x-axis dates at
  first/mid/last), **per-point hover detail** (`date · NAV` via native SVG
  `<title>` on invisible full-height columns, downsampled to ≤120 per chart, with
  a hover-highlight), and a **capped display size** (`max-width:680px` via a
  `.navchart` class) so the chart no longer stretches to full page width. The
  renderer stays pure, JS-free and byte-stable (geometry rounded to 2dp; labels
  and tooltips exempt); the golden fixture was regenerated.

### Fixed — launchd schedule silently dead from `com.apple.provenance` (2026-06-12)

- **The daily/weekly launchd schedule never ran after its first fire.**
  `launchctl print gui/$(id -u)/com.irc.daily` showed `last exit code = 78:
  EX_CONFIG` with `runs` incrementing but the log files untouched — launchd was
  failing to *spawn* the job before bash ever started. Root cause: the plists
  pointed `StandardOutPath`/`StandardErrorPath` at persistent files
  (`outputs/_logs/launchd-daily.{out,err}.log`); once `uv run irc run` wrote to
  them macOS tagged the files with the protected **`com.apple.provenance`** xattr,
  and launchd (a different responsible-app context) was then **denied reopening**
  the tagged file on the next spawn → `EX_CONFIG`. The xattr cannot be stripped.
  This was independent of the label, wrapper, timezone, and machine sleep state
  (proven: an identical agent pointed at *fresh* log paths ran the full pipeline).
- **Fix:** the plists now set `StandardOutPath`/`StandardErrorPath` to `/dev/null`
  (never tagged, never fails to open) and each wrapper writes its **own fresh
  per-run log** `outputs/_logs/run-{daily,weekly}.<timestamp>.log` (pruned after 14
  days), so launchd never reopens a provenance-tagged file. `install.sh` removes
  the legacy `launchd-*.log` files.

### Added — daily schedule resilience: redundant fires, idempotency, single-instance lock (2026-06-12)

- **Redundant fire times.** `com.irc.daily` now fires at **17:30, 20:00 and
  22:30** Mon–Fri. `StartCalendarInterval` cannot wake a sleeping Mac, so a laptop
  closed at 17:30 would otherwise miss the day entirely; a later fire catches it
  once the machine is awake.
- **Idempotency guard.** The daily wrapper skips (exit 0) when today already
  produced `decision_report.md` and is not halted, so the extra fires are no-ops
  on a completed day but still **retry** a fire that halted.
- **Single-instance lock.** Both wrappers take an atomic `mkdir` lock
  (`outputs/_logs/.run.lock`, stale-lock reclaim) so two pipelines never run at
  once. `install.sh`/`uninstall.sh` clear the lock.
- Tests: `tests/ops/test_wrappers.py` covers the `/dev/null` plists, redundant
  fire times, per-run log creation, idempotency skip/retry, and lock skip/steal.

### Fixed — ops wrapper test determinism (2026-06-10)

- The `tests/ops/test_wrappers.py` notify-status regression tests ran the real
  `run-daily.sh` trading-day gate against the real clock, so the daily-wrapper
  parametrizations failed on any CN weekend/holiday (the gate exits 0 before
  notify-status is ever reached; the old comment claiming a forced non-weekend
  date was wrong). The tests now pin the gate's CN-clock via a stub `date` on
  `PATH` (answers `+%Y-%m-%d` / `+%u` with a fixed Wednesday, falls through to
  `/bin/date` otherwise), and a new `test_daily_gate_skips_weekend_before_pipeline`
  locks the weekend skip (exit 0, zero `uv` invocations) under a pinned Saturday.
  Wrapper runtime behavior unchanged. (#125)

### Added — Local scheduler + outcome notifier (2026-06-10)

- **The pipeline now runs unattended on macOS and notifies the operator on
  outcome.** A new `irc notify-status --run-kind {daily|weekly} --last-exit-code
  <int>` subcommand reads today's `outputs/<china-today>/` artifacts
  (`decision_report.json` summary counts, `PIPELINE_HALTED.md`, `STALE_INGEST.md`)
  plus a launchd-wrapper-supplied exit code into a frozen `RunOutcome`, calls the
  pure `classify_run_outcome` (`src/irc/notify/`), and dispatches a macOS
  notification (always, via `osascript`) plus an optional Feishu webhook (gated on
  `IRC_FEISHU_WEBHOOK_URL`). Classification precedence (ADR 0016): missing
  today-dir ⇒ `failed`; exit 1–5 ⇒ `failed`; `PIPELINE_HALTED.md` ⇒ `halted`;
  `STALE_INGEST.md` ⇒ `stale`; any `null` sell-side count ⇒ `action` ("sell-side
  state UNKNOWN — re-run `irc opportunity`", never folded into clean per ADR 0015);
  buys-or-sell-signals ⇒ `action`; else `clean` (quiet by default,
  `--no-notify-on-clean` / `IRC_NOTIFY_ON_CLEAN=0` suppresses). Scheduling is via
  two checked-in launchd LaunchAgents (`ops/launchd/`, install/uninstall scripts):
  a Mon–Fri 17:30 daily run (skips weekends + `config/cn_market_holidays.yaml`)
  and a Saturday-morning weekly run, both running the full `irc run`. The
  classifier is pure and table-tested; only `osascript` / the Feishu POST are
  effects; a notifier transport failure logs and exits non-zero without raising.
  `notify-status` never trips the spend gate. See ADR 0016.

### Added — Sell surfacing + holdings-aware deltas (2026-06-10)

- **The decision report now tells the operator what to TRIM / EXIT / REVIEW, not
  just what to BUY.** The discipline layer's `risk_action` / `dca_action` /
  `portfolio_weight` / `is_holding` are surfaced onto each publishable
  `opportunity_report.json` row (via a defaulted `discipline_by_id` keyword on
  the pure `compose_opportunity_report`, built at the command edge). The decision
  layer maps them through a new pure `map_portfolio_action`
  (`src/irc/decision/portfolio_action.py`) into a five-value `portfolio_action`
  (`no_trade` / `buy` / `trim_review` / `exit_review` / `review`), gated on
  `is_holding` so a non-held overheated instrument never renders as a trim
  (ADR 0015). `decision_report.md` gains a `## 持仓行动 / Sell · Trim · Review`
  section with current-vs-target cost-basis weight deltas (Δpp), and
  `decision_report.json` `summary` gains additive `trim_count` / `exit_count` /
  `review_count` counts for item 002's notifier (no `sell_count` — the notifier
  composes its own rollup). A held row carrying a sell signal that is not also
  blocked or an actionable buy gets `decision_status == "review_sell_later"`.
  No existing JSON key changed; H3 / SAME-3 / Policy B / the `thesis_state`
  setter rule are all untouched. See ADR 0015.

### Added — Valuation axis lock + memo-routing docs (2026-06-10)

- **Regression-locked the shipped valuation-axis and memo-routing contracts.** Two new
  offline unit tests (`tests/templates/test_valuation_buckets_template.py`,
  `tests/templates/test_llm_template.py`) pin the **packaged config templates**: the
  Phase D active-fund look-through axis ships `enabled: true` with `coverage_floor: 0.50`
  (PR #111 / gate #5), and `memo_synthesis`/`memo_audit` route through OpenRouter Anthropic
  models (the shipped default README documents). No production code path changed — the
  axis was already ON; nothing was flipped. The README memo-routing note now names the
  packaged-template-vs-runtime-config distinction so the shipped default cannot be misread
  as DeepSeek. The consensus-upside axis (`consensus_upside_pct`) stays dormant by the
  ADR 0009 degrade-to-`None` contract (out of scope to enable).

### Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)

- **The broad-index PE/PB ingest leg is now polite.** The 8 legulegu calls
  (csi300/csi500/csi1000/sse50 × `stock_index_pe_lg`/`stock_index_pb_lg`) route
  through a new `src/irc/fundamentals/legulegu_fetch.py` paced primitive: a 4s GAP
  is slept before every attempt so the burst detector never trips; ordinary
  network blips retry 3× with 3s·6s backoff (per-symbol → None on exhaustion);
  the throttle signature (missing-CSRF AttributeError / JSON-decode of an HTML
  error body) waits 30s and retries once, then **raises `LeguleguCooldownExhausted`**
  to suspend the remaining broad-leg sweep. Suspension is **non-destructive** — a
  skipped key keeps its cached `index_valuation_history` rows, so a mature key
  still grounds on PE-TTM this run (only the refresh is deferred). The single-shot
  provider seam (`fetch_cn_index_valuation`) catches the same signal → `None`
  (never-raises contract preserved). A **both-axes guard** now blocks the
  destructive DELETE+replace whenever either PE or PB is entirely absent from the
  fresh frame (cache preserved). Skips and suspensions emit tested WARNINGs
  (event · key · missing-axis/skipped-keys · "cache preserved"). Constants are
  hardcoded judgment values (no env knob); gate #4 calibrates the GAP against the
  live limiter. See [ADR 0014](docs/adr/0014-legulegu-rate-limit-handling.md).
  Deferred: full PB date-aligned carry-forward; a run-level ingest diagnostic
  artifact for chronicity; an HTTP adapter that preserves legulegu status codes.

### Added — Spend / balance gate Phase 2: usage-as-data convergence (2026-06-06)

- **The spend gate now learns.** Each gated command records its actual paid-API usage
  (LLM tokens per `llm.yaml` task + search units per provider) and folds it into a rolling
  EWMA usage profile (`data/spend/usage_profile.json`, α = 0.3), so the next estimate
  converges on reality; it also auto-decrements the local ledger (`data/spend/consumption.json`)
  and writes estimated-vs-actual artifacts (`outputs/<date>/spend_estimate.json` at `irc run`
  preflight, `outputs/<date>/spend_actuals.json` accumulating across commands in a day).
  Honours ADR 0013 (usage rides home **as data**): pure cores (`spend/recorder.py`,
  `spend/estimate_io.py`, `fold_actuals`/`effective_profile`, `ledger.apply_usage`) take no
  recorder param and mutate nothing; the `record_command_run` edge does all I/O. Wallet-vs-quota
  is derived from `spend_balances.yaml` (writer/reader can't drift). Recording is hands-off,
  fires on success and failure (`finally`), is non-fatal (WARNING-logged), and no-ops when a
  command made no paid calls. Wired into every paid runner: `memo`, `ask`, `score`, `discover`,
  `research` (the search-unit ledger leg), `opportunity`, plus standalone `eval-funds` /
  `narrative --analyze`. `irc run` needs no change — it records each sub-runner's slice.
  README "Spend / balance gate" §13 expanded. Convergence is proven deterministically with
  injected actuals (no real spend). Known limitation: the JSON state read-modify-write assumes
  sequential invocation (`irc run` is sequential); concurrent same-day commands can lose an
  update, which self-heals on the next run.

### Added — Phase A broad-index PE-TTM grounding (2026-06-05)

- **Phase A — broad-index PE-TTM grounding.** The curated broad-index ETFs (+ legit
  generated index funds) now ground their equity `valuation_state` on the legulegu
  **PE-TTM** (滚动市盈率) historical percentile instead of the NAV self-history
  percentile. PE reads 滚动市盈率 only (never 静态市盈率); production fetch resolves
  symbols from a live-confirmed 4-symbol allowlist (csi300/csi500/csi1000/sse50),
  with a probe-only speculative map for the rest. The broad ingest leg does a per-key
  full replace (`replace_keys=True`) that self-migrates stale static-PE rows.
  `创业板指`/`创业板50` are now distinct slugs (chinext/chinext50). `161721`/`003318`
  get seed overrides stripping their mis-tagged broad `tracked_index`. Measured reach:
  ~9 broad funds grounded.

### Added — Phase B sector-index PE onboarding (B1, activation OFF, 2026-06-05)

- New single-source-of-truth catalog `src/irc/opportunity/sector_indices.py`:
  `SectorIndex` frozen dataclass + `SECTOR_INDICES` (17 slugs = 14 new sector
  indices + the 3 folded-in metals slugs) and derived maps `SECTOR_INDEX_CODE`
  / `SECTOR_INDEX_DISPLAY` / `SECTOR_INDEX_KEYS` / `SECTOR_NAME_TO_SLUG`.
  `lookthrough.py` and `fundamentals/akshare_index_valuation.py` now import the
  derived maps (inline 3-entry sector dicts removed).
- Config allowlist `sector_index_grounding.activated_slugs` (schema
  `SectorIndexGroundingConfig`, template `valuation_buckets.yaml`), threaded
  explicitly to a new gate in `_index_valuation_metrics`: a sector slug not on
  the allowlist short-circuits to the full all-`None` tuple. **B1 default =
  empty → production output byte-identical** (accumulate-only). The schema
  validates `activated_slugs` against `SECTOR_INDEX_KEYS` and rejects unknown
  slugs (fail-loud — an allowlist typo can no longer silently no-op). The csindex
  series take ~6 months to clear the 120/180 maturity gate; **grounded count =
  0 by design at B1** (gate #3 not claimed). Activation (B2) is a separate,
  post-maturation, gate-#5-reviewed change.
- The malformed universe value `中证机床ZZ` is resolved via an alias in
  `SECTOR_INDICES` — **no `config/universe/*.yaml` edit** (preserves byte-identity).
- Per-slug ingest audit `data/index_valuation_ingestor.py::audit_sector_ingest`
  (row count / has-numeric-PE / latest date / freshness / maturity per slug)
  replaces the ingestor's silent aggregate count.
- Strengthened live identity guard `test_sector_index_valuation_live.py`
  (double-gated `IRC_RUN_LIVE_AKSHARE=1`): asserts numeric `市盈率1` AND
  code↔official-name identity in `index_csindex_all` over all codes. Flags
  `sse_star_chip` (000685, absent from `index_csindex_all`) and `csi_resource`
  (000819, display≠official) for human confirmation before B2 activation.

### Changed — Phase D active-fund look-through valuation (PR2 flag flip, 2026-06-05)

- Flipped `active_fund_lookthrough.enabled` to **`true`** (`coverage_floor: 0.50`,
  the gate-#5 decision). Active CN equity funds with no `tracked_index` now derive
  `valuation_state` from the holdings PE/PB look-through (NAV fallback retained when
  ungrounded). Production output is **no longer byte-identical** to the NAV-only path:
  the divergence advisory begins firing for these funds (intended).
- Gates cleared: **#4** (live `stock_value_em` column confirmation — PASS) and **#5**
  (human review of `irc lookthrough-diff` on real cached data; floor chosen = 0.50).
- Recorded impact (real cached data, 2026-06-05): 40 active funds grounded at floor 0.50;
  flips are one-directional (NAV-expensive → PE-cheaper). On an `irc opportunity`
  before/after, 3 funds changed `valuation_state` and 1 (`110022 易方达消费行业`) moved
  `small_watch → core_dca`; row/card/rejection counts unchanged (H3/SAME-3 intact).
- Docs: ADR 0012 addendum (2026-06-05), CONTEXT.md "Valuation inputs", and
  `docs/2026-06-04-phase-d-lookthrough-pr1/gate5-review-note.md`.

### Added — Phase D active-fund look-through valuation (PR1 shadow compute, 2026-06-04)

- Per-stock PE/PB valuation fetch path: `fundamentals/akshare_stock_valuation.py`
  (EastMoney `stock_value_em`, primary) + `fundamentals/tushare_stock_valuation.py`
  (`daily_basic`, token-gated fallback), `data/stock_valuation_history` DuckDB table,
  and `data/stock_valuation_ingestor.py` (atomic upsert, per-row `_source`).
- `irc fundamentals stock-valuation` command: refreshes per-stock history for every
  distinct A-share (`^\d{6}$`) in `fund_holdings`. Heavy, own cadence — NOT part of
  `irc run`. Per-stock failure-isolating.
- Pure aggregation core `opportunity/lookthrough_valuation.py`: rolls a fund's current
  top-N A-share basket into a per-date-renormalized harmonic earnings-yield PE series
  (PB in parallel), with per-metric coverage (PE/PB covered sets computed independently),
  the `/100` coverage-floor ratio, non-positive exclusion, and the PE 120/180 maturity
  gate vs PB `<30` floor.
- `inputs_loader` active-fund branch + `active_fund_lookthrough` config block
  (`config/valuation_buckets.yaml`, default `enabled: false`). **Shadow mode: the flag
  gates slot population, so production is byte-identical to today** (NAV fallback;
  all-`None` dormancy lock). The flag is threaded explicitly through
  `run_opportunity → _build_rows → _build_input → populate_inputs`.
- `irc lookthrough-diff`: gate-#5 diff report (per-fund would-flip band, Δpercentile,
  per-metric coverage + source mix, current-basket caveat, coverage-floor sensitivity at
  0.40/0.50/0.60). Computes regardless of the flag.
- Live-gated EastMoney + Tushare column-confirmation tests authored (double/triple-gated;
  gate #4 — human-run, NOT executed by CI/autodev).

### Fixed — memo citation gate false-positive on the execution-summary pacing line (2026-06-04)

The **memo** stage was BLOCKED by the item-009 citation gate
(`159941:uncited_conclusion`, `513100:uncited_conclusion` → `memo_blocked.md`).

- **Root cause.** The LLM execution summary (§7, free prose after the
  `IRC_EXECUTION_LINES_END` marker) is a pure non-action paragraph — every clause
  is conditional/paused/pacing — but it contained the standalone phrase
  `建仓节奏以小仓位观察为主` (a Rule-9-approved non-action phrase the synthesizer
  emitted *without* the `本期无核心定投候选，` prefix the gate's exemption list
  knew). The bare `建仓` inside `建仓节奏` made `_has_actionable_keyword`
  misclassify the whole summary as actionable, so the two **paused** QDII codes
  the LLM named (`159941`/`513100`, both `pause_wait`, premium-too-high) were
  flagged `uncited_conclusion` — even though they carry no buy recommendation and
  the deterministic §6 QDII-premium block already lists them gate-safely.
- **Fix.** Add `建仓节奏` (position-building *cadence*) to
  `_NON_ACTIONABLE_LABELS`, mirroring the existing `建仓模式`/`建仓方式` pacing
  meta-labels. A real recommendation reads `建仓 X` / `建议建仓`, never
  `建仓节奏`, so stripping it only removes the meta-pacing `建仓` and keeps the
  gate strict for genuine actionable claims.

### Added — commodity-cyclical valuation guard + sector-PE accumulate-forward (2026-06-04)

For commodity-cyclical funds with no fundamental PE anchor, the NAV self-history
percentile is price momentum, not valuation — `narrative compute_metals --analyze`
was reporting nearly every metals/resource fund as `very_expensive` purely off NAV
price action.

- **Symmetric NAV-anchor exclusion (`classify_valuation`).** For an equity row whose
  `theme ∈ COMMODITY_CYCLICAL_THEMES (= {"metals"})` with
  `valuation_percentile_fundamental is None`, the classifier now withholds **every**
  directional verdict — `cheap` *and* `expensive`/`very_expensive` alike — and returns
  the existing `evidence_insufficient` state before any band assignment. The exclusion
  is symmetric on purpose (a post-crash NAV trough reading `cheap` is as much a momentum
  artifact as a peak reading `very_expensive`). `_EQUITY_ASSET_CLASSES` includes
  `qdii_global`, so the guard covers all 21 metals-themed rows. A fund that later gains a
  PE anchor skips the guard and uses the PE rule. New invariant recorded in `CONTEXT.md`.
- **Reachable sector-PE anchor + accumulate-forward (csindex).** A display-name→slug
  normalization layer (`_INDEX_NAME_TO_SLUG`, sector keys only) makes a sector
  `tracked_index` resolve to a canonical slug; `fetch_cn_sector_index_valuation_history`
  reads the canonical `市盈率1` (PE-TTM) column from `stock_zh_index_value_csindex`
  (`pb=None`); a second best-effort `ingest_index_valuation_history` leg over
  `_SECTOR_INDEX_KEYS` grows the series weekly (`INSERT OR REPLACE` dedups). The generator
  emits the 中文 index name for recognised 有色/资源/矿业 ETFs so the mapping survives
  monthly universe regen; actively-managed resource funds stay guarded.
- **Min-history gate (`MIN_PE_POINTS=120`, `MIN_PE_DAYS=180`).** A sector PE percentile is
  surfaced only once the accumulating series is mature (≥120 non-null PE points spanning
  ≥180 days); below that it returns `None` → the §1 guard catches it. The latest-null PE
  guard is preserved; csi300/csi1000 (thousands of points) are unaffected.
- **Narrative surfaces the withheld valuation** as a non-blocking mild risk driver
  (`_state_drivers`); no `evidence_gap` is added, so H3 publishability is unaffected.

### Fixed — opportunity fetch-budget over-estimate (spurious halt); SystemExit halts are resumable (2026-06-04)

A stale weekly `irc run` halted at the **opportunity** stage with
`FetchBudgetExceeded` (e.g. `active_fund_stale=73 fund_level_stale=23 cost=2647
budget=2000`) — the memo (which runs *after* opportunity) was never produced, and
`irc run --resume` started over from scratch.

- **Root cause: the preflight budget over-estimated stale active funds ~35×.** It
  counted every date-stale `cn_equity_fund` at the full top-N re-fetch cost
  (`1 + top_n*3 + 4 = 35` calls), but a date-stale fund whose cached data leg is
  still complete is resolved by `_maybe_freshness_probe` with a **single cheap
  holdings probe (1 call)** — a full re-fetch only fires on a data-leg gap or an
  actual quarter roll. On a routine June run (active-fund quarterly data still on
  the latest disclosed quarter), the real cost was ~756 calls, not 2647 — the halt
  was a **false alarm**. `_classify_active_fund_scores` now returns
  `(misses, stale_full, stale_probe_only)`; `FetchPlan.total_calls` charges
  `stale_probe_only` at 1 call each. The gate now passes and opportunity builds the
  memo from probe-validated current data. A genuinely expensive refresh (data-leg
  gaps, quarter roll, cold misses) still trips the gate → run `irc fundamentals
  snapshot` (the designed quarterly job) or raise `IRC_FETCH_BUDGET`.
- **`--resume` now works after a `SystemExit` halt.** `run_opportunity` raises
  `SystemExit(3)`/`SystemExit(4)` on its budget/lock gates; these `BaseException`s
  previously bypassed `run_pipeline`'s halt handler, so `.pipeline_state.json` was
  never written and `--resume` found nothing to resume. `run_pipeline` now catches
  `SystemExit`/`Exception` from any stage, writes the halt state + a `stage_exception`
  `PIPELINE_HALTED.md`, and `--resume` picks up from the failed stage instead of
  restarting from `ingest`.

### Fixed — rule-2.5 funds no longer crash the per-constituent pure-failure gate (2026-06-04)

The **opportunity** stage aborted with
`RuntimeError: constituent_failure_in_publishable_row: symbol=00998` (e.g. fund
`006809 泰康香港银行指数A`), suppressing every downstream output.

- **Root cause: a latent conflict between Policy B rule 2.5 and item-009's auditor.**
  Rule 2.5 (the 2026-05-26 foreign-heavy short-circuit) *publishes* an active fund on
  fund-level NAV+announcement evidence and bypasses all per-holding checks — so a
  foreign constituent whose CN filings pipeline is structurally unreachable (HK-listed
  `00998`) is a legitimate pure-failure (`evidence=() AND failure_reasons!=()`) on a
  publishable row. Item-009's `find_incomplete_constituent_analyses` (written 2026-05-22,
  before rule 2.5) treated **any** such constituent as an unconditional-fatal
  "escaped-the-gap-stamp" programming bug. A transient `ConnectTimeout` on the HK-news
  leg tipped `00998` from *partial-success* (tolerated) to *pure-failure* (fatal),
  exposing the conflict.
- **Fix.** `find_incomplete_constituent_analyses` gains a `foreign_heavy_exempt_ids`
  parameter; the opportunity-stage gate populates it with the iids whose verdict is
  rule-2.5-publishable (`fired_rule=="2.5" AND gap_codes==()`) and skips those rows
  wholesale — mirroring rule 2.5's per-holding short-circuit. The failed constituent
  still renders as `❌` in the `## 持仓明细` appendix; only the fatal crash is removed.
  See [ADR 0003](docs/adr/0003-failure-mode-policy-b.md) §7.

### Added — fundamental-grounded equity valuation (Phase 1, 2026-06-03)

The equity `valuation_state` for **broad-index CN vehicles** is now decided by a
**fundamental index PE-TTM historical percentile**, not the price/NAV self-history
percentile. The NAV percentile stays as the fallback (no fundamental data) and as a
divergence signal.

- **Data layer (effects at the edge):** new AkShare-only `fetch_cn_index_valuation_history`
  keeps the full legulegu PE/PB series (the latest-row-only fetch discarded it); a new
  `index_valuation_history` DuckDB table + ingest-stage writer refresh it on `irc run
  --from ingest`. The forbidden `基金概况` indicator is never used. The
  `CnFundamentalsProvider` Protocol stays 3-method (the history fetch is ingest infra,
  not a provider method).
- **Classifier (pure):** `classify_valuation` bands on `valuation_percentile_fundamental`
  when present (existing cheap/.20·reasonable_low/.40·fair/.70·expensive/.90 thresholds),
  else falls back byte-for-byte to the NAV percentile. PB percentile adds a cyclical-earnings
  corroboration note (never notches the state). The dormant `earnings_yield − real_yield_10y`
  anchor is lit up with **ratio-unit** data (`earnings_yield = 1/pe_ttm`; `real_yield_10y =
  cn_10y_yield/100`, the 股债利差 nominal gap until CN CPI is ingested).
- **Divergence advisory:** a single pure `valuation_divergence_code` detector emits
  `valuation_price_fundamental_divergence` (band-tier crossing **or** `|gap| ≥ 0.25`) into
  `advisory_gaps` (never `evidence_gaps` — H3/SAME-3 untouched, row stays publishable);
  surfaced as a discipline-report legend note.
- **`irc opportunity` performs no live index fetch** — `populate_inputs` reads only the
  cached `index_valuation_history` table (the live `provider.fetch_index_valuation` call was
  removed). **Risk inherits** the grounded verdict with **no change** to
  `derive_position_risk_level`.
- Scope: broad-index CN ETFs/index funds only. QDII (US/HK), sector-theme ETFs, and active
  funds fall back to the NAV percentile by design (QDII fundamental valuation and Phase-2
  holdings look-through are deferred to later specs).

### Fixed — remove the active-fund `product_quality_state` floor (F-1, 2026-06-03)

`classify_product_quality` no longer forces every active fund (`cn_equity_fund`
off-exchange) to `weak` when `aum_stability_pct` is absent — that input is never
ingested today (`metrics_loader.py` writes `NaN`), so the gate was a universal
structural floor, not a product judgment.

- New `_classify_active_quality` grades active funds on **manager tenure +
  cost/scale** (`_passive_quality_score`). `aum_stability_pct` is now **optional
  corroboration**: present-and-`<= 0.20` permits `strong`; its absence caps the
  ceiling at `acceptable` but never floors a sound product to `weak`. Genuine
  `weak` (tenure `< 2y`, thin or negative cost/scale) is preserved; `tenure is
  None` → `evidence_insufficient`.
- **Opportunity-state ripple (intended):** a sound active fund that is
  cheap/quiet/intact + now-`acceptable` reaches `core_dca` instead of being
  suppressed to `small_watch` (`compose_opportunity_state`).
- Removed the obsolete `_WEAK_FLOOR_LEGEND` / F-1 disclaimer from the narrative
  `.md` — a displayed `质量=weak` is now a real cost/scale verdict; the
  `产品驱动` raw drivers line still carries 费率/规模/任职/跟踪误差.
- Until the F-1 data slice lands, no active fund can reach `strong` (capped at
  `acceptable`); `aum_stability_pct` stays honest-missing. Updated CONTEXT.md.

### Added — `irc narrative` thematic fund mining (2026-06-02)

New top-level **`irc narrative <name>`** command — resolve an investment *narrative*
(e.g. `compute_metals` / 算力金属) to a ranked **shortlist of funds** by holdings
look-through against a curated, frozen **reference basket**, then optionally run the
system's deepest per-fund analysis on the shortlist.

- **Screen (default / `--screen-only`):** enumerates the curated CN-fund universe,
  fetches each fund's disclosed top-10 holdings (AkShare `fund_portfolio_hold_em`,
  cached), scores basket overlap (symbol-first, name-second, with SW-industry credit),
  and ranks by `(basket-weight desc → overlap-count desc → instrument_id)`. Funds with
  no published holdings are written to `<name>_screen_diagnostics.json` — never silently
  dropped.
- **Analyze (`--analyze`):** reuses the existing opportunity-grade cores untouched
  (`build_opportunity_row` → `build_thesis_card` → `derive_dca_action`/`derive_risk_action`)
  per shortlisted fund, emitting the 5 sub-states, `opportunity_state`, `dca_action`,
  `risk_action`, falsification/trim triggers, review cadence, and **cited thesis evidence**
  (`[ref:…]`). Cache-only (mirrors `irc opportunity`); a missing snapshot surfaces as
  `insufficient`, never crashes.
- **New deterministic `position_risk_level`** ∈ `{low, moderate, elevated, high,
  insufficient}` for the *prospective-buy* decision, with a rationale naming the dominant
  drivers (valuation / heat / thesis / product-quality / holdings & narrative
  concentration); `evidence_gaps` non-empty ⇒ `insufficient` (never fabricated).
- New pure-core package `src/irc/narrative/` (schemas / screen / risk / report) + I/O
  edges (`holdings_fetch` / `config` / `analyze`) + thin `commands/narrative_cmd.py`.
  Flags: `--screen-only` / `--analyze` / `--min-overlap` / `--quarter` / `--db` /
  `--role` / `--out` / `--repo-root`. Reusable for new narratives (`ai`, `robots`) by
  adding a `config/narratives/<name>.yaml` — **no code change**. The seeded
  `compute_metals` basket is a **DRAFT** pending user approval.
- **Active-fund autobuild for `--analyze` (2026-06-02):** `irc narrative --analyze`
  now auto-builds + caches the `active_fund` snapshot for shortlisted
  `cn_equity_fund` funds that lack one (mirrors `irc opportunity` autobuild), so
  narrative-*discovered* funds — absent from `scoring.json` — get deepened instead of
  screened to `insufficient`. Default-on; disable with `IRC_NARRATIVE_AUTOBUILD=0`.
  Pre-fetch `IRC_FETCH_BUDGET` guard: a budget trip exits cleanly (`rc=3`, actionable
  message), never a partial report; per-fund build failure degrades that fund to
  `insufficient`, never crashing the run. `analyze_fund` stays read-only (effects at the
  command edge). The misleading `--analyze` prerequisite error string (which told users
  to run `irc fundamentals snapshot` — a command that cannot populate this cache) is
  corrected to name `irc ingest` + the autobuild behaviour.
- **Passive-ETF fund-level deepening for `--analyze` (2026-06-02):** `irc narrative
  --analyze` now deepens passive funds (`cn_etf` and `qdii_*`/`us_etf`/`hk_etf` with a
  resolvable underlying), recovering `robots_report`'s all-passive shortlist. `analyze_fund`
  gains a read-side dispatch on the resolved look-through kind: it loads a fund-level
  `FundLevelSnapshot` (NAV data leg + announcement info leg) and feeds it through the
  same dual-leg-gated thesis derivation as `irc opportunity` (a fund passing the dual-leg
  gate reaches a real `thesis_state`, not `insufficient`). A passive nav-snapshot
  autobuild edge (unified with the active path into a single `autobuild_narrative` with one
  shared fetch-budget preflight) builds + caches missing nav snapshots; `theme_report`
  stays `None` (the fund-level thesis branch is theme-independent — genuine theme sourcing
  is a separate follow-up). Effects stay at the command edge; `analyze_fund` remains
  read-only. Refactor: the nav-cache loader moved from `commands/` to
  `fundamentals/snapshot_cache.py`, removing a `commands↔narrative` import cycle.
- **Narrative report `.md` enrichment (2026-06-02):** the `<name>_report.md` now explains
  *why* a fund earned its verdict, not just the verdict. Each fund block carries the
  `ThesisEvidence.summary` prose on its cited evidence (was opaque `[ref:hex]` IDs only),
  a per-constituent holdings section with `one_line_view`, and a deterministic,
  citation-id-sorted **evidence-footnote appendix** (`证据明细`) that resolves every inline
  `[ref:…]` to a human-readable `type · source · date · summary · url` line — drawn from the
  union of fund-level + constituent evidence so no reference dangles. Product-quality
  **drivers** (费率 / 规模 / 任职 / 跟踪误差) are surfaced next to `质量`, with a report-level
  legend noting that `质量` is currently a structural floor (pending follow-up F-1, since
  `aum_stability_pct` is not yet ingested) so readers weight the drivers over the `weak`
  label. The `.md` adds no datum the `.json` lacks (the `.json` evidence now also carries
  `summary` + `url`). The narrative renderer remains display-only — it is **not** an
  ADR-0004 §3 SAME-3 citation-set surface, so the appendix is exempt from citation-set
  equality. The product-quality scorer itself is unchanged (F-1 follow-up).
- **H3 display discipline for `insufficient` narrative rows (2026-06-02):** in the
  `<name>_report.md`, funds whose `position_risk_level == "insufficient"` no longer print
  earned-looking conclusions they have not earned. The action triad (`机会`/`dca`/`风险`),
  the falsification/trim triggers, the review cadence, AND the `子状态` line (估值/热度/逻辑/质量
  — themselves H3-forbidden conclusion fields) are now **suppressed** for such rows; in their
  place a bilingual "证据不足 / insufficient — 行动建议已抑制" line names the `evidence_gaps`
  and points at `irc narrative <name> --analyze` to refresh. Each insufficient fund still lists
  its id/name, `position_risk_level`, risk drivers/rationale, the raw numeric `产品驱动`
  metrics (data, not a verdict), and any partial cited evidence. Sufficient rows are unchanged.
  This mirrors the opportunity/discipline H3 gapped-row field discipline
  (`failure_renderer.py`). `.md`-only — the `.json` remains the full source of truth (keeps all
  conclusions); `risk.py`/`position_risk_level`/the scorer are untouched.

### Added — `eval-funds` (2026-06-01)

New top-level **`irc eval-funds`** command — targeted per-fund evaluation that
reports each fund's four sub-states (valuation / heat / thesis / product-quality),
its composed `opportunity_state`, `dca_action`, and a boolean **`core_dca`** verdict.
Reuses the pipeline's existing classifiers verbatim (**no new business logic**), works
from cache + the existing read-only `data/local.duckdb`, and sidesteps the broken
`ingest`, discovery gating, and the active-fund cap. Honest about degraded data —
never asserts `core_dca` when a sub-state is `evidence_insufficient` or a snapshot is
missing.

- New `@main.command("eval-funds")` in `cli.py`: `--ids` / `--ids-file`, `--quarter`
  (default: latest cached on disk), `--role` (display-only), `--db`, `--out`.
- New pure core `opportunity/fund_eval.py`: frozen `FundEval`, `evaluate_fund` /
  `evaluate_funds` (sorted core_dca-first), and deterministic `render_fund_eval_md` /
  `render_fund_eval_json` renderers (no I/O).
- New command edge `commands/fund_eval_cmd.py`: read-only DuckDB open (clear rc-2 on
  missing/unopenable db), universe + cached `ActiveFundSnapshot` load, atomic md+json
  write to `outputs/<today>/fund_eval.{md,json}`. Dedupes ids, warns on ids absent from
  the universe, prevents md/json path collision.
- Refactor: `_build_input` extracted from `opportunity_cmd.py` to the shared pure
  `opportunity/inputs_build.py` (behaviour-identical move; re-imported so existing
  callers/tests are unaffected).

### Added — `funding-analysis-005` (2026-05-31)

Optional **bull/bear debate** on the opportunity stage (TradingAgents pattern) —
a reasoning aid, **not** a trading signal. Opt-in, advisory-only, off by default.
See **ADR 0011**.

- New `--adversarial` flag on `irc opportunity` (default OFF). When set, runs both
  a `thesis_defend` (bull) and the existing-shaped `thesis_falsify` (bear) LLM half
  per publishable row and writes an advisory `thesis_debate.md`. When unset, behavior
  is byte-identical to before (zero LLM calls, no debate file).
- New pure module `opportunity/debate.py`: a card-shaped runner (`DefenseResult`,
  `pair_debate`, deterministic `compose_thesis_debate_markdown`) plus thin LLM-edge
  wrappers (`run_defend`/`run_falsify`/`run_debates`) that degrade gracefully per row
  (an LLM failure yields an empty debate for that row, logged at WARNING, without
  aborting the run). New `thesis_defend` task in the LLM registry (deepseek-reasoner,
  mirroring `thesis_falsify`).
- `thesis_debate.md` is a 6th, additive output written **after** the five canonical
  artifacts, on the post-citation-gate publishable rows. It is **not** a canonical
  artifact, **not** part of the H3 gapped-row partition or the SAME-3 citation-set
  equality, and — as an LLM artifact — is exempt from the two-run byte-equality /
  publishable-set-lockdown determinism contract. No change to `thesis_state`
  (owned by `derive_thesis_from_evidence`), Policy B, `valuation_state`/`core_dca`,
  the deterministic memo pillars, or the citation set.
- The live LLM smoke test is double-gated (`RUN_LIVE_LLM_TESTS=1` + a real key) and
  excluded from the default suite; unit tests mock the LLM edge.

### Added — `funding-analysis-003` (2026-05-31)

Pluggable CN fundamentals data layer with an optional **Tushare** fallback — a
behavior-preserving refactor (the AkShare-only path is byte-identical to before)
plus a new data source that activates only when `TUSHARE_TOKEN` is set. See
**ADR 0010**.

- New `fundamentals/provider.py`: a `CnFundamentalsProvider` Protocol
  (`fetch_filing_digest` / `fetch_broker_reports` / `fetch_index_valuation`,
  reusing the existing return types) with `AkShareProvider` (verbatim delegation
  to today's fetchers), `TushareProvider`, a per-method `FallbackProvider`
  (primary miss — `None` / `()` / exception → try secondary; both miss → `None`),
  and a `default_cn_provider()` edge factory (AkShare-only with no token;
  AkShare→Tushare fallback when a token is present).
- New `fundamentals/tushare_provider.py`: routes through a `_tushare_call` edge
  that lazily imports `tushare` (never at module load), so the package + network
  are touched only on the live path. Pure frame→DTO mappers degrade to `None` on
  missing/unrecognized data. The highest-value gap it fills is
  `BrokerReport.target_price`, which activates the already-wired
  `consensus_upside_pct` (ADR 0009).
- The four CN fetch call-sites (`inputs_loader`, `snapshot` ×4) now take an
  injected `provider` (DI at the command edge; stage cores stay pure). The
  AkShare default reproduces prior behavior exactly (byte-equality regression
  lock). The fetch budget and the `fetch_budget_exhausted` sentinel are unchanged
  — Tushare fallback calls are not metered.
- Swallowed provider/Tushare errors (including an invalid/expired token) now emit
  a WARNING (still degrading to `None`) so failures are observable, not silent.
- `tushare_token` (`SecretStr`, `.env`-only) is wired. New triple-gated live test
  (`live_tushare` marker + `IRC_RUN_LIVE_TUSHARE=1` + a real token), excluded from
  the default suite. README documents Tushare setup.

### Added — `funding-analysis-004` (2026-05-31)

Deterministic, pure key-ratios surface closing the balance-sheet / earnings-quality
evidence gap — **no LLM**, reason-only (no new state, gate, or citation):

- New pure module `fundamentals/ratios.py`: `compute_ratios(financials: FilingDigest)
  -> KeyRatios` (`roe`, `debt_equity`, `gross_margin`, `fcf_yield`). Same input →
  equal output; non-finite (NaN/±inf) and missing inputs degrade to `None` (no
  fabrication, ADR 0009 family). `debt_equity`/`fcf_yield` are `None` today (their
  line items aren't fetched) and self-activate when item 003's Tushare feed lands.
- `roe` is now extracted from the already-fetched `stock_financial_abstract`
  `盈利能力` section (new `_profitability_metric`; the shared `_common_metric` /
  `常用指标` read is untouched, no new network call) and added to `FilingDigest`.
  An implausible `roe` (`abs > 1.5`, likely a percent-vs-ratio unit error) degrades
  to `None` rather than display a 100×-wrong figure.
- A compact, caveated reason fragment (`（ROE …·毛利…，口径未核实）`) is appended to the
  constituent `one_line_view` **only when it fits whole** within the existing 60-char
  cap (cap unchanged); `None` ratios are omitted. Filing-derived numbers stay
  disclosure-existence anchors, not endorsed performance figures (ADR 0001 addendum).
- No change to `valuation_state` / `thesis_state` / Policy B / `core_dca` / the
  opportunity partition / the citation set (reason-only posture, locked by tests).

### Added — `funding-analysis-002` (2026-05-31)

Make the inert item-001 fundamental inputs **live**: `valuation_state` now
consumes `consensus_upside_pct` (pe/pb stay reason-only), and `core_dca` gates
on cheap-**AND**-intact. Inputs remain dormant in production until item 003
wires real data (`consensus_upside_pct` is `None` today → `evidence_insufficient`,
ADR 0009):

- New pure module `opportunity/valuation_fundamental.py`:
  `valuation_fundamental_signal(inp)` maps `consensus_upside_pct` to
  `cheap`/`rich`/`neutral`/`None` against module-level thresholds
  (`CHEAP_UPSIDE_THRESHOLD=0.20`, `RICH_UPSIDE_THRESHOLD=-0.10`); a reason
  annotation describes the consensus-upside read (+ optional pe/pb, sign-correct
  for up/down).
- `classify_valuation` appends the fundamental caveat for equities and applies a
  one-notch **cheap-direction-only** adjustment (`reasonable_low`→`cheap`); it
  never moves a state toward more-expensive (AC3).
- `compose_opportunity_state(..., valuation_fundamental=...)` blocks `core_dca`
  when the fundamental signal is `rich` while the percentile says cheap/low — the
  row falls through to `small_watch`; `valuation_state` itself is unchanged.
- Item-001's AC4 inertness lock evolved (renamed
  `test_population_consumes_consensus_upside_per_item_002`) to assert the new
  live behaviour; bond/gold/QDII rows keep a byte-identical inertness lock.
- No change to Policy B, `thesis_state`, the citation set, or the opportunity
  partition (H3/SAME-3 hold; AC8 structural lock).

### Added — `funding-analysis-001` (2026-05-31)

Wire fundamental valuation **inputs** end-to-end without changing any decision
output — the new fields are inert until items 002/003 consume them (proven by
an AC4 inertness lock: `classify_valuation` is byte-identical populated vs bare):

- New pure `consensus_upside_pct(reports, latest_close)` helper in
  `fundamentals/consensus.py` (ratio units, matching `qdii_premium_pct`). Per
  ADR 0009 it degrades to `None` rather than fabricating a `target_price` (the
  wired EastMoney broker feed drops its 目标价 column upstream). NaN screened
  on both legs.
- New thin AkShare fetchers `fetch_cn_index_valuation` (`stock_index_pe_lg` /
  `stock_index_pb_lg`) in `fundamentals/akshare_index_valuation.py`, behind the
  existing `_ak_call` indirection, with one double-gated live test
  (`live_akshare` marker + `IRC_RUN_LIVE_AKSHARE=1`).
- `populate_inputs` now fills `pe_ttm`/`pb`/`dividend_yield`/`consensus_upside_pct`
  on `OpportunityInput` at the fund/index level where a broad index is recognised
  (`None` otherwise). See ADR 0009.

### Changed — `filing-evidence-summary-reframe` (2026-05-28, F6)

Filing-evidence rows previously rendered summary text as
`{symbol} {fiscal_period} revenue_yoy=<raw decimal>` — but the accompanying
appendix caveat said the numeric value "不得作为业绩依据引用". A row that
shouldn't be trusted as a performance number still emitted that number
verbatim in inline picks/§5/§6 citations. ADR 0001 §5 (new "Filing
evidence semantics" addendum) locks the resolution:

- New filing summary template: `{symbol} {fiscal_period} 财报已披露（口径未核实）`.
  This is the disclosure-existence anchor — explicit that a filing was
  published for the period and explicit that the project does not
  endorse the numbers. The substring is the single locus that BOTH
  the user-visible content AND the appendix caveat trigger.
- Three producer sites changed to emit the new template:
  `opportunity/thesis_evidence.py::_filing_evidence`,
  `fundamentals/snapshot.py::_evidence_for_constituent` (CN + HK paths).
- `memo/pipeline.py::_format_appendix_line` trigger updated to match
  the new phrase. **Plus a cache-transition guard** (post-ship hardening
  from /ship step 8): 71 pre-F6 active-fund cache files in
  `data/fundamentals/2026Q1/` still contain `revenue_yoy=<scalar>`
  summaries; the trigger also matches the legacy substring so the
  compliance caveat is NOT silently dropped during the cache-turnover
  window. Once `irc fundamentals snapshot --target all` rewrites the
  caches, the legacy branch becomes dead code.
- `_TYPE_RANK` order, Policy B rule 3 semantics, citation_selector
  shape, `find_uncited_opportunity_rows` audit gate — ALL UNCHANGED.
  Filings still produce constituent-scope data evidence; only the
  user-facing summary text changed.

Citation_id one-time re-roll expected (content-derived per ADR 0001
§2). Filings have non-empty source_urls so the canonical key remains
the URL — citation_ids actually stay stable across this change for
the filing path. Synthesizer prompt rule 5 updated to forbid the
legacy raw-token shape while naming the new locked phrase.

### Changed — `macro-research-excerpt-depth` (2026-05-28, F5)

Memo §2 macro pillar previously rendered the FIRST non-empty LINE of each
theme report's prose — which for 4/7 themes (cn_monetary, geopolitics,
us_fiscal_politics, cn_equity_property_policy) was a bold subheading
(`**时间范围：…**`) or a `### subheading`, so §2 read as heading fragments
rather than paragraphs. ADR 0008 locks the new policy:

- `_summary_from_theme_report` (private in `gold_cmd.py`) now uses a
  skip-list (`##/###` subheadings, pure-bold `**foo**` / `__foo__`)
  + paragraph accumulator (stop at ≥3 sentence terminators OR ≥150
  chars OR blank line after first prose OR 400-char cap with `…`).
- Bullet markers (`- `, `* `, `+ `) stripped per accepted line so
  bullet-shaped reports (geopolitics) hit the 150-char floor with
  content not markers.
- `（报告内容均为标题/小节，未找到正文段落）` distinct sentinel for
  populated-but-all-skipped reports; `（报告为空）` reserved for truly-
  empty prose. Distinguishing both cases prevents the legacy sentinel
  from masking renderer/skip-rule bugs as "no content".
- LLM source-citation markers (`[1]`, `[12]`) stripped from accepted
  prose so they don't collide with downstream footnote numerals.

Existing `extract_prose_from_report_md` (from F4) UNCHANGED — F5 lives
strictly downstream of it. Memo `IRC_*_BEGIN/END` markers UNCHANGED.
H3/SAME-3 invariants UNCHANGED. Citation universe integrity preserved
(every theme still gets a `[ref:HEXID]` row in §2 via `_build_theme_refs`).
22 tests in `test_gold_cmd.py` cover the skip-list, accumulator floors,
bullet stripping, both sentinels, and `[N]` marker stripping. A 5-week
LLM prompt-eval bench was considered but deferred to a follow-up SKIPPED
entry (`F5-followup-prompt-eval`) — building the corpus + harness dwarfs
the benefit of a deterministic-extractor improvement.

### Added — `thesis-news-scoring-plumbing` (2026-05-27, F4)

Wires per-instrument research summaries into `thesis_news` scoring so the
factor actually differentiates picks instead of returning the empty-input
fallback (`50.0`) for every instrument. The factor function
`score_thesis_news` already implemented a real keyword-based rubric; the
gap was in `src/irc/commands/score_cmd.py`, which called `run_scoring`
with `news_summaries={}` so the call site at `scoring/pipeline.py:117`
resolved every instrument to `()`.

- New pure module `src/irc/scoring/news_summaries.py` exporting
  `themes_for_instrument(asset_class) -> tuple[str, ...]` and
  `build_news_summaries(reports, watchlist) -> dict[str, tuple[str, ...]]`.
  Theme tuples sorted ASC for determinism (two runs on same inputs →
  byte-identical scores per ADR 0007 §4).
- Theme→asset_class mapping locked in `THEMES_BY_ASSET_CLASS` against the
  real seven `asset_class` values in `config/universe/*.yaml`
  (`cn_bond_fund`, `cn_equity_fund`, `cn_etf`, `gold`, `hk_etf`,
  `qdii_global`, `us_etf`).
- `src/irc/commands/score_cmd.py` now calls `build_news_summaries(...)`
  and prints a `news coverage: <k>/<N> instruments` line so a zero-
  coverage run (missing or broken research stage) is immediately
  visible — required for ADR 0007 §5 "deferred-to-SKIPPED if rubric
  inadequate" path to be observable.

Empty-input fallback at `factors/thesis_news.py:47` preserved (instruments
without populated news prose still score 50.0). `derive_thesis_from_evidence`
unchanged. Keyword-only — no LLM call introduced (deferred to a
follow-up `F4-followup-llm-rubric` SKIPPED entry if the rubric proves
inadequate post-deployment). ADR 0007 captures the locked decisions.

### Added — `qdii-premium-memo-surface` (2026-05-27)

QDII premium-to-NAV data (already computed by an earlier scoring stage
per ADR 0002 §5 F6) is now visible at memo time across four surfaces:

- **§5 picks table**: new 13th column `溢价` renders the signed premium
  (`+5.42%`, `-0.34%`, `0.00%（场外申赎）` for off-exchange NAV-priced
  feeders, `—` for missing data).
- **§6 风险提示**: new `IRC_QDII_PREMIUM_BEGIN/END` marker block replaces
  the long-standing `"数据未采集——请在交易前查阅各 QDII 二级市场溢价"`
  placeholder when ≥1 QDII pick exists; lists premium per pick with the
  blocking threshold called out.
- **§7 执行要点**: trigger lines for picks with `qdii_premium_too_high`
  get a `⛔ 二级市场溢价 X.YZ% > 5%，本期暂不执行 ` prefix so the user
  cannot miss the hard-block.
- **`outputs/<date>/qdii_premium.json`**: always-written projection
  artifact (atomic write, sorted keys, `generated_at` non-deterministic
  by design — not in two-run byte-equality scope).

No new fetcher (the fetcher landed in a prior 2026-05-26 run); no new
live-test surface. Memo-rendering only. ADR 0006 captures the locked
13-column migration, projection schema, off-exchange cell convention,
and §7 prefix wiring at the memo_cmd edge.

### Added — `concentration-panel-overlap` (2026-05-27)

New pure-analytics module `src/irc/memo/concentration.py` computes pairwise
weighted-overlap of Top-10 holdings across every pair of active-fund picks.
When a pair's weighted overlap (Σ min(w_A[s], w_B[s])) is ≥30%, a new
`IRC_CONCENTRATION_BEGIN/END` marker block in §6 风险提示 surfaces the pair
with its overlap percentage and shared symbols (top-5 shared with elision).

This closes a long-standing gap in the discipline doc: previously the user
could see five different-looking "growth" funds in the `small_watch` list
(e.g. 008382 / 008555 / 018956 / 005825 / 519770) whose Top-5 holdings were
60–80% identical (新易盛 / 中际旭创 / 天孚通信 etc. repeated across all of
them) — buying 3 of them would have been effectively the same CPO bet 3×.
The concentration panel now flags this explicitly before execution.

Memo-only: no new `advisory_gaps` code (concentration is a pair-level
signal, `advisory_gaps` is row-level — ADR 0005 boundary preserved). No
new I/O, reads cached `OpportunityRow.constituent_analyses`. Two-run byte
equality maintained.

### Added — `top-holdings-broker-thin-advisory` (2026-05-27)

New `OpportunityRow.advisory_gaps` field carries a new advisory gap code
`top_holdings_broker_thin` that fires when an active fund has ≥2 of Top-5
holdings (or ≥20% weighted Top-5) marked with `broker_empty:*` failure
reasons. The gap is emitted through the existing `derive_thesis_from_evidence`
return slot — `thesis_state` setter invariant is preserved.

The advisory is surfaced in three places so it informs both immediate and
ongoing decisions:

- §5 picks table — affected rows are stably demoted to the tail of the table
  (informational; does not block execution)
- §6 风险提示 — a new `证据缺口（Top-5 经纪覆盖不足）` marker block lists
  the affected picks
- `discipline_report.md` section header — appends a `（证据缺口：核心持仓
  券商覆盖不足）` suffix on affected funds

Pure analytics: no new I/O, no new fetcher, reads cached `ActiveFundSnapshot`
data already in the opportunity layer. ADR 0005 captures the load-bearing
design decision (separate field vs. widening `evidence_gaps`).

### Added — `memo-picks-table-decision-mirror` (2026-05-26)

Memo §5 picks table now mirrors the per-pick `单次定投上限` (tranche cap)
and `触发状态` (trigger status) columns that already render in
`decision_report.md`'s "决策面板" section. A reader of `memo.md` alone
no longer has to cross-reference the decision report to see the live
trigger state or sizing budget for each pick. Pure renderer change —
no new data dependencies; reuses `suggest_tranche_pct` + `evaluate_trigger`
via the relocated public helpers.

Changes:

- `src/irc/memo/picks_table.py` — `PickRow` gains `tranche_cap_pct:
  float | None = None` and `trigger_status: str = ""` (frozen-dataclass
  safe defaults; all 21 existing call sites use kwargs). New private
  helper `_format_trigger_status_compact` renders triggers as
  `{name} ✓ / ✗ / ⚠` joined by `<br>` for multi-trigger rows.
  Em-dash `—` placeholder for None / zero / empty cases (matches
  existing `_format_citations_cell` convention). Header column order:
  `… | 主要理由 | 单次定投上限 | 触发状态 | 证据 |`.
- `src/irc/decision/sizing.py` — `MACRO_FIELD_TO_KEY` (was
  `_MACRO_FIELD_TO_KEY` in `decision/report.py`) and
  `resolve_trigger_current_value` (was `_resolve_trigger_current_value`)
  promoted to public symbols so the memo renderer can share them.
- `src/irc/decision/live_inputs.py` — new module hosts
  `read_live_decision_inputs` (extracted from `decision/report.py`);
  reads macro snapshot + per-instrument weekly returns from DuckDB.
  Connect-failure and query-failure paths now emit WARNING to stderr
  instead of staying silent.
- `src/irc/decision/report.py` — re-imports the relocated helpers;
  `decision_report.md` output is byte-identical post-refactor.
- `src/irc/commands/memo_cmd.py` + `src/irc/commands/decision_cmd.py`
  — wire the new columns through `_build_pick_rows` and feed live
  decision inputs.

H3 / SAME-3 invariant: the two new cells emit ZERO `[ref:...]` markers
(`test_picks_table_new_columns_carry_no_citation_markers`). The §5
table is inside `<!-- IRC_PICKS_TABLE_BEGIN/END -->` markers — the new
columns come from the deterministic renderer, never from LLM output.

### Added — `qdii-premium-fetcher` (2026-05-26)

QDII premium-to-NAV fetcher unblocks the 8 instruments left in the
`qdii_premium_unknown` bucket. Three on-exchange (517641, 161716, 159691)
now read a live signed premium from AkShare's `fund_etf_spot_em()` bulk
endpoint (column `基金折价率`; sign-flipped to premium-positive units).
Five off-exchange feeders (019172, 513690, 513650, 016452, 019547)
receive a synthetic 0.0 because they transact at NAV — no fetch needed.
The existing gate `qdii_premium_unknown` is retained for the missing-data
path; a new gate `qdii_premium_too_high` fires when premium exceeds the
threshold. Both gates are mutually exclusive by construction.

Net effect on today's data: the largest remaining blocked bucket (8 of
the 11 rows) becomes either actionable (when premium ≤ threshold) or
explicitly blocked with a meaningful "premium = X% > Y%" reason instead
of "unknown".

Changes:

- `src/irc/scoring/qdii_premium.py` adds the canonical
  `_QDII_ASSET_CLASSES: Final[frozenset[str]] = frozenset({"us_etf",
  "hk_etf", "qdii_global"})` and the pure `qdii_premium_for_row(...)`
  router that returns `None` for non-QDII, `0.0` synthetically for
  off-exchange feeders, and delegates to the AkShare fetcher otherwise.
  Four prior duplicate definitions of `_QDII_ASSET_CLASSES` in
  `decision/gates.py`, `memo/diagnostics.py`, `allocation/target_weights.py`,
  and `commands/memo_cmd.py` are removed; all sites now import the
  canonical home.
- `src/irc/data/akshare_client.py` adds `fetch_qdii_premium_pct(symbol)`
  backed by `_fetch_full_etf_spot_table()` with `lru_cache(maxsize=1)`
  (one AkShare call per run). Signed premium: `-(基金折价率)/100`.
  Failures are logged at WARNING with `exc_info=True` before returning
  `None` (no silent swallow).
- `src/irc/scoring/pipeline.py` `run_scoring` gains optional
  `qdii_premium_resolver` parameter; resolver invocation is guarded by
  try/except so a raising resolver does not drop subsequent rows.
- `src/irc/decision/gates.py` `compute_blocking_reasons` registers the
  new `qdii_premium_too_high` reason; `decide_row` reads
  `qdii_max_premium_pct` from config.
- `src/irc/decision/report.py` adds label + remediation for the new
  reason; `compose_decision_report` threads the threshold through.
- `src/irc/commands/{score,memo,decision}_cmd.py` compose the resolver
  closure / read the threshold from `bundle.discovery.hard_filters`.
- `src/irc/schemas/discovery.py` adds `qdii_max_premium_pct: float`
  (default `QDII_MAX_PREMIUM_DEFAULT = 0.05`, constraint `gt=0` —
  zero or negative threshold is invalid configuration). `config/discovery.yaml`
  template updated.
- `docs/adr/0002-active-fund-fetch-engine.md` §5 adds an F6 paragraph
  cross-referencing the QDII premium fetcher.
- `CONTEXT.md` adds glossary entries for "QDII premium-to-NAV ratio",
  `fetch_qdii_premium_pct`, the off-exchange synthetic-zero policy,
  `qdii_premium_too_high`, and `qdii_max_premium_pct`.
- The `qdii_premium_unknown` remediation text in `src/irc/decision/report.py`
  is rewritten to mention AkShare (drops the obsolete "FX status" line).

### Added — `policy-b-foreign-heavy` (2026-05-26)

Policy B rule 2.5 (foreign-heavy short-circuit) — when a fund's top-N
constituent weight is ≥ 50% non-CN-listed (HK/US), accept fund-level
NAV + announcement evidence as the data leg instead of requiring per-
holding filings. Mirrors the 2026-05-25 QDII fetch reform (ADR 0002
§5 F4 / `project_qdii_fetch_reform` memory) for the active-fund path
that Policy B governs. Unblocks 006809 and any future HK-heavy
discretionary fund whose holdings are unreachable by the CN filings
pipeline. Precedence: rule 2.5 fires between rule 2 and rule 3; no
existing rule changes.

Changes:

- `src/irc/opportunity/policy_b.py` adds `_compute_foreign_listed_share`
  (pure helper aggregating constituent weights by exchange), the
  `FOREIGN_HEAVY_THRESHOLD: Final[float] = 0.50` constant, and rule 2.5
  in `evaluate_policy_b`. `PolicyBVerdict` gains `fired_rule: str = ""`
  (structural discriminator; populated with `"1" / "2" / "2.5" / "3" /
  "4" / "5"` at each emit site).
- `src/irc/opportunity/rejection_log.py` appends new gap code
  `foreign_heavy_fund_level_evidence_missing` (mapped to rejection
  reason `foreign_heavy_evidence_missing`) LAST in `_GAP_TO_REASON` to
  preserve all prior precedence.
- `src/irc/fundamentals/types.py` adds optional field `fund_level_evidence:
  tuple[ThesisEvidence, ...] = ()` to `ActiveFundSnapshot` (backward-
  compatible default; legacy cache files rehydrate to `()`).
- `src/irc/fundamentals/snapshot.py` adds `_fetch_active_fund_level_evidence`
  helper that unconditionally fetches NAV (`fetch_fund_nav_report`) +
  announcements (`fetch_fund_announcements`) for every active fund;
  `_build_active_fund_snapshot` now stamps `fund_level_evidence` on
  every `ActiveFundSnapshot` it builds.
- `src/irc/fundamentals/snapshot_cache.py` round-trips the new field
  symmetrically (legacy files default to `()`).
- `src/irc/commands/opportunity_cmd.py` `_stamp_fund_level_evidence_from_verdict`
  stamps fund-level citations onto publishable rule-2.5 rows (`scope=
  "instrument"`, `owner_instrument_id=fund_id`). `FetchPlan.total_calls()`
  accounts for the +4 AkShare calls per active fund (1 NAV + 3
  announcement endpoints).
- `docs/adr/0003-failure-mode-policy-b.md` adds §7 documenting the rule
  2.5 contract; precedence table amended from "five rules" to "six rules".
- `CONTEXT.md` adds glossary entries for `ActiveFundSnapshot.fund_level_evidence`,
  "Foreign-heavy fund (rule 2.5 short-circuit)", and `FOREIGN_HEAVY_THRESHOLD`.

### Added — `decision-confidence + bond-yield-anchor` (2026-05-26)

Closes the five issues that prevented a reader of `outputs/<DATE>/memo.md`
+ `decision_report.md` from making a buy decision with confidence:
(1) `decision_report` flagged 006809 as `actionable_buy` while memo §5
correctly excluded it under Policy B, (2) no per-pick when-to-buy signal
(trigger thresholds declared but current values not shown), (3) no
how-much signal (footnotes said "this plan does not size trades"),
(4) every row's rationale collapsed to "估值=very_expensive、热度=normal",
(5) bond-fund valuation_state was permanently `evidence_insufficient`
because `cn_bond_yield_percentile` was defined in `OpportunityInput`
but never populated.

Net effect on today's outputs:

- 014502 / 511010 / 511220 valuation went from `evidence_insufficient`
  → `expensive` (CN10Y at 1.75% sits at 20th percentile of 3y history;
  composite scores now comparable instead of annotated "不得用于优先级比较").
- 006809 correctly reclassified: now under "Blocked → Excluded from
  opportunity_report (Policy B / dual-coverage gate)" with a one-line
  remediation explaining the HK-constituent data-leg gap.
- decision_report.md gains a "决策面板 / Per-pick decision summary"
  section showing, for each actionable pick: role, target cap,
  per-tranche cap (`build mode → target ÷ 4`), trigger condition with
  live current value (`触发 weekly_drawdown_4pct: <= -4.00%; current =
  -0.77% ⇒ ✗ NOT MET`), and the operational opportunity_state
  (`valuation=expensive · heat=normal · thesis=intact · quality=weak`).
- Visible blocked count dropped from 27.5% (34/124) to 8.3% (11/132) on
  2026-05-26 data — the remaining QDII premium-unknown rows + foreign-
  fund Policy B rejections are sequenced into the follow-up plan.

Changes:

- `src/irc/data/akshare_client.py` adds `_fetch_cn_10y_yield_via_akshare`
  reading the China 10Y CGB column from `bond_zh_us_rate`; registered
  under `_AKSHARE_MACRO_HANDLERS["CN10Y"]`.
- `src/irc/data/openbb_client.py` adds `CN10Y` to `_AKSHARE_ONLY_SERIES`
  (FRED's `IRLTLT01CNM156N` is monthly; daily granularity needed for
  percentile).
- `src/irc/commands/ingest_cmd.py` adds the `CN10Y → cn_10y_yield`
  `_MacroSeriesSpec` so `irc run --only ingest` persists the series.
- `src/irc/opportunity/inputs_loader.py` computes the rank-percentile of
  the latest 10Y yield against the persisted series and populates
  `OpportunityInput.cn_bond_yield_percentile` when
  `asset_class == cn_bond_fund` (None for every other class).
- `src/irc/decision/sizing.py` (new): pure helpers — `suggest_tranche_pct`
  (`build` mode → target/4), `evaluate_trigger` (`met / not_met / missing`),
  `format_why_when_line` (renders `触发 X: condition; current=… ⇒
  ✓/✗/⚠ marker`).
- `src/irc/decision/gates.py`: `decide_row` + `compute_blocking_reasons`
  gain `excluded_from_opportunity` flag; new blocking reason
  `opportunity_excluded` flows through `_BLOCKING_REASON_LABEL` +
  `_BLOCKING_REMEDIATION` so the blocked-section explains it.
- `src/irc/decision/report.py` adds `_decision_sheet_section` rendered
  between "Actionable buys" and "Blocked — fixable today"; threads
  `trade_plan_trades / build_mode / macro_snapshot / weekly_return_by_id
  / opportunity_state_by_id` through `compose_decision_report`.
- `src/irc/commands/decision_cmd.py` reads `opportunity_report.json`
  (published-id set + per-id state), latest macro values + 7-day-prior
  NAV from `local.duckdb`, and passes them in. Read-only and graceful
  on locked DBs (prints WARNING; falls back to "未知 / unknown" markers).
- New: `docs/account-onboarding.md` — how to add `cn_brokerage` /
  `hk_connect` / `us_brokerage` venues with concrete steps + the per-
  venue universe unlock count.
- New: `docs/superpowers/plans/2026-05-26-decision-confidence-and-
  blocked-cleanup.md` — multi-stage plan including the deferred Stage 2
  (foreign-fund Policy B relaxation for 006809) and Stage 4 (QDII
  premium-to-NAV fetcher to unblock the 8 remaining premium-unknown
  rows).
- Tests: `tests/data/test_akshare_client.py` adds CN10Y dispatch test;
  `tests/opportunity/test_inputs_loader.py` adds 3 bond-yield-percentile
  tests (bond-fund populated / non-bond None / empty-series None);
  `tests/decision/test_gates.py` adds `opportunity_excluded` blocking
  reasons tests; `tests/decision/test_sizing.py` (new): 12 sizing +
  trigger-evaluation tests. All 140 prior decision tests still pass.

### Fixed — `memo-decision-consolidation + readable-refs` (2026-05-25)

Closes both items in `outputs/2026-05-25/problem.md`.

**Problem #1 — memo.md misaligned with decision_report.json.** `decision_report` flagged 003318 / 519770 as `actionable_buy` (gates passed) but memo §5 rendered them as `pause_wait` / `small_watch` (opportunity overlay). Two reports answering different questions, and the memo never read decision state, so the user could not reconcile them.

**Problem #2 — refs in memo.md were unscannable.** Inline `[ref:HEXID]` 16-hex markers (e.g. `[ref:4b03af24151fe798]`) were hard to read, and the `_MAX_REFS = 40` cap in `memo/pipeline.py` truncated the appendix so some §5 picks-table refs (e.g. 511010's NAV snapshot) had no appendix entry to anchor on.

Changes:

- `irc run` now executes 10 stages — `decision` is the final stage after `memo`. Standalone `irc opportunity` / `irc decision` invocations are no longer required for the weekly workflow.
- `src/irc/decision/gates.py` promotes `_decision_status` → `compute_decision_status` and `_blocking_reasons` → `compute_blocking_reasons` (both pure, public). Old names kept as aliases.
- Memo §5 picks table gains a **决策** column between 综合分* and 机会状态, populated via `compute_decision_status` over the same primitives `decision_cmd` uses. Cell values: `候选可执行` / `阻断` / `观察` / `回避`.
- Memo §1 TL;DR prepends a **今日唯一行动** banner derived from `actionable_buy` picks (`✅ 候选可执行：003318, 519770` or `⚪ 本周无候选可执行`).
- New module `src/irc/memo/footnote_renderer.py` post-processes the published `memo.md`: inline `[ref:HEXID]` markers become `[1]` / `[2]` / … (global single sequence, ASCII brackets); appendix entries gain a `**[N]**` prefix and preserve the original `[ref:HEXID]` at the line tail for grep/audit. Drops the `_MAX_REFS = 40` cap on the appendix so every ref in the pool always has an entry. Audit gates still operate on the canonical hex-form draft (no audit code changes).
- `src/irc/pipeline_outputs.py` adds `decision_report.{json,md}` to `STAGE_REQUIRED_OUTPUTS`.
- README and `docs/diagrams/overall-workflow.html` updated to show the 10-stage pipeline; ADR 0001 gains a 2026-05-25 addendum documenting the published-memo veneer.
- Tests: `tests/decision/test_gates.py` adds the `compute_decision_status` / `compute_blocking_reasons` golden tables; `tests/memo/test_picks_table.py` adds the 决策-column header + ZH-map assertions; `tests/memo/test_pick_rows.py` adds three decision-status wiring tests; `tests/memo/test_tldr_action_banner.py` adds four banner-branch tests; `tests/memo/test_footnote_renderer.py` adds seven post-pass tests; `tests/commands/test_run_cmd.py` extended for the new `decision` stage.

### Fixed — `memo-evidence-pillar + qdii-fetch-reform + discovery-thresholds` (2026-05-25)

End-to-end fix for the 2026-05-25 memo readability gap. The user opened
`outputs/2026-05-25/memo.md` and found §2 (宏观环境) was a hardcoded
anti-fabrication caveat with no real data, §3 (黄金视角) had no `[ref:...]`
markers, 8/28 role buckets were empty, and the discipline report listed
~22 funds under `证据不足 / Failed fetch`. None of these surfaces gave the
reader anything to actually anchor an investment decision on.

- **Macro evidence pillar — memo §2 and §3 now consume real data**
  (`src/irc/memo/macro_pillar.py` new, `src/irc/commands/gold_cmd.py`,
  `src/irc/commands/memo_cmd.py`, `src/irc/memo/template.py`,
  `src/irc/memo/synthesizer.py`, `src/irc/memo/evidence_pool.py`). Macro
  data (`real_yield_10y_tips`, `DXY`, `vix`, `inflation_5y5y`, `DGS10`)
  was already in DuckDB; theme reports (`us_monetary`, `cn_monetary`,
  `geopolitics`, `us_fiscal_politics`, `cn_equity_property_policy`,
  `gold_drivers`, `holdings_sector`) were already on disk. They were just
  never plumbed into the memo. `gold_cmd` now emits each as a
  `ThesisEvidence` with `scope="asset_class_macro"` into
  `gold_regime.json["evidence"]` (already part of the publishable citation
  universe). `memo_cmd` reads them back, calls `macro_pillar.render_*`
  helpers to produce deterministic §2 / §3 bullets with `[ref:...]`
  markers, and the synthesizer locks them between `IRC_MACRO_LINES_*` /
  `IRC_GOLD_EVIDENCE_*` comment markers (same pattern as §7). The static
  `_MACRO_SUMMARY` constant is kept as a fallback only. **Memo §2 + §3
  now carry 16 macro citations including Fed Chair transition, Russia-
  Ukraine + Iran summit, A-share property policy, real yield = 2.18% and
  DXY = 99.34 snapshots.**
- **QDII fund-level fetch — replaces sentinel skip**
  (`src/irc/opportunity/lookthrough.py`,
  `src/irc/fundamentals/snapshot.py`). ADR 0002 §5 F4 mandated a
  zero-fetch sentinel for every `qdii_us` / `qdii_hk` / `qdii_global`
  `LookthroughTarget`, which routed 20 QDII funds to the discipline
  failure section with `qdii_information_unavailable`. But QDII funds
  ARE CN-registered — the existing `fetch_fund_nav_report` and
  `fetch_fund_announcements` adapters return real NAV + quarterly /
  annual report announcements for them. `lookthrough.py` now populates
  `provider_symbol=instrument_id` on QDII targets, and `build_snapshot`
  routes them through `_build_fund_level_snapshot` when
  `provider_symbol` is non-empty; the sentinel is kept only for
  raw-index aggregate keys. **Discipline-report `证据不足 / Failed
  fetch` count: 22 → 2** (the two remaining are
  `incomplete_constituent_data` cases on `004814` and `501025`).
  Three QDII funds (161716 易方达全球美元债LOF, 017641 摩根标普500
  指数 QDII, 016452 南方纳斯达克100 QDII) are now publishable picks.
  ADR 0002 §5 F4 statement that QDII is the only source of
  `qdii_information_unavailable` no longer holds; pending an ADR
  amendment sweep.
- **Discovery thresholds — relax over-strict V1 filters**
  (`config/discovery.yaml`, `src/irc/templates/config/discovery.yaml`).
  `us_etf_expense_ratio_max` 0.003 → 0.012 (CN-domiciled US-tracking
  ETFs charge 0.6%–1.0%, never the native-US 0.03%; the old threshold
  filtered out essentially every candidate from the
  `core_us_equity` / `defensive_us_bond` / `hedge_low_correlation`
  buckets). `cn_fund_aum_cny_min` 500M → 200M (themed active funds in
  `consumer` / `tech` / `soe` / `real_estate` / `semiconductor` are
  typically 200M–400M; raising the floor to 500M dropped them all).
  `role_bucket.min_candidates_per_role` 8 → 3 and `fail_below` 5 → 1
  (the original thresholds failed buckets with up to 4 surviving
  candidates; any non-empty bucket is now usable signal). **Role-bucket
  warning banner: `8/28 → 1/21`** (only `satellite_cn_real_estate`
  still has zero candidates).
- **Memo picks-table lock — prevents LLM citation cross-borrowing**
  (`src/irc/memo/template.py`, `src/irc/memo/synthesizer.py`). The
  picks table is now wrapped in `IRC_PICKS_TABLE_*` markers and the
  synthesizer is instructed to keep it byte-for-byte (matches the §7
  `IRC_EXECUTION_LINES_*` pattern). Prior to this lock the LLM was
  observed substituting `[ref:a3ff80e80e66caed]` (a 518880 announcement
  ref) into 159937's row → `wrong_instrument_citation` blocking finding.

### Verification

- 1037 unit tests pass.
- Memo audit: `审核通过`. Citation audit: 0 findings (was blocking).
- Rebuilt `outputs/2026-05-25/`: memo.md, opportunity_report.json,
  discipline_report.md, gold_regime.json all reflect the new behavior.
- Earlier-stage artifacts (`discovered_watchlist.csv`, `scoring.json`,
  `proposed_allocation.yaml`, `trade_plan.yaml`) remain from the
  morning run — re-run `uv run irc run` to refresh them under the
  loosened discovery filters (slow: LLM-per-row in discover + score).

### Fixed — `news-fetch-info-leg + memo-audit-stabilization` (2026-05-25)

End-to-end fix for the 2026-05-24/25 pipeline halt where 11 funds were
rejected with `insufficient_info_coverage_top_half` and the memo stage
blocked on the citation gate across repeated LLM regen attempts.

- **CN + HK news fetchers — EastMoney-direct fallback**
  (`src/irc/fundamentals/akshare_fundamentals.py`,
  `src/irc/fundamentals/hkex_client.py`). Root cause: AkShare's
  `stock_news_em` calls `df.str.replace(r"　", "", regex=True)` on
  pyarrow-backed string columns; pandas dispatches the regex to
  pyarrow's RE2 engine which rejects `\u` escapes →
  `ArrowInvalid` for **every** CN symbol. Compounded by the installed
  AkShare lacking `stock_hk_news_em` entirely, which flagged every HK
  constituent as `hk_news_unsupported_adapter`. Added
  `_fetch_eastmoney_news_direct` to both modules — calls EastMoney's
  search-API JSONP endpoint directly, parses with Python `re` (not RE2),
  and works for both 6-digit CN and 5-digit HK codes. Fallback fires on
  any adapter exception; `hk_news_adapter_available()` now returns True
  unconditionally. **Discipline-report
  `insufficient_info_coverage_top_half` count: 11 → 0.**
- **Memo audit — multi-instrument paragraph handling**
  (`src/irc/memo/numeric_audit.py`). `_check_instrument_citation` gained
  a `paragraph_instrument_hits` parameter; when a marker's owner is
  co-mentioned in the same paragraph, the audit no longer flags the
  non-owning instrument with `wrong_instrument_citation` — that marker
  correctly cites the co-mentioned sibling. The dual-leg requirement
  still applies per instrument.
- **Memo audit — whitespace-insensitive exemption match**
  (`src/irc/memo/numeric_audit.py`). `_has_actionable_keyword` now
  normalises whitespace on both the prose and each
  `_NON_ACTIONABLE_LABELS` entry before substring matching, so
  paraphrases like `本期黄金ETF全部暂停加仓` match the existing
  `本期黄金 ETF 全部暂停加仓` label.
- **Memo audit — broader exemption patterns**
  (`src/irc/memo/numeric_audit.py`). Three new regex exemptions in
  `_NEGATED_ACTION_PATTERNS`: `条件性减速定投` (any context),
  `列入…暂停加仓` (bucket-membership enumeration),
  `(均)?(按|依据|根据)规则…暂停加仓` (rule-citation section headers),
  `(本期)?(均|全部|都)\s*暂停加仓` (bucket-aggregation summaries). All are
  meta-descriptions of pause_wait bucket behaviour, never action
  recommendations.
- **Memo synthesizer — strengthened guardrails**
  (`src/irc/memo/synthesizer.py`). Four new hard rules in `_GUARDRAILS`:
  Rule 8 forbids multi-instrument summary paragraphs and requires
  per-instrument bullets with per-instrument `[ref:...]`; Rule 9 lists
  six audit-whitelisted TL;DR phrasings verbatim plus a forbidden-
  paraphrase list; Rule 10 extends Rule 6 to **every** paragraph
  mentioning a fund/ETF code, including descriptive prose; Rule 11
  forbids LLM-invented "补充披露" paragraphs and requires constituent
  `[ref:...]` to come from the same fund's evidence pool (no
  cross-fund borrow).
- **Memo LLM timeouts** (`src/irc/memo/synthesizer.py`,
  `src/irc/memo/auditor.py`). Bumped `synthesize_memo` and
  `audit_memo` to `timeout_s=240.0`; the 30 s default was insufficient
  for deepseek-reasoner CoT with the strengthened guardrail block.

### Fixed — prior unreleased

- Memo publish now treats explicit audit veto variants such as
  `不予直接通过` and `需修订后重新提交` as blocking, not only the exact
  phrase `审核未通过`.
- Reduced citation-gate false positives for conservative/no-add disclosures
  such as grouped `pause_wait` summaries, rule-based `暂停加仓`, and
  target-weight disclaimers, while preserving blocking behavior for real
  uncited actionable conclusions.
- Hardened memo compliance sanitization around ambiguous `revenue_yoy` raw
  fields, valuation-risk phrasing, QDII execution caveats, and
  evidence-insufficient scoring notes.
- Discipline reports now carry attempted evidence fetch types from
  opportunity snapshots, so rows such as `001877 宝盈国家安全沪港深股票A`
  show concrete attempts (`holdings, filing, broker, news`) instead of
  `(none)`.

## [0.9.0] — 2026-05-24

### Added — `thesis-cards-evidence-gap` remediation (10-item autodev run)

Ten-item end-to-end fix for the discovery that `thesis_cards.yaml` / `memo.md`
/ `discipline_report.md` were emitting conclusions without verifiable per-row
evidence. Run dir: `docs/2026-05-22-thesis-cards-evidence-gap/`.

- **Item 001 — `OpportunityRow.contributing_dimensions`** (PR #55). New
  `frozenset[str]` field populated by the scoring engine with the sub-states
  driving `opportunity_state`. Downstream V1 + V2 audit gates check
  per-dimension citation binding.
- **Item 002 — Unified citation data model** (PR #56, ADR 0001). New
  `CitationMeta` schema, `build_cited_map` provenance builder,
  `select_citations` deterministic selector (SAME-3 invariant), `citation_id`
  as 16-hex-char SHA256 prefix. `[ref:{citation_id}]` marker grammar locked.
- **Item 003 — Active-fund constituent layer** (PR #57, ADR 0002). New
  `ActiveFundSnapshot` cache, `LookthroughTarget("active_fund", ...)`
  routing, top-N constituent dispatch with cache-probe + budget +
  resumable state. Per-stock evidence aggregation.
- **Item 004 — Live `fund_announcement_em` verification** (PR #58). Test-only
  PR that locked AkShare 1.18.63 support via 3 topic-specific endpoints
  (`fund_announcement_dividend_em` / `_report_em` / `_personnel_em`); uses
  `报告ID` as opaque citation key.
- **Item 005 — Per-asset-class citation coverage** (PR #59). `cn_etf`, gold,
  cn_bond, tracked CN indices route to fund-level NAV + announcement;
  `qdii_*` reclassified as V1-excluded (info-leg blocker). New
  `FundLevelSnapshot` / `FundNavReport` / `FundAnnouncement` dataclasses.
- **Item 006 — Failure-mode + Policy B v2** (PR #60, ADR 0003). Weight-aware
  top-half info quorum, structured `rejections.json` with deterministic
  precedence, H3 universal gapped-row invariant, atomic write-at-end.
- **Item 007 — Memo + discipline renderers + alias-builder** (PR #61,
  ADR 0004). `[stock:{symbol}] [ref:{citation_id}]` markers in evidence
  pool, nested `thesis_evidence` bullets + inline top-5 holdings + full
  `## 持仓明细` appendix in discipline_report.md. `build_alias_maps` with
  collision invariant.
- **Item 008 — Publishable-set lockdown** (PR #62). 24-test integration
  suite locking 23 ACs end-to-end before item 009 flips the citation gate.
  Two-run byte equality, H3 partition completeness, snapshot-cache
  freshness, QDII exclusion across all four output surfaces. Production
  fix: `_classify_rejection_reason` iterates `_GAP_TO_REASON` key order
  (not `evidence_gaps` tuple order) so QDII precedence holds regardless
  of structural-gap ordering.
- **Item 009 — Citation gate (default `block`)** (PR #63). New
  `IRC_CITATION_ENFORCE_MODE = {off, warn, block}` env var (canonical
  `outputs/YYYY-MM-DD/` paths force `block` regardless). Four audit
  functions: `find_uncited_opportunity_rows`,
  `find_incomplete_constituent_analyses`, `find_missing_pick_citations`,
  `find_uncited_discipline_rows`, plus filled-in `find_uncited_conclusions`
  body. Shadow log `outputs/<date>/citation_audit.json` written in all
  modes including `block`. New gap code `citation_gate_blocked`.
- **Item 010 — DuckDB `fund_holdings` ingest** (PR #64). New
  `src/irc/data/fund_holdings_ingestor.py` with 30-day staleness gate,
  asset-class filter, idempotent batch upsert wrapped in
  `BEGIN`/`COMMIT`/`ROLLBACK`. Wired into `run_ingest` as best-effort
  enrichment so the long-empty `fund_holdings` DuckDB table now feeds
  `scoring/metrics_loader._latest_holdings_concentration` real data
  instead of NaN.

### Changed

- `_GAP_TO_REASON` keys iterate in dict-literal insertion order with
  `qdii_information_unavailable` first (locked by structural unit test).
- `_write_opportunity_outputs` returns a 7-tuple after Policy B v2
  refactor; `_discipline_row_from` consumers receive the same.
- `compose_discipline_markdown` signature gains
  `publishable_rows` + `pick_order_iids` keyword-only kwargs
  (backward-compatible — defaults to empty tuples).
- `_evidence_from_dict` promoted to `ThesisEvidence.from_dict` classmethod;
  the legacy shims at `snapshot_cache.py` + `memo_cmd.py` delegate
  unchanged for back-compat.
- `irc.memo.citation_selector` relocated to `irc.opportunity.citation_selector`
  to break a `opportunity ↔ memo` cycle introduced by item 007; old path
  preserved as a one-line re-export shim.

### Fixed

- `fund_announcements_unavailable` gap code was emitted by snapshot.py but
  missing from `_GAP_TO_REASON`, causing `RuntimeError` at runtime
  (closed inline as part of item 008).

### Known follow-up

- Pre-existing DAG cycle introduced by item 009 (`opportunity/auditor.py`
  imports `irc.memo`) — `test_dag_acyclic_check_*` fails since item 009
  on the base branch as well. Flagged for follow-up before the next
  item-009-touching change.

## [0.8.7] — 2026-05-21

### Added
- **Universe quality-weighted ranking + `qdii_global` asset class.** Replaces
  the fund_code-ascending tiebreaker in `_candidate_rank` with a 1Y-return
  quality signal fetched via `fetch_open_fund_ranks()` (lru-cached, degrades
  gracefully to empty on failure). Adds a new `qdii_global` asset class so
  global-mandate QDII active funds (e.g. 270023 Guafu Global) bucket separately
  from `qdii` (China-biased). Changes are backward-compatible: `_apply_caps`
  with `returns={}` yields the same selection as before. Downstream consumers
  (`decision`, `allocation`, `memo`, `opportunity`) updated to handle
  `qdii_global` explicitly. See
  `docs/2026-05-21-universe-quality-ranking-qdii-global/MASTER-SPEC.md` for
  full decomposition; 11-task plan, 11 commits.

## [0.8.6] — 2026-05-19

### Added
- **decision_report.md trust-check fixes (7-item autodev-loop).** A
  non-finance reader opening `decision_report.md` previously had no
  in-document way to decode column terms, no visibility into the
  memo's compliance audit, no warning about execution drift, no
  protection against QDII premium-blind buying, and no headline
  telling them what (if anything) to actually do today. The
  layperson-facing report now leads with a bilingual **"今日唯一行动
  / Today's only action"** headline, surfaces a **🛑 合规审核未达标**
  banner whenever `memo_audit.txt` reports anything weaker than
  `审核通过`, surfaces an **⚠️ 执行漂移提醒** banner when cash
  residual exceeds target by ≥ 5pp, refuses to mark any
  `us_etf` / `hk_etf` row `actionable` until `qdii_premium_pct` is
  collected, collapses redundant blocked rows with **"✓ Role already
  met"** lines when a proxy already fills the asset class, renders
  every row with a Chinese `name_cn` column plus bilingual
  `score_action / 中文标签` cells, and closes with a `## 术语速查
  (Glossary)` explaining 11 cryptic terms. Pure-functional throughout
  — `extract_audit_summary`, `_execution_drift`, `_build_proxy_coverage`,
  the QDII gate in `decide_row`, the headline renderer — all
  deterministic; no I/O inside. Per-item PRs #41–#47; see
  `2026-05-19-trust-check-fixes/MASTER-SPEC.md` for the full
  decomposition and `cross-branch-diff.md` for the acceptance matrix.

## [0.8.5.1] — 2026-05-19

### Changed
- **Single HTTPS proxy env var.** Replaced the per-provider proxy convention
  (`OPENROUTER_HTTPS_PROXY`, `DEEPSEEK_HTTPS_PROXY`, `AKSHARE_HTTPS_PROXY`) with
  a single `IRC_HTTPS_PROXY` read by `irc.http_proxy.resolve_proxy()`. Applied
  uniformly to every outbound HTTPS call: LLM providers (DeepSeek, OpenRouter),
  web search providers (Tavily, Brave, Bocha), the Jina page extractor, and the
  DXY ingest path. Other akshare paths stay direct because they hit mainland-CN
  hosts that a non-CN proxy would hurt. `README.md` now documents the full list
  of call sites under "HTTPS proxy". Motivated by Tavily quota exhaustion +
  Brave News TLS timeouts that halted `irc research` for every EN theme; the
  proxy unblocks Brave (and Jina) while leaving the call-site-narrow akshare
  behavior intact.

## [0.8.5.0] — 2026-05-17

### Added
- **Geopolitical stress from theme report:** `gold_cmd` now derives
  `geopolitical_stress_0to1` from the persisted `geopolitics` theme report
  written by `irc research`, replacing the prior hardcoded `0.4`. A new pure
  helper `geopolitical_stress_from_theme_report` in
  `src/irc/research/geopolitical_stress.py` tallies stress vs calm keyword
  hits (EN + ZH) and applies a per-hit delta to the default, clipped to
  [0, 1]. Degrades gracefully to 0.4 when the report is absent or failed, so
  existing behavior is preserved in unconfigured environments.

### Changed
- **Remove venue_compatible downgrade gate:** `compose_opportunity_state` no longer
  demotes instruments to `small_watch` when `venue_compatible=False`. Opportunity
  state is now determined purely by valuation, heat, thesis, and product quality.
  Venue information is still tracked in `gates.py` (`venue_status` field) for
  reference but does not affect scoring. Updated test to reflect new behavior.

### Fixed
- **Decision gate: legacy file and empty-pool correctness.**
  `compose_decision_report` now handles two edge cases in the traceability
  coverage gate that previously caused silent block-all:
  (a) on-disk `memo_traceability.json` written before the v0.8.4.0 schema
  change (no `n_refs_quoted_verbatim` key) — treated as unverifiable rather
  than narrative-only; (b) empty evidence pool (`n_refs_provided=0`) —
  vacuous truth, memo cannot be faulted for missing citations.

## [0.8.4.0] — 2026-05-16

### Added
- **`discovery_rejections.csv`:** Discovery now writes per-instrument rejection
  records to `outputs/<date>/discovery_rejections.csv`. Covers three stages —
  `hard_filter`, `quality_filter`, and `role_bucket` (no-role-match orphans) —
  with multiple rejection reasons joined. Gives full traceability of why each
  instrument was dropped before scoring.
- **CSI sector indices in `_TARGET_REGISTRY`:** Ten sector targets registered
  (半导体, 医药, 新能源, 消费, 金融, 军工, 有色金属, 房地产, 国企改革, 科技) so
  sector-theme instruments can resolve to real constituent snapshots instead of
  `evidence_insufficient`. Codes verified against AkShare.
- **HK QDII targets in `_TARGET_REGISTRY`:** Four HK indices registered
  (恒生指数, 恒生科技, 港股红利, 中概互联) with top-10 hardcoded holdings via
  a new `hk_index` spec kind and `fetch_hk_index_constituents` adapter stub.
- **US extras in `_TARGET_REGISTRY`:** 道琼斯, 美国50, 美股大盘 registered for
  US lookthrough coverage.
- **红利 sector target:** 000922 (中证红利) registered as an additional sector index.

### Changed
- **Sector proxy layer removed:** `sector_proxy.py` deleted; `opportunity_cmd`
  now resolves sector themes via direct snapshot lookup using the expanded
  registry, eliminating the broad-fallback approximation.
- **`DiscoveryRunResult` extended:** Carries a `rejections` DataFrame field;
  `discover_cmd` writes it to CSV alongside watchlist and diagnostics.

## [0.8.3.0] — 2026-05-16

### Added
- **Typed EDGAR error codes:** `edgar_client` now returns one of six typed
  constants (`EDGAR_ERROR_MISSING_EMAIL`, `EDGAR_ERROR_HTTP_4XX`,
  `EDGAR_ERROR_HTTP_5XX`, `EDGAR_ERROR_NETWORK`, `EDGAR_ERROR_DECODE`,
  `EDGAR_ERROR_CIK_MISS`) on every failure path instead of raw `None`.
  The CIK integer parse path is now guarded against malformed SEC data.
- **EDGAR error code propagation:** US fundamentals snapshot failures now tag
  `ConstituentSnapshot.failure_reasons` with the typed error code from EDGAR,
  making diagnostics visible in `evidence_gaps`.
- **Sina fallback for SZSE index constituents:** `akshare_fundamentals` falls
  back to Sina Finance when the CSI index API returns no data for 399xxx codes
  (e.g. 创业板指), using the same parsing pipeline as the primary path.
- **Refined `evidence_gaps` constituent labels:** `constituent_fetch_failed` is
  now distinguished from `constituent_missing` by checking `failure_reasons`;
  snapshots with no failure record but empty filings are correctly classified
  as `constituent_missing` rather than a fetch failure.
- **`constituent_not_applicable` label exported publicly:** `NON_INDEXABLE_ASSET_CLASSES`
  is now a public constant in `thesis_evidence`; `states.py` imports the public
  symbol instead of the private alias.

### Fixed
- **Memo TL;DR mode source:** `_derive_tldr_lines` now reads the trade-plan
  `mode` field (e.g. `steady_accumulate`) from `plan.yaml` instead of the
  allocation YAML, eliminating the "build" fallback that contradicted the
  memo body on every run.
- **Weak-link reason in `small_watch` state:** `compose_opportunity_state` now
  threads the weakest classifier's reason into the `small_watch` catch-all,
  making the evidence chain auditable.
- **`asset_class` threading:** `opportunity_cmd` now passes `asset_class`
  through to `derive_thesis_from_evidence` so non-indexable classes correctly
  skip the constituent gap check.


### Added
- **DuckDB evidence wiring:** Opportunity inputs loader now queries DuckDB for
  rolling returns, max drawdown, and percentile rank per instrument — populating
  `evidence_returns` fields that drive valuation/heat decisions.
- **Memo picks table:** Pre-rendered Markdown table of top picks with action
  labels, deduplicated across allocation and trade plan sources. Inlined into
  the LLM memo skeleton for grounded recommendations.
- **Memo evidence pool:** Per-instrument numeric facts (1Y return, drawdown,
  percentile) surfaced alongside thesis and valuation data in the LLM prompt.
- **Sector proxy snapshots:** Instruments mapped to sector themes now fall back
  to proxy snapshot data when no direct snapshot target exists.
- **QDII lookthrough normalization:** QDII fund display names (标普500, 纳斯达克100)
  now correctly map to registered snapshot targets.
- **Theme-report-only thesis:** Instruments without a fundamentals snapshot can
  still derive thesis state from research theme reports alone.

### Changed
- Memo reference budget widened from 200 to 400 characters per citation.
- Opportunity command prints quality warnings when thesis or valuation coverage
  falls below thresholds.

## [0.8.1.0] — 2026-05-16

### Fixed
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
- **Quality gate refactoring:** Split `evaluate_research_quality` into focused
  helpers; wrap `FRESHNESS_DAYS_BY_THEME` as immutable `MappingProxyType`.
- **Eval staleness check:** Research eval now warns when `research_status.json`
  is older than 7 days.

### Added
- **Time-filtered search:** Theme queries now pass `freshness_days` per theme
  (7-30 days) so providers return dated news articles instead of homepages.
- **`eval --all` summary:** Prints per-stage and overall PASS/WARN/FAIL.
- **All-target fundamentals snapshot:** `irc fundamentals snapshot --all` runs
  every registered target in one invocation.

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
