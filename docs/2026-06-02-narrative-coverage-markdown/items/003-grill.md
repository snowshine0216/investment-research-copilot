Verdict: PASS

Subagent: opus
Questions resolved: 6

Item 003 = markdown report enrichment (M1 evidence prose/citations + M2 product metrics) in
`src/irc/narrative/report.py`. Every load-bearing claim in the spec was verified against ADR 0001
(citation model), ADR 0004 (renderer determinism + SAME-3), and the real code. No unresolvable
spec↔ADR/code contradiction — hence PASS. One judgment call (whether to fix the scorer floor) is
correctly deferred to follow-up F-1; one citation error and one threading imprecision were corrected
inline (strike-through, originals preserved).

## Docs touched

- `CONTEXT.md` — two new terms in the "Narrative fund mining" section:
  - **Narrative report is a display-only, non-SAME-3 surface** (the load-bearing boundary).
  - **Active-fund `质量=weak` is a scorer floor, not a product judgment (today)** (the F-1 caveat).
  - (SHA: see commit below.)
- `docs/2026-06-02-narrative-coverage-markdown/items/003-spec.md` — refined in place:
  - Appended `## Resolved decisions` (RD-1..RD-6).
  - Strike-through `~~ADR 0011 §2~~` precedent citation in Q4 (corrected to ADR 0004 §Consequences).
  - Sharpened the Approach threading line (`_report_from_card` must receive `inp` for product metrics;
    `constituent_analyses` already flows via `card`/`row`).
  - Clarified AC4 (footnote pool draws from the flattened `r.thesis_evidence` superset).
  - (SHA: see commit below.)

No new ADR — an additive display-only renderer change fails the three-of-three rule (the SAME-3
boundary is already locked by ADR 0004; the narrative renderer is simply not a bound surface).

## Resolved decisions

### RD-1 — Is `narrative/report.py` bound by ADR 0004 §3 SAME-3 citation-set-equality? (HIGHEST RISK)
- **Q:** If the new evidence appendix exposes a fuller, non-capped citation pool, does it break the
  SAME-3 citation-set-equality invariant that binds the picks-table / evidence-pool / discipline
  surfaces?
- **A:** **NO — `narrative/report.py` is NOT a SAME-3 surface.** The appendix + footnote table are
  safe display-only additions.
- **Rationale:** ADR 0004 §3 (lines 84-92) binds exactly three producers — `_build_pick_rows`,
  `build_evidence_pool`, `_render_section` — all in the opportunity/memo pipeline. CONTEXT.md "SAME-3
  invariant" (line 78) names the same three consumers. `tests/memo/test_same_3_invariant.py` imports
  only those three (lines 13-17) and never imports `narrative.report` / `render_report_md`; no
  memo/opportunity/integration test references the narrative renderer. The narrative `.md` is a
  separate downstream artifact, so a fuller pool there cannot enter any equality check. Same pattern
  as the accepted `thesis_debate.md` exemption (ADR 0004 §Consequences).
- **Doc-impact:** CONTEXT.md term added; spec Q4 confirmed correct (only the precedent citation was
  wrong — `thesis_debate.md` exemption lives in ADR 0004 §Consequences, not "ADR 0011 §2").

### RD-2 — Does `classify_product_quality` structurally floor active funds to `weak`?
- **Q:** Is `质量=weak` a real product judgment, or a scorer artifact of missing metadata? Should item
  003 fix it?
- **A:** **Structural floor — confirmed.** Item 003 surfaces drivers only; the scorer fix is F-1.
- **Rationale:** `states.py:346-349` — for an active fund, when `manager_tenure_years` is present but
  `aum_stability_pct` is `None`, line 349 returns `("weak", …)`. `aum_stability_pct` is the documented
  universal drop (`completeness.py:22`) and is NEVER set by `populate_inputs` (`inputs_loader.py:159-164`
  sets only expense/aum/tenure/tracking_error). So every active fund with a known tenure is floored to
  `weak` regardless of real AUM/expense/track record. Fixing it is a scorer-behaviour change with H3
  ripple → its own slice. Silently re-classifying in the renderer is forbidden.
- **Doc-impact:** CONTEXT.md term added so a reader never treats active-fund `weak` as signal.

### RD-3 — Do footnote IDs stay exactly 16-hex and does every inline ref resolve?
- **Q:** Could the footnote table truncate/reformat the citation id, or emit an unresolvable ref?
- **A:** **No — integrity holds.**
- **Rationale:** `ThesisEvidence.citation_id` is computed to `hexdigest()[:16]` in `__post_init__`
  (`types.py:101`); the renderer reads `ev.citation_id` verbatim. Every marker matches
  `\[ref:[0-9a-f]{16}\]` (ADR 0001). Footnote pool = the fund's full `thesis_evidence` deduped by id,
  so every inline/appendix ref resolves.
- **Doc-impact:** none (ADR 0001 already binds 16-hex).

### RD-4 — Is the appendix + footnote sort deterministic (ADR 0004)?
- **Q:** Any dict-order / set-iteration / timestamp leak in the new sections?
- **A:** **No — deterministic.**
- **Rationale:** footnotes sorted by `citation_id` ascending (a stable 16-hex total order); appendix
  by the existing weight-desc flatten order. The dedup-by-id must use a `citation_id`-sorted
  collection, not raw set iteration. AC5 two-call byte-equality locks it; existing render tests stay
  green (the additions are append-only on the per-fund block).
- **Doc-impact:** none.

### RD-5 — Are the new schema fields safe, and is the threading sound?
- **Q:** Can the product metrics + `constituent_analyses` be added to `NarrativeFundReport` without
  breaking existing constructors / the `.json` round-trip, and where do they come from?
- **A:** **Yes, with one threading correction.**
- **Rationale:** `NarrativeFundReport` is a frozen dataclass; new fields get safe defaults
  (`() / None`), so error_report, `_report_from_card`, and the tests stay valid (AC8/AC9).
  `constituent_analyses` already flows via `card`/`row` (`types.py:170,198`; `cards.py:64`) — the
  appendix just needs the renderer to stop dropping it. The four product metrics are ONLY on
  `OpportunityInput` (`types.py:101-105`), NOT on `OpportunityRow`/`ThesisCard`, so `_report_from_card`
  must additionally receive `inp` (or a `ProductMetrics` bundle built from it at the `analyze_fund`
  edge, `analyze.py:137`). Spec Approach line sharpened inline.
- **Doc-impact:** spec Approach corrected.

### RD-6 — Does the footnote table resolve constituent-only refs?
- **Q:** Appendix refs come from `c.evidence`, not `r.thesis_evidence` — can a constituent-only id be
  unresolvable in the fund-level footnote table?
- **A:** **No — the pool is a superset.**
- **Rationale:** for active-fund rows the per-constituent evidence is flattened into
  `OpportunityRow.thesis_evidence` upstream (ADR 0002 / ADR 0004 "Related ADRs"), so the
  footnote-builder drawing from `r.thesis_evidence` already contains every appendix ref. AC4 clarified
  inline.
- **Doc-impact:** spec AC4 clarified.
