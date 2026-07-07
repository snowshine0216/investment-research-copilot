# Item 002 — implementation notes (deviations + triage)

- T2: transient edit slip (duplicate `|memo` token in CLAUDE.md `--from` line) caught by the implementer's own diff review pre-commit — never committed. No action.
- T4: `evals/README.md` "seven pure scorers" number-swap left the 6-name parenthetical (brief scoped only the token) → combined review Minor → fixed `456e79ff` with the verified 7-name list (+`aggregate_flow`).
- Post-review addition BEYOND 002-c's literal enumeration: DXY-staleness TODOS registration (review TL;DR finding with no entry anywhere; deferred=registered contract; grounded at 2026-06-16 via outputs/2026-07-04/gold_regime.json; item 001's weekly digest cited as interim mitigation) → `456e79ff`. aggressive-but-small → triage: accepted, documented for the close-out roll-up.
- Deferred-by-design residuals confirmed intentional by the review itself: "~86 boards" wording in CONTEXT.md/rotation README stays until R-3 (pagination verification) resolves.
- Process: Tasks 2+3 and 4+5 each ran as one combined dispatch (mechanical doc clusters); one combined factual-accuracy review covered T2-5; T1 (test, solo) landed RED exactly as predicted; T6 verification-only (red→green 4/4, all D-item greps pass, nothing to commit).
