# MASTER-SPEC — actionable-ops

Mode: **backlog** (3 distinct items from the 2026-06-10 implementation review)
Source: chat-described backlog (user: "do all of them one by one, then validate and point me at the report")

## Context

Review of the `irc` pipeline found the system is good for weekly buy-side guidance but
not yet operational for real investing: (a) sell signals are computed by the discipline
layer but never surfaced in the decision report (`portfolio_action` hard-coded to
`"no_trade"` at `src/irc/decision/gates.py:191`; Phase 3 TODO at
`src/irc/decision/models.py:12`); (b) `inputs/account.yaml` holdings are only used for
build-vs-steady-state mode selection, never for current-vs-target weight diffing; (c) no
scheduler or notifier exists despite a fully headless CLI with distinguishable exit
codes (0/1/2/3/4/5) and machine-readable outputs; (d) the valuation fundamental axis
(ADR 0012, Phase D) is built but OFF, and README contradicts `config/llm.yaml` on memo
LLM routing.

## Items

| id  | Title | Scope | Classification |
|-----|-------|-------|----------------|
| 001 | Sell surfacing + holdings-aware deltas | Wire `inputs/account.yaml` holdings into current-vs-target weight diffing; emit `portfolio_action` buy/trim/exit driven by existing discipline `risk_action` signals (`exit_review`/`trim_review`); add Sell/Review section to `decision_report.md`; remove the `"no_trade"` hard-code | **IN** |
| 002 | Local scheduler + notifier | launchd plists for daily-light (`irc ingest → opportunity → decision`, trading days ~17:30 CST) and weekly full run; thin notify script consuming exit codes + `decision_report.json` (`actionable_buy_count`, trigger status, sell/review counts) + `PIPELINE_HALTED.md` + `STALE_INGEST.md`; macOS notification + optional Feishu webhook | **IN** |
| 003 | Valuation axis ON + docs fix | Enable the valuation fundamental axis per the existing Phase D plan (ADR 0012, shadow→on); fix the README vs `config/llm.yaml` memo-routing mismatch | **IN** |

## OUT items

None. All three items are implementable without human input, credentials beyond the
existing `.env`, or org policy changes.

## Run-level validation (after all merges)

- Workflow-completeness audit (per-item verdict files present)
- Diff-scoped pytest vs known-failing baseline (main is NOT green: 8 known pre-existing
  failures + flaky e2e research gate — see project memory)
- `uv run ruff check src tests`
- Real end-to-end `irc decision` run against current outputs
- Final report for the user
