# MASTER-SPEC — Trust-Check Fixes for 2026-05-19

**Source:** `outputs/2026-05-19/adversarial_review_trust_check.md`

The trust-check doc audits whether a non-finance reader can fully trust
`outputs/2026-05-19/decision_report.md`. Its short answer is **"no, not
yet."** The doc lists 6 high-harm gaps (A1–A6), 5 medium-harm clarity
gaps (B1–B5), and consolidates them into a 7-item priority fix list.

## Context: what's already shipped (do NOT redo)

The previous autodev-loop (`2026-05-19-adversarial-fixes/`) shipped 15
signal-layer fixes (v0.8.5.1), most relevant being:

- **009 — memo audit becomes a publish gate** — refuses to write `memo.md`
  when audit emits a P1; non-zero CLI exit.
- **013 — execution-drift alert** — surfaces drift in `memo.md` §4.
- **014 — FX / QDII diagnostics** — surfaces QDII premium gap in
  `memo.md` §6.x with explicit "数据未采集" placeholders.

Those fixes surface in **`memo.md`**, but the trust-check doc demands
they surface in **`decision_report.md`** — the layperson's primary
artifact. This run closes that gap.

## Scope

**IN-scope (7 items, from the doc's priority fix list):**

| ID  | Item                                                               | Maps to trust-check |
|-----|--------------------------------------------------------------------|---------------------|
| 001 | Add beginner glossary to decision_report.md                        | Priority #7, B3     |
| 002 | Reconcile English `score_action` with Chinese instrument label     | Priority #5, B2     |
| 003 | Collapse venue-blocked list to remediation line when proxy covers  | Priority #6, A5     |
| 004 | Banner execution drift in decision_report.md when > 5pp            | Priority #3, B?     |
| 005 | Surface memo_audit P1 in decision_report Verdict (publish gate)    | Priority #2, A6     |
| 006 | Refuse QDII `actionable` when premium / FX status missing          | Priority #4, A2     |
| 007 | Add "Today's only action" headline                                 | Priority #1, A1, B1 |

Ordering: smallest/lowest-risk first (001–003 are pure rendering;
004–006 are diagnostic logic; 007 is the highest-payoff compositional
fix that depends on 005 + 006).

**OUT-scope (documented in `SKIPPED.md`):**

- Strategy Sanity Check S1–S7 (signal-layer issues). Most are already
  addressed by the v0.8.5.1 bundle; the remaining ones (e.g. S6:
  triggers rarely fire) are systemic strategy decisions not
  user-comprehension fixes.
- Section A3 ("Completeness: 1.00" misleads) — partially mitigated by
  glossary (001); deeper fix would require a separate confidence model.
- The pipeline-state visibility critique (B5) — already addressed by
  pipeline_halted Verdict line in the current decision_report.md
  (visible in the 2026-05-19 sample).

## Workflow

- Feature branch: `claude/trust-check-fixes-2026-05-19` from `main`.
- Each item gets a sub-branch `claude/trust-check-fixes-2026-05-19-NNN`
  with its own PR into the feature branch.
- TDD: write tests against decision_report.py / decision_cmd.py first,
  then implementation.
- Single final PR feature → main when all 7 are green.

## Notes on existing WIP

The uncommitted diff on `main` (decision_cmd.py + report.py + tests)
introduces the `instrument_name` column. That work formalizes as item
**002** — we'll fold the WIP into the 002 branch and add the Chinese
action-label translation on top.
