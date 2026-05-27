# F5 — §2 macro research excerpts: heading → paragraph

**Run**: `2026-05-27-pickability-followups`
**Origin**: `docs/2026-05-27-instrument-pickability/SKIPPED.md` F5
**Phase**: spec (Opus brainstorming-as-design)
**Locked dep-scan write surface** (from MASTER-PLAN):
`src/irc/research/synthesize.py`, `src/irc/research/theme_research.py`,
`src/irc/memo/macro_pillar.py`, `src/irc/templates/config/llm.yaml`
(`memo_synthesis` task); secondary `docs/adr/0008-macro-research-excerpt-depth.md`,
tests under `tests/research/` + `tests/memo/`.

---

## Goal

Make memo §2 "本周宏观研究要点" render a **substantive paragraph-shaped excerpt** for
every theme report instead of a heading-fragment first line. The data is already
on disk under `data/research/<theme>.md` and already flows through
`gold_regime.json["evidence"]` via `_summary_from_theme_report`; the symptom is
that the current extractor takes only the FIRST non-empty line of the prose
body, which is often a `### subheading` or `**bold subheading**` rather than
the first real sentence. F5 fixes the **extractor**, not the LLM prompt: we
replace "first non-empty line" with a deterministic "first prose paragraph
(skipping markdown subheadings; capped at ≥3 sentences or ≥150 chars)"
strategy, all within `src/irc/commands/gold_cmd.py::_summary_from_theme_report`
and the shared `extract_prose_from_report_md` helper invariants that landed in
F4. The LLM `memo_synthesis` prompt redesign + 5-week eval bench called for by
SKIPPED.md F5 is **explicitly deferred** to a new SKIPPED entry
`F5-followup-prompt-eval` — see "Reconciliation" below.

## Current state (post-F4, on `autodev/pickability-followups-feature`)

Empirically inspected `outputs/2026-05-27/memo.md` lines 21–28 and
`data/research/*.md` on the feature branch. F4 landed
`extract_prose_from_report_md` correctly: the `# <theme>` heading and
`## Citations` footer are stripped before any consumer reads the prose. But
`gold_cmd._summary_from_theme_report` then iterates `prose.splitlines()`, picks
the FIRST non-empty stripped line, drops leading `- / * / +` bullet markers,
and truncates to 220 chars. For 3 of 7 themes (`us_monetary`, `gold_drivers`,
`holdings_sector`) the report's first prose line happens to be a real
sentence, so §2 reads well. For the other 4 (`cn_monetary`, `geopolitics`,
`us_fiscal_politics`, `cn_equity_property_policy`) the first prose line is a
markdown subheading — `### 央行最近一周货币政策操作与表态`,
`### Geopolitical Events Report: Week of May 20–27, 2026`,
`**1. Bond Market Pressure and Policy Response**`,
`**政策优化信号**：…` — so memo §2 shows the LABEL of the report's first
section instead of any content. The "heading-only" symptom from
SKIPPED.md persists post-F4 for >50% of themes; the F4 helper was a
necessary cleanup but not sufficient to fix the rendered §2 excerpt depth.

## Reconciliation with `SKIPPED.md` F5

SKIPPED.md framed F5 as "LLM prompt redesign + 5-week historical eval bench,
commit only if quality improves ≥4/5 weeks". That framing was correct given
the un-instrumented state at the time, but it conflates two distinct problems:

1. **Prompt quality** — does the LLM produce summary-worthy first paragraphs?
2. **Extraction quality** — does our deterministic extractor pull a sensible
   slice out of whatever the LLM produced?

The post-F4 evidence (above) shows the extractor is the dominant failure mode
for 4/7 themes: the LLM already produced multi-paragraph prose with proper
sentences, but our `splitlines()[0]` strategy grabs subheadings instead. Fixing
the extractor is a small deterministic change that:

- ships today without a 5-week eval-bench framework (which does not exist),
- is byte-deterministic on the same `data/research/` snapshot (the determinism
  contract of `gold_regime.json` / memo locks is preserved by construction),
- can be regression-tested with a single-week fixture from `data/research/`,
- does not touch LLM tokens or cost.

The LLM-prompt redesign + 5-week eval bench moves to a new SKIPPED entry
**`F5-followup-prompt-eval`** for a future autodev run. Per MASTER-SPEC §"Known
risks" §F5, this is the documented fallback when "we cannot produce a 5-week
corpus today" — and we cannot (no historical research snapshots, no eval
harness, no quality rubric). The fallback is the spec.

The position chosen is therefore **(a) deterministic extractor improvement**;
**(b) LLM prompt redesign** is deferred. **(c) multi-paragraph "render
everything between the heading and citations footer"** is rejected because it
would balloon §2 from ~7 lines to ~70 lines and bury the dashboard intent of
the section.

---

## Acceptance criteria

Each item below is independently verifiable. All must be green.

1. **Subheading-skip rule.** `_summary_from_theme_report(report)` skips any
   prose line whose `stripped` form (a) starts with `##` (markdown
   subheading at any depth), or ~~(b) is entirely wrapped in `**...**` /
   `__...__` (a bold-only line with no trailing prose)~~ — corrected by
   grill: predicate tightened to `re.fullmatch(r"\*\*[^*]+\*\*", stripped)`
   / `re.fullmatch(r"__[^_]+__", stripped)` so lines like
   `**政策优化信号**：…` (bold marker followed by trailing prose) DO NOT
   skip, while pure bold-only lines like `**1. Bond Market Pressure and
   Policy Response**` DO skip — or (c) is empty BEFORE any prose line has
   entered the accumulator buffer (blank lines AFTER the first prose
   line behave per rule (iii) in AC #2, not as skips). The first prose
   line is the FIRST line not matching any of those three skip
   conditions. Bullet markers (`- `, `* `, `+ `) are still stripped as
   today (preserves substance of bullet content) — and ALSO stripped from
   continuation lines during accumulation (per grill resolution Q10).

2. **Paragraph-depth rule.** After locating the first prose line, the
   extractor accumulates additional non-skip lines until **either** (i) it
   has collected ≥3 sentence-ending punctuation marks
   (`{".", "。", "！", "!", "?", "？"}`) **or** (ii) the joined text reaches
   ≥150 visible characters (excluding leading/trailing whitespace), **or**
   ~~(iii) a blank line is encountered~~ — corrected by grill: (iii) a
   blank line is encountered AFTER `≥1` prose line is in the buffer.
   Blank lines BEFORE the first prose line are skipped, not terminating
   (otherwise reports starting `### subheading\n\n本文论述...` would
   short-circuit to empty). Whichever condition fires first
   stops accumulation. The result is joined with a single ASCII space
   between lines (mirrors the existing "compact paragraph" rendering
   convention used by `cn_equity_property_policy` which already reads
   well as a one-paragraph block).

3. **Hard char cap retained.** The combined paragraph is truncated to
   `max_chars=400` (raised from 220 — paragraph-shaped excerpts need
   more room; ~~cap of 400 chosen so memo §2 stays under ~15 visible
   lines for all 7 themes~~ — corrected by grill: worst-case is
   7 × 400 / ~50 ≈ **~25 visible lines**, typical 10–15 because the
   150-char floor fires more often than the 400-char ceiling. §2
   remains a single-screen dashboard either way). When truncated,
   suffix `…` (single horizontal-ellipsis char) is appended. The
   existing per-call `max_chars` kwarg is preserved as a kwarg-only
   override so tests can pin behaviour at smaller caps.

4. **Empty-content fallback unchanged.** When the prose is empty (no
   prose lines or all lines hit the skip rules), return the existing
   sentinel `"（报告为空）"`. When `report.failure_reason` is non-empty,
   return `f"研究采集失败：{report.failure_reason}"` unchanged.
   Existing test
   `tests/commands/test_gold_cmd_summary_from_theme_report.py` (whichever
   file currently covers the empty/failure cases) stays green or is
   updated to match the new signature without changing semantics.

5. **Deterministic byte-equality.** Two consecutive `uv run irc run --only gold`
   invocations against the same `data/research/` snapshot produce
   byte-identical `outputs/<date>/gold_regime.json` files. Captured as a
   regression test (new or extension of the existing gold determinism
   test) that compares two SHA-256 digests of `gold_regime.json`.

6. **memo §2 paragraph rendering — current corpus.** Against the
   captured `data/research/` snapshot on `2026-05-27`, **at least 6 of
   the 7 theme excerpts** rendered in memo §2 "本周宏观研究要点"
   contain ≥3 sentence-ending punctuation marks **OR** are ≥150 chars
   long (one of the two conditions). The 7th theme (worst case) MUST
   render at minimum ≥1 sentence-ending punctuation mark, never a bare
   subheading. Regression test loads `outputs/2026-05-27/memo.md`,
   extracts the §2 block between `<!-- IRC_MACRO_LINES_BEGIN -->` /
   `<!-- IRC_MACRO_LINES_END -->`, and asserts the count. **Grill-added
   sub-criterion:** the §3 gold-evidence block, similarly bounded by
   `<!-- IRC_GOLD_EVIDENCE_BEGIN -->` / `<!-- IRC_GOLD_EVIDENCE_END -->`,
   contains paragraph-shaped excerpts for both included themes
   (`gold_drivers`, `geopolitics`) under the same ≥150-char-OR-≥3-sentence
   depth definition — §3 inherits the fix because it reads the SAME
   `ThemeReportRef.summary` field as §2.

7. **memo §2 deterministic markers preserved.** The
   `<!-- IRC_MACRO_LINES_BEGIN -->` / `<!-- IRC_MACRO_LINES_END -->`
   markers continue to surround the §2 macro lines block, and §3's
   `<!-- IRC_GOLD_EVIDENCE_BEGIN -->` / `<!-- IRC_GOLD_EVIDENCE_END -->`
   markers also continue to render their (now-longer) excerpts. The
   synthesizer LLM prompt still receives the deterministic-block
   "leave verbatim" instruction. CONTEXT.md "Renderers + alias-builder"
   invariants unchanged.

8. **Citation marker invariant preserved.** Every excerpt bullet in
   §2 / §3 still ends with exactly one `[ref:...]` marker pointing at
   the theme's `citation_id`. The marker regex `\[ref:[0-9a-f]{16}\]`
   (ADR 0001) continues to match every bullet. No new citation_ids
   are minted by F5 (extractor change is content-only; the evidence
   row's `citation_id` derives from `(source, summary[:64], date)` —
   note the summary change DOES affect the citation_id because the
   preimage includes `summary[:64]`; this is addressed in AC #9).

9. **Citation ID stability handling.** Because `ThesisEvidence.citation_id`
   is derived from a sha256 over `(owner_instrument_id, scope,
   constituent_key, type, canonical_url_or_fallback, date)` where
   `canonical_url_or_fallback` falls back to `f"{source}:{date}:{summary[:64]}"`
   when URL is empty (ADR 0001 §2), changing the extracted summary
   for theme-report evidence WILL change those rows' citation_ids.
   This is acceptable and expected — there is no cross-run stability
   contract on citation_ids (they are content hashes); the publishable
   set is rebuilt from scratch each run. The two-run byte-equality test
   (AC #5) covers same-snapshot reproducibility, which is the only
   stability contract that exists. A note documenting this expected
   churn lands in ADR 0008.

10. **H3 + SAME-3 invariants preserved.** Picks-table / evidence-pool /
    discipline citation-set equality continues to hold for every
    publishable row. Macro theme citations are scope-`asset_class_macro`
    and feed the §2 / §3 renderers only; they are excluded from the
    per-instrument SAME-3 check by construction (the macro universe is
    read from `gold_regime.json["evidence"]`, not from
    `OpportunityRow.thesis_evidence`). The publishable-set lockdown
    integration test stays green.

11. **TDD coverage (red-first).** New unit tests under
    `tests/commands/test_gold_cmd_summary_from_theme_report.py` (or
    sibling, mirroring source path) cover: (i) subheading-skip for
    `###` and `## `; (ii) bold-only-line skip for `**foo**` lines;
    (iii) paragraph accumulation stops at 3 sentence terminators;
    (iv) paragraph accumulation stops at ≥150 chars; (v) paragraph
    accumulation stops at blank line; (vi) char cap truncation
    appends `…`; (vii) empty-prose returns `"（报告为空）"`;
    (viii) failure_reason returns the failure string. All tests
    written BEFORE the implementation per CLAUDE.md TDD rule.

12. **No regression in the LLM `memo_synthesis` prompt.** No edits to
    `src/irc/templates/config/llm.yaml` `memo_synthesis` task. No
    edits to `src/irc/memo/synthesizer.py` prompts. F5 is a
    pure-Python extractor change. (Grill phase may surface a desire
    to nudge the prompt; that's an `F5-followup-prompt-eval`
    concern, not this spec's.)

13. **File / function size budget.** `_summary_from_theme_report`
    stays < 30 lines (currently ~25). If the new logic pushes it
    over, extract a private helper
    `_first_prose_paragraph(prose: str, *, max_chars: int) -> str`
    co-located in `gold_cmd.py` ~~or a new tiny module
    `src/irc/research/excerpt.py` (< 200 lines). Prefer the new
    module because the same paragraph-extraction logic could later be
    consumed by `news_summaries._summary_for_theme` (F4's analogue);
    grill phase to confirm placement.~~ — corrected by grill (Q6): keep
    `_first_prose_paragraph` PRIVATE inside `gold_cmd.py`. The
    speculative consolidation with `news_summaries._summary_for_theme`
    is rejected — `news_summaries` consumes the WHOLE prose for keyword
    scoring, not the first paragraph; sharing the helper would silently
    change the scoring rubric's input. YAGNI applies. No new module.

14. **ADR 0008 lands with this item.** New
    `docs/adr/0008-macro-research-excerpt-depth.md` documents:
    the extractor-not-prompt decision, the skip-rule + accumulator
    + cap algorithm, the citation_id-churn expectation (AC #9), the
    deterministic two-run byte-equality contract (AC #5), the
    deferral of LLM prompt redesign + 5-week eval bench to
    `F5-followup-prompt-eval`, and the relationship to ADR 0007 §3a
    (prose-extraction invariant — F5 builds on top of
    `extract_prose_from_report_md`, never bypasses it).

15. **`F5-followup-prompt-eval` SKIPPED entry.** ~~A new entry in
    **this run's** `docs/2026-05-27-pickability-followups/SKIPPED.md`
    (or, if that file does not exist yet, this item creates it with
    just this entry)~~ — corrected by grill (Q9): the file
    `docs/2026-05-27-pickability-followups/SKIPPED.md` already exists
    in the run dir; F5 APPENDS the entry. Entry captures:
    - the LLM-prompt-redesign + 5-week eval bench scope
    - the eval-corpus prerequisite (5 weekly snapshots of `data/research/`)
    - the success rubric (≥4/5 weeks improved, where "improved" is
      defined as per AC #6 paragraph-depth metric)
    - a pointer back to ADR 0008 and this spec

16. **(Grill-added)** Cross-stage citation universe integrity. Memo
    §2/§3 `[ref:...]` markers MUST resolve to the post-F5 citation_ids
    present in `gold_regime.json["evidence"]`. By construction this
    holds — both surfaces are rendered from the same `evidence_by_source`
    map populated from the (now-longer) `ThemeReportRef.summary`. The
    publishable-set lockdown integration test
    (`tests/integration/test_publishable_set_lockdown.py` AC19) reads
    the citation universe from `opportunity_report.json["rows"]` ∪
    `gold_regime.json["evidence"]` and stays green. F5 introduces no
    citation_ids outside that universe.

---

## Non-goals

1. **LLM `memo_synthesis` prompt redesign.** No prompt changes. No new
   LLM task. Position (a) is locked; the prompt-redesign path is
   deferred to `F5-followup-prompt-eval`.

2. **5-week eval bench / corpus capture infrastructure.** No new
   fixtures replaying historical `data/research/` weeks. No new eval
   harness. No new CLI command. The eval bench is the
   prerequisite-of-the-deferred-followup, not this item's deliverable.
   Building it ON THIS ITEM would push surface area outside the locked
   dep-scan and balloon token cost (per MASTER-SPEC §"Known risks" F5).

3. **Multi-paragraph rendering.** Even though the extractor *could*
   return the entire prose body (it is already available via
   `extract_prose_from_report_md`), §2's dashboard intent is a
   one-glance survey; multi-paragraph rendering would bury picks-table
   §5 below the fold. The ≥3-sentence / ≥150-char target is the
   product judgment.

4. **New citation rows / new evidence sources.** No new
   `ThesisEvidence` records emitted by F5. Macro evidence row count
   stays identical (5 macro snapshots + N theme refs, same as today);
   only the `.summary` field content changes per row. Citation_id
   churn (AC #9) is acknowledged but no new IDs.

5. **Per-asset-class theme filtering in §2 / §3.** F4's
   `themes_for_instrument` mapping is for *scoring* (which themes
   feed an instrument's `thesis_news` factor), not for *rendering*
   §2 macro. Memo §2 continues to render ALL 7 themes in
   `_THEME_DISPLAY_NAMES`-fixed order (`us_monetary`, `cn_monetary`,
   `geopolitics`, `us_fiscal_politics`, `cn_equity_property_policy`,
   `gold_drivers`, `holdings_sector`). No interaction with F4.

6. **Memo §5 / §7 picks-table or execution-lines changes.** F5
   touches §2 / §3 macro evidence rendering only. No edits to
   picks-table.py, execution_lines, evidence_pool, or any other
   memo section. The two paragraphs of "macro" excerpts that already
   render in §3 (gold-evidence block) get the same paragraph-depth
   benefit incidentally because §3 reads from the same
   `ThemeReportRef.summary` field — no §3-specific changes needed.

7. **Edits to `news_summaries._summary_for_theme`.** Though
   structurally similar, F4's `news_summaries._summary_for_theme`
   has a different consumer contract (it feeds the scoring keyword
   rubric, not human-readable memo prose). Whether to consolidate the
   two with a shared `_first_prose_paragraph` helper is an
   implementation-detail choice for the grill phase (AC #13). If
   consolidation happens, it does NOT change the scoring rubric's
   behaviour — `score_thesis_news` already handles arbitrary-length
   summaries — but the unit tests for `news_summaries` must stay
   green untouched.

8. **`data/research/<theme>.md` schema changes.** No new fields, no
   new headings, no new format. The raw theme reports stay exactly
   as `format_report_markdown` emits them today.

9. **Live LLM tests.** No new `pytest.mark.live_llm` tests. F5 is
   pure-Python deterministic logic against on-disk fixtures.

---

## Constraints

1. **TDD mandatory** (CLAUDE.md "All coding must follow TDD"). Every
   new behaviour lands red-first: AC #11's 8 test cases are written
   before any change to `_summary_from_theme_report`. Existing tests
   stay green throughout.

2. **Deterministic memo locks** (CONTEXT.md "Renderers + alias-builder"
   §`IRC_*_BEGIN/END`). The synthesizer prompt's "leave verbatim"
   contract for `<!-- IRC_MACRO_LINES_BEGIN/END -->` and
   `<!-- IRC_GOLD_EVIDENCE_BEGIN/END -->` is untouched. The longer
   excerpts simply produce a longer deterministic block; the LLM
   still copies it verbatim.

3. **H3 + SAME-3 invariants** (CONTEXT.md, ADR 0004). F5 does NOT
   touch `_write_opportunity_outputs`, `thesis_evidence`,
   `evidence_pool`, or the discipline renderer. Macro-scope evidence
   is excluded from SAME-3 by construction (scope filter inside
   `select_citations` and friends), so changing its `.summary` field
   cannot break SAME-3. The publishable-set lockdown integration
   test is the regression gate.

4. **Citation ID format** (ADR 0001). `\[ref:[0-9a-f]{16}\]` matched
   by every bullet. No format change.

5. **FP / immutable** (CLAUDE.md "Functional, immutable"). New code
   is pure functions: input `report_md` string → output excerpt
   string. No module-level mutable state. The `_THEME_DISPLAY_NAMES`
   and `_MACRO_DISPLAY_NAMES` dicts in `gold_cmd.py` stay frozen.

6. **Effects at edges** (CLAUDE.md). `load_theme_reports` (filesystem
   read) stays in `research/persistence.py`. The extractor functions
   are pure and don't touch disk.

7. **File / function size budget**. Functions < 20 lines (ideal);
   the new `_first_prose_paragraph` helper sits within budget.
   `gold_cmd.py` currently 327 lines — adding a small helper keeps
   it under the 200-line ideal for *new* modules but tolerable for
   this CLI command file (no project rule rewrites historical
   command files mid-flight). If the helper moves to
   `src/irc/research/excerpt.py`, that new file is < 100 lines.

8. **No `基金概况` indicator** (CONTEXT.md "Things you'll trip over").
   Irrelevant to F5 (no AkShare fetch code), but the acceptance grep
   test continues to pass.

9. **Live-test gate** (CONTEXT.md). N/A — no live calls in F5.

10. **Run-level branch / PR shape** (MASTER-PLAN). Branch
    `claude/pickability-followups-F5` is cut off
    `autodev/pickability-followups-feature`. PR opens against the
    feature branch, not `main`. Squash-merge after all 6 verdict
    files PASS.

11. **Project conventions for citation_id determinism** (ADR 0001
    §2). Acknowledged that summary content drives citation_id; the
    contract is "same content → same id, different content →
    different id". F5 changes content, so ids change — no contract
    violated. ADR 0008 documents the expected churn.

---

## Open questions resolved during brainstorming

### Q1 — Heading-only symptom: still real after F4?

**Resolved: yes, for 4 of 7 themes.**

Empirically inspected `outputs/2026-05-27/memo.md` lines 21–28
post-F4. `us_monetary`, `gold_drivers`, `holdings_sector` render
well (real first sentence). `cn_monetary`, `geopolitics`,
`us_fiscal_politics`, `cn_equity_property_policy` render the bold
subheading or `### subheading` of their first internal section.
F4's `extract_prose_from_report_md` correctly strips the top-level
`# <theme>` heading and `## Citations` footer, but the first
remaining line is often a `### subheading` because LLM research
prompts produce well-structured multi-section reports. The extractor
must skip past subheadings to find prose.

### Q2 — Three position choices: extract-deeper vs LLM-prompt-redesign vs multi-paragraph

**Resolved: extract-deeper (position a).**

Rationale: (i) prompt redesign requires a 5-week eval bench that
does not exist — building it is its own project, dwarfs the
benefit; (ii) multi-paragraph rendering would balloon §2 to ~70
lines and bury §5's picks table; (iii) extract-deeper is a
~20-line code change with deterministic byte-equality guarantee and
ships today. SKIPPED.md was conservative in framing only path
(b); post-F4 inspection shows path (a) is sufficient for 6 of 7
themes (AC #6).

### Q3 — Why a NEW skip-rule (subheadings + bold-only lines) rather than just "more lines"?

**Resolved: skip-rule first, then accumulate.**

Naive "take first 3 lines" would in many cases produce
`### Section Heading\n\n**1. First subsection title**\n...` which
reads worse than today's "single subheading" output. The skip rule
is the surgical fix; the accumulator is the depth fix. They
compose.

### Q4 — Why 150 chars / 3 sentences and not (e.g.) "first paragraph as defined by blank-line boundary"?

**Resolved: 150-char OR 3-sentence OR blank-line, whichever fires
first.**

Reports vary: some are paragraph-shaped (`us_monetary`,
`gold_drivers`) where the first paragraph is naturally ≥3
sentences; some are bullet-list-shaped (`geopolitics`) where each
bullet is its own "paragraph" by blank-line definition and a single
bullet may be only ~80 chars. The hybrid rule guarantees ≥150
chars of substance in either format. The 150-char floor was chosen
empirically: shorter feels fragmentary, longer crowds the
dashboard. Configurable via `max_chars` kwarg if grill phase
disagrees.

### Q5 — Where does the helper live?

**Resolved: tentatively `src/irc/research/excerpt.py` (new file,
small).**

Pros: shared with potential future `news_summaries` consolidation;
keeps `gold_cmd.py` from growing; mirrors the F4 pattern of
extracting reusable pure helpers into focused modules
(`extract_prose_from_report_md` lives in
`research/persistence.py`). Cons: very small new module
(~30 lines). Grill phase may choose to inline back into
`gold_cmd.py` if the news_summaries consolidation is rejected
as out of scope.

### Q6 — Citation_id churn (AC #9): is this acceptable?

**Resolved: yes, expected.**

ADR 0001 §2 explicitly states citation_id is content-derived; there
is no cross-run id stability contract. Same-run two-pass byte
equality (AC #5) is the only stability invariant and is preserved.
Operators reviewing diff-of-runs across the F5 deploy date will
see macro-theme citation_ids change once and then stabilise.
Documented in ADR 0008 to forestall surprise.

### Q7 — Where does the SKIPPED entry for the deferred prompt redesign live?

**Resolved: a new `docs/2026-05-27-pickability-followups/SKIPPED.md`
created with this item if it does not already exist.**

The convention from `docs/2026-05-27-instrument-pickability/SKIPPED.md`
is "deferred items the autodev orchestrator surfaces back to the
user at run close-out". This run's SKIPPED.md becomes that file.
The entry includes scope, prerequisite (5-week corpus), success
rubric (paragraph-depth metric per AC #6), and back-pointers.

### Q8 — Could not resolve from MASTER-SPEC + code anchors alone

**One soft question, deferred to grill / impl:**

Whether `_first_prose_paragraph` should also strip inline citation
markers `[N]` (e.g. `[2][3]`) that appear in the middle of
theme-report sentences. Currently rendering leaves them in (see
memo line 24: "…manpower [2]." — the inner `[2]` is the
theme-report's own citation index, distinct from the trailing
`[8]` which is the macro evidence pool index). Leaving them in
is verbose but truthful; stripping them is cleaner but loses
provenance. Default: leave them in (matches today's behaviour
for the 3 themes that already read well). If reviewers push back,
this is a one-line regex strip; not blocking the spec.

---

## Why this scope fits today (executive summary for orchestrator)

- **Solves the user-visible symptom** for 6 of 7 themes immediately.
- **No new infrastructure** — no eval bench, no fixture corpus, no
  LLM tokens, no live tests.
- **Deterministic** — same input → same output, byte-equality
  preserved.
- **Reversible** — the change is ~20 lines in a pure function;
  rollback is one revert.
- **Defers ambitious work honestly** — `F5-followup-prompt-eval`
  SKIPPED entry captures the prompt redesign + eval bench so the
  user knows what is NOT done.
- **Respects locked invariants** — H3, SAME-3, deterministic memo
  markers, citation-format, FP/immutable, effects-at-edges, all
  preserved.

---

## Resolved decisions

Twelve questions resolved during the grill-with-docs session (autonomous
mode — no user in loop, recommendations auto-accepted). Each Q/A pair
below records the question, the auto-accepted recommendation, the
rationale, and the documentation impact.

- **Q1: Does the `##`-prefix skip rule actually catch the offending
  `###` subheadings?**
  A: Yes. `extract_prose_from_report_md` already strips lines starting
  with single `#`; only `##`+ survives. `stripped.startswith("##")`
  catches `## subheading`, `### subsubheading`, and deeper. AC #1
  wording is correct as-is.
  Rationale: verified against `src/irc/research/persistence.py`.
  Doc impact: none.

- **Q2: What counts as "entirely wrapped in `**...**`"?**
  A: Tighten to regex `re.fullmatch(r"\*\*[^*]+\*\*", stripped)` /
  `re.fullmatch(r"__[^_]+__", stripped)`. Lines like
  `**政策优化信号**：…` (bold marker + trailing prose) DO NOT skip;
  lines like `**1. Bond Market Pressure...**` (pure bold) DO skip.
  Rationale: the original AC #1 wording "entirely wrapped" is
  ambiguous — the regex makes it precise.
  Doc impact: spec AC #1 corrected; CONTEXT.md "Macro excerpt depth"
  documents the predicate.

- **Q3: Should `_first_prose_paragraph` strip inline `[N]` citation
  markers from the excerpt?**
  A: No — leave them in (matches today's behaviour for the 3 themes
  that already read well).
  Rationale: stripping changes summary content → changes citation_id
  → expands F5 churn surface needlessly. Semantic gain is nil; the 3
  working themes already render fine with `[N]` markers inline.
  Doc impact: ADR 0008 §1 "Trade-offs considered".

- **Q4: Does `max_chars=400` fit the "~15 visible lines" assertion?**
  A: No — worst-case is ~25 lines; typical is 10–15. Correct AC #3
  to acknowledge the worst-case bound honestly.
  Rationale: 7 themes × 400 chars / ~50 chars-per-line = 56 lines
  theoretical worst case; the 150-char floor fires far more often
  than the 400-char ceiling, so empirical typical is 10–15.
  Doc impact: spec AC #3 corrected; CONTEXT.md "Macro excerpt char
  cap" documents the bound.

- **Q5: Does the accumulator's "blank line stops" rule fire before
  the first prose line?**
  A: No. Rule (iii) "blank line stops accumulation" fires ONLY AFTER
  `≥1` prose line is in the buffer. Blank lines before the first
  prose line are skipped, not terminating.
  Rationale: prevents `### subheading\n\n本文论述...` reports from
  short-circuiting to empty.
  Doc impact: spec AC #2 corrected; CONTEXT.md "Macro excerpt depth"
  documents the buffer-state precondition.

- **Q6: Helper location — new module `src/irc/research/excerpt.py`
  or private function in `gold_cmd.py`?**
  A: Private function in `gold_cmd.py`. Reject the speculative
  consolidation with `news_summaries._summary_for_theme`.
  Rationale: `news_summaries` scores against the WHOLE prose, not
  the first paragraph; sharing a helper would silently change the
  scoring rubric's input. YAGNI applies — only one consumer.
  Doc impact: spec AC #13 corrected; spec Q5 resolution flipped.

- **Q7: Is the renderer policy change ADR-worthy?**
  A: Yes — write ADR 0008.
  Rationale: three-of-three test passes — (a) hard to reverse
  (citation_id churn), (b) surprising without context (skip-rule +
  accumulator is non-obvious middle ground), (c) real trade-off
  (multi-paragraph rejected, prompt redesign deferred, depth-vs-
  budget calibrated). Captures the deferral of `F5-followup-
  prompt-eval` as the recorded "explicit no".
  Doc impact: new ADR `docs/adr/0008-macro-research-excerpt-depth.md`.

- **Q8: Does §3 `IRC_GOLD_EVIDENCE_*` block inherit the depth fix?**
  A: Yes — verified by reading `src/irc/memo/macro_pillar.py::
  render_gold_evidence_body`. The §3 block reads
  `ref.summary` from the same `ThemeReportRef` field §2 reads. Add
  an explicit sub-criterion to AC #6 so the §3 inheritance is
  enforced, not just side-noted.
  Rationale: makes the §3 paragraph-depth assertion regression-
  testable, not just an unverified comment.
  Doc impact: spec AC #6 extended.

- **Q9: Does the SKIPPED.md file already exist in the run dir?**
  A: Yes —
  `docs/2026-05-27-pickability-followups/SKIPPED.md` already
  exists. F5 APPENDS the `F5-followup-prompt-eval` entry, does not
  create the file.
  Rationale: verified by `ls` on the run dir.
  Doc impact: spec AC #15 corrected.

- **Q10: How does the accumulator handle bullet-list reports like
  `geopolitics`?**
  A: During accumulation, bullet-prefixed continuation lines
  (`- `, `* `, `+ `) ARE accepted into the buffer with the bullet
  marker stripped. Treats consecutive bullets as continuation
  paragraph lines.
  Rationale: matches the hybrid-rule rationale (bullet reports need
  accumulation to hit the 150-char floor).
  Doc impact: spec AC #1 / AC #2 corrected; CONTEXT.md "Macro
  excerpt depth" documents the bullet-stripping during accumulation.

- **Q11: Does memo §2/§3 `[ref:...]` integrity hold post-F5?**
  A: Yes — by construction. Both surfaces render markers from the
  same `evidence_by_source` map populated by the new (longer)
  `ThemeReportRef.summary`. Add AC #16 to enforce the cross-stage
  invariant against the publishable-set lockdown integration test.
  Rationale: makes the cross-stage citation universe assertion
  explicit rather than inherited from item 008.
  Doc impact: spec AC #16 added.

- **Q12: Are there CONTEXT.md glossary terms F5 should introduce?**
  A: Yes — add four terms under a new "Macro excerpt rendering"
  subsection: `Deterministic theme excerpt`,
  `Macro excerpt depth (skip-rule + paragraph accumulator)`,
  `Macro excerpt char cap`, `Theme-excerpt citation_id churn`.
  Rationale: pre-F5 the user-facing concept of "what we put after
  the theme name in §2" had no canonical name. Future reviewers of
  `_summary_from_theme_report` or `_first_prose_paragraph` should
  land on a glossary entry, not infer the contract from the helper.
  Doc impact: CONTEXT.md new subsection with 4 terms.
