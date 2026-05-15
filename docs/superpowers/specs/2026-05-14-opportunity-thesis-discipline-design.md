# Opportunity Thesis Discipline Design

## Purpose

The current pipeline can discover, score, allocate, plan buys, synthesize a memo, and block unsafe decisions. It still does not answer the user's core behavioral problem:

- "I can sometimes tell when something looks buyable, but I do not know when to sell."
- "The information I see is usually about hot or recently profitable funds, so I end up chasing winners."
- "When a fund falls about 20%, I sell from fear, then it often rebounds without me."

This design adds a disciplined opportunity and thesis layer for Mainland China purchasable funds and ETFs. The goal is not to predict prices. The goal is to produce an auditable loop:

```text
discover candidates -> identify cold-but-intact opportunities -> build thesis cards
-> set DCA discipline -> monitor falsification and heat -> review, trim, or exit
```

## Product Scope

The system focuses on funds and ETFs that a Mainland China investor can plausibly buy through local venues:

- Mainland on-exchange ETFs through `cn_brokerage`.
- Mainland off-exchange funds through `cmb_fund` or similar fund channels.
- QDII funds that provide US or HK exposure through Mainland purchasable products.
- Gold products already supported by the existing gold path.

ETF and index products are the main line. Active funds are allowed as supplementary observations, but they should be treated more conservatively because manager behavior, style drift, holdings disclosure lag, and product changes add extra uncertainty.

## Non-Goals

- Do not place orders or integrate broker execution.
- Do not convert the system into short-term rotation trading.
- Do not let LLM prose directly produce buy, sell, trim, or exit actions.
- Do not run deep LLM research over thousands of funds every time.
- Do not treat a 20% drawdown as an automatic sell signal.
- Do not use the generated universe from another worktree as a hidden runtime dependency.
- Do not use Local Deep Research (LDR) or any self-hosted agent loop for thesis research. LDR is removed from the project.

## Candidate Source

The runtime source of truth is always the current repository root.

The candidate universe is loaded through `load_repo_configs()` from:

- `config/universe/cn_funds.yaml`
- optional `config/universe/cn_funds.generated.yaml`

`config_loader.py` merges the curated file first and the generated file second. If the same `instrument_id` appears in both, the curated row wins.

The file at:

```text
/Users/snow/Documents/Repository/investment-research-copilot.worktrees/copilot-subagent-driven-dev/config/universe/cn_funds.generated.yaml
```

is a useful bootstrap reference, not a runtime dependency. It currently contains 359 instruments: 238 `cn_equity_fund`, 40 `cn_bond_fund`, 40 `hk_etf`, 40 `us_etf`, and 1 `cn_etf`. If this universe is needed in the current worktree, it should be copied into the current repo as `config/universe/cn_funds.generated.yaml` or regenerated with:

```text
uv run irc universe build-cn-funds
```

Opportunity analysis must not read the external worktree path directly.

## Candidate Funnel

The system must not deeply analyze every public fund on every run. Full-market scanning is only a candidate-generation step.

The intended funnel is:

```text
Raw public fund catalog
  -> generated universe, roughly hundreds
  -> discovery filters, roughly tens
  -> opportunity states, usually dozens or fewer
  -> thesis cards for holdings, watchlist, and same-theme winners
```

The current generated-universe caps are already a good first boundary:

- Broad active `cn_equity_fund`: 40.
- Each sector/factor theme: 20.
- CN bond funds: 40.
- CN ETFs: 80.
- US QDII: 40.
- HK QDII: 40.

The opportunity layer should add another deterministic reduction before any expensive LLM reasoning:

- Keep current holdings.
- Keep scored buy/watch candidates.
- Keep at most 1 primary and 1 backup for the same index or highly overlapping lookthrough target.
- Keep at most 2 representative funds per theme unless the theme has materially different sub-indexes.
- Keep active funds only when product quality and style stability evidence are sufficient.

## Analysis Cadence

The system should use different run depths for different jobs.

### Daily Light Check

Scope:

- Existing holdings.
- Existing thesis cards.
- Existing watchlist.

Tasks:

- Update price/NAV movement when data is available.
- Check drawdown, trend-risk, heat, premium, and trigger conditions.
- Emit `normal_dca`, `pause_dca`, `review_required`, `trim_review`, or `exit_review`.

This mode must not rebuild the universe or run theme-level deep research.

### Weekly Full Analysis

Scope:

- Current generated universe plus curated universe.
- Discovery output.
- Scoring output.
- Opportunity states.
- Thesis card refresh.
- Discipline report.

This is the normal "investment desk" run.

### Monthly Universe Rebuild

Scope:

- Re-fetch broad Mainland fund catalog.
- Regenerate `config/universe/cn_funds.generated.yaml`.
- Detect new funds, stale funds, liquidated funds, and replacements.

This keeps the candidate pool current without adding churn to every weekly run.

### Quarterly Thesis Research

Scope:

- Theme-level research for sectors such as healthcare, semiconductor, consumer, new energy, finance, gold, US equity, and HK tech.
- Long-term logic, policy direction, earnings cycle, valuation context, and falsification conditions.
- Constituent-level evidence: top-N holdings of each `lookthrough_target`, their latest filings, broker coverage, and recent news.

The research stack is defined in `2026-05-15-research-adapter-signatures.md`. Two layers cooperate:

1. **Search adapters** (`src/irc/research/search/`) — pluggable web search per locale (Tavily / Brave for English, Bocha for Mainland Chinese), plus Jina Reader for URL → markdown. Output is normalized `SearchHit` dataclasses.
2. **Fundamentals snapshot** (`src/irc/fundamentals/`) — structured fetchers for index constituents (AkShare), CN filings (CNINFO via AkShare), US filings (SEC EDGAR), HK filings (HKEX), and broker reports. Output is a cached `ConstituentSnapshot` per `lookthrough_target` per quarter.

Synthesis is one bounded LLM call (`synthesize_report`) over (search hits + extracted pages + constituent snapshot). Target wall-clock per theme: ≤30 s. Theme research updates thesis evidence and the constituent-snapshot cache; it does not trigger daily actions.

### Event-Triggered Review

Triggers:

- Policy shocks.
- Industry crash or abnormal rally.
- Fund manager change.
- Style drift.
- Large premium or discount.
- Extreme drawdown.
- Thesis-relevant news.

Event reviews should target the affected theme or instrument only.

## Opportunity Identification

The system should identify opportunity funds by looking through the product to the underlying exposure. It should not start from recent fund-profit rankings.

Each candidate gets a `lookthrough_target`:

- Broad index funds: `沪深300`, `中证500`, `中证1000`, `中证A500`, `科创50`, `创业板`, `红利`, and similar.
- Sector or theme funds: healthcare, semiconductor, consumer, new energy, defense, finance, metals, real estate, SOE, tech, and dividend.
- QDII funds: Nasdaq 100, S&P 500, US equity, Hang Seng Tech, Hang Seng, HK dividend, China Internet, and similar.
- Active funds: inferred from main holdings, theme, style, and manager process when available.

Each candidate then receives four state labels.

### Valuation State

`valuation_state` values:

- `cheap`
- `reasonable_low`
- `fair`
- `expensive`
- `very_expensive`
- `evidence_insufficient`

Preferred evidence:

- PE, PB, dividend yield, earnings yield, or index valuation percentile.
- Valuation percentile against the target's own history.
- Relative valuation versus a broad benchmark when self-history is weak.

If reliable valuation data is missing, the system should not infer cheapness from a price drop alone.

### Heat State

`heat_state` values:

- `cold`
- `normal`
- `crowded`
- `overheated`
- `evidence_insufficient`

Preferred evidence:

- 1, 3, 6, and 12 month return rank.
- ETF/fund share or flow changes.
- Premium or discount.
- Trading volume expansion.
- News and research attention.

Recent strong returns should usually increase heat risk, not opportunity score.

### Thesis State

`thesis_state` values:

- `intact`
- `under_pressure`
- `falsified`
- `evidence_insufficient`

Preferred evidence:

- Long-term demand drivers.
- Policy direction.
- Earnings trend.
- Competitive structure.
- Index constituent quality.
- Fund holdings and exposure consistency.

Cheapness is not enough. A low-valuation theme with broken long-term logic should be excluded or sent to `exit_review`.

### Product Quality State

`product_quality_state` values:

- `strong`
- `acceptable`
- `weak`
- `poor`
- `evidence_insufficient`

Preferred evidence:

- Expense ratio.
- AUM and AUM stability.
- Liquidity or purchase channel availability.
- Tracking error for passive funds.
- Premium or discount behavior for ETFs.
- Manager tenure and style stability for active funds.
- Holdings concentration and style drift where available.

## Constituent Fundamentals

The four state labels above need evidence below the fund wrapper. A semiconductor ETF thesis is really a thesis on its top-10 constituents and the industry cycle they are in. Without constituent-level data, `thesis_state` collapses into free-text LLM prose, which is exactly what this design tries to avoid.

For each `lookthrough_target`, the system materializes a `ConstituentSnapshot` (see `2026-05-15-research-adapter-signatures.md`) containing:

- Top-N constituents (default N=10) with name, symbol, weight, market.
- Latest periodic-filing digest per constituent (revenue YoY, net income YoY, gross margin, short guidance excerpt, source URL). 年报 / 季报 for CN, 10-K / 10-Q for US, interim / annual for HK.
- Recent broker reports per constituent (rating, target price, broker, publish date) over a 90-day window for CN; analyst coverage from FMP / EDGAR-linked sources for US.

Sources:

- CN equities: AkShare endpoints — `stock_research_report_em` (broker reports), `stock_financial_abstract`, `stock_zh_a_disclosure_relation_cninfo`, `fund_portfolio_hold_em`, `index_stock_cons_weight_csindex`.
- US equities: SEC EDGAR JSON (`https://data.sec.gov/submissions/CIK*.json`), plus OpenBB FMP for analyst coverage when `OPENBB_FMP_KEY` is set.
- HK equities: HKEX disclosure feed.

Cache layout: `data/fundamentals/<quarter>/<lookthrough_target>.json`. The cache is refreshed quarterly (aligned with earnings season). Weekly runs read the cached snapshot and only re-fetch the news delta via search adapters.

`thesis_state` is then derived from snapshot facts plus the latest theme search results, not from free-text reasoning alone. Example concrete rules (final thresholds tuned during implementation):

- `intact`: ≥60 percent of top-N constituents show positive revenue YoY in the latest filing AND consensus broker rating leans buy/overweight AND no policy news in the last 30 days flagged as negative.
- `under_pressure`: ≥30 percent of top-N constituents show negative revenue YoY OR consensus broker target prices have been cut ≥10 percent in the last 90 days.
- `falsified`: structural impairment (top constituents in earnings decline ≥2 consecutive quarters, regulatory action, or index methodology change that removes the theme's economic exposure).
- `evidence_insufficient`: snapshot is missing or older than one quarter AND search adapters returned no usable hits.

Constituent fundamentals are inputs to opportunity state. They are **not** rendered verbatim in `opportunity_report.json` or `discipline_report.md` — only the derived state and the `thesis_evidence` citations are.

## Opportunity State

The four state labels produce `opportunity_state`:

- `core_dca`: valuation is cheap or reasonable-low, heat is not crowded, thesis is intact, and product quality is acceptable or strong.
- `small_watch`: valuation is attractive but thesis, data, or product evidence has gaps.
- `pause_wait`: thesis may still be intact, but valuation is not attractive, heat is crowded, trend risk is high, or signals conflict.
- `exclude`: thesis is falsified, product quality is poor, venue is impossible, or evidence is too weak for decision-grade analysis.

The first implementation should be conservative. It is acceptable for many rows to become `small_watch`, `pause_wait`, or `exclude`.

## Same-Theme Fund Selection

Funds with the same theme should not be selected by recent return.

### Same Index Or Near Clone

For same-index ETFs or highly overlapping products, keep:

- 1 primary candidate.
- 1 backup candidate when useful.

Ranking criteria:

- Lower expense ratio.
- Higher and more stable AUM.
- Better liquidity or purchase availability.
- Lower tracking error.
- Lower premium or discount risk.
- Longer history.
- Cleaner data completeness.

### Same Theme, Different Index

Do not immediately collapse all same-theme funds. For example, broad healthcare, innovative drugs, and medical devices may represent different exposures.

Keep up to 2 representative lookthrough targets per theme when they reflect materially different theses. Selection should consider:

- Index methodology.
- Constituent quality.
- Concentration.
- Alignment with the current theme thesis.
- Valuation and heat state.

### Active Funds

Active funds are supplementary. A same-theme active fund should only beat passive alternatives when:

- Manager tenure and process are stable.
- Style drift is low.
- Holdings quality is clearly better.
- Drawdown discipline is acceptable.
- Fees are justified by persistent quality evidence.

Otherwise, keep it as `small_watch` or exclude it from the main DCA list.

## Thesis Cards

Each candidate that survives opportunity filtering, and each current holding, gets a structured `thesis_card`.

Fields:

```yaml
instrument_id: "512760"
name_cn: "国泰CES半导体芯片行业ETF"
asset_class: "cn_etf"
theme: "semiconductor"
role: "satellite_cn_semiconductor"
lookthrough_target: "半导体指数"
entry_reason: "底层行业仍有国产替代和周期复苏逻辑，但短期交易热度偏高，暂不追高。"
valuation_state: "reasonable_low"
heat_state: "crowded"
thesis_state: "intact"
product_quality_state: "acceptable"
opportunity_state: "pause_wait"
dca_action: "pause_dca"
risk_action: "review_required"
falsification_triggers:
  - "theme thesis moves to falsified"
  - "product quality moves to poor"
trim_triggers:
  - "valuation_state in [expensive, very_expensive]"
  - "heat_state in [crowded, overheated]"
  - "portfolio weight exceeds target band high"
do_not_sell_just_because:
  - "drawdown_since_entry >= 0.20"
review_cadence: "weekly_light_monthly_full"
evidence_gaps: []
thesis_evidence:
  - type: "filing"         # filing | broker | news | policy | snapshot
    source: "巨潮资讯"
    url: "http://www.cninfo.com.cn/..."
    date: "2026-04-28"
    summary: "中芯国际 2026Q1 营收同比 +18%，毛利率回升至 22%。"
  - type: "broker"
    source: "中信证券"
    url: "https://eastmoney.com/research/..."
    date: "2026-05-02"
    summary: "维持买入评级，目标价上调 12%。"
```

`thesis_evidence` is required for `thesis_state` to be anything other than `evidence_insufficient`. Each entry points to a primary source captured during quarterly research and refreshed weekly via the news delta.

The card is the durable record of why the instrument is held, watched, paused, trimmed, or exited.

## Sell And Trim Discipline

The system should separate selling from trimming.

### Thesis Falsification Exit

Exit review is appropriate when:

- Long-term demand is structurally impaired.
- Policy direction permanently damages the thesis.
- Earnings quality or index constituent quality deteriorates materially.
- An active fund has severe style drift or manager/process damage.
- Product quality becomes poor.

### Valuation And Heat Trim

Trim review is appropriate when:

- Valuation is expensive or very expensive.
- Heat is crowded or overheated.
- The position is above the target band.
- The instrument has contributed enough to make the portfolio too concentrated.

This is profit discipline, not a top prediction.

### Portfolio Rebalance Trim

Trim review is also appropriate when a position is overweight versus target allocation even if the thesis remains intact.

### Risk Protection Review

Trend break, abnormal volatility, or large drawdown should first trigger:

- `pause_dca`
- `review_required`

They should not directly trigger sell. A sell or exit review requires thesis, product, or portfolio evidence.

## DCA And Risk Actions

The short-term layer does not do independent 1 to 3 month rotation trades. It only adjusts DCA rhythm and risk review state.

`dca_action` values:

- `accelerate_dca`
- `normal_dca`
- `slow_dca`
- `pause_dca`
- `do_not_buy`

`risk_action` values:

- `none`
- `review_required`
- `trim_review`
- `exit_review`

Rules:

- Cheap or reasonable-low, cold or normal heat, intact thesis, acceptable product: `normal_dca` or `accelerate_dca`.
- Cheap but under-pressure thesis: `pause_dca` and `review_required`.
- Expensive and crowded: `pause_dca`.
- Expensive, crowded, and overweight: `trim_review`.
- Falsified thesis or poor product quality: `exit_review`.
- Drawdown alone: `review_required`, never automatic sell.

## Pipeline Placement

Current pipeline:

```text
ingest -> discover -> score -> gold -> allocate -> plan -> memo -> decision
```

Target pipeline:

```text
ingest -> discover -> score -> opportunity -> allocate -> plan
-> discipline -> memo -> decision
```

The first implementation can run `opportunity` and `discipline` as sidecar reports after scoring without changing allocation behavior. After the rules are stable, allocation can consume `opportunity_state` to avoid selecting paused or excluded instruments.

The opportunity layer should remain pure as far as possible. I/O belongs in command wrappers.

Recommended module boundaries:

- `src/irc/opportunity/lookthrough.py`: map an instrument to underlying exposure.
- `src/irc/opportunity/states.py`: classify valuation, heat, thesis, and product quality states (consumes `ConstituentSnapshot` and `ThemeReport`).
- `src/irc/opportunity/selection.py`: same-theme and same-index reduction.
- `src/irc/opportunity/cards.py`: build thesis card dictionaries (populates `thesis_evidence`).
- `src/irc/opportunity/discipline.py`: derive DCA and risk actions.
- `src/irc/opportunity/report.py`: compose JSON/YAML/Markdown payloads.
- `src/irc/commands/opportunity_cmd.py`: read current artifacts and write opportunity outputs.
- `src/irc/research/search/` and `src/irc/research/synthesize.py`: search adapters and LLM synthesis (see `2026-05-15-research-adapter-signatures.md`).
- `src/irc/fundamentals/`: constituent-level fetchers and snapshot cache.

## Configuration And Setup

The research stack is keyed by environment variables loaded by `irc.settings.Settings` (pydantic-settings, `.env` file). The user needs to obtain three search API keys plus an optional Jina key.

### Required (at least one English + one Chinese provider)

- `TAVILY_API_KEY` — English search. Sign up at https://app.tavily.com/, free tier 1000 calls/month. Used for US / HK QDII themes, global macro, Fed / SEC primary sources.
- `BOCHA_API_KEY` — Mainland Chinese search via 博查 AI. Sign up at https://open.bochaai.com/, pay-as-you-go. Used for any theme with Locale.ZH (semiconductor, healthcare, consumer, etc.). Covers eastmoney, xueqiu, cls, wallstreetcn, gov.cn.

### Recommended

- `BRAVE_API_KEY` — English news with an independent index. Sign up at https://api.search.brave.com/, free tier 2000 calls/month. Use alongside Tavily for breaking news and freshness filtering.
- `JINA_API_KEY` — URL → markdown extraction. Free tier at https://jina.ai/reader/ works without a key but is rate-limited; paid tier raises throughput. Required as an effective complement to any search provider that returns only snippets.

### Optional fundamentals upgrades

- `OPENBB_FMP_KEY` — already declared; enables US analyst coverage for `fundamentals/edgar_client.py`.
- SEC EDGAR and HKEX are free and require no key, but EDGAR requires a `User-Agent` header with contact email per their API terms — captured in code, not configuration.

### Removed

LDR is removed entirely. The following env vars in `.env` and `.env.example` are deleted: `LDR_ENABLED`, `LDR_BASE_URL`, `LDR_USERNAME`, `LDR_PASSWORD`, `LDR_TIMEOUT_S`, `LDR_SEARCH_TOOL`. The matching fields are removed from `Settings`. The `local-deep-research` install step in README is removed.

### First-run checklist

1. Copy `.env.example` to `.env`.
2. Set `TAVILY_API_KEY` and `BOCHA_API_KEY` (minimum viable).
3. Optionally set `BRAVE_API_KEY` and `JINA_API_KEY` for better coverage.
4. Run `uv run irc research --theme us_monetary` to smoke-test the English path.
5. Run `uv run irc research --theme cn_equity_property_policy` to smoke-test the Chinese path.
6. Each successful run writes a citations-bearing markdown report under `data/research/<theme>.md`.

### Failure behavior

- Missing `TAVILY_API_KEY` and `BRAVE_API_KEY`: EN themes produce `failure_reason="no EN search provider configured"`. ZH themes still run.
- Missing `BOCHA_API_KEY`: ZH themes produce `failure_reason="no ZH search provider configured"`. EN themes still run.
- Missing `JINA_API_KEY`: synthesis runs on search snippets only; report quality is lower but the pipeline does not crash.
- Any provider returning HTTP 5xx or timing out is recorded in `failure_reason`; the affected theme degrades thesis evidence rather than halting the pipeline.

## Outputs

### `opportunity_report.json`

Machine-readable opportunity analysis:

```json
{
  "date": "2026-05-14",
  "summary": {
    "core_dca_count": 0,
    "small_watch_count": 0,
    "pause_wait_count": 0,
    "exclude_count": 0
  },
  "rows": []
}
```

Each row should include:

- `instrument_id`
- `name_cn`
- `asset_class`
- `theme`
- `lookthrough_target`
- `valuation_state`
- `heat_state`
- `thesis_state`
- `product_quality_state`
- `opportunity_state`
- `opportunity_reason`
- `evidence_gaps`

### `thesis_cards.yaml`

Structured thesis cards for holdings, opportunity candidates, and watchlist candidates.

### `discipline_report.md`

Human-readable Chinese report:

- What can be DCA'd today.
- What should be slowed or paused.
- What needs review.
- What enters trim review.
- What enters exit review.
- Why drawdown alone did not produce an automatic sell.

## Decision Integration

The existing `decision` module currently supports conservative buy blocking and mostly emits `no_trade`.

After opportunity and discipline outputs exist, decision can be extended to consume discipline states:

- `add`
- `hold`
- `pause_dca`
- `trim_review`
- `exit_review`
- `no_trade`

This should be a later implementation step. The first opportunity implementation can write its own report without changing decision behavior.

## Error Handling

- Missing valuation evidence produces `valuation_state: evidence_insufficient` with typed gap `missing_valuation_data`.
- Missing heat evidence produces `heat_state: evidence_insufficient` with typed gap `missing_flow_or_return_data`.
- Missing thesis evidence produces `thesis_state: evidence_insufficient` with typed gap from {`missing_constituent_snapshot`, `missing_recent_news`, `missing_broker_coverage`, `missing_policy_data`}.
- Missing product data produces `product_quality_state: evidence_insufficient` with typed gap `missing_product_metadata`.
- `evidence_gaps` is a list of these typed labels and is rendered in `opportunity_report.json`, `thesis_cards.yaml`, and `discipline_report.md`. Gaps demote actions; they are never hidden.
- Invalid or missing generated universe must not block current holdings analysis.
- Search provider failure (any of Tavily / Brave / Bocha) degrades thesis evidence to `evidence_insufficient` for the affected theme; it never fabricates a state and never halts the pipeline.
- Jina Reader failure produces synthesis on search snippets alone; the pipeline does not halt.
- LLM synthesis failure produces `failure_reason` on the report; opportunity composition continues using whatever structured evidence is available.
- Venue incompatibility prevents executable actions but still allows watchlist tracking.

## Performance Contract

The opportunity layer must be bounded by candidate counts and wall-clock per stage.

- Universe generation can inspect the broad catalog, but it runs monthly or on demand.
- Weekly analysis operates on the merged configured universe after deterministic caps.
- LLM calls are theme-level or shortlisted-instrument-level, not full-universe-level.
- Same-theme reduction happens before LLM reasoning whenever possible.
- Daily light checks operate only on holdings, thesis cards, and existing watchlist.

Wall-clock targets (full-pipeline weekly run, ≈20 themes):

- Per-theme search + extract + synthesize: ≤30 s.
- Total weekly research stage: ≤5 minutes.
- Daily light check (no theme research): ≤30 s end-to-end.
- Constituent fundamentals snapshot rebuild (quarterly): ≤15 minutes for full universe.

The design target is stable, explainable output rather than maximal coverage.

## Testing Strategy

Use TDD. Pure functions should be tested before CLI wiring.

Required unit tests:

1. Lookthrough mapping maps broad, sector, QDII, bond, gold, and active fund rows to expected targets.
2. Cheap valuation plus cold heat plus intact thesis plus acceptable product produces `core_dca`.
3. Cheap valuation plus falsified thesis produces `exclude`.
4. Drawdown of 20% does not produce sell or exit by itself.
5. Expensive plus crowded plus overweight produces `trim_review`.
6. Same-index ETF selection keeps one primary and one backup.
7. Same-theme different-index selection can keep two representatives when targets differ.
8. Active funds are demoted when style stability or manager evidence is missing.
9. Missing data produces explicit typed `evidence_gaps`.
10. Search-provider failure (Tavily / Brave / Bocha) degrades thesis evidence without crashing pure opportunity composition.
11. `TavilyProvider`, `BraveNewsProvider`, `BochaProvider`, `JinaReader` each: happy path, HTTP 5xx, timeout, malformed response (all mocked via httpx).
12. `multi_provider_search` dedupes by URL and respects `include_domains`.
13. `synthesize_report` produces non-empty `report_md` with citation indices matching `pages`.
14. `build_snapshot` records per-symbol failures in `failure_reasons` rather than raising.
15. `thesis_evidence` is populated when `ConstituentSnapshot` is present and empty (with appropriate gap) when absent.

Required integration tests:

1. Mock scoring, allocation, metrics, and universe inputs produce `opportunity_report.json`.
2. The same mock inputs produce `thesis_cards.yaml`.
3. The Markdown report starts with Chinese actionable sections for DCA, pause, review, trim, and exit.
4. Existing decision command still works when opportunity outputs are absent.
5. Theme research path runs end-to-end with mocked search + extractor + LLM and produces `data/research/<theme>.md` with citations.

## README Follow-Up

After implementation, README should get a short user-facing section:

- Where candidates come from.
- How often to run `universe build-cn-funds`.
- Difference between daily light check, weekly full analysis, monthly universe rebuild, and quarterly thesis research.
- Why the system does not scan every fund deeply every run.
- How to interpret DCA, pause, review, trim, and exit actions.

The full methodology should remain in this spec. README should stay operational and concise.

## Acceptance Criteria

- The spec-backed implementation never uses the external worktree generated universe path at runtime.
- Opportunity states are deterministic from explicit inputs.
- Same-theme and same-index candidates are reduced before deep research.
- The system can explain why a hot profitable fund is paused instead of chased.
- The system can explain why a 20% drawdown is a review trigger rather than an automatic sell.
- The output distinguishes DCA, pause, review, trim, and exit review.
- Typed evidence gaps are visible in JSON, YAML, and Markdown.
- Active funds remain supplementary unless stronger product-quality evidence exists.
- LDR is fully removed: `src/irc/research/ldr_client.py` and its tests are deleted, `Settings` no longer has `ldr_*` fields, and `.env.example` no longer documents `LDR_*` variables.
- Search adapters for Tavily, Brave, Bocha, and Jina Reader are present and individually unit-tested with mocked HTTP.
- Weekly research stage completes in ≤5 minutes against a ≈20-theme universe.
- Quarterly fundamentals snapshot is cached on disk under `data/fundamentals/<quarter>/` and reused by weekly runs.
- Each `thesis_card` with `thesis_state != evidence_insufficient` carries at least one `thesis_evidence` entry pointing to a primary source with a date.

## Implementation Plan Scope

The next implementation plan should cover the first usable loop:

1. Search adapter layer per `2026-05-15-research-adapter-signatures.md` — Tavily, Brave, Bocha, Jina Reader, dispatch, synthesize. Rewrite `theme_research.py`. Delete `ldr_client.py` and its tests.
2. Settings + `.env.example` update — add `TAVILY_API_KEY`, `BRAVE_API_KEY`, `BOCHA_API_KEY`, `JINA_API_KEY`; remove all `LDR_*`.
3. Fundamentals layer per the same signatures doc — AkShare CN fetchers, EDGAR client, HKEX client, snapshot cache.
4. Pure lookthrough mapping.
5. Pure state classification from available metrics + `ConstituentSnapshot` + `ThemeReport`.
6. Same-theme selection.
7. Thesis card generation including `thesis_evidence`.
8. Discipline action generation.
9. CLI command writing the three output files.
10. Tests for the rules above (see Testing Strategy).

Do not implement multi-agent debate, Kronos features, or full portfolio sell sizing in the first plan. Those are later enhancements after the deterministic discipline layer is stable.
