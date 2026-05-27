Verdict: PASS

Subagent: opus
Questions resolved: 12
Docs touched:
  - CONTEXT.md (commit d9f2571)
  - docs/adr/0008-macro-research-excerpt-depth.md (commit d9f2571)
Spec refined: items/F5-spec.md (commit d9f2571)

## Resolved decisions

- Q: Does the `##`-prefix skip rule actually catch the offending `###` subheadings?
  A: Yes — `extract_prose_from_report_md` already strips single-`#` lines; `stripped.startswith("##")` correctly catches `##` through `####+`. AC #1 wording stays.
  Rationale: verified against `src/irc/research/persistence.py` `_FOOTER_HEADING_RE` + `# vs ##` branch.
  Doc impact: none

- Q: What exactly counts as "entirely wrapped in `**...**`"?
  A: Tighten to `re.fullmatch(r"\*\*[^*]+\*\*", stripped)` / `re.fullmatch(r"__[^_]+__", stripped)` so lines like `**政策优化信号**：…` (bold + trailing prose) DO NOT skip, while `**1. Bond Market Pressure...**` (pure bold) DOES skip.
  Rationale: original "entirely wrapped" wording was ambiguous; regex makes it precise.
  Doc impact: spec AC #1 corrected; CONTEXT.md "Macro excerpt depth"

- Q: Should `_first_prose_paragraph` strip inline `[N]` citation markers from the excerpt?
  A: No — leave them in (matches today's behaviour for 3 themes that read well).
  Rationale: stripping changes summary content → citation_id → expands churn surface; semantic gain nil.
  Doc impact: ADR 0008 §1 "Trade-offs considered"

- Q: Does `max_chars=400` fit the AC #3 "~15 visible lines" claim?
  A: No — worst-case ~25 lines, typical 10–15. Correct AC #3 to be honest.
  Rationale: 7 × 400 / ~50 ≈ 56-line theoretical worst; 150-char floor fires far more often than 400 ceiling, so typical is much lower.
  Doc impact: spec AC #3 corrected; CONTEXT.md "Macro excerpt char cap"

- Q: Does the accumulator's "blank line stops" rule fire before the first prose line?
  A: No — rule (iii) fires ONLY AFTER `≥1` prose line is in the buffer. Blank lines before first prose are skipped, not terminating.
  Rationale: prevents reports starting `### subheading\n\n本文论述...` from short-circuiting to empty.
  Doc impact: spec AC #2 corrected; CONTEXT.md "Macro excerpt depth"

- Q: Helper location — new module `src/irc/research/excerpt.py` or private in `gold_cmd.py`?
  A: Private function in `gold_cmd.py`. Reject consolidation with `news_summaries._summary_for_theme`.
  Rationale: `news_summaries` scores against WHOLE prose; sharing would silently change scoring rubric input. YAGNI — only one consumer.
  Doc impact: spec AC #13 corrected; spec Q5 resolution flipped

- Q: Is the renderer policy change ADR-worthy (three-of-three test)?
  A: Yes — write ADR 0008.
  Rationale: hard to reverse (citation_id churn), surprising without context (skip+accumulator hybrid), real trade-off (multi-paragraph + LLM-redesign both explicitly rejected).
  Doc impact: ADR-0008 created

- Q: Does §3 `IRC_GOLD_EVIDENCE_*` block inherit the depth fix?
  A: Yes — `macro_pillar.render_gold_evidence_body` reads same `ThemeReportRef.summary` field. Add explicit sub-criterion to AC #6.
  Rationale: makes §3 inheritance regression-testable, not just unverified side-comment.
  Doc impact: spec AC #6 extended

- Q: Does `docs/2026-05-27-pickability-followups/SKIPPED.md` already exist in the run dir?
  A: Yes — F5 APPENDS the `F5-followup-prompt-eval` entry, does not create the file.
  Rationale: verified by `ls` on the run dir.
  Doc impact: spec AC #15 corrected

- Q: How does the accumulator handle bullet-list reports (e.g. `geopolitics`)?
  A: During accumulation, bullet-prefixed continuation lines (`- `, `* `, `+ `) ARE accepted with marker stripped. Consecutive bullets treated as continuation paragraph lines.
  Rationale: matches hybrid-rule rationale — bullet reports need accumulation to hit 150-char floor.
  Doc impact: spec AC #1/AC #2 clarified; CONTEXT.md "Macro excerpt depth"

- Q: Does memo §2/§3 `[ref:...]` integrity hold post-F5?
  A: Yes by construction — both surfaces render markers from same `evidence_by_source` map populated by new `ThemeReportRef.summary`. Add AC #16 to enforce against item 008 lockdown.
  Rationale: makes cross-stage citation universe assertion explicit rather than inherited.
  Doc impact: spec AC #16 added

- Q: Are there CONTEXT.md glossary terms F5 should introduce?
  A: Yes — add 4 terms under new "Macro excerpt rendering" subsection.
  Rationale: pre-F5 the user-facing concept had no canonical name; future reviewers should land on glossary entries, not infer contract from helper internals.
  Doc impact: CONTEXT.md new subsection (`Deterministic theme excerpt`, `Macro excerpt depth (skip-rule + paragraph accumulator)`, `Macro excerpt char cap`, `Theme-excerpt citation_id churn`)
