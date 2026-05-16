# Investment Research Copilot

Weekly research-and-recommendation system for gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy).

> **Status:** Plans 1–6 complete. Default pipeline operational: data ingest → discovery → scoring → gold analysis → allocation → trade planning → LLM memo synthesis → interactive queries. Run `irc run` to execute the 7 default stages. Web-search research (Tavily/Brave/Bocha/Jina) runs between ingest and discovery when `RESEARCH_ENABLED=true`. CN fund universe now covers broad/sector/dividend/bond categories with role-aware allocation. Opportunity layer adds valuation/heat/thesis/product-quality states, thesis cards, and DCA discipline actions.

## Design references

- MVP design: [docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md](docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md)
- Opportunity + thesis discipline: [docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md](docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md)

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd investment-research-copilot
uv sync --all-extras
cp .env.example .env
# Edit .env to fill DEEPSEEK_API_KEY and OPENROUTER_API_KEY.
# Optional: set DEBUG=true in .env for verbose logging (full tracebacks, third-party DEBUG records).
# Default DEBUG=false still shows progress bars and categorized ingest-error summaries.
```

### Web research setup

Research uses provider API keys from `.env`:

- `TAVILY_API_KEY` or `BRAVE_API_KEY` for English themes.
- `BOCHA_API_KEY` for Mainland-China themes.
- `JINA_API_KEY` is optional; without it, Jina Reader uses the rate-limited free tier.

Set `RESEARCH_ENABLED=true` only when you want `irc run` to include the research stage.

### Common workflows

```bash
uv run irc init                        # writes inputs/ + config/ defaults
uv run irc config validate             # validates all 14 YAML files

# Build the CN fund universe from Akshare (optional, updates config/universe/cn_funds.generated.yaml):
uv run irc universe build-cn-funds     # ~359 funds across equity/bond/ETF categories
uv run irc config validate             # confirm generated file is accepted (universe grows to ~418)

# Run the default pipeline in one command. This does not rebuild fundamentals snapshots
# and does not run the opportunity layer.
uv run irc run                         # ingest → discover → score → gold → allocate → plan → memo

# Include optional web research between ingest and discovery:
RESEARCH_ENABLED=true uv run irc run    # ingest → research → discover → score → gold → allocate → plan → memo

# Full weekly run with all currently-supported opportunity evidence:
uv run irc ingest                       # refresh market/fund data first
uv run irc research                     # macro/news/theme citations → data/research/
uv run irc fundamentals snapshot --target all --top-n 10
                                       # constituent filings + broker reports for all registered snapshot targets
uv run irc run --from discover          # discover → score → gold → allocate → plan → memo
uv run irc opportunity                  # consumes scoring + data/research + data/fundamentals
uv run irc decision                     # optional decision-readiness report

# Or run stages individually:
uv run irc ingest                      # pulls OpenBB + AKShare data into data/local.duckdb
uv run irc research                    # web research → data/research/<theme>.md + research_status.json
uv run irc research --theme us_monetary  # targeted single-theme smoke test
uv run irc fundamentals snapshot --target 沪深300 --top-n 10  # quarterly constituent snapshot rebuild
uv run irc fundamentals snapshot --target all --top-n 10      # rebuild every registered snapshot target

# Inspect research outputs:
ls data/research
jq '.themes[] | {theme, citation_count, failure_reason, provider_failures}' data/research/research_status.json
jq '.themes[] | select(.failure_reason != "")' data/research/research_status.json
ls data/fundamentals/*
jq '{target: .lookthrough_target, filings: (.filings|length), broker_reports: (.broker_reports|length), failures: (.failure_reasons|length)}' data/fundamentals/*/*.json
uv run irc eval research
uv run irc discover                    # 5-step funnel → outputs/<date>/discovered_watchlist.csv
                                       #                  + outputs/<date>/discovery_diagnostics.csv
uv run irc score                       # 5-factor scoring → outputs/<date>/scoring.json
uv run irc gold                        # regime + band + scenarios → gold_regime.json + gold_band.yaml
uv run irc allocate                    # target weights + top-K → proposed_allocation.yaml
uv run irc plan                        # buy method + triggers → trade_plan.yaml
uv run irc memo                        # LLM synthesis → memo.md + memo_audit.txt + memo_traceability.json
uv run irc decision                    # decision-readiness report → decision_report.json + decision_report.md
uv run irc opportunity                 # opportunity/thesis/discipline → opportunity_report.json
                                       #   + thesis_cards.yaml + discipline_report.md
uv run irc ask "Is SGOL overvalued?"   # interactive Q&A grounded in today's outputs
uv run irc freshness                   # data manifest summary

# Resume from a specific stage (skip earlier stages if outputs exist):
uv run irc run --from score
```

## Tests

```bash
uv run pytest                                       # unit + integration (799 tests)
RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_smoke.py
                                                    # verify live API credentials
```

## Layout

- `src/irc/` — Python package; mirror of design spec §5.A.
- `tests/` — mirrors `src/irc/`.
- `inputs/`, `config/` — generated by `irc init`; user-editable.
- `docs/superpowers/specs/` — design spec.
- `docs/superpowers/plans/` — implementation plans (one per milestone).

## Configuration files

After `irc init` you will have:

- `inputs/account.yaml` — your real holdings + venues.
- `inputs/preferences.yaml` — risk band, asset-class targets, currency tolerance, capital plan.
- `config/llm.yaml` — task → (provider, model) routing.
- `config/scoring.yaml`, `config/gold_drivers.yaml`, `config/discovery.yaml`,
  `config/valuation_buckets.yaml`, `config/triggers.yaml` — tunable parameters.
- `config/overrides.yaml`, `config/macro_view.yaml` — your sovereignty layer.
- `config/universe/*.yaml` — candidate pools.

Edit any of these and re-run `irc config validate`.

## Opportunity and discipline layer

### Where candidates come from

Candidates are loaded from `config/universe/cn_funds.yaml` (curated) and `config/universe/cn_funds.generated.yaml` (generated). The curated file wins on conflict. Run `uv run irc universe build-cn-funds` to regenerate the generated file from Akshare — typically once a month.

### Analysis cadence

| Cadence | Scope | Command |
|---|---|---|
| Daily light | Holdings, thesis cards, watchlist only — check drawdown, heat, triggers | `irc opportunity` (fast) |
| Weekly full | Merged configured universe, discovery, scoring, thesis card refresh | `irc run` then `irc opportunity` |
| Monthly universe rebuild | Re-fetch broad fund catalog, regenerate `cn_funds.generated.yaml` | `irc universe build-cn-funds` |
| Quarterly thesis research | Theme search + citations and constituent snapshot refresh | `uv run irc research` plus `uv run irc fundamentals snapshot --target all --top-n 10` |

The system does not scan every fund deeply on every run. Universe generation runs monthly; weekly analysis operates on the already-filtered configured universe after deterministic caps.

### Evidence refresh order

`irc opportunity` reads cached evidence; it does not fetch it live. Refresh inputs in this order when you want decision-grade thesis cards:

1. `uv run irc ingest` — refresh local market/fund data used by discovery and scoring.
2. `uv run irc research` — refresh macro, policy, gold-driver, geopolitics, and holdings-sector citations under `data/research/`.
3. `uv run irc fundamentals snapshot --target all --top-n 10` — refresh constituent filings and broker reports for every registered snapshot target under `data/fundamentals/`.
4. `uv run irc run --from discover` — rebuild discovered watchlist, scores, allocation, trade plan, and memo from the refreshed inputs.
5. `uv run irc opportunity` — generate `opportunity_report.json`, `thesis_cards.yaml`, and `discipline_report.md`.

`--target all` currently expands to the registered broad-CN targets: 沪深300, 中证500, 中证1000, 中证A500, 上证50, 科创50, 创业板, 中证红利, 红利低波. Sector themes and QDII targets still degrade to `missing_constituent_snapshot` until their `_TargetSpec` entries are added.

### How `fundamentals snapshot` data drives `thesis_state`

```
┌──────────────────────────────────────────────────────────────────┐
│  uv run irc fundamentals snapshot --target <X>                   │
│                                                                  │
│  Per target, fetches three lists via AkShare / EDGAR / HKEX:     │
│    • constituents   — top-N holdings (symbol, name, weight)      │
│    • filings        — per holding: revenue_yoy, net_income_yoy,  │
│                       gross_margin, fiscal_period, source_url    │
│    • broker_reports — per holding (CN only): rating, target_pr,  │
│                       broker, published_iso, title               │
│  Writes data/fundamentals/<quarter>/<target>.json (one per call).│
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  uv run irc opportunity                                          │
│                                                                  │
│  For each instrument in scoring.json:                            │
│    1. lookthrough = map_lookthrough(instrument)  →  display_cn   │
│       (e.g. 510050 → "上证50", 006075 → "标普500")               │
│    2. load_latest_cached_snapshot(display_cn, root/"data")       │
│       reads data/fundamentals/<latest-Q>/<display_cn>.json       │
│    3. derive_thesis_from_evidence(snapshot, theme_report):       │
│         pos, neg, total = count of revenue_yoy>0 / <0 / present  │
│         consensus = Σ rating_sentiment(broker_reports)           │
│         classify:                                                │
│           neg/total ≥ 60%                       → falsified      │
│           pos/total ≥ 60% AND neg/total<30%                      │
│              AND consensus ≥ 0                  → intact         │
│           neg/total ≥ 30% OR consensus < 0      → under_pressure │
│           otherwise                             → evidence_insufficient│
│    4. attach top-3 filings + top-2 broker reports as             │
│       `thesis_evidence` on the thesis card.                      │
└──────────────────────────────────────────────────────────────────┘
```

**Real example** (`data/fundamentals/2026Q1/上证50.json`):

- 10 constituents (贵州茅台 9.4%, 中国平安 6.9%, 紫金矿业 6.0%, …)
- 10 filings with revenue_yoy (茅台 +6.3%, 平安 -6.2%, 紫金 +24.8%, 招商银行 +3.8%, 寒武纪 +159.5%, …)
- Result: `pos/total = 80%`, `neg/total = 10%`, consensus ≈ 0 → `thesis_state = intact`. Instruments tracking 上证50 (e.g. `510050 上证50ETF华夏`) inherit this thesis and surface lines like `贵州茅台 2026Q1 营收同比 +6.3%。` on their thesis cards.

**When `thesis_state = evidence_insufficient`**, the cause is one of:

- `lookthrough_target` does not match a `_TargetSpec` in `_TARGET_REGISTRY` (e.g. `标普500`, `纳斯达克100`, `中证央企创新驱动`, sector themes, gold/bond/active funds). The snapshot file does not exist.
- The snapshot file exists but every filing fetch failed (e.g. `data/fundamentals/2026Q1/创业板.json` is 206 bytes — all `failure_reasons`).
- The snapshot loads but `total_with_revenue_yoy == 0` (filings present but all missing the YoY field).

Snapshot collection is **sequential and serial**: one target after another in the outer loop, and within each target one symbol after another. `--target all` with `--top-n 10` for the 9 registered targets is ~90 filing fetches + ~90 broker-report fetches — typically 5–15 minutes wall time and bounded by the slowest upstream. It does **not** run as part of `irc run`; treat it as a quarterly job.

### Opportunity states

- `core_dca` — cheap/reasonable-low valuation, not crowded, thesis intact, acceptable product. DCA normally or accelerate.
- `small_watch` — attractive valuation but gaps in thesis, data, or product evidence. Monitor.
- `pause_wait` — thesis may be intact, but valuation is unattractive, heat is crowded, or signals conflict. Do not add.
- `exclude` — thesis falsified, poor product quality, unavailable venue, or evidence too weak.

### How to read DCA and risk actions

`dca_action`: `accelerate_dca` · `normal_dca` · `slow_dca` · `pause_dca` · `do_not_buy`

`risk_action`: `none` · `review_required` · `trim_review` · `exit_review`

Key rules:
- A 20% drawdown triggers `review_required`, never an automatic sell. Selling requires thesis, product, or portfolio evidence.
- `trim_review` fires when valuation is expensive/crowded or the position is overweight vs. target band.
- `exit_review` fires when the thesis is falsified or product quality becomes poor.

## Conventions

- Functional programming: pure stages, immutable configs, I/O confined to wrappers.
- TDD: every feature begins with a failing test.
- Files < 200 lines; functions < 20 lines.
- Every secret in `.env`; YAML configs only reference env names.
