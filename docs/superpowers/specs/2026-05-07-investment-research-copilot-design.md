# Investment Research Copilot — MVP Design Spec

**Status:** Draft for user review
**Author:** Brainstormed with Claude Code (`superpowers:brainstorming`)
**Date:** 2026-05-07
**Repo:** `investment-research-copilot` (new, separate from `snow-knowledge-database`)
**Related:** `2026-05-07-investment-research-copilot-roadmap.md`(Future track)

---

## 0. Executive Summary

A weekly research-and-recommendation system for a beginner finance user with current holdings = ¥10,000 paper gold via 招商银行 (CMB). The system:

- Generates a candidate watchlist + proposed allocation + research memo every week, **without requiring the user to hand-write a portfolio or watchlist**.
- Combines OpenBB / AKShare / Scrapling / RSS / Local Deep Research as data + research layers; uses DeepSeek (via direct API) and Claude (via OpenRouter) for LLM tasks.
- Differentiates buy methods by asset class (`gold_savings_dca` for paper gold, `dca_weekly` for QDII funds, `lump_sum` / `scaled_in_N` / `threshold_triggered` / `small_account_anchor` as appropriate).
- Treats every claim as auditable: every score, every memo line traces back to a `raw_ref` (source + retrieved_at + raw artifact).
- First-class eval framework: 12 stages × ~40 metrics, each with thresholds and CLI runner.
- Outputs Markdown reports + CSV/JSON. No dashboard, no broker integration, no auto-trading in MVP.

---

## 1. Project Boundary

### Scope (In)

- **Universe**: gold + Mainland China funds + Mainland China ETFs + HK ETFs (via QDII proxy) + US ETFs (via QDII proxy).
- **Decision cadence**: long-term core + medium-term rotation. No high-frequency / short-term trading.
- **Risk profile**: steady; max-drawdown band 10–20%.
- **Holding privacy**: anonymized via percentage-based reasoning. Real cost values stored locally only; reports show ratios.
- **Outputs**: `outputs/<date>/research_memo.md` + companion CSV/JSON/YAML.
- **Data sources**: free / public first. Pluggable paid sources later (Tushare etc.).
- **Compliance posture**: research memos for human review only; never executes trades.

### Scope (Out, MVP)

- Auto-trading, broker integration, real-time market data feeds.
- HTML dashboard / web UI (Markdown only).
- Individual stock analysis (funds / ETFs / gold only).
- Kronos or any autoregressive model as final decision layer.
- Postgres / InsForge / multi-user.

### Repo posture

- Separate repository at `~/Documents/Repository/investment-research-copilot`.
- `snow-knowledge-database` remains an Obsidian/content system; this project is runnable code.

---

## 2. Inputs, Outputs, Data + News Layers, LLM Gateway

### 2.A User Inputs (only two files)

`inputs/account.yaml`:

```yaml
accounts:
  - broker: cmb
    currency: cny
    available_venues: [cmb_fund, cmb_gold]
    holdings:
      - asset_class: gold
        form: paper_gold
        cost_basis_cny: 10000
```

`inputs/preferences.yaml`:

```yaml
risk_band:
  max_drawdown: [0.10, 0.20]
  horizon: long_core_medium_rotation

universe:
  cn_funds: true
  cn_etfs: true
  hk_etfs: true
  us_etfs: true

asset_class_targets:
  gold:           { center: 0.20, band: [0.12, 0.28] }
  cn_equity_fund: { center: 0.25, band: [0.18, 0.35] }
  cn_bond_fund:   { center: 0.15, band: [0.10, 0.25] }
  hk_etf:         { center: 0.10, band: [0.05, 0.15] }
  us_etf:         { center: 0.25, band: [0.18, 0.35] }
  cash:           { center: 0.05, band: [0.00, 0.10] }

currency_tolerance:
  cny: [0.40, 0.65]
  usd: [0.25, 0.45]
  hkd: [0.05, 0.20]

constraints:
  allow_short: false
  allow_leverage: false
  exclude_themes: []

investment_plan:
  monthly_new_capital_cny: 0   # user fills; if 0 system gives ratios only

report_language: zh
```

`watchlist` and `target_allocation` are NOT inputs — they are system outputs.

### 2.B System Outputs (per `outputs/<date>/`)

| File | Producer | Content |
|---|---|---|
| `discovered_watchlist.csv` | Stage 3 Discovery | candidates × role × LLM reason |
| `scoring.json` | Stage 4a | per-instrument 5-factor scores + `factor_breakdown` |
| `gold_regime.json` | Stage 4b | regime classification + 6-driver scoreboard |
| `gold_band.yaml` | Stage 4b | 6m support/resistance + 3-scenario range |
| `proposed_allocation.yaml` | Stage 5 | target_weights + selected_instruments + diversification check |
| `trade_plan.yaml` | Stage 6 | per-trade buy_method + venue + timing + triggers |
| `research_memo.md` | Stage 7 | 7-section memo (synthesizer + auditor) |
| `event_log.json` | All stages | every event with stage / severity / timestamp / raw_ref |
| `evals/<stage>/report.json` | Stage 8 | per-stage metrics with thresholds |

`outputs/queries/<ts>.md` is a side branch produced by `irc ask`.

### 2.C Data + News Layers

#### Data layer

| Layer | Tool | Coverage | Role |
|---|---|---|---|
| L1 primary | OpenBB | US/HK ETF prices, macro (FRED/ECB/IMF/EconDB), commodities (EIA/CFTC), USD/rates/inflation | "Connect once, consume everywhere" |
| L1 China supplement | AKShare (Python lib, free) | CN public funds NAV/holdings/AUM, CN ETFs, A-share, SHFE gold | Fills OpenBB gap on China |
| L2 last-mile | Scrapling | Fund factsheets / manager commentary PDFs / fee tables / WGC reports | Only when L1 misses; enforces 4-tuple provenance |

#### News layer (independent from data layer; 7 topic domains)

| Topic | Required free sources |
|---|---|
| US monetary policy | federalreserve.gov releases / FRED / CME FedWatch / FOMC minutes |
| US fiscal & politics | Treasury.gov / Reuters Politics / CFR |
| China monetary & fiscal | PBoC / MoF / Xinhua / CCTV Finance / 央行公开市场操作 |
| China equity & property policy | CSRC / 银保监会 / 东方财富 / 财新 free |
| Geopolitics | CFR / ISW / Brookings / Reuters Top / SCMP free |
| Gold-specific | World Gold Council / LBMA / Kitco / SHFE notices / SPDR (GLD) holdings |
| Holdings-driven sectors | Dynamic RSS subscriptions following watchlist themes |

Tools by tier:

| Tier | Tool | Purpose |
|---|---|---|
| N1 | RSS aggregator (`feedparser`) | Cheap, stable, weekly coverage |
| N2 | OpenBB news providers | Benzinga / SeekingAlpha / FMP / WSJ via OpenBB auth |
| N3 | Scrapling | Fed speeches / FOMC minute PDFs / WGC quarterlies / paywalled-but-free pages |
| N4 | Local Deep Research | Synthesize N1–N3 into cited theme research |

**Provenance contract**: every record carries `source_url, retrieved_at, topic, raw_text_ref`. Any memo claim referencing news must cite at least one of these tuples.

#### Research / memory layer

| Layer | Tool | Purpose |
|---|---|---|
| L4 | Local Deep Research | Cited theme research; permanent research memory across runs |

### 2.D LLM Gateway

Two providers, single OpenAI-compatible gateway:

| Provider | Base URL | Env key | Use |
|---|---|---|---|
| `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | Default workhorse (direct, cheapest) |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | Claude (memo synthesis + audit) + optional DeepSeek fallback |

Task routing (`config/llm.yaml`):

```yaml
providers:
  deepseek:
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  openrouter:
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

tasks:
  news_summary:       { provider: deepseek,   model: deepseek-chat }
  news_dedup:         { provider: deepseek,   model: deepseek-chat }
  factor_screening:   { provider: deepseek,   model: deepseek-chat }
  watchlist_reason:   { provider: deepseek,   model: deepseek-chat }
  scoring_rationale:  { provider: deepseek,   model: deepseek-reasoner }
  thesis_falsify:     { provider: deepseek,   model: deepseek-reasoner }
  interactive_query:  { provider: deepseek,   model: deepseek-reasoner }
  memo_synthesis:     { provider: openrouter, model: anthropic/claude-opus-4.7 }
  memo_audit:         { provider: openrouter, model: anthropic/claude-sonnet-4.6 }
```

Switching DeepSeek to OpenRouter is one-line:
```yaml
news_summary: { provider: openrouter, model: deepseek/deepseek-chat }
```

**Hard rule**: `memo_synthesis` and `sanity_check` failures NEVER silently fall back. Hard fail with explicit error.

### 2.E Secrets

`.env` (gitignored), loaded via `pydantic-settings`. `.env.example` checked in. YAML configs reference env names only.

---

## 3. Discovery + Scoring

### 3.A Discovery Funnel (5 steps, pure-function pipeline)

```
Universe → Hard Filter → Quality Filter → Role Bucket → LLM Reason
```

1. **Universe enumeration** — per asset_class from data layer; gold via dedicated path.
2. **Hard filter** (`config/discovery.yaml`):
   - Inception ≥ 3y; CN fund AUM ≥ 5亿; US/HK ETF AUM ≥ 1亿USD
   - CN active ≤ 1.5%; CN passive ≤ 0.5%; US ETF ≤ 0.30%
   - ETF daily volume ≥ 1000万; CN fund no recent suspension
   - Excluded by `preferences.exclude_themes` + `overrides.ban_list`
3. **Quality filter**: max_drawdown_3y ≤ user max × 1.2; tracking error ≤ 1.5% (passive); manager tenure ≥ 2y (active).
4. **Role bucket**: each role keeps ≥ 8 candidates; relax with `relaxed: true` if short.
5. **LLM reason**: DeepSeek-V3 produces ≤ 3-sentence rationale + 1-line risk note, must cite ≥ 1 raw_ref.

Roles:
- `core_gold_hedge`, `core_cn_equity`, `core_us_equity`
- `satellite_cn_growth`, `satellite_us_tech`
- `defensive_cn_bond`, `defensive_us_bond`
- `hedge_low_correlation`

### 3.B Scoring: 5 Factor Families

| Factor | Default weight | Sub-factors | Source |
|---|---|---|---|
| Valuation / Cost | 10% | expense ratio, premium/discount, nominal yield | OpenBB / AKShare |
| Risk | 25% | drawdown_3y, vol_1y, downside_capture, tracking_error | OpenBB / AKShare |
| Quality | 20% | AUM stability, manager tenure, holdings concentration, factor exposure clarity | AKShare / Scrapling |
| Macro Fit | 25% | regime fit (LLM-assessed) | LDR + News |
| Thesis / News | 20% | catalysts, risk events, narrative momentum | LDR + News |

Score → action:

| composite | action | conviction adjustment |
|---|---|---|
| 80-100 | strong_buy_candidate | data completeness < 80% → demote |
| 60-80 | buy_candidate | as above |
| 40-60 | watch | — |
| 20-40 | avoid | — |
| 0-20 | strong_avoid | — |

`factor_breakdown.json` per scored instrument:

```json
{
  "instrument_id": "510300",
  "name_cn": "华泰柏瑞沪深300ETF",
  "composite_score": 72,
  "action": "buy_candidate",
  "conviction": "med",
  "factors": {
    "valuation_cost": { "score": 88, "raw_ref": "ref_a1" },
    "risk":           { "score": 65, "raw_ref": "ref_a2" },
    "quality":        { "score": 78, "raw_ref": "ref_a3" },
    "macro_fit":      { "score": 70, "raw_ref": "ref_a4_news_5_research_2" },
    "thesis_news":    { "score": 60, "raw_ref": "ref_a5_news_3" }
  },
  "weights_version": "2026-05-07-v1",
  "data_completeness": 0.94
}
```

### 3.C Gold-Specific Scoring (independent module)

6 drivers:

| Driver | Source | Direction | Weight |
|---|---|---|---|
| US 10y real yield (TIPS) | FRED via OpenBB | inverse | 25% |
| USD index (DXY) | OpenBB | inverse | 15% |
| Inflation expectations (5y5y forward) | FRED | positive | 15% |
| Central bank gold purchases (WGC quarterly) | Scrapling WGC | slow positive | 15% |
| Gold ETF holdings (GLD/IAU) | Scrapling SPDR | short-term confirmation | 15% |
| Geopolitical stress proxy | LDR + News | pulse positive | 15% |

Outputs:
- `gold_regime.json`: `regime ∈ {range_bound, uptrend, downtrend}` based on 6m vol vs 1y avg + ADX < 25.
- `gold_band.yaml`: 6m high H, low L, midpoint M, Q1, Q3.
- 3 scenarios: strong_bull / base (current) / pullback with driver thresholds + indicative price ranges.
- `gold_tilt`: `{overweight, neutral_plus, neutral, neutral_minus, underweight}`, hard-clamped within `preferences.gold.band`.

### 3.D Sanity Check (block bad scores)

Before publishing recommendations:
- Take instrument data from N=12 months ago.
- Compute scores using **then-current** data.
- Spearman correlation between `score_quintile` and `realized_risk_adj_return_quintile`.
- ρ ≤ 0 → HARD FAIL (blocks Stages 5-7), writes `PIPELINE_HALTED.md`.
- 0 < ρ ≤ 0.1 → continue but downgrade all conviction one notch.

### 3.E User Sovereignty

Three override channels, all logged to `event_log.json` and called out in memo:

1. `config/scoring.yaml` — adjust factor weights globally
2. `config/overrides.yaml` — `boost_list` / `ban_list` per instrument
3. `config/macro_view.yaml` — user's macro thesis, biases Macro Fit factor

---

## 4. Allocation + Trade Plan + Memo

### 4.A 100w Starter Allocation (gold-20% preference)

| Area | Center | Band | 100w center | Notes |
|---|---|---|---|---|
| Gold | 20% | 12-28% | ¥200,000 | User's preference; real-yield sensitive |
| CN equity (fund + ETF) | 25% | 18-35% | ¥250,000 | 沪深300 + 中证500 + 1-2 主动头部 |
| CN bond | 15% | 10-25% | ¥150,000 | Mid-long pure bond focus |
| HK ETF | 10% | 5-15% | ¥100,000 | 恒指 / 恒生科技 / 港股红利 |
| US ETF | 25% | 18-35% | ¥250,000 | 标普 500 wide-base + small NAS100 |
| Cash / MMF | 5% | 0-10% | ¥50,000 | Trigger-ready buffer |

Currency exposure (with gold = 20% paper gold in CNY):
- CNY: 65% (at upper bound of `[0.40, 0.65]`)
- USD: 25%
- HKD: 10%

Expected drawdown: 10-15% historically (2008/2015/2018/2020/2022 backtest).

### 4.B Allocation Derivation (5 steps)

1. Apply `gold_tilt` to gold center within band.
2. Per asset_class: rank by composite_score, take top-K (K=2-3 per role bucket).
3. Score-weighted softmax to distribute class weight across selected instruments.
4. Hard constraints: no_short, no_leverage, currency_tolerance, exclude_themes.
5. Correlation/concentration filter: any pair 1y corr > 0.85 → keep higher score; single instrument ≤ class limit / 2.

### 4.C Cold Start: Build / Hybrid / Steady-State

| Condition | Mode | Behavior |
|---|---|---|
| `current_total_cny < 5万` OR `monthly_new_capital < 5000` | **Build** | Fill priorities, no % targets, gold keeps small `gold_savings_dca` anchor |
| `5万 ≤ current_total < 10万` | **Hybrid** | Ratios given, "hold and dilute" replaces "trim" |
| `current_total_cny ≥ 10万` | **Steady-State** | Full rebalance allowed |

User's current state (¥10,000 paper gold) → **Build mode**. First-week trade plan example:

```
Holdings: 100% gold (¥10,000); target gold weight 12-28%
Strategy: do not sell gold; new capital fills other classes; gold dilutes naturally.
Fill priority (by deficit):
  1. core_us_equity (proxy QDII)  → month 1
  2. core_cn_equity                → month 1
  3. defensive_cn_bond             → month 2
  4. satellite_*                   → month 3+
Gold anchor: ¥200-500/week via 招行 paper gold (持续 dca)
```

**Build-mode interaction with §4.D defaults**: while in Build mode, the
**rotation target** (the class being filled this period) uses its asset-class
default `buy_method` from §4.D. Non-rotation classes are paused this period,
except gold which always runs `gold_anchor_plus_band` at the anchor-only level.
When the account graduates to Hybrid or Steady-State, all classes use their
§4.D defaults concurrently.

### 4.D Buy Methods (5 + 1)

| Method | Description | Defaults |
|---|---|---|
| `lump_sum` | one-shot purchase | low-vol / extreme-cheap valuation |
| `dca_weekly` / `dca_monthly` | fixed amount each interval | high-uncertainty default |
| `scaled_in_N` | N tranches over N weeks | mid-vol with directional conviction |
| `threshold_triggered` | macro signal triggers | gold / rate-sensitive products |
| `gold_anchor_plus_band` | weekly anchor DCA + band-based scale | paper gold (招行 account gold) |
| `small_account_anchor` | rotation fill + small anchor | total < 5万 or monthly < 5000 |

Asset-class default mapping:

| Asset class | Default | Switch on |
|---|---|---|
| Gold (paper / 招行) | `gold_anchor_plus_band` | real_yield ≤ 0% → double anchor; price > 6m Q3 → trim 5-10% |
| Gold ETF (518880) | `scaled_in_3` | premium < 0.3% AND tilt = neutral_plus → `lump_sum` |
| CN active fund | `dca_monthly` | valuation_pct < 20 → `lump_sum` |
| CN passive (off-exchange) | `dca_weekly` | valuation_pct 20-40 → `scaled_in_4` |
| CN on-exchange ETF | `scaled_in_3` | valuation_pct < 15 → `lump_sum` |
| HK ETF | `scaled_in_4` | USD trending strong + HK valuation_pct < 25 → `lump_sum` |
| US ETF (broad: VTI/VOO) | `lump_sum` | VIX > 25 → `scaled_in_3` |
| US ETF (theme: QQQ) | `scaled_in_4` | overheated → `dca_monthly` |
| CN mid-long bond | `lump_sum` | hike cycle ongoing → `scaled_in_2` |
| CN short-term / MMF | `lump_sum` | — |

### 4.E Gold Range-Bound Strategy (`gold_anchor_plus_band`)

Two-track operation:

**Track 1 — anchor DCA (always running)**: weekly fixed amount, regardless of
price. Default scaling tied to `monthly_new_capital_cny`:
- monthly < ¥1,000  → weekly ¥150-200
- ¥1,000 ≤ monthly < ¥4,000 → weekly ¥200-500
- monthly ≥ ¥4,000 → weekly ≥ ¥500 (cap so anchor stays ≤ 25% of monthly add)

**Track 2 — band trading (range-bound regime)**:

System computes 6m rolling H, L, M, Q1, Q3 each week.

| Price zone | Action |
|---|---|
| ≤ Q1 (lower 25%) | aggressive: weekly DCA × 2-3 |
| Q1 to M | normal DCA pace |
| M to Q3 | pause adds, anchor only |
| > Q3 (upper 25%) | trim 5-10% of position |
| Breaks H or L | regime switch, rebuild signals |

3 scenarios for "where can gold go" (driver-based, not point forecast):

| Scenario | Drivers | CNY/g indicative range | Action |
|---|---|---|---|
| Strong bull | real yield < 0.5% AND DXY < 100 AND CB buying > 1000t/y AND geopolitical escalation | ¥1200-1400+ | aggressive DCA, possibly full position |
| Base (current) | real yield 1.5-2.5% AND DXY 100-110 AND CB buying steady | ¥950-1150 range | band trading |
| Pullback | real yield > 2.5% AND DXY > 110 AND ETF outflows | ¥800-950 | pause, await driver reversal |

### 4.F Valuation-Percentile → Buy-Method Switching

| Valuation percentile (5y) | Buy method | Granularity |
|---|---|---|
| < 30% | `lump_sum` or `scaled_in_2` | 1-2 tranches |
| 30-60% | `dca_weekly` | 12-16 weeks |
| **60-80% (current US)** | `dca_weekly` slow | **24-26 weeks**, ≤ 25% of monthly capital per week |
| 80-95% | `dca_monthly` + threshold | 36+ weeks; only add on VIX > 25 or weekly drop > 4% |
| > 95% | **suspend**, divert to bonds / cash | wait for pullback |

### 4.G Triggers (only quantifiable, monitorable)

| Trigger | Source | Use |
|---|---|---|
| Valuation percentile (PE/PB 5y/10y) | OpenBB / AKShare | switch buy_method |
| Real yield (10y TIPS) | FRED | gold dca scaling |
| VIX | OpenBB | US theme buy_method switch |
| ETF premium/discount | OpenBB | favor discounted ETF |
| Weekly drawdown | prices | < -4% → double DCA week |
| User macro view | `config/macro_view.yaml` | bias trigger thresholds |

### 4.H QDII Universe (default starter pool)

| Target | Off-exchange code | On-exchange code | Note |
|---|---|---|---|
| S&P 500 | 易方达 006075 / 博时 050025 / 华夏 040046 | 513500 华夏标普500ETF | US wide-base default |
| NASDAQ 100 | 易方达 161130 / 广发 270042 | 159941 广发纳指 / 513100 | Tech-heavy |
| MSCI USA | 国泰 165509 | — | broader than S&P |
| Hang Seng | 华夏 000071 / 易方达 110031 | 159920 | HK wide-base |
| Hang Seng Tech | 华夏 013402 | 513180 华夏恒生科技 | HK tech |
| HK Dividend | 华泰柏瑞 006186 | 513530 | defensive yield |
| Gold ETF (CN, CNY) | — | 518880 华安黄金 / 159934 易方达黄金 | paper-gold equivalent, lower fee |

### 4.I Venue Compatibility

`account.yaml.available_venues` declares what user can buy where. Trade plan prefers in-venue products; otherwise routes to a QDII proxy + Roadmap suggestion to expand venues.

Example: user only has CMB → cannot buy VTI directly → system suggests `006075` (易方达标普500) and adds Roadmap T1.4 hint.

### 4.J Memo Template (fixed 7 sections)

```
# 周度投资研究备忘录 — YYYY-MM-DD

## TL;DR
- One-line: current portfolio
- 3-5 recommended actions
- One-line: macro backdrop

## 1. 当前组合
[holdings table + ASCII deviation bar]

## 2. 推荐动作
| Product | Role | Current% | Target% | Δ | Method | Timing | Trigger |

## 3. 推导:为什么是这套配置
- Gold tilt rationale (6 drivers snapshot)
- Top-3 per class with 3-line reasons
- Macro backdrop (USD / US rates / China policy)

## 4. 因子分解
[per-instrument factor_breakdown table with raw_ref anchors]

## 5. 风险与证伪
- Top-3 risks for the week
- Falsification conditions
- Data gaps

## 6. 数据完整性
[per-source freshness + per-stage eval PASS/FAIL]

## 7. 用户覆盖记录
[any user override applied this run]
```

Synthesizer: `anthropic/claude-opus-4.7` via OpenRouter.
Auditor: `anthropic/claude-sonnet-4.6`. Audit failure = WARN; synthesis failure = HARD (no silent fallback).

---

## 5. System Architecture + Data Flow

### 5.A Directory Tree

```
investment-research-copilot/
├── README.md
├── pyproject.toml
├── .env.example
├── inputs/
│   ├── account.yaml
│   └── preferences.yaml
├── config/
│   ├── llm.yaml
│   ├── discovery.yaml
│   ├── scoring.yaml
│   ├── gold_drivers.yaml
│   ├── valuation_buckets.yaml
│   ├── triggers.yaml
│   ├── overrides.yaml
│   ├── macro_view.yaml
│   └── universe/
│       ├── qdii_us.yaml
│       ├── qdii_hk.yaml
│       ├── cn_funds.yaml
│       └── gold.yaml
├── lib/
│   ├── llm/{gateway,cost_tracker,retry}.py
│   ├── data/{openbb_client,akshare_client,manifest}.py + scrapling_jobs/
│   ├── news/{rss_aggregator,openbb_news,scrapling_news,topic_classifier,dedup,events_calendar}.py
│   ├── research/{ldr_client,theme_research,falsification}.py
│   ├── discovery/{universe,hard_filter,quality_filter,role_bucket,reason_writer}.py
│   ├── scoring/
│   │   ├── factors/{valuation_cost,risk,quality,macro_fit,thesis_news}.py
│   │   ├── instrument_score.py, gold_score.py, regime_detect.py
│   │   ├── gold_band.py, sanity_check.py
│   ├── allocation/{mode_selector,target_weights,correlation_filter}.py
│   ├── trades/{buy_method,valuation_percentile,venue_check,triggers}.py
│   ├── memo/{template,synthesizer,auditor,traceability}.py
│   └── queries/{parser,responder}.py
├── cli/irc.py
├── evals/
│   ├── data/, news/, research/
│   ├── discovery/, scoring/, gold_score/
│   ├── allocation/, trade_plan/, memo/, queries/, triggers/
│   ├── architecture/
│   ├── spot_check/{queue.csv,reviewed.csv,runner.py}
│   └── _shared/{report_schema.py,status.py,baseline_diff.py,registry.json}
├── data/                        # gitignored
│   ├── openbb/, akshare/, scraped/, news/, research/
│   ├── local.duckdb
│   ├── cache/llm/
│   └── _manifest/
├── outputs/                     # per-run, immutable
│   └── <YYYY-MM-DD>/...
└── tests/                       # mirrors lib/
```

### 5.B Data Flow (8 stages, single-direction)

```
inputs/ + config/
   ↓
Stage 1 INGEST          (lib/data + lib/news)
   ↓
Stage 2 RESEARCH        (lib/research → LDR theme pulls)
   ↓
Stage 3 DISCOVERY       (5-step funnel → discovered_watchlist.csv)
   ↓
Stage 4a SCORING        Stage 4b GOLD SCORE (parallel)
   ↓                     ↓
   └─────────┬──────────┘
             ↓
Stage 5 ALLOCATION      → proposed_allocation.yaml
   ↓
Stage 6 TRADE PLAN      → trade_plan.yaml
   ↓
Stage 7 MEMO            → research_memo.md
   ↓
Stage 8 EVAL            → outputs/<date>/evals/<stage>/report.json

Side branch: irc ask "<question>" → lib/queries → outputs/queries/<ts>.md
```

### 5.C Module Dependency (acyclic)

```
llm/   ←──── (everyone calling LLM)
data/, news/  (no upstream)
research/   ──► data/ news/ llm/
discovery/  ──► data/ research/ universe(config)
scoring/    ──► data/ news/ research/ llm/
allocation/ ──► scoring/ inputs/preferences
trades/     ──► allocation/ scoring/ inputs/account
memo/       ──► (all upstream) llm/
queries/    ──► scoring/ llm/
```

`evals/architecture/` enforces acyclicity at startup.

### 5.D CLI (`irc`)

```
irc init                       # first-run scaffold
irc run                        # full pipeline
irc run --from <stage>         # resume from cached
irc run --only <stage>         # single stage
irc ingest | research | discover | score | allocate | plan | memo
irc eval [<stage>] [--all] [--update-baseline] [--backtest]
irc ask "<question>"
irc config show | validate
irc freshness
```

### 5.E Persistence

| Type | Location | Form | Write strategy |
|---|---|---|---|
| Raw data | `data/<source>/` | parquet/CSV/JSON/PDF | append, date-partitioned |
| Normalized | `data/local.duckdb` | DuckDB single file | upsert by (instrument_id, date) |
| LLM cache | `data/cache/llm/` | JSON, key=(task, payload_hash, model) | persistent, per-task TTL |
| Manifest | `data/_manifest/<source>.json` | JSON | overwrite per-ingest |
| Run outputs | `outputs/<YYYY-MM-DD>/` | YAML/JSON/MD/CSV | **immutable; append new dates only** |
| Query log | `outputs/queries/<ts>.md` | Markdown | append |

Every DuckDB row carries `_ingested_at`, `_source`, `_raw_ref`. LLM cache hit rate ≥ 60% (excluding `memo_synthesis`) is an architectural eval metric.

### 5.F Functional Constraints

Every stage is `def stage_X(stage_inputs: ImmutableDict, config: ImmutableDict) -> StageOutput`:

- Pure: no global state, no `self.x = y`, no implicit I/O in core logic.
- Immutable: configs are read-only frozendicts; intermediate via `assign` not `inplace`.
- Explicit data flow: ONLY interface between stages = files in `outputs/<date>/`.
- Composition: `irc run` = pure pipe of stage 1...8.
- I/O at edges: file/API/DB calls confined to stage wrappers in `cli/irc.py`.
- Module size: file < 200 lines, function < 20 lines.

### 5.G Configuration Files (12)

| File | Purpose | Edited by |
|---|---|---|
| `inputs/account.yaml` | real holdings + venues | user (rare) |
| `inputs/preferences.yaml` | risk / currency / capital plan | user (rare) |
| `config/llm.yaml` | provider + task routing | maintainer |
| `config/discovery.yaml` | hard filter thresholds | tuner |
| `config/scoring.yaml` | 5-factor weights + action thresholds | tuner |
| `config/gold_drivers.yaml` | 6-driver weights | tuner |
| `config/valuation_buckets.yaml` | percentile → buy_method 5 buckets | tuner |
| `config/triggers.yaml` | trigger thresholds | tuner |
| `config/overrides.yaml` | boost_list / ban_list | user (anytime) |
| `config/macro_view.yaml` | user macro thesis | user (anytime) |
| `config/universe/*.yaml` | candidate pools | maintainer |

All YAMLs validated by `pydantic` schemas; `irc config validate` runs before any stage.

---

## 6. Error Handling + Data Quality

### 6.A Three Failure Tiers

| Tier | Action | User-facing |
|---|---|---|
| HARD | Pipeline halts; writes `outputs/<date>/PIPELINE_HALTED.md`; exit 2 | CLI red error + remediation hint |
| SOFT | Stage emits partial output with `partial: true` + `errors[]`; downstream degrades | event_log entry; memo §5 lists data gaps |
| WARN | Output proceeds; flagged in event_log | memo §6 PASS-with-warning |

HARD triggers (definitive list):
- `inputs/*.yaml` schema fail
- `memo_synthesis` 3 consecutive failures
- Sanity check ρ ≤ 0
- DAG cycle
- DuckDB corrupt / disk full
- OpenBB + AKShare both unreachable ≥ 1 hour

### 6.B Four Data-Quality Dimensions

| Dimension | Check | Failure level |
|---|---|---|
| Freshness | `retrieved_at` vs expected timestamp | price > 2 trading days = WARN; > 7 = SOFT; > 30 = HARD |
| Completeness | required fields not null | key fields missing = SOFT; helper missing = WARN |
| Consistency | cross-source reconcile | 0.5-2% diff = WARN; > 2% = SOFT |
| Provenance | `(source, retrieved_at, raw_ref)` triple present | missing ⇒ record rejected |

Trading-calendar-aware via `pandas-market-calendars` for CN/HK/US.

### 6.C Cross-Source Reconciliation

| Field | Primary | Fallback | Tolerance |
|---|---|---|---|
| US ETF price | OpenBB(yfinance) | OpenBB(Tiingo/FMP) | > 1% = SOFT |
| CN fund NAV | AKShare | Scrapling 天天基金 | > 0.5% = WARN; > 2% = SOFT |
| Gold | AKShare(SHFE) | Scrapling(招行) | > 1% = WARN(bank spread) |
| Real yield / DXY | OpenBB(FRED) | OpenBB(EconDB) | > 0.05pp = WARN |
| Fund fee | AKShare | Scrapling 基金公司 | text mismatch = SOFT |

Conflict policy: prefer primary; on disagreement above SOFT threshold, store both + mark `disagreement: true` + downgrade conviction one notch.

### 6.D Retry / Backoff / Fallback

| Failure | Handling |
|---|---|
| HTTP 429 | exp backoff 2/4/8/16s, max 4 |
| HTTP 5xx | 1/3/9s, 3 tries |
| HTTP 4xx (non-429) | no retry, SOFT |
| Auth fail | no retry, HARD; check `.env` |
| Timeout 30s | 1 retry → fallback source → SOFT |
| DNS fail | 1 retry → offline mode |
| LLM non-JSON / bad schema | 1 retry (temp -0.1) → task SOFT |

Forbidden fallbacks: `memo_synthesis` (no DeepSeek fallback), `sanity_check` (no "ignore" fallback).

### 6.E LLM Gateway Error Boundaries

| Task | On failure |
|---|---|
| `news_summary`, `news_dedup` | retry 1; mark item `summary_failed`; continue |
| `factor_screening` | retry 1; mark instrument SOFT |
| `scoring_rationale` (R1) | retry 1; templated fallback explanation + WARN |
| `thesis_falsify` | same |
| `memo_synthesis` (Opus) | retry 3; **all-fail = HARD** |
| `memo_audit` (Sonnet) | failure → memo `unaudited: true`, WARN |
| `interactive_query` | failure → return error + raw data, let user interpret |

Output schema validation at gateway exit. Drift monitoring: weekly compare token length / field completeness / citation count vs prior week; > 30% deviation = WARN.

### 6.F User Input Validation

Each YAML passes pydantic schema + semantic checks:

| File | Semantic checks |
|---|---|
| `account.yaml` | ≥ 1 holding; venue in known set; currency ISO 4217 |
| `preferences.yaml` | sum of class centers ∈ [0.98, 1.02]; currency_tolerance bounds self-consistent |
| `scoring.yaml` | 5-factor weights sum = 1.0 (±1e-6) |
| `gold_drivers.yaml` | 6 driver weights sum = 1.0 |
| `overrides.yaml` | every instrument_id resolvable in `config/universe/*` |
| `macro_view.yaml` | referenced trigger names exist in `triggers.yaml` |
| `triggers.yaml` | `data_field` exists in DuckDB schema (orphan check) |

`irc config validate` is gate-zero for any stage.

### 6.G Trigger Health & Orphan Detection

Per-trigger weekly metrics:

| Metric | Threshold |
|---|---|
| Coverage (referenced field freshness) | > 7d → trigger demoted to "manual review hint" |
| Hit rate (12m) | > 50% = WARN (threshold too loose); < 5% = WARN (useless) |
| Skew (post-trigger N=10 directional accuracy) | < 50% = "reverse trigger" warning |

Orphan check: trigger references unknown DuckDB field → HARD at startup.

### 6.H State Files & Concurrency

| File | Purpose |
|---|---|
| `data/.run.lock` | file lock; PID + start_time; stale > 6h auto-cleanup |
| `data/_manifest/<source>.json` | freshness + schema_version |
| `outputs/<date>/.tmp/` | staging area; atomic rename on completion |
| `outputs/<date>/PIPELINE_HALTED.md` | only HARD-fail artifact; stage / error / fix |
| `event_log.json` | every event with stage / severity / timestamp / raw_ref |

All file writes: write-temp → fsync → rename. DuckDB transactional. Second concurrent run sees lock → exits with PID hint.

### 6.I Sanity-Check Block Flow

```
After scoring.json
  → sanity_check.run(scoring.json, history=12 months)
  → Spearman(score_quintile, realized_risk_adj_return_quintile)
  → if ρ ≤ 0:
       skip allocation/trade_plan/memo
       write PIPELINE_HALTED.md (correlation curve + likely causes + remediation)
       event_log HARD; notify user
    elif 0 < ρ ≤ 0.1:
       continue; memo §5 marks "weak historical correlation; conviction downgraded"
```

### 6.J Offline Mode

DNS all-fail → degraded mode:
1. All data stages fall back to `data/<source>/` cache.
2. `data/_manifest/` marks `offline_since`.
3. LLM tasks all HARD (no offline LLM in MVP).
4. `memo_synthesis` HARD → PIPELINE_HALTED.
5. CLI offers `irc run --offline-research-only` (stage 1 cached + stage 4 scoring; no memo).

Roadmap: Ollama local fallback (T4.4) triggers when both online providers down + user wants memo regardless.

---

## 7. Per-Stage Eval Framework

### 7.A Eval Directory Structure

```
evals/
├── <stage>/
│   ├── metrics.py       # pure: stage_outputs → metrics_dict
│   ├── runner.py        # CLI: read outputs → compute → diff baseline → write report
│   ├── baselines/<YYYY-MM-DD>.json
│   └── fixtures/
└── _shared/
    ├── report_schema.py
    ├── status.py
    ├── baseline_diff.py
    └── registry.json   # all metric names registered
```

### 7.B CLI

```
irc eval data | scoring | gold_score | ...
irc eval --all
irc eval --all --since 2026-04-01
irc eval scoring --update-baseline
irc eval scoring --backtest --since 2025-05-01
```

Exit codes: 0 (all PASS), 1 (any WARN), 2 (any FAIL).

### 7.C Report Schema

```json
{
  "stage": "scoring",
  "ran_at": "2026-05-07T15:00:00+08:00",
  "based_on": ["outputs/2026-05-07/scoring.json"],
  "config_versions": { "scoring.yaml": "sha256:..." },
  "metrics": {
    "<metric_name>": {
      "value": 0.987,
      "threshold": { "warn_below": 0.99, "fail_below": 0.95 },
      "status": "WARN",
      "n_observations": 152,
      "details_ref": "outputs/2026-05-07/evals/scoring/details_<metric>.csv"
    }
  },
  "regressions_vs_baseline": [
    { "metric": "...", "baseline": 0.995, "current": 0.987, "delta": -0.008, "regressed": true }
  ],
  "overall": "PASS_WITH_WARNINGS"
}
```

### 7.D Per-Stage Metric Catalog

| Stage | Metric | Threshold | Failure level |
|---|---|---|---|
| **data** | freshness_per_source (days) | price ≤ 2; NAV ≤ 2; macro ≤ 35 | per 6.B |
| | completeness_per_field | ≥ 95% | SOFT |
| | schema_consistency | 100% | HARD |
| | cross_source_disagreement_rate | ≤ 1% | WARN |
| **news** | coverage_per_topic_per_week | ≥ 3 each | SOFT |
| | dedup_rate | ≥ 80% cluster catch | WARN |
| | citation_reachability (7d) | ≥ 90% | WARN |
| | source_diversity | ≥ 2 per topic | WARN |
| **research** | theme_coverage | 7 themes ≥ 1 pull | SOFT |
| | ldr_citation_validity (sample N=10) | ≥ 90% valid | WARN |
| | hallucination_spotcheck | manual queue | — |
| **discovery** | candidates_per_role | ≥ 8 (< 5 = FAIL) | SOFT |
| | filter_integrity | 100% rejections traceable | SOFT |
| | dedup | 0 duplicates | HARD |
| | llm_reason_grounding | each reason ≥ 1 raw_ref | SOFT |
| **scoring** | factor_breakdown_completeness | ≥ 99% | WARN |
| | raw_ref_reachability | ≥ 99% | SOFT |
| | historical_sanity_rho | > 0 | HARD |
| | score_distribution_stability (KS) | < 0.3 | WARN |
| **gold_score** | drivers_freshness | each ≤ 7 days | SOFT |
| | regime_flip_4w | ≤ 1 | WARN |
| | band_validity | low<high, range>1% | SOFT |
| | tilt_within_preferences_band | 100% | HARD |
| **allocation** | weight_sum | abs(Σ-1) < 1e-3 | HARD |
| | in_band_per_class | each in band | HARD |
| | effective_n | ≥ 4 | WARN |
| | currency_in_tolerance | each currency in [low,high] | SOFT |
| | max_pair_correlation_1y | ≤ 0.85 | WARN |
| **trade_plan** | venue_compatibility_marked | 100% | HARD |
| | buy_method_class_match | 100% | HARD |
| | trigger_monitorability | 100% | HARD |
| **memo** | seven_sections_present | 100% | HARD |
| | raw_ref_reachability_in_memo | ≥ 99% | SOFT |
| | auditor_no_factual_flags | 0 issues | SOFT |
| | length_drift_vs_baseline | ±30% tokens | WARN |
| **queries** | median_response_time | ≤ 30s | WARN |
| | citation_attached_per_response | 100% | SOFT |
| | internal_consistency_with_latest_memo | 100% (LLM check) | WARN |
| **triggers** | coverage / hit_rate / skew | per 6.G | WARN |
| **architecture** | DAG_acyclic | True | HARD |
| | output_files_present | 100% | HARD |
| | max_file_loc | ≤ 250 | WARN |
| | llm_cache_hit_rate (excl memo_synthesis) | ≥ 60% | WARN |

12 stages × ~3-4 metrics ≈ 40+ checks.

### 7.E Three Eval Modes

| Mode | Trigger | Use |
|---|---|---|
| Per-run | end of `irc run` | weekly self-check |
| Regression | `irc eval <stage>` default | diff vs `baselines/latest.json` |
| Backtest | `irc eval scoring --backtest --since YYYY-MM-DD` | replay 12m, validate stability (no LLM, cached) |

### 7.F Baseline Management

- `evals/<stage>/baselines/<YYYY-MM-DD>.json` git-tracked.
- Default compare: `baselines/latest.json` (symlink).
- `irc eval <stage> --update-baseline` writes new + commits.
- Regression marks `delta` per metric; `regressed: true` if outside metric tolerance.
- **Forbidden**: implicit baseline auto-update.

### 7.G Spot-Check Queue

```
evals/spot_check/
├── queue.csv      # auto-sampled weekly, N=10
├── reviewed.csv   # human pass/fail/notes
└── runner.py
```

Weekly auto-sampling: 5 LDR citations + 3 Discovery LLM reasons + 1 memo claim + 1 query response. `reviewed.csv` fail counts toward next-week eval as WARN.

### 7.H Integrations

| Touchpoint | Eval data consumed |
|---|---|
| `irc freshness` | per-source freshness + week's overall status |
| memo §6 | auto-embed 12-stage PASS/WARN/FAIL table |
| `irc run` exit code | any HARD eval = exit 2 |

### 7.I CI / Schedule

- Pre-commit: `irc config validate` + `irc eval architecture`.
- Weekly cron Monday 09:00: `irc run` + `irc eval --all`.
- (Roadmap T4.6) GitHub Actions on PRs: `irc eval architecture` + `irc eval scoring --backtest --quick`.

### 7.J Meta-Eval (`irc eval framework`)

| Check | Pass condition |
|---|---|
| Each stage has `evals/<stage>/runner.py` | 12 stages all present |
| Every metric has `threshold` field | all metrics rated |
| All metric names in `evals/_shared/registry.json` | new metrics registered |
| `baselines/<latest>.json` schema valid | format integrity |

---

## 8. Future Roadmap (high-level pointer)

See `2026-05-07-investment-research-copilot-roadmap.md` for the full Tier 1-5 catalog with trigger / value / integration / cost / dependency for each item.

Out-of-MVP highlights:
- Kronos signal (T2.1), TradingAgents debate (T3.1), Dexter interactive agent (T3.2), individual stocks (T3.3).
- InsForge / Postgres / dashboard (T4.1, T4.2).
- US brokerage / 沪港通 / multi-account aggregation (T1.2, T1.4, T1.5).
- Tushare upgrade (T1.1), risk-factor model (T2.2), adaptive LLM router (T2.3).
- Ollama offline (T4.4), Keychain secrets (T4.5), GH Actions CI (T4.6).
- Tax-aware trading (T5.2), filings watcher (T5.1), quarterly theme reports (T5.3).

Permanently out of scope: real trades / brokers, derivatives, HFT, prescriptive investment advice.

---

## Appendices

### A. `account.yaml` — current state
```yaml
accounts:
  - broker: cmb
    currency: cny
    available_venues: [cmb_fund, cmb_gold]
    holdings:
      - asset_class: gold
        form: paper_gold
        cost_basis_cny: 10000
```

### B. `preferences.yaml` — gold-20 starter
See §2.A.

### C. `config/llm.yaml` — task routing
See §2.D.

### D. Default `config/scoring.yaml` weights
```yaml
factor_weights:
  valuation_cost: 0.10
  risk:           0.25
  quality:        0.20
  macro_fit:      0.25
  thesis_news:    0.20

action_thresholds:
  strong_buy_candidate: 80
  buy_candidate:        60
  watch:                40
  avoid:                20

conviction_data_completeness_threshold: 0.80
weights_version: "2026-05-07-v1"
```

### E. Default `config/gold_drivers.yaml`
```yaml
drivers:
  real_yield_10y_tips: { weight: 0.25, direction: inverse }
  dxy:                 { weight: 0.15, direction: inverse }
  inflation_5y5y:      { weight: 0.15, direction: positive }
  cb_purchases_wgc:    { weight: 0.15, direction: positive_slow }
  etf_holdings_gld:    { weight: 0.15, direction: confirmation_short }
  geopolitical_proxy:  { weight: 0.15, direction: positive_pulse }

regime_detection:
  vol_window_months: 6
  vol_baseline_window_months: 12
  vol_ratio_range_threshold: 1.5
  adx_range_threshold: 25

band:
  rolling_window_months: 6
  zones:
    aggressive_below_q1: 1.0
    normal_q1_to_m: 1.0
    pause_m_to_q3: 0.0
    trim_above_q3: -0.05_to_-0.10
```

### F. CLI reference
```
irc init                            scaffold default inputs/config
irc config show | validate          inspect configuration
irc freshness                       data manifest summary
irc ingest | research | discover    | score | allocate | plan | memo
                                    run a single stage
irc run [--from <stage>] [--only <stage>]
                                    run pipeline (full or partial)
irc ask "<question>"                interactive query side branch
irc eval [<stage>] [--all] [--update-baseline] [--backtest]
                                    eval framework
```

### G. Glossary
- **raw_ref**: 4-tuple `(source, retrieved_at, topic_or_id, raw_artifact_path)` accompanying every record; reachable via DuckDB or filesystem.
- **role bucket**: discovery role like `core_us_equity`, `defensive_cn_bond`, `hedge_low_correlation`.
- **conviction**: per-recommendation confidence label `{low, med, high}`, downgraded on data completeness or weak sanity correlation.
- **gold_tilt**: ±category for gold center adjustment, hard-clamped within `preferences.gold.band`.
- **Build / Hybrid / Steady-State**: portfolio mode determined by `current_total_cny` and `monthly_new_capital_cny`.

---

**End of MVP design spec.**
