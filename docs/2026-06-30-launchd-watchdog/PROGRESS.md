# PROGRESS — launchd Wrapper Watchdog + Single-Instance Lock

**Mode:** spec · **Project type:** non-web · **PR shape:** A · **Feature branch:** `claude/thirsty-lovelace-3da881`

Legend: ⏳ pending · 🔄 in progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped-by-mode · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ `claude/launchd-watchdog-001` | ✅ `5888d1e` | ✅ `daf5cc9` | ✅ [#182](https://github.com/snowshine0216/investment-research-copilot/pull/182) | ✅ `983e451` | ✅ PASS-WITH-NITS | ✅ PASS-WITH-NITS | ✅ 1 round `e480f15` | ✅ `e78fcac` |

### Notes
- **spec** ✅ — `items/001-spec.md` (verbatim copy of merged spec PR #180).
- **grill** ⏭️ — user-grilled (rev-2, grill-with-docs). Orchestrator must not auto-invoke in spec mode.
- **plan** ✅ — `items/001-plan.md` (Opus writing-plans, commit `836a427`); 12 tasks, ~50 steps, TDD red-first; harness assumptions + doc anchors verified by orchestrator.
- **impl** ✅ — `5888d1e` (12 commits). Tests: test_run_lib.py 7✓, test_launchd_monitor.py 40✓, test_notify_cmd.py 26✓, ruff clean. 6 deviations reported & resolved (notably: plan's `acquire_lock` EXIT trap used `local lock_dir` → out-of-scope when trap fires; fixed to script-global `_IRC_LOCK_DIR`. Orchestrator verified the fix is correct). Deviations handed to drift for plan-amend.
- **drift** ✅ — `items/001-drift.md` Verdict: PASS (`daf5cc9`). 12 plan items verified, 10 files = spec §7 exactly, 0 unreported drift; plan amended for the 6 known deviations.
- **PR (ship)** ✅ — [#182](https://github.com/snowshine0216/investment-research-copilot/pull/182) (base = feature branch `claude/thirsty-lovelace-3da881`). `items/001-ship.md`. No VERSION bump.
- **review** ✅ — `items/001-review.md` PASS-WITH-NITS (ship steps 8+9: code-reviewer + silent-failure-hunter + adversarial). 0 P0; wait/127 P0 empirically refuted, mkdir-lock TOCTOU dismissed as inherent. 2 test nits → triage-fix; 1 follow-up (locked spec line).
- **verify** ✅ — `items/001-verify.md` Verdict: PASS (`983e451`). Non-web → `/verify` (XOR: `/qa` never runs). All 5 ACs exercised live (rc=124 on timeout, rc=0/7 propagation, grandchild killed, lock acquire/contention/reclaim, wrapper wiring).
- **pr-review** ✅ — `items/001-pr-review.md` PASS-WITH-NITS ([comment](https://github.com/snowshine0216/investment-research-copilot/pull/182#issuecomment-4841056904)). 3 nits, 0 blockers, 0 latent bugs.
- **fix** ✅ — 1 round (`e480f15`): template_wrapper unconditional copy+assert; timing margin 8.0→9.5; lock-held assertion simplified to `== []`. Test-only (production bash byte-identical). Re-confirmed 73 passed + ruff clean. pr-review's other nits dismissed (matches-original SECONDS=0; documented TOCTOU).
- **merge** ✅ — PR #182 squash-merged to feature branch `claude/thirsty-lovelace-3da881` as `e78fcac`; sub-branch deleted. All 6 pre-merge gates passed (non-protected base, ship+drift+verify+review+pr-review verdicts, MERGEABLE, no blocking comments).
- This is the non-web spec-mode path: exactly one of {qa, verify} → `verify`.

---

## Final status (Phase 3 — run complete)

**RUN COMPLETE.** 1/1 IN-scope item merged. 0 SKIPPED. 0 BLOCKED.

- **Items merged:** 001 (launchd wrapper watchdog + single-instance lock) → PR [#182](https://github.com/snowshine0216/investment-research-copilot/pull/182) squash-merged (`e78fcac`) into feature branch.
- **Feature branch:** `claude/thirsty-lovelace-3da881`
- **Feature-branch PR:** [#183](https://github.com/snowshine0216/investment-research-copilot/pull/183) → base `main` (the default/protected branch)
- **Merged into protected branch: no** — #183 left OPEN for user review (no "merge to main" opt-in this turn; the protected-base guardrail held).

### Phase 3 findings
- **Workflow-completeness audit:** PASS — all required artifacts present (ship+PR, drift PASS, verify PASS, review + pr-review PASS-WITH-NITS; qa absent per non-web XOR; grill absent per spec ⏭️).
- **Build/test sanity (merged branch):** 73 passed (test_run_lib 7 + test_launchd_monitor 40 + test_notify_cmd 26); `bash -n` all 5 launchd scripts OK; `plutil -lint` both plists OK (untouched); ruff clean.
- **Doc-sync:** PASS — README false `.run.lock` claim removed; timeouts + per-wrapper locks + notify asymmetry documented; ADR 0016 pointer; CHANGELOG `[Unreleased]`; TODOS `_ak_call` mitigation note — all present on the merged branch.
- **Integration (cross-cutting, verified):** `install.sh` templates only the 2 named wrappers (not `lib-run.sh`); both wrappers `cd "$REPO_ROOT"` **before** the relative `source ops/launchd/lib-run.sh`, so the lib resolves to the checked-in repo copy at runtime. Sound end-to-end. (The lib's header comment mentions `__UV_BIN__/__REPO_ROOT__` only to document their absence — never sed-substituted.)

### Follow-up work (deferred, non-blocking)
1. `run-monitor.sh` `notify-status … || true` swallows a notifier failure on the timeout path — NOT changed (spec §4.1 locked that exact line; notify is best-effort). A log-on-failure breadcrumb is a small future hardening.
2. Per-`_ak_call` deadline — the wrapper watchdog caps unattended exposure but a manual `irc monitor` is still unbounded (existing `TODOS.md` item, annotated as partially mitigated).
