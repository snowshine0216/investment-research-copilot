Verdict: PASS

Subagent: sonnet
Plan checklist items: 9 tasks / ~40 steps
Verified present: all steps present and matching
Drift findings: 0 unplanned scope-creep; 1 anticipated extraction; 1 in-latitude test tightening

---

## Step-by-step classification

### Task 0 — Baseline
- Step 1 (branch + green baseline): incidental — PROGRESS.md update confirms branch; 36 tests pass on branch. OK.

### Task 1 — ProductMetrics + new NarrativeFundReport fields (schemas.py)
- Step 1 (failing test for ProductMetrics defaults + new field defaults): OK — `tests/narrative/test_report.py` lines 131-141, exact plan code.
- Step 2 (run to verify fail): process-only step; not verifiable in diff. Incidental.
- Step 3 (add ProductMetrics + extend NarrativeFundReport): OK — `src/irc/narrative/schemas.py`: import extended (`ConstituentAnalysis, ThesisEvidence`), `ProductMetrics` frozen dataclass (4 fields, all `None`), `NarrativeFundReport` appended `constituent_analyses` + `product_metrics` with safe defaults. Exact match to plan.
- Step 4-5 (run to verify pass): process-only. Tests confirm: `36 passed`.
- Step 6 (commit): incidental process step.

### Task 2 — Thread constituent_analyses + ProductMetrics through _report_from_card (analyze.py)
- Step 1 (failing tests): OK — `tests/narrative/test_analyze.py` +27 lines: `test_report_from_card_carries_constituent_analyses`, `test_report_from_card_carries_product_metrics_from_input`. Plan's `...` placeholders resolved against existing `_inp`/`_row` fixtures as instructed.
- Step 3 (add `_product_metrics_from_input` + change `_report_from_card` signature): OK — `analyze.py` diff: helper added above `_report_from_card`, signature gains `*, inp: OpportunityInput`, `constituent_analyses` and `product_metrics` threaded. Exact match to plan.
- Step 4 (update `analyze_fund` call site): OK — `analyze.py` line 150: `return _report_from_card(row, shortlist_row, inp=inp, role=role)`. Exact match.
- Step 5 (pre-existing test updated for new signature): OK — `test_report_from_card_carries_evidence_and_states` and `test_report_from_card_missing_snapshot_is_insufficient` updated with `inp=_inp(...)`. Plan Step 5 explicitly permitted this as "the only allowed test churn."

### Task 3 — M1 inline evidence bullet gains · {summary} (AC1, AC2)
- Step 1 (failing tests): OK — `test_report_md_inline_bullet_has_summary_suffix`, `test_report_md_inline_caps_at_three_with_summary` present, exact plan code.
- Step 3 (`_evidence_bullets` updated): OK — `report.py` line 66: `· {ev.summary}` appended. Docstring updated. Exact match.

### Task 4 — M1 footnote appendix resolves every inline [ref:hex] (AC4, AC5)
- Step 1 (failing tests): OK — `test_report_md_every_inline_ref_resolves_to_footnote`, `test_report_md_footnote_table_is_byte_identical_two_calls`, `test_report_md_footnotes_sorted_by_citation_id_asc`, `test_report_md_no_evidence_has_no_footnote_table` all present.
- Step 3 (`_footnote_line` + `_footnote_lines` + wire into `render_report_md`): OK — functions land in `report_appendix.py` (Task 8 fallback — see below); imported into `report.py`. Wire-up at `report.py` lines 93-99 matches plan exactly (`_appendix_lines(r)`, `_footnote_lines(r.thesis_evidence)`, heading `### 证据明细 / Evidence appendix`).
- Task-4 stub (`_appendix_lines` returning `[]`): not visible as a separate stub commit — implementer went straight to full implementation in one pass. Functionally equivalent; tests pass.

### Task 5 — M1 per-constituent appendix prose (AC3)
- Step 1 (failing tests): OK — `test_report_md_appendix_renders_constituent_one_line_view`, `test_report_md_appendix_constituent_failure_only_no_oneline`, `test_report_md_passive_fund_has_no_constituent_block_but_has_footnotes` all present with exact plan assertions.
- Step 3 (`_rank_constituents`, `_appendix_constituent_line`, `_appendix_lines`): OK — in `report_appendix.py`. 5-shape precedence: audit_errors → evidence+failures → failures → evidence → missing_record. Exact match to plan.
- Constituent line head uses `(权重 {c.weight_pct}%)` — plan uses same. Test asserts `"601899 co-601899 (权重 8.5%): 紫金矿业 营收 +20%"`. OK.

### Task 6 — M2 product-quality drivers next to 质量 (AC6, AC7)
- Step 1 (failing tests): OK — all 5 tests present (`test_report_md_renders_product_drivers`, `test_report_md_none_metric_renders_em_dash`, `test_report_md_metadata_floored_weak_shows_all_em_dash`, `test_report_md_genuine_weak_shows_real_numbers`, `test_report_md_no_product_metrics_renders_em_dash_drivers`).
- Step 3 (`_fmt_metric` + `_product_drivers_segment`): OK — in `report_appendix.py`. Exact plan code.
- Wire into sub-state line: OK — `report.py` line 82-84 matches plan verbatim (`｜ 产品驱动: {_product_drivers_segment(r.product_metrics)}`).
- `test_report_md_genuine_weak_shows_real_numbers` tightened: plan said assert `"—" not in block.split(...)[0]` (whole line); implementation uses three separate `assert "费率=—" not in drivers_line` / `"规模=—"` / `"任职=—"`. This is the plan's own documented latitude (Task 6 Step 4 footnote: "tighten assertion to the three providable drivers"). Type: in-latitude adjustment — OK.

### Task 7 — AC8 .json additive serialisation
- Step 1 (failing test): OK — `test_report_json_includes_product_metrics_and_constituents` + `test_report_json_two_calls_byte_identical` present.
- Step 3 (`_product_metrics_dict`, `_constituent_dict`, `_report_dict` extended): OK — `report.py` lines 115-158. Exact plan code. `_report_dict` adds `product_metrics` and `constituent_analyses` after `thesis_evidence`.

### Task 8 — AC9/AC10/AC11 verification + file-size check
- Step 5 (size budget): `report.py` = 164 lines, `report_appendix.py` = 74 lines, `schemas.py` = 133 lines, `analyze.py` = 153 lines. All under 200 lines. OK.
- Step 6 (extraction commit): `report_appendix.py` created per the Task 8 fallback. Type: **plan-anticipated**, NOT scope creep.
- AC9 (existing tests pass): `36 passed` in `tests/narrative/`. OK.
- AC10 (SAME-3 + opportunity/memo green): `495 passed, 3 skipped`. OK.
- AC11 (no scorer/state change): `git diff --name-only` shows only `src/irc/narrative/`, `tests/narrative/`, `docs/2026-06-02-narrative-coverage-markdown/PROGRESS.md`. `states.py`, `risk.py`, `fundamentals/types.py` diffs are empty. OK.

---

## Invariant verification

### Renderer determinism (ADR 0004)
- `_footnote_lines`: `by_id = {ev.citation_id: ev for ev in thesis_evidence}` then `sorted(by_id)` — citation_id ASC, deterministic. OK.
- `_rank_constituents`: `sorted(cas, key=lambda c: (-c.weight_pct, c.symbol))` — weight DESC, symbol ASC tiebreak. Deterministic. OK.
- No `datetime.now()` or unsorted dict/set iteration in any new render path. Confirmed by grep. OK.

### Citation IDs exact 16-hex (ADR 0001)
- `_footnote_line` uses `ev.citation_id` verbatim (read from the ThesisEvidence field, never recomputed/truncated).
- `_evidence_bullets` uses `ev.citation_id` verbatim.
- `_appendix_constituent_line` uses `e.citation_id` verbatim via `select_citations`.
- `test_report_md_every_inline_ref_resolves_to_footnote` uses `re.findall(r"\[ref:([0-9a-f]{16})\]", block)` — validates 16-hex format. `_REF_RE = re.compile(r"\[ref:[0-9a-f]{16}\]")` used in AC9 tests. OK.

### classify_product_quality UNTOUCHED (F-1 deferral)
- `git diff autodev/narrative-coverage-markdown-feature...claude/narrative-coverage-markdown-003 -- src/irc/opportunity/states.py` produces empty output. Confirmed. OK.

### report.py NOT a SAME-3 surface (RD-1)
- No new `select_citations` consumer added to `_build_pick_rows` / `build_evidence_pool` / `_render_section`.
- `select_citations` used in `narrative/report.py` (inline bullets) and `narrative/report_appendix.py` (constituent refs) — display-only, non-SAME-3 surfaces. The plan explicitly permitted this ("Reuse as-is; add NO new consumer to SAME-3 surfaces"). SAME-3 tests: 495 passed. OK.

### .json additive only
- `_report_dict` retains all pre-existing keys; `product_metrics` and `constituent_analyses` appended after `thesis_evidence`. `test_report_json_round_trips_states_and_evidence` (pre-existing AC8 round-trip test) still passes. OK.

### NarrativeFundReport new fields have safe defaults
- `constituent_analyses: tuple[ConstituentAnalysis, ...] = ()` — empty tuple default. OK.
- `product_metrics: ProductMetrics | None = None` — None default. OK.
- `test_narrative_fund_report_new_fields_default_empty` verifies both. OK.

### No 基金概况 literal introduced
- `git diff ... | grep -c "基金概况"` = 0. OK.

---

## Judgment call assessment

1. **Appendix section naming** (`### 证据明细 / Evidence appendix` / `#### 持仓明细 / Holdings`): Plan documented latitude ("or equivalently-named"). Implementation used the plan's own suggested heading text exactly. OK — within stated latitude.

2. **Driver labels** (`费率=/规模=/任职=/跟踪误差=`): Plan documented latitude ("Spec doesn't fix exact labels; chose CN labels matching existing 子状态 line style"). Tests assert these literals. OK — within stated latitude.

3. **`_fmt_metric` raw-float precision** (`f"{v}"`): Plan documented latitude ("render raw float to avoid inventing rounding policy"). OK — within stated latitude.

4. **Task 8 file-split**: `report.py` would have been 238 lines without extraction. Plan Task 8 Step 5/6 explicitly documented this fallback ("extract helpers into `src/irc/narrative/report_appendix.py`"). Implementation matches: pure module, no I/O, imported into `report.py`. **NOT unplanned scope creep.**

5. **`test_report_md_genuine_weak_shows_real_numbers` assertion tightened**: Plan's Task 6 Step 4 footnote explicitly documented this contingency ("tighten assertion to the three providable drivers"). Implementation does exactly that. OK.

---

## Summary

All 9 tasks / ~40 steps verified present and matching. 0 missing steps. 0 divergent steps. 1 plan-anticipated extraction (`report_appendix.py`). 1 in-latitude test tightening. All 11 ACs covered. 36 narrative tests pass. 495 SAME-3/opportunity tests pass. `classify_product_quality` untouched. No `基金概况`. No determinism violations.
