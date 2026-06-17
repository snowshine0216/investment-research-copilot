# ADR 0018 — Monitor scoring: factor priors and weight/band governance

**Status:** Accepted for the **governance + prior-rationale half of M4 only** (2026-06-17).
The quantitative half of M4 (factor ablation, weight/band sensitivity, composite-vs-forward
calibration) is **explicitly Not Accepted** — deferred behind the evidence gate in *Consequences*.
**Builds on:** [ADR 0017 — monitor evidence isolation](0017-monitor-evidence-isolation.md).
**Relates to:** monitor-eval roadmap [§3.4 (eval documents, never auto-tunes)](../superpowers/specs/2026-06-16-monitor-eval-roadmap.md), §4 (`composite → bias` row), §5 (M4); M3 backtest spec [predictive-validity panel + review trigger](../superpowers/specs/2026-06-16-monitor-eval-m3-backtest-design.md).
**Source of truth:** [profiles.py](../../src/irc/monitor/profiles.py) (operative weights), [signal.py](../../src/irc/monitor/signal.py) (composite + gate), [trend.py](../../src/irc/monitor/trend.py), [factor_maps.py](../../src/irc/monitor/factor_maps.py), [news_factor.py](../../src/irc/monitor/news_factor.py).

## Context

`irc monitor` emits a daily per-fund directional bias (`ADD_BIAS | NEUTRAL | REDUCE_BIAS`) from
a five-factor renormalized composite. The mechanics are tested and the validation spine (M0–M3)
is built, but the *design itself* — why these five factors, why these weights, why these gate
thresholds and ±0.40 bands — was hand-chosen and unargued (roadmap §1, "the conviction gap").

Roadmap M4 ("algorithm justification") has two halves with different readiness:

- a **qualitative** half — the economic rationale for each factor and the composite design — that
  is **data-free and can be written today**; and
- a **quantitative** half — leave-one-out ablation IC, weight/band sensitivity, and
  composite-vs-forward calibration — that is **data-blocked** (roadmap §6 Block C "depends on
  Block B's outcome data").

This ADR records the qualitative half and, more importantly, the **governance posture** that
keeps the numbers honest until the quantitative half can run. It does **not** discharge M4.

## Decision

### D1 — Governance posture (the load-bearing decision)

The monitor's factor weights, gate thresholds, and bands are **human-owned and provisional**.
They are justified here by economic priors and **Accepted as priors**. The eval layer
**justifies and documents** them; it **never auto-tunes** them (roadmap §3.4). Closed-loop
calibration on the current sample (7 funds, days of forward history) is rejected as overfitting.

Correspondingly, the **quantitative calibration of these weights/bands is Not Accepted** — it is
withheld until the evidence gate in *Consequences* is met. Publishing a bias today asserts the
*design is a reasoned prior*, never that it is empirically validated; the daily report's
predictive-validity panel and the M3 review trigger keep that gap visible.

### D2 — Two governed weight surfaces; the config default block removed

Weights come from exactly two human-editable surfaces, **both now governed**:

1. **Per-profile base vectors** — `profiles.py` `PROFILES[profile].weights`, the default weight
   vector per analysis profile. The primary governance surface.
2. **Optional per-fund override** — `MonitorFundConfig.signal_weights` in `config/monitor.yaml`,
   overlaid on the base vector ([resolve.py](../../src/irc/monitor/resolve.py) `default_weights` →
   `compose_weights`). This is an **explicitly governed second surface**, not a free-for-all:
   `resolve.py` validates every override at config-load time (`_validate_override`) so it can only
   reweight factors the profile can **structurally fill** (`eligible_factors`), never go
   **negative**, and the composed vector must still **sum to 1.0** (`weights_sum_ok`) — otherwise a
   `ValueError` aborts the run. None of the seven funds currently carries an override, but the
   capability is governed rather than latent.

The earlier `config/monitor.yaml` `defaults.signal_weights` block was a **third, non-operative**
surface — `resolve.py` never read it for weights (only `signal_bands` and `minimum_confidence`), so
it silently diverged (it declared gold at `0.30/0.20/0.15/0.20/0.15` while the operative gold vector
is `trend 0.45 / macro_tilt 0.35 / heat 0.20`). **Decision — reconciliation landed (2026-06-17):**
that block, its `MonitorDefaults.signal_weights` schema field, and the template copy were removed,
so no silent third surface remains. Editing weights anywhere but the two governed surfaces above has
no effect.

### D3 — Per-factor economic priors

Weights below are the **operative per-profile vectors** (`profiles.py`), shown to make the priors
concrete; every number is **provisional** under D1. Eligibility (which profiles can fill a factor)
is structural — a profile never allocates weight to a factor it cannot fill, so a coverage-gate
miss is always a real evidence gap (ADR 0017 / roadmap §3). This invariant is **enforced**, not
merely assumed: a per-fund override that reweights a profile-ineligible factor is rejected at
config-load time (D2).

| Factor | Family (`_FAMILY_OF`) | Economic prior | Operative weights | Eligible profiles |
|---|---|---|---|---|
| **trend** | price-momentum | Trend/momentum persistence is among the most robust cross-asset anomalies; trend is the **only evidence-free, always-on, point-in-time-honest** leg → **gate-required** | gold 0.45 · qdii_global 0.35 · active_cn_equity 0.30 · qdii_china_us_internet 0.30 | all (needs ≥`minimum_observations`=251 NAV obs) |
| **valuation** | valuation | Mean-reversion counterweight to trend (surfaced as the `trend_valuation_conflict` divergence) | 0.20 | active_cn_equity, qdii_china_us_internet (needs a valuation anchor) |
| **heat** | crowding | Crowding / flow-reversal; **asymmetric** — overheated −1, calm only +0.3 → a risk flag, not a buy signal | gold 0.20 · others 0.15 | profiles with a heat signal |
| **macro_tilt** | news | Top-down regime / policy / rates tilt; highest where macro *is* the thesis (gold, QDII) | gold 0.35 · qdii_global 0.35 · active/internet 0.20 | needs **≥2 distinct macro/theme keys** (see D4) |
| **constituent** | news | Bottom-up idiosyncratic tilt via holdings look-through | 0.15 | look-through profiles with `constituent_news` |

Factor value maps (the priors made numeric): **trend** = `clamp(0.50·tanh(8·r60) + 0.30·ma_struct
+ 0.20·(−drawdown_250))` — 60-obs momentum, MA20/MA60 regime + slope, and a 250-obs drawdown
penalty ([trend.py](../../src/irc/monitor/trend.py)); **valuation** = cheap +1 … expensive −1
([factor_maps.py](../../src/irc/monitor/factor_maps.py)); **heat** = restricted&rapid −1,
restricted|rapid −0.5, else +0.3 (rapid = AUM Δ ≥ 20%); **news** (macro & constituent) =
`clamp(Σ wᵢ·impactᵢ·confᵢ)` with confidence `Σ(wᵢ·confᵢ)/Σwᵢ`
([news_factor.py](../../src/irc/monitor/news_factor.py)).

### D4 — Composite design priors

Composite = `round(Σ contributionᵢ, 4)` over **eligible-and-present** factors, each weight
**renormalized** by the available weight ([signal.py](../../src/irc/monitor/signal.py)). The
publish gate and bands encode these priors:

- **trend present** — refuse a directional call without the one evidence-free, always-on,
  hardest-to-game leg; this is what stops an all-news (LLM-driven, ungroundable-after-the-fact)
  bias from publishing.
- **≥2 factor families** (`_FAMILY_OF`: price-momentum / valuation / crowding / **news**) — no
  single-family conviction. Because `macro_tilt` and `constituent` both map to **news**, news
  alone can never clear this gate; a bias needs trend **plus** one of {valuation, crowding, news}.
  *Distinct from* the `macro_tilt` *eligibility* check, which counts **≥2 distinct macro/theme
  keys** within the news leg ([factors.py](../../src/irc/monitor/factors.py) `_macro`).
- **available_weight ≥ 0.60** — at least 60% of the profile's intended weight must be actually
  present, else the renormalized composite extrapolates from too thin a base.
- **confidence ≥ `minimum_confidence` (0.50)** — renorm-weighted item confidence must clear 0.50
  or the signal degrades to `low_confidence` (bias suppressed).
- **bands ±0.40** — a composite in [−0.40, +0.40] is `NEUTRAL`; only `|composite| ≥ 0.40` earns a
  directional bias. A wide neutral band is a deliberately high bar for a directional call on a
  noisy weekly signal.
- **divergence codes** (`trend_valuation_conflict`, `trend_macro_conflict`, `low_factor_agreement`)
  surface internal contradiction as **caveats, never suppressors**.

## Considered options

- *Rejected — closed-loop auto-calibration of weights/bands on accrued data.* The governing
  constraint (roadmap §3.4) and the sample reality (N=7, short history, multiple-testing) make
  data-driven tuning an overfitting trap. Weights stay human-owned; eval documents, never tunes.
- *Rejected — equal-weight all factors.* Ignores that trend is the only evidence-free / always-on
  leg and the highest-conviction empirical anomaly, and ignores profile-specific eligibility (gold
  has no valuation/constituent factor to weight).
- *Rejected — drop the gate, always publish a band-derived bias.* Would ship news-only or
  thin-evidence biases — exactly what the trend-required / ≥2-family / `avail ≥ 0.60` gate exists
  to prevent.
- *Rejected — one weight vector across all profiles* (the shape implied by the config
  `defaults.signal_weights` block). Profile eligibility is structural: a single vector would
  allocate weight to factors a profile cannot fill, defeating the "coverage miss = real evidence
  gap" invariant. Per-profile vectors in `profiles.py` are correct; the config block was the relic,
  since removed (D2).
- *Rejected — defer the whole of M4 until data accrues.* The governance posture (D1) and the
  source-of-truth hazard (D2) are real **today** and cheap to get wrong; recording them now
  prevents silent weight edits and premature "the model is validated" claims while Block C waits.

## Consequences

- **The numbers are provisional priors, not a validated calibration.** This ADR is a reasoned
  argument for the design, not evidence that it predicts forward NAV.
- **Quantitative re-evaluation gate (when the deferred half becomes Acceptable).** Revisit the
  ablation / sensitivity / calibration work only once **both**:
  1. `monitor_forward` has **statistically reportable forward evidence for the headline
     `publishable_bias_directional` metric** (it leaves `insufficient_data`; today the ledger is
     ~1–2 days old → `n=0`), with cross-sectional **`rank_ic` as *supporting* evidence where
     `defined_day_count ≥ MIN_DEFINED_DAYS=8`** — not `rank_ic` alone, which stays
     `insufficient_data` far longer; **and**
  2. **≥2 evidence-free factors are point-in-time reconstructable in the retro replay.** Today the
     retro backtest is **trend-only by construction** —
     [`_evidence_free_composite`](../../src/irc/monitor/eval/backtest.py) hard-nulls valuation,
     heat, macro, and constituent inputs — so leave-one-out IC across factors is impossible (you
     would be ablating a one-factor composite). Building valuation/heat as point-in-time
     reconstructable factors (roadmap OPEN v2.1) is a prerequisite; macro_tilt/constituent are
     evidence-based and cannot be reconstructed point-in-time at all.
  The only empirical read available today is the weak trend-only retro hit-rate (~0.54, wide CI) —
  cited here **only as a caveated footnote**, never as endorsement of any weight.
- **`monitor_forward` is the future evidence channel, never an auto-gate.** Sustained
  underperformance of the headline metric versus its random baseline fires the M3 **human-review
  trigger** (panel flag), which prompts a human to revisit these priors — it never suppresses a
  bias (`EVAL_GATED` is reserved for fresh structural/LLM FAILs, roadmap §5).
- **Reconciled — two governed weight surfaces, no silent third (D2).** *Resolved 2026-06-17.* The
  non-operative `config/monitor.yaml` `defaults.signal_weights` block (and the matching template
  copy) and its `MonitorDefaults.signal_weights` schema field were deleted. The two surviving
  surfaces — `profiles.py` per-profile base vectors and the per-fund
  `MonitorFundConfig.signal_weights` override — are both governed: `resolve.py._validate_override`
  rejects, at config-load time, any override that reweights a profile-ineligible factor or goes
  negative, and `weights_sum_ok` still enforces sum-to-1.0. There is no longer a config weight
  block to edit by mistake; `resolve.py` reads the config `defaults` only for `signal_bands` and
  `minimum_confidence`.
