# Monitor Eval — M3 (Block B · Predictive Validity) Design

**Status:** Draft for review — rev 6 (2026-06-16)
**Parent:** [2026-06-16 monitor-eval roadmap](2026-06-16-monitor-eval-roadmap.md) (Block B, milestone M3) · builds on [2026-06-16 monitor-eval M0–M1 design](2026-06-16-monitor-eval-m0-m1-design.md)
**Owner:** Xue Yin
**Relates to:** [CONTEXT.md](../../../CONTEXT.md) "Monitor set" · ledger writer [forward_log.py](../../../src/irc/monitor/eval/forward_log.py) · [returns.py](../../../src/irc/monitor/returns.py) · eval surface [registry.py](../../../evals/_shared/registry.py) · [report_schema.py](../../../evals/_shared/report_schema.py) · [status.py](../../../evals/_shared/status.py)

This spec details **M3 only**. M4 (factor ablation, weight/band sensitivity, the economic-rationale ADR) stays in the roadmap. Where the roadmap or the M0–M1 spec already decided a contract (forward-ledger row §3.2b, idempotency §3.2d, `latest_stage_report`, `StageReport`), this spec gives the concrete M3 interfaces and reuses those.

> **Design provenance.** Nine review rounds shaped this spec; the resolutions are in the appendix.
> Load-bearing fixes: NAV source separated from the signal ledger; **three dates explicitly
> separated** (`as_of_date` feature cutoff / `run_date` publication / `entry_nav_date` strict `>`);
> **momentum baseline capped at `as_of_date`**; **random baseline grouped by `run_date`**; bad-nav
> handled as row-level exclusion; **null-ledger rows pre-filtered** before maturity check;
> `nav_history` producer appends a **bounded tail only** (not the full series); report-history via
> **`StageReportEntry` wrapper** so `artifact_date` is explicit; staleness on artifact-date; review
> trigger with **ISO-week dedup**; Spearman returns `None` only for **constant** ranks (not all ties);
> random baseline also excluded when all labels are **identical**; block-bootstrap H is a run-date
> count; retro vs forward directionally analogous, not directly comparable.
> Rev 5 (round 8): **retro replay clock** made explicit (sampling grid + retro `as_of_date` /
> `run_date` / `entry_nav_date` analogues, truncated input window, strict-`>` entry); review trigger
> driven by the **headline `publishable_bias_directional` random delta loaded from `details.json`** at
> the edge; **per-metric `details` schema** (Rank-IC carries no momentum/buy_hold baselines);
> **`MIN_DEFINED_DAYS` wired into Rank-IC status** (1–7 defined days ⇒ WARN `insufficient_data`);
> `latest_per_nav_date` gains a **final last-line-wins tiebreak**; **momentum baseline-unavailable**
> exclusion (`momentum_undefined`) when the `<= as_of_date` slice has too few observations.

---

## 1. Scope

M3 answers roadmap layer **B — predictive validity**: *does the bias predict forward NAV?* Two halves
under one offline eval stage `evals/monitor_forward`:

- **Retro backtest** — replays the **evidence-free sub-composite** (`compute_signal` with the
  evidence-based factors N/A so weights renormalize; trend-only today, valuation/heat join when they
  go live) over persisted NAV history → IC / hit-rate, on the **retro replay clock** (§2.3 — its own
  sampling grid and three-date model, mirroring forward's look-ahead discipline). Validates the
  **deterministic core**. Runnable as soon as a fund has **> `minimum_observations` (251) NAV obs** —
  i.e. ≥1 eligible replay point (§2.3); the one-time `nav_history` backfill seeds the historical
  series, so retro lights up **ahead of forward** but its replay count grows with history depth (a
  fund seeded with exactly ~251 obs yields ~0 replay points until more accrue).
- **Forward scorer** — reads the accruing `forward_ledger.jsonl`, dedups (`latest_per_key`), and scores
  the **raw** signal (`raw_composite` / `raw_bias`, per roadmap §3.2c) of *matured* rows against
  realized forward total return. Validates the **whole published signal** (incl. the LLM legs). Lights
  up as the ledger accrues (~20 NAV obs after go-live).

**Informational, never auto-gates** (roadmap §3.4 / §5): a `monitor_forward` FAIL leaves every fund's
`published_state` unchanged. Numbers surface in the daily report's validation panel.

**Non-goals (M4):** factor ablation, weight/band sensitivity, the ADR. No weight/band change, no
auto-tuning. No human gold sets. No live LLM, no web search → **no paid surface**.

---

## 2. NAV source & join contract

### 2.1 One authoritative NAV series — `data/monitor/nav_history.jsonl`

The **signal ledger is not the NAV source** — it is run-sampled (sparse, irregular, duplicate
`as_of_date` across runs). NAV outcomes come from a dense, point-in-time NAV series:

```
nav_history row = { fund_id, nav_date, nav_acc, written_at, source_run_date }
```

- **COALESCE basis:** `nav_acc` is `COALESCE(nav_acc, nav)` — the same perf basis the ledger and
  `eval_trace` use ([fetch.py](../../../src/irc/monitor/fetch.py)).
- **Producer-maintained** (EDGE, in `irc monitor`): each run appends a **bounded trailing window**
  of the fund's NAV series — specifically, only observations where
  `nav_date >= run_date − NAV_APPEND_DAYS` (constant `NAV_APPEND_DAYS = 60` calendar days) — tagged
  `written_at` + `source_run_date`. Appending the full `view.nav_series` every daily run would grow
  the file as O(runs × full_history_length), making read-time dedup quadratic; a bounded window caps
  per-run growth at `7 funds × ~40 NAV dates` while the dedup reader still reconstructs the full
  dense series once the one-time backfill has seeded the pre-window history. Append-only JSONL,
  crash-safe, no read-modify-write (mirrors the forward ledger).
- **Reader** `latest_per_nav_date(rows)` (PURE): dedup by `(fund_id, nav_date)` keeping **max
  `written_at`** (last-write-wins; values for a past date should be identical anyway), then sort
  **ascending by `nav_date`**. Deterministic → byte-stable reports.
- **Eval runner is read-only.** A one-time backfill seeding `nav_history.jsonl` from the latest
  `outputs/<date>/monitor/eval_trace.json` `nav.acc_series` is a **migration script**, never the eval
  runner (the eval surface does not mutate `data/`).
- **Append safety contract: prefix-valid JSONL.** The file is always a valid prefix: every
  fully-written line is a parseable JSON object; a crash mid-write may leave a truncated (partially
  written) final line, which the reader skips with a logged warning. Implementation: open with
  `O_APPEND`, encode each row to bytes, call `os.write()` once per row (a single `os.write` call ≤
  `PIPE_BUF` is atomic for pipes; for regular files on local filesystems the kernel still serialises
  concurrent appenders, but the safe contract to rely on is the prefix-valid guarantee, not
  per-write atomicity). Call `os.fsync()` after the batch (not per-row). **Do not** say
  "atomically" — there is no OS-level snapshot protocol here.
- **Tie handling for identical `written_at`:** if two rows share `(fund_id, nav_date, written_at)` (e.g.
  from a rapid re-run), `latest_per_nav_date` breaks the tie by `source_run_date` descending. Values
  should be identical; if not, log a data-quality warning and keep the one with the later `source_run_date`.
  - **Final deterministic tiebreak — last line wins.** `written_at` and `source_run_date` are
    second-resolution, so two reruns can collide on **both** (same fund, same `nav_date`, same
    `written_at`, same `source_run_date`). The reader resolves this last tie by **file position: the
    later line in the JSONL wins** — i.e. iterate rows in read order and keep the last on an exact key
    collision (a `>=` keep, identical to `forward_log.latest_per_key`'s tie behavior). This makes
    `latest_per_nav_date` **totally ordered on its key** → byte-stable regardless of how many reruns
    collide. (Equivalently: stamp each parsed row with a monotonic read-order ordinal and break the
    final tie by max ordinal.)
- **Line ordering:** the producer appends rows in `nav_date` ascending order within each run window.
  The reader always re-sorts after dedup — canonical ordering is the **reader's** responsibility,
  not the writer's.
- **Reader during a producer burst:** `latest_per_nav_date` reads the file in a single sequential
  pass, skipping any truncated final line, then deduplicates and sorts. There is no snapshot
  protocol — the read is not atomic with respect to concurrent producer appends — but because the
  producer `fsync`s after each batch and the reader skips the truncated tail, the reader always sees
  a consistent prefix. (File grows at ~280 raw rows/run but unique NAV dates dedup to ~1,800/year;
  read-time dedup stays fast. Races are benign at this scale.)

### 2.2 Entry anchor, maturity, bad-data exclusion

Per deduped ledger row (signal at `run_date`), in the fund's ascending `nav_history` series:

**Three dates — kept strictly separate:**

| Date | Meaning | Role |
|---|---|---|
| `as_of_date` | Feature cutoff — last NAV observation in the signal's input window | Part of the signal; must NOT be the entry price |
| `run_date` | Publication date — when the signal is committed and observable to a user | Entry anchor |
| `entry_nav_date` | First NAV strictly after `run_date` — earliest actionable execution price | `series[entry_idx].nav_date` |

**Pre-maturity ledger-quality filter** (applied before the formula below, separate from the
`nav_history` bad-nav exclusion): drop ledger rows where any of these hold:
- `nav_acc is None` (M0 degraded-NAV row: the fund's NAV was unavailable at publish time and the
  ledger was still written with `nav_acc=null`; the momentum baseline would also have no valid
  `as_of_date` cutoff for such a row)
- `as_of_date` is missing, `"N/A"`, or not a parseable ISO date
- `as_of_date > run_date` (data error: feature cutoff after publication date)

These rows are recorded under exclusion reason **`null_signal_nav`** and cannot enter any metric
population. The maturity formula below is applied only to rows that pass this filter.

```
entry_idx   = first index with nav_date > run_date         # strictly AFTER run_date (same-day NAV excluded)
outcome_idx = entry_idx + H,   H = 20 NAV observations
fwd_ret     = series[outcome_idx].nav_acc / series[entry_idx].nav_acc - 1
```

The formula uses `>`, **not** `>=`: a same-day NAV (`nav_date == run_date`) may already be part of the
signal's input window (if `as_of_date == run_date`, which can happen on late-day reruns) and must not
serve as the entry price. Anchoring strictly after `run_date` eliminates this look-ahead.

- **Diagnostic `from_latest_nav`:** a return anchored at `as_of_date` is computed and stored in
  `details` for diagnostic purposes, with a prominent label **"look-ahead diagnostic only — not a
  headline metric."** It is never surfaced in the panel or used in any aggregate statistic.
- **Mature** iff: an entry obs exists (some `nav_date > run_date`); `outcome_idx < len(series)`;
  `series[outcome_idx].nav_date <= today` (China date, `Asia/Shanghai`); **and** both endpoint
  `nav_acc` are finite and `> 0`. Otherwise the row is **excluded with a recorded reason**
  (`no_entry_obs` / `not_matured` / `bad_nav`) — **not** a FAIL. Immature rows mature ~20 NAV days later.
  > **Input-data quality vs scorer-logic failure.** `bad_nav` is a **row-level data exclusion** (the
  > raw `nav_history` value is non-finite or ≤ 0). A scorer-logic **FAIL** (§5.2 / §8) means the
  > evaluation code itself produced an impossible result — e.g. `outcome_idx < entry_idx`, or `fwd_ret`
  > is NaN despite both endpoints being finite and positive. These are different failure modes; the
  > maturity filter handles data quality; the FAIL path handles code invariants.

### 2.3 Retro replay clock (the three dates, retro analogues)

The forward path inherits its clock from the ledger (`as_of_date` / `run_date` already recorded per
row). Retro has **no ledger** — it manufactures signals by replaying `compute_signal` over
`nav_history`, so the same three-date discipline must be **defined explicitly** or an implementer can
accidentally (a) compute trend on the full series (look-ahead — the signal "sees" NAVs after its own
cutoff) or (b) enter on a NAV already inside the feature window. Retro needs only `nav_history` (no
ledger), so it can run **before** the forward ledger has matured — but only at replay points with **≥
`minimum_observations` (251) prior obs** (see Sampling grid); the contract below is what keeps it
look-ahead-free.

**Sampling grid.** Per fund, the replay points are the fund's deduped, ascending `nav_history`
`nav_date`s that satisfy both: the truncated input window holds **≥ the fund's `minimum_observations`**
(`config/monitor.yaml`, currently **251** — sourced, never hardcoded), **and** the row can mature (an
entry obs and `outcome_idx < len(series)` exist per §2.2). The `minimum_observations` floor is
**load-bearing, not cosmetic**: the real `compute_signal` marks the trend leg **N/A below
`minimum_observations`** (`factors.py:29`), because the trend blend's longest lookback is the **250-obs
drawdown** (`trend.py` `_drawdown_250`) — **not** the 20-obs forward horizon (a unit the spec keeps
distinct). On a shorter window the evidence-free composite has **no present factor** → `composite =
round(sum([]), 4) = 0.0` and `status="insufficient_evidence"` (`signal.py:70,74,84`). Scoring those
points would feed the IC a **constant-0 signal** (Spearman `None`, §4.2) — so they are **excluded from
the grid**, not replayed. Every eligible `nav_date` is a replay point; overlapping forward windows are
handled by the shared-timeline clustered block bootstrap (§4.3), not by thinning the grid (the optional
non-overlapping subsample stays a `details` robustness check).

**Three dates — retro analogues** (same strict-`>` entry rule as forward §2.2):

| Date | Forward source | Retro source |
|---|---|---|
| `as_of_date` | recorded in ledger row | **= the replay `nav_date`** — feature cutoff |
| `run_date` (entry anchor) | recorded in ledger row | **= `as_of_date`** — retro has no publication lag; the replayed signal is "published" at its feature cutoff |
| `entry_nav_date` | first `nav_date > run_date` | first `nav_date > as_of_date` — **strictly after**, identical `>` rule |

- **Truncated input window (the load-bearing rule).** At replay point with index `as_of_idx`,
  `compute_signal` is fed **only `series[: as_of_idx + 1]`** (NAVs up to and including the replay
  date). It must **never** see `series[as_of_idx + 1:]`. The evidence legs are N/A (retro is
  evidence-free), so the only future-leaking surface is the trend window — truncation closes it.
- **Entry is strictly after the cutoff.** Because retro's `run_date == as_of_date`, the strict-`>`
  rule means `entry_nav_date = series[entry_idx].nav_date` with `entry_idx = first index with
  nav_date > as_of_date`. The entry NAV is therefore never the cutoff NAV and never inside the
  feature window — this is exactly what prevents "enter on a NAV already visible to the feature
  window." `outcome_idx = entry_idx + H`, `fwd_ret`, and maturity reuse the §2.2 formula verbatim.
- **No `from_latest_nav` headline for retro.** Anchoring retro entry at `as_of_date` (the cutoff NAV)
  would be look-ahead; if computed it is stored as the same labeled diagnostic (§2.2,
  `details.from_latest_nav_diagnostic`), never a headline or aggregate.
- **Eligibility exclusions** mirror forward: a replay point with no `nav_date > as_of_date`
  (`no_entry_obs`), `outcome_idx >= len(series)` or `outcome_nav_date > today` (`not_matured`), or a
  non-finite/≤0 endpoint (`bad_nav`) is excluded with a recorded reason — never a FAIL.

---

## 3. Signal sources

- **Forward** — `latest_per_key(ledger)` → one `(run_date, fund_id)` row carrying `raw_status`,
  `raw_composite`, `raw_bias`, `as_of_date`. Two metric populations, kept distinct:
  - `raw_composite` (continuous, `raw_composite_directional` mode): **all** matured rows, any
    `raw_status` — `signal.py` always returns a composite even for `insufficient_evidence` rows, so
    every matured row contributes. Includes NO_CALL rows.
  - `raw_bias` (discrete, `publishable_bias_directional` mode): `raw_status=="ok"` rows only
    (bias is `None` for non-ok rows).
- **Retro** — `backtest.py` walks the **retro replay clock** (§2.3): at each eligible replay point it
  reconstructs the **evidence-free sub-composite** by calling the real `compute_signal` on the
  **truncated input window `series[:as_of_idx+1]`** with macro_tilt / constituent factors marked N/A,
  reading the continuous `SignalRecord.composite` (which `compute_signal` returns even when
  `status=="insufficient_evidence"` and `bias=None` —
  [signal.py:74,84](../../../src/irc/monitor/signal.py:74)). Each replay point yields one
  `(as_of_date, composite, fwd_ret)` with `fwd_ret` anchored strictly after `as_of_date` (§2.3). Retro
  therefore scores a **continuous composite, never a bias** (trend-only cannot clear the ≥2-family /
  `avail≥0.60` gate). Labeled as validating the deterministic / evidence-free core, **not** the full
  published bias.

---

## 4. Metrics & statistics (`src/irc/monitor/eval/stats.py`, pure)

### 4.1 Two directional modes (kept distinct so retro ≠ a fake track record)

- **`raw_composite_directional`** (scientific): predicted dir = `sign(composite)`, neutral-band points
  included. Computed for **both** retro and forward, allowing directional comparison — but note that
  retro uses the evidence-free renormalized sub-composite while forward uses the full raw signal
  including LLM/news legs. They are **directionally analogous, not directly comparable**: a divergence
  may reflect evidence-leg contribution rather than signal deterioration. Label as such in the panel.
- **`publishable_bias_directional`** (user-facing track record): predicted dir from the published
  `raw_bias`, NEUTRAL excluded. **Forward only** (retro has no publishable bias). This is the headline.

> **`raw_bias` → predicted sign (pinned).** `raw_bias` is the string enum `Bias = Literal["ADD_BIAS",
> "NEUTRAL", "REDUCE_BIAS"]` (`types.py:6`), not a number — so `publishable_bias_directional` needs an
> explicit map: **`ADD_BIAS → +1`, `REDUCE_BIAS → −1`, `NEUTRAL → 0` (excluded, same as a zero
> `fwd_ret`)**. `raw_composite_directional` instead takes `sign(raw_composite)` on the numeric
> composite. Without this map the headline metric — and the review trigger that reads it — is not
> computable.

Directional accuracy = fraction of matured rows where `sign(predicted) == sign(fwd_ret)` and
`fwd_ret != 0`. **Zero forward returns are excluded** (`sign(0) = 0` matches neither direction and
is non-informative for a directional accuracy metric).

### 4.2 Metrics

```python
def hit_rate(pred_dir, fwd_ret) -> float            # directional accuracy (headline)
def spearman_ic(signal, fwd_ret) -> float | None    # avg-rank ties; None ONLY if signal OR return ranks are all identical (constant)
def block_bootstrap_ci(rows, stat, *, seed, b=2000) -> tuple[float, float]   # 95% pct CI
def effective_n(rows) -> int                          # count of shared-timeline run-date blocks
```

> **Spearman tie contract.** Non-constant arrays with ties are handled by **average-rank** Spearman
> (standard scipy convention) — `None` is not returned. `None` is returned **only** when all signal
> values are identical (zero signal variance) OR all return values are identical (zero return
> variance). With 7 funds and rounded composites, partial ties are common and must not be treated
> as undefined.

**Metric–population matrix** (matured = passed §2.2 maturity filter; `fwd_ret != 0` required for
directional metrics):

| Metric | Mode | Population |
|---|---|---|
| hit-rate | `raw_composite_directional` | All matured rows, any `raw_status` (signal.py always emits a composite) |
| hit-rate | `publishable_bias_directional` | `raw_status=="ok"` matured rows (headline, forward only) |
| Rank-IC | cross-sectional | `raw_status=="ok"` matured rows, `raw_composite` as signal |

- **Rank-IC (secondary)** is **cross-sectional per day, time-averaged over defined days.** A day is
  defined only with **≥ `MIN_CROSS=4`** matured funds **and non-constant signal ranks AND
  non-constant forward-return ranks** (Spearman needs variance on both sides). Undefined days are
  **skipped, not zero-filled**. **Population:** `raw_status=="ok"` rows scored on `raw_composite`
  (NEUTRAL composites included). Note: this differs from `raw_composite_directional` hit-rate (all
  rows) and from `publishable_bias_directional` (ok-only, bias signal, NEUTRAL excluded).
  - **Defined-day-count gate (`MIN_DEFINED_DAYS=8`).** Let `defined_day_count` = number of defined
    days. The time-averaged IC is only **statistically reportable** with `defined_day_count ≥
    MIN_DEFINED_DAYS`. The status ladder (mirrors the hit-rate block ladder, so a thin sample never
    renders as a confident point estimate):
    - `defined_day_count == 0` → **`undefined`** sentinel (no cross-section ever cleared the gate).
    - `1 ≤ defined_day_count < MIN_DEFINED_DAYS` (i.e. 1–7) → IC point estimate **is** computed but
      flagged **WARN `insufficient_data`** — never PASS. A single defined cross-section must not read
      as a passing IC.
    - `defined_day_count ≥ MIN_DEFINED_DAYS` → normal status (WARN if the IC CI does not clear its
      `random` permutation baseline, else PASS).

### 4.3 Block bootstrap & `effective_n` (shared-timeline blocks)

Resample by **shared-timeline `run_date` buckets**, not per-fund index: build the global ordered set of
distinct `run_dates`; `bucket = floor(rank(run_date) / H)`; **all funds' rows in a bucket move
together** (preserves contemporaneous cross-fund correlation — the 7-fund cross-section is not
independent). Resample buckets with replacement (B=2000). `effective_n` = bucket count.

> **H in the block bootstrap is a run-date count, not NAV observations.** Monitor run dates and NAV
> observation dates are not equivalent: weekends, public holidays, skipped runs, and re-runs on the
> same day all break the correspondence. The constant `FORWARD_H=20` is reused as the approximate block
> size because it is the right order of magnitude (≈ one forward window), but its unit here is "run
> dates", not "NAV observations." Callers and comments must say "H run-date block" to avoid confusion
> with the `H = 20 NAV observations` forward-return window.

> **Honest framing:** clustered blocking **mitigates, not eliminates** overlap/autocorrelation — within
> a bucket the forward windows still overlap. The spec does **not** claim non-overlapping windows. A
> strictly non-overlapping subsample (entries spaced ≥H apart) is an optional `details` robustness
> check, not the headline (it discards most of a tiny sample).

### 4.4 Baselines (paired delta)

- `buy_hold` — always-long (`+`); its hit-rate = base rate of positive forward return.
- `momentum` — `sign(window_returns[20])` computed from the NAV series slice restricted to
  `nav_date <= as_of_date` (the signal's own feature cutoff — the exact information set the monitor
  signal had when it published), passed to [returns.py](../../../src/irc/monitor/returns.py) which
  uses the last observation in the provided series as its endpoint. **Not** `nav_history[:entry_idx+1]`:
  `entry_idx` is strictly after `run_date`, so that slice includes one post-publication NAV the signal
  never saw; on thin NAV histories the first post-publication observation can flip the 20-day momentum
  sign and make the "is it just trend?" comparison unfair.
  - **Definedness / degradation (no silent population drift).** `window_returns[20]` returns `None`
    **only** when the `<= as_of_date` slice has **fewer than 21 observations** or the 20-back
    denominator is **falsy/zero** — its sole guard is `if not denom`
    ([returns.py:6-12](../../../src/irc/monitor/returns.py:6)). It does **not** catch a **negative**
    denominator (passes `not denom`) or a **non-finite** endpoint (a `NaN`/`inf` NAV propagates to a
    `NaN`/`inf` result, **not** `None`). So the momentum-baseline code must treat the direction as
    **undefined** when `window_returns[20]` is `None` **or** the returned value fails
    `math.isfinite(...)` — relying on `is None` alone would let a `NaN` momentum slip in and corrupt
    the baseline. (`bad_nav` ≤0/non-finite endpoints are already scrubbed at the maturity boundary
    §2.2, but the momentum slice is taken from `nav_history` independently, so the explicit finite
    check is still required.) Because the momentum delta is a **paired** statistic
    (signal vs momentum, same rows), an undefined-momentum row is **dropped from the momentum
    paired-delta population only** — it still contributes to the signal's own hit-rate `value` and to
    the `buy_hold`/`random` deltas — and is counted under exclusion reason **`momentum_undefined`** in
    the hit-rate row's `excluded` diagnostic. This keeps the paired population explicit instead of
    letting it silently shrink. If the surviving paired rows span **fewer than `N_MIN_BLOCKS`**
    run-date blocks (the same block unit the paired bootstrap resamples, §4.3), the momentum delta
    carries `state="baseline_unavailable"` (no point estimate, no CI) rather than a delta over a
    drifted/degenerate population. `buy_hold` is always defined (always-long `+`), so only `momentum`
    can degrade this way.
- `random` — **within-`run_date` permutation** of signal labels (preserves each publication cohort's
  return cross-section and signal distribution), B=2000, seed `f(run_date,"perm")`. The grouping key
  is `run_date`, not `entry_nav_date`: funds published on the same monitor run share the same
  opportunity set regardless of fund-specific NAV calendar lags; permuting within `entry_nav_date`
  would mix opportunity sets from different publication dates (different `run_date` → different
  signal information set). Population filter is applied first (same as the metric being compared
  against), then grouped by `run_date`. A `run_date` group is **excluded** from the permutation
  component when either: (a) it has `< 2` actionable rows (permuting a single row is identity), or
  (b) **all actionable rows in the group have identical signal labels** (permuting identical values
  is identity regardless of count — provides no null variation). Both reasons are counted separately
  in the `excluded` diagnostic. Too few permutable `run_date`s (`< MIN_PERM_DATES`) → the random-delta
  `state="insufficient_data"`. The **permuted statistic is the metric under test** — directional
  hit-rate for the two hit-rate rows, time-averaged cross-sectional Spearman IC for the Rank-IC row —
  so `random` is the **one baseline shared by all three metric rows** (and, per §5.3, the IC row's
  *only* baseline). `momentum`/`buy_hold` are directional-only.

`delta = signal_metric − baseline_metric`. `momentum` / `buy_hold` deltas use the **paired block
bootstrap** (`seed f(run_date,"boot")`); `random` uses the permutation null. All RNG seeds are functions
of `run_date` with named salts → reproducible, byte-stable.

### 4.5 Horizon & determinism

The constant `FORWARD_H = 20` serves two roles with different units:

- **Forward return window, momentum window, maturity:** `H = 20 NAV observations` — matching
  `returns.py`'s observation-window convention. No calendar-day vocabulary.
- **Block bootstrap block size:** `H ≈ 20 run dates` — an approximation of the forward window
  length, but in run-date count (see §4.3). Code comments must say "H run-date block."

Fixed seeds → identical CIs across reruns of the same artifacts.

---

## 5. Eval surface (`evals/monitor_forward/`)

### 5.1 Registry & CLI

```python
EvalStageSpec("monitor_forward", "evals.monitor_forward.runner", lifecycle="active", in_all_suite=False)
```

A new **documented registry category**: *active (runnable by name) but excluded from the green `--all`* —
informational and data-dependent. `registry.py`'s lifecycle docstring gains a note so a maintainer does
not "fix" it into `--all` and make the green suite data-dependent. Runnable via `irc eval
monitor_forward`; not `live_gated` (no LLM/env), **no spend gate / recorder** (reads `forward_ledger.jsonl`
+ `nav_history.jsonl` only — zero paid calls). rc `0 PASS / 1 WARN / 2 FAIL`.

**Cadence:** scheduled / CI (weekly is ample — data accrues slowly). The daily brief only *renders the
latest report*, never computes the backtest.

### 5.2 Runner (EDGE) & metrics (pure)

`runner.py`: read `forward_ledger.jsonl` + `nav_history.jsonl` (+ retro NAV history) → call the pure
cores → write `StageReport` + a `details.json` sibling. `metrics.py` (pure) maps results → `MetricReport`.

- **Status is set manually, not via thresholds alone.** CI-crossing is not a single-threshold compare,
  so the runner/metrics set `status="WARN"` explicitly for: CI not clearing a baseline, `insufficient_data`,
  or `undefined`. `threshold` dicts are **documentation only**; metric thresholds use **only
  `warn_below`/`warn_above`, never `fail_below`/`fail_above`** so `classify_status` can never emit FAIL
  for statistical weakness.
- **FAIL is reserved for the input-contract path** (raised before metrics): missing/corrupt ledger or
  `nav_history` → `missing_input_report` FAIL; a broken scorer invariant — `outcome_idx < entry_idx`,
  or `fwd_ret` computed as NaN despite both endpoint NAV values being finite and positive — → explicit
  FAIL. **Not** a FAIL: raw input data with non-finite or ≤ 0 NAV values — those are handled as
  `bad_nav` row-level exclusions in the maturity filter (§2.2). `overall = worst_status(metric statuses)`
  is therefore WARN-max for a valid-but-weak run.

### 5.3 `details_ref` JSON (no `report_schema` migration)

`MetricReport` only holds scalar `value` + `threshold: dict[str,float]` + `n_observations` +
`details_ref`. Rich stats live in a sibling JSON:

- **`artifact_date`** = the eval-runner's execution date (`YYYY-MM-DD`, `Asia/Shanghai` timezone),
  passed to `report_dir(repo_root, "monitor_forward", artifact_date)`. It is **not** the max mature
  `run_date`, not the max NAV date, not the latest ledger write date — it is when this eval run
  was executed, so re-runs on different days produce distinguishable reports.
- Writer: `report_dir(repo_root, "monitor_forward", artifact_date) / "details.json"`
  ([report_paths.py](../../../evals/_shared/report_paths.py)).
- `MetricReport.details_ref` = **repo-relative** `outputs/<artifact_date>/evals/monitor_forward/details.json`
  (no leading slash).
- **Per-metric `details` is metric-specific** — momentum and buy_hold are *directional hit-rate*
  baselines (sign vs `fwd_ret`); they have **no meaningful cross-sectional Rank-IC analogue**, so they
  must not appear on the IC row:
  - **Hit-rate rows** (`raw_composite_directional`, `publishable_bias_directional`):
    `{ value, ci_low, ci_high, baseline_deltas:{ random, momentum, buy_hold: {delta, ci_low, ci_high} },
    effective_n, excluded:{reason:count}, state }`.
  - **Rank-IC row** (`rank_ic`): `{ value, ci_low, ci_high, baseline_deltas:{ random: {delta, ci_low,
    ci_high} }, defined_day_count, effective_n, excluded:{reason:count}, state }`. The **only** IC
    baseline is `random` — the per-day permutation null applied to the cross-sectional IC (permute
    signal labels within each defined day, recompute Spearman). `momentum` / `buy_hold` keys are
    **absent** on the IC row (not `null` — absent), so a reader never mistakes a directional baseline
    for an IC baseline.
  - **Degraded baselines carry a `state` in place of `{delta,ci_low,ci_high}`.** A baseline entry is
    `{delta, ci_low, ci_high}` when computable, else `{state}` — `random:{state:"insufficient_data"}`
    when too few permutable `run_date`s (§4.4), `momentum:{state:"baseline_unavailable"}` when too few
    defined paired rows (§4.4). The panel renders "baseline n/a" for a stated baseline; the metric's
    own `value`/`status` are unaffected (a missing baseline never upgrades or downgrades the headline).
- **`from_latest_nav` in `details`:** the diagnostic anchored at `as_of_date` (§2.2) is stored
  under `details.from_latest_nav_diagnostic` and carries an explicit `"label": "look-ahead
  diagnostic only — not a headline metric"` field. It must **not** appear in any rendered panel
  section without that label shown immediately adjacent.
- **Per `MetricReport`:** `value` is **that metric's own scalar** — the stage produces one
  `MetricReport` per metric (three rows: `raw_composite_directional`, `publishable_bias_directional`,
  `rank_ic`), each with its own `value`. `value` is hit-rate for the two hit-rate rows and IC for
  the IC row. Do not put hit-rate into the IC row or vice-versa. `n_observations` = `effective_n`
  (block count) for hit-rate rows; `defined_day_count` for the IC row. `status ∈ {PASS,WARN}`.
  - **`n_observations` units are intentionally row-type-dependent** (it is one int field on
    `MetricReport`): block count for hit-rate rows, defined-day count for IC. A consumer must key off
    the metric `name`, **never** compare `n_observations` across the three rows as if same-unit; the
    unit-disambiguated values (`effective_n`, `defined_day_count`) also live in `details`.
  - **Undefined Rank-IC (zero defined days):** sentinel `value=0.0, status="WARN",
    n_observations=0, details.state="undefined"`.
  - **Thin Rank-IC (1–7 defined days, `< MIN_DEFINED_DAYS`):** `value`=(computed time-averaged IC),
    `status="WARN"`, `n_observations`=`defined_day_count`, `details.state="insufficient_data"`. The
    point estimate is recorded but explicitly sub-threshold — never PASS (§4.2 ladder).
  - **Insufficient blocks (hit-rate rows), `effective_n < N_MIN_BLOCKS`:** `value`=(computable
    hit-rate), `status="WARN"`, `n_observations`=`effective_n`, `details.state="insufficient_data"`.

---

## 6. Panel integration (I/O at the command edge, render pure)

The runner only **writes** the `monitor_forward` `StageReport`. The monitor command edge
(`_write_outputs` in [monitor_cmd.py](../../../src/irc/commands/monitor_cmd.py)) reads
`latest_stage_report_entry(repo_root, "monitor_forward")`
([latest_report.py](../../../evals/_shared/latest_report.py)) to get the `StageReportEntry`
(needed for `artifact_date` staleness check), extracts `.report` for the panel model, and passes it
into the **pure** `render_report` — exactly as the M0/M1 `gates` dict flows
([render_html.py:146](../../../src/irc/monitor/render_html.py:146)). `panel.py` gains pure
`predictive_validity_panel_html(*, model)`.

- States rendered: normal (IC/hit-rate + baseline deltas + CIs, with a per-baseline "n/a" when a
  baseline is `insufficient_data`/`baseline_unavailable`), `insufficient_data` ("accruing — N/target"),
  `undefined`, and a **review trigger** flag.

- **`StageReportEntry` wrapper (new, in `latest_report.py`).**  `StageReport` has no `artifact_date`
  field, and `latest_report.py` currently discards the directory name after parsing. Staleness and
  ISO-week dedup both need the artifact date as a first-class value, so introduce:
  ```python
  StageReportEntry = namedtuple("StageReportEntry", ["artifact_date", "report"])
  # artifact_date: str  — YYYY-MM-DD, from the output directory name
  # report:        StageReport
  ```

- **Report-history helper (new, shared).** `latest_report.py` gains two new functions alongside
  the unchanged `latest_stage_report`:
  - `list_stage_reports(repo_root, stage_name, *, limit=None, today_iso=None) -> list[StageReportEntry]` —
    scans `outputs/*/evals/<stage>/report.json`, **applying the same `dir_name <= today_iso` clamp as
    the existing `latest_stage_report`** ([latest_report.py:47-52](../../../evals/_shared/latest_report.py:47):
    a future-dated dir is skipped so the trigger's K-week window is deterministic and unaffected by
    clock skew / backfilled future dates), descending by `artifact_date` (directory name); returns all
    parseable reports as `StageReportEntry` objects, `ran_at` descending as tiebreak within the same
    `artifact_date`, optionally capped at `limit`; corrupt/unparseable `report.json` skipped + logged
    (same as `latest_stage_report`). `today_iso` is injectable for tests.
  - `latest_stage_report_entry(repo_root, stage_name) -> StageReportEntry | None` — returns
    `list_stage_reports(repo_root, stage_name, limit=1)[0]` or `None`. The daily brief uses
    **this**, not `latest_stage_report`, so it has `artifact_date` for the staleness check.
  - The existing `latest_stage_report` remains for backward compatibility with M0/M1 callers that
    only need the `StageReport`.

- **Staleness model.** The daily brief calls `latest_stage_report_entry("monitor_forward")` →
  `StageReportEntry | None`. A report is **stale** if `entry.artifact_date < today − STALE_EVAL_DAYS`
  (`STALE_EVAL_DAYS = 10`, `Asia/Shanghai`). Panel states:
  - No entry found → "no backtest yet — run `irc eval monitor_forward`".
  - Stale → caveat banner showing `entry.artifact_date`; prompt to rerun.
  - Fresh → normal metric display.

- **Human-review trigger** — fires when the **headline metric's point estimate sits below its random
  baseline for ≥ K=4 consecutive ISO-week reports** → panel shows "⚠ review: signal
  underperforming." **Never** `EVAL_GATED` (roadmap §5).
  - **Trigger metric is pinned: the `publishable_bias_directional` random delta** (`details.baseline_deltas.random.delta`
    of the headline hit-rate row). "Below random baseline" ⇔ that delta `< 0`. The other metrics
    (`raw_composite_directional`, `rank_ic`) do not drive the trigger.
  - **Why a command-edge load.** That delta lives in `details.json`, not in `StageReport` —
    `MetricReport` carries only `value` (the metric's own scalar) + `details_ref` (a path), per the
    no-`report_schema`-migration decision (§5.3). So the **command edge** resolves each deduped
    week's `details_ref`, reads `details.json`, and extracts the headline random delta; the pure
    trigger never does I/O.
  - **ISO-week dedup (pure).** Call `list_stage_reports(limit=K*4)` (fetch a buffer), group by
    `ISO year-week(entry.artifact_date)`, keep one `StageReportEntry` per ISO week (the one with the
    highest `artifact_date`; tiebreak by `entry.report.ran_at`), take the K most recent weeks. Four
    manual reruns across four calendar days in the same week count as **one** week's report — not
    four consecutive failures. The dedup logic is pure, testable independently from the trigger.
  - **Edge → pure handoff.** For each of the K deduped weekly entries the edge builds a per-week
    scalar `headline_random_delta: float | None` (`None` when the headline row's `details.state` is
    `insufficient_data`/`undefined`, the `details.json` is missing/unreadable, or the random delta is
    `insufficient_data`). It passes the ordered list to the pure
    `review_trigger(weekly_headline_random_deltas: list[float | None]) -> bool`, which returns `True`
    iff the most recent K entries are all present (non-`None`) and `< 0`. **A `None` week breaks the
    streak** (missing/weak data never counts as a failing week) → conservative, no false review alarm.
  - K=4 is configurable via `REVIEW_TRIGGER_K`.

---

## 7. Data flow

```
PRODUCER (irc monitor):  view.nav_series ──► append data/monitor/nav_history.jsonl  (+ forward_ledger.jsonl from M0)

OFFLINE EVAL (irc eval monitor_forward, scheduled/CI):
  RETRO:   nav_history ─replay clock §2.3► backtest.py (compute_signal on series[:as_of_idx+1], evidence N/A → composite) ─entry strictly > as_of_date► (composite, fwd_ret) ─┐
  FORWARD: forward_ledger ─latest_per_key► mature filter (entry@run_date, +20 obs in nav_history) ──► (raw_composite/raw_bias, fwd_ret) ─┤
                                                                                                                                         ▼
                       stats.py: hit-rate(2 modes) + rank-IC + baseline deltas (block bootstrap / permutation null), effective_n
                                                                                                                                         ▼
                       runner ──► StageReport (WARN-max for weakness; FAIL only on input contract) + details.json
                                                                                                                                         ▼
GATE READ (daily): monitor_cmd edge ─latest_stage_report_entry► pure panel model ─► render_report(... predictive_panel=model)   [never gates]
```

---

## 8. Error handling / degradation

- Ledger **file absent** → `missing_input` FAIL (producer never ran). Ledger **present but the matured
  population spans `< N_MIN_BLOCKS` run-date blocks** (`effective_n < N_MIN_BLOCKS`, the single block
  unit of §4.3 — the same constant the momentum-degradation gate uses) → **WARN** `insufficient_data`
  (expected early).
- `nav_history` absent → FAIL; retro NAV too shallow → retro section `N/A` WARN, forward still runs.
- Malformed ledger / nav_history lines → skip + log; **all** bad → FAIL.
- Broken scorer invariant (e.g. `outcome_idx < entry_idx`, computed `fwd_ret` NaN despite finite
  positive endpoints) → FAIL. Bad input NAVs (non-finite or ≤ 0 in `nav_history`) are caught in
  the maturity filter (§2.2) as `bad_nav` row-level exclusions — not FAILs.
- A `monitor_forward` failure returns rc 2 from its own command and **cannot touch the daily brief**;
  a stale/absent latest report renders the existing staleness caveat.

---

## 9. Testing (TDD, test-first)

- **Pure unit (no network):**
  - `test_stats` — `hit_rate` / `spearman_ic` on known arrays; **zero `fwd_ret` rows excluded from
    `hit_rate`** (not counted as correct or incorrect); Spearman: **constant signal ranks → None**;
    **constant return ranks → None**; **non-constant tied arrays (partial ties) → avg-rank
    Spearman, not None** (test with all-same-but-one fixture to guard against over-broad None
    returns); `block_bootstrap_ci` coverage on synthetic data + **fixed-seed determinism**;
    `effective_n` shared-timeline bucket counting; block size H labeled as **run-date count** in
    the test fixture comment (asserts that bucket assignment is by run-date rank, not NAV obs index).
  - `test_baselines` — buy_hold / momentum (`window_returns[20]` sign from `nav_history` slice
    where `nav_date <= as_of_date` — **sign-flip test**: fixture where the entry NAV reverses the
    20-day momentum sign relative to the `as_of_date` slice; assert the baseline uses the
    `as_of_date` slice, not the `entry_idx+1` slice) / within-**`run_date`** permutation null (not
    `entry_nav_date`; verify that funds sharing a `run_date` but with different `entry_nav_date`s
    are permuted together); **single-actionable `run_date` excluded** from the permutation
    component; **identical-label `run_date` excluded** (all 7 funds `ADD_BIAS` → permutation is
    identity → no null variation; assert this group appears in `excluded.identical_labels`, not
    in `excluded.too_few_rows`); **momentum-undefined exclusion**: a row whose `<= as_of_date` slice
    has `< 21` observations (so `window_returns[20] is None`) **and** a row whose momentum value is
    **non-finite** (`NaN`/`inf` from a non-finite endpoint — `window_returns` returns the `NaN`, not
    `None`) are **both** dropped from the **momentum paired population only** (counted in
    `excluded.momentum_undefined`; assert an `is None`-only filter is insufficient and a
    `math.isfinite` check is required) while still contributing to the signal `value` and to
    `buy_hold`/`random` deltas; when surviving paired rows span `< N_MIN_BLOCKS` run-date blocks,
    `baseline_deltas.momentum.state == "baseline_unavailable"` (no delta/CI).
  - `test_nav_history` — `latest_per_nav_date` dedup (max `written_at`), ascending sort, byte-stability;
    **`written_at` tie-break** by `source_run_date` descending; **fully-degenerate tie** (two rows with
    identical `fund_id`/`nav_date`/`written_at`/`source_run_date` but differing `nav_acc`) → **last line
    wins** (assert the later-in-file row survives, matching `forward_log.latest_per_key`); **truncated
    final line** in fixture is skipped with a logged warning; reader re-sorts regardless of writer order.
  - `test_join` — **three-date model**: entry anchored at `run_date` (strictly `>`, not `>=`); a
    same-day NAV (`nav_date == run_date`) is **excluded** from entry candidates; `as_of_date`-anchored
    diagnostic is stored in `details` with `"label": "look-ahead diagnostic only..."` and is never the
    headline; maturity needs both endpoints `≤ today` & finite/`>0`; `bad_nav` / `no_entry_obs`
    excluded as row-level reasons, not FAILs; a scorer-invariant violation (`outcome_idx < entry_idx`)
    **is** a FAIL. **Null-ledger pre-filter**: ledger row with `nav_acc=None` → excluded as
    `null_signal_nav` before the maturity formula; ledger row with `as_of_date="N/A"` → same;
    ledger row with `as_of_date > run_date` → same; none of these are FAILs.
  - `test_backtest` — synthetic NAV → evidence-free `composite` → known `(composite, fwd_ret)`; **retro
    never emits a bias**. **Retro replay clock (§2.3)**: at each replay point `compute_signal` receives
    **only `series[:as_of_idx+1]`** (assert the input window never includes a `nav_date > as_of_date`);
    entry is the first `nav_date > as_of_date` (**strict `>`** — a same-`nav_date`-as-cutoff obs is
    never the entry); **look-ahead guard**: appending future NAVs after the replay point leaves every
    replayed `composite` byte-identical (proves the trend leg never reads past the cutoff); a replay
    point with `<` the fund's `minimum_observations` (251) prior obs or no maturable outcome is
    excluded with a recorded reason, not a FAIL. **Degenerate-grid guard**: a window just below
    `minimum_observations` makes `compute_signal` return `composite==0.0` /
    `status=="insufficient_evidence"` (trend N/A) — assert such points are **not** replay points (grid
    excludes them) so the IC is never fed a constant-0 signal.
  - `test_forward_score` — `latest_per_key` dedup + rerun last-wins; matured-only; **population matrix**:
    `raw_composite_directional` includes all matured rows (including `raw_status != "ok"` / NO_CALL
    rows); `publishable_bias_directional` includes `raw_status=="ok"` rows only; Rank-IC uses
    `raw_status=="ok"` rows on `raw_composite`; **zero-return rows excluded from hit-rate** in all modes.
  - `test_metrics` — strongly-negative-IC fixture → **WARN** (not FAIL); insufficient blocks → WARN
    `insufficient_data`; zero defined IC days → sentinel `value=0.0`/WARN/`undefined`; **1–7 defined
    IC days (`< MIN_DEFINED_DAYS`) → WARN `insufficient_data`** with the point estimate computed but
    never PASS (a single defined cross-section must not render as a passing IC); `≥ MIN_DEFINED_DAYS`
    defined days → normal PASS/WARN per CI-vs-baseline.
  - `test_panel` — pure snapshot of normal / insufficient_data / undefined / review-trigger states;
    **ISO-week dedup test**: 4 reports with consecutive artifact_dates within one ISO week count as
    1 week (trigger not fired); 4 reports each in a distinct ISO week all with headline random delta
    `< 0` → trigger fires; `list_stage_reports` dedup logic tested independently from the trigger
    boolean. **Trigger-input test**: `review_trigger` takes a `list[float | None]` of per-week
    headline random deltas — a `None` week (insufficient_data / missing details) **breaks the
    streak** (3 negative + 1 `None` + 1 negative ⇒ no fire); the edge extracts the delta from the
    `publishable_bias_directional` row's `details.json`, not from `MetricReport.value`.
- **Runner:** good fixture → `StageReport` + `details.json` at `outputs/<date>/evals/monitor_forward/`;
  absent ledger → FAIL; thin ledger → WARN; `details_ref` is repo-relative.
- **Registry:** `monitor_forward` is `active, in_all_suite=False`; **excluded from `active_suite_stages()`**
  (green `--all` stays cost-free and data-independent); `irc eval monitor_forward` runs it directly.
- **Integration:** `monitor_cmd` edge renders the panel from `latest_stage_report_entry` (the
  `StageReportEntry`, for `artifact_date` staleness); no entry → "no backtest yet"; stale → caveat.
- **Acceptance (the M3 invariant):** a **FAIL** `monitor_forward` report leaves every fund's
  `published_state` **unchanged** (proves M3 never gates); forward return uses the `COALESCE(nav_acc,nav)`
  basis, not unit NAV; the panel renders without JS and is byte-stable across reruns.

---

## 10. Pinned decisions

- **NAV source:** authoritative `data/monitor/nav_history.jsonl` (producer-maintained, append-only,
  dedup-on-read); the ledger supplies signal + entry anchor only. `latest_per_nav_date` dedup key is
  `(fund_id, nav_date)`; tiebreak chain is `written_at` desc → `source_run_date` desc → **last line
  in file wins** (totally ordered → byte-stable, matching `forward_log.latest_per_key`).
- **`nav_history` bounded append:** producer appends only `nav_date >= run_date − NAV_APPEND_DAYS
  (60)` per run; one-time backfill seeds pre-window history. Prevents O(runs × history) growth.
- **Null-ledger pre-filter:** ledger rows with `nav_acc=None`, non-date `as_of_date`, or
  `as_of_date > run_date` are excluded as `null_signal_nav` before the maturity formula. These
  rows never enter any metric population.
- **`StageReportEntry` wrapper:** `namedtuple("StageReportEntry", ["artifact_date", "report"])`;
  `list_stage_reports` and `latest_stage_report_entry` return this type; `latest_stage_report`
  unchanged for M0/M1 backward compat.
- **Spearman `None` contract:** `None` only for constant signal ranks OR constant return ranks;
  partial ties → average-rank Spearman (valid, not None).
- **Random baseline identical-label degeneracy:** `run_date` groups with all identical signal
  labels are excluded (separate reason `identical_labels`, not `too_few_rows`).
- **Three-date model:** `as_of_date` = feature cutoff; `run_date` = publication date; `entry_nav_date`
  = first NAV strictly after `run_date` (formula uses `>`, not `>=`). These are different dates and
  must never be aliased. `from_latest_nav` (`as_of_date` anchor) is a diagnostic only, labeled
  "look-ahead diagnostic only — not a headline metric", never surfaced in the panel unlabeled.
- **Retro replay clock (§2.3):** retro manufactures the three dates per replay point — `as_of_date` =
  the replay `nav_date`, `run_date` = `as_of_date` (no publication lag), `entry_nav_date` = first NAV
  strictly `> as_of_date`. `compute_signal` sees **only `series[:as_of_idx+1]`** (truncated input
  window) so the trend leg never reads future NAVs; entry strictly after the cutoff prevents entering
  on a NAV inside the feature window. Sampling grid = every eligible `nav_date` (**≥ the fund's
  `minimum_observations`, 251** — the trend leg's 250-obs drawdown lookback, `factors.py:29`; a shorter
  window yields an identically-0.0 evidence-free composite and is excluded — and maturable).
- **Zero forward returns:** excluded from directional hit-rate in all modes (`sign(0) = 0` is
  non-informative; excluded rows are counted in `excluded.zero_fwd_ret`).
- **Horizon:** `H = 20 NAV observations` (constant `FORWARD_H`) for the forward return window.
  Block-bootstrap block size reuses `FORWARD_H` but its unit is **run-date count**, not NAV
  observations — must be documented as "H run-date block" in all code comments.
- **Metric populations:** `raw_composite_directional` = all matured rows any `raw_status`;
  `publishable_bias_directional` = `raw_status=="ok"` only; Rank-IC = `raw_status=="ok"` on `raw_composite`.
- **Retro vs forward comparability:** directionally analogous, not directly comparable (different signal
  scope: evidence-free sub-composite vs full raw signal). Panel must label the retro metric accordingly.
- **`artifact_date`:** eval-runner execution date, not max ledger date or max NAV date.
- **Primary metric:** directional hit-rate (publishable-bias mode headline; raw-composite mode for
  retro/forward directional analogy); Rank-IC secondary.
- **CI:** clustered block bootstrap over shared-timeline run-date buckets, B=2000, fixed `run_date` seed;
  **mitigates not eliminates** overlap.
- **Baselines:** buy_hold / momentum (info set = `nav_date <= as_of_date`, matching the signal's
  exact feature cutoff; **not** `entry_idx+1`) / random (within-`run_date` permutation; grouping key
  is publication date, not `entry_nav_date`; population filter applied before grouping). **Momentum
  degradation:** a row has undefined momentum when `window_returns[20] is None` (`< 21` obs in the
  `<= as_of_date` slice, or falsy/zero denominator) **OR** the returned value is non-finite
  (`not math.isfinite(...)`) — `returns.py` only None-guards a falsy denominator (`if not denom`), so a
  `NaN`/`inf` momentum is **not** `None` and must be caught by an explicit finite check, never `is None`
  alone. Such a row is dropped from the **momentum paired
  population only** (`excluded.momentum_undefined`); surviving paired rows spanning `< N_MIN_BLOCKS`
  run-date blocks ⇒ `momentum` delta `state="baseline_unavailable"`. Hit-rate baselines (momentum/buy_hold) do **not**
  apply to Rank-IC — the IC row's only baseline is the `random` permutation IC null.
- **Report-history API:** `list_stage_reports → list[StageReportEntry]` and
  `latest_stage_report_entry → StageReportEntry | None`, both in `latest_report.py`; artifact_date
  descending, `ran_at` descending tiebreak. Review trigger reads K ISO-week-deduped entries; the edge
  loads each week's `details.json` and hands the pure trigger the **headline
  `publishable_bias_directional` random delta** per week (`None` for weak/missing weeks, which break
  the streak).
- **Staleness:** artifact-date semantics — `artifact_date < today - STALE_EVAL_DAYS (10 days)` →
  stale; `ran_at` is not the staleness signal.
- **Severity split:** statistical weakness ⇒ WARN (manual, no `fail_below`); input-contract / scorer-logic
  failure ⇒ FAIL; bad input NAV data (`bad_nav`) ⇒ **row-level exclusion** (not FAIL, not WARN).
- **Encoding:** `details_ref` JSON for CIs/deltas, **per-metric `details` schema** — hit-rate rows
  carry `baseline_deltas:{random,momentum,buy_hold}`, the Rank-IC row carries `baseline_deltas:{random}`
  only (momentum/buy_hold are directional baselines, absent on the IC row); undefined IC = sentinel
  `value=0.0`/WARN/`undefined`; no `report_schema` migration.
- **Surface:** `active, in_all_suite=False` (documented category); scheduled/CI weekly; informational,
  **never auto-gates**.
- **Constants (module-level, tunable; calibration is M4):** `FORWARD_H=20`, `N_MIN_BLOCKS=8`,
  `MIN_CROSS=4`, `MIN_DEFINED_DAYS=8`, `MIN_PERM_DATES=8`, `BOOTSTRAP_B=2000`, `REVIEW_TRIGGER_K=4`,
  `NAV_APPEND_DAYS=60`, `STALE_EVAL_DAYS=10`. **Retro replay eligibility reuses the fund's
  `minimum_observations` (`config/monitor.yaml`, currently 251) — sourced from config, NOT a new
  literal**, so the grid floor never drifts from the trend leg's actual requirement.

---

## 11. File-by-file change list

**New (pure):** `src/irc/monitor/eval/{stats,baselines,backtest,forward_score}.py`;
extend `src/irc/monitor/eval/{types,panel}.py` (`BacktestResult`, `ForwardResult`, `PredictiveMetric`,
`predictive_validity_panel_html`, `review_trigger`).
**New (edge/IO):** `data/monitor/nav_history.jsonl` writer + pure `latest_per_nav_date` reader (in a new
`src/irc/monitor/eval/nav_history.py`); `evals/monitor_forward/{__init__,runner,metrics}.py`; a one-time
`nav_history` backfill migration script; mirrored `tests/`.
**Modified:** `evals/_shared/registry.py` (register `monitor_forward`; document the `active`+`in_all=False`
category); `src/irc/commands/monitor_cmd.py` (`nav_history` append in the producer; edge reads
`latest_stage_report_entry("monitor_forward")` → `StageReportEntry` → panel model, and loads the
headline row's `details.json` for the review-trigger delta); `src/irc/monitor/render_html.py`
(+ predictive panel CSS).
**Modified (shared):** `evals/_shared/latest_report.py` gains `StageReportEntry` (namedtuple),
`list_stage_reports(repo_root, stage_name, *, limit=None, today_iso=None) -> list[StageReportEntry]`,
and `latest_stage_report_entry(repo_root, stage_name) -> StageReportEntry | None`; existing
`latest_stage_report` unchanged for backward compat.
**Modified (producer):** `src/irc/commands/monitor_cmd.py` bounded-tail append
(`nav_date >= run_date − NAV_APPEND_DAYS`) replaces full-series append.
**Reused unchanged:** `forward_log.latest_per_key`, `evals/_shared/report_paths`,
`evals/_shared/{status,report_schema,missing_input}`.

---

## 12. Out of scope (M4)

Factor ablation, weight/band sensitivity, the economic-rationale ADR, any weight/band change or
auto-tuning, human gold sets. M3 is informational input to M4, not a calibrator.

---

## Appendix — review resolutions

**Round 1 (Part 1)**

| Finding | Sev | Resolution |
|---|---|---|
| eval runner must not call `nav_series_for` (edge) | P0 | §2.1: runner reads persisted `nav_history.jsonl` + ledger; never AkShare |
| trend-only `compute_signal` yields no bias | P0/P1 | §3: retro scores the continuous evidence-free `composite`, not a bias |
| "overall capped at WARN, never FAIL" too broad | P1 | §5.2: statistical weakness ⇒ WARN; input-contract failure ⇒ FAIL |
| panel "reads latest report" misplaces I/O | P1/P2 | §6: command edge reads `latest_stage_report`; render stays pure |

**Round 2 (Part 2)**

| Finding | Sev | Resolution |
|---|---|---|
| CI unit must be clustered blocks of rows | P0 | §4.3: shared-timeline run-date buckets, whole cross-section together |
| Spearman undefined on many days | P1 | §4.2: `MIN_CROSS`, both-sided variance, skip undefined days |
| permutation null not byte-stable | P1 | §4.4: within-date permutation, seed `f(run_date,"perm")` |
| threshold vs rc; `insufficient_data` shape | P1 | §5.2/§5.3: WARN-only thresholds; `details.state`, status WARN, `n_observations` |
| directional retro vs forward apples-to-oranges | P2 | §4.1: two explicit directional modes |
| `H=20d` calendar vs observations | P2 | §4.5: `H=20 NAV observations` everywhere |
| `active`+`in_all=False` semantically new | P2 | §5.1: documented registry category |

**Round 3 (Part 2 refinement)**

| Finding | Sev | Resolution |
|---|---|---|
| NAV join/maturity contract still absent | P0 | §2.1/§2.2: authoritative `nav_history` + explicit join + maturity |
| "20-observation calendar span" reintroduced ambiguity | P0 | §4.5: observations only; "calendar" removed |
| block bootstrap overclaims non-overlapping | P1 | §4.3: "mitigates not eliminates"; honest caveat |
| Rank-IC must check return ties + population | P1 | §4.2: both-sided variance; population pinned |
| `MetricReport.value` can't be undefined | P1 | §5.3: sentinel `value=0.0`/WARN/`undefined` |
| `details_ref` path must be repo-relative | P1 | §5.3: `outputs/<artifact_date>/…`, no leading slash |
| WARN-only must forbid `fail_below` | P2 | §5.2: thresholds documentation-only; WARN set manually |
| permutation unit undefined | P2 | §4.4: within-entry-date permutation |

**Round 4 (final pins)**

| Finding | Sev | Resolution |
|---|---|---|
| entry on `as_of_date` → look-ahead | P0 | §2.2: entry anchored at `run_date`; `from_latest_nav` diagnostic only |
| `nav_history.jsonl` write/dedup unpinned | P0 | §2.1: row schema, append-only, `latest_per_nav_date` dedup |
| seeding contract vague | P1 | §2.1: producer-maintained; runner read-only; backfill = migration |
| maturity must check both endpoints + bad data | P1 | §2.2: entry+outcome obs, `≤ today`, finite/`>0`, else excluded |
| "calendar block" wording lingers | P1 | §4.3: run-date buckets on a shared timeline |
| cross-fund blocks need a global key | P1 | §4.3: bucket by shared-timeline run-date rank, all funds together |
| `details_ref` rooted-path risk | P1 | §5.3: repo-relative, writer uses `report_dir(...)` |
| WARN via thresholds insufficient for CI metrics | P2 | §5.2: runner sets WARN manually; thresholds documentation |
| within-date permutation degenerate on tiny cross-sections | P2 | §4.4: exclude `<2`-row dates; too few → `insufficient_data` |

**Round 5 (clock / bad-nav / comparability / spec tightening)**

| Finding | Sev | Resolution |
|---|---|---|
| `>=` allows same-day NAV → look-ahead | P0 | §2.2: formula uses `>` (strict); three-date table added; §9 tests same-day exclusion |
| Momentum baseline can see post-signal NAVs | P0 | §4.4: series slice pinned to `nav_history[:entry_idx+1]` |
| `bad_nav` exclusion vs FAIL contradiction (§2.2 vs §5.2/§8) | P0 | §2.2 blockquote, §5.2, §8: data-quality exclusion ≠ scorer-logic FAIL; clarified in both places |
| Block bootstrap H unit mismatch (run dates ≠ NAV obs) | P1 | §4.3: H in bootstrap is run-date count; caveat block added; §9 asserts bucket by run-date rank |
| `raw_composite_directional` population under-specified | P1 | §3, §4.2 table: all matured rows any `raw_status`; metric–population matrix added |
| Retro vs forward "directly comparable" overclaim | P1 | §4.1: "directionally analogous, not directly comparable"; panel label required |
| `nav_history` append contract under-specified | P2 | §2.1: append failure, tie-break, line-ordering, reader-during-burst all pinned |
| Staleness model deferred to M1 without explicit spec | P2 | §6: staleness model spelled out (`STALE_EVAL_DAYS`, three panel states) |
| `sign(0)` / zero-return handling undefined | Open Q | §4.1: zero-return rows excluded from hit-rate; §10 pinned; §9 tested |
| `artifact_date` definition ambiguous | Open Q | §5.3, §10: eval-runner execution date, not max ledger or NAV date |
| `from_latest_nav` needs look-ahead label if rendered | Open Q | §2.2, §5.3: stored as `details.from_latest_nav_diagnostic` with required label; §9 tests label present |

**Round 6 (baselines / report-history plumbing / MetricReport clarity)**

| Finding | Sev | Resolution |
|---|---|---|
| Momentum `[:entry_idx+1]` still includes one post-publication NAV the signal never saw | P0 | §4.4: slice changed to `nav_date <= as_of_date` (signal's own feature cutoff); §9 sign-flip test added |
| Staleness uses `ran_at` but `latest_report.py` is artifact-date-based | P1 | §6: staleness now `artifact_date < today - STALE_EVAL_DAYS`; `ran_at` not used for staleness |
| `list_stage_reports` missing — review trigger has no history API | P1 | §6, §10, §11: `list_stage_reports(repo_root, stage_name, *, limit)` added to `latest_report.py` |
| Review trigger counts reruns as separate weeks | P1 | §6: ISO-week dedup before trigger evaluation; K distinct ISO weeks required; §9 tested |
| Random null groups by `entry_nav_date` (wrong) instead of `run_date` | P1 | §4.4: permutation within `run_date` (publication cohort); grouping rationale added |
| `MetricReport.value` ambiguous for Rank-IC vs hit-rate rows | P2 | §5.3: each metric row carries its own scalar; three `MetricReport` rows named explicitly |
| Append contract claims "reads atomically" (not a real guarantee) | P2 | §2.1: "prefix-valid JSONL" framing; `O_APPEND` + `os.write` per row + batch `fsync`; "atomically" removed |

**Round 7 (implementability audit — `StageReport`, NAV growth, null-ledger, Spearman, identical labels)**

| Finding | Sev | Resolution |
|---|---|---|
| `artifact_date` not in `StageReport`; staleness/review trigger not implementable | P1 | §6, §10, §11: `StageReportEntry(artifact_date, report)` wrapper; `list_stage_reports` and `latest_stage_report_entry` return it; `latest_stage_report` unchanged |
| Producer appends full `view.nav_series` → O(runs × history) growth | P1 | §2.1, §10, §11: bounded tail `nav_date >= run_date − NAV_APPEND_DAYS (60)`; file-size note corrected |
| M0 null-ledger rows (`nav_acc=null`, `as_of_date="N/A"`) can enter maturity filter | P1 | §2.2, §10: pre-maturity ledger-quality filter; `null_signal_nav` exclusion reason; §9 `test_join` updated |
| Spearman `None` contract: "return-tie & signal-tie → None" conflates ties with constant | P2 | §4.2: constant ranks → None; partial ties → avg-rank Spearman; §9 `test_stats` corrected |
| Random baseline: all-identical-label group provides zero null variation | P2 | §4.4, §10: `identical_labels` exclusion separate from `too_few_rows`; §9 `test_baselines` updated |

**Round 8 (retro clock / trigger plumbing / IC gating / baseline degradation)**

| Finding | Sev | Resolution |
|---|---|---|
| Retro replay clock underspecified → look-ahead risk (no sampling grid, no retro three-date model) | P1 | §2.3 (new): sampling grid + retro `as_of_date`/`run_date`/`entry_nav_date` analogues; truncated input window `series[:as_of_idx+1]`; strict-`>` entry; §3/§7 reference it; §9 `test_backtest` look-ahead guard |
| Human-review trigger not implementable from `StageReportEntry` (random delta lives in `details.json`, metric unspecified) | P1 | §6, §10: pinned to headline `publishable_bias_directional` random delta; edge loads `details.json`; pure `review_trigger(list[float\|None])`; `None` week breaks streak; §9 `test_panel` updated |
| `baseline_deltas` schema over-broad for Rank-IC (momentum/buy_hold meaningless as IC baselines) | P1 | §5.3, §10: per-metric `details` schema — hit-rate rows keep random/momentum/buy_hold; IC row keeps `random` only (momentum/buy_hold absent) |
| `MIN_DEFINED_DAYS=8` pinned but not wired into Rank-IC status (1–7 defined days unhandled) | P1 | §4.2, §5.3: defined-day ladder — 0 → `undefined`; 1–7 → WARN `insufficient_data`; ≥8 → normal; §9 `test_metrics` updated |
| Panel API contradiction: data-flow/file-list still say `latest_stage_report` not `latest_stage_report_entry` | P2 | §7 diagram, §9 integration, §11 file list switched to `latest_stage_report_entry` |
| `latest_per_nav_date` has no final deterministic tiebreak (collide on `written_at`+`source_run_date`) | P2 | §2.1, §10: final **last-line-wins** tiebreak (matches `forward_log.latest_per_key`); §9 `test_nav_history` degenerate-tie case |
| Momentum baseline degradation underspecified (`< 21` obs / non-finite denom) → silent population drift | P2 | §4.4, §5.3, §10: `momentum_undefined` paired exclusion; `< N_MIN_BLOCKS` survivors ⇒ `state="baseline_unavailable"`; §9 `test_baselines` updated |

**Round 9 (adversarial review of the Round-8 rev — source-grounded)**

| Finding | Sev | Resolution |
|---|---|---|
| Retro grid floor `MIN_TREND_OBS=21` ~12× too small — real trend leg needs `minimum_observations` (251; `_drawdown_250` 250-obs lookback, `factors.py:29`); below it `compute_signal` returns `composite=0.0`/`insufficient_evidence` (`signal.py:84`) → constant-0 retro signal, contradicting "runnable day one" | P0 | §1, §2.3, §10: grid floor sourced from `minimum_observations` (config, 251), `MIN_TREND_OBS` literal removed; degenerate points excluded from grid; "runnable day one" qualified (needs `> minimum_observations` obs / ≥1 replay point); §9 `test_backtest` degenerate-grid guard |
| `publishable_bias_directional` computes `sign(predicted)` on `raw_bias`, a **string** enum — no string→sign map defined ⇒ headline + trigger uncomputable | P1 | §4.1: pinned `ADD_BIAS→+1`, `REDUCE_BIAS→−1`, `NEUTRAL→0` (excluded); `test_baselines` `BULLISH`→`ADD_BIAS` |
| Momentum-undefined detection over-claims `returns.py` coverage — `window_returns` only None-guards falsy denom, NOT negative denom / non-finite endpoints (`NaN` propagates) | P1 | §4.4: require `is None` **or** `not math.isfinite(...)` check; §9 `test_baselines` non-finite exclusion case |
| Block-count threshold inconsistently named (`N_MIN` in §8 undeclared vs `N_MIN_BLOCKS`; hit-rate "insufficient blocks" gate unstated) | P1 | §8, §5.3: unified to `effective_n < N_MIN_BLOCKS` (single block unit, same constant as momentum gate) |
| `list_stage_reports` filter behavior vs existing `latest_stage_report` `<= today` clamp unpinned | P2 | §6: `list_stage_reports` applies the same `dir_name <= today_iso` clamp (injectable `today_iso`), skips corrupt reports |
| `MetricReport.n_observations` overloaded across rows (block count vs defined-day count) with no discriminator | P2 | §5.3: note that the unit is row-type-dependent; consumers key off metric `name`, never cross-compare |
| (re-review catch) §10 pinned-decision summary still said momentum undefined on "falsy/**non-finite denominator**" — reintroduced the `is None`-only misconception the §4.4 fix removed | P1 | §10 momentum-degradation line re-synced to §4.4: `is None` (`<21` obs / falsy denom) **OR** `not math.isfinite(...)`; explicit finite check, not `is None` alone |
| (re-review catch) §11 `list_stage_reports` signature omitted `today_iso=None` (drifted from §6) | P2 | §11 signature synced to `(repo_root, stage_name, *, limit=None, today_iso=None)` |
