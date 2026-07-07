# Item 004 — Offline replay runtime proof (Task 5, AC6/AC7)

Replay executed 2026-07-07 against the real on-disk artifacts (`data/rotation/board_series.json`,
`data/monitor/stock_industry_map.json`, `data/narrative_holdings/`), no network. Script:
`<scratchpad>/replay_004.py` (not committed — not a fixture, references the 2.9 MB
`board_series.json`).

Observed output:

```
active_boards=21 funds=446 seen_syms=699 unresolved_names=0
PRE-FIX  candidates=0 coverage=67.8016 unmapped=331
POST-FIX candidates=38 raw_pre_cap=111 coverage=67.8016 unmapped=331
per_board(raw active >=10%)={'BK1036': 69, 'BK0465': 19, 'BK0727': 15, 'BK0474': 3, 'BK1044': 3, 'BK0473': 1, 'BK1259': 1}
ALL INVARIANTS PASS
```

Exit code 0.

Note: integers are a drifting snapshot; the gate is the invariants (review-time 96/34 →
2026-07-07 replay 111/38, both pre-fix=0, both cap-biting, both coverage-identical). The fix
moves *candidates* 0 → nonzero; it never moves the coverage diagnostic.

Cross-check (AC7/G2/G4): `coverage=67.8016 unmapped=331` matches the git-tracked
`outputs/2026-07-06/rotation/rotation_radar.json` `diagnostics.holdings_coverage_pct=67.8016`
and `len(diagnostics.unmapped_syms)=331` exactly.

Invariant gates, all passing:
- INV-iii: pre-fix (names fed as codes) candidates == 0 — observed 0
- INV-i: post-fix candidates > 0 — observed 38
- INV-ii (coverage bound): raw_pre_cap >= capped candidates — observed 111 >= 38
- INV-ii (cap bites): max per-board raw count > CAND_TOP_N (10) — observed max 69 > 10
- AC7/G4: coverage_pct byte-identical pre/post — observed 67.8016 == 67.8016
- locked: all seen 行业 names resolve to a board — observed unresolved_names=0
