Verdict: FAIL

Subagent: sonnet
Source: Fallback used: `uv run pytest tests/commands/test_gold_cmd.py -v` + direct Python import smoke against `data/research/` snapshot + integration test run.
Entry point exercised: `uv run pytest tests/commands/test_gold_cmd.py -v` (22/22 PASS, 0.84 s); Python smoke against `data/research/` snapshot confirming F5 extractor on real corpus.

Observed behavior:

  - AC #1 (4 problem themes show paragraphs, not bare subheadings) — PASS.
    `_summary_from_theme_report` run against real `data/research/` snapshot:
    - `cn_monetary`: `'本周央行连续开展7天期逆回购操作…'` (len=62, terms=2) — subheading `### 央行最近一周货币政策操作与表态` skipped.
    - `geopolitics`: `'**Military Stalemate**: Putin's anticipated…'` (len=200) — bold+trailing prose NOT skipped per grill Q2 rule.
    - `us_fiscal_politics`: `'Long-term Treasury yields have surged…'` (len=400) — subheading `**1. Bond Market Pressure and Policy Response**` skipped.
    - `cn_equity_property_policy`: `'**政策优化信号**：2026年4月30日…'` (len=210) — bold+trailing prose NOT skipped.
    All 4 problem themes produce paragraph-shaped prose rather than the bare heading label.

  - AC #2 (paragraph-depth rule: ≥3 terminators OR ≥150 chars, blank line stops after ≥1 prose) — PASS.
    `test_summary_accumulates_until_three_sentence_terminators`, `test_summary_accumulates_until_150_chars_floor`, `test_summary_stops_at_blank_line_after_first_prose` all pass. Blank-line-before-first-prose correctly skipped (`test_summary_stops_at_blank_line_after_first_prose` fixture starts with `\n\n`).

  - AC #3 (hard char cap 400 with `…` suffix) — PASS.
    `test_summary_truncates_at_400_char_cap_with_ellipsis` passes (len=400, ends with `…`). On real corpus: `us_fiscal_politics` (len=400, ends `…`) and `gold_drivers` (len=400, ends `…`) both truncated correctly; remaining 5 themes under cap.

  - AC #4 (bullet markers stripped on first + continuation lines) — PASS.
    `test_summary_strips_bullet_markers_on_first_and_continuation_lines` passes. No output for any theme starts with `- `, `* `, or `+ ` on the real corpus.

  - AC #5 (deterministic byte-equality) — PASS.
    Two consecutive calls against same `data/research/` snapshot produce SHA256 `67134db5fb64728f` both times. `test_macro_pillar_renders_paragraph_shaped_excerpt_post_f5` also asserts same `ref.summary` across construction.

  - AC #6 (≥6 of 7 themes paragraph-shaped on current corpus; §3 inherits fix) — PASS.
    Real corpus results: us_monetary (len=188,terms=1 ≥150), cn_monetary (len=62,terms=2 — MINIMAL, ≥1 term), geopolitics (len=200,terms=1 ≥150), us_fiscal_politics (len=400,terms=2 ≥150), cn_equity_property_policy (len=210,terms=4 ≥3), gold_drivers (len=400,terms=3 ≥3), holdings_sector (len=99,terms=5 ≥3). 6/7 meet ≥150-or-≥3; cn_monetary is the 1 minimal case with terms=2 but len=62 (below 150 floor). cn_monetary meets the AC spec minimum (≥1 term, not a bare subheading). §3 gold_drivers (len=400,terms=3 ≥3) and geopolitics (len=200,terms=1 ≥150) both pass the sub-criterion.

  - AC #7 (IRC_MACRO_LINES_BEGIN/END and IRC_GOLD_EVIDENCE_BEGIN/END markers preserved) — PASS.
    `test_macro_pillar_renders_paragraph_shaped_excerpt_post_f5` asserts `MACRO_SECTION_MARKER_BEGIN`/`MACRO_SECTION_MARKER_END` present. Rendered §3 block via `render_gold_evidence_body` confirmed `<!-- IRC_GOLD_EVIDENCE_BEGIN -->` and `<!-- IRC_GOLD_EVIDENCE_END -->` present.

  - AC #8 (citation marker `[ref:hex16]` per theme in evidence) — PASS.
    All 7 theme rows in `gold_regime.json["evidence"]` have `citation_id` matching `[0-9a-f]{16}`: us_monetary=`6489724e2a91d33d`, cn_monetary=`7e9186993646268c`, geopolitics=`a6a313908ecad928`, us_fiscal_politics=`77158bfe5578f8f1`, cn_equity_property_policy=`fca3e7e41c5e0c14`, gold_drivers=`4797cf536b748f4b`, holdings_sector=`a4cd8df1c92bf922`. `test_macro_pillar_renders_paragraph_shaped_excerpt_post_f5` also asserts `re.search(r"\[ref:[0-9a-f]{16}\]", body) is not None`.

  - AC #9 (citation_id churn documented in ADR 0008) — PASS.
    ADR 0008 §3 "Citation_id churn is expected and documented" present with full rationale, two-run byte-equality note, and memo §2/§3 integrity explanation.

  - AC #10 (H3 + SAME-3 invariants preserved) — PASS.
    Integration test suite run. 4 failing tests are pre-existing on `main` (confirmed by running same tests against `main` — identical 4 failures: `test_opportunity_pipeline_produces_three_outputs`, `test_opportunity_pipeline_preserves_holdings_even_when_dropped`, `test_qdii_appears_in_rejections_with_qdii_reason`, `test_memo_cites_only_publishable_citation_ids`). F5 introduces no new integration failures.

  - AC #11 (TDD coverage — 8 required test cases) — PASS.
    22/22 tests pass. The 8 required cases are all present and named: `test_summary_skips_double_hash_subheading`, `test_summary_skips_triple_hash_subheading`, `test_summary_skips_pure_bold_line` (pure bold skip), `test_summary_does_not_skip_bold_with_trailing_prose`, `test_summary_accumulates_until_three_sentence_terminators`, `test_summary_accumulates_until_150_chars_floor`, `test_summary_stops_at_blank_line_after_first_prose`, `test_summary_truncates_at_400_char_cap_with_ellipsis`, plus 2 P0 sentinel tests, the `[N]` marker strip test, the failure_reason test, real-world shape smoke, and 2 macro_pillar end-to-end tests.

  - AC #12 (no edits to `llm.yaml` memo_synthesis task) — PASS.
    `git diff main...HEAD -- src/irc/templates/config/llm.yaml` returns empty. memo_synthesis task verified present and unmodified.

  - AC #13 (function size budget: `_first_prose_paragraph` < 30 lines) — FAIL.
    `ast.parse` reports `_first_prose_paragraph` spans lines 211–259 (49 total). The spec AC #13 states it "stays < 30 lines". While 19 of those lines are docstring, the AST count is 49. The actual logic block (lines 232–259) is 28 lines — on the edge — but the function as measured by the spec criterion (total lines) is clearly over budget. No separate private helper was extracted to compensate. The function remains readable and correct; this is a style-budget miss, not a correctness failure.

  - AC #14 (ADR 0008 lands) — PASS.
    `docs/adr/0008-macro-research-excerpt-depth.md` exists (101 lines). Contains: extractor-not-prompt decision (§Context, §Decision §1), skip-rule + accumulator algorithm, `max_chars=400` rationale (§Decision §2), citation_id churn expectation (§Decision §3), F5-followup-prompt-eval deferral (§Decision §4), non-goals, consequences, and related ADRs. CONTEXT.md "Macro excerpt rendering" subsection adds 4 glossary terms: all 4 found (`Deterministic theme excerpt`, `Macro excerpt depth`, `Macro excerpt char cap`, `Theme-excerpt citation_id churn`).

  - AC #15 (`F5-followup-prompt-eval` SKIPPED entry appended) — FAIL.
    `docs/2026-05-27-pickability-followups/SKIPPED.md` is 5 lines containing only the preamble. No `F5-followup-prompt-eval` entry has been appended. The ADR 0008 §Decision §4 documents that the entry "lands in `docs/2026-05-27-pickability-followups/SKIPPED.md`" and lists the required fields (scope, eval-corpus prerequisite, success rubric, back-pointer to ADR 0008), but the file itself is empty of this entry. This is a required deliverable per spec AC #15 that was not shipped.

  - AC #16 (cross-stage citation universe integrity) — PASS.
    Both §2 and §3 render `[ref:...]` markers from the same `evidence_by_source` map populated from `ThemeReportRef.summary`. `tests/integration/test_publishable_set_lockdown.py` reads the citation universe from `gold_regime.json["evidence"]`; test file references gold_regime confirmed present. No citation_ids are minted outside this universe.

  - P0 fix: distinct over-skip sentinel — PASS.
    `test_summary_returns_overskip_sentinel_when_lines_exist_but_all_skipped` asserts `"（报告内容均为标题/小节，未找到正文段落）"` (distinct from `"（报告为空）"`). Implementation at `gold_cmd.py` L278–284 branches on `prose.strip()` to choose sentinel.

  - P0 fix: `[N]` markers stripped — PASS.
    `test_summary_strips_llm_source_citation_markers_from_excerpt` asserts `[1]`..`[4]` absent, content words present. `_LLM_REF_MARKER_RE = re.compile(r"\s*\[\d{1,2}\]\s*")` at L59; applied in `_first_prose_paragraph` L245.

Failures attributable to F5:
  - AC #13: `_first_prose_paragraph` is 49 AST lines (spec budget < 30). Functional logic is ~28 lines; docstring is 18 lines. Style miss, not correctness failure.
  - AC #15: `F5-followup-prompt-eval` SKIPPED entry missing from `docs/2026-05-27-pickability-followups/SKIPPED.md`.

Pre-existing failures (not attributable to F5): 4 integration tests fail identically on `main`.
