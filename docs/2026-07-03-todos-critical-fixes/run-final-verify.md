Verdict: PASS

# Final integrated smoke test — todos-critical-fixes

Subagent: none (Agent tool forbidden for this run per instruction; all steps executed
directly in this session).

Branch: `autodev/todos-critical-fixes-feature` (confirmed via `git branch --show-current`),
HEAD `75e583fd` at test time, working tree clean.

Scope: end-to-end surface smoke across the run's merged items (001, 002, 004, 005; 003
reclassified OUT as a stale TODO — see SKIPPED.md). No `irc run` / `irc opportunity` /
`irc monitor` executed (network + paid-LLM cost constraint respected).

## Source / Entry point exercised

1. **CLI entry + config validation** (secret-free by design):
   - `uv run irc --help` → prints full command list, exit 0.
   - `uv run irc config validate` → `OK: all 15 YAML files validated.` (scoring weights
     2026-05-19-v2, universe 471 instruments, 13 LLM tasks, spend margin 1.2), exit 0.

2. **Full import graph** — one process imports every touched/integration module:
   `irc.cli`, `irc.commands.opportunity_cmd`, `irc.commands.monitor_cmd`,
   `irc.monitor.narrative_macro`, `irc.fundamentals.fund_level_repair`,
   `irc.opportunity.thesis_evidence`, `irc.opportunity.policy_b` →
   `import graph OK`, exit 0. No circular-import or missing-symbol errors across the
   four items' modules loaded together.

3. **Cross-item integration flow (002 + 004)** — direct Python exercise
   (`/private/tmp/.../scratchpad/cross_item_smoke.py`), using fixture shapes copied from
   `tests/fundamentals/test_fund_level_repair.py`:
   - Built a foreign-heavy `ActiveFundSnapshot` (HK-listed constituent, 80% weight ⇒
     foreign_listed_share 0.80 ≥ 0.50 threshold) whose cached `fund_level_evidence` has a
     DATA leg (NAV) but is missing the INFORMATION leg (announcements previously failed;
     `fund_announcements_unavailable:006809` recorded). Confirmed
     `foreign_heavy_fund_level_gap(snap_before) == True` (item 004's real predicate).
   - Fed `snap_before` to the REAL `derive_thesis_from_evidence` →
     `thesis_state == "evidence_insufficient"`, reason "主动基金证据缺少信息腿（券商/新闻/公告），
     长期逻辑暂不背书。" (item 002's dual-leg thesis heuristic correctly detects the info-leg
     gap in the flattened+fund_level union).
   - Ran the REAL `merge_fund_level_evidence` (item 004) with a fake fresh fetch
     supplying only the recovered INFORMATION leg → verified leg-wise monotone merge:
     `fund_level_evidence == (cached_data_leg, fresh_info_leg)` (cached leg retained,
     fresh leg added — not full replacement), `fund_level_failure_reasons == ()`,
     `cache_probed_at` byte-identical, and `foreign_heavy_fund_level_gap(snap_after) ==
     False`.
   - Fed `snap_after` to the REAL `derive_thesis_from_evidence` →
     `thesis_state == "intact"`, reason "主动基金 1 个核心持仓的成分股证据已收集。"
   - **Result: `evidence_insufficient` → `intact` within one script run** — proves the
     single-run heal path both specs promise (item 004 Q9/R5: repair precedes
     `derive_thesis_from_evidence` in `_build_rows`, so a healed fund can flip state in
     the same run, not the next one). Script exit 0, all in-script asserts passed.

## Cross-item flow observed (with evidence)

- 002 (dual-leg thesis heuristic) and 004 (fund-level evidence repair probe) compose
  correctly: 004's merge output is exactly the input 002's heuristic needs to flip state.
  No glue code was needed beyond calling both real functions in sequence — confirming the
  two items' contracts (evidence shape, `citation_kind` literals, `ActiveFundSnapshot`
  field semantics) agree.

## Test sweep (integrated branch, merged items' mirror files together)

```
uv run pytest tests/monitor/test_narrative_macro.py tests/opportunity/test_thesis_evidence.py \
  tests/opportunity/test_fund_eval.py tests/fundamentals/test_fund_level_repair.py \
  tests/opportunity/test_policy_b.py -q
```
→ `155 passed, 1 skipped in 0.26s` (the skip is a pre-existing marker-gated case, not a
failure).

```
uv run pytest tests/commands/test_monitor_cmd_theme_consolidation.py -q
```
→ `6 passed in 0.26s`.

## Lint baseline check

- `uv run ruff check src` (feature branch) → **25 errors**.
- `uv run ruff check src` on a clean `main` worktree (`221a34e4`, via
  `git worktree add`) → **25 errors** — identical count.
- `diff` of sorted `ruff check --output-format=concise` output between the two →
  **empty** (same files, same lines, same rules; zero new/removed violations from any
  of the four merged items).
- Cross-checked against the run's documented repo-wide baseline (`uv run ruff check src
  tests`, recorded as 118 across items 001/002/004/005 verify+drift docs): reproduced
  exactly — `Found 118 errors` on the feature branch, matching. (Task instruction step 5
  used `ruff check src` only; both scopes were checked for full transparency, both
  reproduce their respective documented/expected numbers with zero regression.)
- Worktree cleaned up (`git worktree remove --force`).

## Failures

None. All five smoke steps passed:
1. CLI help + config validate — exit 0 both.
2. Import graph — OK, exit 0.
3. Cross-item (002+004) heal flow — evidence_insufficient → intact, exit 0.
4. Test sweep (5 mirror files + 1 per-file) — 155 passed/1 skipped + 6 passed, 0 failed.
5. Ruff — 25/25 (src-only) and 118/118 (src+tests) vs. main, zero-diff violation sets.
