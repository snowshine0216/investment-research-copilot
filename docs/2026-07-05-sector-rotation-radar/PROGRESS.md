# PROGRESS — Sector rotation radar

**Mode:** spec · **Project type:** non-web · **PR shape:** A · **Feature branch:** `autodev/sector-rotation-radar-feature` (base `main`, prep commit `2c1b844b`)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped-by-mode · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|-----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ | ✅ | ✅ | 🔄 | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

<sub>branch: ✅ `claude/sector-rotation-radar-001` (off `autodev/sector-rotation-radar-feature`)</sub>
<sub>impl: ✅ `d92321a7..bd1d75bb` (18 tasks; new `src/irc/rotation/` package + `rotation_cmd.py` + CLI + 15:45 wrapper chain + docs; 74 tests green). Survived a 2-worker concurrent race on Cluster 4a; 3 review findings fixed (AC8 diagnostics `3f2be6da`, composite flow5 dark-factor `ac517d07`); §8 daily top-up deferred → follow-up **F6** (documented in spec §12 / CONTEXT / docstring).</sub>

**Evidence cells** (filled as phases pass):

- **001-spec** ✅ → [`items/001-spec.md`](items/001-spec.md) (verbatim user spec; Goal + AC1–AC12 present)
- **001-grill** ⏭️ → user-grilled (spec status "grilled + locked"; ADR 0023 + CONTEXT "Sector rotation radar" section are the grill artifacts). Orchestrator does not auto-invoke grill in spec mode.
- **001-plan** ✅ → [`items/001-plan.md`](items/001-plan.md) (writing-plans; 18 tasks / 90 steps; commits `e50a3e2a` + amendment `1cb3d3f5` wiring pe_pctl/chase_risk per §6; all AC1–AC12 mapped, 31 pytest verification cmds)
- **001-verify** ⏳ → `/verify` (non-web; NOT `/qa`)
- **001-drift** ✅ → [`items/001-drift.md`](items/001-drift.md) (commit `34c6dc08`; 18/18 tasks present; F6 deferral documented in 4 places = accepted-divergence; `flow_leg_dark`+AC8 = accepted-improvements; only nit = `rotation_cmd.py` 245 lines, cosmetic)
- **001-pr-review** ⏳ → `/code-review` on the open PR

## Notes

- QA column omitted from the table on purpose: project type is **non-web**, so the post-ship verifier is `/verify` (XOR — never `/qa`).
- Prep commit `2c1b844b` (f127→f100) landed at the feature-branch base per user direction; it is a prerequisite (spec §13-T1/AC1), not a radar item.
