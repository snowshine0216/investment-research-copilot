# CN Fund Universe Discovery Design

## Problem

`irc discover` currently produces an ETF-only watchlist because the candidate universe is effectively a hand-curated ETF seed list. The live `config/universe/cn_funds.yaml` contains 59 instruments, 55 of which have `ETF` in the Chinese name. The discovery funnel then applies hard filters, quality filters, and role bucketing to that narrow seed list, so the final `discovered_watchlist.csv` cannot represent the thousands of public funds available in China.

This is not primarily an LLM-selection problem. The LLM only writes reasons for candidates that already survived discovery. The root issue is candidate generation.

## Goal

Build a CN fund universe generation path that starts from Akshare's broad China mutual-fund catalog, classifies fund candidates into the existing instrument model, narrows them through deterministic prefilters, and feeds a role-diverse candidate set into the existing ingest and discovery pipeline.

The watchlist should include real `cn_equity_fund` candidates, not only ETFs, when suitable active funds pass the configured filters.

## Non-Goals

- Do not score every Chinese public fund with an LLM.
- Do not replace the existing `ingest -> discover -> score -> allocate -> plan -> memo` pipeline.
- Do not overwrite hand-curated universe files without an explicit command or flag.
- Do not build a new portfolio allocator in this change.
- Do not scrape authenticated broker holdings or account data.

## Current System

Discovery currently flows through these units:

- `config/universe/*.yaml` defines static instruments.
- `src/irc/discovery/universe.py` combines universe files and deduplicates by `instrument_id`.
- `src/irc/commands/ingest_cmd.py` fetches metadata, prices, NAV history, and stores them in DuckDB.
- `src/irc/discovery/hard_filter.py` applies inception, AUM, fee, volume, and ban-list filters.
- `src/irc/discovery/quality_filter.py` applies drawdown, tracking-error, and manager-tenure filters.
- `src/irc/discovery/role_bucket.py` maps surviving instruments into roles such as `core_cn_equity`, `satellite_cn_growth`, `satellite_cn_healthcare`, and `defensive_cn_bond`.
- `src/irc/discovery/pipeline.py` writes reasons and returns the watchlist dataframe.

The existing role bucket already supports active funds:

- `cn_equity_fund` with no theme falls into `satellite_cn_growth`.
- `cn_equity_fund` with sector themes falls into sector buckets.
- `cn_equity_fund` with broad index metadata can fall into `core_cn_equity`.

The missing piece is a real candidate-universe builder.

## Proposed Design

Add a generated CN fund universe layer beside the hand-curated config layer.

The system should keep these two ideas separate:

1. **Curated universe**: hand-edited YAML for high-conviction instruments and manual overrides.
2. **Generated universe**: reproducible YAML built from Akshare catalog data and deterministic classification rules.

Discovery should enumerate both layers and deduplicate by `instrument_id`, with curated entries winning when the same instrument exists in both files.

## File Responsibilities

### `src/irc/data/akshare_client.py`

Expose a catalog function that wraps Akshare's open-fund table and normalizes column names to a stable internal shape:

- `fund_code`
- `fund_name`
- `fund_type`

The wrapper should remain a thin data-source boundary. It should not classify funds or apply investment rules.

### `src/irc/discovery/cn_fund_universe.py`

Create pure functions for classification and deterministic candidate shaping:

- Normalize raw catalog rows.
- Exclude unusable fund classes.
- Infer `asset_class`.
- Infer `theme` from fund name and fund type.
- Infer `market` and `venue_required`.
- Deduplicate share classes.
- Cap generated candidates per asset class and theme.
- Return `Instrument` objects or serializable dictionaries compatible with `UniverseConfig`.

This module should not call Akshare, DuckDB, the filesystem, or the LLM.

### `src/irc/commands/universe_cmd.py`

Add a CLI command for generated universe files:

```text
irc universe build-cn-funds --repo-root .
```

The command should:

- Fetch the raw Akshare fund catalog through `akshare_client`.
- Classify and cap candidates through `cn_fund_universe.py`.
- Write `config/universe/cn_funds.generated.yaml` atomically.
- Print counts by `asset_class` and `theme`.

The generated file should be deterministic: same input rows and options produce the same YAML ordering and contents.

### `src/irc/config_loader.py`

Load the optional generated universe file when it exists. The loader should continue to work when the file is absent, so existing repos remain valid.

The merged CN universe should be ordered as:

1. Hand-curated `config/universe/cn_funds.yaml`
2. Generated `config/universe/cn_funds.generated.yaml`

When the same `instrument_id` appears in both, the hand-curated row wins.

### `src/irc/discovery/diagnostics.py`

Add a small diagnostics model for funnel counts and rejection reasons.

Diagnostics should capture:

- Universe count by `asset_class` and `theme`.
- Hard-filter pass and rejection counts.
- Quality-filter pass and rejection counts.
- Role bucket counts.
- Failed and relaxed roles.

### `src/irc/commands/discover_cmd.py`

Write diagnostics next to the watchlist:

```text
outputs/<date>/discovery_diagnostics.csv
```

This file should make ETF-only outputs easy to explain without rerunning custom Python snippets.

## Classification Rules

Classification must be deterministic and easy to audit.

### Exclude

Exclude catalog rows that are poor fits for this investment-research pipeline:

- Money market funds.
- Short-duration cash-management funds.
- Pure FOF products.
- C share classes when an A share exists for the same normalized fund name.
- Duplicate share classes where another preferred share class already exists.
- Funds with names indicating liquidation, termination, or abnormal status.

### Asset Class

Map catalog rows into the existing asset classes:

- `cn_equity_fund`: active equity funds and active mixed-equity funds.
- `cn_bond_fund`: bond funds intended for defensive allocation.
- `cn_etf`: exchange-traded domestic ETF products.
- `us_etf` / `hk_etf`: QDII funds whose names clearly indicate US or HK market exposure.

The classifier should not call every index fund an ETF. ETF classification should require name/type evidence such as `ETF`, `交易型开放式`, or an exchange-traded market marker.

### Theme

Infer themes from fund names and fund types using a keyword table that maps into existing `Theme` literals:

- `broad`: 沪深300, 中证500, 中证1000, 上证50, A500, 创业板, 科创50, 宽基.
- `dividend`: 红利, 股息, 低波.
- `tech`: 科技, 信息技术, 互联网, 软件, 通信, AI, 人工智能.
- `semiconductor`: 半导体, 芯片, 集成电路.
- `defense`: 军工, 国防, 航天.
- `healthcare`: 医疗, 医药, 创新药, 中药, 生物.
- `new_energy`: 新能源, 光伏, 电池, 储能, 电动车.
- `consumer`: 消费, 食品饮料, 酒, 家电.
- `finance`: 银行, 券商, 证券, 金融.
- `metals`: 有色, 金属, 化工, 资源.
- `real_estate`: 地产, 房地产.
- `soe`: 央企, 国企, 国资.

If no theme matches and the fund is an active equity fund, keep `theme: null` so it can route to `satellite_cn_growth`.

## Prefilter Strategy

The generated universe must not dump thousands of raw rows into ingest. It should create a bounded, explainable candidate set.

Use deterministic catalog-stage prefilters before expensive metadata and NAV calls:

- Keep a configurable maximum per theme and asset class.
- Prefer A shares over C shares.
- Prefer names without `联接` unless the linked ETF is unavailable.
- Prefer funds whose names map cleanly into a supported role.
- Keep broad active funds even without a theme, up to a separate cap.

Initial caps:

- Broad active `cn_equity_fund`: 40.
- Each sector/factor theme: 20.
- CN bond funds: 40.
- CN ETFs: 80.
- US/HK QDII: 40 each.

These caps keep ingest tractable while allowing much wider coverage than the current hand-written file.

## Filter Calibration

The current filters should become less ETF-centric.

### Fees

Use thresholds that distinguish direct ETFs from China fund products:

- Direct low-cost ETF products can keep tight fee thresholds.
- QDII feeder funds need a higher fee ceiling than `0.003`.
- Active `cn_equity_fund` should use the existing active fee ceiling or a clearly named active-fund threshold.

### Drawdown

One global drawdown cap is too blunt. Discovery should support class-aware or role-aware drawdown limits:

- Gold can tolerate drawdowns slightly above the current 24% cap.
- Growth and sector themes need a wider cap than defensive/core assets.
- Defensive bond funds should keep a tighter cap.

### Tenure

Manager tenure should apply only to active funds. It should not remove on-exchange bond ETFs or passive funds.

## Data Flow

```text
Akshare fund catalog
  -> akshare_client catalog wrapper
  -> cn_fund_universe pure classifier
  -> config/universe/cn_funds.generated.yaml
  -> config_loader merges curated + generated universe
  -> ingest fetches metadata, prices, NAV
  -> discover hard filter
  -> discover quality filter
  -> role bucket
  -> discovered_watchlist.csv + discovery_diagnostics.csv
```

## Error Handling

- If Akshare catalog fetch fails, `irc universe build-cn-funds` should exit non-zero and leave the previous generated file untouched.
- If individual fund metadata or NAV fetch fails during ingest, existing skip-and-warn behavior remains acceptable.
- If generated YAML validation fails, the command should not write the file.
- If no generated file exists, discovery should behave exactly as it does today.
- If the generated file exists but is empty, discovery should still run using the curated universe.

## Testing Strategy

Use TDD for every behavior change.

Unit tests:

- `tests/discovery/test_cn_fund_universe.py` for pure classification, theme inference, exclusion rules, share-class dedupe, and caps.
- `tests/data/test_akshare_client.py` for catalog wrapper column normalization.
- `tests/test_config_loader.py` for optional generated universe loading and curated-wins dedupe.
- `tests/discovery/test_diagnostics.py` for funnel count and rejection aggregation.

Command tests:

- `tests/commands/test_universe_cmd.py` for generated YAML writing, atomic no-overwrite-on-failure behavior, and printed counts.
- `tests/commands/test_discover_cmd.py` for `discovery_diagnostics.csv` creation.

End-to-end smoke:

- A mocked catalog containing ETFs, active equity funds, bond funds, QDII funds, C shares, and excluded money-market funds should produce a watchlist with at least one `cn_equity_fund` after `ingest -> discover`.

## Rollout

1. Add pure classifier and tests.
2. Add Akshare catalog wrapper and tests.
3. Add `irc universe build-cn-funds` and generated YAML output.
4. Add optional generated universe loading.
5. Add diagnostics output.
6. Calibrate discovery filter config.
7. Run unit tests and mocked e2e tests.
8. Run live `irc universe build-cn-funds`, then `irc ingest`, then `irc discover`.

## Success Criteria

- `irc universe build-cn-funds` creates a valid `config/universe/cn_funds.generated.yaml` from a mocked Akshare catalog.
- The generated universe contains non-ETF active funds classified as `cn_equity_fund`.
- `irc discover` reads both curated and generated universe files.
- `discovered_watchlist.csv` can include `cn_equity_fund` rows when active funds pass metadata and quality filters.
- `discovery_diagnostics.csv` explains why each asset class and role did or did not appear.
- Existing repos without a generated universe file continue to pass tests.

## Design Risks

- Akshare fund catalog and metadata endpoints can be slow or unstable. The generated file gives us a cache boundary and avoids rebuilding the catalog on every pipeline run.
- Name-based theme inference will be imperfect. The generated YAML remains auditable and can be overridden by curated entries.
- Active fund manager tenure is still approximate when the upstream source lacks exact tenure. Existing fallback behavior should remain visible in diagnostics or logs.
- Broadening drawdown thresholds may admit volatile sector funds. Role-aware filtering and downstream scoring should keep this explicit rather than hiding it.

## Approval State

This spec captures the chosen direction: build a generated CN fund universe before writing the implementation plan. Implementation should not start until this spec is reviewed and approved.