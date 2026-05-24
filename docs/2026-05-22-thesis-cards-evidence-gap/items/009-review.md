# Item 009 inline review verdict (from `/ship` steps 8+9)

**Verdict:** PASS-WITH-NITS (after pre-PR fix-round)
**Captured by:** 3 parallel subagents (`pr-review-toolkit:code-reviewer` + `pr-review-toolkit:silent-failure-hunter` + adversarial `general-purpose`) — dispatched as item 009's POST-ship reviewers; serves as the inline-review verdict per the autodev /ship steps 8+9 contract.
**Date:** 2026-05-24
**Branch:** `autodev/thesis-evidence-009-citation-gate-block-mode`
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/63

## Findings closed in fix-round

### P0
1. **Step 2a `replace(evidence_gaps=...)` overwrote pre-existing gaps** (code-reviewer P0.1) — currently safe per H3 but fragile. Fix: APPEND.
2. **Shadow-log write failure swallowed gate raise** (silent-failure P0.1 + P0.2) — opportunity & memo. Fix: try/except around shadow write; gate verdict still applies.
3. **Gate ordering hid constituent pure-failure** (silent-failure P0.3) — Step 2a's demotion removed rows from publishable before Step 2b's constituent check. Fix: Step 2b runs on the FULL publishable set BEFORE Step 2a's demotion (Step 2b is the unconditional-fatal gate anyway).

### P1
4. **`warn` mode silently demoted op-rows** (code-reviewer P1.4) — docs said log-and-continue but op-rows were always removed. Fix: Step 2a demotion CONDITIONAL on `enforce_mode == "block"`.
5. **memo_cmd shadow log fallback hardcoded `canonical_path: False`** (code-reviewer P1.5) — production `out_dir` is always canonical. Fix: `_is_canonical_out_dir(out_dir)` import + call.
6. **Canonical-path override silent** (silent-failure P1.1) — operator setting `IRC_CITATION_ENFORCE_MODE=warn` on canonical path got no signal. Fix: stderr WARN when override fires AND env differs from `block`.
7. **`find_uncited_conclusions` wrong-owner short-circuit** (silent-failure P1.2) — first wrong-owner marker bailed before checking subsequent markers; legitimate `uncited_conclusion` silently suppressed when remaining markers had only one of two legs. Fix: don't return early; emit both findings.
8. **2a-pass/2c-fail asymmetry in warn/off mode** (adversarial finding 3) — provenance mismatch passed 2a but failed 2c; row silently leaked in warn/off mode. Fix: parallel Step 2c demotion (in `block` mode only) with same APPEND semantics.

## Deferred (P2 / Notes / design)

- **Env-var trailing-space / case sensitivity** (adversarial 2) — fail-safe lands at `block`; defer.
- **Shadow log RMW race in concurrent runs** (adversarial 4) — sequential pipeline by convention; no fcntl lock; defer.
- **`build_constituent_cited_map` uncaught RuntimeError** (silent-failure note) — intended loud failure per ADR 0001; defer.
- **`_resolve_enforce_mode` env-var ignored on canonical path** (code-reviewer note 3) — by design per Q2 grill resolution; canonical paths must not be silenceable. Documented.
- **`_section_at`/`_subsection_at` early break fragility** (code-reviewer P0.2) — currently safe (spans naturally ascending); defer.
- **Symlinked canonical path edge** (adversarial 1 note) — `Path.resolve()` follows symlinks so a symlinked canonical path resolves to its target; if the target isn't under `outputs/`, the canonical-path override doesn't fire. Documented; defer.

## Verification

- `pytest tests/integration/test_publishable_set_lockdown.py tests/integration/test_citation_audit_gate.py tests/memo/test_numeric_audit.py tests/opportunity/ -q`: **426 passed / 2 skipped**.
- Item 008 baseline: **24 passed / 1 skipped** with gate live (Q6 contract holds).
- Ruff clean on item 009 touched files.

## Recommendation

**PASS-WITH-NITS.** All 8 actionable findings closed in `fix(009)` commit. Deferred items are P2/design-justified. Ready for `gh pr merge`.
