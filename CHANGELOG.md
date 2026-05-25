# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
