# Preflight Spend / Balance Gate — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorm) → pending implementation plan
**Author:** pairing session (paid-token balance protection)

## Context

Several `.env` tokens require prepaid payment (DeepSeek, OpenRouter, Tavily, Brave,
Bocha, Jina, and the OpenBB data keys). A run that exhausts a balance mid-pipeline
fails partway and wastes work. Today there is **no preflight check**: `run_pipeline`
starts the stage loop immediately, and the only cost signal — `prompt_tokens` /
`completion_tokens` on `ChatResponse`, plus the dormant `CostEntry` type in
`src/irc/llm/cost_tracker.py` — is never persisted or aggregated.

We want a **preflight gate** that, before any paid work begins, estimates the run's
spend per provider and stops the run when a provider's balance cannot cover it. The
estimate is a **learned cost model** that starts from a conservative seed and
**converges toward real cost** as runs accumulate actual usage.

## 1. Goals

- Before a gated command does paid work, **estimate spend per provider** (in that
  provider's own unit) and compare it to that provider's **available balance**.
- **Hard-stop** (don't start the run, exit code `5`) only on a **confirmed
  insufficient** balance; never on an unreadable one.
- Cover **every paid provider a command will actually use** — DeepSeek + OpenRouter
  (LLM), Tavily/Brave/Bocha/Jina (search/extract), OpenBB FMP/Tiingo (data) — scoped
  per command to only the providers in play.
- Use a **per-task EWMA cost model** that begins at a deliberately-high seed and
  converges to observed cost as actual usage is recorded.
- For providers with **no queryable balance API**, track balance in a **local ledger**:
  a human-edited anchor file minus machine-counted usage.
- Keep pure cores (estimator, gate, EWMA, ledger math, scope) **unit-testable without
  mocks**; confine network/disk to thin edges.

## 2. Non-goals

- Not metering or capping *mid-run* spend — this is a **preflight** gate only.
- Not converting currencies — estimate vs. balance is compared **strictly within one
  provider's own unit**; never summed across providers, never FX-converted.
- Not auto-topping-up or calling any billing/payment API.
- Not reconciling ledger balances automatically for no-API providers (the user
  re-anchors by editing the balances file against the vendor dashboard).
- Not changing any stage's business logic or outputs.

## 3. Architecture

New package **`src/irc/spend/`** (named to avoid colliding with the existing *fetch
budget* concept in `opportunity` / `FetchBudgetExceeded`):

```
src/irc/spend/
  types.py        # frozen dataclasses (Section 4)
  pricing.py      # load config/spend_pricing.yaml → PricingTable; pure lookups
  profile.py      # load/save data/spend/usage_profile.json + pure EWMA update
  estimator.py    # PURE: (tasks-that-will-fire, profile, pricing) → {provider: CostEstimate}
  ledger.py       # PURE: (balances yaml, consumption json, clock) → effective balances
  gate.py         # PURE: (estimates, balances, margin) → GateDecision
  scope.py        # PURE: command/stage → in-scope tasks & providers (static map)
  probes/         # I/O: one BalanceProbe per provider behind a common protocol
  recorder.py     # I/O (Phase 2): per-run actuals → cost log → fold into profile + ledger
  preflight.py    # EDGE: probe in-scope providers, estimate, decide, print, return exit code
```

The estimator, gate, scope, pricing lookup, EWMA update, and ledger math are **pure**.
Only `probes/`, `recorder.py`, and `preflight.py` touch network/disk. Probes reuse the
existing `verify_host_resolves_publicly` SSRF guard and `resolve_proxy()` so
`IRC_HTTPS_PROXY` applies uniformly, exactly like `llm/http_client.py`.

### 3.1 Preflight data flow (every gated command's entry)

```
command scope ─→ scope.py ─→ tasks/providers that will fire
                                   │
                  profile.json ────┼──→ estimator.py ──→ {provider: estimated spend (own unit)}
                  pricing.yaml ────┘                              │
                                                                  ▼
   in-scope providers ──→ probes/* (API)    ─┐
                       ──→ ledger.py (no-API) ┴─→ {provider: balance} ──→ gate.py
                                                                            │
                       balance < estimate × margin  (or is_available=false,
                       or ledger negative)?  ── yes → print table, exit 5 (don't start)
                                                no / unreadable → print, proceed
```

### 3.2 Convergence data flow (Phase 2, after a run)

```
LLM calls ──(actual prompt/completion tokens per task)──┐
search/extract calls ──(query/page counts per provider)─┤
                                                         ▼
                            run end ──→ recorder.py ──→ EWMA fold → usage_profile.json
                                                   └──→ decrement → consumption.json
```

## 4. Data contracts (`src/irc/spend/types.py`, frozen dataclasses)

```python
@dataclass(frozen=True)
class TaskUsage:                       # learned profile entry, keyed by llm.yaml task name
    task: str
    avg_calls_per_run: float
    avg_prompt_tokens: float           # mean per call
    avg_completion_tokens: float       # mean per call (DeepSeek completion already includes reasoning)
    samples: int                       # 0 ⇒ fall back to seed

@dataclass(frozen=True)
class UsageProfile:
    tasks: Mapping[str, TaskUsage]
    alpha: float                       # EWMA smoothing, default 0.3

@dataclass(frozen=True)
class CostEstimate:
    provider: str
    currency: str                      # "CNY" | "USD" | "credits" | "tokens"
    amount: float                      # estimated spend in the provider's own unit
    breakdown: Mapping[str, float]     # task/leg → amount, for the printed table

@dataclass(frozen=True)
class BalanceReading:
    provider: str
    currency: str
    amount: float | None               # None ⇒ unreadable → never hard-stops
    available: bool                    # provider's own flag (e.g. DeepSeek is_available)
    source: str                        # "api" | "ledger" | "probe_failed" | "no_balance_api"

@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    estimate: float | None
    balance: float | None
    status: str                        # "ok" | "blocked" | "warning" | "info"
    detail: str

@dataclass(frozen=True)
class GateDecision:
    blocked: tuple[ProviderVerdict, ...]   # confirmed insufficient → exit 5
    warnings: tuple[ProviderVerdict, ...]  # unreadable / skipped → proceed
    ok: tuple[ProviderVerdict, ...]
```

## 5. The cost-estimation model

### 5.1 Unit of estimation

The **`llm.yaml` task name** (e.g. `memo_synthesis`, `scoring_rationale`). A task maps
1:1 to a model, hence to pricing, and matches `CostEntry.task`. A stage's estimate is
the sum of its tasks; the run's estimate is the sum of its stages.

### 5.2 Pricing config (`config/spend_pricing.yaml`)

Prices are **config, never inlined in code**; real values are verified against each
provider's pricing page at implementation time. Top-level `margin` (default **1.2**),
also overridable via `IRC_SPEND_MARGIN`.

```yaml
margin: 1.2
llm:
  deepseek:
    currency: CNY
    models:
      deepseek-chat:     { input_per_mtok: 2.0, output_per_mtok: 8.0 }
      deepseek-reasoner: { input_per_mtok: 4.0, output_per_mtok: 16.0 }
  openrouter:
    currency: USD
    models: { }                       # per-model rates, filled at implementation
search:
  tavily: { currency: credits, per_query: 1 }
  bocha:  { currency: CNY,     per_query: 0.03 }
  jina:   { currency: tokens,  per_page: 1000 }
quota:                                # tier 3 — no estimate; remaining-quota only
  brave:      { unit: monthly_queries }
  openbb_fmp: { unit: daily_calls }
  tiingo:     { unit: hourly_requests }
```

### 5.3 Seeded usage profile

`data/spend/usage_profile.json` is global (accumulates across all runs, **not**
date-partitioned), atomic-written via the repo's `.tmp.{pid} → os.replace` pattern.
A cold profile (`samples == 0` for a task) uses **deliberately-high seed defaults** so a
fresh install over-estimates (the safe direction for a "do I have enough?" gate). Seeds
live alongside pricing (`config/spend_pricing.yaml` or a sibling `spend_seed.yaml`).

### 5.4 EWMA convergence (pure, `profile.py`)

```
new_value = α · observed_this_run + (1 − α) · old_value        # α = 0.3 default
```

applied independently to `avg_calls_per_run`, `avg_prompt_tokens`,
`avg_completion_tokens`; `samples += 1`. With `samples == 0` the estimator ignores the
zeroed entry and uses the seed.

### 5.5 Per-task / per-provider estimate (pure, `estimator.py`)

```
task_cost = avg_calls_per_run · (avg_prompt_tokens · input_price
                                 + avg_completion_tokens · output_price) / 1e6
provider_estimate = Σ task_cost   over tasks routed to that provider whose stage is in scope
```

**Conservative cache bias:** DeepSeek bills cache-hit input tokens cheaper, but the
estimator prices *all* prompt tokens at the cache-miss rate — a deliberate
over-estimate, the safe direction for the gate.

## 6. Local balance ledger (no-API providers)

Providers without a queryable balance endpoint (Tavily, Bocha, Jina, Brave) track
balance locally, split so the **human edits exactly one file** and the machine's
subtraction lives in a separate file the human never opens.

### 6.1 Human-owned anchor — `config/spend_balances.yaml`

Machine **never writes** this; comments/formatting always survive. Edit on top-up.

```yaml
# Edit when you top up. Machine only reads this. Effective balance =
# this number minus usage the machine counted since `as_of`.
tavily: { balance: 950,     as_of: 2026-06-01 }   # credits
bocha:  { balance: 30.00,   as_of: 2026-06-01 }   # CNY
jina:   { balance: 1000000, as_of: 2026-06-01 }   # tokens
brave:  { quota: 2000, reset: monthly, reset_day: 1 }   # quota, not a wallet
```

### 6.2 Machine-owned consumption — `data/spend/consumption.json`

Machine-managed, human never edits. Tracks usage counted since the anchor.

```jsonc
{
  "tavily": { "consumed_since": 41,  "since": "2026-06-01" },
  "brave":  { "consumed_this_period": 380, "period_start": "2026-06-01" }
}
```

### 6.3 Effective-balance math (pure, `ledger.py`)

Two flavors:

| Flavor | Providers | Human sets | Machine does | Effective remaining |
|---|---|---|---|---|
| Wallet | Tavily, Bocha, Jina | `balance` + `as_of` (edit on top-up) | subtract usage since `as_of` | `balance − consumed_since` |
| Quota  | Brave | `quota` + `reset` (set once) | subtract usage; auto-reset each period | `quota − consumed_this_period` |

- **Re-anchor:** if the human's `as_of` is later than the machine's stored `since`, the
  machine resets `consumed_since = 0, since = as_of`. Topping up = edit the number + date.
- **Auto-reset (quota):** at gate-time the clock (supplied by the effect layer, same as
  `_china_today()` — never `Date.now()` inside pure code) is compared to `period_start`;
  when the calendar has rolled past `reset_day`, the machine zeroes `consumed_this_period`
  and advances `period_start`. Nothing to remember.
- A ledger balance is fed to `gate.py` exactly like a probed one, so **Tavily/Bocha/
  Jina/Brave get a real hard-stop**, not just a warning. **Negative balance ⇒ insufficient
  ⇒ block** + prompt to re-anchor `config/spend_balances.yaml`.

`irc spend status` is an **optional** read-only convenience (show effective balances
across all vendors, triggering quota auto-reset computation). Not required — the YAML is
human-readable.

## 7. Provider probes (`src/irc/spend/probes/`)

```python
class BalanceProbe(Protocol):
    provider: str
    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading: ...
```

A registry maps `provider → probe`; `preflight.py` invokes a probe only for an in-scope
provider whose key is set. Each probe wraps one SSRF-guarded, proxy-aware HTTPS GET,
parses, and returns a `BalanceReading`. Retry reuses the tenacity patterns in
`llm/retry.py`; on retry-exhaustion it returns `amount=None, source="probe_failed"`.

| Provider | Endpoint | Tier | Status |
|---|---|---|---|
| DeepSeek | `GET /user/balance` → `is_available` + `total_balance` (CNY) | prepaid money | **confirmed** |
| OpenRouter | `GET /api/v1/key` → `limit_remaining` (or `/credits`: total − usage, USD) | prepaid money | **confirmed** |
| Jina | dashboard key endpoint → token balance | prepaid tokens (ledger) | verify; else ledger-only |
| Tavily | usage endpoint → plan/used/limit (credits) | prepaid credits (ledger) | verify; else ledger-only |
| Bocha | prepaid RMB balance | prepaid money (ledger) | verify; else ledger-only |
| Brave | monthly plan quota | quota (ledger) | no preflight API → ledger only |
| OpenBB FMP / Tiingo | plan rate-limit | quota | no prepaid balance → warn-skip |

If a "verify" provider exposes a usable live endpoint, its probe supplements the ledger;
otherwise the **ledger is authoritative** for that provider. OpenBB/Tiingo are
rate-limits, not depletable balances — they remain best-effort **warn-skip**.

## 8. Gate logic & per-command scope

### 8.1 Gate (`gate.py`, pure)

For each in-scope provider:
- estimate present **and** `balance.amount is not None`: **block** if `available is False`
  **or** `balance.amount < estimate.amount × margin`; else **ok**.
- `balance.amount is None` (probe_failed / no_balance_api): **warning**, proceed.
- quota-tier with neither estimate nor balance: **info** line only.

### 8.2 Scope (`scope.py`, pure static table)

Each gated command declares the tasks + non-LLM legs it will fire. For `run`, a provider
is included **only when its code path is actually active** in that invocation (search
providers iff `research` runs; OpenBB iff active ingest legs use it).

| Command | LLM tasks | Other paid legs |
|---|---|---|
| `run` | union of tasks for stages that will actually run (after `RESEARCH_ENABLED` filtering) | search providers iff `research` runs; OpenBB iff active |
| `opportunity` | `thesis_falsify`, `thesis_defend` | — |
| `memo` | `memo_synthesis`, `memo_audit` | — |
| `ask` | `interactive_query` | — |
| `eval-funds` / `narrative --analyze` | per-fund eval tasks | — |
| `decision` | *(verify call sites)* | — |

The exact `STAGE_TASKS` / command→task rows are confirmed at implementation by grepping
each stage's `call(...)` sites. A completeness test (mirroring `test_stage_names_complete`)
asserts **every `llm.yaml` task maps to ≥1 command scope**, so a future task can't
silently escape the gate.

## 9. Error handling (consolidated)

- Probe fails → retry → `amount=None` → **warn + proceed**.
- No balance API → ledger-tracked providers are still gated via the ledger; only
  OpenBB/Tiingo truly **warn-skip**.
- Confirmed insufficient (`balance < estimate × margin`, or `is_available=false`, or
  **ledger negative**) → **block, exit 5**, print a table (provider, estimate, balance,
  shortfall, source).
- Optional providers are only in-scope when their key is set (no key ⇒ not probed).
- Missing `spend_balances.yaml` / `consumption.json` → treat as unknown / zero with a
  warning; **malformed** config → fail loud at load, folded into `irc config validate`.
- The gate runs **before** the stage loop; a block writes **no** resume state (nothing
  started) — it just refuses to start with a clear message.

## 10. Phasing

### Phase 1 — working gate, seeded estimate (ships usable)

- `src/irc/spend/` package: `types.py`, `pricing.py` + `config/spend_pricing.yaml`,
  `scope.py`, `estimator.py` (seed-only), `ledger.py`, `gate.py`, `probes/` (DeepSeek +
  OpenRouter confirmed; Jina/Tavily/Bocha verify-or-ledger), `preflight.py`.
- Ledger **read** path: `config/spend_balances.yaml` + `data/spend/consumption.json` →
  effective balance. With no recorder yet, consumption is empty, so effective = the
  human anchor; ledger providers are gated from day 1 against the seed estimate.
- Wire `preflight_gate(...)` into `run_cmd` (before the stage loop) and the other gated
  commands; block → print table, exit `5`.
- Seed usage profile deliberately high (overestimate-safe).

### Phase 2 — convergence + auto-decrement

- `recorder.py`: during a run, capture LLM token actuals per task **and** non-LLM
  query/page counts per provider; at run end fold into `usage_profile.json` (EWMA) and
  update `consumption.json` (wallet decrement / quota period-counter with auto-reset).
- Recorder hooks at the `commands/<stage>_cmd.py` edges (stages return usage; the command
  writes it — I/O at the edge, no globals).
- `estimator.py` switches from seed-only to **learned profile with seed fallback**
  (`samples == 0` → seed).

## 11. Testing (TDD, pure cores first)

- **No-mock unit tests:** estimator (seed + learned); gate block/warn/ok matrix; EWMA
  convergence (feeding actuals moves the estimate toward observed); ledger
  effective-balance (wallet decrement; quota **auto-reset across a month boundary with an
  injected clock**; re-anchor reset); scope completeness (every `llm.yaml` task maps);
  and an acceptance test that **currency is never crossed**.
- **I/O boundary:** probe parsers against recorded JSON fixtures (httpx `MockTransport`);
  live double-gated tests (`IRC_RUN_LIVE_BALANCE=1` + a `pytest.mark` marker) hitting real
  DeepSeek/OpenRouter endpoints.
- **Integration:** `run_pipeline` refuses to start (exit 5) on injected-insufficient
  balance, and proceeds-with-warning on probe failure; recorder round-trip updates both
  profile and ledger.

## 12. Open items for implementation

- Verify the live balance/usage endpoints + JSON shapes for Jina, Tavily, Bocha; any that
  lack a usable preflight endpoint fall back to **ledger-only**.
- Fill real per-model / per-query prices in `config/spend_pricing.yaml`.
- Confirm `decision` / `eval-funds` / `narrative --analyze` task sets by grepping
  `call(...)` sites.
- Choose the seed magnitudes (high enough to over-estimate a cold run without being
  absurd).
- Decide whether `config/spend_balances.yaml` ships a committed `.example` and is
  gitignored (it holds user-specific operational state, not secrets).
```
