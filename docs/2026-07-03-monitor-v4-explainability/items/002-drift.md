Verdict: PASS

Subagent: sonnet
Plan checklist items: 9 tasks / 56 steps (Task 1: pure `macro_direction.py` join + chip helpers;
Task 2: direction chips + legend + CSS + threading through `_write_outputs`/`run_monitor`; Task 3:
render/trace reconciliation pin; Task 4: claim strength tags on both render paths; Task 5: prompt v3 +
dual-shape parser + mechanism validator + `PROMPT_VERSION`; Task 6: mechanism render line + additive
trace field under schema "7"; Task 7: eval corpus extension + `mechanism_validity` metric; Task 8: docs
+ CHANGELOG; Task 9: full verification sweep)
Verified present in diff: 9/9
Drift findings: 1 (adjudicated — plan amended, not a FAIL; see below)

## Verification detail

Diff compared: `git diff autodev/monitor-v4-explainability-feature...claude/monitor-v4-explainability-002`
(23 files, 1076 insertions / 51 deletions, matching the stated scope). Every hunk in every touched file
was read directly (not the impl agent's summary) and diffed against the plan's prescribed code/text
blocks; all matched character-for-character.

- **Task 1** (`src/irc/monitor/macro_direction.py`, `tests/monitor/test_macro_direction.py`, both new) —
  `join_macro_impacts` (exact-string theme→fund→record join, first-wins on duplicate keys),
  `direction_class` (±0.15 display bands), `format_signed` (trimmed 2dp signed, `-0`→`+0` guard extended
  post-trim) match the plan's "Create with exactly" blocks byte-for-byte. 11 new tests, all present
  verbatim. OK.
- **Task 2** (`src/irc/monitor/render_html.py`, `src/irc/commands/monitor_cmd.py`,
  `tests/monitor/golden/report.html`, `tests/monitor/test_render_html.py`,
  `tests/commands/test_monitor_cmd.py`) — imports added after the `narrative_macro` import; `_CSS` gains
  `.fund-chip`/`.chip-pos`/`.chip-neg`/`.chip-flat`/`.claim-strength`/`.macro-mechanism`/`.macro-legend`
  rules verbatim (all 7 rules added in one hunk, as the plan intended, so the golden file regenerates
  exactly once); `_MACRO_LEGEND` constant + `_fund_chip` helper + rewritten `_macro_theme_section` +
  rewritten `macro_narrative_html` (now threading `macro_impacts_by_fund`) match the plan's replacement
  blocks exactly; `render_report`'s new keyword-only `macro_impacts_by_fund: ... = None` param and its
  threading into the `macro_narrative_html` call match. `monitor_cmd._write_outputs`'s new
  `macro_impacts_by_fund` param + `render_report` call-site + `run_monitor`'s
  `macro_impacts_by_fund={b.fund_id: b.macro_impacts for b in bundles}` call-site match verbatim (same
  `bundles` already in scope, feeding `build_eval_trace` — render/trace equality by construction, RD-12).
  Golden file diff verified directly: `git diff --stat` → `1 file changed, 1 insertion(+), 1 deletion(-)`;
  the diff's `+`/`-` line count via `grep -c '^[+-]<'` → `2` (one line out, one in — the `<style>` line
  only), matching Task 9 Step 6's expected output exactly. 8 new render tests + 1 wiring test in
  `test_monitor_cmd.py` (`test_run_monitor_threads_macro_impacts_into_render`) present verbatim. OK.
- **Task 3** (`tests/monitor/test_render_html.py`) — `test_macro_chips_reconcile_with_eval_trace` (ONE
  fixture set fed to both `build_eval_trace` and `render_report`; parsed chip value == `round(trace
  impact, 2)`; IFF no-record → bare chip; IFF off-theme record → trace-only, never rendered) present
  verbatim. OK.
- **Task 4** (`src/irc/monitor/render_html.py`, `tests/monitor/test_render_html.py`) — `_STRENGTH_LABEL`
  map (4 locked Chinese labels) + `_STRENGTH_FALLBACK` + rewritten `_macro_claim_html` (single tag site on
  both idx-None and idx-present paths, RD-7) match verbatim; `_macro_theme_section`'s body-line
  simplification (`_macro_claim_html(c, idx) for c in block.claims`, dropping the old inline idx-None
  branch) matches. 4 new tests match verbatim. OK.
- **Task 5** (`src/irc/monitor/narrative_macro.py`, `src/irc/commands/monitor_cmd.py`,
  `tests/monitor/test_narrative_macro.py`, `tests/monitor/test_acceptance_eval.py`) — `PROMPT_VERSION =
  "3"` + `_MAX_MECHANISM_CHARS = 60` constants; `MacroThemeBlock.mechanism: str | None = None` additive
  field; `_validate_mechanism` (non-str/empty/oversized/sanitizer-changed/language-guard drop reasons,
  never raises, never truncates) and `_split_theme_value` (dict→v3 object dispatch, raises
  `_MacroNarrErr` only when `"claims"` missing/non-list) match verbatim, reusing the module's pre-existing
  `sanitize_untrusted`/`_passes_language_guard` (no new imports needed — both already present at
  narrative_macro.py:13/101). `_PROMPT_SYSTEM_V3` hoisted constant + rewritten `_build_macro_messages`
  match verbatim (hardened-note untouched, AC8). `gather_macro_narrative`'s parse-block rewrite (value→
  `_split_theme_value`→claims+mechanism→`MacroThemeBlock(theme, claims, mechanism)`, claims-driven
  emission unchanged) matches. `monitor_cmd.py` import gains `PROMPT_VERSION`; line 489 (`Provenance`)
  changed from hardcoded `"2"` to `PROMPT_VERSION`. 13 new narrative tests + 1 new acceptance test
  (`test_report_header_prompt_cannot_drift_from_constant`) match verbatim. OK.
- **Task 6** (`src/irc/monitor/render_html.py`, `src/irc/monitor/eval/trace.py`,
  `src/irc/commands/monitor_cmd.py`, `tests/monitor/test_render_html.py`, `tests/monitor/eval/test_trace.py`,
  `tests/commands/test_monitor_cmd.py`) — `_macro_theme_section`'s mechanism line (`<p
  class="macro-mechanism">对本组基金的传导：…</p>`, placed between chips and claims, escaped, absent when
  `None`) matches verbatim; `trace.py:_macro_narrative` block dict gains `"mechanism": b.mechanism`
  (verified: `SCHEMA_VERSION` at trace.py:17 untouched, still `"7"`); `monitor_cmd._narrative_dump`'s
  `__macro__` block dict gains the same key. 3 render tests + 1 trace test (explicit "NO second bump"
  assertion) + 1 narrative-dump test match verbatim. OK.
- **Task 7** (corpus JSON, `src/irc/monitor/eval/metrics_narrative.py`, `evals/monitor_narrative/runner.py`,
  `tests/monitor/eval/test_metrics_narrative.py`, `tests/evals/test_monitor_narrative_runner.py`) —
  `mechanism_1.json`/`mechanism_2.json` (category `"mechanism"`, 16-hex non-colliding citation ids) match
  verbatim. `metrics_narrative.py`'s rewritten `_all_claims` (dual-shape: dict value → `.get("claims",
  [])` when list else `[]`; list value → itself) + verbatim-reproduced `_MAX_MECHANISM_CHARS`/
  `_CJK_MIN_RATIO`/`_is_cjk_char`/`_cjk_ratio` + new `_mechanism_valid` + new `mechanism_validity` match
  the plan's blocks exactly. **Confirmed no `narrative_macro` import added to `metrics_narrative.py`**
  (`grep '^import\|^from'` on the file shows only `from __future__` and `import re` — ADR 0017 §3.3
  scorer-purity held). `runner.py`'s import/`_MECH_TH`/`named_values` row match verbatim; offline test
  update (metric-name set) matches. 12 new metric tests + 1 runner-test update match verbatim. OK.
- **Task 8** (`docs/monitor/README.md`, `docs/diagrams/monitor-workflow.html`, `evals/README.md`,
  `CHANGELOG.md`) — all 4 `docs/monitor/README.md` edits (run-level step 6, schema 6→7 repair ×2, report
  anatomy) match verbatim; diagram's two `<text>` line edits match; `evals/README.md`'s metric-list
  addition matches; `CHANGELOG.md`'s new `### Added` subsection inserted directly under `##
  [Unreleased]`, above the pre-existing block, matches verbatim. `VERSION` file untouched (not in the
  diff's 23-file list). OK.
- **Task 9** (verification sweep, no files) — re-run directly in this drift pass, not trusted from the
  impl agent: `uv run ruff check` on all touched `src/`+`tests/` files for this item → `All checks
  passed!` (the 118 whole-repo `ruff check src tests` errors are pre-existing/unrelated files, confirmed
  none of the 118 hits fall in this item's file list). `uv run pytest tests/monitor/ -q` → 1027 passed, 12
  skipped. Per-file commands suite (never whole-dir): `test_monitor_cmd.py` 57 passed (run standalone in
  background, exit 0, confirmed via notification), `test_monitor_cmd_trace.py` /
  `test_monitor_cmd_forward_eval.py` / `test_monitor_cmd_timeline.py` / `test_monitor_constituent.py` all
  passed as part of the 5-file batch (57 total across the batch matches expectation — no failures).
  `tests/notify/test_monitor_run_kind.py tests/ops/test_launchd_monitor.py
  tests/evals/test_monitor_narrative_runner.py tests/monitor/eval/` → 352 passed. Invariant greps (Step 5)
  re-run directly: `grep -n '^SCHEMA_VERSION' src/irc/monitor/eval/trace.py` → `17:SCHEMA_VERSION = "7"`;
  `git diff ... | grep -E '^[+-]_ENGINE_VERSION'` → empty, rc=1; `git diff ... -- VERSION
  src/irc/monitor/factors.py src/irc/monitor/signal.py src/irc/monitor/eval/forward_log.py` → empty;
  `grep -rn '"2"' src/irc/commands/monitor_cmd.py | grep -i provenance` → empty, rc=1. Golden diff audit:
  `grep -c '^[+-]<'` on the golden-file diff → `2`. All match Step 5/6's expected outputs exactly.

## Drift finding: `tests/monitor/eval/test_corpus_contract.py` `_NARR_CATS` addition (commit b3146466)

**Nature:** commit `b3146466` ("fix(monitor): verification-sweep fixups (002)") changes exactly one line
in `tests/monitor/eval/test_corpus_contract.py`: `_NARR_CATS` gains `"mechanism"`. Confirmed via `git show
--stat b3146466` (1 file, 1 insertion, 1 deletion) and full diff read — no other change in the commit.

**Why it deviates from the plan:** `test_corpus_contract.py` is never named anywhere in the 002 plan
(not in the File Structure table, not in any task). `test_narrative_categories_exact` (AC2 of a *prior*
item) asserts the narrative corpus's category set is exactly a closed set. Task 7 of *this* plan adds
`mechanism_1.json`/`mechanism_2.json` with `"category": "mechanism"` — a new category the closed-set test
had no way to know about, so it breaks mechanically the moment Task 7's corpus files land, with no design
choice available other than adding the literal string.

**Adjudication:** (a) small, forced consequence of Task 7's own new corpus category — not (b) functional
scope creep. Evidence: the fix touches only the one `_NARR_CATS` set literal; it does not alter any
production code path, any metric, any gating threshold, or any behavior the plan's ACs govern; it is
required for the test suite to stay green after Task 7's own additions (which the plan explicitly
specifies), and Task 9 Step 7 explicitly anticipates exactly this class of fixup ("Fix anything red, then
final commit if needed"). No other fixups are bundled into the same commit (verified above). Resolution:
amended `docs/2026-07-03-monitor-v4-explainability/items/002-plan.md` inline (Task 9 Step 7) with a
one-line rationale documenting this as an anticipated, in-scope fixup rather than an untracked file
touch. Not a FAIL.

## Cross-cutting invariants (explicit re-verification)

- `schema_version` stays `"7"` — no second bump. `SCHEMA_VERSION` at `trace.py:17` unchanged; the only
  trace-side diff hunk is the additive `"mechanism": b.mechanism` key inside the existing block dict.
  CONFIRMED.
- `PROMPT_VERSION = "3"` constant defined in `narrative_macro.py:24`; consumed by `monitor_cmd.py:489`'s
  `Provenance(_ENGINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION, "")`. `grep -rn '"2"' monitor_cmd.py | grep
  -i provenance` → empty (rc=1) — no hardcoded `"2"` literal remains. CONFIRMED.
- `_ENGINE_VERSION`, `VERSION`, `src/irc/monitor/signal.py`, `src/irc/monitor/factors.py`,
  `src/irc/monitor/eval/forward_log.py` all have **zero** diff hunks in this range (`_ENGINE_VERSION`
  assignment-line grep empty; the four files are entirely absent from the 23-file changed-file list, and
  a direct scoped `git diff` against them returns nothing). CONFIRMED.
- `mechanism_validity` in `src/irc/monitor/eval/metrics_narrative.py` does NOT import `narrative_macro`
  (module imports are `from __future__ import annotations` and `import re` only) — the validity predicate
  constants/helpers (`_MAX_MECHANISM_CHARS`, `_CJK_MIN_RATIO`, `_is_cjk_char`, `_cjk_ratio`,
  `_mechanism_valid`) are verbatim reproductions per ADR 0017 §3.3 scorer purity, same precedent as the
  pre-existing `_BANNED_VERBS`. CONFIRMED.
- No live LLM call paths added by any new/modified test. All narrative/render/trace/metric tests use
  fakes (`_fake_resp`, monkeypatched `resolve_route`/`_resolve_model`, or pure in-memory fixtures); the
  eval runner tests remain offline (fake `_call`); the corpus additions are data-only JSON fixtures
  consumed by the existing `live_gated` suite (untouched gating). CONFIRMED.
