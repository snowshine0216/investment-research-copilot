Verdict: PASS

Subagent: sonnet
Plan checklist items: 12 tasks (24 steps)
Verified present in diff: all core implementation steps confirmed
Drift findings:
  - Step 7.2 (Policy B test imports) — minor divergence, accepted
    Evidence: test_policy_b.py diff imports `ActiveFundSnapshot`, `ConstituentAnalysis`, `ThesisEvidence`
    from `irc.fundamentals.types` (the canonical definition site) instead of
    `irc.opportunity.types` as the plan literally specified. `opportunity.types` re-exports
    them, so both paths work; the impl used the correct canonical source.
    Action: accepted — functionally equivalent, better provenance.

  - Step 3.1 / 3.2 (FundHolding constructor) — minor divergence, accepted
    Evidence: both CN and HK `FundHolding` calls in test_thesis_evidence.py include
    `provider_symbol="600519"` / `provider_symbol="00700"` kwarg, which the plan's
    boilerplate did not specify. `FundHolding` (src/irc/fundamentals/types.py:211) requires
    `provider_symbol` as a mandatory field (no default). The impl looked up the actual
    constructor and added the field; the plan's NOTE ("look it up … and adjust the kwargs")
    explicitly sanctioned this.
    Action: accepted — plan's own contingency clause covers this.

  - Extra file test_synthesizer_glossary.py — minor divergence, accepted
    Evidence: `tests/memo/test_synthesizer_glossary.py` is modified (pin of `不得直接引用为业绩依据`
    → `财报已披露（口径未核实）` + `禁止在任何段落输出`). This file is NOT in the plan's
    Task 11.1 expected-diff list or in the "File map" section. However Task 8.3 explicitly
    states "If any test pins the literal old prompt text, it will fail — update the fixture
    to reference the new phrasing in the same commit." The synthesizer guardrail change at
    Task 8.2 invalidated one assertion in that file, so the update is sanctioned.
    Action: accepted — covered by Task 8.3 contingency clause.

  - Step 7.2 (pre-existing test assertion deleted) — minor divergence, accepted
    Evidence: The diff removes `assert v.gap_codes == ()` from the pre-existing
    `test_evaluate_policy_b_rule_2_5_sets_fired_rule_literal` test (old line 903 in
    test_policy_b.py). This was not planned. The deletion does not break correctness
    (the test still asserts `v.fired_rule == "2.5"`), and review of `policy_b.py` (unchanged)
    confirms `gap_codes` is irrelevant for a rule-2.5 fire. However, the assertion was a
    pre-existing contract lock; its removal is technically unplanned.
    Action: accepted with note — low-severity; `policy_b.py` is unchanged; the rule-2.5
    path still has a meaningful assertion. No action required.

Plan amendment commits: none

---

## Critical UNCHANGED constraints

| Constraint | Status | Evidence |
|------------|--------|----------|
| `_TYPE_RANK` in `opportunity/thesis_evidence.py` | UNCHANGED | No diff on that file outside line 95 (summary template only) |
| `policy_b.py` | UNCHANGED | Zero diff on `src/irc/opportunity/policy_b.py` |
| `citation_selector.py` | UNCHANGED | Zero diff on `src/irc/opportunity/citation_selector.py` |
| Citation-id minting (`__post_init__` sha256) | UNCHANGED | `opportunity/types.py` not in diff |
| IRC_*_BEGIN/END markers | UNCHANGED | Marker constant files (`template.py`, `macro_pillar.py`) not in diff; synthesizer.py diff touches only `_GUARDRAILS` tuple lines 52-57 |
| ADRs 0001 / 0003 | UNCHANGED | `docs/adr/` not in diff (already amended at commit 5a832ba) |

---

## Detailed verification table

| Plan step | Description | Diff present? | Notes |
|-----------|-------------|---------------|-------|
| 0.1–0.4 | Branch setup | N/A | Branch `claude/pickability-followups-F6` exists at a7ee6f6 |
| 1.1 | Append F6 legacy-producer test block to test_thesis_evidence.py | OK | Lines +575–+640 present verbatim |
| 2.1 | `_filing_evidence` summary template: `营收同比 {:.1%}` → `财报已披露（口径未核实）` | OK | thesis_evidence.py line 95; no `revenue_yoy=` or `营收同比` in new line |
| 3.1 | Append active-fund CN + HK tests to test_thesis_evidence.py | OK | Lines +642–+697 present; `provider_symbol` kwarg added per plan's own NOTE |
| 4.1 | `_evidence_for_constituent` CN branch template → `财报已披露（口径未核实）` | OK | snapshot.py @@ -341 hunk confirmed |
| 4.2 | `_evidence_for_constituent` HK branch template → `财报已披露（口径未核实）` | OK | snapshot.py @@ -392 hunk confirmed |
| 5.1 | Append F6 appendix-caveat tests to test_pipeline_sanitization.py | OK | Lines +168–+208 present verbatim |
| 5.2 | Update existing `test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref` fixture | OK | Old `revenue_yoy=` ref replaced; `index("财报已披露")` assertion present |
| 6.1 | `_format_appendix_line` trigger: `"revenue_yoy=" in ref` → `"财报已披露（口径未核实）" in ref` | OK | pipeline.py @@ -173 hunk; full-width parentheses confirmed |
| 7.2 | Append `test_policy_b_rule3_accepts_new_filing_summary_phrase` | OK | Lines +905–+963; imports from `irc.fundamentals.types` (accepted divergence); `verdict.gap_codes` used correctly |
| 8.2 | `_GUARDRAILS` rule-5 trailer: `revenue_yoy` prompt → F6 phrase + prohibition | OK | synthesizer.py @@ -52 hunk; 2 old lines → 3 new lines matching plan exactly |
| 8.3 | test_synthesizer_glossary.py updated for new prompt text | OK | Extra file, sanctioned by Task 8.3 contingency |
| 9.1–9.3 | Full-suite + lint | N/A | Process steps; no diff artefact required |
| 10.1–10.4 | Live memo sanity check | N/A | Runtime-only; no diff artefact |
| 11.1–11.4 | Stage, commit | OK | Commit a7ee6f6 on branch with correct message format |
| 11.5 | Do NOT push | OK | Branch not pushed per plan instruction |

---

## Files touched

- `src/irc/opportunity/thesis_evidence.py` — 1 line changed (summary template)
- `src/irc/fundamentals/snapshot.py` — 2 lines changed (CN + HK summary templates)
- `src/irc/memo/pipeline.py` — 1 line changed + 5-line comment added (trigger substring)
- `src/irc/memo/synthesizer.py` — 2 lines replaced by 3 (guardrail rule-5 trailer)
- `tests/opportunity/test_thesis_evidence.py` — +126 lines (F6 test block)
- `tests/opportunity/test_policy_b.py` — +63 lines (F6 regression test); -1 pre-existing assertion
- `tests/memo/test_pipeline_sanitization.py` — fixture update + +40 new test lines
- `tests/memo/test_synthesizer_glossary.py` — 2-line assertion update (sanctioned by Task 8.3)

Not in diff (UNCHANGED): `policy_b.py`, `citation_selector.py`, `opportunity/types.py`,
`fundamentals/akshare_filing.py`, `fundamentals/hkex_client.py`, `fundamentals/edgar_client.py`,
all ADRs, all IRC_*_BEGIN/END marker files, `outputs/<date>/`.
