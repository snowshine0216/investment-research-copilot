# Item 003 — Markdown report enrichment (M1 evidence prose/citations + M2 product metrics)

**Run:** `narrative-coverage-markdown` · **Handoff steps:** #3 (M1), #4 (M2)
**Primary file:** `src/irc/narrative/report.py` (renderer)
**Supporting edits:** `src/irc/narrative/schemas.py` (`NarrativeFundReport` carries the data the
renderer needs), `src/irc/narrative/analyze.py` (`_report_from_card` threads it through)
**Pattern to mirror:** `src/irc/opportunity/report.py:289` `_format_appendix_constituent_line` (the
`## 持仓明细` per-constituent `one_line_view` + refs + failure-shape appendix) and
`opportunity/report.py:196` `_render_thesis_evidence_bullets` (the locked
`- [ref:{citation_id}] {type} · {source} · {date}` inline bullet shape).
**Read-only references:** `src/irc/fundamentals/types.py` (`ThesisEvidence.summary`,
`ConstituentAnalysis.one_line_view`), `src/irc/opportunity/states.py:342` `classify_product_quality`,
`src/irc/opportunity/inputs_loader.py:23` (product-metric source columns), ADR 0001, ADR 0004.

## Goal

The narrative `.md` reports under-render their own evidence (M1) and label every fund `质量=weak`
with no supporting numbers (M2). After items 001+002, passive and active narrative funds deepen and
carry real `thesis_evidence` (the good metals funds carry 46–59 records each) — but the `.md`
projection still emits, per fund, only state labels + a one-line templated `说明` + up to 3 **opaque**
`[ref:hex]` IDs with no source text. The reader can read the *verdict* but not *why the fund earned
it*, and cannot resolve any citation. This item makes the narrative `.md` self-explaining without
touching any scorer, gate, or invariant.

**M1 — render evidence prose + resolvable citation footnotes.** Two changes to the per-fund block in
`render_report_md`:

1. **Inline evidence cell stays capped at 3** (`select_citations(thesis_evidence, cap=3)`), but each
   bullet gains the `ThesisEvidence.summary` source text — i.e. the locked
   `- [ref:{citation_id}] {type} · {source} · {date}` line gains a trailing ` · {summary}` segment
   so the inline cell carries human-readable prose, not just an opaque id triple.
2. **A per-fund evidence appendix** (`### 证据明细 / Evidence appendix`) exposes the **deeper pool**
   that today lives only in the `.json`:
   - For **active-fund** rows (rows carrying `constituent_analyses`), render the per-constituent
     `one_line_view` + that constituent's `select_citations(c.evidence, cap=3)` refs, reusing the
     line shape of `opportunity/report.py::_format_appendix_constituent_line` (a self-contained copy,
     NOT an import — see Approach below). This surfaces the per-constituent narrative prose.
   - A **footnote table** resolving every citation that appears anywhere in this fund's block:
     `[ref:{citation_id}] {type} · {source} · {date} · {summary}` (and `· {url}` when `url` is
     non-empty), one line per distinct `citation_id`, drawn from the fund's **full**
     `thesis_evidence` pool. This is what makes each inline `[ref:hex]` resolvable.

**M2 — surface product-quality drivers next to `质量=weak`.** Add a drivers segment to the sub-state
line (or an adjacent line) showing the underlying product metrics —
`expense_ratio`, `aum_cny`, `manager_tenure_years` (and `tracking_error` for passive vehicles) —
formatted with `—` for any metric that is `None`. This lets the reader distinguish a genuinely weak
product (small AUM, high fee, short record) from a fund **floored to `weak` on missing metadata**.
The metric values must be threaded onto `NarrativeFundReport` (it does not carry them today). The
scorer-flooring root cause is documented in **Resolved decisions RD-2** and **flagged as a follow-up
(F-1)** — item 003 changes only the rendering, never `classify_product_quality`.

## Approach (recommended)

**A — thread the data onto `NarrativeFundReport`; render in a self-contained narrative renderer.**

`NarrativeFundReport` today carries `thesis_evidence` but NOT `constituent_analyses` and NOT the raw
product metrics — `_report_from_card` (`analyze.py:86-96`) drops `card.constituent_analyses`, and no
product numbers ever reach the report. This item adds the missing fields (frozen-dataclass, defaulted
so existing constructors stay valid) and threads them at the `_report_from_card` edge. The renderer
gains the inline-summary segment, the appendix, and the footnote table as small pure helpers, each
mirroring (not importing) the opportunity-report shape.

Rejected alternatives:
- **B — render the appendix from `thesis_evidence` only, skip `constituent_analyses`.** Loses the
  per-constituent `one_line_view` prose the handoff explicitly asks for ("`one_line_view` per
  constituent"). Rejected.
- **C — import `_format_appendix_constituent_line` / `_render_thesis_evidence_bullets` from
  `opportunity/report.py`.** Couples the narrative renderer to the opportunity discipline-report
  internals — including functions that participate in the SAME-3-bound surfaces (ADR 0004 §3). A
  future change to those for the opportunity report would silently alter the narrative `.md`.
  Rejected: keep the narrative renderer self-contained; mirror the line shape, do not import it.

## Acceptance criteria

Each criterion is independently verifiable by a unit test in `tests/narrative/test_report.py`
(mirroring the existing renderer-test style) unless noted.

1. **Inline cell keeps the 3-citation cap with prose.** `render_report_md` still emits at most 3
   inline `[ref:hex]` bullets per fund via `select_citations(thesis_evidence, cap=3)` (unchanged
   selector, unchanged cap), and each bullet now ends with ` · {summary}`. Verified: a fund with > 3
   `thesis_evidence` records emits exactly 3 inline bullets, each containing its record's `summary`
   text.
2. **Inline ref format is still 16-hex and matches the locked regex.** Every inline `[ref:...]`
   marker matches `\[ref:[0-9a-f]{16}\]` (ADR 0001). The existing
   `test_report_md_emits_ref_from_thesis_evidence` assertion on the `- [ref:{id}] {type} · {source} ·
   {date}` prefix still holds (the summary is appended, not substituted).
3. **Active-fund evidence appendix renders per-constituent prose.** For a report carrying
   `constituent_analyses`, the `.md` contains a `### 证据明细` (or equivalently-named) appendix with
   one bullet per constituent showing `{symbol} {name_cn} (权重 {weight_pct}%): {one_line_view}` +
   that constituent's capped refs, mirroring `_format_appendix_constituent_line`'s evidence-only and
   evidence+failures shapes. A constituent with no evidence renders its `failure_reasons` /
   `audit_errors` (never a fabricated `one_line_view`).
4. **Citation footnotes resolve every inline `[ref:hex]`.** For any fund, every `citation_id`
   appearing in an inline bullet (and in an appendix constituent bullet) appears exactly once in the
   fund's footnote table as `[ref:{citation_id}] {type} · {source} · {date} · {summary}` (plus
   ` · {url}` when non-empty). Verified: extract all `[ref:hex]` ids from a fund's block via the
   locked regex; assert each id has a matching footnote line. (This is the "every inline `[ref:hex]`
   resolves" criterion.)
5. **Footnotes are deterministic.** The footnote table is sorted by a stable key (`citation_id`
   ascending) so two `render_report_md` calls on the same reports produce byte-identical output.
   Verified by a two-call byte-equality assertion (ADR 0004 determinism).
6. **M2 product-metric drivers are surfaced.** For every fund, the `.md` shows the product-quality
   drivers `expense_ratio`, `aum_cny`, `manager_tenure_years` (and `tracking_error` for passive)
   adjacent to `质量={product_quality_state}`. A `None` metric renders as `—` (not `None`, not
   `0`). Verified: a fund with `aum_cny=None` shows `aum=—`; a fund with `aum_cny=5.0e8` shows the
   formatted value.
7. **M2 distinguishes genuine-weak from metadata-floored.** When `product_quality_state == "weak"`
   AND all surfaced metrics that gate the scorer are `None`/unprovidable (the metadata-thin case),
   the line is visibly distinguishable from a weak verdict backed by real numbers — at minimum by the
   `—` placeholders rendered in AC6. (The renderer does not re-classify; it only displays the inputs.
   The scorer-flooring fix itself is follow-up F-1, NOT this item.)
8. **`NarrativeFundReport` carries the new fields without breaking JSON.** `render_report_json` still
   round-trips all existing fields; new fields (product metrics, `constituent_analyses` if added to
   the report) serialize deterministically. The `.json` remains the **full source of truth** — the
   `.md` adds no datum the `.json` lacks.
9. **Existing renderer tests still pass.** The current `tests/narrative/test_report.py` suite
   (`test_report_md_emits_ref_from_thesis_evidence`, `test_report_md_renders_risk_and_action_fields`,
   `test_report_md_no_evidence_has_no_ref`, `test_report_json_round_trips_states_and_evidence`,
   shortlist/diagnostics tests) passes unchanged in behaviour. A fund with empty `thesis_evidence`
   still emits no `[ref:...]` and no footnote table.
10. **SAME-3 and the opportunity/memo determinism suites still pass.** Item 003 touches only
    `src/irc/narrative/*` — it adds no `ThesisEvidence`, changes no `citation_id` preimage, and does
    not modify `select_citations`, `opportunity/report.py`, `memo/evidence_pool.py`, or any
    SAME-3-bound surface. The picks-table / evidence-pool / discipline citation-set-equality suite
    (`tests/memo/test_evidence_pool.py` and friends) is unaffected. Verified by a targeted run of the
    SAME-3 / opportunity-renderer tests showing green.
11. **No scorer / state change.** `git diff` touches no file under `src/irc/opportunity/states.py`,
    `thesis_evidence.py`, `risk.py`, or any classifier. Verified by inspecting the changed-files set.

## Non-goals

- **Item 004's gapped-row action-triad suppression.** Suppressing the `机会/dca/风险` triad +
  falsification/trim triggers on `position_risk_level == "insufficient"` rows (and rendering an
  "insufficient — refresh evidence" line) is **item 004**, NOT this item (MASTER-SPEC row 004;
  handoff PART 2 "Related (lower priority)"). Item 003 leaves the triad rendering exactly as-is;
  it only enriches the evidence/citation/product-metric surface.
- **Coverage-gap code (items 001/002).** Active-fund autobuild, passive fund-level wiring, the
  `analyze_fund` snapshot loaders, and the misleading error string are 001/002. Item 003 assumes the
  reports already carry deepened evidence and only changes how that evidence is *rendered*.
- **Changing the product-quality scorer.** The `aum_stability_pct`-floor-to-`weak` behaviour
  (RD-2 / F-1) is a real issue but is **out of scope** — item 003 surfaces the drivers so the floor
  is *visible*, it does not fix the floor. Silently re-classifying in the renderer is forbidden.
- **New LLM prose / re-synthesis.** "Narrative prose" here means rendering existing deterministic
  fields (`summary`, `one_line_view`), not generating new text via an LLM. No new LLM task.
- **Theme-report enrichment.** Sourcing real `theme_report` citations for the narrative path is the
  flagged 002 follow-up; not in 003.

## Constraints

- **Renderer determinism (ADR 0004).** Every new rendered section MUST be deterministic — no
  dict-iteration-order leaks, no timestamps, no `set` iteration without a sort. Footnote ordering and
  appendix ordering use explicit stable keys (`citation_id` asc for footnotes; existing
  weight-desc flatten order for constituents). Two `render_report_md` calls on identical input are
  byte-identical (AC5).
- **SAME-3 display invariant (ADR 0004 §3).** SAME-3 binds **three opportunity/memo surfaces**
  (picks-table, evidence-pool, discipline nested bullets) — the **narrative report is NOT one of
  them**. The inline cell keeps `select_citations(cap=3)`; the appendix/footnotes are **display-only
  for a non-SAME-3 surface** and do not enter any citation-set-equality check. Item 003 adds NO new
  consumer of `select_citations` to the three bound surfaces. (Flagged for the grill: confirm the
  appendix cannot leak into the picks/evidence-pool/discipline equality — it cannot, because it lives
  in `narrative/report.py`, a separate artifact never read by the memo/opportunity citation-set
  assertions.)
- **Citation ID format (ADR 0001).** 16 hex chars; every emitted marker matches
  `\[ref:[0-9a-f]{16}\]`. The renderer never recomputes or mints ids — it reads `ev.citation_id`.
- **TDD.** Red → green → refactor; each AC gets a failing test first. Test file
  `tests/narrative/test_report.py` mirrors `src/irc/narrative/report.py`.
- **`.json` remains the full source of truth.** The `.md` is a richer projection but adds no datum
  absent from the `.json`; `render_report_json` is the canonical dump.
- **Size budget.** `report.py` stays < 200 lines (extract small pure helpers); each new helper
  function < 20 lines. Effects at edges — the renderer is pure (string in/out); the field threading
  happens in `analyze.py`'s `_report_from_card` edge.
- **Immutability.** New `NarrativeFundReport` fields are frozen-dataclass fields with defaults
  (`()` / `None`); construction uses keyword args, never mutation.

## Open questions — resolved

**Q1 — M1 prose form: which fields actually exist to render, and what goes inline vs appendix?**
A: Two real fields. (a) `ThesisEvidence.summary` (`fundamentals/types.py:69`) is the per-citation
human-readable text (filing: "宁德时代 2026Q1 财报已披露（口径未核实）"; broker: "{broker} {rating}:
{title}"; news: the headline) — render it in the **inline** cell as a ` · {summary}` suffix and in
the **footnote** table. (b) `ConstituentAnalysis.one_line_view` (`fundamentals/types.py:145`) is the
per-constituent prose, present only on **active-fund** snapshots — render it in the **appendix**.
Inline cell = capped 3 (the SAME-3-style display cap, kept); appendix = the fuller per-constituent
prose + the full-pool footnotes.
Rationale: these are the only deterministic prose fields available; both are already rendered by the
opportunity discipline report, so the shape is proven. No new field invention, no LLM.

**Q2 — Where is the citation source text, and how does a `[ref:hex]` footnote resolve?**
A: On the `ThesisEvidence` record itself: `summary` (+ `source`, `date`, `type`, `url`). The footnote
table is built from the fund's full `thesis_evidence` tuple (the same objects the inline cell selects
3 from), deduplicated by `citation_id`. Because every inline/appendix `[ref:hex]` is the
`citation_id` of a record in that pool, every marker resolves (AC4). No external lookup, no I/O.
Rationale: `thesis_evidence` already carries the resolvable text; the renderer just stops dropping it
(`_evidence_dict` currently omits `summary`; the inline bullet omits it too).

**Q3 — Footnote / appendix format — must be deterministic per ADR 0004.**
A: Footnote table sorted by `citation_id` ascending (stable, content-addressed, collision-free at 16
hex). Constituent appendix bullets ordered by the existing weight-desc flatten order
(`_flatten_analyses` semantics: weight_pct desc, type_rank asc, citation_id asc) — already
deterministic. No `dict`/`set` iteration without an explicit sort.
Rationale: `citation_id` is a stable total order; reusing the established flatten order avoids a
second ordering policy. Locked by the AC5 two-call byte-equality test.

**Q4 — SAME-3 coexistence: does the appendix violate the picks/evidence-pool/discipline citation-set
equality?**
A: **No.** ADR 0004 §3 binds exactly three surfaces, all in the **opportunity/memo** pipeline
(`_build_pick_rows`, `build_evidence_pool`, `_render_section`). The narrative report
(`narrative/report.py`) is a **separate downstream artifact** that is never read by the SAME-3
regression test (`tests/memo/test_evidence_pool.py`), so exposing the deeper pool there cannot enter
the equality check. The narrative inline cell still calls `select_citations(cap=3)` so it stays
consistent with its own JSON-side selection. **Flagged for the grill** to confirm no test treats the
narrative `.md` as a SAME-3 surface (it does not).
Rationale: SAME-3 is a *consumer-side* contract over three named producers; adding a fourth,
display-only, unbound surface is exactly the "extra additive file outside the SAME-3 set" pattern
already accepted for `thesis_debate.md` (ADR 0011 §2).

**Q5 — M2: which exact product metrics, and what are their source fields?**
A: Surface `expense_ratio`, `aum_cny`, `manager_tenure_years` for all funds, plus `tracking_error`
for passive vehicles. Sources (read-only context): `expense_ratio`, `aum` (→ `aum_cny`),
`manager_tenure_years` come from the DuckDB `instruments` table (`inputs_loader.py:23,30-32`);
`tracking_error` from `fund_metrics` (`inputs_loader.py:36-44`). They flow into `OpportunityInput`
but are NOT on `OpportunityRow` / `ThesisCard` / `NarrativeFundReport` today — so this item threads a
small, pre-formatted **driver bundle** (a tuple of `(label, value-or-None)` or a frozen
`ProductMetrics` value object) from the input onto the report at the `analyze.py` edge.
Rationale: these four are exactly the metrics `_passive_quality_score` and the active branch of
`classify_product_quality` consume, so they are the honest drivers behind the `weak` label.

**Q6 — Does `classify_product_quality` floor to `weak` on missing metadata? Cite the code.**
A: **Yes, for active funds — confirmed.** `classify_product_quality` (`states.py:342-359`): when
`_is_active_fund(inp)` is true, line 346 checks `manager_tenure_years is None OR aum_stability_pct is
None`; if **both** are None → `evidence_insufficient` (line 348), but if **tenure is present and
`aum_stability_pct` is None** → returns `("weak", "主动基金证据不足，未达可推荐水平")` (line 349).
Critically, **`aum_stability_pct` is NEVER populated** anywhere in `populate_inputs` — it is the
documented "universal drop" (`decision/completeness.py:22`: "we do not yet ingest a multi-period AUM
history"; `inputs_loader.py` never sets it). So **every active fund with a known manager tenure is
structurally floored to `weak`**, regardless of its real AUM / expense / track record. This is M2's
"scorer floored to weak on thin metadata" — and it is bigger than rendering. The `.md` signals it by
showing the drivers (AC6/AC7); the scorer fix is **follow-up F-1**, NOT item 003.
Rationale: grounded in the exact code; resolving it inside item 003 would silently change scorer
behaviour, which the task and ADR discipline forbid.

**Q7 — Does threading product metrics + `constituent_analyses` onto `NarrativeFundReport` touch any
gate / invariant?**
A: No. Both are plain display fields (numbers and already-built `ConstituentAnalysis` objects). They
emit no `ThesisEvidence`, no `citation_id`, no `evidence_gaps`; they do not feed
`derive_thesis_from_evidence`, Policy B, H3 partition, or `select_citations`. The risk level and all
states are computed upstream and only *rendered* here.
Rationale: structural — the new fields are inert with respect to every ADR 0001/0003/0004 invariant.

**Q8 — Should the appendix render for passive (`FundLevelSnapshot`) funds, which have no
`constituent_analyses`?**
A: For passive funds the per-constituent appendix block is **empty** (no `one_line_view` exists — the
look-through is fund-level), but the **footnote table still renders** from the fund's
`thesis_evidence` (NAV + announcement legs), so passive funds still get resolvable citations + inline
summaries. The constituent appendix is gated on `constituent_analyses != ()`.
Rationale: matches the asset-class shape — passive investability is fund-level (no drill-through,
CONTEXT.md), so there is no per-constituent prose to render, but the fund-level evidence is still
worth resolving.

### Could not be fully resolved from MASTER-SPEC / handoff / code alone

- **None blocking.** Both M1 (source-text + prose fields) and M2 (scorer-flooring) were fully
  resolvable from the code: `ThesisEvidence.summary` / `ConstituentAnalysis.one_line_view` are the
  prose sources (Q1/Q2), and the `aum_stability_pct`-floor is provable from
  `states.py:346-349` + `decision/completeness.py:22` + the absence of any `aum_stability_pct`
  setter in `populate_inputs` (Q6).
- **Judgment call (resolved, flagged):** whether to also fix the scorer floor. Resolved **out of
  scope** — item 003 makes the floor *visible* (drivers + `—` placeholders) and records the fix as
  **follow-up F-1** below; it does not change `classify_product_quality`.

## Flagged follow-up (bigger than rendering — do NOT change the scorer in item 003)

- **F-1 — `classify_product_quality` floors active funds to `weak` on the unprovidable
  `aum_stability_pct`.** Because `aum_stability_pct` is never ingested (the documented universal
  drop, `decision/completeness.py:22`), the active branch (`states.py:346-349`) can never exceed
  `weak` for a fund with a known manager tenure — making `质量=weak` near-universal and **not** a
  real product judgment. The principled fix is to give the active branch an `evidence_insufficient`
  path when the only missing input is the structurally-unprovidable `aum_stability_pct` (so a
  metadata-thin fund reads `evidence_insufficient`, not a defamatory `weak`), OR to drop
  `aum_stability_pct` from the active gate entirely and score on the providable
  expense/AUM/tenure metrics. Either is a **scorer-behaviour change** with H3 / opportunity-state
  ripple — it needs its own slice, spec, and grill (not a renderer change). **Recorded here; not
  implemented in item 003.** (Surfacing the drivers in the `.md`, AC6/AC7, is the interim mitigation
  so an operator can already tell metadata-floored from genuinely-weak.)
