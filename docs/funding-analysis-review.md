# Fundamental ("funding") Analysis — Review & Enhancement Plan

> Date: 2026-05-31 · Reviewer: AI analysis pass · Scope: how IRC analyzes company/constituent
> fundamentals, benchmarked against trading-research patterns collected in `snow-knowledge-database`.

## TL;DR

IRC's fundamental layer is a **clean, auditable thesis-direction engine**, not a valuation engine.
It looks *through* an index/fund to its top-N constituents, reads each one's latest-quarter YoY
numbers + broker sentiment, and votes a `thesis_state`. That is a genuine strength (deterministic,
cited, multi-source) but it answers "is the long-term logic still alive?" — **not "is this cheap?"**
The highest-ROI improvements all close the valuation/quality gap using data IRC *already fetches*.

## Progress update (2026-06-05)

Since this review, the **valuation axis** (recommendations 1–3 below) has largely been built. The
review's headline gap — "no valuation at all" — is now closed for index-tracking vehicles and, in
shadow mode, for active funds:

- **ADR 0012 — fundamental-led equity valuation (landed, live).** Index/ETF funds now get a
  `valuation_percentile_fundamental` from the index PE-TTM history (`self_history_percentile`, a
  120-point/180-day maturity gate, PB corroborate-only, a price-vs-fundamental divergence advisory).
  This feeds the existing `classify_valuation → valuation_state` axis, so `core_dca` already gates on
  cheap-AND-intact for indexable vehicles. ADR 0009 added the degrade-to-None discipline for the
  consensus-upside input (the `target_price` wiring of recommendation 1).
- **Phase D PR1 — active-fund holdings look-through (landed, shadow mode, flag OFF).** Active CN
  equity funds (no `tracked_index`) reconstruct a **current-basket harmonic PE/PB series** from their
  top-N A-share holdings' per-stock valuation history and percentile it into the *same*
  `valuation_percentile_fundamental` slot. New pieces: `fundamentals/akshare_stock_valuation.py` +
  `tushare_stock_valuation.py`, the `stock_valuation_history` table + ingestor, the dedicated
  `irc fundamentals stock-valuation` command, the pure `opportunity/lookthrough_valuation.py`
  aggregation core, a flag-gated `inputs_loader` branch, and the `irc lookthrough-diff` review
  report. Behind `active_fund_lookthrough.enabled` (default `false`) — production is byte-identical
  until the flag flips. **Remaining (human/PR2):** gate #4 (live-symbol column confirmation), gate #5
  (review the diff report + choose the final `coverage_floor`), then PR2 flips the flag and writes the
  ADR 0012 addendum + CONTEXT.md "Valuation inputs".

Endpoint correction worth recording: recommendation 1 suggested AkShare `stock_a_indicator_lg` for
per-stock PE/PB — that endpoint is **not present in the locked AkShare 1.18.60**. The implementation
uses EastMoney `stock_value_em` (one call returns the full daily PE(TTM)/市净率 history), with Tushare
`daily_basic` as a per-stock fallback (recommendation 3 — the CN data layer is no longer
single-sourced for the valuation leg, and the `tushare_token` plumbing is now real for this path).

**Still open** (unchanged by the above): balance-sheet quality (weakness 2), earnings quality /
accruals (3), backtest / validation (6), LLM-synthesis claim-checking (7), the `key_ratios` surface
(recommendation 4), and the bull/bear debate (recommendation 5). PE/PB only — no EV/EBITDA, PEG, DCF,
or FCF yet.

## What the code actually does

The fundamental reasoning lives in two places:

- `src/irc/fundamentals/` — fetches constituent financials: `akshare_filing.py` (CN revenue/NI YoY,
  gross margin, 券商研报 broker ratings), `edgar_client.py` (US 10-K/10-Q), `hkex_client.py` (HK),
  `snapshot.py` (top-N constituent registry + caching).
- `src/irc/opportunity/thesis_evidence.py` — the classifier:

```python
# _classify_state(pct_pos, pct_neg, consensus)
if pct_neg >= 0.60:                                       -> "falsified"
if pct_pos >= 0.60 and pct_neg < 0.30 and consensus >= 0: -> "intact"
if pct_neg >= 0.30 or consensus < 0:                      -> "under_pressure"
else:                                                     -> "evidence_insufficient"
```

`pct_pos`/`pct_neg` = share of constituents with positive/negative **revenue YoY**; `consensus` =
sum of broker-rating sentiment (买入/增持/卖出 → +1/0/−1 via regex). Evidence = up to 3 filings
(largest YoY moves) + 2 recent broker reports + 2 theme-research citations, each a content-addressed
citation (`fundamentals/types.py:54-135`). The LLM (`thesis_falsify`, deepseek-reasoner) is used to
*adversarially question* the derived state — not to generate it.

## Strengths

| Strength | Where | Why it matters |
|---|---|---|
| Deterministic, auditable core | `thesis_evidence.py:330+` | thesis state from rules, reproducible & testable |
| Citation accountability | `fundamentals/types.py:54-135` | every claim is a SHA256-addressed citation; no orphan claims |
| Multi-source convergence | filings + broker + theme research | can detect divergence (good earnings, bearish broker → `under_pressure`) |
| Look-through transparency | `snapshot.py:56-142` | reasons at constituent level ("贵州茅台 +6.3% rev YoY [cite]") |
| **LLM as skeptic, not oracle** | `thesis_falsify` task | the single best design choice; mirrors a bull/bear debate |
| Strong TDD / test coverage | ~257 test files | rare discipline for a personal finance tool |

## Weaknesses / gaps (for rigorous fundamentals)

1. **No valuation at all** — no PE / PB / EV-EBITDA / PEG / DCF / FCF. Measures *growth direction*,
   never *what you pay*. A stock can be `intact` (revenue up) and a terrible buy at 80× earnings.
   — 🟡 **Largely addressed** (PE/PB only): ADR 0012 (index funds, live) + Phase D PR1 (active funds,
   shadow→PR2). See "Progress update". EV/EBITDA, PEG, DCF, FCF still absent.
2. **No balance-sheet quality** — no debt/equity, current ratio, ROE/ROIC, interest coverage.
3. **No earnings quality / accruals** — a +50% revenue from an acquisition looks identical to organic.
4. **`target_price` fetched but never used** (`fundamentals/types.py:182`) — free consensus
   upside/downside is collected and thrown away.
5. **Hardcoded, staleness-dated QDII constituents** (`snapshot.py:100-130`, literally
   `# STALENESS_AFTER: 2026-08-16`) — silently wrong if the manual quarterly refresh is skipped.
6. **No backtest / validation anywhere** — the 5-factor weights in `config/scoring.yaml` are hand-set;
   no evidence the scoring predicts returns.
7. **Hallucination risk** in `research/synthesize.py` — LLM theme synthesis isn't validated against
   whether claims actually appear in the cited sources.
8. **CN data single-sourced on AkShare→EastMoney** with no fallback (US/HK have OpenBB fallback;
   CN does not). `tushare_token` is a stub in `settings.py`.
   — 🟡 **Partially addressed**: the per-stock **valuation** leg (Phase D) now has a Tushare
   `daily_basic` fallback behind EastMoney, with real token plumbing. The **filings** leg
   (`akshare_filing.py`) is still single-sourced.

## Enhancements — mapped to ideas already in the knowledge base

| Gap | Idea to steal | Source note (`snow-knowledge-database`) |
|---|---|---|
| No structured fundamental tools (ratios, statements, screening) | tool-decomposition over a financials API (`key_ratios`, `segments`, NL screener) | `agent-frameworks/dexter.md` |
| No valuation/quality discipline | analyst checklist: pillars/risks/catalysts/conviction + value/growth/quality screens | `claude/financial-services.md` |
| Thin single-pass thesis | bull-vs-bear researcher debate before a verdict | `agent-frameworks/tradingagents.md` |
| Single-sourced CN data | provider-agnostic data layer with fallback; add Tushare | `dev-tools/openbb.md`, `agent-frameworks/hermes-agent-vs-openbb.md` |
| No predictive signal / backtest | K-line foundation model + Qlib walk-forward backtest | `ai-engineering/kronos.md` |
| Unvalidated LLM synthesis | scratchpad / evidence-trail so every claim is link-checkable | `agent-frameworks/dexter.md`, `rag-and-knowledge/local-deep-research.md` |

## Recommended changes (priority order)

1. **Use the data you already fetch.** ✅ **Done.** `target_price`→consensus upside wired (item 002 /
   ADR 0009 degrade-to-None); per-stock PE/PB added via ADR 0012 + Phase D. *Endpoint correction:*
   `stock_a_indicator_lg` is not in AkShare 1.18.60 — the build uses EastMoney `stock_value_em`.
2. **Add a fundamental `valuation_state`.** ✅ **Done** (index path live; active-fund path shadow
   pending PR2). The fundamental percentile now flows through `classify_valuation → valuation_state`,
   and `core_dca` gates on cheap-AND-intact via the existing 4-dimension compose.
3. **Make the CN data layer pluggable** (OpenBB/Hermes lesson). 🟡 **In progress** — Tushare
   `daily_basic` is now the per-stock-valuation fallback (Phase D). Extending the fallback to the
   filings leg and point-in-time financials remains. The `tushare_token` plumbing is now real.
4. **Borrow Dexter's `key_ratios` surface.** A deterministic `compute_ratios(financials) ->
   {roe, debt_equity, gross_margin, fcf_yield}` closes the balance-sheet/earnings-quality gap with no LLM.
5. **Add bull/bear debate** behind an optional `--adversarial` flag on the opportunity stage. The
   `thesis_falsify` half exists; add a `thesis_defend` half and let them argue (TradingAgents pattern).

## Scope boundary (important)

Do **not** bolt trading (signals, backtests, ML factors) onto IRC. IRC's job is low-frequency
fund-DCA + thesis discipline. A-share ML quant is a different problem shape (daily cross-sectional
ranking, backtest rigor, transaction-cost modeling) and now lives in the separate **`ashare-quant`**
repo. The clean contract: ashare-quant *exports a per-instrument signal*; IRC *consumes it as one
more feature* behind its decision layer — exactly the Kronos pattern (a model signal is an input,
never the buy/sell decision).
