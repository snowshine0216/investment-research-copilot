# ADR 0020 — Monitor dual-track valuation + False-Cheap clamp

**Status:** Accepted as a **prior** (2026-06-21). Records the design rationale for re-basing the monitor look-through valuation factor bottom-up (per-stock dual-track + clamp); the quantitative validation stays deferred behind ADR 0018's evidence gate (priors are justified, never auto-tuned).

**Builds on:** [ADR 0017 — monitor evidence isolation](0017-monitor-evidence-isolation.md), [ADR 0018 — monitor scoring rationale + weight/band governance](0018-monitor-scoring-rationale-and-governance.md), [ADR 0019 — monitor capital-flow factor](0019-monitor-capital-flow-factor.md) (D4 deferred this work; per-symbol fetch posture reused).

**Relates to:** #156 / [ADR 0015](0015-portfolio-action-emission-contract.md) (a better-reasoned lean, never an order), [ADR 0014](0014-legulegu-rate-limit-handling.md) (per-symbol cached fetch), [ADR 0012](0012-fundamental-led-equity-valuation.md)/[ADR 0009](0009-consensus-upside-degrade-to-none.md) (why PEG/DCF stay out). **Spec:** [`docs/superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md`](../superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md).

**Source of truth:** [holding_metrics.py](../../src/irc/monitor/holding_metrics.py) (dual-track score, clamp, aggregate_valuation, named-constant priors), [industry_valuation.py](../../src/irc/monitor/industry_valuation.py) (industry data edge), [factors.py](../../src/irc/monitor/factors.py) (`_valuation` numeric path + KNOWN_NA_REASONS), [valuation.py](../../src/irc/monitor/valuation.py) (`ValuationResolution.path`), [monitor_cmd.py](../../src/irc/commands/monitor_cmd.py) (`_ENGINE_VERSION`, wiring), [eval/structural.py](../../src/irc/monitor/eval/structural.py) (reconciliation oracle).

## Context

The look-through valuation factor collapsed a fund's holdings into one portfolio earnings-yield series and took its self-history percentile. Self-history alone is value-trap-blind: a stock cheap vs its own (possibly de-rated) history can be expensive vs its peers. Separately, #168 surfaced a per-stock board that did not drive the bias. This ADR re-bases the factor bottom-up so the board and the factor agree, and adds an industry-relative leg + clamp to detect value traps. This touches a governed scoring surface (ADR 0018) and therefore records the priors here.

## Decision

### D1 — Bottom-up dual-track REPLACES the portfolio-harmonic percentile (methodology replacement, not a value re-base)

The new path is a cross-sectional weighted mean of per-stock dual-track scores, NOT the old portfolio-harmonic-series percentile. Consequences: (1) the factor value moves for look-through funds even with zero industry data (no "industry-off ⇒ byte-identical" fallback); (2) maturity is gated per stock (a fund near the floor with short-history holdings can newly read `valuation_no_coverage`); (3) no portfolio-harmonic fallback — under-coverage → honest N/A. The old `src/irc/monitor/lookthrough.py` + `_resolve_lookthrough` are deleted.

### D2 — Dual-track blend = 0.60·self-history + 0.40·industry-richness

`self_score = valuation_state_score(state)` (reuses the existing percentile→band→state→{1.0..-1.0} ladder verbatim, so the board's displayed state and self_score can never disagree). `industry_score` from richness `r = stock_pe / industry_avg_pe`, additive ASYMMETRIC raw-`r` bands (`r≤0.70→+1.0 · 0.70–0.90→+0.5 · 0.90–1.10→0.0 · 1.10–1.20→−0.5 · r≥1.20→−1.0`), matching the codebase's "slow to call cheap" conservatism. Industry leg N/A → `val_score = self_score` (honest 1.0·self fallback; per-stock `industry_no_data`, never a fabricated leg).

### D3 — Industry leg = Option A, EastMoney-coherent, per-symbol

Stock PE vs industry-average PE under ONE taxonomy (东财行业): industry-average PE from market-wide `stock_board_industry_name_em` (1 cached call/day); stock→industry per-symbol via `stock_individual_info_em` (~15–25 deduped cached calls/run). No single-call market-wide stock→industry table exists under a PE-matching taxonomy, so the leg is per-symbol — and that is fine: it reuses the proven flow per-symbol cached pattern (ADR 0014/0019), NOT a new rate-limit risk. Rejected: Option B (per-peer true percentile, ~N×constituents fetch), Option D (sector-blind absolute ceiling). **Denominator-robustness risk:** EM's 市盈率 is a single column (cap-weighting unverified, no median variant); non-positive/NaN PE is dropped to `industry_no_data`. A breadth guard is added ONLY if EM proves arithmetic-mean — recorded here as a risk, not a pre-built knob.

### D4 — False-Cheap clamp = hard-0 in the value-trap quadrant (deliberately NOT min(blend,0))

`self_score > 0 AND r ≥ 1.2` → hard-assign `val_score = 0.0`, `false_cheap=True`. The clamp fires ONLY in the value-trap quadrant (cheap-vs-self AND rich-vs-peers), where the correct stance is to discard the whole valuation verdict to neutral (epistemic humility on a detected trap + the noise-prone industry denominator), NOT to preserve the industry leg's magnitude. The one cell `self=+0.5 ∧ r≥1.2` (unclamped blend ≈ −0.1) is nudged UP to 0.0 ON PURPOSE — that is the verdict-discard, and it keeps the board annotation `→中性` literally true. Clamp to 0, never negative (the guard removes a false bullish signal; it does not assert bearishness).

### D5 — Coverage = fraction of fund NAV; monitor floor 0.40 (deliberate divergence from opportunity's 0.50)

`covered_weight_ratio = Σ covered weight_pct / 100.0` (NAV denominator, matching `lookthrough_valuation._coverage_ratio`). The aggregate uses the FULL disclosed basket (~top-10), NOT flow's top-5 (top-5 NAV coverage is 26–41% — fatal at any floor). Monitor floor = 0.40, NOT 0.50: at 0.50 the factor fired for 1 of 7 funds and was a phantom for 6/7; at 0.40 → 6/7 (only the most diversified fund, 260112 at 0.34, stays honest-N/A). The 0.40 is a monitor-specific named constant distinct from `lookthrough._COVERAGE_FLOOR=0.50` — the monitor valuation is a 0.20-weight research lean, not a publishability gate. Coverage-scaled confidence is a deferred follow-up.

### D6 — No PEG/DCF; valuation weight unchanged at .20; engine bump "2"→"3" (global)

PEG/DCF stay dropped (D6 of the spec); the industry leg + clamp IS the False-Cheap mechanism. The valuation weight stays `.20` on `active_cn_equity` (re-base the value, not the weight — no profile change). Engine bumps `"2"→"3"` globally (all 7 active funds change look-through→bottom-up); gold/qdii's needless forward-clock reset is accepted (per-fund engine versioning is not worth the complexity on a 10-fund set). Forward-eval isolation targets `"3"`; Follow-up 1's `engine_population` WARN covers the transition.

### D7 — Reasons: factor codes vs per-stock codes

`valuation_no_data` (zero covered) + `valuation_no_coverage` (below the NAV floor) are FACTOR N/A reasons → added to `KNOWN_NA_REASONS` (10→12) with reachable `_valuation` branches. `industry_no_data` + `false_cheap_clamp` are PER-STOCK `HoldingMetric` reasons, NEVER in `KNOWN_NA_REASONS` (the factor stays eligible on self-only / the clamped stock is covered).

### D8 — Named-constant priors (governed, never auto-tuned per ADR 0018)

blend `0.60/0.40`, `_FALSE_CHEAP_RICHNESS = 1.2`, monitor floor `0.40`, industry bands `0.70/0.90/1.10/1.20`. Promote to `config/monitor.yaml` only if later tuned.

## Consequences

- The board's weighted dual-track equals the valuation factor value (reconciliation oracle, 4dp) — the methodology is legible and verifiable.
- 018132 (sector-concentrated, holdings ≈ the industry → r≈1) collapses to ~self-only; the clamp rarely fires. Acceptable; a cleaner sector-index read needs its `tracked_index` populated (out of scope).
- The post-composite veto tier (conflict hard-suppression, flow-reversal guard) stays deferred (spec §10) — judged against forward evidence that resets to engine "3" here.
- Framing held: 研究参考信号，非买卖指令 (ADR 0015).

## Addendum — industry-leg root-cause correction + raw re-transport (2026-07-02)

**The D3 industry leg never produced data in production.** Measured 2026-07-02 (live probes, both direct and through the new CN proxy — so NOT a geo problem):

- `ak.stock_board_industry_name_em` (akshare 1.18.60) **no longer returns a `市盈率` column** → `parse_industry_pe` → `{}`, which `fetch_industry_pe` then cached for the day (`data/monitor/industry_pe/2026-06-29/-30.json` are both `{}`).
- `ak.stock_individual_info_em` **raises `ValueError: Length mismatch` on every call** since ~06-23 (EastMoney added `dlmkts`/`dsc` response keys the wrapper's fixed-key parser can't handle) → every symbol TRANSIENT, no cache written; the two pre-drift days (06-21/22) produced all-"miss" caches. Net: every engine-"3" ledger row to date carries **self-only** valuation.

**Decision (spec [`2026-07-02-monitor-cn-egress-data-plane-lightup-design.md`](../superpowers/specs/2026-07-02-monitor-cn-egress-data-plane-lightup-design.md) D3/D4):** re-transport the leg on raw EastMoney JSON — paginated `clist/get` `f9` for board PE, `stock/get` `f127` for stock→industry — slotted into the existing injectable `fetch` hooks so the parse / per-day cache / 3-outcome contracts are untouched, routed through `IRC_CN_PROXY`. `fetch_industry_pe` no longer caches an **empty** parse (aligned with the transient philosophy). **No `_ENGINE_VERSION` bump:** the dual-track methodology IS engine "3" and the leg never emitted a value, so lighting it up is data availability returning (the ADR 0019 DARK→FRESH class), not a semantics change. The D3 denominator-robustness risk stands — `f9` is 市盈率(动), single-column, weighting unverified; the Slice-0 sanity check hand-verifies a few boards against the EastMoney web UI before rollout.
