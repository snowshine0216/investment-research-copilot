# 003-spec — Mirror Decision Sheet into memo §5 picks table

**Backlog:** `decision-confidence-followup` (2026-05-26)
**Source row:** MASTER-SPEC.md item 003
**Effort:** S — pure renderer change (`src/irc/memo/picks_table.py`) plus the construction-site `_build_pick_rows` in `src/irc/commands/memo_cmd.py`.
**Touches:** no new domain concepts, no new ADR. Mirrors a decision-grade view that already exists in `outputs/<DATE>/decision_report.md`.

---

## Goal

A reader who only opens `outputs/<DATE>/memo.md` (today's actionable output for the human operator) should see per-pick **per-tranche sizing cap** and **current trigger state** directly in the §5 picks table — the same information that today lives only in `decision_report.md`'s `## 决策面板 / Per-pick decision summary` section. Two new columns are added to the deterministic, LLM-locked picks table: `单次定投上限` (per-tranche cap %) and `触发状态` (compact trigger marker per condition). All sizing logic is reused from `irc.decision.sizing.suggest_tranche_pct` and `evaluate_trigger`; no new sizing semantics are introduced.

---

## Acceptance criteria

Every criterion below is independently verifiable by a unit test in `tests/memo/`.

1. **`PickRow` gains two new fields**, both `frozen` dataclass attributes with safe defaults so all existing callers / tests continue to pass without modification:
   - `tranche_cap_pct: float | None = None` — fraction of total NAV, e.g. `0.05` for 5%.
   - `trigger_status: str = ""` — pre-formatted compact string; empty → renders `—`.
2. **`render_picks_table` header line** includes the two new columns in this exact order: `... | 主要理由 | 单次定投上限 | 触发状态 | 证据 |`. The `主要理由` and `证据` column header strings are unchanged; the two new headers are the literal Chinese strings `单次定投上限` and `触发状态`.
3. **Per-tranche cap cell formatting**:
   - When `tranche_cap_pct is not None`: render `≤ {pct * 100:.2f}%` (e.g. `≤ 5.00%`). Two decimal places mirrors decision_report.md.
   - When `tranche_cap_pct is None` OR `tranche_cap_pct <= 0.0`: render `—` (single em-dash, identical to the empty-citations convention).
4. **Trigger status cell formatting**:
   - When `trigger_status` is non-empty: render the string verbatim. Multiple triggers are pre-joined by `<br>` so the markdown row stays single-line.
   - When `trigger_status == ""`: render `—`.
5. **Compact trigger format** (helper `_format_trigger_status_compact` in `src/irc/memo/picks_table.py`):
   - Per trigger: `{trigger.name} {marker}` where `marker ∈ {"✓", "✗", "⚠"}` for state `met / not_met / missing` respectively (glyph derived via `evaluate_trigger`).
   - Multi-trigger join: `<br>` between entries; YAML order from `trade["triggers"]` preserved (no re-sort).
   - Empty triggers tuple → returns `""` (renderer then emits `—`).
6. **`_build_pick_rows` (memo_cmd.py) populates the two new fields**:
   - `tranche_cap_pct = suggest_tranche_pct(target_weight, plan_build_mode)` where `plan_build_mode` defaults to `"build"` when `plan.get("mode")` is missing.
   - `trigger_status = _format_trigger_status_compact(trade.get("triggers") or (), macro_snapshot, weekly_return_by_id, instrument_id)`.
   - `_build_pick_rows`'s signature gains three optional parameters: `build_mode: str = "build"`, `macro_snapshot: dict[str, float] | None = None`, `weekly_return_by_id: dict[str, float] | None = None`. All three default such that legacy callers / tests stay green.
7. **Live macro + weekly-return resolution at memo runtime**:
   - `run_memo` calls a helper to read the same `(macro_snapshot, weekly_return_by_id)` shape that `decision_cmd.py::_read_live_decision_inputs` returns today. The simplest path is to either (a) extract `_read_live_decision_inputs` into `src/irc/decision/live_inputs.py` and import from both `memo_cmd.py` and `decision_cmd.py`, or (b) duplicate a ~~30-line~~ **58-line** helper at the memo entry point.
   - **Lock:** option (a). The function is pure I/O over `data/local.duckdb`; centralising it eliminates two-place drift. Caller-side graceful degrade (`returns ({}, {}) on DB-missing / connect-fail`) is preserved exactly. **Public name (grill):** `read_live_decision_inputs` (drop the leading `_`) — once a helper crosses module boundaries it stops being private to its origin command.
8. **Trigger field-name resolution** reuses the macro-key mapping from `decision/report.py::_MACRO_FIELD_TO_KEY` and the same `instrument.weekly_return` short-circuit. The mapping is moved to `src/irc/decision/sizing.py` or a new `src/irc/decision/trigger_resolution.py` so memo and decision both import it. Locked: place it on `sizing.py` alongside the `TriggerSpec` it serves, exported as `MACRO_FIELD_TO_KEY: dict[str, str]` and `resolve_trigger_current_value(trig: dict, instrument_id: str, macro_snapshot: dict, weekly_return_by_id: dict) -> tuple[float | None, str]` — a pure function. **Grill confirmation:** `decision/report.py:555` is the only existing call site; after the move it imports the public symbol and emits character-identical output. No behaviour change.
9. **Footnote update**: `_SCORING_FOOTNOTE` in `picks_table.py` gains a single short sentence at the end (before the closing period) explaining that `单次定投上限 = 目标权重 ÷ 4 (build 模式)` and `触发状态` reflects the conditions of trade_plan §7 evaluated against the latest macro / NAV snapshot. The existing 不构成投资建议 phrase remains the closing token (Audit P5 lock).
10. **Determinism preserved**:
    - Two `irc memo` runs over identical inputs produce byte-identical §5 picks tables (locked by ADR 0004 §SAME-3, and by the existing two-run lockdown test in `tests/integration/test_publishable_set_lockdown.py`).
    - Trigger ordering inside a cell is YAML-insertion order from `trade_plan.yaml::trades[*].triggers` — no sort, no shuffle.
    - Numeric formatting is locale-independent (`f"{x:.2f}"`).
11. **Empty cases**:
    - Pick with `target_weight == 0.0` (observation-only): `tranche_cap_pct = 0.0` from `suggest_tranche_pct`; cell renders `—` (rule 3).
    - Pick with no `triggers` in its trade entry: `trigger_status = ""`; cell renders `—`.
    - When `macro_snapshot == {} AND weekly_return_by_id == {}` (DuckDB absent): trigger states resolve to `missing` ⇒ `⚠` marker per trigger; cell still renders meaningful text, not `—`.
12. **Test coverage** (new + modified):
    - `tests/memo/test_picks_table.py`: + tests for header presence/order, per-tranche cell `≤ X.XX%` format, em-dash fallback for `None` / zero-weight, multi-trigger `<br>`-joined cell, empty-triggers → `—`, footnote updated text. Existing tests untouched (defaults keep them green).
    - `tests/memo/test_pick_rows.py`: + test asserting `_build_pick_rows` populates both fields when `trades + macro_snapshot + weekly_return_by_id` are passed; + test asserting both fields default to safe sentinels when those args are omitted.
    - New `tests/memo/test_trigger_status_compact.py`: 6+ cases — single trigger met / not_met / missing, multi-trigger ordering, empty triggers, unknown comparator-fallback (`missing`).
    - New `tests/decision/test_trigger_resolution.py` (or extend existing `test_sizing.py`): 4+ cases for the extracted `resolve_trigger_current_value` — `instrument.weekly_return` hit, `macro.real_yield_10y_tips` hit, unknown field returns `(None, "raw")`, missing key returns `(None, "raw")`.
13. **`decision_report.md` output unchanged**. The extraction in AC 7 + 8 is a refactor: `decision/report.py::_decision_sheet_section` switches its import source for `_MACRO_FIELD_TO_KEY` and `_resolve_trigger_current_value` but emits character-identical output. Locked by re-running the existing decision-report tests; no rendered fixtures need updating because none exist.
14. **No mutation of the publishable citation universe / SAME-3 contract**. The new columns carry zero citation markers — `单次定投上限` is a derived number, `触发状态` is a status glyph. Item 009's `find_missing_pick_citations` and the audit gate remain unchanged.

---

## Non-goals

1. **No new sizing logic.** `suggest_tranche_pct` is reused as-is; no new modes, no new tranche-count constant. The existing 4-tranche `build` convention is the only path.
2. **No resurrection of `decision_sheet.md`.** That file was a manual one-shot and was deleted (per handoff Tripwire). The Decision Sheet content lives in `decision_report.md::_decision_sheet_section`; this item mirrors a *subset* into memo §5, not the whole sheet.
3. **No changes to `decision_report.md` output.** The renderer extraction is pure refactor; any rendered byte-drift in decision_report.md is a regression.
4. **No new data dependencies** beyond the existing `macro_series` + `nav_history` reads already done by `_read_live_decision_inputs`. The memo stage already touches `data/local.duckdb` indirectly (via `require_fresh_ingest`); a read-only connect for macro/returns is in scope.
5. **No new live-test gate.** All new tests are deterministic / fixture-based; no `IRC_*=1` env var introduced.
6. **No changes to memo §1-§4, §6, §7.** The picks table sits inside `<!-- IRC_PICKS_TABLE_BEGIN/END -->` only.
7. **No expansion of `format_why_when_line`.** No `compact=True` parameter; the existing helper is decision-report-only. Memo gets its own compact helper.

---

## Constraints

- **TDD.** Every AC ships with a failing test first, then implementation, then refactor.
- **Renderer determinism (ADR 0004).** Picks-table rendering is byte-stable across two runs of the same inputs. Trigger ordering, numeric formatting, and `<br>` joins are all order-preserving and locale-independent.
- **Reuse, do not duplicate.** `suggest_tranche_pct`, `evaluate_trigger`, and the new `resolve_trigger_current_value` are the *only* sources of sizing / trigger logic. The renderer never recomputes a state — it only formats.
- **Frozen dataclass backward compatibility.** New `PickRow` fields are positional-last, default-valued; all 30+ existing `PickRow(...)` call sites continue to compile and produce identical rendered output (apart from the two new columns, which render `—` when defaults are used).
- **No I/O in pure modules.** `picks_table.py` and `sizing.py` stay pure. The DuckDB read lives in `decision/live_inputs.py` (extracted), called from both `memo_cmd.py` and `decision_cmd.py`.
- **No `基金概况` indicator** anywhere in the new code path (CLAUDE.md restriction; mechanical — this item does not touch fundamentals fetch code, but the constraint is stamped here for completeness).
- **Layperson glyph vocabulary.** `✓ / ✗ / ⚠` already established in `decision_report.md::_decision_sheet_section` — reuse exactly, no new symbols.
- **`PickRow` ordering of fields is stable.** New fields appended at the end of the dataclass (after `decision_status`) so positional `PickRow(...)` calls do not shift. All construction sites in production code use keyword arguments, so this is defence-in-depth.

---

## Open questions resolved during brainstorming

### Q1. `PickRow` field strategy — store the computed value, or compute at render time?
**A.** Store on `PickRow` (option a). `render_picks_table`'s purity is preserved; the renderer never needs `OpportunityRow`, trade triggers, macro snapshot, or weekly returns. Compute once in `_build_pick_rows`, pass forward. Unit tests for the renderer stay table-driven.

### Q2. Column header naming.
**A.** Exact strings `单次定投上限` and `触发状态` — verified from `outputs/2026-05-26/decision_report.md` lines 38 + (handoff). Pinned.

### Q3. Determinism — is §5 inside a locked marker?
**A.** Yes — wrapped in `<!-- IRC_PICKS_TABLE_BEGIN -->` / `<!-- IRC_PICKS_TABLE_END -->` (template.py L36-37, L72) and the synthesizer prompt instructs the LLM to keep locked sections verbatim (memory `feedback_memo_pillar_locks.md`). Adding columns is safe; LLM cannot drift them.

### Q4. Snapshot test impact.
**A.** None on disk. No fixture `.md` files for the picks table exist. All current tests inline-construct `PickRow`. With default values, every test stays green. New tests are additive.

### Q5. Optional vs always-on; placeholder when sizing absent.
**A.** Columns are always rendered (table-validity). Missing data → `—` (matches the existing `_format_citations_cell` empty convention). No `N/A` or empty string. Pinned.

### Q6. Trigger state display — full vs compact?
**A.** Compact (`{name} ✓ / ✗ / ⚠`, multi-line via `<br>`). The full `format_why_when_line` output is too long for a table cell with up to 10 columns. The compact form preserves the actionable signal (which trigger and is it met?) and the user can drill into `decision_report.md::决策面板` for the full why-when line.

### Q7. Reuse vs DRY — extend `format_why_when_line` or add a new helper?
**A.** New compact helper `_format_trigger_status_compact` in `src/irc/memo/picks_table.py`. `format_why_when_line` is decision-report-specific layout and stays unchanged. The shared atom is `evaluate_trigger` (already exported from `sizing.py`) + the newly extracted `resolve_trigger_current_value`. No `compact=True` parameter pollution on the original.

### Q8. Other `PickRow` consumers.
**A.** `template.py` consumes only the rendered string; `tldr_action_banner`, `numeric_audit`, integration tests consume `instrument_id` / `citations` / `decision_status`. All ignore the new fields by construction. Frozen dataclass + default values = zero breakage.

### Q9. `Why / 主要理由` line interaction with `触发状态`.
**A.** Complementary, not overlapping. `主要理由` summarises the opportunity-state narrative (valuation / heat / thesis). `触发状态` reports trade-plan §7 trigger conditions vs current data. Adjacent column placement (`... | 主要理由 | 单次定投上限 | 触发状态 | 证据 |`) groups discipline (sizing + trigger) together between rationale and evidence.

### Q10. Tests.
**A.** Three test files: extend `test_picks_table.py`, lightly extend `test_pick_rows.py`, add new `test_trigger_status_compact.py` + `test_trigger_resolution.py`. Six+ new test cases per file. No live-test gate; no fixtures. Existing snapshot/integration tests (`test_publishable_set_lockdown.py`) re-validate determinism implicitly — they read memo.md byte-for-byte across two runs.

### Q11 (deferred bonus). Trigger ordering inside a cell.
**A.** YAML insertion order from `trade_plan.yaml::trades[*].triggers` — no re-sort. Mirrors how `decision_report.md::_decision_sheet_section` already iterates `(trade or {}).get("triggers") or []`.

---

## Implementation order (for the planner)

1. **Red — sizing extraction.** Add failing `tests/decision/test_trigger_resolution.py` for `resolve_trigger_current_value`. Move `_MACRO_FIELD_TO_KEY` + `_resolve_trigger_current_value` from `decision/report.py` to `decision/sizing.py`. Re-export. Decision-report tests stay green.
2. **Red — live-inputs extraction.** Move `_read_live_decision_inputs` from `decision_cmd.py` into new `src/irc/decision/live_inputs.py`. Update `decision_cmd.py` import. No behaviour change.
3. **Red — compact helper.** Add failing `tests/memo/test_trigger_status_compact.py`. Implement `_format_trigger_status_compact` in `picks_table.py`.
4. **Red — PickRow + render columns.** Add failing tests in `test_picks_table.py` for new columns. Add `tranche_cap_pct` / `trigger_status` fields to `PickRow` with defaults. Extend `render_picks_table` header + row format. Extend footnote.
5. **Red — `_build_pick_rows` wiring.** Add failing test in `test_pick_rows.py`. Thread `build_mode` + `macro_snapshot` + `weekly_return_by_id` through `_build_pick_rows`; populate the two new fields.
6. **Red — `run_memo` wiring.** Add integration test (extend an existing memo-cmd test) that `run_memo` reads live inputs and threads them through. Implement.
7. **Green / refactor.** Tidy imports, ensure all 14 ACs pass.
8. **Determinism check.** Run two-run lockdown test (`tests/integration/test_publishable_set_lockdown.py`) to confirm byte-equality.

---

## Resolved decisions (grill)

- Q: §5 picks table is inside `IRC_PICKS_TABLE_BEGIN/END` — is the synthesizer prompt *actually* told to keep the new columns verbatim, or just "the table"?
  A: VERIFIED verbatim. `src/irc/memo/synthesizer.py:127–133` instructs the LLM that "the entire markdown table (header, every row, footnote)" between the markers must be kept byte-for-byte, with explicit anti-drift wording on citations. Adding columns to the deterministic Python renderer is safe — the LLM literally cannot rewrite them.
  Rationale: matches `feedback_memo_pillar_locks.md` memory — §5 is one of the four pillar-locked pillars.
  Doc impact: CONTEXT.md "Decision Sheet → memo §5 picks-table mirror" entry pins the relationship.

- Q: Do the new columns leak any new citations and break SAME-3?
  A: NO. `单次定投上限` is a `≤ X.XX%` literal; `触发状态` is `{name} ✓/✗/⚠` joined by `<br>`. Zero `[ref:...]` markers in either cell by construction. SAME-3 set equality across picks-table 证据 cell / evidence-pool / discipline nested bullets is preserved unchanged (AC14 already states this).
  Rationale: glyphs and percentages carry no citation_id.
  Doc impact: none beyond the existing AC14 statement.

- Q: Is the `_read_live_decision_inputs` extraction in-scope for "optional polish", or scope-creep?
  A: In-scope and load-bearing. Without it, `run_memo` would duplicate 58 lines (NOT 30 — counted) of DuckDB I/O across two command modules. The project's "effects at edges + single seam" principle (CLAUDE.md) makes the extraction a prerequisite, not a follow-up.
  Rationale: structural — two-place drift is the failure mode this refactor pre-empts.
  Doc impact: spec AC7 line-count corrected via strike-through; CONTEXT.md `live_inputs.py` entry.

- Q: Is the helper extraction big enough to warrant a new ADR (or amend ADR 0004)?
  A: NO. The renderer-determinism contract is already locked by ADR 0004; this item is a faithful application (pure renderer, no consumer-side filter, no per-surface modes). The `live_inputs.py` and `resolve_trigger_current_value` moves are mechanical I/O / pure-function relocations — no new architectural seam, no surprising trade-off. CONTEXT.md addendum (added inline) covers the new vocabulary.
  Rationale: ADR criteria (hard-to-reverse + surprising + real trade-off) not met. CONTEXT entries are sufficient.
  Doc impact: CONTEXT.md gains 5 new bullets under "Renderers + alias-builder"; no ADR amendment.

- Q: Compact trigger display uses `<br>` to join multi-trigger lines — does GFM render that in table cells?
  A: YES, and the project already does this. `picks_table.py:_format_citations_cell` joins multiple citations with `<br>` in the 证据 cell. The new helper mirrors the precedent exactly.
  Rationale: precedent-matching keeps the table rendering idiom consistent.
  Doc impact: CONTEXT.md `_format_trigger_status_compact` entry references the `_format_citations_cell` precedent.

- Q: Naming — should the new symbols follow item 001's `FOREIGN_HEAVY_THRESHOLD` / item 002's `QDII_MAX_PREMIUM_DEFAULT` `Final[float]` pattern?
  A: Partially. Item 003 introduces no new tuning constants (the existing `_BUILD_TRANCHE_COUNT = 4` in `sizing.py` is reused). The new module-level names are:
    1. `MACRO_FIELD_TO_KEY: dict[str, str]` (public; was `_MACRO_FIELD_TO_KEY` in report.py — `_` prefix dropped on relocation).
    2. `resolve_trigger_current_value(...)` (public; was `_resolve_trigger_current_value` — `_` prefix dropped).
    3. `read_live_decision_inputs(...)` (public; was `_read_live_decision_inputs` — `_` prefix dropped).
    4. `_format_trigger_status_compact(...)` (PRIVATE; lives in `picks_table.py` as a renderer-internal helper, matching `_format_citation` / `_format_citations_cell` / `_format_score` precedent).
  Rationale: project convention — `_`-prefixed when module-private, dropped on cross-module export.
  Doc impact: spec AC5 / AC7 / AC8 already match this; the AC7 strike-through pins the rename.

- Q: Are there on-disk memo.md golden fixtures that need updating when columns are added?
  A: NO. `tests/fixtures/` carries no memo.md goldens; the integration test `test_publishable_set_lockdown.py::test_pipeline_two_run_byte_equality` (AC23) hashes `outputs/<date>/memo.md` AFTER a full live `run_memo`. It is a self-consistent two-run check (both runs use the new columns) — adds will not break it. The only on-disk memo.md files live under `outputs/<date>/` which is gitignored.
  Rationale: empirical — `find tests/fixtures -name memo.md` returns empty; the lockdown test reads `out_a/memo.md` vs `out_b/memo.md` from temp dirs.
  Doc impact: spec Q4 already states "No on-disk fixtures"; verified true.

- Q: Does the spec respect frozen-dataclass backward compatibility — i.e. can the two new fields be appended without breaking any of the 21 existing `PickRow(...)` call sites?
  A: YES. `grep PickRow(` returns 21 call sites (1 in src + 20 in tests); ALL use keyword arguments. Frozen dataclass + default values = zero call-site edits required for legacy code.
  Rationale: empirical scan.
  Doc impact: spec Constraints bullet "PickRow ordering of fields is stable" already states this; verified true.

- Q: Does the 4-tranche `build` convention need re-justification, or can `suggest_tranche_pct` be reused verbatim?
  A: Verbatim reuse. `_BUILD_TRANCHE_COUNT = 4` is already documented in `sizing.py`'s module docstring + comment ("Project convention is 4 tranches (monthly)"). No new tranche-count rationale to add.
  Rationale: `suggest_tranche_pct` is the single source of sizing truth and is the right reuse point.
  Doc impact: none (existing comment is sufficient).

- Q: What happens for the QDII case where `target_weight > 0` but the row is also `qdii_premium_too_high`-blocked? Does the per-tranche cap still render?
  A: YES — `tranche_cap_pct = target_weight / 4` renders as `≤ X.XX%`. The blocking is orthogonal: the picks table reports the *sizing cap* (what you would buy if the trigger fires), while the discipline / decision_report tells the operator the QDII gate is blocked. The two views complement each other (also matches AC9 footnote: "权重均为上限约束（≤），非强制建仓目标").
  Rationale: cap and execution-readiness are separate concerns by design.
  Doc impact: none (AC1 / footnote already cover this semantically).
