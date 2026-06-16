# MASTER-SPEC — Monitor Eval M3 (Block B · Predictive Validity)

**Mode:** `spec` (single-feature design doc → writing-plans authors the plan)
**Detected:** 2026-06-16
**Source spec:** [`docs/superpowers/specs/2026-06-16-monitor-eval-m3-backtest-design.md`](../superpowers/specs/2026-06-16-monitor-eval-m3-backtest-design.md) — rev 6, 9 review rounds
**Verbatim copy:** [`items/001-spec.md`](items/001-spec.md)

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | `monitor_forward` offline eval stage — retro backtest + forward scorer for the Monitor signal's predictive validity (Block B / M3) | **IN** | Single coherent feature; the design spec is fully grilled (9 review rounds, all P0/P1 resolved); no live LLM / web / paid surface; informational, never auto-gates |

## What IN-scope 001 delivers (from the spec)

- **New NAV source** `data/monitor/nav_history.jsonl` — producer-maintained bounded-tail append (EDGE in `irc monitor`), pure `latest_per_nav_date` dedup reader, one-time backfill migration script.
- **Retro backtest** (`backtest.py`) — replays the evidence-free sub-composite via `compute_signal` on a truncated input window (`series[:as_of_idx+1]`), on the explicit retro replay clock (§2.3), grid floor sourced from `minimum_observations` (251, config).
- **Forward scorer** (`forward_score.py`) — `latest_per_key(ledger)` → matured rows scored against realized forward total return; two distinct populations (`raw_composite_directional` all-rows, `publishable_bias_directional` ok-only).
- **Stats core** (`stats.py`) — `hit_rate`, `spearman_ic`, clustered block bootstrap CI, `effective_n`; **baselines** (`baselines.py`) — buy_hold / momentum / within-`run_date` permutation null.
- **Eval surface** `evals/monitor_forward/{__init__,runner,metrics}.py` — registered `active, in_all_suite=False`; rc `0/1/2`; WARN-max for statistical weakness, FAIL only on input-contract / scorer-invariant breach.
- **Report-history plumbing** — `StageReportEntry` namedtuple + `list_stage_reports` + `latest_stage_report_entry` in `evals/_shared/latest_report.py` (existing `latest_stage_report` unchanged).
- **Panel integration** — pure `predictive_validity_panel_html`, staleness model, ISO-week-deduped human-review trigger (pure `review_trigger`, edge loads `details.json` headline random delta).
- **Mirrored TDD tests** for every pure core + runner + registry + integration + the M3 acceptance invariant (a FAIL leaves `published_state` unchanged).

## Non-goals (explicit, stay OUT — these are M4, not this run)

Factor ablation, weight/band sensitivity, the economic-rationale ADR, any weight/band change or auto-tuning, human gold sets. M3 is informational input to M4, not a calibrator. **No OUT-scope items decomposed here** — they are a separate future milestone, not deferred sub-items of this spec.

## SKIPPED

None. See [SKIPPED.md](SKIPPED.md) (empty — single-task spec mode).
