Verdict: PASS

# Item 002 grill report — `ActiveFundSnapshot` dual-leg thesis gate

## Subagent

autodev-dispatched grill subagent, 2026-07-03, branch
`autodev/todos-critical-fixes-feature`. Skill: `grill-with-docs`
(autonomous mode — recommended answers auto-accepted; every code-location
and literal claim in the spec was re-verified against source, not trusted
from the spec's own text).

## Questions resolved (7)

1. **Union vs ADR 0003 rule 2.5 / dual-coverage gate in published
   scenarios** — no contradiction. Exhaustive over `evaluate_policy_b`
   verdict shapes (`policy_b.py:217–366`): publishable ⟺ rules-3+4-passed
   (constituent dual-leg guaranteed) ∨ rule-2.5-passed (`fund_level_evidence`
   dual-leg guaranteed, `:283–312`). QDII bypasses Policy B (§6,
   `FundLevelSnapshot` branch — untouched). **Union decision SURVIVED the
   Policy-B stress test**, with one hardening (Q2).
2. **Found the one hole: empty-flattened + dual-leg-fund_level rule-2.5
   row** (all top-N constituents pure-failure — reachable per ADR 0003 §7's
   2026-06-04 reconciliation). A naive union-first check would flip this
   *published* row `evidence_insufficient → intact` while passing AC5 as
   originally written. Resolution R1: empty-flattened guard runs FIRST
   (load-bearing); AC5 gains fixture (b); Goal/AC10/Q3(c) amended.
   Intact-ward resolution rejected as out of scope (ADR 0003 §8 Alt B).
3. **Reason literals** — existing literals byte-verified
   (`thesis_evidence.py:388/:392/:371`). New AC6 literals deliberately NOT
   the FundLevel shared literal (direction-specific = better diagnostics);
   exposure audit proves they can never reach a SAME-3-relevant or
   citation-bearing artifact (publishable rows never carry them; memo pool
   keeps state segment only, `evidence_pool.py:89`; failure renderer reads
   4 non-conclusion fields; `RejectionRecord` has no reason field,
   `rejection_log.py:40–51`; alias-builder keys on ids/names).
4. **H3 partition** — provably unchanged: predicate is `evidence_gaps`-only;
   `top_holdings_broker_thin` confirmed advisory (`advisory_gaps.py:23–26`);
   no test asserts `intact` on data-only active fixtures; gapped-row
   internal flips change zero canonical output bytes.
5. **eval-funds sensitivity** — confirmed: `FundEval` carries
   `thesis_state`/`core_dca`/`note_cn=opportunity_reason`
   (`fund_eval.py:58–72`); `_intact_snapshot` already dual-leg. AC9 sound.
6. **Terminology** — rejected "dual-coverage gate now applies to both
   snapshot shapes" (conflates the auditor's publishability gate with the
   thesis heuristic); CONTEXT.md gains the distinct term **"Dual-leg thesis
   heuristic"** instead.
7. **ADR bar** — three-of-three met (hard to reverse, surprising
   presence-only union + load-bearing ordering, real trade-off among three
   alternatives) → amendment-in-place **ADR 0003 §8** per §7's own
   Alternative B precedent; no new ADR.

## Docs touched

- `CONTEXT.md` — new **"Dual-leg thesis heuristic"** entry (after the
  dual-coverage gate entry), incl. the presence-only union, empty-first
  guard, insufficient-not-under_pressure choice, and an _Avoid_ note.
- `docs/adr/0003-failure-mode-policy-b.md` — status line amended; new
  **§8 Thesis-level dual-leg union for `ActiveFundSnapshot`** (three locked
  properties + three rejected alternatives + literal-exposure note).

## Spec refined (`items/002-spec.md`, in place)

- Goal: strike-through + correction (union claim scoped to non-empty
  flattened evidence; empty-first guard documented as load-bearing).
- AC5: now TWO fixtures — (a) plain empty, (b) empty + dual-leg
  `fund_level_evidence` (the naive-implementation killer).
- AC10: strike-through + split into the two rule-2.5 sub-cases (AC4 /
  AC5(b)).
- Q3(c): bracketed R1 caveat on the invariance proof.
- Appended **## Resolved decisions** R1–R7.

## Resolved decisions list

- R1 — empty-flattened guard precedes the union leg check (load-bearing;
  AC5 fixture (b)); intact-ward resolution rejected for this item.
- R2 — union decision survives the Policy-B stress test in every published
  scenario (with R1); QDII path untouched.
- R3 — reason literals verified byte-for-byte where shared; new
  direction-specific literals never reach SAME-3/citation artifacts.
- R4 — H3 partition provably unchanged (gaps slot locked; rejections.json
  carries no conclusion fields).
- R5 — eval-funds output shape confirmed sensitive to `thesis_state`;
  AC9's surface correct.
- R6 — new CONTEXT.md term "Dual-leg thesis heuristic"; do NOT extend the
  dual-coverage gate entry.
- R7 — ADR 0003 §8 addendum (amendment-in-place), not a new ADR.
