# ADR 0008 — Macro research excerpt depth (renderer policy)

**Status:** Accepted (2026-05-27, pickability-followups item F5).
**Supersedes:** none. Builds on [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0004 — renderer determinism + alias policy](0004-renderer-determinism-and-alias-policy.md), [ADR 0007 — thesis-news scoring](0007-thesis-news-scoring.md) §3a (prose-extraction invariant).
**Spec:** `docs/2026-05-27-pickability-followups/items/F5-spec.md`.

## Context

Post-F4, the `extract_prose_from_report_md` helper correctly strips the `# <theme>` heading and the `## Citations` footer from persisted theme reports before any downstream consumer reads the prose. But `gold_cmd._summary_from_theme_report` then picked the FIRST non-empty stripped line — which, for 4 of 7 themes on the 2026-05-27 snapshot, is a `### subheading` or `**bold-only subheading**` rather than a real sentence. Memo §2 `本周宏观研究要点` rendered subheading labels instead of substantive prose for `cn_monetary`, `geopolitics`, `us_fiscal_politics`, and `cn_equity_property_policy`.

Three decisions are non-obvious, expensive to reverse, and the product of real trade-offs:

1. **Extractor improvement, not LLM prompt redesign.** The alternative was a `memo_synthesis` prompt rewrite + 5-week historical eval bench. The eval-corpus prerequisite (5 weekly snapshots of `data/research/`) does not exist; building it would be its own project. Post-F4 inspection shows the LLM already produces multi-paragraph prose with proper sentences — the extractor is the dominant failure mode for 4/7 themes.
2. **Skip-rule + paragraph accumulator, NOT "render everything between heading and citations footer".** The alternative would balloon §2 from ~7 lines to ~70 lines and bury §5's picks-table dashboard.
3. **`max_chars=400` (raised from 220).** Paragraph-shaped excerpts need more room than line-fragment excerpts. 400 is the empirical sweet spot — ≥150-char floor (per AC #2) prevents fragmentary excerpts; 400 ceiling caps worst-case §2 length at ~25 visible lines.

This ADR locks all three. A reviewer reading `gold_cmd._summary_from_theme_report` or `gold_cmd._first_prose_paragraph` six months from now should land here first.

## Decision

### 1. Skip-rule + paragraph-accumulator extractor

`_summary_from_theme_report(report, *, max_chars=400)` in `src/irc/commands/gold_cmd.py` delegates the paragraph extraction to a private helper `_first_prose_paragraph(prose: str, *, max_chars: int) -> str`, co-located in the same file (NOT a new module — only one consumer; YAGNI; the spec's alternative `src/irc/research/excerpt.py` was rejected because `news_summaries._summary_for_theme` has a different consumer contract — it scores against the WHOLE prose, not the first paragraph).

The helper algorithm is fully specified in CONTEXT.md "Macro excerpt depth (skip-rule + paragraph accumulator)". Summary:

**Skip rule** — drop any line whose stripped form matches (a) `startswith("##")`, OR (b) `re.fullmatch(r"\*\*[^*]+\*\*", s)` / `re.fullmatch(r"__[^_]+__", s)` (bold-only line with NO trailing prose), OR (c) is empty before any prose line has entered the buffer.

**Accumulator rule** — locate the first non-skip prose line, strip a leading bullet marker (`- `, `* `, `+ `), then continue collecting subsequent non-skip lines until ONE of: (i) `≥3` sentence-ending punctuation marks `{".", "。", "！", "!", "?", "？"}` are present, (ii) the buffer reaches `≥150` visible chars, (iii) a blank line is encountered AFTER `≥1` prose line is in the buffer. Lines joined with a single ASCII space.

The hybrid stop-rule guarantees ≥150 chars of substance for both paragraph-shaped reports (e.g. `us_monetary`) and bullet-list-shaped reports (e.g. `geopolitics`).

**Trade-offs considered:**

- *Alternative — naive "first 3 lines".* Rejected: would produce `### Section Heading\n\n**1. First subsection title**\n...` for the offending 4 themes. Reads worse than today.
- *Alternative — blank-line-only paragraph boundary.* Rejected: bullet-list reports have each bullet as its own "paragraph" by blank-line definition. A single 80-char bullet would fall below the substance floor.
- *Alternative — leave inline `[N]` citation markers in the excerpt verbatim.* Initially preferred (3 themes that already read well today carry inline `[N]` markers; stripping changes their summary content → changes their citation_id → expands the F5 churn surface). **REVERSED post-impl** after the /ship step 8 silent-failure hunter (PR #81, fix commit `997e418`) found that surviving `[N]` markers collide visually with the memo's downstream footnote numerals after `render_footnotes` — a reader cannot distinguish an LLM-internal source index from a genuine footnote reference. The strip is implemented via `_LLM_REF_MARKER_RE = re.compile(r"\s*\[\d+\]\s*")` in `gold_cmd.py` and applied to every accepted prose line before accumulation. Covers `[0]` through arbitrary-digit citations (synth output occasionally exceeds 99 entries). Trade-off accepted: the affected citation_ids did churn during the F5 PR, but the alternative (silent confusion in §2/§3 rendering) was worse.

### 2. `max_chars=400` (raised from 220)

The hard char cap is `400`. When the accumulated paragraph exceeds the cap, truncate to `max_chars - 1` and append the single horizontal-ellipsis char `…`. The kwarg-only `max_chars` override is preserved so tests pin behaviour at smaller caps.

Worst-case §2 section length: 7 themes × 400 chars / ~50 chars-per-line ≈ ~25 visible lines. Empirically the 150-char floor fires far more often than the 400-char ceiling, so typical §2 is ~10–15 lines. §2 remains a single-screen dashboard.

**Trade-offs considered:**

- *Alternative — keep 220.* Rejected: paragraph-shaped excerpts need more room. A 220-char cap forces truncation on most multi-sentence excerpts after the first sentence, defeating the depth fix.
- *Alternative — raise to 600 or remove cap entirely.* Rejected: worst-case §2 length would push past one screen; §5's picks-table is the dashboard intent.

### 3. Citation_id churn is expected and documented

Because `ThesisEvidence.citation_id` is content-derived (ADR 0001 §2: `canonical_url_or_fallback = url or f"{source}:{date}:{summary[:64]}"`) and theme-report evidence has empty `url`, changing the extracted summary CHANGES the row's citation_id.

This is acceptable and expected:

- ADR 0001 §2 explicitly states no cross-run id stability contract — content hash means same-content/same-id, different-content/different-id.
- The two-run byte-equality contract (same `data/research/` snapshot → byte-identical `gold_regime.json` → identical ids) is preserved by F5 and locked by a regression test.
- Memo §2/§3 `[ref:...]` markers continue to match `gold_regime.json["evidence"]` ids by construction (the same `evidence_by_source` map renders the markers).
- The publishable-set lockdown integration test (item 008 AC19) reads from `gold_regime.json` for the universe and stays green.

Operators reviewing diff-of-runs across the F5 deploy date see macro-theme citation_ids change once and then stabilise. This ADR documents the expected churn to forestall surprise.

### 4. Deferred follow-up — `F5-followup-prompt-eval`

The LLM `memo_synthesis` prompt redesign + 5-week historical eval bench called for in `docs/2026-05-27-instrument-pickability/SKIPPED.md` F5 is DEFERRED. The prerequisite (5 weekly snapshots of `data/research/`, a quality rubric, an eval harness) does not exist. The SKIPPED entry `F5-followup-prompt-eval` lands in `docs/2026-05-27-pickability-followups/SKIPPED.md` (file already exists in this run dir; F5 appends to it) and captures:

- the LLM-prompt-redesign scope,
- the eval-corpus prerequisite,
- the success rubric (≥4/5 weeks improved, where "improved" is the AC #6 paragraph-depth metric),
- back-pointer to this ADR.

## Non-goals (locked)

- **No `memo_synthesis` prompt changes.** F5 is a pure-Python extractor change. `src/irc/templates/config/llm.yaml` is untouched.
- **No new citation rows / no new evidence sources.** Macro evidence row count is identical pre/post F5; only the `.summary` field content changes.
- **No multi-paragraph rendering.** §2 dashboard intent preserved.
- **No `news_summaries._summary_for_theme` consolidation.** The scoring rubric consumes the WHOLE prose; sharing a paragraph extractor would silently change the rubric's input. Rejected.

## Consequences

**Positive:**

- Memo §2 finally renders substantive paragraph-shaped excerpts for all 7 themes; the heading-fragment symptom is gone.
- §3 `IRC_GOLD_EVIDENCE_*` block inherits the depth fix incidentally (same `ThemeReportRef.summary` field).
- Deterministic — same `data/research/` snapshot → byte-identical `gold_regime.json`. Locked by regression test.
- Reversible at the policy level — `max_chars` is a kwarg, the skip-rule predicates are pure functions, the rollback is one revert.

**Negative (acknowledged):**

- Macro-theme citation_ids churn once on the F5 deploy run. ADR 0001 contract not violated; documented in §3 above.
- §2 section length is bounded but not tight — worst-case ~25 visible lines (typical ~10–15). Acceptable; below the §5 picks-table fold.
- The skip-rule is a heuristic. A future LLM that produces report bodies starting with an unrecognised heading shape (e.g. `>>> Section` or numbered lists `1. Section`) would silently fall through. Mitigated by AC #6 regression test that asserts ≥6 of 7 themes hit the paragraph-depth metric on the current corpus.

## Related ADRs

- [ADR 0001 — citation data model](0001-citation-data-model.md): citation_id is content-derived; churn expected and contract-compliant.
- [ADR 0004 — renderer determinism + alias policy](0004-renderer-determinism-and-alias-policy.md): SAME-3 / H3 invariants untouched (macro-scope evidence is excluded from SAME-3 by construction).
- [ADR 0007 — thesis-news scoring](0007-thesis-news-scoring.md) §3a: prose-extraction invariant — F5 builds on top of `extract_prose_from_report_md`, never bypasses it.
- `docs/2026-05-27-pickability-followups/items/F5-spec.md`: the implementation spec this ADR governs.
- CONTEXT.md "Macro excerpt rendering" — the four glossary terms (`Deterministic theme excerpt`, `Macro excerpt depth (skip-rule + paragraph accumulator)`, `Macro excerpt char cap`, `Theme-excerpt citation_id churn`).
