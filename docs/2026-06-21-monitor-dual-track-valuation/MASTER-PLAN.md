# MASTER-PLAN — Monitor dual-track valuation + False-Cheap clamp

**Mode:** spec
**Project type:** non-web    # Python `irc` CLI / DuckDB / pandas — no browser surface → post-ship verifier is `/verify` (NOT `/qa`)
**PR shape:** A    # per-item PR into the feature branch (no `--rollup` given)
**Base (protected):** main — NO "merge to main" opt-in this turn
**Feature branch (synthesized):** `autodev/monitor-dual-track-valuation-feature` (off `main`, pushed)
**Per-item branch prefix:** `claude/monitor-dual-track-valuation-`

## Per-mode skill skips (spec mode)

| Phase | Skill | This run |
|-------|-------|----------|
| spec | `superpowers:brainstorming` | ⏭️ SKIPPED — user authored the spec (verbatim copy in `items/001-spec.md`) |
| grill | `grill-with-docs` | ⏭️ PRE-COMPLETED — spec was grilled 2026-06-21 (Q1–Q8 resolved inline; CONTEXT.md updated; memory `project-monitor-dual-track-valuation-grill`). Orchestrator MUST NOT auto-invoke. |
| plan | `superpowers:writing-plans` | ✅ RUNS (Opus) — **ENTRY phase** — reads the refined spec, turns §7 slices into a concrete plan |
| impl | `superpowers:subagent-driven-development` | ✅ RUNS (Sonnet) |
| drift | in-prompt diff-vs-plan | ✅ RUNS (Sonnet) |
| ship | `/ship` (primary), `gh pr create` last resort | ✅ RUNS — opens PR + docs + inline review |
| verify | `/verify` (non-web branch of the XOR — **NOT** `/qa`) | ✅ RUNS (Sonnet) |
| pr-review | `/code-review` | ✅ RUNS (Sonnet) on the open PR |
| fix | Sonnet triage | runs if any of the 3 post-ship verdicts FAIL |
| merge | `gh pr merge --squash --delete-branch` into the **feature branch** | pre-merge gate enforced |

## Model contract
- Orchestrator: session default (no override).
- Plan: **opus**. Impl / drift / verify / pr-review / fix: **sonnet**.

## Build-critical constraints (from the grill — see memory + spec Q1–Q8)
- **Coverage crisis (Q8):** aggregate over the **FULL disclosed basket (~top-10)**, NOT flow's top-5 (top-5 NAV coverage 26–41% = fatal). **Monitor coverage floor = 0.40** (deliberate divergence from opportunity's `lookthrough._COVERAGE_FLOOR=0.50`). Coverage uses the **NAV denominator** `Σ covered weight_pct / 100.0`.
- **Data source (Q1):** Option A is **per-symbol** — `stock_board_industry_name_em` (industry-avg PE, 1 call/day) + `stock_individual_info_em` per-symbol classification (~15–25 deduped cached calls/run, the flow_fetch contract). Direct CN endpoint, never raises, per-day JSON cache.
- **018132 fiction (Q6):** all 7 active funds have `tracked_index=NaN` → resolve look-through → bottom-up. NO live fund uses the index valuation path. Test index dispatch via a **synthetic fixture fund**, never 018132.
- **Methodology REPLACEMENT (Q5):** bottom-up cross-sectional REPLACES portfolio-harmonic percentile. **Delete** `src/irc/monitor/lookthrough.py` + `_resolve_lookthrough` + `tests/monitor/test_lookthrough.py` (opportunity `lookthrough_valuation.py` STAYS). Add `ValuationResolution.path: Literal["index","lookthrough"]`, short-circuit look-through. Feed gate: `path=="lookthrough"` AND `holding_metrics` non-empty (so 009225 qdii keeps `valuation_no_anchor`).
- **Scoring:** `self_score = valuation_state_score(stock.valuation_state)`; `industry_score` additive raw-`r` bands `0.70/0.90/1.10/1.20` (asymmetric); `r = stock_pe/industry_avg_pe`; blend `0.60·self + 0.40·industry`; industry-N/A → self-only. **Clamp: hard-0** (NOT `min(blend,0)`) when `self_score>0 AND r≥1.2`.
- **Reasons:** `KNOWN_NA_REASONS` 10→12 (add **factor** codes `valuation_no_data`, `valuation_no_coverage`, both with reachable `_valuation` branches). `industry_no_data` + `false_cheap_clamp` are **per-stock HoldingMetric reasons, NOT factor reasons** — never add to `KNOWN_NA_REASONS`.
- **Versioning:** `_ENGINE_VERSION "2"→"3"` (global); trace `_SCHEMA_VERSION "3"→"4"`.
- **ADR 0020** must be authored (records all the above rationale).
- ⚠️ **Test scope on signature changes** (FactorInputs gains a trailing field): run `tests/monitor/`, `tests/monitor/eval/`, and `tests/commands/test_monitor_cmd*` **per-file** — the whole `tests/commands/` dir HANGS on suite ordering.

## Loop exit contract (per item)
All three post-ship verdicts PASS / PASS-WITH-NITS: `/verify` + inline review (from `/ship`) + `/code-review`. No retry budget; environmental stops only.
