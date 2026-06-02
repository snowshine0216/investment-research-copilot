# Investment Research Copilot

Weekly research-and-recommendation system for gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy).

> **Status:** Plans 1–6 complete. Default pipeline operational: data ingest → discovery → scoring → gold analysis → allocation → trade planning → opportunity layer → LLM memo synthesis → decision-readiness report. Run `irc run` to execute the 9 default stages (plus optional research). Web-search research (Tavily/Brave/Bocha/Jina) runs between ingest and discovery when `RESEARCH_ENABLED=true`. CN fund universe now covers broad/sector/dividend/bond categories with role-aware allocation. Opportunity layer adds valuation/heat/thesis/product-quality states, thesis cards, and DCA discipline actions. Memo §5 now consolidates the decision-readiness verdict (decision_status) alongside the opportunity overlay so the two views align in a single picks table; inline citations render as `[1]`, `[2]`, … with a numbered appendix mapping back to `[ref:HEXID]` for grep/audit.

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
# Edit .env before the first LLM-backed run. See Environment setup below.
uv run irc init
uv run irc config validate
uv run irc run
```

`irc run` executes the default pipeline: ingest -> discover -> score -> gold -> allocate -> plan -> opportunity -> memo -> decision. It skips web research unless `RESEARCH_ENABLED=true` and does not rebuild fundamentals snapshots (quarterly job — see `irc fundamentals snapshot`).

## Environment setup

Copy `.env.example` to `.env`, keep every secret there, and treat `.env.example` as the complete reference. The table below groups the variables by the workflows that need them.

| Variable | Needed for | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` | Required for default config | Used by research synthesis, scoring rationales, thesis checks, and interactive Q&A. `Settings()` also requires it for full validation. |
| `OPENROUTER_API_KEY` | Required by default memo routes | `config/llm.yaml` routes `memo_synthesis` and `memo_audit` through OpenRouter Anthropic models. Re-route those tasks if you want a DeepSeek-only setup. |
| `RESEARCH_ENABLED` | Optional web research in `irc run` | Leave `false` for faster default runs. Set `true` to insert research between ingest and discovery. |
| `TAVILY_API_KEY` | English web research | Use Tavily or Brave for EN themes. Tavily is the main EN search provider. |
| `BRAVE_API_KEY` | English web/news research | Optional complement to Tavily, useful for news freshness and independent coverage. |
| `BOCHA_API_KEY` | Mainland-China web research | Required for full ZH theme coverage. Missing Bocha makes ZH themes degrade with a recorded failure reason. |
| `JINA_API_KEY` | URL-to-markdown extraction | Optional. Free tier works without a key, but rate limits are lower. |
| `EDGAR_CONTACT_EMAIL` | SEC EDGAR fundamentals | Set a real reachable email before quarterly snapshots that touch US filings. SEC fair-use policy expects this in the User-Agent. |
| `OPENBB_FMP_KEY`, `OPENBB_TIINGO_KEY` | Optional OpenBB premium data | MVP works without these; they improve premium provider coverage when available. |
| `TUSHARE_TOKEN` | Optional CN fundamentals fallback | Enables the Tushare per-method fallback for CN filing digests and broker `target_price` (activates `consensus_upside_pct`). Unset = AkShare-only, byte-identical to before. Get a token at [tushare.pro](https://tushare.pro). |
| `FRED_API_KEY`, `INTRINIO_API_KEY` | Optional FRED macro data | Used when OpenBB pulls live FRED macro series. Without them, the ingest stage falls back where possible. |
| `ACTIVE_FUND_TENURE_PROXY_ENABLED` | Active fund discovery behavior | Defaults to `true`; set `false` to require real manager-tenure data for active funds. |
| `IRC_HTTPS_PROXY` | Outbound HTTPS proxy | Single value applied to every outbound HTTPS call this codebase makes. See "HTTPS proxy" below for the full list of call sites. Leave unset for direct connections. |
| `DEBUG` | Troubleshooting | Set `DEBUG=true` for verbose CLI logging and full tracebacks. Default output still includes progress bars and categorized error summaries. |

Minimum local `.env` for the default config:

```dotenv
DEEPSEEK_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
```

Add these for research-backed runs:

```dotenv
RESEARCH_ENABLED=true
TAVILY_API_KEY=tvly-...
BOCHA_API_KEY=bocha-...
# Optional but recommended for richer extraction/news coverage:
BRAVE_API_KEY=
JINA_API_KEY=
```

Add these before quarterly fundamentals refreshes that include US filings or live macro data:

```dotenv
EDGAR_CONTACT_EMAIL=you@example.com
FRED_API_KEY=
INTRINIO_API_KEY=
OPENBB_FMP_KEY=
```

### Tushare fallback (optional)

IRC's CN fundamentals are primarily sourced from AkShare→EastMoney. Tushare is an
optional **per-method fallback**: when a `TUSHARE_TOKEN` is set, IRC tries AkShare
first and fills only the gaps Tushare can cover — most valuably broker
**target prices**, which EastMoney drops upstream (so `consensus_upside_pct` is
honestly `None` today; see `docs/adr/0009-consensus-upside-degrade-to-none.md`). With no token, behavior is
byte-identical to before — AkShare alone.

How the fallback works (ADR 0010): for each of the three CN-fundamentals surfaces
(filing digest, broker reports, index valuation), AkShare is the primary; on a
miss (`None`/empty) or error, Tushare is tried; if both miss, the result stays
`None`/empty. Tushare calls are NOT metered against the AkShare fetch budget, and
Tushare (`api.tushare.pro`, mainland-CN) is called direct — never through
`IRC_HTTPS_PROXY`.

Setup:

```dotenv
TUSHARE_TOKEN=your-tushare-token
```

```bash
uv add tushare              # already a dependency after item 003; explicit add is a no-op
```

Note: the broker `target_price` feed (Tushare `report_rc`) is gated behind a
points/paid tier. On a free token the fallback still adds CN filing-digest
redundancy and `consensus_upside_pct` simply stays `None`.

Verify the live Tushare shape (triple-gated — skipped in normal runs):

```bash
IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \
    tests/fundamentals/test_tushare_provider_live.py -v -s
```

### HTTPS proxy

Set `IRC_HTTPS_PROXY` (e.g. `http://10.27.7.110:8080`) when running from a network that blocks any of the upstream hosts the pipeline calls. One value, applied uniformly to:

- LLM provider calls — DeepSeek (`api.deepseek.com`) and OpenRouter (`openrouter.ai`), driven by `config/llm.yaml`.
- Web search providers — Tavily (`api.tavily.com`), Brave News (`api.search.brave.com`), and Bocha (`api.bochaai.com`).
- Page extractor — Jina Reader (`r.jina.ai`).
- DXY ingest only — EastMoney via AkShare. Other AkShare calls stay direct because most of them serve mainland-CN domains where a non-CN proxy hurts more than it helps.

Leave the variable unset (or blank) for direct connections everywhere. If a single host on this list is the only one you need to route, point the proxy at a forwarder that you control which can selectively bypass the rest.

## Workflows by cadence

Run these from the repo root.

### First-time setup

```bash
uv run irc init
uv run irc config validate
```

`irc init` writes editable defaults under `inputs/` and `config/`. Re-run `irc config validate` after changing YAML.

### Daily light check

Use this when you want a fast read on current holdings, drawdowns, thesis cards, and decision readiness while reusing the latest deeper research artifacts.

```bash
uv run irc ingest
uv run irc opportunity
uv run irc decision
uv run irc freshness
```

### Weekly default run

Use this for the normal weekly recommendation memo without refreshing web research or fundamentals snapshots.

```bash
uv run irc run
```

`irc run` now bundles opportunity + decision into the default pipeline — the consolidated `memo.md` (with the 决策 column and the `今日唯一行动` banner) and `decision_report.{json,md}` are written in a single invocation.

### Weekly run with research

Use this when you want fresh macro/news/theme citations included before discovery and scoring.

```bash
RESEARCH_ENABLED=true uv run irc run
```

### Monthly universe maintenance

Use this to refresh the generated Mainland China fund universe from AkShare.

```bash
uv run irc universe build-cn-funds
uv run irc config validate
```

### Quarterly thesis refresh

Use this when you want decision-grade thesis cards backed by fresh theme research plus constituent filings and broker reports.

```bash
uv run irc research
uv run irc fundamentals snapshot --target all --top-n 10
uv run irc run --from discover
```

(`--from discover` re-runs every stage from discover through decision; opportunity + memo + decision are part of the default chain.)

`fundamentals snapshot --target all --top-n 10` is intentionally not part of `irc run`; it can take several minutes because it fetches filings and reports target by target.

### Thematic fund mining (`irc narrative`)

Mine the funds tied to an investment *narrative* — e.g. `compute_metals` (算力金属: AI-datacenter demand for copper / aluminium / tin industrial metals + PCB-gold) — and decide, per fund, **whether to invest and at what risk level**. A narrative is a curated, frozen **reference basket** of stocks + SW industries at `config/narratives/<name>.yaml`; the command resolves it to a ranked fund shortlist by **holdings look-through** (a fund qualifies when its disclosed top-10 overlaps the basket), then — opt-in — runs the deepest per-fund analysis on the shortlist. It reuses the opportunity-grade cores and never touches the main pipeline's outputs.

**Screen only (default — cheap; network = top-10 holdings fetches):**

```bash
uv run irc narrative compute_metals                       # screen only is the default
uv run irc narrative compute_metals --screen-only --min-overlap 12   # lower the basket-weight bar
```

Writes, under `outputs/<today>/narrative/`:
- `compute_metals_shortlist.{md,json}` — the ranked shortlist (basket-weight %, overlap count, hits)
- `compute_metals_screen_diagnostics.json` — funds excluded and **why** (e.g. `no_published_holdings`); never silently dropped

```bash
jq '.funds[] | {id: .instrument_id, name: .name_cn, wt: .basket_weight_pct, n: .overlap_count}' \
  outputs/$(date +%F)/narrative/compute_metals_shortlist.json
```

**Full deep analysis (`--analyze`) — screen, then opportunity-grade per-fund eval + a prospective-buy `position_risk_level`:**

```bash
# Prerequisite — the analyze phase needs the DuckDB market store:
uv run irc ingest                                         # builds data/local.duckdb

uv run irc narrative compute_metals --analyze             # screen + deep analyze (auto-builds missing snapshots)
uv run irc narrative compute_metals --analyze --quarter 2026Q2 --top-n 10
```

`--analyze` **auto-builds** the per-fund snapshot cache for shortlisted funds that lack one — active funds (`cn_equity_fund`) get an `active_fund` snapshot, passive funds (`cn_etf` / QDII / `us_etf` / `hk_etf`) get a fund-level NAV snapshot — so narrative-*discovered* funds (absent from `scoring.json`) get deepened, not just screened. Autobuild is default-on; set `IRC_NARRATIVE_AUTOBUILD=0` to disable it (then the phase is cache-only like `irc opportunity`), and it is bounded by `IRC_FETCH_BUDGET` (a budget trip exits cleanly with `rc=3`). `irc fundamentals snapshot` (quarterly) pre-warms the index/sector NAV caches but is **not** a prerequisite for narrative-discovered funds — it cannot populate their cache. If `data/local.duckdb` or a snapshot quarter is entirely absent, the screen outputs are still written and the command exits `rc=2` with an actionable message.

`--analyze` additionally writes `compute_metals_report.{md,json}` — per shortlisted fund: the four sub-states, `opportunity_state`, `dca_action`, `risk_action`, falsification/trim triggers, review cadence, cited `[ref:…]` thesis evidence (the `.md` renders the evidence **prose** + a citation-id-sorted **footnote appendix** that resolves every `[ref:…]`, plus product-quality **drivers** — 费率/规模/任职/跟踪误差 — next to `质量`), and the **`position_risk_level`** ∈ `{low, moderate, elevated, high, insufficient}` for the *prospective* buy. A fund whose evidence can't be gathered surfaces as `insufficient` (never crashes); on `insufficient` rows the `.md` **suppresses** the unearned action triad / triggers / sub-states (H3 gapped-row discipline) and shows a `证据不足 / insufficient — refresh evidence` line instead (the `.json` keeps the full data). The `.md` adds no datum the `.json` lacks.

Flags: `--screen-only` (default) · `--analyze` · `--min-overlap PCT` (override the config basket-weight threshold) · `--top-n N` · `--quarter <YYYYQn>` · `--db <path>` · `--out <dir>` · `--repo-root <path>`.

**Add a new narrative (AI, robots, …) with no code change** — drop a new `config/narratives/<name>.yaml` mirroring `compute_metals.yaml`, validate with `uv run irc config validate`, then `uv run irc narrative <name>`.

## Debug session: run phases individually

Use this playbook when one stage failed, when you want to inspect intermediate artifacts, or when you fixed an upstream issue and do not want to rerun everything.

```bash
# 1. Validate config before chasing runtime issues.
uv run irc config validate

# 2. Refresh raw market/fund data.
uv run irc ingest

# 3. Run web research only, or smoke-test one theme.
uv run irc research
uv run irc research --theme us_monetary
uv run irc research --theme cn_equity_property_policy

# 4. Inspect research health.
ls data/research
jq '.themes[] | {theme, citation_count, failure_reason, provider_failures}' data/research/research_status.json
jq '.themes[] | select(.failure_reason != "")' data/research/research_status.json
uv run irc eval research

# 5. Rebuild fundamentals snapshots.
uv run irc fundamentals snapshot --target 沪深300 --top-n 10
uv run irc fundamentals snapshot --target all --top-n 10

# 6. Run default pipeline stages one by one.
uv run irc discover
uv run irc score
uv run irc gold
uv run irc allocate
uv run irc plan
uv run irc opportunity
uv run irc memo
uv run irc decision

# 8. Ask grounded questions against today's outputs.
uv run irc ask "Is SGOL overvalued?"

# 9. Resume the pipeline after fixing or refreshing an upstream artifact.
uv run irc run --from score
uv run irc run --from discover

# 10. Run one stage with verbose tracebacks.
DEBUG=true uv run irc ingest
DEBUG=true uv run irc research
DEBUG=true uv run irc run --from discover
```

You can also use `uv run irc run --only <stage>` for a pipeline-stage-only rerun. Valid stages are `ingest`, `research`, `discover`, `score`, `gold`, `allocate`, `plan`, `opportunity`, `memo`, and `decision`.

## Output inspection cheatsheet

| Command | Main outputs |
|---|---|
| `uv run irc ingest` | `data/local.duckdb`, provider manifests under `data/_manifest/` |
| `uv run irc research` | `data/research/*.md`, `data/research/research_status.json` |
| `uv run irc fundamentals snapshot` | `data/fundamentals/<quarter>/*.json` |
| `uv run irc discover` | `outputs/<date>/discovered_watchlist.csv`, `outputs/<date>/discovery_diagnostics.csv` |
| `uv run irc score` | `outputs/<date>/scoring.json` |
| `uv run irc gold` | Gold regime and band outputs under `outputs/<date>/` |
| `uv run irc allocate` | `outputs/<date>/proposed_allocation.yaml` |
| `uv run irc plan` | `outputs/<date>/trade_plan.yaml` |
| `uv run irc memo` | `outputs/<date>/memo.md`, `memo_audit.txt`, `memo_traceability.json` |
| `uv run irc opportunity` | `outputs/<date>/opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md` |
| `uv run irc eval-funds --ids "<id1>,<id2>"` | targeted per-fund opportunity_state / core_dca evaluation from cache + DuckDB (sidesteps discovery + the active-fund cap). Writes `outputs/<today>/fund_eval.{md,json}`. |
| `uv run irc decision` | `outputs/<date>/decision_report.json`, `decision_report.md` |

Useful inspection commands:

```bash
jq '.themes[] | {theme, citation_count, failure_reason, provider_failures}' data/research/research_status.json
jq '.themes[] | select(.failure_reason != "")' data/research/research_status.json
ls data/fundamentals/*
jq '{target: .lookthrough_target, filings: (.filings|length), broker_reports: (.broker_reports|length), failures: (.failure_reasons|length)}' data/fundamentals/*/*.json
uv run irc eval research
```

## Tests

```bash
uv run pytest                                       # unit + integration
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
| Weekly full | Merged configured universe, discovery, scoring, thesis card refresh, decision-readiness | `irc run` (opportunity + decision are now part of the default chain) |
| Monthly universe rebuild | Re-fetch broad fund catalog, regenerate `cn_funds.generated.yaml` | `irc universe build-cn-funds` |
| Quarterly thesis research | Theme search + citations and constituent snapshot refresh | `uv run irc research` plus `uv run irc fundamentals snapshot --target all --top-n 10` |

The system does not scan every fund deeply on every run. Universe generation runs monthly; weekly analysis operates on the already-filtered configured universe after deterministic caps.

### Evidence refresh order

`irc opportunity` reads cached evidence; it does not fetch it live. Refresh inputs in this order when you want decision-grade thesis cards:

1. `uv run irc ingest` — refresh local market/fund data used by discovery and scoring.
2. `uv run irc research` — refresh macro, policy, gold-driver, geopolitics, and holdings-sector citations under `data/research/`.
3. `uv run irc fundamentals snapshot --target all --top-n 10` — refresh constituent filings and broker reports for every registered snapshot target under `data/fundamentals/`.
4. `uv run irc run --from discover` — rebuild discovered watchlist, scores, allocation, trade plan, opportunity, memo, and decision from the refreshed inputs.

`--target all` currently expands to the registered broad-CN targets: 沪深300, 中证500, 中证1000, 中证A500, 上证50, 科创50, 创业板, 中证红利, 红利低波. Sector themes and QDII targets still degrade to `missing_constituent_snapshot` until their `_TargetSpec` entries are added.

<details>
<summary>Deep dive: how `fundamentals snapshot` data drives `thesis_state`</summary>

### Snapshot-to-thesis flow

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

</details>

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
