# ADR 0019 — Monitor capital-flow factor: economic prior, weight governance, engine-version isolation

**Status:** Accepted as a **prior** (2026-06-18). Records the *design rationale* for the `flow` factor added by the per-stock drill-down spec; the **quantitative validation** of the new weight stays deferred behind ADR 0018's evidence gate (priors are justified, never auto-tuned). Pending implementation.

**Builds on:** [ADR 0017 — monitor evidence isolation](0017-monitor-evidence-isolation.md), [ADR 0018 — monitor scoring rationale + weight/band governance](0018-monitor-scoring-rationale-and-governance.md).

**Relates to:** #156 (bias is a research lean, not a buy/sell order), [ADR 0015 — `portfolio_action` emission contract](0015-portfolio-action-emission-contract.md) (the line monitor must not cross), [ADR 0014 — legulegu rate-limit handling](0014-legulegu-rate-limit-handling.md) (per-symbol fetch posture), [ADR 0012](0012-fundamental-led-equity-valuation.md)/[ADR 0009](0009-consensus-upside-degrade-to-none.md) (why the dual-track valuation guard is deferred). **Spec:** [`docs/superpowers/specs/2026-06-18-monitor-flow-stock-drilldown-design.md`](../superpowers/specs/2026-06-18-monitor-flow-stock-drilldown-design.md).

**Source of truth:** [profiles.py](../../src/irc/monitor/profiles.py) (operative weights), [factor_maps.py](../../src/irc/monitor/factor_maps.py) (`flow_score` band map), `src/irc/monitor/flow_fetch.py` + `holding_metrics.py` (data + aggregate), [signal.py](../../src/irc/monitor/signal.py) (`_FAMILY_OF`, divergence), [forward_score.py](../../src/irc/monitor/eval/forward_score.py) + [evals/monitor_forward/runner.py](../../evals/monitor_forward/runner.py) (engine isolation), [monitor_cmd.py](../../src/irc/commands/monitor_cmd.py) (`_ENGINE_VERSION`).

## Context

`irc monitor` emits a daily per-fund directional bias from a five-factor renormalized composite (ADR 0018). The valuation factor already collapses cached per-stock PE/PB into one fund state but discards the per-stock detail, and there is **no capital-flow signal** anywhere — the only crowding input is the restriction leg (`fund_purchase_em`). The user (risk-control lead) asked to ground the bias bottom-up in the top holdings' PB/PE **and** main-money net inflow, so that `ADD_BIAS` reads as a better-reasoned "buy lean" and `REDUCE_BIAS` as a "sell lean." Adding a factor and reweighting `active_cn_equity` is a change to a **governed weight surface** (ADR 0018 D2) and therefore requires a recorded economic prior (ADR 0018 D1). Three choices here are hard to reverse, surprising without context, and the product of real trade-offs.

## Decision

### D1 — Capital flow is a **separate, bullish-on-inflow** factor, never folded into `heat`

Main-money net inflow (主力净流入净占比, A-share) enters as its own `flow` factor, NOT as a leg of `heat`. **Economic prior:** sustained net inflow into a fund's top holdings is a *directional* accumulation signal (smart money adding) → positive score toward `ADD_BIAS`; net outflow → negative toward `REDUCE_BIAS`. This is the **opposite sign** to `heat`/crowding, whose prior is that *froth/restriction* is a contrarian negative. Folding inflow into heat would force one factor to carry two opposite-signed meanings and make the composite uninterpretable. Distinct factor, distinct family (`capital-flow`), distinct sign.

- *Rejected — fold into a redefined `heat`.* Avoids a 6th factor and reweight, but the crowding-bearish vs inflow-bullish sign clash is irreconcilable and defeats the "legible methodology" goal.

### D2 — Weight `.15` on `active_cn_equity`, carved from the lower-signal legs

`active_cn_equity` vector: trend `.30→.25`, **flow `—→.15`**, heat `.15→.10`, macro_tilt `.20→.15`; valuation `.20` and constituent `.15` **unchanged** (sum stays `1.0`). **Prior:** flow is a higher-signal, daily-fresh, *directional* crowding read than the restriction-only `heat` leg (which can only fire ±0.5 today, AUM-Δ deferred), so weight moves *from* heat toward flow; trend and macro give a little because the goal is to raise the **fundamental/flow** evidence share (valuation `.20` + flow `.15` = `.35`) so "cheap + inflow" genuinely drives the lean. Flow is **ineligible** on gold/qdii_global/qdii_china_us_internet (no A-share constituents) → `profile_ineligible`, no weight allocated (ADR 0018 D2: a profile never weights a factor it cannot structurally fill). Per-fund `signal_weights` overrides remain the governed second surface.

### D3 — Engine-version isolation: bump **and** a forward-eval reader filter

`_ENGINE_VERSION "1"→"2"` (the composite/bias semantics change). The bump alone is **insufficient** — today nothing reads `manifest_versions.engine`, so pre-flow (v1) and post-flow (v2) ledger rows would pool into one forward metric. The bump is therefore paired with a `score_forward(target_engine=…)` filter + `runner._target_engine` (max engine present, compared numerically) + `details.json.excluded_by_engine`. **Trade-off:** this sacrifices forward-ledger **continuity** across the change for honest **population isolation** — accepted, because pooling incomparable biases is worse than a reset (ADR 0018 D1 "keep the numbers honest"). A deliberate rollback is out of scope.

### D4 — Scope guardrails

- **Lean, not order (ADR 0015 line).** The flow grounding makes the lean better-*reasoned*; the drill-down board uses 偏多/偏空 language and explanatory "why," and MUST NOT emit imperative 买入/卖出, target weights, weight deltas, or a `portfolio_action`. Executable buy/trim/exit on held positions stays in the decision layer under ADR 0015.
- **Self-history valuation now; dual-track deferred.** Per-stock valuation is scored by self-history percentile; the 60/40 self-history + industry-cross-sectional dual-track and the "False Cheap" clamp are deferred to their own spec (industry-average data + ADR-0012/0009 fundamental signal is fund-level + dormant). Conflict-suppression and the flow-reversal sign-agreement guard are deferred with them as veto-class mechanisms judged together against forward evidence.
- **Isolation (ADR 0017).** Flow data is the monitor's OWN cache (`data/monitor/fund_flow/`); pure core, effects at edges; no opportunity output files read.

## Consequences

- The bias for the 7 `active_cn_equity` funds now reflects top-5 capital flow; the per-fund drill-down board exposes the PB/PE + flow that justify each lean. `flow` is N/A (no weight) on the 3 non-A-share-constituent funds.
- The forward ledger restarts its comparable population at engine `"2"`; pre-flow history is retained but excluded from v2 metrics (counted in `details.json`).
- The new weight vector is an **Accepted prior**, not an empirical optimum. The daily predictive-validity panel + M3 review trigger keep the conviction gap visible; ADR 0018's evidence gate still governs any future quantitative re-weighting (no auto-tune).
- Adds the per-symbol `stock_individual_fund_flow` fetch (~15-25 sequential CN calls/run, cached per day, free endpoint, paced per ADR 0014); a throttled symbol degrades to `flow_no_data` for the run, never a crash, and is retried on the next run (see the 2026-06-22 addendum — transient failures are no longer cached as confirmed misses).

## Addendum — D3 follow-up: the engine-drop WARN keys on the hit-rate headline, not `rank_ic` (2026-06-20)

D3 isolates the comparable forward population by engine version but leaves the **transition itself unattributed** — after an `_ENGINE_VERSION` bump the append-only ledger strands prior-engine rows, so the headline metrics go thin and the stage already shows `WARN`, but an operator can't tell *engine-reset thinness* from *general youth*. Follow-up 1 (spec `docs/superpowers/specs/2026-06-19-monitor-forward-engine-drop-warn-design.md`) adds an **attribution-only** `engine_population` diagnostic row that flips its `state` to `engine_transition` when the drop is the proximate cause. It **never changes `rc`** — it only WARNs when a headline metric is *already* `WARN`.

## Addendum — transient-resilient per-symbol cache contract (2026-06-22)

**Symptom.** On 2026-06-21 the flow factor was N/A for 6 of 7 `active_cn_equity` funds: the day's `fund_flow` cache held 30 symbols but only **5 `ok`** (the first fund's top-5) and **25 `miss`**; the per-symbol industry cache (`stock_industry`) was **60/60 miss**. EastMoney served the first handful of sequential calls, then throttled — the classic burst-then-block pattern (cf. ADR 0014 legulegu).

**Root cause.** Both per-symbol fetchers (`flow_fetch`, `industry_valuation.fetch_stock_industry_map`) collapsed **three** outcomes into two: a raised fetch (timeout / rate-limit / 5xx) was cached as `status:miss` — indistinguishable from a genuinely dead symbol — and the cache-first guard (`if symbol in cached: skip`) then made that miss permanent for the day. One throttle burst **poisoned** the cache; no same-day re-run recovered, and there was no backoff to survive the burst.

**Decision.** A shared edge — `src/irc/monitor/cached_fetch.py` — now distinguishes three outcomes:

- `ok` — parsed payload (incl. a legitimately empty one) → persisted, not re-fetched within the day.
- `dead` — confirmed absence (non-A-share line; or the endpoint answered with no usable field) → persisted as `miss`, never retried. **`miss` now means *confirmed dead*, not "any failure."**
- `transient` — the fetch **raised** → **never persisted** → retried on the next run, and retried within-run with bounded exponential backoff (0.5s → 1.5s). A **consecutive-transient circuit-breaker** (default 5) stops hammering an endpoint that has begun hard-blocking, leaving the remainder uncached for the next run.

**Trade-off.** A genuinely dead symbol is now re-probed across runs *only if* it raises (vs. answers-empty), a small extra call cost; in exchange a throttle event no longer silently zeroes a whole factor for the day. The market-wide `fetch_industry_pe` call already self-healed (failure → `{}`, uncached) and is unchanged. Recovering an already-poisoned day still requires deleting that day's cache file — the fix prevents future poisoning, it does not rewrite history.

**The non-obvious choice worth recording:** the trigger keys on **`publishable_bias_directional.state == "insufficient_data"` only, and deliberately EXCLUDES `rank_ic`.** A future reader will see only the hit-rate headline checked and reasonably try to "fix" it by also keying on `rank_ic` (the dominant post-bump low-n metric). **Do not.** `rank_ic` flaps into `"undefined"` whenever a run-date has `< MIN_CROSS` (4) defined funds — with a 7-fund monitor set that is ordinary cross-sectional sparsity, **unrelated to any engine bump**, and recurs indefinitely. Because `engine_mismatch > 0` is permanent in an append-only ledger, keying on `rank_ic` would make the attribution WARN re-fire forever on sparsity that has nothing to do with a transition — the exact permanent / false-attribution failure D3's isolation is meant to avoid. Keying on the hit-rate headline loses nothing at the *real* transition (right after a bump the matured target-engine population is ≈ 0, so the hit-rate headline is *also* thin and fires correctly) and clears monotonically as blocks accrue. `publishable_bias_directional` is chosen over `raw_composite_directional` because it is the *published* signal and matches the existing M3 review-trigger. *Rejected — `any`-over-all-three metrics: reintroduces the permanent false-attribution WARN via `rank_ic` flapping.*
