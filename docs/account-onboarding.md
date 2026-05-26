# Account onboarding — expanding venue reach

> **What this is.** A guide to growing `inputs/account.yaml` so the pipeline
> can suggest a wider universe of instruments. Until you do, many otherwise
> attractive rows will show up under **Blocked / Out of scope** in the
> decision report.
>
> **What this isn't.** Advice on which broker to choose. The pipeline is
> broker-agnostic; this doc just tells you which `available_venues` strings
> unlock which instrument families.

---

## Current default

`inputs/account.yaml` ships with:

```yaml
accounts:
  - broker: cmb
    currency: cny
    available_venues: [cmb_fund, cmb_gold]
```

This unlocks two channels:

- **`cmb_fund`** — off-exchange mutual funds bought via 招商银行 App
  (e.g. 003318 景顺长城中证500行业中性低波动指数A, 014502 泰信汇盈债券A,
  006809 泰康香港银行指数A).
- **`cmb_gold`** — 招商银行 paper-gold (账户金) account.

This does **not** unlock exchange-traded ETFs, HK-connect stocks, US
brokerage holdings, or QDII secondary-market premium signals.

---

## Adding `cn_brokerage` — A-share exchange ETFs

A `cn_brokerage` venue unlocks ~50+ exchange-traded ETFs the discovery
stage routinely surfaces: 沪深300 ETF (510300, 510330, 159919), 上证50 ETF
(510050), 中证500 ETF (510500), 标普500 ETF (513500, 513650, 159655),
纳指 ETF (159941, 513100, 513300, 159501), 国债 ETF (511010, 511260,
511020), 政金债 ETF (511520, 159650), 城投债 ETF (511220), 可转债 ETF
(511180, 511380), 黄金 ETF (518880, 159937, 159934, 518800, 518850),
央企创新 ETF (512960), 港股红利 ETF (159691, 513690).

### What you need

A mainland securities account at any 持牌券商. The lowest-friction add
for an existing CMB customer is **招商证券** (内嵌 in 招行 App for some
account types). Comparable alternatives: 中信证券, 华泰证券, 国泰君安,
平安证券, 东方财富证券, 富途 (HK-licensed, mainland-restricted features).

### Registration steps (typical)

1. Download the broker's App (招商证券 / 华泰证券 / etc.).
2. Open an A-share account (开户) — requires your ID card, a bank-card
   for the 三方存管 link, and a 5-minute video review during market
   hours.
3. Enable second-board permission if you also want 创业板 / 科创板 ETFs.

### Add to `account.yaml`

```yaml
accounts:
  - broker: cmb
    currency: cny
    available_venues: [cmb_fund, cmb_gold]
    holdings:
      - asset_class: gold
        form: paper_gold
        cost_basis_cny: 10000
  # NEW — your A-share brokerage:
  - broker: cms        # or whatever your broker code is (cms = 招商证券)
    currency: cny
    available_venues: [cn_brokerage]
    holdings: []
```

Then `uv run irc config validate` to confirm parsing.

After your next pipeline run the **Blocked — fixable today** section in
`decision_report.md` should shrink dramatically — the ~14 venue-blocked
ETF rows for 沪深300/中证500/纳指/标普500/国债/黄金 become reachable.

---

## Adding `hk_connect` — HK Stock Connect

The `hk_connect` venue unlocks HK-listed ETFs (港股红利, 港股科技, 港股 50)
and direct HK stocks (constituent lookthrough quality improves).

### What you need

A mainland securities account (the `cn_brokerage` above) **plus**
沪港通 / 深港通 permission:

- 50万 RMB minimum-asset threshold (regulator-imposed) measured as the
  20-day rolling average in your brokerage account.
- A separate risk-acknowledgement signed once in the broker's App.

### Add to `account.yaml`

Extend the brokerage row's venues:

```yaml
  - broker: cms
    currency: cny
    available_venues: [cn_brokerage, hk_connect]
    holdings: []
```

---

## Adding `us_brokerage` — direct US equities/ETFs

The `us_brokerage` venue unlocks direct US-listed ETFs (SPY, QQQ, etc.).
The pipeline's QDII feeders (017641 摩根标普500, 019172 摩根纳斯达克100,
161716 易方达全球美元债) are a substitute when this venue is unavailable.

### What you need

A US brokerage account: **Interactive Brokers (IBKR)**, **Charles Schwab**,
**TD Ameritrade** (now part of Schwab). For mainland-China residents,
IBKR and Saxo are the practical options; both require:

- Identity verification (passport).
- A funding source (typically wire transfer in USD).
- Tax declaration (W-8BEN for non-US residents).

### Add to `account.yaml`

```yaml
  - broker: ibkr
    currency: usd
    available_venues: [us_brokerage]
    holdings: []
```

---

## Verifying `cmb_gold` works

If `decision_report.md` still shows `cmb_paper_gold` as `blocked_no_proxy`
despite `cmb_gold` being in your venues, it likely means the universe
config's `cmb_paper_gold` row asks for a venue with a different name
(e.g. `cmb_paper_gold` instead of `cmb_gold`). Check
`config/universe/gold.yaml` line ~5:

```yaml
- { instrument_id: cmb_paper_gold, ..., venue_required: [cmb_gold] }
```

If the `venue_required` list shows a different code, either:

- Rename in the universe config (recommended — `cmb_gold` is the
  user-facing name), or
- Add the matching code to your `account.yaml`.

---

## Quick reference

| Venue string | Real-world account | Unlocks |
|---|---|---|
| `cmb_fund` | 招商银行 App fund channel | Off-exchange mutual funds (FOF, 主动股票/债券, 联接基金) |
| `cmb_gold` | 招商银行 paper-gold | `cmb_paper_gold` |
| `cn_brokerage` | Any 持牌券商 (招商证券/中信/华泰/…) | Exchange-traded ETFs (ETFs on SH/SZ) |
| `hk_connect` | 沪/深港通 permission via `cn_brokerage` | HK-listed ETFs + HK stocks |
| `us_brokerage` | IBKR / Schwab / Saxo | Direct US ETFs / stocks |

After every change to `account.yaml`, run:

```bash
uv run irc config validate          # parse + schema check
uv run irc run --from discover      # re-pick the watchlist with new venues
```

The new venue strings flow through to the venue-check in
`src/irc/trades/venue_check.py` and into the per-row `venue_compatible` /
`proxy_id` fields in `trade_plan.yaml`.
