Verdict: PASS

Subagent: opus
Questions resolved: 7
Docs touched:
  - CONTEXT.md (commit 46076fe1)
  - docs/2026-07-07-review-followup/items/004-spec.md (commit 46076fe1)
Spec refined: items/004-spec.md (commit 46076fe1)

No ADR created (G6: three-of-three test fails — L2 bug fix executing a locked approach,
consistent with ADR 0023). No spec-vs-ADR contradiction found (G5), so no FAIL condition.

## Resolved decisions

- Q: Translation-map source — build `{board_name: board_code}` from `states` (mature boards
     only) or from the full board universe?
  A: Keep `states`, per locked AC1.
  Rationale: `board_signals` (composite.py:31) drops boards < MIN_TD=20 td, so the map covers
     mature boards only — harmless for candidates (active boards are mature by construction),
     moot on the 07-06 proof date (all 200 boards mature).
  Doc impact: CONTEXT.md "Stock-industry map" term.

- Q: AC7 coverage figure (62.16% / 389 unmapped) — is it right?
  A: No — correct to 67.80% / 331 unmapped.
  Rationale: matches the git-tracked outputs/2026-07-06/rotation/rotation_radar.json (67.8016)
     and an independent replay; byte-identical pre-fix vs post-fix.
  Doc impact: spec AC7 strike-through.

- Q: AC6 replay integers (96 raw / 34 capped; per-board 58,19,15,2,1,1) — hard gate or snapshot?
  A: Illustrative snapshot; gate on invariants, not integers.
  Rationale: current-artifact replay yields 108 raw / 35 capped (cache grew); the spec's own
     Non-goals admit artifacts drift. Invariants: candidates > 0, cap bites, pre-fix = 0.
  Doc impact: spec AC6 + Q2 strike-through.

- Q: Does the fix change the coverage diagnostic (regression risk)?
  A: No — pre-fix and post-fix coverage are identical on the proof date.
  Rationale: every seen 行业 name resolves to a board code, so the fix moves candidates 0→~35,
     never the coverage/unmapped diagnostic on 07-06.
  Doc impact: none (folds into the AC7 correction).

- Q: Does the fix contradict ADR 0023 (D1/D3)?
  A: No — it upholds D1 (canonical unit = EM board keyed by code); D3 is silent on slot contents.
  Rationale: the false "codes-in-slot" claim lived only in the industry_map_store.py docstring
     (AC3 fixes it); no load-bearing ADR conflict → Verdict PASS.
  Doc impact: none.

- Q: Is a new ADR warranted?
  A: No.
  Rationale: three-of-three (hard-to-reverse + surprising + real trade-off) fails — a ~2-line
     pure translation, trivially reversible, no version/store-shape change; obvious minimal fix.
  Doc impact: none.

- Q: Terminology — name-vs-code and where translation lives?
  A: Store holds 东财行业 names (f100), never codes, for both monitor and radar; radar
     translates name → board code at its own join (resolve_candidates), never in the store.
  Rationale: sharpens the exact confusion that made the join dead code; enforced by AC3.
  Doc impact: CONTEXT.md "Stock-industry map" term.
