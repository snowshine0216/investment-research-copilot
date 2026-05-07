# Investment Research Copilot — Future Roadmap

**Status:** Draft for user review
**Date:** 2026-05-07
**Companion to:** `2026-05-07-investment-research-copilot-design.md` (MVP)

Each entry is independently follow-able. Cost: **S** < 1 week, **M** 1-3 weeks, **L** > 1 month. "Trigger" = the condition under which the entry becomes worth doing; do not pre-build.

---

## Tier 1 — Data / Universe Expansion

### T1.1 Tushare upgrade (replace/supplement AKShare)
- **Trigger**: AKShare fails ≥ 2 times/month, OR factor work needs higher precision (institutional holdings, intra-day, 龙虎榜).
- **Value**: A-share factor data, more reliable historical NAV.
- **Integration**: `lib/data/tushare_client.py` mirrors `akshare_client.py` interface; `data/_manifest/` distinguishes sources.
- **Cost**: M.
- **Dependencies**: Tushare积分 (free tier may not suffice; user provides token via `.env`).

### T1.2 Multi-account aggregation
- **Trigger**: User opens ≥ 2 accounts (华泰 / 老虎 / 富途 / 盈透 / IBKR).
- **Value**: True cross-venue holdings; unified rebalance view.
- **Integration**: `account.yaml` schema gains repeated `accounts[]` with per-broker `available_venues`; `venue_check` learns inter-broker substitution.
- **Cost**: M (depends on broker API/CSV format).
- **Dependencies**: per-broker CSV export or API access (manual import OK first).

### T1.3 Self-owned backtest engine
- **Trigger**: Historical sanity_check insufficient; user wants to validate strategy variants beyond Spearman correlation.
- **Value**: Real subscription / redemption costs, taxes, slippage, walk-forward.
- **Integration**: `lib/backtest/`; reuses `data/local.duckdb` historical NAV; outputs `outputs/backtests/<run_id>/`.
- **Cost**: L.
- **Dependencies**: complete historical NAV in DuckDB (probably 6+ months ingest first).

### T1.4 US brokerage account enabled
- **Trigger**: User opens 老虎 / 富途 / 盈透 / Schwab; wants to buy GLD/IAU/VTI/VOO directly without QDII proxy or premium drag.
- **Value**: USD-denominated assets; gold currency diversification (today gold = 100% CNY); access to US-listed sector ETFs.
- **Integration**: `available_venues` adds `us_brokerage`; `trade_plan` prefers native targets over QDII proxies.
- **Cost**: M (mostly product mapping, not engineering).
- **Dependencies**: user opens account; FX channel established.

### T1.5 沪港通 direct HK ETF
- **Trigger**: User's financial assets ≥ ¥500k (Stock Connect threshold).
- **Value**: Buy 2800 / 2801 / 2828 etc. directly; lower premium than QDII.
- **Integration**: `venue_check` adds `cn_to_hk` substitution rule.
- **Cost**: S.
- **Dependencies**: 50万门槛.

---

## Tier 2 — Model / Signal Enhancement

### T2.1 Kronos sequence signal
- **Trigger**: MVP scoring baseline stable ≥ 1 month AND user wants short-horizon expected_return / dispersion features.
- **Value**: Sequence-model representations complementary to 5-factor scores; per-instrument predicted distribution.
- **Integration**: `scoring/factors/kronos_signal.py` exposes `kronos_features` dict (expected_return, forecast_dispersion, regime_confidence); plugs into `macro_fit` or `risk` as one sub-score; never the final decision layer (per Kronos repo's own caveat).
- **Cost**: L.
- **Dependencies**: GPU access (or paid inference); clean training data; finetuning + walk-forward harness.

### T2.2 Risk-factor model (Fama-French / Barra-like)
- **Trigger**: Want stricter risk decomposition than current `risk` factor; or correlation matrix drift requires factor-based explanation.
- **Value**: Style attributions (size / value / momentum / quality / volatility); factor-orthogonalized correlations.
- **Integration**: Extends `scoring/factors/risk.py`; new artifact `outputs/<date>/factor_exposures.json`.
- **Cost**: L.
- **Dependencies**: historical factor data (free options: Ken French data library; paid: Barra etc.).

### T2.3 Adaptive LLM router (cost / latency / quality A/B)
- **Trigger**: Manual `config/llm.yaml` task routing has been re-tuned ≥ 3 times without stabilizing.
- **Value**: Auto-pick provider × model on a per-task basis using collected telemetry.
- **Integration**: `lib/llm/gateway.py` adds router; `data/cache/llm_telemetry/` stores cost / latency / quality flags.
- **Cost**: M.
- **Dependencies**: ≥ 4 weeks of telemetry collected.

---

## Tier 3 — Agent / Decision Architecture

### T3.1 TradingAgents multi-role debate
- **Trigger**: MVP single-LLM memo synthesis stable ≥ 1 month AND user wants explicit bull / bear / risk dialogue.
- **Value**: 7-role chamber (Technical / Fundamental / News / Sentiment / Bull / Bear / Risk / PM); structured disagreement is auditable.
- **Integration**: Replaces `lib/memo/synthesizer.py`; LDR feeds the News analyst; Kronos (if enabled, T2.1) feeds Technical; outputs include per-role transcripts.
- **Cost**: L.
- **Dependencies**: LangGraph + checkpoint design; per-role system prompts; agent-level eval beyond memo eval.

### T3.2 Dexter-style interactive research agent
- **Trigger**: Need to query individual instruments in natural language; or expand to single-stock workflows where simple `irc ask` is too rigid.
- **Value**: Multi-turn deep-dive; natural-language screening; scratchpad-traced reasoning.
- **Integration**: Extends `lib/queries/`; new tool layer wrapping data + scoring + research; conversation logs to `outputs/dialogues/<thread_id>.md`.
- **Cost**: L.
- **Dependencies**: T1.4 US brokerage may be co-triggered (single-stock natural for US universe).

### T3.3 Individual stock analysis (US / A-share / HK)
- **Trigger**: Funds / ETFs / gold pipelines stable ≥ 3 months AND user wants active stock selection.
- **Value**: Active management space; broader research surface (filings, earnings, DCF, industry).
- **Integration**: New `asset_class: cn_stock / us_stock / hk_stock`; scoring gains earnings / valuation / industry-position factors; `discovery` adds filings-based screening.
- **Cost**: L.
- **Dependencies**: T1.1 Tushare for A-share fundamentals; T1.4 brokerage if direct buys intended.

---

## Tier 4 — Platform / Experience

### T4.1 InsForge / Postgres / backend
- **Trigger**: DuckDB + Markdown layer no longer scales (run history > 1 year, per-date Markdown unwieldy, want concurrent reads).
- **Value**: Persistent multi-device store; real-time queries; dashboard substrate.
- **Integration**: Replaces persistence layer; weekly memo becomes one dashboard view.
- **Cost**: L.
- **Dependencies**: data model stable for ≥ 6 months.

### T4.2 HTML dashboard
- **Trigger**: T4.1 done; want time-series visualization of metrics, scores, allocation drift.
- **Value**: At-a-glance comprehension; trend lines for eval baselines.
- **Integration**: New frontend (likely Next.js or htmx + FastAPI); reads InsForge.
- **Cost**: M.
- **Dependencies**: T4.1.

### T4.3 Email / Telegram notify + cron scheduler
- **Trigger**: Weekly manual run becomes friction.
- **Value**: Auto Monday 09:00 push of memo + trigger-fire alerts during week.
- **Integration**: `lib/notify/`; cron invokes `irc run`.
- **Cost**: S.
- **Dependencies**: SMTP / Telegram bot setup (user provides creds in `.env`).

### T4.4 Ollama local fallback
- **Trigger**: Both online LLM providers down AND user still wants to produce a memo, OR privacy-sensitive deployment.
- **Value**: Offline / private operation; eliminates external dependency for non-critical tasks.
- **Integration**: `config/llm.yaml` adds `ollama` provider with `base_url: http://localhost:11434`.
- **Cost**: M (local model selection, prompt re-tuning for smaller model).
- **Dependencies**: hardware capable of running 13B+ model.

### T4.5 macOS Keychain / 1Password CLI
- **Trigger**: Multi-device sharing OR deployment to a non-personal machine.
- **Value**: Secrets out of `.env`.
- **Integration**: `pydantic-settings` plugin to read keyring.
- **Cost**: S.
- **Dependencies**: keyring client availability per OS.

### T4.6 GitHub Actions CI
- **Trigger**: Want PR-time validation when collaborating.
- **Value**: Auto `irc eval architecture` + `irc eval scoring --backtest --quick` on every PR.
- **Integration**: `.github/workflows/eval.yml`.
- **Cost**: S.
- **Dependencies**: repo on GitHub; secrets via Actions repo settings.

### T4.7 Multi-user / auth
- **Trigger**: Want to share with family / friends with separate state.
- **Value**: Per-user `account.yaml` and `preferences.yaml`; role-based access.
- **Integration**: T4.1 InsForge auth module.
- **Cost**: L.
- **Dependencies**: T4.1.

---

## Tier 5 — Workflow / Content Depth

### T5.1 Filings / announcements watcher
- **Trigger**: T3.3 stocks enabled; need real-time earnings / filings / disclosures.
- **Value**: Earnings day, guidance, insider sales surface immediately into news layer.
- **Integration**: `lib/news/filings_watcher.py`; SEC EDGAR + 巨潮资讯 + HKEX news.
- **Cost**: M.
- **Dependencies**: T3.3.

### T5.2 Tax-aware trading
- **Trigger**: Capital base > ¥500k; tax drag becomes meaningful.
- **Value**: QDII dividend withholding awareness; ETF dividend reinvestment vs cash; CN equity "持有满 1 年免税" optimization (if applicable to fund types).
- **Integration**: `trades/tax_aware.py`; tax assumptions in `preferences.yaml`.
- **Cost**: M.
- **Dependencies**: detailed venue → tax-treatment mapping table.

### T5.3 Quarterly theme deep research
- **Trigger**: Weekly memo can't cover long-cycle themes (gold supercycle, Fed regime shift, China 14-五).
- **Value**: ~5000-word quarterly reports, citation-heavy, slow build of theme convictions.
- **Integration**: New artifact `outputs/quarterly/<theme>.md`; new LDR run with extended budget.
- **Cost**: M.
- **Dependencies**: LDR usage matured; user stable theme list.

---

## Out of Scope (Permanent — never enters Roadmap)

| Item | Reason |
|---|---|
| Real trade execution / broker integration | Compliance + responsibility risk; system stays advisory |
| Derivatives (options / futures) | Outside steady risk profile (10-20% drawdown band) |
| HFT / short-term / minute-level | Decision cadence (long-core + medium-rotation) doesn't fit |
| Prescriptive investment advice ("must buy / must sell") | Legal risk; system stays at "research memo" tone |
| Anti-bot scraping bypass for paid data | Legal + ethical risk; respect robots.txt and ToS |

---

## Cross-Tier Dependencies (visual)

```
T1.4 us_brokerage ──► T3.2 dexter_agent
                  └─► T1.3 backtest_engine (true USD costs)
                  └─► T2.1 kronos (if US universe)

T1.1 tushare ─────► T3.3 stocks
                └─► T2.2 risk_factor_model

T3.3 stocks ──────► T5.1 filings_watcher

T4.1 insforge ────► T4.2 dashboard
              └──► T4.7 multi_user

T2.3 adaptive_router needs ≥ 4w telemetry ←── T4.3 cron (drives volume)
```

---

## Adoption Triggers Summary

The Roadmap is **demand-driven**, not roadmap-driven. Do not pre-build. Track triggers in:

- `evals/<stage>/report.json` for stability triggers (T2.1 / T2.3 / T3.1).
- `event_log.json` failure clusters for source-failure triggers (T1.1).
- User-event signals (account opened, capital threshold reached) for venue triggers (T1.2 / T1.4 / T1.5).
- Storage / latency watermarks for platform triggers (T4.1).

When a trigger fires, escalate the corresponding entry from this Roadmap to a normal brainstorming + spec + plan cycle of its own.

---

**End of Roadmap.**
