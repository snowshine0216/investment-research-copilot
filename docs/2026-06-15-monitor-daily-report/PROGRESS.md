# PROGRESS — `irc monitor` daily brief

Mode: **spec** · Project type: **non-web** · PR shape: **A**
Feature branch: `autodev/monitor-daily-report-feature` (off `main`, left open at end)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | QA | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ✅ | ✅ | ✅ | 🔄 | ⏳ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

## Notes

- **001 spec** — ✅ user-provided, verbatim copy at [`items/001-spec.md`](items/001-spec.md).
- **001 grill** — ⏭️ user-grilled (source §14 "Grilling, 2026-06-15, grill-with-docs"); orchestrator must not auto-invoke.
- **001 QA** — ⏭️ non-web project; post-ship verifier is `/verify` (XOR), see [`items/001-verify.md`] when written.
- **001 plan** — ✅ entry phase; Opus `superpowers:writing-plans` dispatched successfully (commit `aca2c11`, not pushed). 13 phases (A–M), 42 TDD-ordered tasks, ~4.66k lines, 35 test files. Pinned trend blend: `trend = clamp(0.50·tanh(8·r60) + 0.30·ma_struct + 0.20·(−drawdown_250), −1, 1)`. 5 spec gaps judgment-called + documented in plan (trend formula; `qdii_china_us_internet` routed to `kind="qdii_global"` provider_symbol=fund_id never us_etf alias; v1 cached index-valuation N/A-degrade; MiniMax price seed `minimax-default` + VERIFY fallback; quarterly fire = 1st Jan/Apr/Jul/Oct 08:00). §12 open items are in-build verification steps w/ N/A-surfaced degradation, never blocking. *(The previous session anticipated an inline fallback after a 529-overload streak; the dispatch pool recovered and the proper Opus subagent path was used.)*
- **001 branch** — sub-branch `claude/monitor-daily-report-001` off the feature branch.
- **001 impl** — ✅ Phases A–M via 12 sequential Sonnet subagents (subagent-driven-development), TDD throughout, one commit per task. **335 monitor-suite tests pass / 11 skipped (live-gated)** in ~13s; every feature file **ruff-clean** (the 120 repo-wide ruff errors are all in pre-existing untouched files, e.g. `tests/llm/test_retry.py`, `src/irc/scoring/`). All monitor src files <200 lines. `irc config validate` → 15 YAMLs OK. Diff vs `main`: 97 files, +9982/−701.
  - **Live verification (§12, run by orchestrator):** AkShare NAV smoke ✅ — all 7 ids yield ≥251 acc-NAV points within the 550-day window (§12.6 confirmed). MiniMax smoke — path ✅ (`/v1/chat/completions` reached, `Authorization: Bearer` scheme correct), but **401 Unauthorized: the `MINIMAX_API_KEY` in `.env` is a placeholder/invalid key (65-char, non-JWT)**. This is a **credential issue, not a code defect**; the degradation contract handles it (monitor_* fails at the call edge with a clear error, report ships with `narrative_status` degraded, deterministic facts/signal/evidence still render). **USER ACTION: supply a valid `MINIMAX_API_KEY` for live narratives.**
  - **Notable in-flight deviations (all sensible, for drift to confirm):** `config/*.yaml` force-added (gitignored, matches existing tracked-config precedent); existing `test_settings.py` deepseek-required test updated → call-edge semantics (planned Task 18); old `run-daily.sh`/`run-weekly-full.sh` + their tests removed via `git rm` (jobs removed per §9); sole-source guard implemented via AST-walk (avoids docstring false-positive); `launchctl`/install/uninstall NOT executed against live system (deferred to user deploy).
