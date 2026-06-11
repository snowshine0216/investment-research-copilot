# PROGRESS — actionable-ops

| id  | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ✅ | ✅ | ✅ claude/actionable-ops-001 | ✅ 4d2dcdf | ✅ | ✅ #124 | ⏭️ | ✅ | ✅ | ✅ | ✅ 2 rounds | ✅ f843669 |
| 002 | ✅ | ✅ | ✅ | ✅ claude/actionable-ops-002 | ✅ 6d6c327 | ✅ | ✅ #125 | ⏭️ | ✅ | ✅ | ✅ | ✅ 3 rounds | ✅ bae6236 |
| 003 | ✅ | ✅ | ✅ | ✅ claude/actionable-ops-003 | ✅ 90a7050 | ✅ | ✅ #123 | ⏭️ | ✅ | ✅ | ✅ | ✅ 0 rounds | ✅ efd8010 |

QA column pre-filled ⏭️ for all items: project type is **non-web** → post-ship verifier
is `/verify` (XOR rule).

## Run-level

| gate | status |
|------|--------|
| run-doc-sync | ⏳ |
| run-final-verify | ⏳ |
| close-out | ⏳ |

## Notes

- Feature branch `autodev/actionable-ops-feature` synthesized off `main` (protected;
  user gave no merge-to-main opt-in) and pushed 2026-06-10.

### 003 evidence
- spec: items/003-spec.md (50428f8); grill: items/003-grill.md PASS (9b79ef0); plan: items/003-plan.md (8135e86)
- impl commits: 88b3845..90a7050 (tests/templates 4 passed; regression-bite verified both locks)
- drift: items/003-drift.md PASS (2162c7e) — 1 accepted incidental (pre-existing ruff baseline noise)
- PR: https://github.com/snowshine0216/investment-research-copilot/pull/123 (ship: items/003-ship.md)
- verify: items/003-verify.md PASS (all 7 AC); review: items/003-review.md PASS-WITH-NITS (/ship 8+9,
  review fix 7afb738); pr-review: items/003-pr-review.md PASS-WITH-NITS
  (comment: pull/123#issuecomment-4668303130)
- merge: squash efd8010 (#123); orphaned verify/pr-review verdict commits recovered via
  cherry-pick 9140d0c+e3f3012 (process note below)

### Process note (binds items 001/002)
Before `gh pr merge`, PUSH the sub-branch so post-ship verdict commits land in the PR —
subagents commit without pushing; merging an unpushed-tip PR orphans their commits.

### 001 evidence (through drift)
- spec: items/001-spec.md (ea1dc6c); grill: items/001-grill.md PASS (02f1d06, ADR 0015);
  plan: items/001-plan.md (ae4cba1)
- impl: f93e706,2c1c9bb,94751d9,c06bfc8,1d82afc,4d2dcdf — 346 passed incl. invariant guards;
  e2e irc decision exit 0
- drift: items/001-drift.md PASS (701ef6c) — 41/41 steps; 2 accepted findings

### 001 evidence (post-ship)
- PR: https://github.com/snowshine0216/investment-research-copilot/pull/124 (items/001-ship.md)
- pre-push fix round 1 (2 P0 + contract + 4 P1): 8039927,30d5dba,b3f3002,9365e16 — items/001-ship-blocked.md
- verify: items/001-verify.md PASS (11/11 AC; e2e irc decision; 814 passed)
- review: items/001-review.md PASS-WITH-NITS (/ship 8+9)
- pr-review: items/001-pr-review.md PASS after fix round 2 (107f45a: latent _reason() bug,
  CONTEXT precedence, dead param; re-verified e378131, 815 passed)
- merge: squash f843669 (#124); local feature reset --hard to origin (spec/grill/plan commits
  subsumed by squash — verified zero unique local content before reset)

### Process note 2 (binds item 002)
Push the feature branch right after spec/grill/plan commits, BEFORE cutting the sub-branch —
otherwise the post-merge local feature diverges from the squash (add/add conflicts).

### 002 evidence (through drift)
- spec: items/002-spec.md (be32078); grill: items/002-grill.md PASS (014e277, ADR 0016);
  plan: items/002-plan.md
- impl: 31ef841..6d6c327 — 46 notify+CLI tests; plutil/bash -n clean
- drift: items/002-drift.md FAIL→PASS (3aae487→16f42fb) — F2 httpx token-leak to launchd logs
  found by drift, fixed 55ecd8a (RED→GREEN + counterfactual re-verification)

### 002 evidence (post-ship)
- PR: https://github.com/snowshine0216/investment-research-copilot/pull/125 (items/002-ship.md)
- fix rounds: drift F2 token leak (55ecd8a); pre-landing 4P0+3P1 (dc8c468,e305f7e);
  adversarial BREAKS set-e/wait (8b01906+6b8ec17); pr-review exit-code catch-all (dc731b9)
- verify: items/002-verify.md PASS (12/12 AC); review: PASS-WITH-NITS; pr-review:
  FAIL→PASS-WITH-NITS (e37bcb0; comment pull/125#issuecomment-4669479737)
- merge: squash bae6236 (#125), fast-forward clean (process note 2 held)

## FINAL STATUS (close-out 2026-06-11)

- Items merged: 3/3 (003 → #123 efd8010; 001 → #124 f843669; 002 → #125 bae6236)
- Items skipped/blocked: none
- Run-level gates: doc-sync PASS (run-doc-sync.md, +863e3f1 gap fix); final-verify PASS
  (run-final-verify.md); workflow-completeness audit PASS (all 18 verdict artifacts)
- Full suite: 3254 passed / 24 failed / 62 skipped — failure set identical to main
  (23 verified failing on main in targeted run; 24th = known hang-prone e2e baseline).
  ZERO regressions. ruff byte-identical to main (124 pre-existing).
- Post-merge follow-up landed on branch: 81c1afb (calendar-independent wrapper tests, #125 flag)
- launchd agents INSTALLED on operator machine 2026-06-10 (com.irc.daily Mon-Fri 17:30,
  com.irc.weekly-full Sat 09:00); README automation section updated (e5d8fbb)
- Feature branch: autodev/actionable-ops-feature
- Feature-branch PR: https://github.com/snowshine0216/investment-research-copilot/pull/126
- Merged into protected branch: no (PR left open for user review)
