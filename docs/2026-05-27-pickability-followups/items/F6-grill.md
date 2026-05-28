Verdict: PASS

Subagent: opus
Questions resolved: 12
Docs touched:
  - CONTEXT.md (commit 5a832ba)
  - docs/adr/0001-citation-data-model.md (commit 5a832ba)
  - docs/adr/0003-failure-mode-policy-b.md (commit 5a832ba)
Spec refined: items/F6-spec.md (commit 5a832ba)

## Resolved decisions

- Q: Exact final wording of the new filing summary template?
  A: `f"{symbol} {fiscal_period} 财报已披露（口径未核实）"` — full-width
  parentheses （） per project Chinese-prose convention; quarter-period token
  leads so `## 持仓明细` appendix `summary[:24]` fragment renders a stable
  per-holding identifier (`"600519.SH 2026Q1 财报已"`).
  Rationale: shorter alternatives (e.g. `财报已披露`) collide with too many
  generic prose lines and weaken the appendix-trigger substring match; the
  parenthetical 口径未核实 is the user-visible epistemic disclaimer.
  Doc impact: AC #1 corrected; CONTEXT.md "Filing summary template";
  ADR 0001 §5 Addendum.

- Q: Caveat trigger replacement — structural flag on evidence vs. type-based
  lookup vs. substring on the new locked phrase?
  A: Substring match on the locked Chinese phrase `财报已披露（口径未核实）`
  in `memo/pipeline.py::_format_appendix_line`.
  Rationale: zero schema change to `ThesisEvidence` (avoids cache migration);
  appendix line-builder already only sees the rendered ref-line string, so
  plumbing the parsed-ref tuple through is out-of-scope churn; the Chinese
  phrase is non-ASCII and locked by both the producer summaries AND the
  synthesizer prompt clause.
  Doc impact: AC #6 corrected; CONTEXT.md "Filing summary template";
  ADR 0001 §5.2.

- Q: Does the new substring trigger remain robust against the synthesizer
  paraphrasing it?
  A: Yes — the synthesizer-prompt clause at `memo/synthesizer.py:55-56` is
  updated in lock-step to reference the new template phrase and continue
  forbidding any free-text `revenue_yoy=…` output.
  Rationale: `sanitize_unverified_revenue_yoy` stays as belt-and-braces; the
  producer always emits the locked phrase into `summary`, so the appendix
  ref line always carries it verbatim.
  Doc impact: AC #8 narrowed; ADR 0001 §5.1.

- Q: Should the legacy `_filing_evidence` summary line
  (`opportunity/thesis_evidence.py:98`) also be reframed?
  A: Yes — converge to the same locked phrase. The legacy line currently
  renders `营收同比 {revenue_yoy:+.1%}。` which is the same class of
  unverified-confidence claim, rendered as `+.1%` instead of `={raw}`.
  Rationale: single locus for the appendix trigger and the prompt clause to
  match against; the legacy path feeds passive ETF + tracked-index rows
  where the same epistemic posture applies.
  Doc impact: spec "smaller surface" paragraph extended with a grill-phase
  clarification noting the legacy path also needs reframing.

- Q: Citation-id one-time re-roll — same handling as F5 churn?
  A: Yes — mirror F5's precedent. But more precise than the spec's original
  claim: filing-typed evidence rows carry `FilingDigest.source_url` in the
  canonical case, so the URL dominates the preimage and the summary change
  does NOT churn the id for non-empty-URL filings. Only degraded-path
  filings with empty URL re-roll once.
  Rationale: ADR 0001 §2 preimage is `url or f"{source}:{date}:{summary[:64]}"`
  — URL takes precedence when present.
  Doc impact: ADR 0001 §5.3 acknowledgement (more precise than the original
  spec's "the citation_id WILL change").

- Q: ADR target — 0001 alone, or 0001 + 0003 cross-reference?
  A: ADR 0001 hosts the new addendum subsection; ADR 0003 §1 rule 3 gets a
  one-line pointer back.
  Rationale: ADR 0001 governs the citation data model (what a citation IS,
  including what its summary should and should not contain). ADR 0003
  governs the audit policy. The change is purely about the meaning + display
  of a filing citation; Policy B rule 3 still reads `citation_kind="data"`
  unchanged. Mirrors precedent (ADR 0005 cross-refs ADR 0003 H3; ADR 0008
  cross-refs ADR 0007 §3a).
  Doc impact: ADR 0001 §5 Addendum added; ADR 0003 §1 rule 3 pointer added.

- Q: Subsection title for the ADR 0001 amendment?
  A: `## Addendum — 2026-05-28: Filing evidence semantics` — same
  `Addendum — <date>: <topic>` pattern as the existing 2026-05-25
  footnote-numbering veneer addendum already in ADR 0001 (lines 92-98).
  Rationale: precedent-consistent; chronological scan of ADR addenda gives
  a quick history of the citation model's evolution.
  Doc impact: ADR 0001 §5 subsection title locked.

- Q: Should `derive_thesis_from_evidence` `_TYPE_RANK` change?
  A: No — `_TYPE_RANK = {"filing": 0, "broker": 1, "news": 2}` reflects
  display ordering and remains correct for the disclosure-existence form.
  Rationale: filings are still the most foundational evidence row per
  holding; broker commentary + news build on top of disclosure existence.
  Doc impact: none beyond spec's pre-existing Q5 resolution.

- Q: Does the `_yoy_split` direction-only invariant need a cross-provider
  sign-convention audit before F6 ships?
  A: No — defer to `F6-followup-yoy-sign-convention` SKIPPED entry. F6 is
  a display change; the legacy `_yoy_split` reading `revenue_yoy > 0`
  continues to feed `thesis_state`. Direction is robust to scale errors as
  long as sign conventions agree.
  Rationale: F6's Non-goals already exclude fundamentals-data rewrites; a
  per-provider sign audit is a separately-scoped follow-up.
  Doc impact: SKIPPED follow-up captured in the run's `SKIPPED.md` log.

- Q: Does the existing two-run byte-equality lockdown (item 008) break?
  A: No structural break — the lockdown asserts two-consecutive-runs
  byte-equality, not cross-deploy stability. Pre-F6 vs post-F6 diff is
  expected and one-time; same shape as F5's macro-theme citation_id churn.
  Rationale: lockdown contract is the two-run-same-input invariant. Baseline
  is re-recorded in the same PR.
  Doc impact: ADR 0001 §5.3 cross-references the F5 precedent.

- Q: CONTEXT.md glossary — which new entries to add?
  A: Four entries under a new "Filing evidence semantics" subsection:
  `Filing evidence semantics`, `Filing summary template`,
  `Constituent-scope data evidence (producer mapping)`,
  `F6 reframe-vs-drop-vs-normalize rationale`.
  Rationale: pre-F6 the disclosure-existence anchor concept had no canonical
  name; future reviewers should land on glossary entries, not infer the
  contract from helper internals.
  Doc impact: CONTEXT.md new subsection placed after "Thesis-news scoring"
  and before "Holdings ingest policy".

- Q: Is the spec's chosen position (Option C — reframe) ADR-worthy
  (three-of-three test)?
  A: Yes — write the ADR 0001 §5 Addendum.
  Rationale: (1) hard to reverse — producer templates land in three files
  plus the appendix trigger plus citation_id re-roll; (2) surprising without
  context — a future reader will ask "why is unverified filing scalar
  accepted as the data leg?"; (3) real trade-off — drop / normalize /
  reframe are genuinely distinct alternatives with structurally different
  downstream consequences.
  Doc impact: ADR-0001 §5 Addendum authored.
