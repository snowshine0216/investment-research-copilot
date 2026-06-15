# PROGRESS — `irc monitor` daily brief

Mode: **spec** · Project type: **non-web** · PR shape: **A**
Feature branch: `autodev/monitor-daily-report-feature` (off `main`, left open at end)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

## Post-close-out — live-verification fixes + schedule setup (2026-06-15)

After the autodev run closed, live runs with a real `MINIMAX_API_KEY` surfaced issues the
mocked tests couldn't (gather functions were monkeypatched). All fixed on the feature branch
(PR #129), each TDD'd + live-verified:

- `074ad0c` **robust JSON extraction** — `MiniMax-M3` reasoning model emits `<think>…</think>`; bare `json.loads` failed every call. Spec §6 "extract JSON" now implemented (strips reasoning/fences, first balanced object).
- `17fc49b` **temperature=0 + max_tokens** on LLM calls (spec §6) — gather functions passed neither → unbounded generation.
- `1e92492` **snapshot write dispatch** — `irc monitor snapshot` crashed (`'FundLevelSnapshot' has no attribute 'as_of_iso'`); now type-dispatches to `write_nav_cache`/`write_active_fund_cache`/`write_snapshot`. The cold-start + quarterly job would both have failed.
- `ea617f4` **constituent factor wired** — reads cached active-fund snapshot holdings (top-5 by weight) → `gather_impacts` → `constituent_rows`; lifts the active CN funds off `NO_CALL`. (v2.0 snapshot-grounded; daily-fresh-news per holding = v2.1.)
- `a4ffb24` docs + `install.sh` legacy-job removal.

**Model requirement learned:** `MINIMAX_MODEL` must be a **fast non-reasoning chat model**
(`MiniMax-Text-01`). `MiniMax-M3` (reasoning) overruns the 60s call deadline + truncates JSON.
Set in `.env` (local). Documented in README + ops/launchd/README.

**Schedule INSTALLED:** `com.irc.monitor` (Mon–Fri 09:00 + 13:00) + `com.irc.fundamentals-quarterly`
loaded in launchd; legacy `com.irc.daily`/`weekly-full` booted out; cold-start snapshot ran (7 caches).

**Final live brief (MiniMax-Text-01):** exit 0, all 5 outputs, **6/7 funds earn directional biases**
(008986 NEUTRAL · 270023 ADD_BIAS · 519069 NEUTRAL · 260112 NEUTRAL · 006533 ADD_BIAS · 000083 NEUTRAL),
**7/7 narratives ok**. 009225 = honest `NO_CALL` (fund-level QDII, no constituent holdings; valuation
factor is the next piece). Feature-scoped suite: 380 passed / 11 skipped; feature files ruff-clean.

**Known follow-ups (v2.1):** valuation factor wiring (would lift 009225 + add confidence); daily-fresh
constituent news (current uses snapshot research); constituent symbol-keying can vary run-to-run.

## ✅ RUN COMPLETE (2026-06-15)

- **Items:** 1 merged (001), 0 SKIPPED, 0 BLOCKED.
- **Item PR:** [#128](https://github.com/snowshine0216/investment-research-copilot/pull/128) MERGED (squash `a065581`) into the feature branch.
- **Feature branch:** `autodev/monitor-daily-report-feature` — **left OPEN**.
- **Feature-branch PR:** [#129](https://github.com/snowshine0216/investment-research-copilot/pull/129) (→ `main`, **opened not merged** — user lands it).
- **Merged into protected branch:** no (PR #129 left open for user review — guardrail held; no "merge to main" opt-in given).
- **Phase 3:** workflow-completeness audit PASS (all verdict artifacts present/valid); build/test sanity PASS (355 passed / 11 skipped on merged branch, feature files ruff-clean, `config validate` OK). N=1 spec mode → cross-item analysis N/A.
- **Fix rounds:** 4 (P0 `irc monitor` crash + P1 latent bugs, all fixed pre/post-PR). Zero blockers at merge.
- **Follow-ups (in PR #129 body):** (1) ⚠️ valid `MINIMAX_API_KEY` needed for live narratives (current key is a placeholder → 401 → graceful degradation); (2) deploy schedule via `ops/launchd/install.sh` (jobs are artifacts only); (3) deferred cosmetic nit `factors.py` `families` var name; (4) v1 scope: cached-only index-valuation, hysteresis off (v2 spec recorded).

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏭️ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Notes

- **001 spec** — ✅ user-provided, verbatim copy at [`items/001-spec.md`](items/001-spec.md).
- **001 grill** — ⏭️ user-grilled (source §14 "Grilling, 2026-06-15, grill-with-docs"); orchestrator must not auto-invoke.
- **001 QA** — ⏭️ non-web project; post-ship verifier is `/verify` (XOR), see [`items/001-verify.md`] when written.
- **001 plan** — ✅ entry phase; Opus `superpowers:writing-plans` dispatched successfully (commit `aca2c11`, not pushed). 13 phases (A–M), 42 TDD-ordered tasks, ~4.66k lines, 35 test files. Pinned trend blend: `trend = clamp(0.50·tanh(8·r60) + 0.30·ma_struct + 0.20·(−drawdown_250), −1, 1)`. 5 spec gaps judgment-called + documented in plan (trend formula; `qdii_china_us_internet` routed to `kind="qdii_global"` provider_symbol=fund_id never us_etf alias; v1 cached index-valuation N/A-degrade; MiniMax price seed `minimax-default` + VERIFY fallback; quarterly fire = 1st Jan/Apr/Jul/Oct 08:00). §12 open items are in-build verification steps w/ N/A-surfaced degradation, never blocking. *(The previous session anticipated an inline fallback after a 529-overload streak; the dispatch pool recovered and the proper Opus subagent path was used.)*
- **001 branch** — sub-branch `claude/monitor-daily-report-001` off the feature branch.
- **001 impl** — ✅ Phases A–M via 12 sequential Sonnet subagents (subagent-driven-development), TDD throughout, one commit per task. **335 monitor-suite tests pass / 11 skipped (live-gated)** in ~13s; every feature file **ruff-clean** (the 120 repo-wide ruff errors are all in pre-existing untouched files, e.g. `tests/llm/test_retry.py`, `src/irc/scoring/`). All monitor src files <200 lines. `irc config validate` → 15 YAMLs OK. Diff vs `main`: 97 files, +9982/−701.
  - **Live verification (§12, run by orchestrator):** AkShare NAV smoke ✅ — all 7 ids yield ≥251 acc-NAV points within the 550-day window (§12.6 confirmed). MiniMax smoke — path ✅ (`/v1/chat/completions` reached, `Authorization: Bearer` scheme correct), but **401 Unauthorized: the `MINIMAX_API_KEY` in `.env` is a placeholder/invalid key (65-char, non-JWT)**. This is a **credential issue, not a code defect**; the degradation contract handles it (monitor_* fails at the call edge with a clear error, report ships with `narrative_status` degraded, deterministic facts/signal/evidence still render). **USER ACTION: supply a valid `MINIMAX_API_KEY` for live narratives.**
  - **Notable in-flight deviations (all sensible, for drift to confirm):** `config/*.yaml` force-added (gitignored, matches existing tracked-config precedent); existing `test_settings.py` deepseek-required test updated → call-edge semantics (planned Task 18); old `run-daily.sh`/`run-weekly-full.sh` + their tests removed via `git rm` (jobs removed per §9); sole-source guard implemented via AST-walk (avoids docstring false-positive); `launchctl`/install/uninstall NOT executed against live system (deferred to user deploy).
- **001 drift** — ✅ Verdict: PASS (commit `22a5879`); 42/42 plan tasks structurally present, 0 drift/scope-creep, 7 deviations verified. *(Drift checks structural presence; it did NOT catch the value-level `call=None` wiring bug nor the skipped Step 3a — those are runtime/behavioral and were caught by the ship inline review below. Working as designed: structural gate + behavioral gate are complementary.)*
- **001 ship (steps 8+9 review)** — 🔄 **BLOCKED on a P0** (3 reviewers, consensus BREAKS): `irc monitor` crashed on every real run because `_process_fund` passed `call=None`/`route=None` to the gather functions and `build_evidence_pool` was a `return ()` stub (plan Step 3a skipped). Findings in [`items/001-ship-blocked.md`](items/001-ship-blocked.md). Plan Task 32 amended (its own `route=None` was also wrong — gateway `call` needs the `LLMConfig`). Routed to **fix loop** → real `call=llm_call` + `route=llm_config` wiring + graceful degradation (empty-pool/transport-error never crash, §6) + real `build_evidence_pool` + surface `impacts.status` + guard `_r60` zero-denom + end-to-end test through the real gather path. Re-run ship steps 8+9 after fix; open PR only when clean.
- **001 ship** — ✅ **PR [#128](https://github.com/snowshine0216/investment-research-copilot/pull/128)** (`claude/monitor-daily-report-001` → `autodev/monitor-daily-report-feature`, base verified non-protected). Artifact [`items/001-ship.md`](items/001-ship.md). 3 inline-review fix rounds resolved the P0 + all P1s BEFORE the PR opened (commits 0a2217e, 9acdc83, 3cb042a). Review verdict [`items/001-review.md`](items/001-review.md) = **PASS-WITH-NITS**. Final feature-scoped suite at push: 353 passed / 11 skipped. `/ship` adaptations: base→feature branch (not main); VERSION not bumped (0.9.3, project convention); tests feature-scoped (not the 61-min suite).
- **001 verify** — ✅ `/verify` PASS ([`items/001-verify.md`](items/001-verify.md)): `uv run irc monitor` exit 0; all 5 outputs; graceful 401-degradation (deterministic signal intact); self-contained HTML (no remote refs, no JS); universal-row invariant (7/7 funds); `monitor snapshot --help` exit 0; sole-source contract.
- **001 pr-review** — ✅ `/code-review` on PR #128 PASS-WITH-NITS ([`items/001-pr-review.md`](items/001-pr-review.md)). Round 1 flagged 2 latent-bugs (CostEntry hardcoded provider/model="minimax") + 2 nits → fixed (c0c85cd: resolve real provider+model via `resolve_route`+`_resolve_model`; run-monitor.sh `exit $rc`). Round 2 re-review: 1 cosmetic nit only (`factors.py` `families` var name — intentionally left). [comment](https://github.com/snowshine0216/investment-research-copilot/pull/128#issuecomment-4706336461)
- **001 fix** — ✅ Loop exited after all 3 post-ship verdicts PASS/PASS-WITH-NITS, zero blockers/latent bugs. **4 fix rounds total:** 3 pre-PR (inline review P0+P1s) + 1 post-ship (pr-review CostEntry latent-bugs). Commits 0a2217e, 9acdc83, 3cb042a, c0c85cd.
- **001 merge** — ✅ PR [#128](https://github.com/snowshine0216/investment-research-copilot/pull/128) **MERGED** (squash) into `autodev/monitor-daily-report-feature` — merge commit `a065581`; sub-branch deleted. All pre-merge gates passed (protected-base: feature branch non-protected; ship + drift PASS; verify PASS; review + pr-review PASS-WITH-NITS; grill absent-OK spec mode; no required CI). Feature branch left **OPEN** for the user to land into `main`.
