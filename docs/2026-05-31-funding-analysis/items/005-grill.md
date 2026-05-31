Verdict: PASS

Subagent: opus
Questions resolved: 7
Docs touched:
  - CONTEXT.md (commit 8504e7a)
  - docs/adr/0011-adversarial-debate-advisory-only.md (commit 8504e7a)
Spec refined: items/005-spec.md (commit 8504e7a)

## Resolved decisions

- Q (G2, key): Is `thesis_falsify` truly unwired, and do we build a fresh card-shaped runner or reuse `research/falsification.py`?
  A: Confirmed unwired — `grep -rn '"thesis_falsify"' src/` empty; the only definition `research/falsification.py::generate_falsification` has zero callers in `src/` and is theme-shaped (`thesis_summary: str`, pre-resolved `route`). Build a FRESH card-shaped defend+falsify pair in `src/irc/opportunity/debate.py` over `OpportunityRow` fields.
  Rationale: Reusing the theme falsifier forces a lossy card→prose flatten and couples opportunity→research (wrong dependency direction). Two single-tuple result types (`DefenseResult` / `FalsificationResult`) in two packages is correct.
  Doc impact: CONTEXT.md `DefenseResult` / `ThesisDebate`; ADR 0011 §3.

- Q (G1): Markdown or machine-readable for the debate file?
  A: Markdown (`thesis_debate.md`), human-reader register, peer of `discipline_report.md`.
  Rationale: No tool consumes it; advisory prose matches the only other advisory opportunity output.
  Doc impact: CONTEXT.md `thesis_debate.md`.

- Q (G3): Row-level or constituent-level debate?
  A: Row-level — one debate per publishable `OpportunityRow`.
  Rationale: Constituent-level is N× LLM cost and YAGNI; mirrors H3 (only `thesis_state`-bearing rows get downstream treatment).
  Doc impact: CONTEXT.md `Bull/bear debate (--adversarial)`.

- Q (G4): Is `--adversarial` allowed on canonical `outputs/<date>/` paths?
  A: Yes. The `--limit` canonical rejection exists only because `--limit` caps the active-fund set and corrupts the publishable set (`validate_cli_args` / `_build_rows:777-783`); `--adversarial` adds a file and touches no row.
  Rationale: The advisory file cannot corrupt a canonical artifact, so no canonical-path restriction is warranted.
  Doc impact: CONTEXT.md `thesis_debate.md`; ADR 0011 §2.

- Q (G5): Is `thesis_debate.md` exempt from the two-run byte-equality / determinism contract?
  A: Yes — explicitly exempt. The contract is scoped to the deterministic renderers (`memo.md` + `discipline_report.md`, ADR 0004 §Consequences) and the five canonical artifacts (item 008 lockdown); an LLM-prose artifact is outside both. The pure renderer `compose_thesis_debate_markdown` is still deterministic; only the upstream LLM `arguments`/`conditions` are not.
  Rationale: Prevents a future contributor from "fixing" the apparent violation or adding the file to the lockdown's byte-equality assertion.
  Doc impact: CONTEXT.md `thesis_debate.md`; ADR 0011 §2.

- Q: Is the advisory-only / non-canonical / state-free posture ADR-worthy under three-of-three?
  A: Yes — ADR 0011 written. The flag/file are reversible, but emitting a non-deterministic LLM artifact from the deterministic `_write_opportunity_outputs` boundary, exempt from the determinism/lockdown contract, is surprising-without-context and the chosen one of three real alternatives (reuse theme-falsifier / make-canonical / let-it-set-state). Corrects D11's original "No new ADR".
  Rationale: Three-of-three met on the boundary/exemption decision, not on the trivially-additive flag alone.
  Doc impact: ADR 0011; D11 strike-through in items/005-spec.md.

- Q: Any spec claim FALSE against the code?
  A: None. The KEY claim (`thesis_falsify` registered but ZERO production call-sites) is TRUE. Also verified TRUE: the 5-canonical-artifact set + `atomic_write_text` write boundary in `_write_opportunity_outputs`; H3 partition predicate `evidence_gaps == ()`; SAME-3 set-equality scope; `OpportunityRow` carrying `name_cn`/`thesis_state`/`opportunity_reason`/`thesis_evidence`; `resolve_route` task-by-name with extra-tasks-allowed (`REQUIRED_TASKS` = memo_synthesis/memo_audit only); `--rebuild-fundamentals` attach layer in `cli.py:115-131`; `thesis_state` sole-ownership by `derive_thesis_from_evidence` (ADR 0003); the `RUN_LIVE_LLM_TESTS=1` + `DEEPSEEK_API_KEY` double-gate in `tests/llm/test_live_smoke.py`.
  Rationale: No factual strike-through required; the only correction was reversing D11's ADR judgement.
  Doc impact: none (D11 ADR reversal only).
