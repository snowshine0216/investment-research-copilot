# Memo / Decision Consolidation and Readable Refs — Design

**Date:** 2026-05-25
**Status:** Approved (brainstorming complete; awaiting user sign-off)
**Driver:** `outputs/2026-05-25/problem.md` flagged two issues:
1. `memo.md` §5 shows `opportunity_state = pause_wait` for 003318 / 519770 while `decision_report.json` independently shows `decision_status = actionable_buy`. The two reports answer different questions and the memo never reads decision state, so the user cannot reconcile them.
2. Inline citation markers in `memo.md` are 16-hex `[ref:HEXID]` strings — hard to scan, and the `_MAX_REFS = 40` cap in `src/irc/memo/pipeline.py` truncates the appendix so some §5 refs (e.g. `[ref:4b03af24151fe798]` for 511010) have no appendix entry to land on.

---

## 1. Goals

- `irc run` produces the full consolidated output — opportunity AND decision — in one command. Today only opportunity runs; decision is a separate step.
- `memo.md` becomes the consolidated weekly report: it surfaces both the decision-readiness verdict (gates) and the opportunity overlay (valuation/heat) per pick, side-by-side, plus a "today's only action" banner mirroring `decision_report.md`.
- Inline citation markers in the published memo render as ASCII footnote numbers (`[1]`, `[2]`, …) with a complete appendix mapping each number to the underlying `[ref:HEXID]` evidence line. No §5 citation can be missing from the appendix.
- Internal data flows (LLM prompts, audit gates, traceability JSON, citation_audit.json) continue to operate on the canonical `[ref:HEXID]` form. ADR 0001's `\[ref:[0-9a-f]{16}\]` regex is unchanged for everything upstream of the published memo.

## 2. Non-goals

- No change to scoring, allocation, gold, or trade-plan logic.
- No change to opportunity-stage evidence collection or thesis derivation.
- No new fields in `opportunity_report.json` or `decision_report.json`.
- No re-routing of LLM tasks.
- No change to memo §2 / §3 / §7 deterministic blocks. The 决策 column lives inside §5's existing `IRC_PICKS_TABLE_BEGIN/END` deterministic block.

## 3. Architecture

### 3.1 Pipeline change — `decision` becomes a stage

`src/irc/commands/run_cmd.py`:

```python
STAGE_NAMES: tuple[str, ...] = (
    "ingest", "research", "discover", "score", "gold",
    "allocate", "plan", "opportunity", "memo", "decision",  # +decision
)
```

`_runners_map()` gets the `"decision": run_decision` entry. No change to `_without_disabled_optional_stages` (research is the only optional stage). `decision` runs AFTER memo, so it still reads `memo_audit.txt` / `memo_traceability.json` as today — the audit banner in `decision_report.md` keeps working.

### 3.2 Extract pure `compute_decision_status` helper

`src/irc/decision/gates.py` currently exposes `_decision_status(score_action, blocking_reasons, allocation_selected) → DecisionStatus`. Promote it to a module-level pure function with the same signature, renamed `compute_decision_status` (drop the leading underscore). The existing private `_decision_status` becomes a one-line alias to preserve backwards compatibility for any internal caller until cleaned up by the implementation plan.

The function is already pure — no I/O, no module-level state. Promotion is mechanical.

### 3.3 Memo `§5` — 决策 column

`src/irc/memo/picks_table.py`:

- `PickRow` gains one field: `decision_status: str = "watch_only"`. Default keeps backwards compatibility for tests that build PickRow manually.
- Header changes from
  `| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 机会状态 | 本期行动 | 主要理由 | 证据 |`
  to
  `| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | 主要理由 | 证据 |`
- Cell renders `decision_status` via a deterministic ZH map:
  - `actionable_buy` → `候选可执行`
  - `blocked` → `阻断`
  - `watch_only` → `观察`
  - `avoid` → `回避`

`src/irc/commands/memo_cmd.py::_build_pick_rows` populates the new field by:

1. Reading `allocation` (already loaded) to derive `allocation_selected = iid ∈ allocated_ids`.
2. Reading `scoring` (already loaded) to look up `score_action` per iid.
3. Composing `blocking_reasons` from the same primitives `decision_cmd` uses — by promoting the existing `_blocking_reasons` helper in `decision/gates.py` to a module-level pure function `compute_blocking_reasons` (same signature). Pass it the same venue/qdii/completeness inputs `_build_pick_rows` already has access to via `bundle`, `opportunity_row`, and `trade_plan`.
4. Calling `compute_decision_status(score_action, blocking_reasons, allocation_selected)`.

This adds three small reads (`allocation`, `scoring`, `bundle`) to a function that already takes `scoring` and `opportunity` — minimal coupling growth. The new wiring is testable in isolation because both `compute_decision_status` and `compute_blocking_reasons` are pure.

### 3.4 Memo `§1` TL;DR — 今日唯一行动 banner

`src/irc/commands/memo_cmd.py::_derive_tldr_lines` prepends one line to the TL;DR tuple, derived from the `actionable_buy` rows already computed in §3.3:

- ≥ 1 actionable_buy: `✅ 候选可执行：{iid_list}（仍需人工核对 venue/溢价/合规）`
- 0 actionable_buy: `⚪ 本周无候选可执行（详见 §5 决策列与 §6 风险提示）`

This is deterministic and independent of the LLM-managed narrative.

### 3.5 Footnote post-pass — readable refs

New module `src/irc/memo/footnote_renderer.py`:

```python
def render_footnotes(memo_md: str, refs: list[str]) -> str:
    """Rewrite inline `[ref:HEXID]` markers as `[1]`, `[2]`, ... in document order.

    - Numbering is GLOBAL across the entire memo (not reset per section).
    - Same HEXID seen twice reuses the same number.
    - Appendix lines are rewritten from
        `- [ref:HEXID] snapshot · ... summary`
      to
        `- **[1]** snapshot · ... summary  (`[ref:HEXID]`)`
      so the hex is preserved at the line tail for grep/audit.
    - Refs in `refs` that never appear inline (rare; appendix-only) are
      assigned trailing numbers in `refs`-list order.
    """
```

Wiring (`src/irc/memo/pipeline.py::run_memo_pipeline`):

- Audit gates and `check_traceability` still operate on the pre-postprocess draft (which contains `[ref:HEXID]`). No audit code changes.
- After audit passes, before `MemoOutput.draft` is returned, run `render_footnotes(final_draft, sanitized_refs)`.
- Drop `_MAX_REFS = 40` for the appendix. The synthesizer prompt still gets the truncated `effective_refs = raw_ref_pool[:_MAX_REFS]` (it's a prompt-budget concern), but `_render_evidence_appendix` is called with the full `raw_ref_pool` so no appendix entry is ever dropped. This fixes Problem #2 root cause (Problem.md lines 28–40).

### 3.6 Data flow

```
ingest → discover → score → gold → allocate → plan → opportunity → memo → decision
                                                                    │
                                                            (compute_decision_status
                                                             feeds §5 决策 column
                                                             + §1 banner)
                                                                    │
                                                            audit gates run on hex-form draft
                                                                    │
                                                            render_footnotes() post-pass
                                                            (writes the final memo.md)
```

## 4. Component inventory

| File | Change |
|---|---|
| `src/irc/commands/run_cmd.py` | Add `"decision"` to `STAGE_NAMES` and `_runners_map()`. |
| `src/irc/decision/gates.py` | Promote `_decision_status` → `compute_decision_status` and `_blocking_reasons` → `compute_blocking_reasons` (both pure, public). Old names kept as 1-line aliases. |
| `src/irc/memo/picks_table.py` | `PickRow` adds `decision_status` field. `render_picks_table` adds 决策 column with ZH map. |
| `src/irc/commands/memo_cmd.py` | `_build_pick_rows` populates `decision_status` via `compose_blocking_reasons` + `compute_decision_status`. `_derive_tldr_lines` prepends "今日唯一行动" banner. |
| `src/irc/memo/footnote_renderer.py` | NEW. Pure post-pass that renumbers refs and rewrites appendix. |
| `src/irc/memo/pipeline.py` | Wire `render_footnotes` after audit passes. Pass full `raw_ref_pool` (not truncated) to `_render_evidence_appendix`. Keep `_MAX_REFS` only for the synthesizer prompt input. |
| `README.md` | Update §Status, §Quick start, §Weekly default run, §Weekly run with research, §Debug session §7, §Output inspection cheatsheet. |
| `docs/diagrams/overall-workflow.html` | Add Box 10 `decision` after `memo`. Update "9 stages" → "10 stages" copy at lines 136, 162, 165. |
| `docs/diagrams/stage0-ingest-to-plan.html` | Verify ingest-to-plan scope unaffected; no edit if scope is correct. |
| `docs/adr/0001-citation-model.md` | Footer note: published memo post-processes `[ref:HEXID]` → `[N]`; upstream regex unchanged. |
| `CHANGELOG.md` | Entry summarizing both fixes. |
| `outputs/2026-05-25/problem.md` | Mark both items resolved with links to the new commit(s). |

## 5. Tests (TDD)

New tests (each starts as a failing red):

| Test file | Cases |
|---|---|
| `tests/decision/test_gates.py::test_compute_decision_status_pure` | Golden table over `(score_action, blocking_reasons, allocation_selected)` → expected `DecisionStatus`. Covers: actionable_buy, watch_only (no allocation), blocked (any blocking reason), avoid. |
| `tests/memo/test_picks_table.py::test_render_picks_table_includes_decision_column` | Header has 决策 between 综合分* and 机会状态. Cell ZH map covers all 4 statuses. |
| `tests/memo/test_footnote_renderer.py` | Empty → empty. Single ref → `[1]` inline + appendix. Duplicate HEXID → both render `[1]`. 50+ refs → all numbered + all in appendix. Hex preserved in appendix tail. Refs appearing only in appendix (not inline) get trailing numbers. |
| `tests/memo/test_template.py::test_tldr_action_banner` | actionable_buy_count > 0 → ✅ line. == 0 → ⚪ line. |
| `tests/commands/test_run_cmd.py::test_decision_in_stage_names` | `"decision"` is in `STAGE_NAMES` and resolves via `_runners_map()`. |
| `tests/integration/test_run_pipeline_includes_decision.py` | After `run_pipeline()` against a golden fixture, both `decision_report.json` and `decision_report.md` exist. |

Existing tests that need mechanical updates:

- Any test asserting the picks-table header string (search for `综合分.*机会状态`): add 决策 between them.
- Any test asserting `[ref:` appears inline in the synthesised memo body (post-publish): switch to asserting `[ref:` appears in the appendix instead, and `[\d+]` appears inline.
- `tests/memo/test_pipeline.py` if it asserts the appendix is capped at 40 refs: drop that assertion; replace with "appendix length == len(raw_ref_pool)".

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Ref order changes between runs would re-number refs. | Document order is already deterministic for §2/§3/§5/§7 per CLAUDE.md memo-pillar locks. LLM-managed paragraphs are §1 TL;DR (now also deterministic), §4 allocation, §6 risks — but `render_footnotes` runs post-LLM so any ref the LLM did happen to emit is numbered in its actual position. Number stability across runs depends on (a) ref-pool order (already stable: gold → macro → trade-plan order → remaining opportunity) and (b) LLM not reordering refs. We accept the latter as acceptable variance — numbers are stable inside a single run, and that's what matters for readability. |
| Citation audit (`find_uncited_conclusions`, `check_traceability`, `find_hallucinated_citations`) breaks on the new `[N]` form. | Audit runs BEFORE `render_footnotes`. The draft fed to the auditor is still hex-form. The published `memo.md` is the post-processed form; nothing reads memo.md back into audit logic. Confirmed by reading `run_memo_pipeline` flow. |
| `decision` running as a stage might surface latent failures (e.g. missing artifacts) that today only show when the user explicitly calls `irc decision`. | `run_decision` already returns rc=2 with a clear "missing decision inputs in <out_dir>: …" message when any of the 4 required artifacts is missing. `run_pipeline` already handles non-zero rc by halting and writing `.halt_reason.json`. No new failure mode. |
| `IRC_PICKS_TABLE_BEGIN/END` marker contents change shape — picks-table acceptance tests will fail. | Expected and covered by the test-update list in §5. The marker block remains deterministic. |
| Appendix grows unbounded for runs with very large evidence pools. | Today's full pool is ~45 entries. Doubling to ~100 is fine for a markdown memo. If we observe runaway growth later we can revisit a soft cap (e.g. 200) with an explicit "appendix truncated at N; full evidence in `memo_traceability.json`" notice. Out of scope for this design. |

## 7. Documentation impact

- **README** — see component inventory.
- **`docs/diagrams/overall-workflow.html`** — add `decision` box; bump stage count.
- **`docs/adr/0001-citation-model.md`** — footer note as in §3.5.
- **CLAUDE.md** — no edit needed. The two pillar-lock memories (`feedback_memo_pillar_locks.md` and `project_memo_macro_evidence_pillar.md`) remain accurate: §5 deterministic block keeps its `IRC_PICKS_TABLE_BEGIN/END` marker; new 决策 column lives inside that block.

## 8. Sequencing / acceptance criteria

Implementation order (each step is a green test before moving on):

1. Promote `_decision_status` → `compute_decision_status`. Test golden table.
2. Add `decision_status` field to `PickRow`. Test header + ZH map.
3. Wire `_build_pick_rows` to populate `decision_status` via `compose_blocking_reasons` + `compute_decision_status`.
4. Prepend 今日唯一行动 banner in `_derive_tldr_lines`. Test both branches.
5. Add `"decision"` to `STAGE_NAMES` + `_runners_map()`. Test stage presence + integration fixture.
6. Write `footnote_renderer.py`. Test all cases.
7. Wire `render_footnotes` into `run_memo_pipeline`. Drop appendix cap.
8. Update README, diagrams, ADR, CHANGELOG.
9. Re-run `uv run pytest` and `uv run ruff check src tests` — both clean.
10. Re-run `uv run irc run` on a fresh date; inspect `memo.md` to confirm 决策 column, banner, and `[N]` refs render as expected.
11. Mark items in `outputs/2026-05-25/problem.md` as resolved with commit hashes.

**Acceptance:**
- `uv run irc run` writes all 10 stage outputs in a single invocation, including `decision_report.{json,md}`.
- `memo.md` §5 picks table contains a 决策 column with ZH labels matching `decision_report.json::rows[].decision_status` for the same instruments.
- `memo.md` §1 first line is the 今日唯一行动 banner.
- `memo.md` body has zero `[ref:HEXID]` strings; all inline citations are `[N]` numerals.
- `memo.md` appendix has one entry per number, with `[ref:HEXID]` preserved at the line tail.
- No §5 ref number lacks an appendix entry.
- `pytest` and `ruff` pass.

## 9. Open questions

None. All design choices were resolved during brainstorming via AskUserQuestion:

- Consolidation style: 决策 column alongside 机会状态.
- Decision↔memo coupling: pure `compute_decision_status` helper, called by both sides.
- Extra decision-report content folded into memo: just the 今日唯一行动 banner.
- Ref render style: footnote numbers `[1]` `[2]` `[3]` with full appendix.
- Numbering scope: global single sequence.
- Footnote glyph: ASCII `[1]` (not unicode superscripts).
- Decision audit banner: keep existing behavior (decision still reads memo_audit.txt).
