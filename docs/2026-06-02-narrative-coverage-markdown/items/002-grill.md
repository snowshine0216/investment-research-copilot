Verdict: PASS

Subagent: opus
Questions resolved: 8 (RD-1 … RD-8; two carry sub-notes RD-6a / RD-7a)

## Docs touched

- `CONTEXT.md` — commit `f1deb2e`. Three new terms:
  - **Narrative passive fund-level autobuild** (sibling to the active autobuild; eligibility on resolved `LookthroughTarget.kind` + `provider_symbol`, instr-resolved, shared kill-switch + budget).
  - **Narrative passive path is theme-independent** (records WHY `theme_report=None` is by-design, not a bug — the `FundLevelSnapshot` branch never reads `theme_report`).
  - **NAV-derived quarter (latest-`nav/` probe)** (distinguishes the fund-level NAV-derived idempotence key from the active-fund provider-declared holdings quarter).
- `docs/2026-06-02-narrative-coverage-markdown/PROGRESS.md` — commit `f1deb2e` (grill cell → done; 002-spec ledger line).
- **No `docs/adr/` change** — the passive narrative path is a documented extension of ADR 0002 §5 (fund-level engine) + item 001's autobuild pattern. Fails the three-of-three ADR test (not hard-to-reverse: kill-switch; not surprising: mirrors item 001 + opportunity fund-level dispatch). ADR 0002 §5 itself already rejected a separate fund-level ADR.

## Spec refined

- `docs/2026-06-02-narrative-coverage-markdown/items/002-spec.md` — commit `f1deb2e`. Appended `## Resolved decisions` (RD-1…RD-8 Q/A/Rationale/Doc-impact); strikethrough corrections on Q1 prose (no `cn_etf` branch in `map_lookthrough`) and AC2 (`ShortlistRow` carries no `theme`/`tracked_index` → eligibility needs the instrument index). Original content preserved.

## theme_report=None decision

UNCHANGED. Confirmed correct against `thesis_evidence.py:348-373`: the `FundLevelSnapshot` branch of
`derive_thesis_from_evidence` reads only `snapshot.evidence` + `snapshot.evidence_gaps` and never
consults `theme_report`. `has_data AND has_info → "intact"`. `robots_report` recovery is gate-
independent of `theme_report`; genuine theme-report sourcing is a citation-richness follow-up, not a
gate requirement. WHY-it's-by-design now recorded in CONTEXT.md so a future reader won't file it as a bug.

## Resolved decisions

**RD-1 — `theme_report=None` correctness.**
A: Correct, UNCHANGED. FundLevelSnapshot branch is theme-independent (`thesis_evidence.py:348-373`).
Rationale: dual-coverage gate satisfied by NAV (data) + announcement (info) legs alone.
Doc-impact: CONTEXT.md "Narrative passive path is theme-independent".

**RD-2 — Passive eligibility set matches opportunity?**
A: Predicate correct, matches `opportunity_cmd.py:909-912`. Q1 prose overstated cn_etf coverage.
Rationale: no `cn_etf` branch in `map_lookthrough`; bare cn_etf → no-`provider_symbol` default → correctly excluded.
Doc-impact: spec Q1 strikethrough.

**RD-3 — Eligibility computable from `ShortlistRow`?**
A: No — corrected. Needs the instrument index; resolve via `map_lookthrough(_build_input(...))`.
Rationale: `ShortlistRow` lacks `theme`/`tracked_index`; `_build_input` reads them from `Instrument`.
Doc-impact: spec AC2 strikethrough; CONTEXT.md autobuild term.

**RD-4 — Latest-`nav/`-quarter probe vs analyze-context-quarter?**
A: Latest-`nav/` scan correct, UNCHANGED.
Rationale: fund-level `source_report_quarter` is NAV-derived (`infer_quarter`), unknowable pre-fetch; fixed-quarter probe → non-idempotent.
Doc-impact: CONTEXT.md "NAV-derived quarter (latest-`nav/` probe)".

**RD-5 — New ADR or new kill-switch?**
A: No new ADR; reuse `IRC_NARRATIVE_AUTOBUILD`.
Rationale: documented extension of ADR 0002 §5 + item 001; one narrative switch governs both edges.
Doc-impact: CONTEXT.md "Narrative passive fund-level autobuild".

**RD-6 — Dual-leg gate → real Policy-B-free `thesis_state`?**
A: Confirmed, UNCHANGED (`thesis_evidence.py:361-368`). Sub-note RD-6a: widen `build_opportunity_row`'s `snapshot` annotation to include `FundLevelSnapshot` (zero-risk typing fix; production already passes one).
Doc-impact: spec note only.

**RD-7 — Failure/budget parity with item 001?**
A: Confirmed, UNCHANGED (`FetchPlan.fund_level_misses` @ 4 calls, pre-fetch `FetchBudgetExceeded`). Sub-note RD-7a: prefer a single shared preflight `FetchPlan` over two independent budget checks.
Doc-impact: spec note only.

**RD-8 — Terminology drift?**
A: Reconciled — "nav snapshot" = `FundLevelSnapshot` under `nav/`; "dual-leg gate" = fund-level branch of the canonical Dual-coverage gate; "passive fund" = Passive ETF / tracked index.
Doc-impact: captured in the new CONTEXT.md narrative-passive terms.
