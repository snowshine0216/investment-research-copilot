# Fundamental ("funding") Analysis — Review & Enhancement Plan

> Date: 2026-05-31 · Reviewer: AI analysis pass · Scope: how IRC analyzes company/constituent
> fundamentals, benchmarked against trading-research patterns collected in `snow-knowledge-database`.

## TL;DR

IRC's fundamental layer is a **clean, auditable thesis-direction engine**, not a valuation engine.
It looks *through* an index/fund to its top-N constituents, reads each one's latest-quarter YoY
numbers + broker sentiment, and votes a `thesis_state`. That is a genuine strength (deterministic,
cited, multi-source) but it answers "is the long-term logic still alive?" — **not "is this cheap?"**
The highest-ROI improvements all close the valuation/quality gap using data IRC *already fetches*.

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

1. **Use the data you already fetch.** Wire `target_price` into a consensus upside metric; add
   `pe`/`pb` from AkShare (`stock_a_indicator_lg` / `stock_individual_info_em`). Few hours; adds the
   missing valuation axis immediately.
2. **Add a fundamental `valuation_state`.** Today `intact` ignores price. Gate `core_dca` on
   cheap-AND-intact. `opportunity/states.py` already supports a 4-dimension classification — it just
   needs a fundamental valuation input.
3. **Make the CN data layer pluggable** (OpenBB/Hermes lesson). Add Tushare as fallback/primary; the
   `tushare_token` stub already exists. Bonus: Tushare/RiceQuant give **point-in-time** financials
   that AkShare lacks — important if scoring is ever validated against forward returns.
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
